---
name: tools
description: "Give your agents capabilities through tools (function calling). Helps you identify what your agent needs to do, create tool definitions, and attach them to config variations."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.1.0-experimental"
---

# Config Tools

You're using a skill that will guide you through adding capabilities to your agents through tools (function calling). Your job is to identify what your agent needs to do, create tool definitions, attach them to variations, and verify they work.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Required MCP tools:**
- `create-ai-tool` -- create a new tool definition with a schema
- `update-ai-config-variation` -- attach tools to a config variation
- `get-ai-config` -- verify tools are attached to the variation

**Optional MCP tools:**
- `list-ai-tools` -- browse existing tools in the project
- `get-ai-tool` -- inspect a specific tool's schema

## Core Principles

1. **Start with Capabilities**: Think about what your agent needs to do before creating tools
2. **Framework Matters**: LangGraph/CrewAI often auto-generate schemas; OpenAI SDK needs manual schemas
3. **Create Before Attach**: Tools must exist before you can attach them to variations
4. **Verify**: The agent fetches the config to confirm attachment
5. **Complete the Full Workflow**: Listing existing tools is a discovery step, not the end goal. After listing, always proceed to create the requested tool, attach it, and verify. Do not stop after exploration.

## Workflow

### Step 1: Identify Needed Capabilities

What should the agent be able to do?
- Query databases, call APIs, perform calculations, send notifications
- Check what exists in the codebase (API clients, functions)
- Consider framework: LangGraph/LangChain auto-generate schemas; direct SDK needs manual schemas

If the user asks to check existing tools first, or you have no codebase context about what tools exist, follow this exact order:
1. `list-ai-tools` -- explore what exists
2. `create-ai-tool` -- create the new tool (with a key different from existing ones)
3. `update-ai-config-variation` -- attach it
4. `get-ai-config` -- verify

Call `list-ai-tools` as your **first** tool call before any creation. Never stop after listing alone -- always proceed through all four steps.

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

Use `update-ai-config-variation` to attach tools. **Pass only the `tools` field.** Do not bundle `instructions`, `messages`, `model`, or `parameters` into this PATCH unless the user has explicitly asked you to also update those fields. Those fields may have been edited in the LaunchDarkly UI since the variation was created, and including them in a tool-attachment PATCH will silently clobber the UI edits.

```json
{
  "projectKey": "my-project",
  "configKey": "support-chatbot",
  "variationKey": "default",
  "tools": [
    {"key": "search-knowledge-base", "version": 1}
  ]
}
```

If you observe a UI-clear bug where attaching tools wipes other fields, **do not work around it by re-sending those fields from the previous `get-ai-config` response** — that masks the bug and can resurrect stale values that the user has since edited. Report the bug instead.

### Step 4: Verify

1. Use `get-ai-tool` to confirm the tool exists with a valid schema
2. Use `get-ai-config` to confirm the tool is attached to the variation (check `tools` in the variation's output)

**Report results:**
- Tool created with valid schema
- Tool attached to variation
- Flag any issues

## Implement the tools in your application

LaunchDarkly stores each tool's schema and attaches it to the variation. Your application supplies the function that runs when the model calls the tool. With the AI SDK (`launchdarkly-ai-server` for Python, `@launchdarkly/ai-node` for Node.js) and a provider handler package, that function is all you write. The handler converts the schemas to the provider's format, runs the tool loop, and records a `$ld:ai:tool_call` event for every call. You don't convert schemas, write a loop, or call a tracker.

Pass the functions as `tool_handlers` (Python) or `toolHandlers` (Node.js), keyed by the tool key you created in Step 2:

```python
from launchdarkly_ai_server import config
from launchdarkly_ai_openai_messages import create_openai_messages_handler

def search_knowledge_base(args):
    # args is one dict of the arguments the model sent, matching the tool's schema
    return kb.search(args["query"], limit=args.get("limit", 10))

result = await config(
    key="support-chatbot",
    handler=[create_openai_messages_handler()],
    tool_handlers={"search-knowledge-base": search_knowledge_base},
).invoke(user_input, {"kind": "user", "key": "user-123"})
```

```typescript
import { config } from '@launchdarkly/ai-node';
import { createOpenAIHandler } from '@launchdarkly/ai-openai-messages';

const result = await config({
  key: 'support-chatbot',
  handler: [createOpenAIHandler()],
  toolHandlers: {
    'search-knowledge-base': async (args) => kb.search(args.query, args.limit ?? 10),
  },
}).invoke(userInput, { kind: 'user', key: 'user-123' });
```

Rules for tool functions:

- **Keys must match exactly.** The key in `tool_handlers` must equal the tool key on the variation, including case. If the model calls a tool with no function, `invoke()` raises `No handler registered for tool "<key>"`.
- **One argument.** The function receives a single dict (Python) or object (Node.js) of arguments, not keyword arguments. It can be sync or async. The handler sends the return value back to the model as a string.
- **The loop is bounded.** The handler packages stop after 10 tool steps and raise `Tool loop exceeded the maximum number of steps (10)`. A runaway loop is almost always a prompt or schema bug.
- **Which tools the model sees.** The Node.js handlers offer the model only the variation's tools that have a function. The Python handlers offer every tool on the variation, so register a function for each one.

To share tools across call sites, put them in a `Registry` (`Registry(handlers=..., tools=...)` in Python, `new Registry({ handlers, tools })` in Node.js) and pass `registry=` instead. A call receives only the tools its variation names. Some providers have built-in tools, such as `ClaudeWebSearch` from `launchdarkly-ai-claude-agents`. Assign one as the value for a tool key instead of a function, and its calls are tracked the same way.

### Custom handlers

Only write provider-specific tool code when no handler package covers your provider. Then build a handler with `create_handler()` / `createHandler()`. The SDK calls your function with five arguments: the resolved config, the user input, the tool functions, the variables, and the conversation history. The config is a plain dict: `config["model"]` holds `name` and `parameters`, and `config["tools"]` maps each tool key to `{type, name, description, parameters}`. Convert those to the provider's shape:

| Provider | Target shape | Where it goes on the call |
|---|---|---|
| OpenAI Chat Completions | `{type: "function", function: {name, description, parameters}}` | top-level `tools=[...]` |
| OpenAI Responses API | `{type: "function", name, description, parameters}` | top-level `tools=[...]` |
| Anthropic | `{name, description, input_schema}`, renaming `parameters` to `input_schema` | top-level `tools=[...]` |
| Bedrock Converse | `{toolSpec: {name, description, inputSchema: {json: parameters}}}` | inside `toolConfig.tools=[...]` |
| Gemini (`google-genai`) | `{function_declarations: [{name, description, parameters}]}` | `GenerateContentConfig.tools=[...]` |

The tool functions the SDK passes in are already wrapped to record `$ld:ai:tool_call`, so call them directly. Return the final text and the token usage. Here's a bounded loop against Anthropic:

```python
from anthropic import AsyncAnthropic
from launchdarkly_ai_server import create_handler

anthropic_client = AsyncAnthropic()
MAX_STEPS = 5

async def call_anthropic(ld_config, user_input, tool_handlers, variables, history):
    tools = [
        {"name": t["name"], "description": t.get("description", ""), "input_schema": t["parameters"]}
        for t in (ld_config.get("tools") or {}).values()
    ]
    system = "\n".join(m["content"] for m in ld_config.get("messages") or [] if m["role"] == "system")
    messages = [{"role": "user", "content": user_input}]
    usage = {"input": 0, "output": 0}
    for _ in range(MAX_STEPS):
        response = await anthropic_client.messages.create(
            model=ld_config["model"]["name"], max_tokens=1024,
            system=system, messages=messages, tools=tools,
        )
        usage["input"] += response.usage.input_tokens
        usage["output"] += response.usage.output_tokens
        if response.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                output = await tool_handlers[block.name](block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
        messages.append({"role": "user", "content": results})
    text = "".join(b.text for b in response.content if b.type == "text")
    return {"output": text, "usage": usage}

# provides_for must be a tuple in Python. A list never matches the router.
anthropic_handler = create_handler(("Anthropic", "messages"), call_anthropic)
```

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
- Don't bundle `instructions`, `messages`, `model`, or `parameters` into the tool-attachment PATCH. Send `tools` alone unless the user explicitly asked for a multi-field update — bundled PATCHes silently clobber UI edits to the other fields.

## Related Skills

- `configs-create` -- Create config before attaching tools
- `configs-variations` -- Manage variations with different tool sets
