const { test } = require("node:test");
const assert = require("node:assert/strict");

// A test-level `expose_mcp_tools` var overrides the suite's provider config for
// that one test, so a suite can include a "no LaunchDarkly access" case.
const { resolveExposeMcpTools } = require("../providers/claude-skill-agent-sdk");

test("a false var turns the mocks off when the config has them on", () => {
  assert.equal(resolveExposeMcpTools(true, false), false);
});

test('a "false" string var turns the mocks off', () => {
  assert.equal(resolveExposeMcpTools(true, "false"), false);
});

test("a true var turns the mocks on when the config has them off", () => {
  assert.equal(resolveExposeMcpTools(false, true), true);
});

test('a "true" string var turns the mocks on', () => {
  assert.equal(resolveExposeMcpTools(false, "true"), true);
});

test("an absent var keeps the config's on setting", () => {
  assert.equal(resolveExposeMcpTools(true, undefined), true);
});

test("an absent var keeps the config's off setting", () => {
  assert.equal(resolveExposeMcpTools(false, undefined), false);
});

test("an unrecognized var value keeps the config setting", () => {
  assert.equal(resolveExposeMcpTools(true, "no"), true);
});
