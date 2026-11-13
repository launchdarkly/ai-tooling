#!/usr/bin/env node
/**
 * Run skill eval suites and aggregate results into eval-scores.json at the
 * repo root.
 *
 * Modes:
 *   node scripts/aggregate.js              # rebuild from existing results.json
 *   node scripts/aggregate.js --run        # run every suite then aggregate
 *   node scripts/aggregate.js --run --only=configs-create,configs-update
 *
 * Exits 0 on success, 1 on failure.
 */

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const { SUITES } = require("./_manifest");

const REPO_ROOT = path.resolve(__dirname, "../..");
const EVALS_DIR = path.resolve(__dirname, "..");
const SCORES_PATH = path.join(REPO_ROOT, "eval-scores.json");
const PROMPTFOO_BIN = path.join(EVALS_DIR, "node_modules", ".bin", "promptfoo");

function parseArgs(argv) {
  const args = { run: false, only: null };
  for (const arg of argv.slice(2)) {
    if (arg === "--run") args.run = true;
    else if (arg.startsWith("--only=")) {
      args.only = arg.slice("--only=".length).split(",").map((s) => s.trim()).filter(Boolean);
    } else if (arg === "--help" || arg === "-h") {
      process.stdout.write("Usage: aggregate.js [--run] [--only=<slug,slug,...>]\n");
      process.exit(0);
    }
  }
  return args;
}

function selectSuites(only) {
  if (!only || only.length === 0) return SUITES.slice();
  const set = new Set(only);
  const matched = SUITES.filter((s) => set.has(s.suite));
  const unknown = only.filter((s) => !SUITES.find((suite) => suite.suite === s));
  if (unknown.length > 0) {
    console.error(`aggregate.js: unknown suite slugs: ${unknown.join(", ")}`);
    console.error(`Known suites: ${SUITES.map((s) => s.suite).join(", ")}`);
    process.exit(1);
  }
  return matched;
}

function headCommit() {
  const r = spawnSync("git", ["rev-parse", "--short", "HEAD"], {
    cwd: REPO_ROOT,
    encoding: "utf-8",
  });
  return r.status === 0 ? r.stdout.trim() : null;
}

function runSuite(suite) {
  const outFile = path.join(EVALS_DIR, suite.suite, "results.json");
  console.log(`\n▶ Running eval suite: ${suite.suite}`);

  const result = spawnSync(
    PROMPTFOO_BIN,
    [
      "eval",
      "-c", path.join(EVALS_DIR, "shared", "defaults.yaml"),
      "-c", path.join(EVALS_DIR, suite.suite, "promptfooconfig.yaml"),
      ...(fs.existsSync(path.join(EVALS_DIR, ".env")) ? ["--env-file", path.join(EVALS_DIR, ".env")] : []),
      "--no-cache",
      "-o", outFile,
    ],
    { cwd: EVALS_DIR, stdio: "inherit", env: { ...process.env } },
  );

  // promptfoo exits 100 when tests ran but some failed — that's a valid run,
  // results.json is still written. Treat any other non-zero as a hard failure.
  if (result.status !== 0 && result.status !== 100) {
    console.error(`✗ Suite ${suite.suite} exited with status ${result.status}`);
    return false;
  }
  return true;
}

function readResults(suite) {
  const outFile = path.join(EVALS_DIR, suite.suite, "results.json");
  if (!fs.existsSync(outFile)) {
    console.error(`aggregate.js: results.json not found for "${suite.suite}" — run with --run first`);
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(outFile, "utf-8"));
  } catch (e) {
    console.error(`aggregate.js: failed to parse results.json for "${suite.suite}": ${e.message}`);
    return null;
  }
}

function summarize(suite, results, commit) {
  const tests = results?.results?.results || results?.results || [];
  const arr = Array.isArray(tests) ? tests : [];
  const total = arr.length;
  const passed = arr.filter((t) => t.success).length;
  const score = total > 0 ? Math.round((passed / total) * 100) : 0;
  const perTest = arr.map((t) => ({
    description: t.description || t.vars?.user_request?.slice(0, 80) || "",
    pass: t.success,
    score: t.score ?? (t.success ? 1.0 : 0.0),
  }));

  return {
    score,
    passed,
    total,
    status: score >= 75 ? "passing" : "failing",
    lastCommit: commit || null,
    lastRun: new Date().toISOString(),
    perTest,
  };
}

// In GitHub Actions, emit one warning annotation per failed test with the
// failed assertions' reasons. Check run annotations can be read where the
// job log cannot (for example through a proxy that does not follow log
// redirects).
function annotateFailures(suite, results) {
  if (!process.env.GITHUB_ACTIONS) return;
  const tests = results?.results?.results || results?.results || [];
  // GitHub workflow command escaping: escapeData for the message, and
  // escapeProperty (which also encodes ":" and ",") for the title.
  const escData = (v) => String(v).replace(/%/g, "%25").replace(/\r/g, "%0D").replace(/\n/g, "%0A");
  const escProp = (v) => escData(v).replace(/:/g, "%3A").replace(/,/g, "%2C");
  for (const t of Array.isArray(tests) ? tests : []) {
    if (t.success) continue;
    const parts = (t.gradingResult?.componentResults || [])
      .filter((c) => !c.pass)
      .map((c) => `${c.assertion?.metric || c.assertion?.value || "assert"}: ${c.reason || ""}`);
    if (t.error) parts.unshift(`error: ${t.error}`);
    // What the agent did: its tool calls and the start of its final reply.
    let out = t.response?.output;
    try { out = typeof out === "string" ? JSON.parse(out) : out; } catch { out = null; }
    if (out && typeof out === "object") {
      if (Array.isArray(out.tools_called)) parts.push(`tools: ${out.tools_called.join(",").slice(0, 400)}`);
      if (out.terminated) parts.push(`terminated: ${out.terminated}`);
      if (out.response) parts.push(`reply: ${String(out.response).slice(0, 400)}`);
    }
    const name = t.description || t.testCase?.description || t.vars?.user_request?.slice(0, 80) || "test";
    console.log(`::warning title=${escProp(`${suite.suite}: ${String(name).slice(0, 160)}`)}::${escData(parts.join(" | ").slice(0, 1500))}`);
  }
}

function main() {
  const args = parseArgs(process.argv);
  const suites = selectSuites(args.only);
  const commit = headCommit();

  if (args.run) {
    let anyFailed = false;
    for (const suite of suites) {
      if (!runSuite(suite)) anyFailed = true;
    }
    if (anyFailed) {
      console.error("\naggregate.js: one or more suites failed to run.");
      process.exit(1);
    }
  }

  let existing = {};
  if (fs.existsSync(SCORES_PATH)) {
    try {
      existing = JSON.parse(fs.readFileSync(SCORES_PATH, "utf-8")).skills || {};
    } catch {
      existing = {};
    }
  }

  const skills = { ...existing };
  let anyError = false;

  for (const suite of suites) {
    const results = readResults(suite);
    if (!results) { anyError = true; continue; }
    skills[suite.skillKey] = summarize(suite, results, commit);
    annotateFailures(suite, results);
    const s = skills[suite.skillKey];
    const icon = s.status === "passing" ? "✓" : "✗";
    console.log(`${icon} ${suite.skillKey}: ${s.passed}/${s.total} passed (${s.score}%)`);
  }

  const output = { schemaVersion: 1, updatedAt: new Date().toISOString(), skills };
  fs.writeFileSync(SCORES_PATH, JSON.stringify(output, null, 2) + "\n");
  console.log(`\nWrote ${SCORES_PATH}`);

  const belowThreshold = suites
    .filter((suite) => skills[suite.skillKey] && skills[suite.skillKey].score < 75)
    .map((suite) => suite.skillKey);
  if (belowThreshold.length > 0) {
    console.error(`\naggregate.js: suites below 75% threshold: ${belowThreshold.join(", ")}`);
  }
  if (anyError || belowThreshold.length > 0) process.exit(1);
}

if (require.main === module) main();

module.exports = { annotateFailures };
