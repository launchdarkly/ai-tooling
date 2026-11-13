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

// Flag release plan step: REST commands shown to the user, who runs them.
const BASE = "https://app.launchdarkly.com/api/v2/projects/default/flag-release-plans";
const block = (cmd) => "```sh\n" + cmd + "\n```";
const writeCmd = (method, path, body, beta = true) =>
  `curl -sS -w '\\nHTTP %{http_code}\\n' -X ${method} \\\n  -H "Authorization: $LD_ACCESS_TOKEN" \\\n${beta ? '  -H "LD-API-Version: beta" \\\n' : ""}  "${BASE}${path}" \\\n  --data @- <<'JSON'\n${JSON.stringify(body)}\nJSON`;
const looksGood = (turn) => ({
  tool: "ask-question",
  turn,
  arguments: { prompt: "Make these changes?", options: [{ id: "ok", label: "Looks good" }, { id: "change", label: "Change something" }] },
  selected: ["ok"],
});
const frpBody = (extra = {}) => ({
  key: "default-release",
  name: "Default release",
  default: true,
  environments: [{ environmentKey: "production", environmentReleasePlanKey: "progressive", triggerType: "flag_eval" }],
  ...extra,
});
const envPlan = { tool: "create-environment-release-plan", turn: 6, arguments: { environmentKey: "production", key: "progressive" } };
const envDefault = { tool: "update-default-environment-release-plan", turn: 7, arguments: { environmentKey: "production", releasePlanKey: "progressive", default: true } };
const shown = (turn, cmd) => ({ turn, text: "Run this in your terminal with your LaunchDarkly API access token:\n" + block(cmd) });

test("flagReleasePlanAfterEnvPlans: the create command after Looks good and the default, naming the new plan", () => {
  const good = { trajectory: [looksGood(5), envPlan, envDefault], assistant_turns: [shown(8, writeCmd("POST", "", frpBody()))], response: "" };
  assert.equal(ra.flagReleasePlanAfterEnvPlans(good).pass, true);
  assert.equal(ra.flagReleasePlanAfterEnvPlans({ ...good, assistant_turns: [shown(4, writeCmd("POST", "", frpBody()))] }).pass, false);
  assert.equal(ra.flagReleasePlanAfterEnvPlans({ ...good, assistant_turns: [shown(8, writeCmd("POST", "", frpBody({ environments: [{ environmentKey: "production", environmentReleasePlanKey: "made-up", triggerType: "flag_eval" }] })))] }).pass, false);
  assert.equal(ra.flagReleasePlanAfterEnvPlans({ ...good, assistant_turns: [shown(8, writeCmd("POST", "", frpBody({ default: undefined })))] }).pass, false);
  assert.equal(ra.flagReleasePlanAfterEnvPlans({ ...good, trajectory: [envPlan, envDefault] }).pass, false);
});

test("a shown command is not a write for noWrites", () => {
  assert.equal(ra.noWrites({ trajectory: [], assistant_turns: [shown(2, writeCmd("POST", "", frpBody()))] }).pass, true);
});

test("flagReleasePlanVerified wants the report to name the plan as set up", () => {
  assert.equal(ra.flagReleasePlanVerified({ trajectory: [], response: "Flag release plan: Default release (production), the project's default." }).pass, true);
  assert.equal(ra.flagReleasePlanVerified({ trajectory: [], response: "Flag release plan Default release: not verified." }).pass, false);
});

test("confirmListsFlagReleasePlan reads text up to the confirmation only", () => {
  const listed = { trajectory: [looksGood(3)], assistant_turns: [{ turn: 2, text: "1. Create the flag release plan Default release for project default" }] };
  assert.equal(ra.confirmListsFlagReleasePlan(listed).pass, true);
  const later = { trajectory: [looksGood(3)], assistant_turns: [{ turn: 2, text: "1. Create the production release plan" }, { turn: 6, text: "Flag release plan created" }] };
  assert.equal(ra.confirmListsFlagReleasePlan(later).pass, false);
  assert.equal(ra.confirmListsFlagReleasePlan({ trajectory: [] }).pass, false);
});

test("followUpHasFlagReleasePlanCommand wants the command with the beta header in the report", () => {
  const cmd = writeCmd("POST", "", frpBody());
  assert.equal(ra.followUpHasFlagReleasePlanCommand({ trajectory: [], response: "Follow-ups:\n" + block(cmd) }).pass, true);
  assert.equal(ra.followUpHasFlagReleasePlanCommand({ trajectory: [], response: "Follow-ups:\n" + block(writeCmd("POST", "", frpBody(), false)) }).pass, false);
  assert.equal(ra.followUpHasFlagReleasePlanCommand({ trajectory: [], response: "Follow-ups:\n" + block(cmd) + "\nOr paste your access token here." }).pass, false);
  assert.equal(ra.followUpHasFlagReleasePlanCommand({ trajectory: [], response: "Create the flag release plan later." }).pass, false);
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

test("confirmShowsPlan needs the plan, with every written repo, in the Looks good question", () => {
  const plan = "Here's the plan:\n- Map acme/demo to project default, with auto-flagging on\n- Turn on auto-flagging for the account";
  const write = repoWrite({ autoFlagging: { enabled: true } });
  assert.equal(ra.confirmShowsPlan({ trajectory: [ask(plan, ["Looks good", "Change something"]), write] }).pass, true);
  const inPreview = ask("Make these changes?", ["Looks good", "Change something"]);
  inPreview.arguments.options[0].preview = plan;
  assert.equal(ra.confirmShowsPlan({ trajectory: [inPreview, write] }).pass, true);
  const inChangePreview = ask("Make these changes?", ["Looks good", "Change something"]);
  inChangePreview.arguments.options[1].preview = plan;
  assert.equal(ra.confirmShowsPlan({ trajectory: [inChangePreview, write] }).pass, false);
  assert.equal(ra.confirmShowsPlan({ trajectory: [ask("Ready to apply?", ["Looks good", "Change something"]), write] }).pass, false);
  assert.equal(ra.confirmShowsPlan({ trajectory: [ask("- Turn on auto-flagging for the account", ["Looks good", "Change something"]), write] }).pass, false);
  assert.equal(ra.confirmShowsPlan({ trajectory: [ask(plan), write] }).pass, false);
});

// Flag release plan step through the MCP tools.
const frpCreate = (args = {}, preview = "{\"key\":\"default-release\"}") => ({ tool: "create-flag-release-plan", turn: 8, arguments: { projectKey: "default", ...frpBody(), ...args }, mock_response_preview: preview });
const frpRead = (args = {}) => ({ tool: "get-flag-release-plans", turn: 12, arguments: { projectKey: "default", flagReleasePlanKey: "default-release", ...args } });

test("flagReleasePlanMcpAfterEnvPlans: create after Looks good and the default, naming the new plan, as the default", () => {
  const good = { trajectory: [looksGood(5), envPlan, envDefault, frpCreate()], response: "" };
  assert.equal(ra.flagReleasePlanMcpAfterEnvPlans(good).pass, true);
  assert.equal(ra.flagReleasePlanMcpAfterEnvPlans({ trajectory: [envPlan, envDefault, frpCreate()] }).pass, false, "no Looks good");
  assert.equal(ra.flagReleasePlanMcpAfterEnvPlans({ trajectory: [looksGood(5), envPlan, frpCreate(), envDefault] }).pass, false, "before the default");
  assert.equal(ra.flagReleasePlanMcpAfterEnvPlans({ trajectory: [looksGood(5), envPlan, envDefault, frpCreate({ default: undefined })] }).pass, false, "not the default");
  assert.equal(ra.flagReleasePlanMcpAfterEnvPlans({ trajectory: [looksGood(5), envPlan, envDefault, frpCreate({ environments: [{ environmentKey: "production", environmentReleasePlanKey: "made-up", triggerType: "flag_eval" }] })] }).pass, false, "wrong plan");
  assert.equal(ra.flagReleasePlanMcpAfterEnvPlans({ trajectory: [looksGood(5), envPlan, envDefault, frpCreate({}, "{\"error\":\"already has a default\"}")] }).pass, false, "failed create");
});

test("flagReleasePlanMcpVerified wants a read after the create and the plan named in the report", () => {
  const response = "Flag release plan: Default release (production), the project's default.";
  assert.equal(ra.flagReleasePlanMcpVerified({ trajectory: [frpCreate(), frpRead()], response }).pass, true);
  assert.equal(ra.flagReleasePlanMcpVerified({ trajectory: [frpCreate(), frpRead({ flagReleasePlanKey: undefined })], response }).pass, true, "a list read counts");
  assert.equal(ra.flagReleasePlanMcpVerified({ trajectory: [frpRead(), frpCreate()], response }).pass, false, "read only before the create");
  assert.equal(ra.flagReleasePlanMcpVerified({ trajectory: [frpCreate(), frpRead()], response: "Flag release plan Default release: not verified." }).pass, false);
});

test("flag release plan writes count as writes, and their tool names are raw names", () => {
  assert.equal(ra.noWrites({ trajectory: [frpCreate()] }).pass, false);
  assert.equal(ra.confirmsBeforeWriting({ trajectory: [frpCreate(), looksGood(9)] }).pass, false);
  assert.equal(ra.noRawNames({ trajectory: [], assistant_turns: [], response: "I'll call create-flag-release-plan next." }).pass, false);
});

test("noCommandsShown fails on a shown command or a Run this command question", () => {
  assert.equal(ra.noCommandsShown({ trajectory: [frpCreate()], assistant_turns: [], response: "Created." }).pass, true);
  assert.equal(ra.noCommandsShown({ trajectory: [], assistant_turns: [shown(8, writeCmd("POST", "", frpBody()))], response: "" }).pass, false);
  const run = ask("Run this command", ["Done, here's the output", "Skip"]);
  assert.equal(ra.noCommandsShown({ trajectory: [run], assistant_turns: [], response: "" }).pass, false);
});

test("missingPlanToolsSkipsRelease does not count a flag release plan read as a write", () => {
  const rw = repoWrite({ autoFlagging: { enabled: true }, autoReleasing: { enabled: false } });
  const out = { trajectory: [{ tool: "get-flag-release-plans", arguments: { projectKey: "default" } }, rw], response: "Your LaunchDarkly MCP server does not have the release plan tools yet. Update or reconnect it." };
  assert.equal(ra.missingPlanToolsSkipsRelease(out).pass, true);
  assert.equal(ra.missingPlanToolsSkipsRelease({ ...out, trajectory: [frpCreate(), rw] }).pass, false);
});
