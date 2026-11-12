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

test("a pasted { when, text } answer answers the first question whose prompt matches", () => {
  const { pickAnswer } = require("../providers/claude-skill-agent-sdk");
  const options = [{ id: "done", label: "Done, here's the output" }, { id: "skip", label: "Skip" }];
  const answers = [["Skip"], { when: "list", text: "{\"items\":[]}\nHTTP 200" }];
  const used = new Set();
  assert.deepEqual(pickAnswer(answers, 0, options, true, used, "Run this list command"), ["{\"items\":[]}\nHTTP 200"]);
  assert.deepEqual(pickAnswer(answers, 1, options, true, used, "Run this list command"), ["skip"]);
  assert.equal(pickAnswer([{ when: "create", text: "x" }], 0, options, true, new Set(), "Run this list command"), undefined);
  assert.deepEqual(pickAnswer([{ text: "pasted" }], 0, options, false, new Set(), "anything"), ["pasted"]);
});

test("scrubLdCredentials removes LaunchDarkly credentials and keeps the rest", () => {
  const { scrubLdCredentials } = require("../providers/claude-skill-agent-sdk");
  const env = scrubLdCredentials({ LD_ACCESS_TOKEN: "real", LD_BASE_URI: "x", LAUNCHDARKLY_API_KEY: "y", PATH: "/bin", LD_LIBRARY_PATH: "/lib" });
  assert.deepEqual(env, { PATH: "/bin", LD_LIBRARY_PATH: "/lib" });
});
