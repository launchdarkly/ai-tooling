const { test } = require("node:test");
const assert = require("node:assert/strict");

// Suite-level provider config: `tool_definitions` adds or replaces mock tools,
// `exclude_mcp_tools` hides ones the skill's real MCP server doesn't offer, and `inline_skill` puts SKILL.md in the
// agent's instructions.
const { filterToolDefs, mergeToolDefs, skillInstructions } = require("../providers/claude-skill-agent-sdk");

const defs = [{ name: "create-flag" }, { name: "create-feature-flag" }, { name: "get-flag" }];

test("no exclusions returns every definition", () => {
  assert.deepEqual(filterToolDefs(defs, undefined), defs);
  assert.deepEqual(filterToolDefs(defs, []), defs);
});

test("excluded tools are hidden", () => {
  assert.deepEqual(filterToolDefs(defs, ["create-feature-flag"]).map((d) => d.name), ["create-flag", "get-flag"]);
});

test("a comma-separated string hides each named tool", () => {
  assert.deepEqual(filterToolDefs(defs, "create-feature-flag, get-flag").map((d) => d.name), ["create-flag"]);
  assert.deepEqual(filterToolDefs(defs, ""), defs);
});

// promptfoo turns a test var that is a list of strings into one test per
// item, so a per-test exclude_mcp_tools list would hide nothing.
test("no test sets exclude_mcp_tools to a list of strings", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const yaml = require("js-yaml");
  const root = path.join(__dirname, "..");
  const bad = [];
  for (const dir of fs.readdirSync(root)) {
    const file = path.join(root, dir, "promptfooconfig.yaml");
    if (!fs.existsSync(file)) continue;
    const cfg = yaml.load(fs.readFileSync(file, "utf8")) || {};
    for (const t of cfg.tests || []) {
      const v = t && t.vars && t.vars.exclude_mcp_tools;
      if (Array.isArray(v) && typeof v[0] === "string") bad.push(`${dir}: ${t.description}`);
    }
  }
  assert.deepEqual(bad, []);
});

test("an unknown name hides nothing", () => {
  assert.deepEqual(filterToolDefs(defs, ["delete-flag"]), defs);
});

test("suite definitions replace shared ones by name and add new tools", () => {
  const merged = mergeToolDefs(defs, [{ name: "get-flag", description: "suite" }, { name: "update-rollout" }]);
  assert.deepEqual(merged.map((d) => d.name), ["create-flag", "create-feature-flag", "get-flag", "update-rollout"]);
  assert.equal(merged.find((d) => d.name === "get-flag").description, "suite");
  assert.deepEqual(mergeToolDefs(defs, []), defs);
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

test("a test's exclude_mcp_tools hides tools on top of the suite's", () => {
  const suite = filterToolDefs(defs, ["create-feature-flag"]);
  assert.deepEqual(filterToolDefs(suite, ["get-flag"]).map((d) => d.name), ["create-flag"]);
});

test("skillInstructions appends references after the skill", () => {
  const out = skillInstructions("---\nname: x\n---\n# Skill\n", [{ path: "references/a.md", text: "# A\n" }]);
  assert.ok(out.includes("<skill>\n# Skill\n</skill>"));
  assert.ok(out.endsWith('<reference path="references/a.md">\n# A\n</reference>'));
});

test("readReferences lists a skill's reference files in order", () => {
  const { readReferences } = require("../providers/claude-skill-agent-sdk");
  const path = require("node:path");
  const refs = readReferences(path.join(__dirname, "..", "..", "skills", "release-autopilot", "launchdarkly-release-plans"));
  assert.deepEqual(refs.map((r) => r.path), ["references/environment-release-plans.md", "references/rest-api.md"]);
  assert.deepEqual(readReferences(path.join(__dirname, "no-such-skill")), []);
});
