const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  getTools,
  getTrajectory,
  firstCallOf,
  lastCallOf,
  called,
  calledAny,
  calledNone,
  expectAfter,
  expectNotCalled,
  expectAnyCalled,
} = require("../shared/assertions");

// Fixture helpers
function makeOutput(tools) {
  const trajectory = tools.map((tool, i) => ({
    tool,
    arguments: {},
    turn: i + 1,
  }));
  return { tools_called: tools, trajectory };
}

// ---------------------------------------------------------------------------
// getTools / getTrajectory
// ---------------------------------------------------------------------------

test("getTools returns tools_called array", () => {
  const out = makeOutput(["list-agentcontrol-configs", "setup-agentcontrol-config"]);
  assert.deepEqual(getTools(out), ["list-agentcontrol-configs", "setup-agentcontrol-config"]);
});

test("getTools returns [] for missing/invalid output", () => {
  assert.deepEqual(getTools(null), []);
  assert.deepEqual(getTools({}), []);
  assert.deepEqual(getTools({ tools_called: "bad" }), []);
});

test("getTrajectory returns trajectory array", () => {
  const out = makeOutput(["setup-agentcontrol-config"]);
  assert.equal(getTrajectory(out).length, 1);
  assert.equal(getTrajectory(out)[0].tool, "setup-agentcontrol-config");
});

test("getTrajectory returns [] for missing/invalid output", () => {
  assert.deepEqual(getTrajectory(null), []);
  assert.deepEqual(getTrajectory({}), []);
});

// ---------------------------------------------------------------------------
// firstCallOf / lastCallOf
// ---------------------------------------------------------------------------

test("firstCallOf returns first occurrence", () => {
  const out = makeOutput(["get-agentcontrol-config", "setup-agentcontrol-config", "get-agentcontrol-config"]);
  const { call, idx } = firstCallOf(out, "get-agentcontrol-config");
  assert.equal(idx, 0);
  assert.equal(call.tool, "get-agentcontrol-config");
});

test("lastCallOf returns last occurrence", () => {
  const out = makeOutput(["get-agentcontrol-config", "setup-agentcontrol-config", "get-agentcontrol-config"]);
  const { call, idx } = lastCallOf(out, "get-agentcontrol-config");
  assert.equal(idx, 2);
  assert.equal(call.tool, "get-agentcontrol-config");
});

test("firstCallOf returns idx=-1 when not found", () => {
  const out = makeOutput(["setup-agentcontrol-config"]);
  assert.equal(firstCallOf(out, "missing-tool").idx, -1);
  assert.equal(firstCallOf(out, "missing-tool").call, null);
});

test("lastCallOf returns idx=-1 when not found", () => {
  const out = makeOutput([]);
  assert.equal(lastCallOf(out, "anything").idx, -1);
});

// ---------------------------------------------------------------------------
// called / calledAny / calledNone
// ---------------------------------------------------------------------------

test("called returns true when tool is present", () => {
  const out = makeOutput(["setup-agentcontrol-config"]);
  assert.equal(called(out, "setup-agentcontrol-config"), true);
  assert.equal(called(out, "delete-agentcontrol-config"), false);
});

test("calledAny returns true if at least one tool matches", () => {
  const out = makeOutput(["create-agentcontrol-config"]);
  assert.equal(calledAny(out, ["setup-agentcontrol-config", "create-agentcontrol-config"]), true);
  assert.equal(calledAny(out, ["setup-agentcontrol-config", "delete-agentcontrol-config"]), false);
});

test("calledNone returns true only if no tools match", () => {
  const out = makeOutput(["list-agentcontrol-configs", "setup-agentcontrol-config"]);
  assert.equal(calledNone(out, ["delete-agentcontrol-config", "archive-flag"]), true);
  assert.equal(calledNone(out, ["setup-agentcontrol-config"]), false);
});

// ---------------------------------------------------------------------------
// expectAfter
// ---------------------------------------------------------------------------

test("expectAfter passes when after follows before", () => {
  const out = makeOutput(["list-agentcontrol-configs", "setup-agentcontrol-config"]);
  const r = expectAfter(out, { before: "list-agentcontrol-configs", after: "setup-agentcontrol-config" });
  assert.equal(r.pass, true);
  assert.equal(r.score, 1);
});

test("expectAfter fails when before is absent", () => {
  const out = makeOutput(["setup-agentcontrol-config"]);
  const r = expectAfter(out, { before: "list-agentcontrol-configs", after: "setup-agentcontrol-config" });
  assert.equal(r.pass, false);
  assert.equal(r.score, 0);
});

test("expectAfter fails when after is absent", () => {
  const out = makeOutput(["list-agentcontrol-configs"]);
  const r = expectAfter(out, { before: "list-agentcontrol-configs", after: "setup-agentcontrol-config" });
  assert.equal(r.pass, false);
});

test("expectAfter uses last occurrence of after vs first occurrence of before", () => {
  // get-agentcontrol-config appears before AND after setup; last get-agentcontrol-config should be after setup
  const out = makeOutput(["get-agentcontrol-config", "setup-agentcontrol-config", "get-agentcontrol-config"]);
  const r = expectAfter(out, { before: "setup-agentcontrol-config", after: "get-agentcontrol-config" });
  assert.equal(r.pass, true);
});

test("expectAfter fails when after only appears before before", () => {
  const out = makeOutput(["get-agentcontrol-config", "setup-agentcontrol-config"]);
  // last get-agentcontrol-config is at idx 0, setup-agentcontrol-config (before) is at idx 1 — so after < before
  const r = expectAfter(out, { before: "setup-agentcontrol-config", after: "get-agentcontrol-config" });
  assert.equal(r.pass, false);
});

// ---------------------------------------------------------------------------
// expectNotCalled / expectAnyCalled
// ---------------------------------------------------------------------------

test("expectNotCalled passes when none of the tools appear", () => {
  const out = makeOutput(["setup-agentcontrol-config"]);
  const r = expectNotCalled(out, ["delete-agentcontrol-config", "archive-flag"]);
  assert.equal(r.pass, true);
  assert.equal(r.score, 1);
});

test("expectNotCalled fails when a forbidden tool appears", () => {
  const out = makeOutput(["setup-agentcontrol-config", "delete-agentcontrol-config"]);
  const r = expectNotCalled(out, ["delete-agentcontrol-config"]);
  assert.equal(r.pass, false);
  assert.equal(r.score, 0);
  assert.match(r.reason, /delete-agentcontrol-config/);
});

test("expectAnyCalled passes when at least one tool appears", () => {
  const out = makeOutput(["create-agentcontrol-config"]);
  const r = expectAnyCalled(out, ["setup-agentcontrol-config", "create-agentcontrol-config"]);
  assert.equal(r.pass, true);
  assert.equal(r.score, 1);
  assert.match(r.reason, /create-agentcontrol-config/);
});

test("expectAnyCalled fails when no matching tool appears", () => {
  const out = makeOutput(["list-agentcontrol-configs"]);
  const r = expectAnyCalled(out, ["setup-agentcontrol-config", "create-agentcontrol-config"]);
  assert.equal(r.pass, false);
  assert.equal(r.score, 0);
});
