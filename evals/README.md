# Skill Evaluations

Automated evaluations for LaunchDarkly agent skills using [promptfoo](https://promptfoo.dev).

Each skill gets a set of test cases that verify an agent follows the skill's workflow correctly when given realistic user requests. The evals run Claude through the [Claude Agent SDK](https://www.npmjs.com/package/@anthropic-ai/claude-agent-sdk) so `SKILL.md` is loaded the way a real Claude Code session loads it (off disk, via `.claude/skills/<slug>/`), present it with mocked LaunchDarkly MCP tools, and assert on both the tool-call trajectory and response quality.

## Setup

```bash
cd evals
npm install
cp .env.example .env  # then fill in ANTHROPIC_API_KEY (and optionally AGENT_MODEL / RUBRIC_MODEL)
```

## Unit Tests

The harness utility modules (`_mock.js`, `_jsonschema-to-zod.js`, `transform.js`, `output-valid.js`, `assertions.js`) have unit tests that run without any API calls or environment variables:

```bash
npm test
```

Run these after any changes to the provider, mock, or shared utilities to catch regressions before running full evals.

## Running Evals

```bash
# From evals/

# Run a single suite (all test cases)
npm run eval:configs-create           # agentcontrol/configs-create
npm run eval:configs-update           # agentcontrol/configs-update
npm run eval:agentcontrol-tools       # agentcontrol/tools
npm run eval:configs-variations       # agentcontrol/configs-variations
npm run eval:flag-create             # feature-flags/launchdarkly-flag-create
npm run eval:onboarding              # onboarding

# Quick smoke check — first test case only (~15-20s, ~$0.05)
npm run eval:configs-create:single
npm run eval:configs-update:single
npm run eval:agentcontrol-tools:single
npm run eval:configs-variations:single
npm run eval:flag-create:single
npm run eval:onboarding:single

# Aggregate and CI operations
npm run eval:all                     # Run every suite and rebuild ../eval-scores.json
npm run eval:aggregate               # Rebuild eval-scores.json from existing results (no API calls)
npm run eval:diff                    # Show which suites need re-running since last eval:all
npm run eval:badges                  # Rewrite eval score badges in skill READMEs
npm run eval:view                    # Open results UI at localhost:15500

# Cross-model evaluation
npm run eval:haiku                   # Run all suites against claude-haiku-4-5
npm run eval:sonnet                  # Run all suites against claude-sonnet-4-6
npm run eval:opus                    # Run all suites against claude-opus-4-6
npm run eval:matrix                  # Run all suites against haiku + sonnet + opus

# From repo root
npm run eval                         # Alias for eval:all
```

All scripts pass `--no-cache` so dev iterations always reflect the current `SKILL.md` and provider.

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | Authenticates the agent with Anthropic. Also used by the rubric grader if `RUBRIC_MODEL` is an Anthropic model (the default). |
| `AGENT_MODEL` | No | Override the system-under-test model (default: `claude-sonnet-4-6`). |
| `RUBRIC_MODEL` | Yes | Rubric grader model for `llm-rubric` assertions (set in `.env.example`). |
| `OPENAI_API_KEY` | If using OpenAI for `RUBRIC_MODEL` | Authenticates the rubric grader. |
| `SKILL_EVAL_DEBUG=1` | No | Dump every SDK message to a temp JSON file for inspection. |

## Architecture

```
evals/
  package.json                       # npm scripts + dependencies
  .env.example                       # Environment variable template
  shared/
    defaults.yaml                    # defaultTest block merged into every suite
    transform.js                     # Parses agent output once; assertions skip JSON.parse
    output-valid.js                  # Weight-0 sanity assertion for the parse step
    assertions.js                    # Trajectory helper functions (for scripts, not inline assertions)
  providers/
    claude-skill-agent-sdk.js        # The agent loop: loads skill via SDK, mocks LD tools
    _mock.js                         # Template renderer + stateful write/read overlay
    _jsonschema-to-zod.js            # JSON Schema -> Zod shape converter
  tools/
    definitions.json                 # Anthropic-format tool definitions for all LD MCP tools
  mocks/
    tool-responses.json              # Canned responses for mocked tool calls
  scripts/
    _manifest.js                     # Maps suites to skills (single source of truth)
    _models.js                       # Model aliases: haiku, sonnet, opus
    aggregate.js                     # Runs suites and writes ../eval-scores.json
    diff-changed-skills.js           # Lists suites that need re-running based on git changes
    render-badges.js                 # Rewrites eval score badges in skill READMEs
    run-models.js                    # Cross-model runner (haiku/sonnet/opus matrix)
  <skill-name>/
    promptfooconfig.yaml             # One per skill; test cases + assertions
```

### How a test case runs

1. Promptfoo loads the suite config merged with `shared/defaults.yaml`.
2. The provider creates an isolated temp directory containing only a symlink to the target skill at `.claude/skills/<slug>/` so the SDK only discovers the one skill being evaluated.
3. LaunchDarkly MCP tools are exposed through an in-process mock server. Responses come from `mocks/tool-responses.json` with `{{placeholder}}` substitution from the tool's input arguments.
4. The agent runs. Every tool call is recorded into a `trajectory`. When done, the provider returns:
   ```json
   {
     "response": "The agent's final text",
     "first_assistant_text": "The agent's first non-empty text turn",
     "kickoff_text": "All assistant prose up to and including the first user-observable tool call",
     "assistant_turns": [{ "turn": 1, "text": "..." }],
     "trajectory": [{ "tool": "setup-ai-config", "arguments": {...}, "turn": 2 }],
     "tools_called": ["list-ai-configs", "setup-ai-config"],
     "turn_count": 3,
     "terminated": null
   }
   ```
5. `shared/transform.js` parses the JSON before assertions run. Every assertion receives `output` as an object — **do not call `JSON.parse(output)` inside assertions**.

### Shared defaults (`shared/defaults.yaml`)

Every suite is run with two `-c` flags:

```bash
promptfoo eval -c shared/defaults.yaml -c <skill>/promptfooconfig.yaml
```

The shared defaults supply:
- `defaultTest.threshold: 0.75` — minimum weighted-average score per test to count as passing.
- `defaultTest.options.transform: file://./transform.js` — parses the agent's JSON output once.
- `defaultTest.assert` — sanity check (`output_valid`, weight 0) and latency assertion (180s cap).

### Trajectory ordering convention

Use **FIRST occurrence** for prerequisites and **LAST occurrence** for verifiers when checking tool ordering:

```js
const aIdx = tools.indexOf('list-ai-configs');   // first: prerequisite
const bIdx = tools.lastIndexOf('setup-ai-config'); // last: verifier
const pass = aIdx >= 0 && bIdx > aIdx;
```

This handles agents that call `get-foo` before AND after mutation; using `indexOf` for both would silently pass against the pre-mutation call.

### Cross-model evaluation (`run-models.js`)

The cross-model runner evaluates all suites against one or more model aliases without touching the canonical `eval-scores.json`. Results are written to `<suite>/results.<alias>.json` (e.g., `configs-create/results.haiku.json`).

```bash
npm run eval:haiku                   # claude-haiku-4-5-20251001
npm run eval:sonnet                  # claude-sonnet-4-6
npm run eval:opus                    # claude-opus-4-6
npm run eval:matrix                  # all three in sequence
```

After running, a summary matrix is printed to stdout. These files are gitignored — they're for local comparison only.

### Diff-gated re-runs (`diff-changed-skills.js`)

`eval:diff` compares the current `HEAD` against the `lastCommit` recorded in `eval-scores.json` and reports which suites need re-running:

```bash
npm run eval:diff                    # prints affected suites
npm run eval:diff -- --json          # machine-readable JSON array
npm run eval:diff -- --verbose       # show changed file paths
npm run eval:diff -- --base=abc1234  # compare against a specific commit
```

**Global triggers** — changes to `evals/providers`, `evals/shared`, `evals/tools`, or `evals/mocks` invalidate every suite, because those files affect all test runs.

Typical CI workflow:
```bash
npm run eval:diff -- --json          # determine which suites changed
# then run only the affected suite(s)
npm run eval:<suite>
npm run eval:aggregate               # rebuild eval-scores.json from results
```

### README badge rendering (`render-badges.js`)

`eval:badges` rewrites the eval score block in each skill's README between `<!-- eval-score:start -->` and `<!-- eval-score:end -->` markers:

```bash
npm run eval:badges
```

If a skill README doesn't have the markers, `render-badges.js` appends a new `## Eval Score` section. If no README exists, a stub is created.

Badge format example:
```
**Eval score:** 100/100 (4/4 passing, passing) — last run 2026-05-19
```

Run this after `eval:all` (or `eval:aggregate`) to keep README badges in sync.

### `shared/assertions.js`

This module exports trajectory helper functions for use in **scripts** and **Node.js files**. It cannot be `require()`'d inside inline YAML assertions (promptfoo evaluates those as isolated `new Function` contexts).

```js
const { called, calledNone, expectAfter } = require('../shared/assertions');

called(output, 'setup-ai-config')          // → boolean
calledNone(output, ['delete-ai-config'])   // → boolean
expectAfter(output, 'list-ai-configs', 'setup-ai-config')  // → boolean
```

For inline YAML assertions, implement the same logic directly — see the [Trajectory ordering convention](#trajectory-ordering-convention) section above.

## Adding Evals for a New Skill

### Step 1: Check tool coverage

Read the SKILL.md and note every MCP tool it references. Verify each tool exists in `tools/definitions.json` and has a mock response in `mocks/tool-responses.json`. Add them if missing.

### Step 2: Create the eval directory and config

```bash
mkdir <skill-name>
```

Use the same name as the skill directory (e.g., `configs-create`). Create `promptfooconfig.yaml`:

```yaml
# yaml-language-server: $schema=https://promptfoo.dev/config-schema.json
description: "End-to-end evaluation of the <skill-name> skill"

prompts:
  - file://../../skills/<domain>/<skill-name>/SKILL.md

providers:
  - id: file://../providers/claude-skill-agent-sdk.js
    label: claude-skill-agent-sdk
    config:
      skill_slug: <skill-name>

tests:
  - description: "<scenario description>"
    vars:
      user_request: >
        <what the user asks>
      codebase_context: >
        <simulated project info, or "" for exploration scenarios>
    assert:
      # ... assertions
```

### Step 3: Add npm scripts

Add two entries to `evals/package.json` scripts. The full-suite script **must** include `-o <skill>/results.json` so `aggregate.js` can read it:

```json
"eval:<skill>": "promptfoo eval -c shared/defaults.yaml -c <skill>/promptfooconfig.yaml --env-file .env --no-cache -o <skill>/results.json",
"eval:<skill>:single": "promptfoo eval -c shared/defaults.yaml -c <skill>/promptfooconfig.yaml --env-file .env --no-cache --filter-first-n 1",
```

### Step 4: Register in the manifest

Add an entry to `scripts/_manifest.js`:

```js
{
  suite: "<skill-name>",
  skillKey: "<domain>/<skill-name>",   // e.g. "agentcontrol/configs-create"
  skillDir: "skills/<domain>/<skill-name>",
  readme: "skills/<domain>/<skill-name>/README.md",
},
```

### Step 5: Write test cases (3-5 per skill)

| Scenario | Purpose |
|----------|---------|
| Happy path | Most common use case |
| Variant input | A different mode/intent that exercises a decision branch |
| Exploration | User provides minimal context; agent must investigate |
| Edge case | Specific inputs (tags, descriptions) are passed correctly |
| Safety | Agent avoids tools the skill warns against |

**Important:** mock data for `list-*` tools must NOT contain items whose key/name matches what the test asks to create. If `list-flags` returns a flag named `new-checkout` and the test asks to create a checkout flag, the agent will skip creation.

### Step 6: Write assertions

Every `type: javascript` assertion must return `{ pass: boolean, score: number, reason: string }`. Promptfoo rejects objects missing `score`.

**Tool presence:**
```yaml
- type: javascript
  value: |
    const tools = output.tools_called || [];
    const pass = tools.includes('setup-ai-config');
    return { pass, score: pass ? 1 : 0, reason: 'Tools: ' + tools.join(' -> ') };
  metric: calls_setup_ai_config
  weight: 3
```

**Tool ordering (FIRST prerequisite, LAST verifier):**
```yaml
- type: javascript
  value: |
    const tools = output.tools_called || [];
    const aIdx = tools.indexOf('list-ai-configs');
    const bIdx = tools.lastIndexOf('setup-ai-config');
    const pass = aIdx >= 0 && bIdx > aIdx;
    return { pass, score: pass ? 1 : 0, reason: 'list@' + aIdx + ' setup@' + bIdx };
  metric: explores_before_creating
  weight: 3
```

**Tool arguments:**
```yaml
- type: javascript
  value: |
    const call = (output.trajectory || []).find(t => t.tool === 'setup-ai-config');
    if (!call) return { pass: false, score: 0, reason: 'No setup-ai-config call' };
    const a = call.arguments;
    const hasKey = typeof a.key === 'string' && /^[a-z][a-z0-9-]*$/.test(a.key);
    return { pass: hasKey, score: hasKey ? 1 : 0, reason: 'key=' + (a.key || '?') };
  metric: key_is_kebab_case
  weight: 2
```

**LLM rubric (semantic quality):**
```yaml
- type: llm-rubric
  value: |
    Evaluate whether the agent followed the skill workflow correctly.
    Score 1.0 if all criteria are met, deduct proportionally for each miss.
    1. <criterion from SKILL.md>
    2. <criterion>
  metric: workflow_quality
  weight: 2
```

#### Weight guidelines

| Weight | Use for |
|--------|---------|
| 3 | Core behavior — the tool call that IS the skill |
| 2 | Important supporting behavior — verification, safety checks, workflow quality |
| 1 | Nice-to-have — metadata, formatting, optional steps |
| 0 | Sanity checks that should not affect score (e.g., `output_valid`) |

## Provider Config Options

| Option | Default | Effect |
|--------|---------|--------|
| `skill_slug` | (required) | Folder name of the skill under `skills/` |
| `allow_builtins` | `false` | When `true`, expose Claude Code's built-in tools (Read/Grep/Glob/Bash/Edit/Write). Use for skills that scan the codebase. |
| `expose_mcp_tools` | `true` | When `false`, do not expose LaunchDarkly mock MCP tools. Use for routing/advisory skills. |
| `force_skill_invocation` | `false` | When `true`, set `initialPrompt` to `/<skill_slug>` so the skill is invoked via slash command. Use for skills whose description-based activation is unreliable. |
| `expose_ask_question` | `false` | When `true`, expose an `ask-question` MCP tool for testing blocking decision points. |

## Aggregated Quality Artifact (`eval-scores.json`)

Running `npm run eval:all` writes a summary at the repo root:

```json
{
  "schemaVersion": 1,
  "updatedAt": "2026-05-19T00:00:00Z",
  "lastCommit": "fc69376",
  "skills": {
    "agentcontrol/configs-create": {
      "score": 100,
      "passed": 4,
      "total": 4,
      "status": "passing",
      "lastRun": "2026-05-19T00:00:00Z",
      "perTest": [{ "description": "...", "pass": true, "score": 1.0 }]
    }
  }
}
```

- `lastCommit` — the short git SHA at the time of the last `eval:all` run. Used by `eval:diff` to determine which suites have changed since scores were recorded.
- `skillKey` — the canonical key is `<domain>/<skill-name>` (e.g., `agentcontrol/configs-create`).

Run `node scripts/aggregate.js` (without `--run`) to rebuild this file from existing `<suite>/results.json` files without making any API calls.
