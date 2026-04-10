---
name: aiconfig-create
description: "Create and configure AI Configs in LaunchDarkly. Helps you choose between agent vs completion mode, create the config, add variations with models and prompts, and verify the setup."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.0.0-experimental"
---

# Create AI Config

You're using a skill that will guide you through creating an AI Config in LaunchDarkly. Your job is to understand the use case, choose the right mode, create the config and its variations, and verify everything is set up correctly.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Primary MCP tool:**
- `setup-ai-config` -- create a config with its first variation in one step (recommended)

**Alternative MCP tools (for more control):**
- `create-ai-config` -- create just the config shell (key, name, mode)
- `create-ai-config-variation` -- add a variation with model, prompts, and parameters
- `get-ai-config` -- verify the config was created correctly

**Optional MCP tools (enhance workflow):**
- `list-ai-configs` -- browse existing configs to understand naming conventions
- `create-project` -- create a project if one doesn't exist yet

## Important: Bias Towards Action

When the user provides enough context (use case, model, mode), proceed through the entire workflow without stopping to ask for details you can infer. Use reasonable defaults for unspecified fields: `default` for variation key, the use case as the basis for instructions/messages, kebab-case for config keys. Complete all steps (create + verify) in one pass.

## Workflow

### Step 1: Understand the Use Case

Before creating, identify what you're building:

- **What framework?** LangGraph, LangChain, CrewAI, OpenAI SDK, Anthropic SDK, custom
- **What does the AI need?** Just text generation, or tools/function calling?
- **Agent or completion?** See the decision matrix below

### Step 2: Choose Agent vs Completion Mode

This choice is about **input schema and framework compatibility**, not execution behavior. Agent mode returns an `instructions` string; completion mode returns a `messages` array. Both provide provider abstraction, A/B testing, and metrics tracking.

| Your Need | Mode | Why |
|-----------|------|-----|
| LangGraph, CrewAI, AutoGen frameworks | **Agent** | Frameworks expect goal/instruction input |
| Persistent instructions across interactions | **Agent** | Single instructions string, SDK method: `aiclient.agent()` |
| Direct OpenAI/Anthropic API calls | **Completion** | Messages array maps directly to provider APIs |
| Full control of message structure | **Completion** | System/user/assistant role-based messages |
| One-off text generation | **Completion** | Standard chat format |
| Need online evaluations (LLM-as-judge) | **Completion** | Online evals are only available in completion mode |

**Both modes support tools.** Not all models support agent mode -- check model compatibility if using agent mode. If unsure, start with completion mode (it's the API default and more flexible).

### Step 3: Create the Config (Recommended: One Step)

Use `setup-ai-config` to create the config and its first variation in one call. This is the recommended approach: it handles creation, variation setup, and verification automatically.

**Config fields:**
- `key` -- unique identifier (lowercase, hyphens)
- `name` -- human-readable name
- `mode` -- `"agent"` or `"completion"`
- Optional: `description`, `tags`

**Variation fields:**
- `variationKey`, `variationName` -- identifiers for the first variation
- `modelConfigKey` -- must be `Provider.model-id` format (e.g., `OpenAI.gpt-4o`, `Anthropic.claude-sonnet-4-5`)
- `modelName` -- the model identifier (e.g., `gpt-4o`)

**For agent mode**, provide:
- `instructions` -- a string with the agent's system instructions

Example agent-mode call:
```json
{
  "projectKey": "my-project", "key": "support-agent", "name": "Support Agent",
  "mode": "agent", "variationKey": "default", "variationName": "Default",
  "modelConfigKey": "OpenAI.gpt-4o", "modelName": "gpt-4o",
  "instructions": "You are a customer support agent. Help users resolve their issues."
}
```

**For completion mode**, provide:
- `messages` -- an array of `{role, content}` objects (system, user, assistant)

Example completion-mode call:
```json
{
  "projectKey": "my-project", "key": "product-descriptions", "name": "Product Descriptions",
  "mode": "completion", "variationKey": "default", "variationName": "Default",
  "modelConfigKey": "Anthropic.claude-sonnet-4-5", "modelName": "claude-sonnet-4-5",
  "messages": [
    {"role": "system", "content": "You are a product copywriter. Write compelling descriptions."},
    {"role": "user", "content": "Write a description for: {{product_name}}"}
  ]
}
```

**Optional:**
- `parameters` -- model parameters like `{temperature: 0.7, maxTokens: 2000}`

The tool returns the full verified config detail with the variation attached.

### Step 3 (Alternative): Two-Step Creation

If the user asks for more control or a step-by-step approach, use the individual tools:

1. `create-ai-config` -- create the config shell
2. `create-ai-config-variation` -- add the variation with model, prompts, and parameters
3. `get-ai-config` -- verify the result

**Execute all three steps without stopping to ask for details.** Infer the variation key (`default`), name (`Default`), instructions/messages, and model from the user's request context. If the user asked for GPT-4o agent mode, you have enough to complete the entire flow. Only ask clarifying questions if the mode or model is truly ambiguous.

### Step 4: Verify

If you used `setup-ai-config`, verification is automatic: the response includes the full config with variations. Check:

1. Config exists with the correct mode
2. Variation has a model assigned (not "NO MODEL")
3. Instructions or messages are present
4. Parameters are set

**Report results:**
- Config created with correct structure
- Variation has model assigned
- Flag any missing model or parameters
- Provide config URL: `https://app.launchdarkly.com/projects/{projectKey}/ai-configs/{configKey}`

## modelConfigKey Format

Required for models to display in the UI. Format: `{Provider}.{model-id}`

- `OpenAI.gpt-4o`
- `OpenAI.gpt-4o-mini`
- `Anthropic.claude-sonnet-4-5`
- `Anthropic.claude-3-5-sonnet`

The `create-ai-config-variation` tool validates this format and rejects invalid values.

## Edge Cases

| Situation | Action |
|-----------|--------|
| Config already exists | Ask if user wants to update instead |
| Variation shows "NO MODEL" | Use `update-ai-config-variation` to set modelConfigKey |
| Need to attach tools | Create tools first (`aiconfig-tools` skill), then update the variation |

## What NOT to Do

- Don't create configs without understanding the use case
- Don't skip the two-step process (config then variation)
- Don't try to attach tools during initial creation -- update the variation afterward
- Don't forget modelConfigKey (models won't show in the UI)

## Related Skills

- `aiconfig-tools` -- Create tools before attaching
- `aiconfig-variations` -- Add more variations for experimentation
- `aiconfig-update` -- Modify configs based on learnings
