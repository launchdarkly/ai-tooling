# LaunchDarkly Config Migrate Skill

An Agent Skill for migrating an application with hardcoded LLM prompts to a full LaunchDarkly AgentControl implementation in five stages: audit, wrap, tools, metrics, evals.

## Overview

This skill orchestrates the full migration journey from hardcoded `openai.chat.completions.create(model="gpt-4o", ...)` (or equivalent in any provider SDK) to a managed config with tools, metrics, and judges. It uses the current AI SDKs (`launchdarkly-ai-server` for Python, `@launchdarkly/ai-node` for Node.js), where `config().invoke()` runs the provider call through a handler and records metrics automatically. It also covers moving off the legacy LaunchDarkly AI SDK.

The five stages:

1. **Audit** hardcoded model names, prompts, parameters, and template placeholders (read-only)
2. **Wrap** the call in `config().invoke()` with a handler package or custom handler, keeping the original call as the fallback. Delegates config creation to `configs-create` and serving to `configs-targeting`
3. **Tools** — move function-calling schemas into LaunchDarkly and pass implementations as `tool_handlers`. Delegates to `tools`
4. **Metrics** — confirm the automatic duration, token, success/error, and tool-call metrics, and add user feedback events
5. **Evals** — attach judges for LLM-as-a-judge scoring. Delegates to `online-evals`

## Installation (Local)

Copy `skills/agentcontrol/migrate/` into your agent client's skills path.

## Prerequisites

- Remotely hosted LaunchDarkly MCP server
- `LD_SDK_KEY` environment variable (server-side SDK key, starts with `sdk-`)
- A Python or Node.js application with hardcoded LLM calls (OpenAI, Anthropic, Bedrock, Gemini, LangChain, LangGraph, CrewAI, or Strands)

## Usage

```
Migrate our chat service from hardcoded OpenAI prompts to LaunchDarkly AgentControl
```

```
Our LangGraph agent has its model and instructions baked in — walk me through wrapping it in a config
```

```
We're on the old ldai SDK with create_tracker everywhere — move us to the current SDK
```

## Structure

```
migrate/
├── SKILL.md
├── README.md
└── references/
    ├── phase-1-analysis-checklist.md
    ├── before-after-examples.md
    ├── sdk-ai-tracker-patterns.md
    ├── agent-mode-frameworks.md
    ├── fallback-defaults-pattern.md
    └── agent-graph-reference.md
```

## Related

- [Configs Create](../configs-create/): Delegated to by Stage 2 (wrap)
- [Configs Targeting](../configs-targeting/): Serves the new variation after creation
- [Tools](../tools/): Delegated to by Stage 3 (tools)
- [Built-in Metrics](../built-in-metrics/): Per-provider handler details and the legacy-to-current mapping
- [Online Evals](../online-evals/): Delegated to by Stage 5 (evals)
- [Configs Variations](../configs-variations/): Next step after migration for A/B testing
- [LaunchDarkly AgentControl Docs](https://launchdarkly.com/docs/home/agentcontrol)

## License

Apache-2.0
