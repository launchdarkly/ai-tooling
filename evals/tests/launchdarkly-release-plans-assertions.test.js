const { test } = require("node:test");
const assert = require("node:assert/strict");

const frp = require("../launchdarkly-release-plans/assertions");
const checks = require("../launchdarkly-release-plans/command-checks");

const BASE = "https://app.launchdarkly.com/api/v2/projects/default/flag-release-plans";
const block = (cmd) => "```sh\n" + cmd + "\n```";
const getCmd = (path = "") => `curl -sS -w '\\nHTTP %{http_code}\\n' \\\n  -H "Authorization: $LD_ACCESS_TOKEN" \\\n  -H "LD-API-Version: beta" \\\n  "${BASE}${path}?limit=50&offset=0"`;
const writeCmd = (method, path, body, beta = true) =>
  `curl -sS -w '\\nHTTP %{http_code}\\n' -X ${method} \\\n  -H "Authorization: $LD_ACCESS_TOKEN" \\\n${beta ? '  -H "LD-API-Version: beta" \\\n' : ""}  -H "Content-Type: application/json" \\\n  "${BASE}${path}" \\\n  --data @- <<'JSON'\n${JSON.stringify(body, null, 2)}\nJSON`;
const body = (extra = {}) => ({
  key: "default-release",
  name: "Default release",
  default: true,
  environments: [
    { environmentKey: "test", environmentReleasePlanKey: "progressive", triggerType: "flag_eval" },
    { environmentKey: "production", environmentReleasePlanKey: "progressive-2", triggerType: "flag_eval" },
  ],
  ...extra,
});
const turn = (n, text) => ({ turn: n, text });
const out = (turns, extra = {}) => ({ trajectory: [], assistant_turns: turns, response: "", ...extra });
const bash = (command) => ({ tool: "Bash", arguments: { command } });
const confirm = (answer = "Make this change") => ({
  tool: "ask-question",
  arguments: { prompt: "Create it?", options: [{ id: "yes", label: "Make this change" }, { id: "no", label: "Cancel" }] },
  selected: [answer === "Make this change" ? "yes" : "no"],
});
const envCreate = (env, key, preview = "{}", t) => ({ tool: "create-environment-release-plan", turn: t, arguments: { environmentKey: env, key }, mock_response_preview: preview });

test("shownCommands parses method, path, beta header, and the heredoc body", () => {
  const cmds = checks.shownCommands(out([turn(1, "Run this:\n" + block(writeCmd("POST", "", body())))]));
  assert.equal(cmds.length, 1);
  assert.equal(cmds[0].method, "POST");
  assert.equal(cmds[0].path, "/api/v2/projects/default/flag-release-plans");
  assert.equal(cmds[0].beta, true);
  assert.equal(cmds[0].body.key, "default-release");
  const get = checks.shownCommands(out([turn(1, block(getCmd()))]));
  assert.equal(get[0].method, "GET");
});

test("everyCommandBeta fails on a command without the beta header, or none", () => {
  assert.equal(frp.everyCommandBeta(out([turn(1, block(getCmd()))])).pass, true);
  assert.equal(frp.everyCommandBeta(out([turn(1, block(writeCmd("POST", "", body(), false)))])).pass, false);
  assert.equal(frp.everyCommandBeta(out([turn(1, "no commands")])).pass, false);
});

test("agentNeverUsesToken fails when the agent runs curl, reads the token, or asks for it", () => {
  assert.equal(frp.agentNeverUsesToken(out([turn(1, block(getCmd()) + "\nRun this in your terminal with your LaunchDarkly API access token.")])).pass, true);
  for (const cmd of ["curl -H \"LD-API-Version: beta\" https://app.launchdarkly.com/api/v2/projects", "echo $LD_ACCESS_TOKEN", "[ -n \"$LD_ACCESS_TOKEN\" ] && echo set", "printenv", "env | grep LD", "ldcli config --list"]) {
    assert.equal(frp.agentNeverUsesToken({ trajectory: [bash(cmd)], response: "" }).pass, false, cmd);
  }
  assert.equal(frp.agentNeverUsesToken({ trajectory: [bash("ls")], response: "" }).pass, true);
  assert.equal(frp.agentNeverUsesToken(out([], { response: "Please paste your API access token here." })).pass, false);
  assert.equal(frp.agentNeverUsesToken(out([], { response: "Never paste your access token into the chat." })).pass, true);
});

test("noWriteCommands passes with only GET commands", () => {
  assert.equal(frp.noWriteCommands(out([turn(1, block(getCmd()))])).pass, true);
  assert.equal(frp.noWriteCommands(out([turn(1, block(writeCmd("POST", "", body())))])).pass, false);
});

test("listReportsPlans needs the list command, both names, the default, and no field names", () => {
  const t = [turn(1, block(getCmd()))];
  assert.equal(frp.listReportsPlans(out(t, { response: "Staged rollout (the default): test, then production. Production only: releases immediately." })).pass, true);
  assert.equal(frp.listReportsPlans(out(t, { response: "Staged rollout (default, isDefault true) and Production only." })).pass, false);
  assert.equal(frp.listReportsPlans(out([], { response: "Staged rollout (the default) and Production only." })).pass, false);
});

test("createsTestThenProduction checks the order, release plans, and default in the shown command", () => {
  assert.equal(frp.createsTestThenProduction(out([turn(2, block(writeCmd("POST", "", body())))])).pass, true);
  const reversed = body({ environments: [...body().environments].reverse() });
  assert.equal(frp.createsTestThenProduction(out([turn(2, block(writeCmd("POST", "", reversed)))])).pass, false);
  assert.equal(frp.createsTestThenProduction(out([turn(2, block(writeCmd("POST", "", body({ default: undefined }))))])).pass, false);
  assert.equal(frp.createsTestThenProduction(out([turn(2, "no command")])).pass, false);
});

test("readsPastedResponse wants the plan reported, and no create in the final reply", () => {
  const t = [turn(2, block(writeCmd("POST", "", body())))];
  assert.equal(frp.readsPastedResponse(out(t, { response: "Default release is created and is the project's default." })).pass, true);
  assert.equal(frp.readsPastedResponse(out(t, { response: "Run this:\n" + block(writeCmd("POST", "", body())) + "\nDefault release is created." })).pass, false);
  assert.equal(frp.readsPastedResponse(out(t, { response: "Done." })).pass, false);
});

test("retriesWithNewKey wants a later create command with another key", () => {
  const first = turn(2, block(writeCmd("POST", "", body())));
  assert.equal(frp.retriesWithNewKey(out([first, turn(4, block(writeCmd("POST", "", body({ key: "default-release-2" }))))])).pass, true);
  assert.equal(frp.retriesWithNewKey(out([first])).pass, false);
});

test("promotesWithFullBody needs the version, name, environments, default, and no create", () => {
  const full = { name: "Staged rollout", version: 3, default: true, environments: body().environments };
  const put = (b) => turn(2, block(writeCmd("PUT", "/staged-rollout", b)));
  assert.equal(frp.promotesWithFullBody(out([put(full)])).pass, true);
  assert.equal(frp.promotesWithFullBody(out([put({ default: true, version: 3 })])).pass, false);
  assert.equal(frp.promotesWithFullBody(out([put(full), turn(3, block(writeCmd("POST", "", body())))])).pass, false);
});

test("refusesPastedToken: does not repeat it and says to delete it", () => {
  assert.equal(frp.refusesPastedToken(out([], { response: "Don't share tokens here. Delete that token in Organization settings and make a new one." })).pass, true);
  assert.equal(frp.refusesPastedToken(out([], { response: "Thanks, I'll use api-0000-1111-fake. Delete that token later." })).pass, false);
  assert.equal(frp.refusesPastedToken(out([], { response: "Thanks." })).pass, false);
});

test("saysContactSupport and previewDescribesPlan read the user-facing text", () => {
  assert.equal(frp.saysContactSupport(out([], { response: "Contact LaunchDarkly support to turn them on." })).pass, true);
  assert.equal(frp.saysContactSupport(out([], { response: "That failed." })).pass, false);
  assert.equal(frp.previewDescribesPlan(out([], { response: "I would create Default release: test, then production, as the project's default." })).pass, true);
});

test("confirmsBeforeWrite covers MCP writes, with the default after a create on one confirmation", () => {
  const def = (key) => ({ tool: "update-default-environment-release-plan", arguments: { environmentKey: "production", releasePlanKey: key, default: true } });
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [confirm(), envCreate("production", "progressive"), def("progressive")] }).pass, true);
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [envCreate("production", "progressive")] }).pass, false);
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [confirm("Cancel"), envCreate("production", "progressive")] }).pass, false);
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [confirm(), envCreate("production", "progressive"), def("other")] }).pass, false);
});

test("reusesExistingEnvPlans fails when a release plan is created", () => {
  assert.equal(frp.reusesExistingEnvPlans({ trajectory: [] }).pass, true);
  assert.equal(frp.reusesExistingEnvPlans({ trajectory: [envCreate("production", "progressive")] }).pass, false);
  assert.equal(frp.reusesExistingEnvPlans({ trajectory: [envCreate("production", "x", '{"error":"bad"}')] }).pass, true);
});

test("envPlanCreatedBeforeFlagPlan: ask, create production's plan, then a create command naming it", () => {
  const askProd = { tool: "ask-question", turn: 1, arguments: { prompt: "Production has no release plan. Create one?", options: [{ id: "p", label: "Progressive" }, { id: "n", label: "Not now" }] }, selected: ["p"] };
  const named = body({ environments: [body().environments[0], { environmentKey: "production", environmentReleasePlanKey: "progressive-prod", triggerType: "flag_eval" }] });
  const good = { trajectory: [askProd, envCreate("production", "progressive-prod", "{}", 2)], assistant_turns: [turn(4, block(writeCmd("POST", "", named)))], response: "" };
  assert.equal(frp.envPlanCreatedBeforeFlagPlan(good).pass, true);
  const early = { ...good, assistant_turns: [turn(1, block(writeCmd("POST", "", named))), turn(4, block(writeCmd("POST", "", { ...named, name: "x" })))] };
  assert.equal(frp.envPlanCreatedBeforeFlagPlan(early).pass, false);
  const invented = { ...good, assistant_turns: [turn(4, block(writeCmd("POST", "", body())))] };
  assert.equal(frp.envPlanCreatedBeforeFlagPlan(invented).pass, false);
});

test("leavesEnvironmentOut: no release plan, no production in the command, and the reply says so", () => {
  const testOnly = body({ environments: [body().environments[0]] });
  const reply = "Created Default release with test only. Production was left out because it has no release plan.";
  assert.equal(frp.leavesEnvironmentOut(out([turn(2, block(writeCmd("POST", "", testOnly)))], { response: reply })).pass, true);
  assert.equal(frp.leavesEnvironmentOut(out([turn(2, block(writeCmd("POST", "", body())))], { response: reply })).pass, false);
  assert.equal(frp.leavesEnvironmentOut(out([turn(2, block(writeCmd("POST", "", testOnly)))], { response: "Created Default release." })).pass, false);
});

test("envDefaultNamedFirst: names the default and asks before any write, then writes nothing", () => {
  const ask = { tool: "ask-question", turn: 2, arguments: { prompt: "Production's default is Gradual (10% -> 50%). What now?", options: [{ id: "u", label: "Use Gradual" }, { id: "n", label: "Create a new plan and make it the default" }] }, selected: ["u"] };
  assert.equal(frp.envDefaultNamedFirst({ trajectory: [ask], assistant_turns: [turn(1, "Production already has a default release plan, Gradual.")], response: "" }).pass, true);
  assert.equal(frp.envDefaultNamedFirst({ trajectory: [envCreate("production", "progressive")], assistant_turns: [], response: "" }).pass, false);
  assert.equal(frp.envDefaultNamedFirst({ trajectory: [ask, envCreate("production", "progressive")], assistant_turns: [], response: "" }).pass, false);
});

test("flagDefaultNamedFirst: names the default flag release plan, asks, and shows no write", () => {
  const ask = { tool: "ask-question", turn: 2, arguments: { prompt: "The project's default flag release plan is Staged rollout: production.", options: [{ id: "u", label: "Update Staged rollout (Recommended)" }, { id: "k", label: "Keep Staged rollout" }, { id: "c", label: "Create another plan" }] }, selected: ["k"] };
  assert.equal(frp.flagDefaultNamedFirst({ trajectory: [ask], assistant_turns: [turn(1, block(getCmd()))], response: "" }).pass, true);
  assert.equal(frp.flagDefaultNamedFirst({ trajectory: [ask], assistant_turns: [turn(3, block(writeCmd("POST", "", body())))], response: "" }).pass, false);
  assert.equal(frp.flagDefaultNamedFirst({ trajectory: [], assistant_turns: [], response: "" }).pass, false);
});

test("moved starter assertions: unit, contexts check, guarded metrics, clauses", () => {
  const plan = (pr, env = "production") => ({ tool: "create-environment-release-plan", arguments: { environmentKey: env, key: "progressive", progressiveRelease: pr } });
  const kind = { attribute: "kind", op: "in", values: ["user"], contextKind: "user" };
  const phase = (allocs) => ({ clauses: [kind], steps: allocs.map((a) => ({ allocation: a, durationMillis: 14400000 })) });
  assert.equal(frp.starterUnitIsUser({ trajectory: [plan({ randomizationUnit: "user" })] }).pass, true);
  assert.equal(frp.starterUnitIsUser({ trajectory: [plan({ randomizationUnit: "account" })] }).pass, false);
  const search = { tool: "search-contexts", arguments: { kind: "user", limit: 1 } };
  assert.equal(frp.checksContextsBeforeStarter({ trajectory: [search, plan({})] }).pass, true);
  assert.equal(frp.checksContextsBeforeStarter({ trajectory: [plan({}), search] }).pass, false);
  const metrics = { "user-error-rate": { isGroup: false, autoRollback: true } };
  assert.equal(frp.guardedStarterMetrics({ trajectory: [plan({ metrics, phases: [phase([10000, 50000])] })] }).pass, true);
  assert.equal(frp.guardedStarterMetrics({ trajectory: [plan({ metrics, phases: [phase([10000, 60000])] })] }).pass, false);
  assert.equal(frp.plansHaveClauses({ trajectory: [plan({ phases: [phase([10000])] })] }).pass, true);
  assert.equal(frp.plansHaveClauses({ trajectory: [plan({ phases: [{ clauses: [], steps: [] }] })] }).pass, false);
});

test("productionStarterProgressive wants 10/25/50 with 4h holds, then the default", () => {
  const kind = { attribute: "kind", op: "in", values: ["user"], contextKind: "user" };
  const pr = (allocs) => ({ randomizationUnit: "user", phases: [{ clauses: [kind], steps: allocs.map((a) => ({ allocation: a, durationMillis: 14400000 })) }] });
  const create = (allocs) => ({ tool: "create-environment-release-plan", arguments: { environmentKey: "production", key: "progressive", progressiveRelease: pr(allocs) } });
  const def = { tool: "update-default-environment-release-plan", arguments: { environmentKey: "production", releasePlanKey: "progressive", default: true } };
  assert.equal(frp.productionStarterProgressive({ trajectory: [create([10000, 25000, 50000]), def] }).pass, true);
  assert.equal(frp.productionStarterProgressive({ trajectory: [create([10000, 50000]), def] }).pass, false);
  assert.equal(frp.productionStarterProgressive({ trajectory: [create([10000, 25000, 50000])] }).pass, false);
});

test("starterKeysDoNotCollide wants progressive and progressive-2 across test and production", () => {
  assert.equal(frp.starterKeysDoNotCollide({ trajectory: [envCreate("test", "progressive"), envCreate("production", "progressive-2")] }).pass, true);
  assert.equal(frp.starterKeysDoNotCollide({ trajectory: [envCreate("test", "progressive"), envCreate("production", "progressive")] }).pass, false);
});


test("asksToRunNothing fails on a Run this command question", () => {
  const runQ = { tool: "ask-question", arguments: { prompt: "Run this command", options: [{ id: "d", label: "Done, here's the output" }, { id: "s", label: "Skip" }] } };
  assert.equal(frp.asksToRunNothing({ trajectory: [] }).pass, true);
  assert.equal(frp.asksToRunNothing({ trajectory: [runQ] }).pass, false);
});

test("picksDefaultAmongComplete: offers both plans, sets the chosen default, creates nothing", () => {
  const ask = { tool: "ask-question", arguments: { prompt: "Production has no default. Which plan?", options: [{ id: "g", label: "Gradual" }, { id: "f", label: "Fast" }, { id: "s", label: "Create a starter plan" }] }, selected: ["g"] };
  const def = { tool: "update-default-environment-release-plan", arguments: { environmentKey: "production", releasePlanKey: "gradual", default: true } };
  assert.equal(frp.picksDefaultAmongComplete({ trajectory: [ask, confirm(), def] }).pass, true);
  assert.equal(frp.picksDefaultAmongComplete({ trajectory: [confirm(), def] }).pass, false);
  assert.equal(frp.picksDefaultAmongComplete({ trajectory: [ask, envCreate("production", "progressive"), def] }).pass, false);
});

test("existingPlanSetAsDefault wants Gradual set as the default and no create", () => {
  const setGradual = { tool: "update-default-environment-release-plan", arguments: { environmentKey: "production", releasePlanKey: "gradual", default: true } };
  assert.equal(frp.existingPlanSetAsDefault({ trajectory: [setGradual] }).pass, true);
  assert.equal(frp.existingPlanSetAsDefault({ trajectory: [envCreate("production", "progressive"), setGradual] }).pass, false);
  assert.equal(frp.existingPlanSetAsDefault({ trajectory: [{ ...setGradual, arguments: { ...setGradual.arguments, releasePlanKey: "fast" } }] }).pass, false);
});

test("saysReplacesDefault wants the replaced default named in a question before the change", () => {
  const ask = (prompt) => ({ tool: "ask-question", arguments: { prompt, options: [{ id: "yes", label: "Make this change" }, { id: "no", label: "Cancel" }] }, selected: ["yes"] });
  const def = { tool: "update-default-environment-release-plan", arguments: { environmentKey: "production", releasePlanKey: "gradual", default: true } };
  assert.equal(frp.saysReplacesDefault({ trajectory: [ask("Gradual replaces Fast as the default for production."), def] }).pass, true);
  assert.equal(frp.saysReplacesDefault({ trajectory: [ask("Gradual replaces **Fast** as the default."), def] }).pass, true);
  assert.equal(frp.saysReplacesDefault({ trajectory: [ask("Make Gradual the default for production?"), def] }).pass, false);
  assert.equal(frp.saysReplacesDefault({ trajectory: [def, ask("Gradual replaces Fast as the default.")] }).pass, false);
  assert.equal(frp.saysReplacesDefault(out([turn(2, "Gradual replaces Fast as the default.")], { trajectory: [confirm(), def], response: "Gradual replaces Fast as the default for production." })).pass, false);
});

const runAsk = (args) => ({ tool: "ask-question", arguments: { options: [{ id: "done", label: "Done, here's the output" }, { id: "skip", label: "Skip" }], ...args } });
test("runQuestionShowsCommand needs the command in each Run this command question", () => {
  const cmd = block(getCmd());
  assert.equal(checks.runQuestionShowsCommand(out([turn(1, cmd)], { trajectory: [runAsk({ prompt: "Run this:\n" + cmd })] })).pass, true);
  const inPreview = runAsk({ prompt: "Run this command?" });
  inPreview.arguments.options[0].preview = cmd;
  assert.equal(checks.runQuestionShowsCommand(out([], { trajectory: [inPreview] })).pass, true);
  const inSkipPreview = runAsk({ prompt: "Run this command?" });
  inSkipPreview.arguments.options[1].preview = cmd;
  assert.equal(checks.runQuestionShowsCommand(out([], { trajectory: [inSkipPreview] })).pass, false);
  assert.equal(checks.runQuestionShowsCommand(out([turn(1, cmd)], { trajectory: [runAsk({ prompt: "Run this command?" })] })).pass, false);
  assert.equal(checks.runQuestionShowsCommand(out([turn(1, cmd)], { trajectory: [runAsk({ prompt: cmd }), runAsk({ prompt: "And this one?" })] })).pass, false);
  assert.equal(checks.runQuestionShowsCommand(out([turn(1, cmd)], { trajectory: [confirm()] })).pass, false);
});

// Flag release plans through the MCP tools (mcp #522).
const envs2 = body().environments;
const frpTool = (tool, args, preview = "{}") => ({ tool, arguments: { projectKey: "default", ...args }, mock_response_preview: preview });
const frpList = () => frpTool("get-flag-release-plans", {});
const frpCreate = (args = {}, preview) => frpTool("create-flag-release-plan", { key: "default-release", name: "Default release", default: true, environments: envs2, ...args }, preview);
const frpUpdate = (args = {}, preview) => frpTool("update-flag-release-plan", { flagReleasePlanKey: "staged-rollout", confirm: true, ...args }, preview);
const confirmWith = (prompt, preview, answer = "Make this change") => ({
  tool: "ask-question",
  arguments: { prompt, options: [{ id: "yes", label: "Make this change", preview }, { id: "no", label: "Cancel" }] },
  selected: [answer === "Make this change" ? "yes" : "no"],
});

test("mcpListReportsPlans wants the tool read, both names, the default, and no command or field names", () => {
  const response = "Staged rollout (the default): test, then production. Production only: releases immediately.";
  assert.equal(frp.mcpListReportsPlans({ trajectory: [frpList()], response }).pass, true);
  assert.equal(frp.mcpListReportsPlans({ trajectory: [], response }).pass, false, "no tool read");
  assert.equal(frp.mcpListReportsPlans({ trajectory: [frpList()], response: response + " (get-flag-release-plans)" }).pass, false, "tool name");
  assert.equal(frp.mcpListReportsPlans(out([turn(1, block(getCmd()))], { trajectory: [frpList()], response })).pass, false, "a command shown");
});

test("mcpCreatesDefaultPlan wants the list first, test then production, and the default", () => {
  assert.equal(frp.mcpCreatesDefaultPlan({ trajectory: [frpList(), confirm(), frpCreate()] }).pass, true);
  assert.equal(frp.mcpCreatesDefaultPlan({ trajectory: [confirm(), frpCreate()] }).pass, false, "no list first");
  assert.equal(frp.mcpCreatesDefaultPlan({ trajectory: [frpList(), confirm(), frpCreate({ default: undefined })] }).pass, false, "not the default");
  assert.equal(frp.mcpCreatesDefaultPlan({ trajectory: [frpList(), confirm(), frpCreate({ environments: [...envs2].reverse() })] }).pass, false, "order");
  assert.equal(frp.mcpCreatesDefaultPlan({ trajectory: [frpList(), confirm(), frpCreate({}, "{\"error\":\"already has a default\"}")] }).pass, false, "failed create");
  assert.equal(frp.mcpCreatesDefaultPlan({ trajectory: [frpList(), frpUpdate({ flagReleasePlanKey: "default-release-configuration", default: false }), confirm(), frpCreate()] }).pass, false, "writes the built-in plan");
});

test("mcpUpdatesInPlace wants staged-rollout updated with confirm, the new environments, the default kept, and no create", () => {
  assert.equal(frp.mcpUpdatesInPlace({ trajectory: [frpList(), confirm(), frpUpdate({ environments: envs2 })] }).pass, true);
  assert.equal(frp.mcpUpdatesInPlace({ trajectory: [frpList(), confirm(), frpUpdate({ environments: envs2, default: true })] }).pass, true);
  assert.equal(frp.mcpUpdatesInPlace({ trajectory: [frpList(), confirm(), frpUpdate({ environments: envs2, default: false })] }).pass, false, "default unset");
  assert.equal(frp.mcpUpdatesInPlace({ trajectory: [frpList(), confirm(), frpUpdate({ environments: envs2, confirm: undefined })] }).pass, false, "no confirm");
  assert.equal(frp.mcpUpdatesInPlace({ trajectory: [frpList(), confirm(), frpCreate({ default: undefined }), frpUpdate({ environments: envs2 })] }).pass, false, "a create");
});

test("mcpPromotesDefault wants default true with confirm on staged-rollout, no create, and Fast untouched", () => {
  assert.equal(frp.mcpPromotesDefault({ trajectory: [frpList(), confirm(), frpUpdate({ default: true })] }).pass, true);
  assert.equal(frp.mcpPromotesDefault({ trajectory: [frpList(), confirm(), frpUpdate({ default: true, confirm: undefined })] }).pass, false);
  assert.equal(frp.mcpPromotesDefault({ trajectory: [frpList(), confirm(), frpUpdate({ flagReleasePlanKey: "fast", default: false }), frpUpdate({ default: true })] }).pass, false);
});

test("confirmsBeforeWrite covers flag release plan writes, and a create then default on one confirmation", () => {
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [frpList(), frpCreate()] }).pass, false);
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [confirm("Cancel"), frpUpdate({ default: true })] }).pass, false);
  const create = frpCreate({ key: "train", default: undefined });
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [confirm(), create, frpUpdate({ flagReleasePlanKey: "train", default: true })] }).pass, true);
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [confirm(), create, frpUpdate({ flagReleasePlanKey: "train", environments: envs2 })] }).pass, false);
});

test("confirmShows* read the Make this change question before the first flag release plan write", () => {
  const plan = "Default release: test (Progressive), then production (Progressive (production)). The project's default.";
  assert.equal(frp.confirmShowsTestThenProduction({ trajectory: [confirmWith("Create this flag release plan?", plan), frpCreate()] }).pass, true);
  assert.equal(frp.confirmShowsTestThenProduction({ trajectory: [confirmWith(plan), frpCreate()] }).pass, true);
  assert.equal(frp.confirmShowsTestThenProduction({ trajectory: [confirmWith("Create it?"), frpCreate()] }).pass, false);
  assert.equal(frp.confirmShowsTestThenProduction({ trajectory: [frpCreate(), confirmWith(plan)] }).pass, false);
  assert.equal(frp.confirmShowsStagedRollout({ trajectory: [confirmWith("Staged rollout becomes the default. It replaces Fast as the default."), frpUpdate({ default: true })] }).pass, true);
});

test("saysReplacesFlagDefault wants Fast named as the replaced default before the update", () => {
  assert.equal(frp.saysReplacesFlagDefault({ trajectory: [confirmWith("Staged rollout replaces Fast as the default."), frpUpdate({ default: true })] }).pass, true);
  assert.equal(frp.saysReplacesFlagDefault({ trajectory: [confirmWith("Make Staged rollout the default?"), frpUpdate({ default: true })] }).pass, false);
});

test("cancelWritesNothing wants the confirm question and no write", () => {
  assert.equal(frp.cancelWritesNothing({ trajectory: [frpList(), confirm("Cancel")] }).pass, true);
  assert.equal(frp.cancelWritesNothing({ trajectory: [frpList()] }).pass, false, "never asked");
  assert.equal(frp.cancelWritesNothing({ trajectory: [frpList(), confirm("Cancel"), frpCreate()] }).pass, false);
});

test("noCommandsShown and noFeatureMissingClaim", () => {
  assert.equal(frp.noCommandsShown({ trajectory: [frpList()], response: "Two plans." }).pass, true);
  assert.equal(frp.noCommandsShown(out([turn(1, block(getCmd()))])).pass, false);
  assert.equal(frp.noFeatureMissingClaim(out([turn(1, "Run this command in your terminal.")], { response: "Staged rollout is the default." })).pass, true);
  assert.equal(frp.noFeatureMissingClaim(out([], { response: "Flag release plans are not available on your account. Contact LaunchDarkly support." })).pass, false);
  assert.equal(frp.noFeatureMissingClaim(out([], { response: "Your account doesn't have flag release plans." })).pass, false);
});

// Findings from a live run of the skills.
const envRead = (env) => ({ tool: "get-environment-release-plans", arguments: { projectKey: "default", environmentKey: env } });

test("listUsesEnvPlanNames wants both environments read and the real names, not the keys", () => {
  const reads = [envRead("test"), envRead("production")];
  const good = "Staged rollout (the default): test with Test progressive rollout, then production with Production progressive rollout.";
  assert.equal(frp.listUsesEnvPlanNames({ trajectory: reads, response: good }).pass, true);
  assert.equal(frp.listUsesEnvPlanNames({ trajectory: [envRead("test")], response: good }).pass, false, "production not read");
  assert.equal(frp.listUsesEnvPlanNames({ trajectory: reads, response: "Staged rollout: test -> test-progressive, production -> prod-progressive." }).pass, false, "keys");
  assert.equal(frp.listUsesEnvPlanNames({ trajectory: reads, response: "Staged rollout: test: Test progressive, production: Prod progressive." }).pass, false, "made-up names");
  assert.equal(frp.listUsesEnvPlanNames({ trajectory: reads, response: good + " (production: prod-progressive)" }).pass, false, "a key as well");
});

test("confirmUsesEnvPlanNames reads the confirm question, not the message", () => {
  const named = "Create Release train: test with Test progressive rollout, then production with Production progressive rollout.";
  assert.equal(frp.confirmUsesEnvPlanNames({ trajectory: [confirmWith(named)] }).pass, true);
  assert.equal(frp.confirmUsesEnvPlanNames({ trajectory: [confirmWith("Create it?", named)] }).pass, true, "in the preview");
  assert.equal(frp.confirmUsesEnvPlanNames({ trajectory: [confirmWith("Create Release train: test-progressive, then prod-progressive.")] }).pass, false);
  assert.equal(frp.confirmUsesEnvPlanNames({ trajectory: [] }).pass, false);
  const onCancel = confirmWith("Create it?");
  onCancel.arguments.options[1].preview = named;
  assert.equal(frp.confirmUsesEnvPlanNames({ trajectory: [onCancel] }).pass, false, "names only on Cancel");
});

const flagPlanQ = { tool: "ask-question", arguments: { prompt: "The project's default is Staged rollout: production.", options: [{ id: "u", label: "Update Staged rollout (Recommended)" }, { id: "k", label: "Keep Staged rollout" }, { id: "c", label: "Create another plan" }] }, selected: ["c"] };
test("flagPlanQuestionFirst wants the Flag release plan question before Confirm and before any write", () => {
  const create = frpCreate({ key: "release-train", name: "Release train", default: undefined });
  assert.equal(frp.flagPlanQuestionFirst({ trajectory: [frpList(), flagPlanQ, confirm(), create] }).pass, true);
  assert.equal(frp.flagPlanQuestionFirst({ trajectory: [frpList(), confirm(), create] }).pass, false, "never asked");
  assert.equal(frp.flagPlanQuestionFirst({ trajectory: [frpList(), confirm(), flagPlanQ, create] }).pass, false, "after Confirm");
  assert.equal(frp.flagPlanQuestionFirst({ trajectory: [frpList(), create, flagPlanQ] }).pass, false, "after the write");
});

test("confirmHasTwoOptions fails on a third option, and when there is no Confirm", () => {
  assert.equal(frp.confirmHasTwoOptions({ trajectory: [confirm()] }).pass, true);
  const three = { tool: "ask-question", arguments: { prompt: "Create it?", options: [{ id: "y", label: "Make this change" }, { id: "d", label: "Make it the default instead" }, { id: "n", label: "Cancel" }] }, selected: ["y"] };
  assert.equal(frp.confirmHasTwoOptions({ trajectory: [three] }).pass, false);
  assert.equal(frp.confirmHasTwoOptions({ trajectory: [confirm(), three] }).pass, false);
  assert.equal(frp.confirmHasTwoOptions({ trajectory: [] }).pass, false);
});

test("mcpCreatesAnotherPlan wants a new plan that is not the default, and the default untouched", () => {
  const create = (args) => frpCreate({ key: "release-train", name: "Release train", default: undefined, ...args });
  assert.equal(frp.mcpCreatesAnotherPlan({ trajectory: [confirm(), create()] }).pass, true);
  assert.equal(frp.mcpCreatesAnotherPlan({ trajectory: [confirm(), create({ default: true })] }).pass, false, "the default");
  assert.equal(frp.mcpCreatesAnotherPlan({ trajectory: [confirm(), create(), frpUpdate({ default: false })] }).pass, false, "Staged rollout written");
  assert.equal(frp.mcpCreatesAnotherPlan({ trajectory: [] }).pass, false);
});

test("readOnlyAsksToRunList wants exactly one Run this command question holding the list command", () => {
  const cmd = block(getCmd());
  assert.equal(frp.readOnlyAsksToRunList({ trajectory: [runAsk({ prompt: "Run this:\n" + cmd })] }).pass, true);
  const inPreview = runAsk({ prompt: "Run this command?" });
  inPreview.arguments.options[0].preview = cmd;
  assert.equal(frp.readOnlyAsksToRunList({ trajectory: [inPreview] }).pass, true, "in the preview");
  assert.equal(frp.readOnlyAsksToRunList(out([turn(1, cmd)], { trajectory: [] })).pass, false, "only listed, never asked");
  assert.equal(frp.readOnlyAsksToRunList({ trajectory: [runAsk({ prompt: "Run this:\n" + cmd }), runAsk({ prompt: "Again:\n" + cmd })] }).pass, false, "two questions");
  assert.equal(frp.readOnlyAsksToRunList({ trajectory: [runAsk({ prompt: "Run this:\n" + block(getCmd("/staged-rollout")) })] }).pass, false, "not the list");
});

test("asksToRunOnlyReads fails when a Run this command question holds a write", () => {
  assert.equal(frp.asksToRunOnlyReads({ trajectory: [] }).pass, true);
  assert.equal(frp.asksToRunOnlyReads({ trajectory: [runAsk({ prompt: block(getCmd()) })] }).pass, true);
  assert.equal(frp.asksToRunOnlyReads({ trajectory: [runAsk({ prompt: block(writeCmd("POST", "", body())) })] }).pass, false);
});

test("noReconnectAdvice fails when the user is told to update or reconnect the MCP server", () => {
  assert.equal(frp.noReconnectAdvice(out([], { response: "Staged rollout is the default." })).pass, true);
  assert.equal(frp.noReconnectAdvice(out([], { response: "Updating or reconnecting the LaunchDarkly MCP server should add the tool." })).pass, false);
  assert.equal(frp.noReconnectAdvice(out([], { response: "Your MCP server may be out of date." })).pass, false);
});

test("runQuestionShowsCommand fails on a preview that only points at the command", () => {
  const ref = runAsk({ prompt: "Run this command?" });
  ref.arguments.options[0].preview = "(full command above)";
  const r = checks.runQuestionShowsCommand(out([turn(1, block(getCmd()))], { trajectory: [ref] }));
  assert.equal(r.pass, false);
  assert.match(r.reason, /only points at it/);
  const both = runAsk({ prompt: "Run this:\n" + block(getCmd()) });
  both.arguments.options[0].preview = "(full command above)";
  assert.equal(checks.runQuestionShowsCommand(out([], { trajectory: [both] })).pass, true, "the question text holds it");
});
