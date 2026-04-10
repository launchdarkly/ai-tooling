# LaunchDarkly Agent Evals

LLM evaluation suite for the [agent-skills](../agent-skills) skill library. Tests that skill instructions drive correct agent behavior: right tool selection, correct workflow ordering, gate conditions, and appropriate disambiguation.

## What This Tests

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Behavioral (llm-rubric)                           │
│  Does the agent follow skill workflow steps correctly?       │
│  Does it ask for approval before destructive operations?     │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Structural (contains / not-contains)              │
│  Does the agent mention the right tool names?                │
│  Does it NOT call create before getting approval?            │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Tool Selection (javascript assertions)            │
│  For tool-calling models: did it pick the right function?    │
└─────────────────────────────────────────────────────────────┘
```

These tests are regression guards for skill changes — not tests of model intelligence.

## Setup

```bash
npm install
```

Required environment variables:

```bash
# At least one model provider
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

## Running Evals

```bash
# All skills
npm run eval

# Individual domains
npm run eval:metrics
npm run eval:flags
npm run eval:aiconfigs

# Single skill
npx promptfoo eval --config evals/metrics/metric-create.eval.yaml

# View results in browser
npm run view
```

## Directory Structure

```
agent-evals/
├── promptfooconfig.yaml          Root config — aggregates all evals
├── fixtures/
│   ├── metrics-tools.json        Tool schemas for metrics MCP server
│   ├── feature-flags-tools.json  Tool schemas for FM MCP server
│   └── ai-configs-tools.json     Tool schemas for AI Configs MCP server
└── evals/
    ├── metrics/
    │   ├── metric-create.eval.yaml
    │   ├── metric-choose.eval.yaml
    │   └── metric-instrument.eval.yaml
    ├── feature-flags/
    │   ├── flag-create.eval.yaml
    │   ├── flag-targeting.eval.yaml
    │   ├── flag-cleanup.eval.yaml
    │   └── flag-discovery.eval.yaml
    └── ai-configs/
        ├── aiconfig-create.eval.yaml
        ├── aiconfig-update.eval.yaml
        ├── aiconfig-targeting.eval.yaml
        ├── aiconfig-variations.eval.yaml
        ├── aiconfig-tools.eval.yaml
        ├── aiconfig-online-evals.eval.yaml
        └── aiconfig-projects.eval.yaml
```

## Test Anatomy

Each eval file tests one skill. Tests cover:

- **Happy path** — user request is clear, agent should proceed correctly
- **Disambiguation** — ambiguous input, agent should ask a clarifying question
- **Gate condition** — agent must NOT call a create/mutate tool without explicit user approval
- **Tool ordering** — agent should call check/list tools before create/delete tools

## CI Integration

See `.github/workflows/evals.yml`. On PRs that touch skill files, only changed-domain evals run (cost control). Nightly runs test all skills against both GPT-4o and Claude Sonnet.

Pass rate threshold: **80%** (configurable via `PROMPTFOO_PASS_RATE_THRESHOLD`).

## Adding New Tests

1. Find the skill YAML file in `../agent-skills/skills/`
2. Create a new `.eval.yaml` in the appropriate domain directory
3. Add it to `promptfooconfig.yaml` configs list
4. Test locally: `npx promptfoo eval --config evals/your-new-skill.eval.yaml`
