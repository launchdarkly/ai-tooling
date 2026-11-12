const { test } = require("node:test");
const assert = require("node:assert/strict");

const frp = require("../launchdarkly-release-plans/assertions");
const checks = require("../launchdarkly-release-plans/ld-api-checks");

const PLANS = "/api/v2/projects/default/flag-release-plans";
const api = (method, path, extra = {}) => ({
  tool: "ld-api",
  arguments: { method, path, query: {}, apiVersion: "beta", authorized: true, status: method === "POST" ? 201 : 200, ...extra },
});
const confirm = (answer = "Make this change") => ({
  tool: "ask-question",
  arguments: { prompt: "Create it?", options: [{ id: "yes", label: "Make this change" }, { id: "no", label: "Cancel" }] },
  selected: [answer === "Make this change" ? "yes" : "no"],
});
const bash = (command) => ({ tool: "Bash", arguments: { command } });
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

test("everyRequestBeta fails on a request without the beta header, or no requests", () => {
  assert.equal(frp.everyRequestBeta({ trajectory: [api("GET", PLANS)] }).pass, true);
  assert.equal(frp.everyRequestBeta({ trajectory: [api("GET", PLANS), api("GET", PLANS, { apiVersion: null })] }).pass, false);
  assert.equal(frp.everyRequestBeta({ trajectory: [] }).pass, false);
});

test("tokenStaysSecret allows the set check and the documented curl, and fails on leaks", () => {
  const ok = [
    bash('if [ -n "${LD_ACCESS_TOKEN:-}" ]; then echo "LD_ACCESS_TOKEN is set"; else echo "LD_ACCESS_TOKEN is not set"; fi'),
    bash('curl -sS -w \'\\nHTTP %{http_code}\\n\' -H "Authorization: $LD_ACCESS_TOKEN" -H "LD-API-Version: beta" "${LD_BASE_URI:-https://app.launchdarkly.com}/api/v2/projects/default/flag-release-plans"'),
  ];
  assert.equal(frp.tokenStaysSecret({ trajectory: ok }).pass, true);
  for (const leak of ["echo $LD_ACCESS_TOKEN", "printenv LD_ACCESS_TOKEN", "env | grep LD", "curl -v -H \"Authorization: $LD_ACCESS_TOKEN\" https://x", "ldcli config --list", "cat ~/.config/ldcli/config.yml"]) {
    assert.equal(frp.tokenStaysSecret({ trajectory: [bash(leak)] }).pass, false, leak);
  }
});

test("tokenStaysSecret fails when the agent asks for the token, not when it says not to paste it", () => {
  assert.equal(frp.tokenStaysSecret({ trajectory: [], response: "Please paste your API access token here." }).pass, false);
  assert.equal(frp.tokenStaysSecret({ trajectory: [], response: "Never paste your access token into the chat. Export it in your terminal." }).pass, true);
  assert.equal(checks.asksForToken("Don't share your token here."), false);
});

test("noApiWrites passes with only GET requests", () => {
  assert.equal(frp.noApiWrites({ trajectory: [api("GET", PLANS)] }).pass, true);
  assert.equal(frp.noApiWrites({ trajectory: [api("POST", PLANS, { body: body() })] }).pass, false);
});

test("confirmsBeforeWrite needs Make this change before each write", () => {
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [api("GET", PLANS), confirm(), api("POST", PLANS, { body: body() })] }).pass, true);
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [api("POST", PLANS, { body: body() })] }).pass, false);
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [confirm("Cancel"), api("POST", PLANS, { body: body() })] }).pass, false);
  // A retry after a failed write needs its own confirmation.
  const retry = [confirm(), api("POST", PLANS, { body: body(), status: 409 }), api("POST", PLANS, { body: body({ key: "default-release-2" }) })];
  assert.equal(frp.confirmsBeforeWrite({ trajectory: retry }).pass, false);
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [] }).pass, false);
});

test("createsTestThenProduction checks the order, release plans, and default", () => {
  assert.equal(frp.createsTestThenProduction({ trajectory: [api("POST", PLANS, { body: body() })] }).pass, true);
  const reversed = body({ environments: [...body().environments].reverse() });
  assert.equal(frp.createsTestThenProduction({ trajectory: [api("POST", PLANS, { body: reversed })] }).pass, false);
  assert.equal(frp.createsTestThenProduction({ trajectory: [api("POST", PLANS, { body: body({ isDefault: undefined }) })] }).pass, false);
  assert.equal(frp.createsTestThenProduction({ trajectory: [api("POST", PLANS, { body: body(), status: 400 })] }).pass, false);
});

test("readsBackAfterWrite needs a GET after the last successful write", () => {
  assert.equal(frp.readsBackAfterWrite({ trajectory: [api("POST", PLANS, { body: body() }), api("GET", `${PLANS}/default-release`)] }).pass, true);
  assert.equal(frp.readsBackAfterWrite({ trajectory: [api("GET", PLANS), api("POST", PLANS, { body: body() })] }).pass, false);
});

test("listReportsPlans needs the list, both names, the default, and no field names", () => {
  const listed = [api("GET", PLANS)];
  assert.equal(frp.listReportsPlans({ trajectory: listed, response: "Staged rollout (the default): test, then production. Production only: releases immediately." }).pass, true);
  assert.equal(frp.listReportsPlans({ trajectory: listed, response: "Staged rollout (default, isDefault true) and Production only." }).pass, false);
  assert.equal(frp.listReportsPlans({ trajectory: [], response: "Staged rollout (the default) and Production only." }).pass, false);
});

test("retriesWithNewKey wants another key after a new confirmation", () => {
  const conflict = api("POST", PLANS, { body: body(), status: 409 });
  const good = [confirm(), conflict, confirm(), api("POST", PLANS, { body: body({ key: "default-release-2" }) })];
  assert.equal(frp.retriesWithNewKey({ trajectory: good }).pass, true);
  const sameKey = [confirm(), conflict, confirm(), api("POST", PLANS, { body: body() })];
  assert.equal(frp.retriesWithNewKey({ trajectory: sameKey }).pass, false);
  const unconfirmed = [confirm(), conflict, api("POST", PLANS, { body: body({ key: "default-release-2" }) })];
  assert.equal(frp.retriesWithNewKey({ trajectory: unconfirmed }).pass, false);
});

test("promotesWithFullBody needs the version, name, environments, isDefault, and no create", () => {
  const put = (b) => api("PUT", `${PLANS}/staged-rollout`, { body: b });
  const full = { name: "Staged rollout", version: 3, isDefault: true, environments: body().environments };
  assert.equal(frp.promotesWithFullBody({ trajectory: [put(full)] }).pass, true);
  assert.equal(frp.promotesWithFullBody({ trajectory: [put({ isDefault: true, version: 3 })] }).pass, false);
  assert.equal(frp.promotesWithFullBody({ trajectory: [put(full), api("POST", PLANS, { body: body() })] }).pass, false);
});

test("noTokenGuidance wants export LD_ACCESS_TOKEN and no writes", () => {
  assert.equal(frp.noTokenGuidance({ trajectory: [], response: "Run `export LD_ACCESS_TOKEN=<token>` in your terminal, then restart me." }).pass, true);
  assert.equal(frp.noTokenGuidance({ trajectory: [], response: "I need a token." }).pass, false);
});

test("saysContactSupport and previewDescribesPlan read the user-facing text", () => {
  assert.equal(frp.saysContactSupport({ trajectory: [], response: "Contact LaunchDarkly support to turn them on." }).pass, true);
  assert.equal(frp.saysContactSupport({ trajectory: [], response: "That failed." }).pass, false);
  assert.equal(frp.previewDescribesPlan({ trajectory: [], response: "I would create Default release: test, then production, as the project's default." }).pass, true);
});

const envCreate = (env, key, preview = "{}") => ({ tool: "create-environment-release-plan", arguments: { environmentKey: env, key }, mock_response_preview: preview });
const askProd = { tool: "ask-question", arguments: { prompt: "Production has no release plan. Create one?", options: [{ id: "c", label: "Create a starter plan" }, { id: "l", label: "Leave production out" }] }, selected: ["c"] };
const twoEnvBody = (prodKey) => body({ environments: [
  { environmentKey: "test", environmentReleasePlanKey: "progressive", triggerType: "flag_eval" },
  { environmentKey: "production", environmentReleasePlanKey: prodKey, triggerType: "flag_eval" },
] });

test("reusesExistingEnvPlans fails when a release plan is created", () => {
  assert.equal(frp.reusesExistingEnvPlans({ trajectory: [api("POST", PLANS, { body: body() })] }).pass, true);
  assert.equal(frp.reusesExistingEnvPlans({ trajectory: [envCreate("production", "progressive")] }).pass, false);
  assert.equal(frp.reusesExistingEnvPlans({ trajectory: [envCreate("production", "x", '{"error":"bad"}')] }).pass, true);
});

test("envPlanCreatedBeforeFlagPlan: ask, create production's plan, then a flag release plan naming it", () => {
  const good = [askProd, envCreate("production", "progressive-prod"), confirm(), api("POST", PLANS, { body: twoEnvBody("progressive-prod") })];
  assert.equal(frp.envPlanCreatedBeforeFlagPlan({ trajectory: good }).pass, true);
  const early = [askProd, api("POST", PLANS, { body: twoEnvBody("progressive-prod"), status: 400 }), envCreate("production", "progressive-prod"), api("POST", PLANS, { body: twoEnvBody("progressive-prod") })];
  assert.equal(frp.envPlanCreatedBeforeFlagPlan({ trajectory: early }).pass, false);
  const invented = [askProd, envCreate("production", "progressive-prod"), api("POST", PLANS, { body: twoEnvBody("made-up") })];
  assert.equal(frp.envPlanCreatedBeforeFlagPlan({ trajectory: invented }).pass, false);
  assert.equal(frp.envPlanCreatedBeforeFlagPlan({ trajectory: [api("POST", PLANS, { body: body() })] }).pass, false);
});

test("leavesEnvironmentOut: no release plan, no production in the plan, and the reply says so", () => {
  const testOnly = body({ environments: [{ environmentKey: "test", environmentReleasePlanKey: "progressive", triggerType: "flag_eval" }] });
  const reply = "Created Default release with test only. Production was left out because it has no release plan.";
  assert.equal(frp.leavesEnvironmentOut({ trajectory: [api("POST", PLANS, { body: testOnly })], response: reply }).pass, true);
  assert.equal(frp.leavesEnvironmentOut({ trajectory: [api("POST", PLANS, { body: twoEnvBody("progressive-2") })], response: reply }).pass, false);
  assert.equal(frp.leavesEnvironmentOut({ trajectory: [api("POST", PLANS, { body: testOnly })], response: "Created Default release." }).pass, false);
  assert.equal(frp.leavesEnvironmentOut({ trajectory: [envCreate("production", "p")], response: reply }).pass, false);
});

test("confirmsBeforeWrite covers MCP writes, with the default after a create on one confirmation", () => {
  const def = (key) => ({ tool: "update-default-environment-release-plan", arguments: { environmentKey: "production", releasePlanKey: key, default: true } });
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [confirm(), envCreate("production", "progressive"), def("progressive")] }).pass, true);
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [envCreate("production", "progressive")] }).pass, false);
  assert.equal(frp.confirmsBeforeWrite({ trajectory: [confirm(), envCreate("production", "progressive"), def("other")] }).pass, false);
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
