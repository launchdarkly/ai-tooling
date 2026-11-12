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
const email = { attribute: "email", op: "endsWith", values: ["@acme.example"], contextKind: "user" };
const hold = (allocation) => ({ allocation, durationMillis: 14400000 });
const internalFirst = (internalAllocation, metrics) => ({
  trajectory: [
    { tool: "create-environment-release-plan", arguments: { projectKey: "default", environmentKey: "production", key: "internal-first", progressiveRelease: {
      randomizationUnit: "user", metrics,
      phases: [{ clauses: [kind, email], steps: [hold(internalAllocation)] }, { clauses: [kind], steps: [hold(10000), hold(25000), hold(50000)] }],
    } }, mock_response_preview: "{\"key\":\"internal-first\"}" },
    { tool: "update-default-environment-release-plan", arguments: { environmentKey: "production", releasePlanKey: "internal-first", default: true } },
  ],
});
const rollback = { "user-error-rate": { isGroup: false, autoRollback: true } };

test("internal users first: one 99000 internal step without metrics, 50000 with metrics", () => {
  assert.equal(ra.starterPlanInternalFirst(internalFirst(99000, {})).pass, true);
  assert.equal(ra.starterPlanInternalFirst(internalFirst(50000, {})).pass, false);
  assert.equal(ra.starterPlanInternalFirstGuarded(internalFirst(50000, rollback)).pass, true);
  assert.equal(ra.starterPlanInternalFirstGuarded(internalFirst(99000, rollback)).pass, false);
});

test("noProductNameAfterIntro also checks code blocks", () => {
  const out = { trajectory: [], response: "Here's what would change:\n```\n- [ ] Turn on Release Autopilot for acme/demo\n```" };
  assert.equal(ra.noProductNameAfterIntro(out).pass, false);
  assert.equal(ra.noProductNameAfterIntro({ trajectory: [], response: "```\n- [ ] Turn on auto-flagging for acme/demo\n```" }).pass, true);
});

test("noInternalFirstOffered needs the starter question without the internal option", () => {
  const starter = (labels) => ({ trajectory: [ask("Which starter plan?", labels)] });
  assert.equal(ra.noInternalFirstOffered(starter(["Progressive (Recommended)", "Custom"])).pass, true);
  assert.equal(ra.noInternalFirstOffered(starter(["Internal users first (Recommended)", "Progressive", "Custom"])).pass, false);
  assert.equal(ra.noInternalFirstOffered({ trajectory: [] }).pass, false);
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
