const { test } = require("node:test");
const assert = require("node:assert/strict");

// matchOption resolves a scripted ask-question answer to an option id, so a
// test can steer by label when the agent invents the ids.
const { matchOption } = require("../providers/claude-skill-agent-sdk");

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
