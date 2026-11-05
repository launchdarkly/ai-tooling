const { test } = require("node:test");
const assert = require("node:assert/strict");

const transform = require("../shared/transform");

test("returns parsed object when given valid JSON string", () => {
  const input = JSON.stringify({ response: "hello", tools_called: ["setup-agentcontrol-config"] });
  const result = transform(input);
  assert.deepEqual(result, { response: "hello", tools_called: ["setup-agentcontrol-config"] });
});

test("returns object unchanged when already an object", () => {
  const input = { response: "hello" };
  const result = transform(input);
  assert.equal(result, input);
});

test("returns raw string when JSON.parse fails", () => {
  const bad = "not json {{";
  const result = transform(bad);
  assert.equal(result, bad);
});

test("returns non-string, non-object values unchanged", () => {
  assert.equal(transform(null), null);
  assert.equal(transform(42), 42);
  assert.equal(transform(undefined), undefined);
});
