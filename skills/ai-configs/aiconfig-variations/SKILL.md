---
name: aiconfig-variations
description: "Experiment with AI configurations by creating and managing variations. Helps you test different models, prompts, and parameters to find what works best through systematic experimentation."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.0.0-experimental"
---

# AI Config Variations

You're using a skill that will guide you through testing and optimizing AI configurations through variations. Your job is to design experiments, create variations, and systematically find what works best.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Primary MCP tool:**
- `clone-ai-config-variation` -- clone a baseline variation with selective overrides (recommended for experimentation)

**Alternative MCP tools (for more control):**
- `get-ai-config` -- review existing variations before adding new ones
- `create-ai-config-variation` -- create new variations from scratch

**Optional MCP tools:**
- `update-ai-config-variation` -- refine a variation after creation
- `delete-ai-config-variation` -- remove variations that didn't work out

## Core Principles

1. **Test One Thing at a Time**: Change model OR prompt OR parameters, not all at once
2. **Have a Hypothesis**: Know what you're trying to improve
3. **Measure Results**: Use metrics to compare variations
4. **Verify via Tool**: The agent fetches the config to confirm variations exist

## Workflow

### Step 1: Identify What to Optimize

What's the problem? Cost, quality, speed, accuracy? How will you measure success?

### Step 2: Design the Experiment

| Goal | What to Vary |
|------|--------------|
| Reduce cost | Cheaper model (e.g., `gpt-4o-mini`) |
| Improve quality | Better model or more detailed prompt |
| Reduce latency | Faster model, lower `maxTokens` |
| Increase accuracy | Different model family (Claude vs GPT-4) |

### Step 3: Create Variations (Recommended: Clone with Overrides)

Use `clone-ai-config-variation` to duplicate the baseline and override only what you're testing. This ensures everything stays constant except your test variable: the tool reads the source variation, merges your overrides, and creates the new variation.

Provide:
- `sourceVariationKey` -- the baseline to clone from
- `key` and `name` -- identifiers for the new variation (e.g., `gpt4o-mini-cost-test`)
- Only the fields you want to change (e.g., `modelConfigKey` and `modelName` to test a cheaper model)

The response returns both the source and created variation, so you can immediately verify the diff.

### Step 3 (Alternative): Create from Scratch

If you need full control, use `get-ai-config` to review the current state, then `create-ai-config-variation` with all fields specified manually.

### Step 4: Verify

If you used `clone-ai-config-variation`, the response includes both source and created variations for immediate comparison. Otherwise, use `get-ai-config` to confirm.

**Report results:**
- Variations created with correct models and parameters
- Only the intended variable differs between variations
- Flag any issues

## modelConfigKey Format

Required for models to display in the UI. Format: `{Provider}.{model-id}`:
- `OpenAI.gpt-4o`, `OpenAI.gpt-4o-mini`
- `Anthropic.claude-sonnet-4-5`, `Anthropic.claude-3-5-sonnet`

## What NOT to Do

- Don't test too many things at once
- Don't forget modelConfigKey
- Don't make decisions on small sample sizes
- Don't remove the baseline variation while testing

## Related Skills

- `aiconfig-create` -- Create the initial config
- `aiconfig-update` -- Refine based on learnings
