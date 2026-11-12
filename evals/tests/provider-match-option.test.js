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

test("a pasted { command, text } answer needs a matching shown command, and option answers win", () => {
  const { pickAnswer, lastShownCommand } = require("../providers/claude-skill-agent-sdk");
  const run = [{ id: "done", label: "Done, here's the output" }, { id: "skip", label: "Skip" }];
  const plan = [{ id: "use", label: "Use this plan" }, { id: "other", label: "Choose another" }];
  const list = { command: "^GET .*/flag-release-plans$", text: "{\"items\":[]}\nHTTP 200" };
  const create = { command: "^POST .*/flag-release-plans$", text: "{\"key\":\"default-release\"}\nHTTP 201" };
  const answers = [create, list, ["Use this plan"]];
  const used = new Set();
  // A plan question takes the option answer, not a paste.
  assert.deepEqual(pickAnswer(answers, 0, plan, true, used, "GET /api/v2/projects/default/flag-release-plans"), ["use"]);
  // The list step takes the list paste, not the earlier create paste.
  assert.deepEqual(pickAnswer(answers, 1, run, true, used, "GET /api/v2/projects/default/flag-release-plans"), [list.text]);
  // No shown command: no paste.
  assert.equal(pickAnswer(answers, 2, run, true, used, ""), undefined);
  assert.deepEqual(pickAnswer(answers, 2, run, true, used, "POST /api/v2/projects/default/flag-release-plans"), [create.text]);
  // An option answer that fits a run question wins over a paste.
  assert.deepEqual(pickAnswer([list, ["Skip"]], 0, run, true, new Set(), "GET /api/v2/projects/default/flag-release-plans"), ["skip"]);
  assert.deepEqual(pickAnswer([{ text: "pasted" }], 0, run, false, new Set(), ""), ["pasted"]);

  const block = (cmd) => "```sh\n" + cmd + "\n```";
  const get = 'curl -sS -H "LD-API-Version: beta" "https://app.launchdarkly.com/api/v2/projects/default/flag-release-plans?limit=50"';
  const post = 'curl -sS -X POST -H "LD-API-Version: beta" "https://app.launchdarkly.com/api/v2/projects/default/flag-release-plans" --data @- <<\'JSON\'\n{}\nJSON';
  assert.equal(lastShownCommand([block(get)]), "GET /api/v2/projects/default/flag-release-plans");
  assert.equal(lastShownCommand([block(get), "then", block(post)]), "POST /api/v2/projects/default/flag-release-plans");
  assert.equal(lastShownCommand(["no command here"]), "");
});

test("scrubLdCredentials removes LaunchDarkly credentials and keeps the rest", () => {
  const { scrubLdCredentials } = require("../providers/claude-skill-agent-sdk");
  const env = scrubLdCredentials({ LD_ACCESS_TOKEN: "real", LD_BASE_URI: "x", LAUNCHDARKLY_API_KEY: "y", PATH: "/bin", LD_LIBRARY_PATH: "/lib" });
  assert.deepEqual(env, { PATH: "/bin", LD_LIBRARY_PATH: "/lib" });
});
