const { test } = require("node:test");
const assert = require("node:assert/strict");

// The provider's default export is the class; stripRawWrapper is attached to it
// for testing. It unwraps a Nunjucks `{% raw %}...{% endraw %}` block so a diff
// containing `{{ ... }}` survives promptfoo's var rendering.
const { stripRawWrapper } = require("../providers/claude-skill-agent-sdk");

test("strips a raw wrapper and preserves inner content verbatim", () => {
  const inner = "style={{ fontSize: 13 }}\nconst x = {{ y }};";
  const wrapped = `{% raw %}\n${inner}\n{% endraw %}`;
  assert.equal(stripRawWrapper(wrapped), inner);
});

test("is a no-op when there is no wrapper", () => {
  const s = "diff --git a/x b/x\n+const a = 1;";
  assert.equal(stripRawWrapper(s), s);
});

test("tolerates surrounding whitespace around the tags", () => {
  assert.equal(stripRawWrapper("  {% raw %}\nhello\n{% endraw %}  "), "hello");
});

test("tolerates flexible spacing inside the tags", () => {
  assert.equal(stripRawWrapper("{%raw%}\nabc\n{%endraw%}"), "abc");
});

test("does not strip a lone opening tag (both required)", () => {
  const s = "{% raw %}\nno closing tag here";
  assert.equal(stripRawWrapper(s), s);
});

test("returns non-string values unchanged", () => {
  assert.equal(stripRawWrapper(undefined), undefined);
  assert.equal(stripRawWrapper(null), null);
  assert.deepEqual(stripRawWrapper({ a: 1 }), { a: 1 });
});
