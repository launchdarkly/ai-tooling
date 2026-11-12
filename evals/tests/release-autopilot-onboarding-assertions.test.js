const { test } = require("node:test");
const assert = require("node:assert/strict");

const ra = require("../release-autopilot-onboarding/assertions");

const repoWrite = (args) => ({ tool: "update-automations", arguments: { accountWide: false, repo: "acme/demo", projectKey: "default", ...args } });
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

const kind = { attribute: "kind", op: "in", values: ["user"], contextKind: "user" };
const hold = (allocation) => ({ allocation, durationMillis: 14400000 });
const starter = (allocations) => ({
  trajectory: [
    { tool: "create-environment-release-plan", arguments: { projectKey: "default", environmentKey: "production", key: "progressive", progressiveRelease: {
      randomizationUnit: "user", metrics: {}, phases: [{ clauses: [kind], steps: allocations.map(hold) }],
    } }, mock_response_preview: "{\"key\":\"progressive\"}" },
    { tool: "update-default-environment-release-plan", arguments: { environmentKey: "production", releasePlanKey: "progressive", default: true } },
  ],
});

test("starterPlanProgressive wants 10/25/50 in one phase, set as default", () => {
  assert.equal(ra.starterPlanProgressive(starter([10000, 25000, 50000])).pass, true);
  assert.equal(ra.starterPlanProgressive(starter([10000, 50000])).pass, false);
  assert.equal(ra.starterPlanProgressive({ trajectory: starter([10000, 25000, 50000]).trajectory.slice(0, 1) }).pass, false);
});

test("noProductNameAfterIntro also checks code blocks", () => {
  const out = { trajectory: [], response: "Here's what would change:\n```\n- [ ] Turn on Release Autopilot for acme/demo\n```" };
  assert.equal(ra.noProductNameAfterIntro(out).pass, false);
  assert.equal(ra.noProductNameAfterIntro({ trajectory: [], response: "```\n- [ ] Turn on auto-flagging for acme/demo\n```" }).pass, true);
});

test("stopsReleaseSetupOnPlanError fails on a policy fallback or auto-releasing on", () => {
  assert.equal(ra.stopsReleaseSetupOnPlanError({ trajectory: [repoWrite({ autoFlagging: { enabled: true }, autoReleasing: { enabled: false } })] }).pass, true);
  assert.equal(ra.stopsReleaseSetupOnPlanError({ trajectory: [{ tool: "get-release-policies", arguments: { projectKey: "default" } }] }).pass, false);
  assert.equal(ra.stopsReleaseSetupOnPlanError({ trajectory: [repoWrite({ autoReleasing: { enabled: true } })] }).pass, false);
});

test("saysReplacesDefault looks for the replaced default by name", () => {
  assert.equal(ra.saysReplacesDefault({ trajectory: [], response: "Gradual replaces Fast as the default for production." }).pass, true);
  assert.equal(ra.saysReplacesDefault({ trajectory: [], response: "Gradual becomes the default for production." }).pass, false);
});

test("pausesOnReposError wants a second read, the resume phrase, and no writes", () => {
  const read = { tool: "get-automations", arguments: {} };
  const paused = { trajectory: [read, read], response: "Say \"continue Release Autopilot setup\" once it can be read." };
  assert.equal(ra.pausesOnReposError(paused).pass, true);
  assert.equal(ra.pausesOnReposError({ ...paused, trajectory: [read] }).pass, false);
  assert.equal(ra.pausesOnReposError({ ...paused, trajectory: [read, read, ask("Which repos?", ["acme/demo", "acme/api"])] }).pass, false);
});

test("starterUnitIsUser checks the created plan's randomization unit", () => {
  const plan = (unit) => ({ trajectory: [{ tool: "create-environment-release-plan", arguments: { progressiveRelease: { randomizationUnit: unit } } }] });
  assert.equal(ra.starterUnitIsUser(plan("user")).pass, true);
  assert.equal(ra.starterUnitIsUser(plan("account")).pass, false);
});

test("previewReposErrorNoConnect fails on a Connect GitHub item", () => {
  const ok = { trajectory: [], response: "- [ ] Map acme/demo to project default once the GitHub App install can be read" };
  assert.equal(ra.previewReposErrorNoConnect(ok).pass, true);
  assert.equal(ra.previewReposErrorNoConnect({ trajectory: [], response: ok.response + "\n- [ ] Connect GitHub" }).pass, false);
});
