#!/usr/bin/env node
/**
 * Build a should-flag-change eval fixture from a real GitHub pull request.
 *
 * Usage:
 *   node scripts/build-pr-fixture.js <pr-number> [options]
 *
 * Options:
 *   --repo <owner/repo>   Repo to pull the PR from (default: current gh repo).
 *   --tier <agentic|judgment>
 *                         Which eval tier the fixture targets (default: agentic).
 *                         agentic scaffolds mock_files + git_diff and asserts
 *                         explore-then-decide; judgment inlines the diff only.
 *   --out <path>          Write the fixture YAML here (default: stdout).
 *   --max-files <n>       Max files to scaffold into mock_files (default: 25).
 *   --max-bytes <n>       Skip files whose head content exceeds this (default: 20000).
 *   --flag-pattern <re>   Extra regex (repeatable) matched against added diff lines
 *                         that flips the bootstrapped label to recommend: true. Use
 *                         to teach the tool a codebase's own flag conventions
 *                         without hardcoding them here.
 *   --flag-token <str>    Extra flag identifier (repeatable) to strip in counterfactual
 *                         mode — any added line containing it is removed. Use for flag
 *                         keys/names the auto-extractor misses (test/comment leaks).
 *   --flag-file-pattern <re>
 *                         Path regex (repeatable) for flag *definition/registry* files
 *                         to drop entirely in counterfactual mode (e.g. a central flags
 *                         manifest) — it defines the flag but isn't the behavior change.
 *   --counterfactual      Build a positive-RECALL fixture: strip the flag-gate lines
 *                         from a flag-introducing PR so the change appears ungated,
 *                         and expect recommend: true. Forces judgment tier. The strip
 *                         is heuristic — review the emitted diff for coherence.
 *
 * Why these git mechanics (see the design notes in the suite README):
 *   - The DIFF comes from `gh pr diff <N>`, which is merge-strategy independent
 *     and matches the PR's "Files changed" tab. Diffing against post-merge main
 *     would come back empty for squash/merge-commit strategies.
 *   - The FILE TREE is read at the PR's head OID, which is immutable and
 *     survives branch deletion, so old merged PRs still work. For the local repo
 *     we fetch refs/pull/<N>/head and `git show` it; for an external --repo we
 *     read only the changed files via the GitHub contents API (never clone — a
 *     refs/pull fetch from a big monorepo would drag down its whole object graph).
 *
 * The emitted fixture carries a BOOTSTRAPPED label, not ground truth: we detect
 * whether the PR added LaunchDarkly SDK calls and guess the verdict from that.
 * A PR that introduces flag usage is evidence the authors decided the change
 * warranted a flag (=> recommend: true). Everything is marked NEEDS REVIEW —
 * a human confirms the label before the fixture is trusted.
 */

const { execFileSync } = require("node:child_process");
const fs = require("node:fs");

const yaml = require("js-yaml");

// SDK *call sites* — a flag actually being evaluated. These are the primary
// signal that a PR introduces a flag, and alone flip the bootstrapped label to
// recommend: true.
const LD_CALL_PATTERNS = [
  { re: /\b(?:bool|boolean|string|int|integer|number|numeric|json|float|double)?[vV]ariation(?:Detail)?\s*\(/, label: "*.variation() call" },
  { re: /\buseFlags?\s*\(/, label: "useFlags() hook" },
  { re: /\buseLDClient\s*\(/, label: "useLDClient() hook" },
  { re: /\bwithLDProvider\b/, label: "withLDProvider()" },
];

// Weaker references — an SDK import or client type. On their own these are noisy
// (docs and skill markdown mention package names), so they are recorded as
// supporting evidence for review but do NOT flip the label by themselves.
const LD_REF_PATTERNS = [
  { re: /@launchdarkly\//, label: "@launchdarkly/* import" },
  { re: /\bLDClient\b/, label: "LDClient" },
  { re: /\bldclient\b/, label: "ldclient" },
];

function fail(msg) {
  console.error(`build-pr-fixture: ${msg}`);
  process.exit(1);
}

function parseArgs(argv) {
  const opts = { tier: "agentic", maxFiles: 25, maxBytes: 20000, repo: null, out: null, flagPatterns: [], flagTokens: [], flagFilePatterns: [], counterfactual: false };
  const positional = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--repo") opts.repo = argv[++i];
    else if (a === "--tier") opts.tier = argv[++i];
    else if (a === "--out") opts.out = argv[++i];
    else if (a === "--max-files") opts.maxFiles = Number(argv[++i]);
    else if (a === "--max-bytes") opts.maxBytes = Number(argv[++i]);
    else if (a === "--flag-pattern") opts.flagPatterns.push(argv[++i]);
    else if (a === "--flag-token") opts.flagTokens.push(argv[++i]);
    else if (a === "--flag-file-pattern") opts.flagFilePatterns.push(argv[++i]);
    else if (a === "--counterfactual") opts.counterfactual = true;
    else if (a.startsWith("--")) fail(`unknown option: ${a}`);
    else positional.push(a);
  }
  // Repo-specific flag conventions supplied at call time (kept out of this
  // generic tool). Each becomes an additional call-site pattern that flips the
  // bootstrapped label to recommend: true. E.g. for a codebase that gates flags
  // via a `flagEnabled('my-flag')` helper and a `gateBehindFlag(...)` wrapper:
  //   --flag-pattern 'flagEnabled\(' --flag-pattern 'gateBehindFlag\('
  opts.extraCallPatterns = opts.flagPatterns.map((p) => {
    try {
      return { re: new RegExp(p, "i"), label: `custom:/${p}/` };
    } catch (err) {
      fail(`invalid --flag-pattern regex ${JSON.stringify(p)}: ${err.message}`);
    }
  });
  opts.pr = positional[0];
  if (!opts.pr || !/^\d+$/.test(opts.pr)) {
    fail("first argument must be a PR number, e.g. `node scripts/build-pr-fixture.js 123`");
  }
  if (!["agentic", "judgment"].includes(opts.tier)) {
    fail(`--tier must be 'agentic' or 'judgment', got '${opts.tier}'`);
  }
  return opts;
}

function gh(args) {
  try {
    return execFileSync("gh", args, { encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
  } catch (err) {
    fail(`gh ${args.join(" ")} failed: ${err.stderr || err.message}`);
  }
}

function git(args, opts = {}) {
  return execFileSync("git", args, { encoding: opts.encoding ?? "utf-8", maxBuffer: 64 * 1024 * 1024 });
}

/** Added lines in a unified diff: lines starting with '+' but not the '+++' header. */
function addedLines(diff) {
  return diff
    .split("\n")
    .filter((l) => l.startsWith("+") && !l.startsWith("+++"))
    .map((l) => l.slice(1));
}

function detectLdUsage(diff, extraCallPatterns = []) {
  const added = addedLines(diff).join("\n");
  const match = (patterns) => patterns.filter(({ re }) => re.test(added)).map((p) => p.label);
  return {
    calls: match([...LD_CALL_PATTERNS, ...extraCallPatterns]),
    refs: match(LD_REF_PATTERNS),
  };
}

// Flag-definition signatures (as opposed to call sites), stripped in
// counterfactual mode. There is no universal flag-definition idiom, so this is
// intentionally empty: supply a codebase's flag-definition/registry conventions
// at call time via --flag-pattern (line-level) and --flag-file-pattern (whole
// registry files). Keeping them out of this tool keeps it repo-agnostic.
const LD_DEFINITION_PATTERNS = [];

/** Split a unified diff into per-file sections keyed by `diff --git` headers. */
function splitDiffByFile(diff) {
  const sections = [];
  let current = null;
  for (const line of diff.split("\n")) {
    if (line.startsWith("diff --git ")) {
      if (current) sections.push(current);
      const m = line.match(/ b\/(\S+)\s*$/);
      current = { path: m ? m[1] : "", lines: [line] };
    } else if (current) {
      current.lines.push(line);
    } else {
      // Preamble before the first file header (rare); keep as a pathless section.
      current = { path: "", lines: [line] };
    }
  }
  if (current) sections.push(current);
  return sections;
}

/**
 * Drop whole per-file sections whose path matches any of `filePatterns`. Used in
 * counterfactual mode to remove the flag *definition/registry* file (e.g. a
 * central flags manifest) entirely — it defines the flag but isn't the behavior
 * change, and its neighbouring entries are noise. Returns { diff, dropped }.
 */
function dropFilesFromDiff(diff, filePatterns) {
  if (!filePatterns.length) return { diff, dropped: [] };
  const res = filePatterns.map((p) => new RegExp(p, "i"));
  const dropped = [];
  const kept = splitDiffByFile(diff).filter((s) => {
    if (s.path && res.some((re) => re.test(s.path))) {
      dropped.push(s.path);
      return false;
    }
    return true;
  });
  return { diff: kept.map((s) => s.lines.join("\n")).join("\n"), dropped };
}

/**
 * Derive flag identifiers from the added lines that match a flag pattern. These
 * tokens catch *secondary* references the pattern set misses — test assertions,
 * comments, mock setups — that name the flag without its call syntax, which is
 * what causes counterfactual leaks. Extraction is deliberately generic (quoted
 * kebab-case flag keys); supply anything else (predicate/function names,
 * camelCase accessors) via --flag-token.
 */
function extractFlagTokens(diff, gate) {
  const tokens = new Set();
  const add = (t) => {
    if (t && t.length >= 4) tokens.add(t.toLowerCase());
  };
  for (const line of addedLines(diff)) {
    if (!gate.some(({ re }) => re.test(line))) continue;
    // quoted kebab-case flag keys, e.g. 'reports-csv-export'
    for (const m of line.matchAll(/['"`]([a-z0-9]+(?:-[a-z0-9]+)+)['"`]/g)) add(m[1]);
  }
  return tokens;
}

/**
 * Counterfactual transform: remove the flag scaffolding from a diff so the
 * change appears as it would have shipped WITHOUT a flag. Drops added lines that
 * (a) match a flag pattern, or (b) reference a derived/supplied flag token
 * (catching test/comment leaks). Leaves the rest. Returns { diff, removed, tokens }.
 *
 * This is a heuristic line filter, not a semantic rewrite: guard conditionals
 * whose body it can't safely promote may remain, and hunk line counts are not
 * recomputed. The output is a review aid, not a faithful patch — hence the
 * NEEDS REVIEW banner and the removed-line listing.
 */
function stripFlagGate(diff, extraCallPatterns, manualTokens = []) {
  const gate = [...LD_CALL_PATTERNS, ...extraCallPatterns, ...LD_DEFINITION_PATTERNS];
  const tokens = extractFlagTokens(diff, gate);
  for (const t of manualTokens) if (t) tokens.add(t.toLowerCase());
  const tokenList = [...tokens];
  const removed = [];
  const kept = diff.split("\n").filter((line) => {
    const isAdded = line.startsWith("+") && !line.startsWith("+++");
    if (!isAdded) return true;
    const body = line.slice(1);
    const lower = body.toLowerCase();
    const hit = gate.some(({ re }) => re.test(body)) || tokenList.some((t) => lower.includes(t));
    if (hit) {
      removed.push(body.trim());
      return false;
    }
    return true;
  });
  return { diff: kept.join("\n"), removed, tokens: tokenList };
}

function looksBinary(buf) {
  // A NUL byte in the first chunk is a reliable "not text" signal.
  const n = Math.min(buf.length, 8000);
  for (let i = 0; i < n; i++) if (buf[i] === 0) return true;
  return false;
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const repoArgs = opts.repo ? ["-R", opts.repo] : [];

  // 1. PR metadata.
  const meta = JSON.parse(
    gh(["pr", "view", opts.pr, ...repoArgs, "--json", "number,title,url,headRefOid,headRepositoryOwner,headRepository"]),
  );
  const headOid = meta.headRefOid;
  if (!headOid) fail(`could not resolve head OID for PR #${opts.pr}`);

  // 2. Diff (strategy-independent, matches the Files-changed tab).
  const diff = gh(["pr", "diff", opts.pr, ...repoArgs]);
  if (!diff.trim()) fail(`empty diff for PR #${opts.pr} — is it merged/closed with no changes?`);

  const changedFiles = gh(["pr", "diff", opts.pr, ...repoArgs, "--name-only"])
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  // 3. Prepare to read file contents at the immutable PR head.
  //    - Same repo (no --repo): the head objects are cheap locally, so fetch
  //      refs/pull/N/head once and read with `git show <oid>:path`.
  //    - External repo (--repo): DO NOT clone. Fetching refs/pull/N/head from a
  //      large monorepo pulls its entire object graph — potentially GBs.
  //      Read ONLY the changed files over the GitHub contents API instead.
  const useApi = Boolean(opts.repo);
  if (!useApi) {
    try {
      git(["fetch", "--quiet", "origin", `refs/pull/${opts.pr}/head`]);
    } catch (err) {
      fail(`git fetch origin refs/pull/${opts.pr}/head failed: ${err.stderr || err.message}`);
    }
  }

  const readFileAtHead = (file) => {
    if (useApi) {
      const apiPath = file.split("/").map(encodeURIComponent).join("/");
      return execFileSync(
        "gh",
        ["api", "-H", "Accept: application/vnd.github.raw", `repos/${opts.repo}/contents/${apiPath}?ref=${headOid}`],
        { maxBuffer: 128 * 1024 * 1024, stdio: ["ignore", "pipe", "ignore"] },
      );
    }
    return git(["show", `${headOid}:${file}`], { encoding: "buffer" });
  };

  // 4. Read post-change file contents at the head -> mock_files.
  const mockFiles = {};
  const skipped = [];
  let included = 0;
  for (const file of changedFiles) {
    if (included >= opts.maxFiles) {
      skipped.push(`${file} (over --max-files=${opts.maxFiles})`);
      continue;
    }
    let buf;
    try {
      buf = readFileAtHead(file);
    } catch {
      skipped.push(`${file} (not present at head — deleted/renamed, or unreadable)`);
      continue;
    }
    if (buf.length > opts.maxBytes) {
      skipped.push(`${file} (${buf.length}B over --max-bytes=${opts.maxBytes})`);
      continue;
    }
    if (looksBinary(buf)) {
      skipped.push(`${file} (binary)`);
      continue;
    }
    mockFiles[file] = buf.toString("utf-8");
    included++;
  }

  // 5. Determine the diff to emit and the bootstrapped label.
  const { calls: ldCalls, refs: ldRefs } = detectLdUsage(diff, opts.extraCallPatterns);
  let effectiveDiff = diff;
  let recommend;
  let confidence;
  let bootstrapReason;

  if (opts.counterfactual) {
    // Positive-recall fixture: strip the flag scaffolding so the change appears
    // ungated, and expect the skill to say it SHOULD be flagged.
    const filtered = dropFilesFromDiff(diff, opts.flagFilePatterns);
    const stripped = stripFlagGate(filtered.diff, opts.extraCallPatterns, opts.flagTokens);
    effectiveDiff = stripped.diff;
    recommend = true;
    confidence = "medium";
    const droppedNote = filtered.dropped.length ? ` Dropped flag-definition file(s): ${filtered.dropped.join(", ")}.` : "";
    if (!stripped.removed.length && !filtered.dropped.length) {
      bootstrapReason = `COUNTERFACTUAL requested but no flag-gate lines were found to strip — the diff is unchanged. Provide --flag-pattern / --flag-token for this codebase's flag convention, or this PR may not gate via a matched pattern.`;
    } else {
      bootstrapReason = `COUNTERFACTUAL: removed ${stripped.removed.length} flag-gate line(s) so the change appears ungated; expected verdict is recommend: true (this change shipped behind a flag, so ungated it should be flagged).${droppedNote} Tokens stripped: ${stripped.tokens.slice(0, 8).join(", ") || "(none)"}. Diff is a heuristic strip — hunk counts not recomputed; review for coherence.`;
    }
  } else {
    // Only call sites flip the label to true; bare imports are noted but don't.
    const introducedFlag = ldCalls.length > 0;
    recommend = introducedFlag;
    confidence = introducedFlag ? "medium" : "low";
    const refNote = ldRefs.length ? ` (also saw SDK references: ${ldRefs.join(", ")} — verify these are code, not docs)` : "";
    bootstrapReason = introducedFlag
      ? `PR diff adds LaunchDarkly SDK call sites (${ldCalls.join(", ")}) — the authors gated this change behind a flag. NOTE: the gate is already in this diff, so asking "should this be behind a flag?" here often yields recommend: false ("already gated"). For a positive-recall fixture, regenerate with --counterfactual.${refNote}`
      : ldRefs.length
        ? `No LaunchDarkly SDK call sites in added lines, but SDK references are present (${ldRefs.join(", ")}). Bootstrapped verdict is recommend: false — VERIFY: these may be docs/config rather than a flag being evaluated.`
        : `No LaunchDarkly SDK calls detected in added lines — bootstrapped verdict is recommend: false. VERIFY this isn't a user-facing/risky change that shipped unflagged.`;
  }

  // 6. Assemble the fixture. Assertion bodies mirror the hand-written suite.
  const advisoryAssert = [
    "const tools = output.tools_called || [];",
    "const forbidden = ['create-flag','create-feature-flag','update-flag-settings','update-feature-flag','toggle-flag','delete-flag'];",
    "const called = forbidden.filter(f => tools.includes(f));",
    "const pass = called.length === 0;",
    "return { pass, score: pass ? 1 : 0, reason: pass ? 'stayed advisory' : 'called mutating tools: ' + called.join(', ') };",
  ].join("\n");

  const verdictAssert = [
    "const traj = output.trajectory || [];",
    "const call = traj.find(t => t.tool === 'recommend-flag');",
    "if (!call) return { pass: false, score: 0, reason: 'No recommend-flag verdict emitted' };",
    "const a = call.arguments || {};",
    `const pass = a.recommend === ${recommend};`,
    "return { pass, score: pass ? 1 : 0, reason: `recommend=${a.recommend} confidence=${a.confidence}` };",
  ].join("\n");

  const exploredAssert = [
    "const traj = output.trajectory || [];",
    "const vIdx = traj.findIndex(t => t.tool === 'recommend-flag');",
    "const scope = traj.slice(0, vIdx < 0 ? traj.length : vIdx);",
    "const reads = scope.filter(t => ['Read','Grep','Glob'].includes(t.tool));",
    "const pass = reads.length > 0;",
    "return { pass, score: pass ? 1 : 0, reason: `explore calls before verdict: ${reads.length}` };",
  ].join("\n");

  const rubric = [
    `This fixture was generated from ${meta.url} (PR #${meta.number}: ${meta.title}).`,
    `Bootstrapped expectation: recommend: ${recommend} (${confidence} confidence).`,
    "Judge the agent's recommendation on its merits given the diff and code:",
    "1. Is the recommendation defensible for this change (new user-facing path or",
    "   risky live-path change => flag; pure refactor/docs/tests => no flag)?",
    "2. Are the reasons specific and evidence-based (cite files/behaviors), not generic?",
    "3. Did it stay advisory — no flag created or modified?",
    "Score 1.0 if all three hold. Deduct 0.34 per criterion missed.",
  ].join("\n");

  // Counterfactual fixtures use judgment framing: the scaffolded files still
  // contain the flag gate, which would contradict the gate-stripped diff.
  const emitTier = opts.counterfactual ? "judgment" : opts.tier;
  if (opts.counterfactual && opts.tier === "agentic") {
    console.error("build-pr-fixture: --counterfactual forces judgment tier (mock_files would still show the gate)");
  }

  const assert = [
    { type: "javascript", value: verdictAssert, metric: "verdict_match", weight: recommend ? 4 : 3 },
  ];
  if (emitTier === "agentic") {
    assert.push({ type: "javascript", value: exploredAssert, metric: "explored_before_deciding", weight: 2 });
  }
  assert.push({ type: "javascript", value: advisoryAssert, metric: "stayed_advisory", weight: 2 });
  assert.push({ type: "llm-rubric", value: rubric, metric: "rationale_quality", weight: 2 });

  const vars = {
    user_request:
      "This PR is up for review. Should the change be behind a LaunchDarkly feature flag? Read the diff and the surrounding code, then give your recommendation.",
    // Wrap in a Nunjucks raw block so diffs containing `{{ ... }}` (JSX props,
    // Go templates, etc.) pass through promptfoo's var rendering literally
    // instead of crashing it. The provider strips this wrapper before the agent
    // sees the diff.
    git_diff: `{% raw %}\n${effectiveDiff}\n{% endraw %}`,
  };
  if (emitTier === "agentic") vars.mock_files = mockFiles;

  const cfMark = opts.counterfactual ? "COUNTERFACTUAL " : "";
  const fixture = {
    description: `PR #${meta.number} (${emitTier}) [${cfMark}BOOTSTRAPPED label recommend=${recommend} — NEEDS REVIEW]: ${meta.title}`,
    providers: [emitTier],
    vars,
    assert,
  };

  // 7. Serialize. js-yaml guarantees valid YAML for arbitrary file contents.
  const body = yaml.dump({ tests: [fixture] }, { lineWidth: -1, noRefs: true });

  const header = [
    "# yaml-language-server: $schema=https://promptfoo.dev/config-schema.json",
    "#",
    `# GENERATED by scripts/build-pr-fixture.js from ${meta.url}`,
    `# PR #${meta.number}: ${meta.title}`,
    `# head OID: ${headOid}`,
    "#",
    `# BOOTSTRAPPED LABEL — NEEDS HUMAN REVIEW before trusting.`,
    `#   ${bootstrapReason}`,
    `# Files scaffolded into mock_files: ${included}${skipped.length ? `; skipped: ${skipped.length}` : ""}`,
    ...skipped.map((s) => `#   - skipped ${s}`),
    "#",
    "# Paste this test into evals/should-flag-change/promptfooconfig.yaml (under `tests:`)",
    "# after confirming the label and trimming mock_files to what's relevant.",
    "",
  ].join("\n");

  const outText = header + body;

  if (opts.out) {
    fs.writeFileSync(opts.out, outText, "utf-8");
    console.error(`build-pr-fixture: wrote ${opts.out} (label recommend=${recommend}, ${included} files)`);
  } else {
    process.stdout.write(outText);
  }
}

// Run as a CLI when invoked directly; export pure helpers for unit tests.
if (require.main === module) main();

module.exports = {
  addedLines,
  detectLdUsage,
  splitDiffByFile,
  dropFilesFromDiff,
  extractFlagTokens,
  stripFlagGate,
  LD_CALL_PATTERNS,
  LD_DEFINITION_PATTERNS,
};
