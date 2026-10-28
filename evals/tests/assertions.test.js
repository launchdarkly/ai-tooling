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
  const out = makeOutput(["get-agent-configs", "setup-agent-config"]);
  assert.deepEqual(getTools(out), ["get-agent-configs", "setup-agent-config"]);
});

test("getTools returns [] for missing/invalid output", () => {
  assert.deepEqual(getTools(null), []);
  assert.deepEqual(getTools({}), []);
  assert.deepEqual(getTools({ tools_called: "bad" }), []);
});

test("getTrajectory returns trajectory array", () => {
  const out = makeOutput(["setup-agent-config"]);
  assert.equal(getTrajectory(out).length, 1);
  assert.equal(getTrajectory(out)[0].tool, "setup-agent-config");
});

test("getTrajectory returns [] for missing/invalid output", () => {
  assert.deepEqual(getTrajectory(null), []);
  assert.deepEqual(getTrajectory({}), []);
});

// ---------------------------------------------------------------------------
// firstCallOf / lastCallOf
// ---------------------------------------------------------------------------

test("firstCallOf returns first occurrence", () => {
  const out = makeOutput(["get-agent-configs", "setup-agent-config", "get-agent-configs"]);
  const { call, idx } = firstCallOf(out, "get-agent-configs");
  assert.equal(idx, 0);
  assert.equal(call.tool, "get-agent-configs");
});

test("lastCallOf returns last occurrence", () => {
  const out = makeOutput(["get-agent-configs", "setup-agent-config", "get-agent-configs"]);
  const { call, idx } = lastCallOf(out, "get-agent-configs");
  assert.equal(idx, 2);
  assert.equal(call.tool, "get-agent-configs");
});

test("firstCallOf returns idx=-1 when not found", () => {
  const out = makeOutput(["setup-agent-config"]);
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
  const out = makeOutput(["setup-agent-config"]);
  assert.equal(called(out, "setup-agent-config"), true);
  assert.equal(called(out, "delete-agent-config"), false);
});

test("calledAny returns true if at least one tool matches", () => {
  const out = makeOutput(["create-agent-config"]);
  assert.equal(calledAny(out, ["setup-agent-config", "create-agent-config"]), true);
  assert.equal(calledAny(out, ["setup-agent-config", "delete-agent-config"]), false);
});

test("calledNone returns true only if no tools match", () => {
  const out = makeOutput(["get-agent-configs", "setup-agent-config"]);
  assert.equal(calledNone(out, ["delete-agent-config", "archive-flag"]), true);
  assert.equal(calledNone(out, ["setup-agent-config"]), false);
});

// ---------------------------------------------------------------------------
// expectAfter
// ---------------------------------------------------------------------------

test("expectAfter passes when after follows before", () => {
  const out = makeOutput(["get-agent-configs", "setup-agent-config"]);
  const r = expectAfter(out, { before: "get-agent-configs", after: "setup-agent-config" });
  assert.equal(r.pass, true);
  assert.equal(r.score, 1);
});

test("expectAfter fails when before is absent", () => {
  const out = makeOutput(["setup-agent-config"]);
  const r = expectAfter(out, { before: "get-agent-configs", after: "setup-agent-config" });
  assert.equal(r.pass, false);
  assert.equal(r.score, 0);
});

test("expectAfter fails when after is absent", () => {
  const out = makeOutput(["get-agent-configs"]);
  const r = expectAfter(out, { before: "get-agent-configs", after: "setup-agent-config" });
  assert.equal(r.pass, false);
});

test("expectAfter uses last occurrence of after vs first occurrence of before", () => {
  // get-agent-configs appears before AND after setup; last get-agent-configs should be after setup
  const out = makeOutput(["get-agent-configs", "setup-agent-config", "get-agent-configs"]);
  const r = expectAfter(out, { before: "setup-agent-config", after: "get-agent-configs" });
  assert.equal(r.pass, true);
});

test("expectAfter fails when after only appears before before", () => {
  const out = makeOutput(["get-agent-configs", "setup-agent-config"]);
  // last get-agent-configs is at idx 0, setup-agent-config (before) is at idx 1 — so after < before
  const r = expectAfter(out, { before: "setup-agent-config", after: "get-agent-configs" });
  assert.equal(r.pass, false);
});

// ---------------------------------------------------------------------------
// expectNotCalled / expectAnyCalled
// ---------------------------------------------------------------------------

test("expectNotCalled passes when none of the tools appear", () => {
  const out = makeOutput(["setup-agent-config"]);
  const r = expectNotCalled(out, ["delete-agent-config", "archive-flag"]);
  assert.equal(r.pass, true);
  assert.equal(r.score, 1);
});

test("expectNotCalled fails when a forbidden tool appears", () => {
  const out = makeOutput(["setup-agent-config", "delete-agent-config"]);
  const r = expectNotCalled(out, ["delete-agent-config"]);
  assert.equal(r.pass, false);
  assert.equal(r.score, 0);
  assert.match(r.reason, /delete-agent-config/);
});

test("expectAnyCalled passes when at least one tool appears", () => {
  const out = makeOutput(["create-agent-config"]);
  const r = expectAnyCalled(out, ["setup-agent-config", "create-agent-config"]);
  assert.equal(r.pass, true);
  assert.equal(r.score, 1);
  assert.match(r.reason, /create-agent-config/);
});

test("expectAnyCalled fails when no matching tool appears", () => {
  const out = makeOutput(["get-agent-configs"]);
  const r = expectAnyCalled(out, ["setup-agent-config", "create-agent-config"]);
  assert.equal(r.pass, false);
  assert.equal(r.score, 0);
});
