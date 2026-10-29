const { test } = require("node:test");
const assert = require("node:assert/strict");

// matchOption resolves a scripted ask-question answer to an option id, so a
// test can steer by label when the agent invents the ids.
const { matchOption, pickAnswer } = require("../providers/claude-skill-agent-sdk");

const options = [
  { id: "af", label: "Auto-flagging (Recommended)" },
  { id: "ar", label: "Auto-releasing" },
];

test("keeps an exact id", () => {
  assert.equal(matchOption("ar", options), "ar");
});

test("matches a label substring, case-insensitively", () => {
  assert.equal(matchOption("auto-flagging", options), "af");
});

test("passes an unmatched answer through", () => {
  assert.equal(matchOption("nothing", options), "nothing");
});

test("tolerates missing options", () => {
  assert.equal(matchOption("x", undefined), "x");
});

test("order mode returns the answer at the call index as written", () => {
  assert.deepEqual(pickAnswer([["x"], ["Auto-releasing"]], 1, options, false, new Set()), ["Auto-releasing"]);
});

test("match mode skips answers that fit no option, and uses each once", () => {
  const used = new Set();
  const answers = [["Looks good"], ["Auto-flagging"], ["Auto-flagging"]];
  assert.deepEqual(pickAnswer(answers, 0, options, true, used), ["af"]);
  assert.deepEqual(pickAnswer(answers, 1, options, true, used), ["af"]);
  assert.equal(pickAnswer(answers, 2, options, true, used), undefined);
});

test("match mode returns undefined when nothing fits", () => {
  assert.equal(pickAnswer([["Looks good"]], 0, options, true, new Set()), undefined);
});

test("order mode keeps an explicit [] as a dismissed question", () => {
  assert.deepEqual(pickAnswer([[]], 0, options, false, new Set()), []);
});
