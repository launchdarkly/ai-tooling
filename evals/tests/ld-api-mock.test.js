const { test } = require("node:test");
const assert = require("node:assert/strict");

// The local REST API mock behind ld_api_mock: flag release plan routes, the
// releases service's validation rules, and the provider's environment.
const { createLdApiState, handleLdApiRequest, startLdApiMock } = require("../providers/_ld_api_mock");
const { ldApiEnvironment } = require("../providers/claude-skill-agent-sdk");

const TOKEN = "eval-token";
const BASE = "/api/v2/projects/default";
const headers = (extra = {}) => ({ authorization: TOKEN, "ld-api-version": "beta", ...extra });
const call = (state, method, path, body, opts = {}) =>
  handleLdApiRequest(state, { method, path: BASE + path, query: opts.query || {}, headers: opts.headers || headers(), body }, { token: TOKEN, overrides: opts.overrides });

const seed = () => createLdApiState({ environmentReleasePlans: { test: ["progressive"], production: ["progressive-2"] } });
const planBody = (extra = {}) => ({
  key: "default-release",
  name: "Default release",
  environments: [
    { environmentKey: "test", environmentReleasePlanKey: "progressive", triggerType: "flag_eval" },
    { environmentKey: "production", environmentReleasePlanKey: "progressive-2", triggerType: "flag_eval" },
  ],
  ...extra,
});

test("a request without the beta header is rejected", () => {
  const out = call(seed(), "GET", "/flag-release-plans", undefined, { headers: { authorization: TOKEN } });
  assert.equal(out.status, 400);
  assert.match(out.body.message, /LD-API-Version: beta/);
});

test("a request without the token is 401", () => {
  const out = call(seed(), "GET", "/flag-release-plans", undefined, { headers: { "ld-api-version": "beta" } });
  assert.equal(out.status, 401);
});

test("create returns the plan with defaults, and list and get read it back", () => {
  const state = seed();
  const created = call(state, "POST", "/flag-release-plans", planBody({ isDefault: true }));
  assert.equal(created.status, 201);
  assert.equal(created.body.version, 1);
  assert.equal(created.body.executionMode, "sequential");
  assert.equal(created.body.isDefault, true);
  const list = call(state, "GET", "/flag-release-plans");
  assert.equal(list.body.totalCount, 1);
  assert.equal(list.body.items[0].key, "default-release");
  assert.equal(call(state, "GET", "/flag-release-plans/default-release").status, 200);
  assert.equal(call(state, "GET", "/flag-release-plans/missing").status, 404);
});

test("a taken key is 409", () => {
  const state = seed();
  call(state, "POST", "/flag-release-plans", planBody());
  assert.equal(call(state, "POST", "/flag-release-plans", planBody()).status, 409);
});

test("isDefault on create while the project has a default is 400", () => {
  const state = seed();
  call(state, "POST", "/flag-release-plans", planBody({ isDefault: true }));
  const out = call(state, "POST", "/flag-release-plans", planBody({ key: "second", isDefault: true }));
  assert.equal(out.status, 400);
  assert.match(out.body.message, /already has a default/);
});

test("an environment needs a known release plan unless it is immediate", () => {
  const state = seed();
  const missing = planBody({ environments: [{ environmentKey: "test", triggerType: "flag_eval" }] });
  assert.equal(call(state, "POST", "/flag-release-plans", missing).status, 400);
  const unknown = planBody({ environments: [{ environmentKey: "test", environmentReleasePlanKey: "nope", triggerType: "flag_eval" }] });
  assert.match(call(state, "POST", "/flag-release-plans", unknown).body.message, /doesn't exist/);
  const wrongEnv = planBody({ environments: [{ environmentKey: "test", environmentReleasePlanKey: "progressive-2", triggerType: "flag_eval" }] });
  assert.equal(call(state, "POST", "/flag-release-plans", wrongEnv).status, 400);
  const both = planBody({ environments: [{ environmentKey: "test", environmentReleasePlanKey: "progressive", isImmediate: true, triggerType: "flag_eval" }] });
  assert.equal(call(state, "POST", "/flag-release-plans", both).status, 400);
  const immediate = planBody({ environments: [{ environmentKey: "test", isImmediate: true, triggerType: "flag_eval" }] });
  assert.equal(call(state, "POST", "/flag-release-plans", immediate).status, 201);
});

test("trigger rules: required, promotion not first, manual needs sequential", () => {
  const state = seed();
  const noTrigger = planBody({ environments: [{ environmentKey: "test", environmentReleasePlanKey: "progressive" }] });
  assert.equal(call(state, "POST", "/flag-release-plans", noTrigger).status, 400);
  const promoFirst = planBody({ environments: [{ environmentKey: "test", environmentReleasePlanKey: "progressive", triggerType: "promotion" }] });
  assert.equal(call(state, "POST", "/flag-release-plans", promoFirst).status, 400);
  const manualParallel = planBody({ executionMode: "parallel", environments: [{ environmentKey: "test", environmentReleasePlanKey: "progressive", triggerType: "manual" }] });
  assert.equal(call(state, "POST", "/flag-release-plans", manualParallel).status, 400);
});

test("environment release plans created this run count as existing", () => {
  const created = { production: [{ key: "starter" }] };
  const state = createLdApiState({}, (env, key) => (created[env] || []).some((p) => p.key === key));
  const body = planBody({ environments: [{ environmentKey: "production", environmentReleasePlanKey: "starter", triggerType: "flag_eval" }] });
  assert.equal(call(state, "POST", "/flag-release-plans", body).status, 201);
});

test("put is a full replace: isDefault demotes the old default, omitting it clears it, a stale version is 409", () => {
  const state = seed();
  call(state, "POST", "/flag-release-plans", planBody({ key: "old", isDefault: true }));
  call(state, "POST", "/flag-release-plans", planBody({ key: "new" }));
  const { key: _k, ...rest } = planBody();
  const promoted = call(state, "PUT", "/flag-release-plans/new", { ...rest, isDefault: true, version: 1 });
  assert.equal(promoted.status, 200);
  assert.equal(promoted.body.version, 2);
  assert.equal(call(state, "GET", "/flag-release-plans/old").body.isDefault, false);
  assert.equal(call(state, "PUT", "/flag-release-plans/new", { ...rest, isDefault: true, version: 1 }).status, 409);
  const cleared = call(state, "PUT", "/flag-release-plans/new", { ...rest, version: 2 });
  assert.equal(cleared.body.isDefault, false);
});

test("delete removes the plan", () => {
  const state = seed();
  call(state, "POST", "/flag-release-plans", planBody());
  assert.equal(call(state, "DELETE", "/flag-release-plans/default-release").status, 204);
  assert.equal(call(state, "GET", "/flag-release-plans").body.totalCount, 0);
});

test("a flag release from a plan needs the plan to exist", () => {
  const state = seed();
  assert.equal(call(state, "POST", "/flags/new-checkout/flag-releases", { kind: "plan", planKey: "default-release" }).status, 400);
  call(state, "POST", "/flag-release-plans", planBody());
  const out = call(state, "POST", "/flags/new-checkout/flag-releases", { kind: "plan", planKey: "default-release" });
  assert.equal(out.status, 201);
  assert.ok(out.body.id);
});

test("overrides force a response, and an array answers successive calls", () => {
  const state = seed();
  const overrides = { "GET flag-release-plans": [{ status: 403, body: { code: "forbidden", message: "Plan does not allow this operation" } }, { status: 200, body: { items: [], totalCount: 0 } }] };
  assert.equal(call(state, "GET", "/flag-release-plans", undefined, { overrides }).status, 403);
  assert.equal(call(state, "GET", "/flag-release-plans", undefined, { overrides }).status, 200);
  assert.equal(call(state, "GET", "/flag-release-plans", undefined, { overrides }).status, 200);
});

test("a null override entry answers normally", () => {
  const state = seed();
  const overrides = { "POST flag-release-plans": [{ status: 409, body: { code: "conflict", message: "taken" } }, null] };
  assert.equal(call(state, "POST", "/flag-release-plans", planBody(), { overrides }).status, 409);
  assert.equal(call(state, "POST", "/flag-release-plans", planBody(), { overrides }).status, 201);
});

test("seeded environment release plans list with the first as the default", () => {
  const out = call(seed(), "GET", "/environments/production/release-plans");
  assert.deepEqual(out.body.items.map((p) => [p.key, p.default]), [["progressive-2", true]]);
  assert.equal(call(seed(), "GET", "/environments/production/default-release-plan").body.key, "progressive-2");
  assert.equal(call(seed(), "GET", "/environments/staging/default-release-plan").status, 404);
});

test("an unknown route is 404", () => {
  assert.equal(call(seed(), "GET", "/flags").status, 404);
});

test("the server records each request without the token", async () => {
  const entries = [];
  const api = await startLdApiMock({ state: seed(), token: TOKEN, record: (e) => entries.push(e) });
  try {
    const res = await fetch(`${api.baseUri}${BASE}/flag-release-plans`, {
      method: "POST",
      headers: { Authorization: TOKEN, "LD-API-Version": "beta", "Content-Type": "application/json" },
      body: JSON.stringify(planBody()),
    });
    assert.equal(res.status, 201);
    assert.equal((await res.json()).key, "default-release");
  } finally {
    await api.close();
  }
  assert.equal(entries.length, 1);
  assert.equal(entries[0].method, "POST");
  assert.equal(entries[0].apiVersion, "beta");
  assert.equal(entries[0].authorized, true);
  assert.equal(entries[0].body.key, "default-release");
  assert.ok(!JSON.stringify(entries).includes(TOKEN));
});

test("the agent's environment drops real credentials and points at the mock", () => {
  const env = ldApiEnvironment({ LD_ACCESS_TOKEN: "real", LD_BASE_URI: "https://app.launchdarkly.com", LAUNCHDARKLY_API_KEY: "x", PATH: "/bin", LD_LIBRARY_PATH: "/lib" }, "http://127.0.0.1:1", "fake");
  assert.equal(env.LD_ACCESS_TOKEN, "fake");
  assert.equal(env.LD_BASE_URI, "http://127.0.0.1:1");
  assert.equal(env.LAUNCHDARKLY_API_KEY, undefined);
  assert.equal(env.PATH, "/bin");
  assert.equal(env.LD_LIBRARY_PATH, "/lib");
  const noToken = ldApiEnvironment({ LD_ACCESS_TOKEN: "real" }, "http://127.0.0.1:1", null);
  assert.equal(noToken.LD_ACCESS_TOKEN, undefined);
});
