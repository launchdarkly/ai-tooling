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

test("previewReposErrorNoConnect fails on a Connect GitHub item", () => {
  const ok = { trajectory: [], response: "- [ ] Map acme/demo to project default once the GitHub App install can be read" };
  assert.equal(ra.previewReposErrorNoConnect(ok).pass, true);
  assert.equal(ra.previewReposErrorNoConnect({ trajectory: [], response: ok.response + "\n- [ ] Connect GitHub" }).pass, false);
});

test("saysContactSupport wants support and no release policies", () => {
  assert.equal(ra.saysContactSupport({ trajectory: [], response: "Release plans are not available on your account. Contact LaunchDarkly support." }).pass, true);
  assert.equal(ra.saysContactSupport({ trajectory: [], response: "Your account uses release policies instead." }).pass, false);
});

test("missingPlanToolsSkipsRelease: reconnect message, auto-flagging on, no support wording", () => {
  const rw = repoWrite({ autoFlagging: { enabled: true }, autoReleasing: { enabled: false } });
  const ok = { trajectory: [rw], response: "Your LaunchDarkly MCP server does not have the release plan tools yet. Update or reconnect it." };
  assert.equal(ra.missingPlanToolsSkipsRelease(ok).pass, true);
  assert.equal(ra.missingPlanToolsSkipsRelease({ ...ok, response: "Release plans are not available on your account. Contact LaunchDarkly support." }).pass, false);
  assert.equal(ra.missingPlanToolsSkipsRelease({ ...ok, trajectory: [repoWrite({ autoReleasing: { enabled: false } })] }).pass, false);
  // A mapping that omits autoReleasing inherits the account's setting.
  assert.equal(ra.missingPlanToolsSkipsRelease({ ...ok, trajectory: [repoWrite({ autoFlagging: { enabled: true } })] }).pass, false);
});

// Flag release plan step (REST API requests recorded as "ld-api").
const PLANS = "/api/v2/projects/default/flag-release-plans";
const apiCall = (method, path, extra = {}) => ({
  tool: "ld-api",
  arguments: { method, path, query: {}, apiVersion: "beta", authorized: true, status: method === "POST" ? 201 : 200, ...extra },
});
const looksGood = (turn) => ({
  tool: "ask-question",
  turn,
  arguments: { prompt: "Make these changes?", options: [{ id: "ok", label: "Looks good" }, { id: "change", label: "Change something" }] },
  selected: ["ok"],
});
const frpBody = (extra = {}) => ({
  key: "default-release",
  name: "Default release",
  isDefault: true,
  environments: [{ environmentKey: "production", environmentReleasePlanKey: "progressive", triggerType: "flag_eval" }],
  ...extra,
});
const envPlan = { tool: "create-environment-release-plan", arguments: { environmentKey: "production", key: "progressive" } };
const envDefault = { tool: "update-default-environment-release-plan", arguments: { environmentKey: "production", releasePlanKey: "progressive", default: true } };

test("flagReleasePlanAfterEnvPlans: after the plan and its default, before the repo write, after Looks good", () => {
  const good = [looksGood(5), envPlan, envDefault, apiCall("POST", PLANS, { body: frpBody() }), repoWrite({ autoFlagging: { enabled: true } })];
  assert.equal(ra.flagReleasePlanAfterEnvPlans({ trajectory: good }).pass, true);
  const early = [looksGood(5), apiCall("POST", PLANS, { body: frpBody() }), envPlan, envDefault];
  assert.equal(ra.flagReleasePlanAfterEnvPlans({ trajectory: early }).pass, false);
  const unconfirmed = [envPlan, envDefault, apiCall("POST", PLANS, { body: frpBody() })];
  assert.equal(ra.flagReleasePlanAfterEnvPlans({ trajectory: unconfirmed }).pass, false);
  const wrongPlan = [looksGood(5), envPlan, envDefault, apiCall("POST", PLANS, { body: frpBody({ environments: [{ environmentKey: "production", environmentReleasePlanKey: "other", triggerType: "flag_eval" }] }) })];
  assert.equal(ra.flagReleasePlanAfterEnvPlans({ trajectory: wrongPlan }).pass, false);
  const notDefault = [looksGood(5), envPlan, envDefault, apiCall("POST", PLANS, { body: frpBody({ isDefault: undefined }) })];
  assert.equal(ra.flagReleasePlanAfterEnvPlans({ trajectory: notDefault }).pass, false);
});

test("an API write counts as a write for noWrites and confirmsBeforeWriting", () => {
  assert.equal(ra.noWrites({ trajectory: [apiCall("GET", PLANS)] }).pass, true);
  assert.equal(ra.noWrites({ trajectory: [apiCall("POST", PLANS, { body: frpBody() })] }).pass, false);
  assert.equal(ra.confirmsBeforeWriting({ trajectory: [apiCall("POST", PLANS, { body: frpBody() }), looksGood(5), envPlan] }).pass, false);
});

test("flagReleasePlanVerified wants a read after the create", () => {
  assert.equal(ra.flagReleasePlanVerified({ trajectory: [apiCall("POST", PLANS, { body: frpBody() }), apiCall("GET", `${PLANS}/default-release`)] }).pass, true);
  assert.equal(ra.flagReleasePlanVerified({ trajectory: [apiCall("GET", PLANS), apiCall("POST", PLANS, { body: frpBody() })] }).pass, false);
});

test("confirmListsFlagReleasePlan reads text up to the confirmation only", () => {
  const listed = { trajectory: [looksGood(3)], assistant_turns: [{ turn: 2, text: "1. Create the flag release plan Default release for project default" }] };
  assert.equal(ra.confirmListsFlagReleasePlan(listed).pass, true);
  const later = { trajectory: [looksGood(3)], assistant_turns: [{ turn: 2, text: "1. Create the production release plan" }, { turn: 6, text: "Flag release plan created" }] };
  assert.equal(ra.confirmListsFlagReleasePlan(later).pass, false);
  assert.equal(ra.confirmListsFlagReleasePlan({ trajectory: [] }).pass, false);
});

test("followUpHasFlagReleasePlanCommand wants the endpoint, the beta header, and the env token", () => {
  const cmd = 'curl -sS -X POST -H "Authorization: $LD_ACCESS_TOKEN" -H "LD-API-Version: beta" "${LD_BASE_URI:-https://app.launchdarkly.com}/api/v2/projects/default/flag-release-plans" --data @- <<\'JSON\'';
  assert.equal(ra.followUpHasFlagReleasePlanCommand({ trajectory: [], response: "Follow-ups:\n```sh\n" + cmd + "\n```" }).pass, true);
  assert.equal(ra.followUpHasFlagReleasePlanCommand({ trajectory: [], response: cmd.replace("-H \"LD-API-Version: beta\" ", "") }).pass, false);
  assert.equal(ra.followUpHasFlagReleasePlanCommand({ trajectory: [], response: cmd + "\nOr paste your access token here and I'll run it." }).pass, false);
});

test("previewListsFlagReleasePlan wants it listed and no API write", () => {
  assert.equal(ra.previewListsFlagReleasePlan({ trajectory: [apiCall("GET", PLANS)], response: "- [ ] Create the flag release plan Default release" }).pass, true);
  assert.equal(ra.previewListsFlagReleasePlan({ trajectory: [apiCall("POST", PLANS, { body: frpBody() })], response: "- [ ] Create the flag release plan" }).pass, false);
  assert.equal(ra.previewListsFlagReleasePlan({ trajectory: [], response: "- [ ] Map acme/demo" }).pass, false);
});

test("flagReleasePlanUpdatedInPlace wants a PUT on the existing key, still default, and no POST", () => {
  const put = (b, extra = {}) => apiCall("PUT", `${PLANS}/staged-rollout`, { body: b, ...extra });
  const good = { name: "Staged rollout", version: 2, isDefault: true, environments: [{ environmentKey: "production", environmentReleasePlanKey: "gradual", triggerType: "flag_eval" }] };
  assert.equal(ra.flagReleasePlanUpdatedInPlace({ trajectory: [looksGood(5), put(good)] }).pass, true);
  assert.equal(ra.flagReleasePlanUpdatedInPlace({ trajectory: [looksGood(5), put(good), apiCall("POST", PLANS, { body: frpBody() })] }).pass, false);
  assert.equal(ra.flagReleasePlanUpdatedInPlace({ trajectory: [looksGood(5), put({ ...good, isDefault: undefined })] }).pass, false);
  assert.equal(ra.flagReleasePlanUpdatedInPlace({ trajectory: [put(good)] }).pass, false);
  assert.equal(ra.flagReleasePlanUpdatedInPlace({ trajectory: [looksGood(5), apiCall("POST", PLANS, { body: frpBody() })] }).pass, false);
});

test("autoReleasingOnWithFollowUp wants auto-releasing on for the repo and no off write", () => {
  assert.equal(ra.autoReleasingOnWithFollowUp({ trajectory: [repoWrite({ autoFlagging: { enabled: true }, autoReleasing: { enabled: true } })] }).pass, true);
  assert.equal(ra.autoReleasingOnWithFollowUp({ trajectory: [repoWrite({ autoFlagging: { enabled: true }, autoReleasing: { enabled: false } })] }).pass, false);
  assert.equal(ra.autoReleasingOnWithFollowUp({ trajectory: [repoWrite({ autoFlagging: { enabled: true } })] }).pass, false);
});

test("notesNoReleaseUntilPlan wants the note in the confirmation and the report", () => {
  const note = "Auto-releasing is on, but it proposes no release until the flag release plan exists.";
  const out = (summary, report) => ({ trajectory: [looksGood(3)], assistant_turns: [{ turn: 2, text: summary }], response: report });
  assert.equal(ra.notesNoReleaseUntilPlan(out(note, note)).pass, true);
  assert.equal(ra.notesNoReleaseUntilPlan(out("Map acme/demo.", note)).pass, false);
  assert.equal(ra.notesNoReleaseUntilPlan(out(note, "All set.")).pass, false);
  assert.equal(ra.notesNoReleaseUntilPlan(out("Auto-releasing won't propose a release until you create the flag release plan.", note)).pass, true);
});
