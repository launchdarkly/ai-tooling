const { test } = require("node:test");
const assert = require("node:assert/strict");

const ra = require("../release-autopilot-onboarding/assertions");

const repoWrite = (args) => ({ tool: "update-release-autopilot", arguments: { accountWide: false, repo: "acme/demo", projectKey: "default", ...args } });
const ask = (prompt, labels = ["Done", "Later"]) => ({
  tool: "ask-question",
  arguments: { prompt, options: labels.map((label, i) => ({ id: String(i), label })) },
});

test("repoTurnsAutoFlaggingOn passes when the mapping turns auto-flagging on", () => {
  const out = { trajectory: [repoWrite({ autoFlagging: { enabled: true }, autoReleasing: { enabled: false } })] };
  assert.equal(ra.repoTurnsAutoFlaggingOn(out).pass, true);
});

test("repoTurnsAutoFlaggingOn fails when the mapping leaves auto-flagging unset", () => {
  const out = { trajectory: [repoWrite({ autoReleasing: { enabled: false } })] };
  assert.equal(ra.repoTurnsAutoFlaggingOn(out).pass, false);
});

test("browser step links must point at the Automations settings page", () => {
  const old = { trajectory: [ask("Open /projects/default/settings/lifecycle and turn on automatic archival. Done?")] };
  const current = { trajectory: [ask("Open /projects/default/settings/automations and turn on automatic archival. Done?")] };
  assert.equal(ra.archivalQuestionHasAutomationsLink(old).pass, false);
  assert.equal(ra.archivalQuestionHasAutomationsLink(current).pass, true);
  assert.equal(ra.cleanupQuestionHasAutomationsLink(current).pass, true);
  assert.equal(ra.byokQuestionHasAutomationsLink({ trajectory: [ask("Open /projects/default/settings/vega. Done?")] }).pass, false);
});

test("previewListsBrowserSteps wants the Automations link in the checklist", () => {
  assert.equal(ra.previewListsBrowserSteps({ trajectory: [], response: "- [ ] In the browser: turn on automated flag cleanup at /projects/default/settings/automations" }).pass, true);
  assert.equal(ra.previewListsBrowserSteps({ trajectory: [], response: "- [ ] In the browser: turn on automated flag cleanup at /projects/default/settings/lifecycle" }).pass, false);
});
