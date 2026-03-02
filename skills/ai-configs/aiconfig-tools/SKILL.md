---
name: aiconfig-tools
description: "Give your AI agents capabilities through tools (function calling). Helps you identify what your AI needs to do, create tool definitions, and attach them to AI Config variations."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.0.0-experimental"
---

# AI Config Tools

You're using a skill that will guide you through adding capabilities to your AI agents through tools (function calling). Your job is to identify what your AI needs to do, create tool definitions, attach them to variations, and verify they work.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Required MCP tools:**
- `create-ai-tool` -- create a new tool definition with a schema
- `update-ai-config-variation` -- attach tools to an AI Config variation
- `get-ai-config` -- verify tools are attached to the variation

**Optional MCP tools:**
- `list-ai-tools` -- browse existing tools in the project
- `get-ai-tool` -- inspect a specific tool's schema

## Core Principles

1. **Start with Capabilities**: Think about what your AI needs to do before creating tools
2. **Framework Matters**: LangGraph/CrewAI often auto-generate schemas; OpenAI SDK needs manual schemas
3. **Create Before Attach**: Tools must exist before you can attach them to variations
4. **Verify**: The agent fetches the config to confirm attachment

## Workflow

### Step 1: Identify Needed Capabilities

What should the AI be able to do?
- Query databases, call APIs, perform calculations, send notifications
- Check what exists in the codebase (API clients, functions)
- Consider framework: LangGraph/LangChain auto-generate schemas; direct SDK needs manual schemas

### Step 2: Create Tools

Use `create-ai-tool` with:
- `key` -- unique identifier for the tool
- `description` -- clear description (the LLM uses this to decide when to call the tool)
- `schema` -- raw JSON Schema (do NOT use the OpenAI function calling wrapper):

```json
{
  "type": "object",
  "properties": {
    "query": {"type": "string", "description": "Search query"},
    "limit": {"type": "integer", "default": 10}
  },
  "required": ["query"]
}
```

### Step 3: Attach to Variation

Use `update-ai-config-variation` to attach tools. Pass the tool references in the `parameters` object:

```json
{
  "parameters": {
    "tools": [
      {"key": "search-database", "version": 1}
    ]
  }
}
```

### Step 4: Verify

1. Use `get-ai-tool` to confirm the tool exists with a valid schema
2. Use `get-ai-config` to confirm the tool is attached to the variation (check `tools` in the variation's output)

**Report results:**
- Tool created with valid schema
- Tool attached to variation
- Flag any issues

## Orchestrator Note

LangGraph, CrewAI, and AutoGen often generate schemas from function definitions. You still need to create tools in LaunchDarkly and attach keys to variations so the SDK knows what's available.

## Edge Cases

| Situation | Action |
|-----------|--------|
| Tool already exists (409) | Use existing or create with different key |
| Schema invalid | Use raw JSON Schema format (type: object, properties, required) |
| Wrong endpoint assumed | The tools use `/ai-tools`, not `/ai-configs/tools` |

## What NOT to Do

- Don't try to attach tools during config creation -- update the variation afterward
- Don't skip clear tool descriptions (LLM needs them to decide when to call)
- Don't forget to verify attachment after updating the variation

## Related Skills

- `aiconfig-create` -- Create config before attaching tools
- `aiconfig-variations` -- Manage variations with different tool sets
