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
  isDefault: true,
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
  assert.equal(frp.createsTestThenProduction(out([turn(2, block(writeCmd("POST", "", body({ isDefault: undefined }))))])).pass, false);
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

test("promotesWithFullBody needs the version, name, environments, isDefault, and no create", () => {
  const full = { name: "Staged rollout", version: 3, isDefault: true, environments: body().environments };
  const put = (b) => turn(2, block(writeCmd("PUT", "/staged-rollout", b)));
  assert.equal(frp.promotesWithFullBody(out([put(full)])).pass, true);
  assert.equal(frp.promotesWithFullBody(out([put({ isDefault: true, version: 3 })])).pass, false);
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

const runAsk = (args) => ({ tool: "ask-question", arguments: { options: [{ id: "done", label: "Done, here's the output" }, { id: "skip", label: "Skip" }], ...args } });
test("runQuestionShowsCommand needs the command in each Run this command question", () => {
  const cmd = block(getCmd());
  assert.equal(checks.runQuestionShowsCommand(out([turn(1, cmd)], { trajectory: [runAsk({ prompt: "Run this:\n" + cmd })] })).pass, true);
  const inPreview = runAsk({ prompt: "Run this command?" });
  inPreview.arguments.options[0].preview = cmd;
  assert.equal(checks.runQuestionShowsCommand(out([], { trajectory: [inPreview] })).pass, true);
  assert.equal(checks.runQuestionShowsCommand(out([turn(1, cmd)], { trajectory: [runAsk({ prompt: "Run this command?" })] })).pass, false);
  assert.equal(checks.runQuestionShowsCommand(out([turn(1, cmd)], { trajectory: [runAsk({ prompt: cmd }), runAsk({ prompt: "And this one?" })] })).pass, false);
  assert.equal(checks.runQuestionShowsCommand(out([turn(1, cmd)], { trajectory: [confirm()] })).pass, false);
});
