#!/usr/bin/env node
/**
 * Run skill eval suites and aggregate results into eval-scores.json at the
 * repo root.
 *
 * Modes:
 *   node scripts/aggregate.js              # rebuild from existing results.json
 *   node scripts/aggregate.js --run        # run every suite then aggregate
 *   node scripts/aggregate.js --run --only=configs-create,configs-update
 *   node scripts/aggregate.js --run --only=release-autopilot-onboarding#2
 *                                          # shard 2 of the suite's manifest `shards`
 *   node scripts/aggregate.js --run --only=launchdarkly-release-plans --shard=1/2
 *
 * Shards are described in scripts/shards.js. A sharded run writes
 * results.shard-<i>-of-<n>.json; aggregating without --run merges a suite's
 * shard files into one score.
 *
 * Exits 0 on success, 1 on failure.
 */

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const { SUITES } = require("./_manifest");
const shards = require("./shards");

const REPO_ROOT = path.resolve(__dirname, "../..");
const EVALS_DIR = path.resolve(__dirname, "..");
const SCORES_PATH = path.join(REPO_ROOT, "eval-scores.json");
const PROMPTFOO_BIN = path.join(EVALS_DIR, "node_modules", ".bin", "promptfoo");

function parseArgs(argv) {
  const args = { run: false, only: null, shard: null };
  for (const arg of argv.slice(2)) {
    if (arg === "--run") args.run = true;
    else if (arg.startsWith("--shard=")) args.shard = shards.parseShard(arg.slice("--shard=".length));
    else if (arg.startsWith("--only=")) {
      args.only = arg.slice("--only=".length).split(",").map((s) => s.trim()).filter(Boolean);
    } else if (arg === "--help" || arg === "-h") {
      process.stdout.write("Usage: aggregate.js [--run] [--only=<slug[#i],slug,...>] [--shard=<i/n>]\n");
      process.exit(0);
    }
  }
  return args;
}

// Returns [{ suite, shard }] in manifest order. A "<slug>#i" entry selects
// shard i of the suite's manifest `shards`; --shard=i/n applies to every
// selected suite that has no "#i".
function selectSuites(only, shardArg = null) {
  const entries = (only && only.length > 0 ? only : SUITES.map((s) => s.suite)).map(shards.parseEntry);
  const unknown = entries.filter((e) => !SUITES.find((suite) => suite.suite === e.suite)).map((e) => e.suite);
  if (unknown.length > 0) {
    console.error(`aggregate.js: unknown suite slugs: ${unknown.join(", ")}`);
    console.error(`Known suites: ${SUITES.map((s) => s.suite).join(", ")}`);
    process.exit(1);
  }
  const picked = [];
  for (const suite of SUITES) {
    for (const e of entries.filter((x) => x.suite === suite.suite)) {
      let shard = shardArg;
      if (e.index !== null) {
        const count = suite.shards || 1;
        if (e.index < 1 || e.index > count) {
          console.error(`aggregate.js: ${suite.suite} has ${count} shard(s); no shard ${e.index}`);
          process.exit(1);
        }
        shard = { index: e.index, count };
      }
      if (shard && shard.count <= 1) shard = null;
      picked.push({ suite, shard });
    }
  }
  return picked;
}

function headCommit() {
  const r = spawnSync("git", ["rev-parse", "--short", "HEAD"], {
    cwd: REPO_ROOT,
    encoding: "utf-8",
  });
  return r.status === 0 ? r.stdout.trim() : null;
}

const suiteDir = (suite) => path.join(EVALS_DIR, suite.suite);
const outFileFor = (suite, shard) => path.join(suiteDir(suite), shard ? shards.shardFile(shard.index, shard.count) : "results.json");

// Removes result files this run would make stale: an unsharded run removes
// shard files, and a sharded run removes results.json and files from
// another shard count.
function clearStaleResults(suite, shard) {
  const dir = suiteDir(suite);
  const stale = shards.listShardFiles(dir).filter((f) => !shard || f.count !== shard.count).map((f) => f.name);
  if (shard) stale.push("results.json");
  for (const name of stale) fs.rmSync(path.join(dir, name), { force: true });
}

function runSuite(suite, shard = null) {
  const outFile = outFileFor(suite, shard);
  const label = `${suite.suite}${shard ? ` (shard ${shard.index}/${shard.count})` : ""}`;
  console.log(`\n▶ Running eval suite: ${label}`);
  clearStaleResults(suite, shard);

  const filter = [];
  if (shard) {
    const all = shards.loadTests(path.join(suiteDir(suite), "promptfooconfig.yaml"));
    const selected = shards.selectTests(all, shard);
    console.log(`  ${selected.length} of ${all.length} tests: ${selected.map((t) => t.description).join(" | ")}`);
    if (selected.length === 0) {
      fs.writeFileSync(outFile, JSON.stringify({ results: { results: [] } }) + "\n");
      return true;
    }
    if (selected.length < all.length) filter.push("--filter-pattern", shards.filterPattern(selected, all));
  }

  const result = spawnSync(
    PROMPTFOO_BIN,
    [
      "eval",
      "-c", path.join(EVALS_DIR, "shared", "defaults.yaml"),
      "-c", path.join(EVALS_DIR, suite.suite, "promptfooconfig.yaml"),
      ...(fs.existsSync(path.join(EVALS_DIR, ".env")) ? ["--env-file", path.join(EVALS_DIR, ".env")] : []),
      "--no-cache",
      ...filter,
      "-o", outFile,
    ],
    { cwd: EVALS_DIR, stdio: "inherit", env: { ...process.env } },
  );

  // promptfoo exits 100 when tests ran but some failed — that's a valid run,
  // results.json is still written. Treat any other non-zero as a hard failure.
  if (result.status !== 0 && result.status !== 100) {
    console.error(`✗ Suite ${label} exited with status ${result.status}`);
    return false;
  }
  return true;
}

// One shard's results when `shard` is set; otherwise the whole suite,
// merging its shard files when it has them.
function readResults(suite, shard = null) {
  if (shard) {
    const file = outFileFor(suite, shard);
    try {
      return JSON.parse(fs.readFileSync(file, "utf-8"));
    } catch (e) {
      console.error(`aggregate.js: cannot read ${path.basename(file)} for "${suite.suite}": ${e.message}`);
      return null;
    }
  }
  const r = shards.readSuiteResults(suiteDir(suite));
  if (r.error) {
    console.error(`aggregate.js: ${suite.suite}: ${r.error}`);
    return null;
  }
  return r.results;
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
  const picked = selectSuites(args.only, args.shard);
  const commit = headCommit();

  if (args.run) {
    let anyFailed = false;
    for (const { suite, shard } of picked) {
      if (!runSuite(suite, shard)) anyFailed = true;
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

  // A shard's score is reported and checked against the threshold, but
  // only a whole suite (all shards merged) is written to eval-scores.json.
  const below = [];
  const seen = new Set();
  for (const { suite, shard } of picked) {
    if (!shard && seen.has(suite.suite)) continue;
    seen.add(suite.suite);
    const results = readResults(suite, shard);
    if (!results) { anyError = true; continue; }
    const s = summarize(suite, results, commit);
    if (!shard) skills[suite.skillKey] = s;
    annotateFailures(suite, results);
    const icon = s.status === "passing" ? "✓" : "✗";
    const name = `${suite.skillKey}${shard ? ` (shard ${shard.index}/${shard.count})` : ""}`;
    console.log(`${icon} ${name}: ${s.passed}/${s.total} passed (${s.score}%)`);
    if (s.score < 75) below.push(name);
  }

  const output = { schemaVersion: 1, updatedAt: new Date().toISOString(), skills };
  fs.writeFileSync(SCORES_PATH, JSON.stringify(output, null, 2) + "\n");
  console.log(`\nWrote ${SCORES_PATH}`);

  if (below.length > 0) {
    console.error(`\naggregate.js: suites below 75% threshold: ${below.join(", ")}`);
  }
  if (anyError || below.length > 0) process.exit(1);
}

if (require.main === module) main();

module.exports = { annotateFailures, selectSuites, summarize };
