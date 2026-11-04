/**
 * Prompt function for this suite: returns SKILL.md wrapped in nunjucks `{% raw %}`.
 *
 * promptfoo renders every prompt through nunjucks, and this SKILL.md 
 * uses its own placeholder-hole syntax — `{{measurement:...}}`,
 * `{{component:hint}}` in the output-contract examples. Nunjucks parses `measurement`
 * as a variable, hits the `:`, and throws "expected variable end" on all the tests.
 *
 * A function prompt does NOT skip the nunjucks pass: promptfoo's renderPrompt 
 * assigns the function's return value to basePrompt and still calls nunjucks.renderString on it. 
 * Its own escape hatch,
 * autoWrapRawIfPartialNunjucks, only fires on *unclosed* tags (`{{` with no `}}`), so
 * closed-but-invalid expressions like `{{measurement:...}}` go through unprotected.
 * Wrapping here supplies the `{% raw %}` that helper would have added. renderString then
 * returns the file byte-for-byte, so results.json still shows the exact skill text.
 * The tags live only in this in-memory prompt — SKILL.md is not changed.
 *
 * The prompt is not what the agent under test sees. The skill is loaded into
 * `.claude/skills/<slug>/`, and builds the user turn from vars.user_request. This
 * exists to satisfy promptfoo's requirement that a prompt be defined.
 */
const fs = require("node:fs");
const path = require("node:path");

const SKILL_MD = path.resolve(
  __dirname,
  "../../skills/experiments/launchdarkly-experiment-hypothesis-builder/SKILL.md",
);

module.exports = () => `{% raw %}${fs.readFileSync(SKILL_MD, "utf-8")}{% endraw %}`;
