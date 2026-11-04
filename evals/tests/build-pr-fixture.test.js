const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  addedLines,
  detectLdUsage,
  splitDiffByFile,
  dropFilesFromDiff,
  extractFlagTokens,
  stripFlagGate,
  LD_CALL_PATTERNS,
} = require("../scripts/build-pr-fixture");

// A small unified diff: one new gated endpoint plus a test reference.
const GATED_DIFF = [
  "diff --git a/src/routes/reports.js b/src/routes/reports.js",
  "index 2c1d3e4..7a8b9c0 100644",
  "--- a/src/routes/reports.js",
  "+++ b/src/routes/reports.js",
  "@@ -1,3 +1,8 @@",
  " const router = require('express').Router();",
  "+router.get('/export', async (req, res) => {",
  "+  const on = await client.variation('reports-csv-export', ctx, false);",
  "+  if (!on) return res.status(404).end();",
  "+  res.send(await buildCsv());",
  "+});",
  " module.exports = router;",
].join("\n");

const REGISTRY_DIFF = [
  "diff --git a/src/flags.js b/src/flags.js",
  "--- a/src/flags.js",
  "+++ b/src/flags.js",
  "@@ -1 +1,2 @@",
  "+export const reportsCsvExport = defineFlag('reports-csv-export');",
  "diff --git a/src/routes/reports.js b/src/routes/reports.js",
  "--- a/src/routes/reports.js",
  "+++ b/src/routes/reports.js",
  "@@ -1 +1,2 @@",
  "+router.get('/export', h);",
].join("\n");

// ---------------------------------------------------------------------------
// addedLines
// ---------------------------------------------------------------------------

test("addedLines returns added content lines without the + prefix", () => {
  const lines = addedLines(GATED_DIFF);
  assert.ok(lines.includes("router.get('/export', async (req, res) => {"));
  assert.ok(lines.some((l) => l.includes("client.variation(")));
});

test("addedLines excludes the +++ header and context lines", () => {
  const lines = addedLines(GATED_DIFF);
  assert.ok(!lines.some((l) => l.startsWith("+ b/")));
  assert.ok(!lines.includes(" module.exports = router;"));
  assert.ok(!lines.includes("module.exports = router;"));
});

// ---------------------------------------------------------------------------
// detectLdUsage
// ---------------------------------------------------------------------------

test("detectLdUsage flags an SDK call site (variation)", () => {
  const { calls } = detectLdUsage(GATED_DIFF);
  assert.ok(calls.length > 0, "expected a call-site match for client.variation(");
});

test("detectLdUsage treats a bare import as a ref, not a call", () => {
  const diff = "@@ -1 +1,2 @@\n+import { init } from '@launchdarkly/node-server-sdk';\n";
  const { calls, refs } = detectLdUsage(diff);
  assert.equal(calls.length, 0);
  assert.ok(refs.length > 0);
});

test("detectLdUsage picks up a caller-supplied extra pattern", () => {
  const diff = "@@ -1 +1,2 @@\n+  if (flagEnabled('x')) doThing();\n";
  const before = detectLdUsage(diff);
  assert.equal(before.calls.length, 0, "generic patterns should not match flagEnabled(");
  const after = detectLdUsage(diff, [{ re: /flagEnabled\(/, label: "custom" }]);
  assert.ok(after.calls.includes("custom"));
});

// ---------------------------------------------------------------------------
// splitDiffByFile / dropFilesFromDiff
// ---------------------------------------------------------------------------

test("splitDiffByFile splits sections and captures the b/ path", () => {
  const sections = splitDiffByFile(REGISTRY_DIFF);
  assert.equal(sections.length, 2);
  assert.deepEqual(sections.map((s) => s.path), ["src/flags.js", "src/routes/reports.js"]);
});

test("dropFilesFromDiff removes whole matching file sections", () => {
  const { diff, dropped } = dropFilesFromDiff(REGISTRY_DIFF, ["flags\\.js$"]);
  assert.deepEqual(dropped, ["src/flags.js"]);
  assert.ok(!diff.includes("defineFlag"));
  assert.ok(diff.includes("src/routes/reports.js"));
});

test("dropFilesFromDiff is a no-op with no patterns", () => {
  const { diff, dropped } = dropFilesFromDiff(REGISTRY_DIFF, []);
  assert.equal(dropped.length, 0);
  assert.equal(diff, REGISTRY_DIFF);
});

// ---------------------------------------------------------------------------
// extractFlagTokens
// ---------------------------------------------------------------------------

test("extractFlagTokens derives the quoted kebab-case key from a gate line", () => {
  const tokens = extractFlagTokens(GATED_DIFF, LD_CALL_PATTERNS);
  assert.ok(tokens.has("reports-csv-export"));
});

test("extractFlagTokens ignores keys on non-gate lines", () => {
  const diff = "@@ -1 +1,2 @@\n+const label = 'some-plain-string';\n";
  const tokens = extractFlagTokens(diff, LD_CALL_PATTERNS);
  assert.equal(tokens.size, 0);
});

// ---------------------------------------------------------------------------
// stripFlagGate (counterfactual transform)
// ---------------------------------------------------------------------------

test("stripFlagGate removes the gate line and reports it", () => {
  const { diff, removed } = stripFlagGate(GATED_DIFF, []);
  assert.ok(!diff.includes("client.variation("), "gate call line should be stripped");
  assert.ok(diff.includes("res.send(await buildCsv())"), "behavior line should survive");
  assert.ok(removed.some((l) => l.includes("client.variation(")));
});

test("stripFlagGate also strips lines naming a derived flag token", () => {
  const diff = GATED_DIFF + "\n+// TODO: remove reports-csv-export after rollout";
  const { diff: out } = stripFlagGate(diff, []);
  assert.ok(!out.includes("reports-csv-export"), "token-bearing comment should be stripped");
});

test("stripFlagGate honors a manual --flag-token", () => {
  const diff = "@@ -1 +1,3 @@\n+const on = gateBehind('exp');\n+doThing();\n+// gated by ExpFlag\n";
  const { diff: out } = stripFlagGate(diff, [], ["ExpFlag"]);
  assert.ok(!out.includes("ExpFlag"));
  assert.ok(out.includes("doThing();"), "unrelated behavior line should survive");
});

test("stripFlagGate leaves a diff with no gate untouched", () => {
  const diff = "@@ -1 +1,2 @@\n+function add(a, b) { return a + b; }\n";
  const { diff: out, removed } = stripFlagGate(diff, []);
  assert.equal(removed.length, 0);
  assert.equal(out, diff);
});
