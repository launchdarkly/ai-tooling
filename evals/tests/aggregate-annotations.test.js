const { test } = require("node:test");
const assert = require("node:assert/strict");

// annotateFailures prints one GitHub warning annotation per failed test,
// with the failed assertions' reasons, so CI failures can be read from the
// check run's annotations.
const { annotateFailures } = require("../scripts/aggregate");

function capture(fn) {
  const lines = [];
  const orig = console.log;
  console.log = (l) => lines.push(l);
  try { fn(); } finally { console.log = orig; }
  return lines;
}

test("annotateFailures emits a warning per failed test, escaped, only in GitHub Actions", () => {
  const results = { results: { results: [
    { success: true, description: "ok" },
    { success: false, description: "Create:\nplan", gradingResult: { componentResults: [{ pass: false, reason: "no create\ncommand", assertion: { metric: "plan_shape" } }, { pass: true, reason: "fine" }] } },
    { success: false, vars: { user_request: "list plans" }, error: "provider failed" },
  ] } };
  const prev = process.env.GITHUB_ACTIONS;
  try {
    delete process.env.GITHUB_ACTIONS;
    assert.deepEqual(capture(() => annotateFailures({ suite: "demo" }, results)), []);
    process.env.GITHUB_ACTIONS = "true";
    const lines = capture(() => annotateFailures({ suite: "demo" }, results));
    assert.deepEqual(lines, [
      "::warning title=demo: Create:%0Aplan::plan_shape: no create%0Acommand",
      "::warning title=demo: list plans::error: provider failed",
    ]);
  } finally {
    if (prev === undefined) delete process.env.GITHUB_ACTIONS; else process.env.GITHUB_ACTIONS = prev;
  }
});
