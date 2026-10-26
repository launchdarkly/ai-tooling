# Agent-Mode Frameworks

How to run an **agent-mode** config through the frameworks that take an instructions string: LangGraph, CrewAI, Strands, and custom ReAct loops. In every case the whole agent turn runs inside one `config().invoke()` call, either through a handler package or a custom agent handler that wraps the framework.

## When to pick agent mode

Completion mode is the default and covers direct provider calls where the app assembles a `messages` array. Pick **agent mode** when:

| Signal | Framework | Example |
|--------|-----------|---------|
| Takes a `system_prompt` / `prompt` / `instructions` string | LangGraph prebuilt agent | Python: `create_agent(llm, tools, system_prompt="You are...")`; Node.js: `createReactAgent({ llm, tools, prompt: "You are..." })` |
| Takes `role`, `goal`, `backstory` | CrewAI `Agent` | `Agent(role="researcher", goal="...", backstory="...")` |
| Custom ReAct loop with a system instruction separate from messages | Hand-rolled | `system = "You can use search..."; while not done: ...` |
| Provider-agnostic agent with `@tool` functions and `invoke_async` | Strands `Agent` | `Agent(model=OpenAIModel(...), system_prompt="You are...", tools=[search])` |

Agent-mode configs carry `instructions`; completion-mode configs carry `messages`. Both support tools and parameters, both are recorded the same way, and judges can be attached to either.

## Invariants for any framework

The examples below use specific frameworks. These three rules apply to any of them, including DSPy, AutoGen, Pydantic AI, Haystack, and LlamaIndex agents:

1. **One `invoke()` per user turn.** Each call evaluates the config once and records one run with its own `runId`. Calling `invoke()` per loop step fragments the run and lets a mid-turn targeting change swap the variation between steps.
2. **The whole turn runs inside the handler.** A custom agent handler receives the served config and runs the framework's loop to completion. Return the final text and the token usage **summed across every model call in the turn**.
3. **Tools go through `tool_handlers`.** Pass your tool implementations to `config(tool_handlers=...)`. The handler receives them wrapped so each call records `$ld:ai:tool_call`. Tools the framework calls directly, bypassing the wrapped functions, aren't recorded.

What "one user turn" means differs by app shape:

| App shape | One turn = |
|-----------|------------|
| Request/response HTTP handler | One request |
| Chat loop (one session across many user inputs) | One user input, not the whole session; pass earlier turns as `history` |
| LangGraph `app.ainvoke(...)` / `createReactAgent().invoke(...)` | One call to `ainvoke` / `invoke` |
| Custom ReAct loop | The full loop run, not one iteration |
| Batch job / dataset walk | One row |
| Streaming response (SSE / WebSocket) | The full stream, through `stream()` |

### Context keys and MAU

A shared literal key like `"anonymous"` collapses every request into one targeting segment, which breaks experiments. A per-turn `uuid4()` fixes that but registers a new context per request, and LaunchDarkly bills by distinct context keys per month. Pick one:

1. **Known user identity (preferred).** Use the session or auth ID as the context key.
2. **Session-scoped key.** Use the LangGraph `thread_id` or chat-session ID. MAU scales with sessions, not turns.
3. **Per-turn `uuid4()`.** Only for demos, or when you accept the MAU cost. Document the decision in the repo.

## Custom agent handlers

A custom handler is a function the SDK calls with the served config. Register it for each provider your variations serve, in `agent` mode:

```python
from launchdarkly_ai_server import config, create_handler, parse_template

async def run_agent(ld_config, user_input, tool_handlers, variables, history):
    instructions = parse_template(ld_config.get("instructions", ""), variables)
    params = {k: v for k, v in ld_config["model"].get("parameters", {}).items() if k != "tools"}
    knobs = ld_config["model"].get("custom") or {}
    # ... run the framework's turn ...
    return {"output": final_text, "usage": {"input": input_tokens, "output": output_tokens}}

handlers = [create_handler((provider, "agent"), run_agent) for provider in ("OpenAI", "Anthropic")]
result = await config(key="support-agent", handler=handlers, tool_handlers=TOOLS).invoke(user_input, context)
```

```typescript
import { config, createHandler, parseTemplate } from '@launchdarkly/ai-node';

const runAgent = async (ldConfig, userInput, toolHandlers, variables, history) => {
  const instructions = parseTemplate(ldConfig.instructions ?? '', variables);
  // ... run the framework's turn ...
  return { output: finalText, usage: { input: inputTokens, output: outputTokens } };
};

const handlers = ['OpenAI', 'Anthropic'].map((p) => createHandler([p, 'agent'], runAgent));
const result = await config({ key: 'support-agent', handler: handlers, toolHandlers: TOOLS }).invoke(userInput, context);
```

Rules for every custom handler:

- **Render templates yourself.** Handler packages call `parse_template` / `parseTemplate`; custom handlers must, or `{{name}}` reaches the model as literal text.
- **Strip `tools` from `model.parameters`.** Attached tool definitions are stored there in LaunchDarkly's format and will be rejected by the provider SDK. The definitions are also available as `ld_config["tools"]`, a map from tool name to `{description, parameters}`.
- **Don't catch provider exceptions.** If the handler raises, the SDK records the duration and an error, then re-raises it to the caller.
- **Don't raise `RuntimeError` from a handler.** The fallback around `invoke()` catches `RuntimeError` as "LaunchDarkly can't serve this config", so a handler failure of that type would be silently served by the hardcoded path. Raise a specific exception type instead.
- **Provider names are case-sensitive:** `OpenAI`, `Anthropic`, `Bedrock`, `Gemini`.

## Tool-scoped and app-scoped knobs go in `model.custom`

If the Stage 1 audit found configuration that isn't a model parameter, such as `max_search_results`, `chunk_size`, `retry_budget`, or a feature toggle, put it in the variation's `model.custom`, **not** `model.parameters`. Handler packages forward parameters to the provider SDK, which rejects unknown keys (`AsyncMessages.create() got an unexpected keyword argument 'max_search_results'`).

A custom agent handler reads knobs from `ld_config["model"]["custom"]` once per turn and passes them to the tools that need them. Wrap the recorded tool from `tool_handlers` rather than replacing it, so tool-call metrics still flow:

```python
async def search(args: dict) -> str:
    return str(await TavilySearch(max_results=args.get("max_results", 10)).ainvoke({"query": args["query"]}))

async def run_agent(ld_config, user_input, tool_handlers, variables, history):
    knobs = ld_config["model"].get("custom") or {}
    max_results = knobs.get("max_search_results", 10)
    tracked_search = tool_handlers["search"]
    tools = {**tool_handlers, "search": lambda args: tracked_search({**args, "max_results": max_results})}
    ...

agent = config(key="support-agent", handler=handlers, tool_handlers={"search": search})
```

Code outside a handler can read knobs with `(await inspect_config(key, context))["config"]["model"]["custom"]`, at the cost of a second evaluation per turn. Keep the current values as code defaults so the fallback behaves the same.

Set the knobs with the `update-agentcontrol-config-variation` MCP tool. `custom` replaces the whole object, so send every knob, not only the one you're changing:

```json
{
  "projectKey": "{projectKey}",
  "configKey": "{configKey}",
  "variationKey": "{variationKey}",
  "custom": {"max_search_results": 10}
}
```

## Framework by framework

### LangGraph prebuilt agent

Use the `langchain-agents` handler package. It builds the same ReAct agent from the served config: the model from `model.name` and `model.parameters`, the system prompt from `instructions`, and the tools from the config's tool definitions plus `tool_handlers`. See Example 3 in [before-after-examples.md](before-after-examples.md) for the full Python before/after.

```python
from launchdarkly_ai_server import config
from launchdarkly_ai_langchain_agents import create_langchain_agents_handler

agent = config(
    key="support-agent",
    handler=create_langchain_agents_handler(),
    tool_handlers={"search-kb": lambda args: search_kb.invoke(args)},
)
result = await agent.invoke(user_input, context, history=previous_turns)
```

```typescript
import { config } from '@launchdarkly/ai-node';
import { createLangChainAgentsHandler } from '@launchdarkly/ai-langchain-agents';

const agent = config({
  key: 'support-agent',
  handler: createLangChainAgentsHandler(),
  toolHandlers: { 'search-kb': (args) => searchKb.invoke(args) },
});
const result = await agent.invoke(userInput, context);
```

- The handler registers for any provider. It maps `Anthropic` to `ChatAnthropic`, `Bedrock` to `ChatBedrockConverse`, and everything else to `ChatOpenAI`. For Gemini or a specially configured client, pass a model or a factory: `create_langchain_agents_handler(lambda cfg: ChatGoogleGenerativeAI(model=cfg["model"]["name"]))`.
- Delete hand-rolled `init_chat_model(...)` / `load_chat_model(...)` wrappers; they drop variation parameters, and the handler replaces them.
- The handler runs the agent per call, so chat memory comes from the `history` argument rather than a `MemorySaver` checkpointer. If the app depends on a checkpointer, use a custom `StateGraph` handler instead.

### Custom `StateGraph`

If the app compiles its own graph (`bind_tools` + `ToolNode`, custom nodes), keep it and wrap one `ainvoke` in a custom agent handler. Build the graph's tools from the wrapped `tool_handlers` so tool calls are recorded, and sum `usage_metadata` across the turn's messages:

```python
import inspect

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool as lc_tool
from launchdarkly_ai_server import config, create_handler, parse_template

def build_tools(ld_config, tool_handlers):
    tools = []
    for name, spec in (ld_config.get("tools") or {}).items():
        fn = tool_handlers[name]
        async def call(_fn=fn, **kwargs):
            result = _fn(kwargs)
            return str(await result if inspect.isawaitable(result) else result)
        tools.append(lc_tool(name, call, description=spec.get("description", ""), args_schema=spec.get("parameters") or {}))
    return tools

async def run_graph(ld_config, user_input, tool_handlers, variables, history):
    llm = build_chat_model(ld_config)  # your existing model setup, fed ld_config["model"]
    app = build_graph(llm, build_tools(ld_config, tool_handlers))  # your existing StateGraph, compiled
    system = parse_template(ld_config.get("instructions", ""), variables)
    state = await app.ainvoke({"messages": [SystemMessage(system), *history_to_messages(history), HumanMessage(user_input)]})

    ai_msgs = [m for m in state["messages"] if isinstance(m, AIMessage) and m.usage_metadata]
    return {
        "output": str(state["messages"][-1].content),
        "usage": {
            "input": sum(m.usage_metadata["input_tokens"] for m in ai_msgs),
            "output": sum(m.usage_metadata["output_tokens"] for m in ai_msgs),
        },
    }

handlers = [create_handler((p, "agent"), run_graph) for p in ("OpenAI", "Anthropic")]
result = await config(key="research-agent", handler=handlers, tool_handlers=TOOLS).invoke(user_input, context)
```

This replaces the legacy `setup_run` / `finalize` node pattern: no tracker in graph state, no per-node tracking calls, and nothing run-scoped to exclude from a checkpointer. Build `build_chat_model` with every `model.parameters` key except `tools`, or use `create_langchain_agents_handler` if the graph is just a ReAct loop.

In Node.js the same shape applies with `createHandler([provider, 'agent'], fn)` and `usage_metadata` on each `AIMessage`. Prefer `createReactAgent` through the handler package unless the app needs graph-level control.

### CrewAI

CrewAI has no handler package; wrap `kickoff` in a custom agent handler. `Agent` takes three fields, so keep `backstory` in the config's `instructions` and put `role` and `goal` in `model.custom` (or render them into `instructions` with `{{role}}` / `{{goal}}` variables):

```python
from crewai import Agent, Crew, Task
from launchdarkly_ai_server import config, create_handler, parse_template

async def run_crew(ld_config, user_input, tool_handlers, variables, history):
    custom = ld_config["model"].get("custom") or {}
    agent = Agent(
        role=custom.get("role", "Research Analyst"),
        goal=custom.get("goal", "Answer the user's question accurately."),
        backstory=parse_template(ld_config.get("instructions", ""), variables),
        llm=f'{ld_config["provider"]["name"].lower()}/{ld_config["model"]["name"]}',
    )
    task = Task(description=user_input, expected_output="A concise answer.", agent=agent)
    out = await Crew(agents=[agent], tasks=[task]).kickoff_async()
    return {
        "output": out.raw,
        "usage": {"input": out.token_usage.prompt_tokens, "output": out.token_usage.completion_tokens},
    }

handlers = [create_handler((p, "agent"), run_crew) for p in ("OpenAI", "Anthropic")]
```

CrewAI's `llm` string uses LiteLLM provider prefixes (`openai/`, `anthropic/`); map provider names explicitly if your variations serve others. CrewAI calls its own tools, so tool calls aren't recorded unless you build CrewAI tools that call the wrapped `tool_handlers`.

### Strands

Strands has no handler package; wrap `invoke_async` in a custom agent handler and dispatch on `ld_config["provider"]["name"]` to build the matching model class. `result.metrics.accumulated_usage` already sums tokens across the turn (keys are camelCase: `inputTokens`, `outputTokens`). The `built-in-metrics` skill's Strands reference has the full handler.

The Strands TypeScript SDK ships `BedrockModel` and `OpenAIModel` only, so Anthropic-backed variations need the Python SDK.

### Custom ReAct loop

If the loop calls OpenAI or Anthropic and only exists to dispatch tools, **delete it** and use the `openai-messages` or `claude-messages` handler package. It runs the tool loop itself (up to 10 model calls per `invoke()`), calls your `tool_handlers`, and records the whole turn.

If the loop does more (custom stopping rules, a provider without a handler package), move it into a custom handler unchanged. Call the wrapped `tool_handlers[name](args)` for each tool call, accumulate usage across iterations, and return the sum:

```python
class AgentStepLimitError(Exception):
    pass

async def run_loop(ld_config, user_input, tool_handlers, variables, history):
    system = parse_template(ld_config.get("instructions", ""), variables)
    tool_specs = ld_config.get("tools") or {}
    messages = [*history, {"role": "user", "content": user_input}]
    usage = {"input": 0, "output": 0}
    for _ in range(MAX_STEPS):
        response = await my_provider.complete(model=ld_config["model"]["name"], system=system, messages=messages, tools=to_provider_tools(tool_specs))
        usage["input"] += response.usage.input_tokens
        usage["output"] += response.usage.output_tokens
        calls = extract_tool_calls(response)
        if not calls:
            return {"output": response.text, "usage": usage}
        for call in calls:
            result = await tool_handlers[call.name](call.args)
            messages.extend(tool_result_messages(call, result))
    raise AgentStepLimitError(f"agent exceeded {MAX_STEPS} steps")
```

## Tools

**Map existing implementations into `tool_handlers`.** Keys are the tool keys attached to the config in Stage 3; each value takes one dict of arguments. LangChain `@tool` objects fit as `lambda args: my_tool.invoke(args)`.

**Extract schemas from existing tools** when creating them in Stage 3, rather than hand-writing JSON Schema:

```python
schema = search_kb.args_schema.model_json_schema()  # @tool-decorated function or Pydantic model
```

**Toggling tools from LaunchDarkly.** Only tools attached to the served variation are offered to the model, so removing a tool from a variation removes it from production without a redeploy, and targeting can roll a new tool out to a percentage of traffic. Keep every implementation in `tool_handlers`; unattached ones are simply never called.

## Routing between agents

If the framework picks between downstream agents (a supervisor routing to a security agent or a support agent), don't hand-roll routing on top of single configs. Model it as an agent graph; see [agent-graph-reference.md](agent-graph-reference.md). Migrate the single agents first.

## Keep control of the provider call when you need it

Handler packages own the provider call. When the app needs control of retries, timeouts, custom headers, authentication (Azure endpoints, IAM roles, proxies), or streaming backpressure, use a custom handler that reuses your existing client: the provider call stays in your code, and the SDK still records the run. Keep the original pre-migration call as the fallback, so removing LaunchDarkly gets you back to the hardcoded app.
