const { test } = require("node:test");
const assert = require("node:assert/strict");

// A test-level `mock_overrides` var replaces a tool's shared template for that
// one test, so a suite can exercise branches like `requiresApproval`.
const { resolveMockOverride, renderOverride } = require("../providers/_mock");

test("no overrides returns undefined", () => {
  assert.equal(resolveMockOverride(undefined, "toggle-flag", 0), undefined);
  assert.equal(resolveMockOverride({}, "toggle-flag", 0), undefined);
});

test("an override for another tool returns undefined", () => {
  assert.equal(resolveMockOverride({ "get-flag": { a: 1 } }, "toggle-flag", 0), undefined);
});

test("an object override answers every call", () => {
  const overrides = { "toggle-flag": { requiresApproval: true } };
  assert.deepEqual(resolveMockOverride(overrides, "toggle-flag", 0), { requiresApproval: true });
  assert.deepEqual(resolveMockOverride(overrides, "toggle-flag", 5), { requiresApproval: true });
});

test("an array override answers successive calls and repeats its last entry", () => {
  const overrides = { "list-approval-requests": [{ status: "pending" }, { status: "approved" }] };
  assert.deepEqual(resolveMockOverride(overrides, "list-approval-requests", 0), { status: "pending" });
  assert.deepEqual(resolveMockOverride(overrides, "list-approval-requests", 1), { status: "approved" });
  assert.deepEqual(resolveMockOverride(overrides, "list-approval-requests", 7), { status: "approved" });
});

test("an empty array override falls back to the template", () => {
  assert.equal(resolveMockOverride({ "get-flag": [] }, "get-flag", 0), undefined);
});

test("renderOverride substitutes placeholders from the tool input", () => {
  const rendered = renderOverride({ key: "{{flagKey}}", nested: ["{{projectKey}}"] }, { flagKey: "exp-a", projectKey: "web" });
  assert.deepEqual(rendered, { key: "exp-a", nested: ["web"] });
});

test("a by_arg override answers by the argument's value", () => {
  const overrides = {
    "get-experiment-metric-results": {
      by_arg: "metricKey",
      cases: { "checkout-completed": { lift: 0.08 } },
      default: { lift: 0 },
    },
  };
  assert.deepEqual(resolveMockOverride(overrides, "get-experiment-metric-results", 0, { metricKey: "checkout-completed" }), { lift: 0.08 });
  assert.deepEqual(resolveMockOverride(overrides, "get-experiment-metric-results", 1, { metricKey: "error-rate" }), { lift: 0 });
  assert.deepEqual(resolveMockOverride(overrides, "get-experiment-metric-results", 2, {}), { lift: 0 });
});

// ---------------------------------------------------------------------------
// An override never hides a flag the agent created
// ---------------------------------------------------------------------------

const { renderMockResponse, createMockState } = require("../providers/_mock");
const TEMPLATES = require("../mocks/tool-responses.json");
const { overrideFor } = require("../providers/claude-skill-agent-sdk");

test("a get-flag override doesn't hide a flag the agent created", () => {
  const state = createMockState();
  const overrides = { "get-flag": { error: "flag not found" } };
  assert.deepEqual(overrideFor(overrides, "get-flag", 0, { flagKey: "exp-a" }, state), { error: "flag not found" });
  renderMockResponse(TEMPLATES["create-flag"], { projectKey: "p", key: "exp-a", name: "A" }, "create-flag", state);
  assert.equal(overrideFor(overrides, "get-flag", 1, { flagKey: "exp-a" }, state), undefined);
});
