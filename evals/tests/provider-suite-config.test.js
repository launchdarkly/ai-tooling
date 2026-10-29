const { test } = require("node:test");
const assert = require("node:assert/strict");

// Suite-level provider config: `exclude_mcp_tools` hides mock tools the skill's
// real MCP server doesn't offer, and `inline_skill` puts SKILL.md in the
// agent's instructions.
const { filterToolDefs, skillInstructions } = require("../providers/claude-skill-agent-sdk");

const defs = [{ name: "create-flag" }, { name: "create-feature-flag" }, { name: "get-flag" }];

test("no exclusions returns every definition", () => {
  assert.deepEqual(filterToolDefs(defs, undefined), defs);
  assert.deepEqual(filterToolDefs(defs, []), defs);
});

test("excluded tools are hidden", () => {
  assert.deepEqual(filterToolDefs(defs, ["create-feature-flag"]).map((d) => d.name), ["create-flag", "get-flag"]);
});

test("an unknown name hides nothing", () => {
  assert.deepEqual(filterToolDefs(defs, ["delete-flag"]), defs);
});

test("skillInstructions drops the frontmatter and wraps the body", () => {
  const out = skillInstructions('---\nname: "x"\ndescription: "y"\n---\n\n# Title\n\nDo the thing.\n');
  assert.ok(!out.includes('name: "x"'));
  assert.ok(out.includes("<skill>\n# Title\n\nDo the thing.\n</skill>"));
});

test("skillInstructions handles CRLF line endings and a BOM", () => {
  const out = skillInstructions('﻿---\r\nname: "x"\r\n---\r\n# Title\r\n');
  assert.ok(!out.includes('name: "x"'));
  assert.ok(out.includes("# Title"));
});
