# Agent-Mode Frameworks

How to wire an AI Config in **agent mode** into the frameworks that take a goal/instructions string: LangGraph, CrewAI, Strands, and custom ReAct loops. Also covers the **dynamic tool loading** pattern from the devrel-agents-tutorial — how to extract tool names from `config.tools` at runtime and instantiate the actual tool implementations without hardcoding.

## When to pick agent mode

Completion mode is the default and covers direct provider calls (OpenAI, Anthropic, Bedrock) where the app assembles a `messages` array. Pick **agent mode** when:

| Signal | Framework | Example |
|--------|-----------|---------|
| Takes a `prompt` or `instructions` string as a single argument | LangGraph `create_react_agent` | `create_react_agent(model, tools, prompt="You are...")` |
| Takes `role`, `goal`, `backstory` | CrewAI `Agent` | `Agent(role="researcher", goal="...", backstory="...")` |
| Custom ReAct loop with a system instruction separated from messages | hand-rolled | `system = "You can use search..."; while not done: ...` |
| Multi-step tool use with persistent instructions across turns | LangGraph / LangChain `AgentExecutor` | The system prompt stays stable across a long interaction |
| Provider-agnostic agent with `@tool` decorators and `invoke_async` | Strands `Agent` | `Agent(model=OpenAIModel(...), system_prompt="You are...", tools=[search])` |

Agent mode returns an `instructions` string. Completion mode returns a `messages` array. Both modes support tools, parameters, and the same tracker — the only difference is the input shape the SDK returns to you.

**Caveat:** judges cannot be attached to agent-mode variations via the LaunchDarkly UI. Agent mode evaluations must go through the programmatic judge API (`create_judge(...).evaluate(input, output)`). See `aiconfig-online-evals` for the programmatic path.

**Model construction for LangChain / LangGraph.** When the framework runs on top of LangChain (which includes LangGraph's `create_react_agent` and most custom graphs), build the chat model with `create_langchain_model(ai_config)` (Python) or `LangChainProvider.createLangChainModel(aiConfig)` (Node). These helpers forward every variation parameter (`temperature`, `max_tokens`, `top_p`, …) and handle LaunchDarkly→LangChain provider-name mapping internally. Do not hand-roll `init_chat_model(model=..., model_provider=...)` — it silently drops every variation parameter. See [langchain-tracking.md](../../aiconfig-ai-metrics/references/langchain-tracking.md) for the canonical single-model and LangGraph patterns, including the per-message token-aggregation extractor used with `track_metrics_of_async` / `trackMetricsOf`.

## Tool-scoped and app-scoped knobs go in `model.custom`

If the Stage 1 audit identified configuration that isn't a native model parameter — the kind of thing a provider SDK will reject with `unexpected keyword argument` if you forward it — these fields belong in `ModelConfig(custom={...})`, **not** `ModelConfig(parameters={...})`. Typical examples:

- `max_search_results` (tool behavior — how many hits the search tool returns)
- `chunk_size` / `chunk_overlap` (RAG preprocessing knobs)
- `retry_budget` / `retry_backoff` (app-level retry policy)
- `enable_reranking`, `use_cache`, any boolean feature toggle the agent consumes
- any value that governs **tool behavior** or **app behavior** rather than **model behavior**

`create_langchain_model` / `LangChainProvider.createLangChainModel` forwards every key in `parameters` wholesale to the provider SDK. Anthropic, OpenAI, and Gemini all raise on unknown kwargs — a `max_search_results` entry in `parameters` crashes the request with `AsyncMessages.create() got an unexpected keyword argument 'max_search_results'`. Put the same field in `custom` and the helper leaves it alone; the app reads it where it's needed.

```python
# Fallback: mirror the hardcoded knob shape using custom
FALLBACK = AIAgentConfigDefault(
    enabled=True,
    model=ModelConfig(
        name="claude-sonnet-4-5-20250929",
        parameters={"temperature": 0.3, "max_tokens": 2000},  # provider-bound
        custom={"max_search_results": 10},                    # app-scoped
    ),
    provider=ProviderConfig(name="anthropic"),
    instructions="You are a helpful assistant.",
)

# In the tool or app code that needs the knob:
def search(query: str) -> dict:
    ai_config = get_current_agent_config()
    max_results = ai_config.model.get_custom("max_search_results") or 10
    return TavilySearch(max_results=max_results).invoke({"query": query})
```

Mirror the same shape on the LaunchDarkly variation. **MCP caveat.** The `update-ai-config-variation` MCP tool does not currently expose the `custom` field — to populate `model.custom` on an existing variation, PATCH it through the REST API directly:

```bash
curl -X PATCH \
  "https://app.launchdarkly.com/api/v2/projects/$PROJECT/ai-configs/$CONFIG_KEY/variations/$VARIATION_ID" \
  -H "Authorization: $LD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"patch":[{"op":"add","path":"/model/custom","value":{"max_search_results":10}}]}'
```

### Getting knobs into tools: two patterns, different tradeoffs

Tools need read access to `model.custom` at call time. There are two idiomatic shapes; each has a different cost profile:

1. **Re-call `agent_config()` inside the tool.** Simplest to reason about: the tool fetches a fresh `AIAgentConfig` with the current targeting, reads `ai_config.model.get_custom("max_search_results")`, and proceeds. Works with any framework. The cost is that each tool invocation emits another `$ld:ai:agent:config` evaluation event, which inflates agent-config usage counts on the Monitoring tab in proportion to how often tools run. For low-frequency tool calls this is fine; for a chatty agent that calls search on every turn it's noisy.

2. **Populate `runtime.context` at `call_model` time (LangGraph).** LangGraph-idiomatic: in the `call_model` node, read `ai_config.model.get_custom(...)` once, stash the values on a request-scoped context object, and have the tool read from `runtime.context` instead of re-fetching. One config fetch per turn instead of one per tool call. The cost is that you have to rebuild the compiled graph with a refreshed `Context` on each turn (or use LangGraph's `context_schema` + per-invocation `config={"configurable": {...}}` plumbing) — non-trivial if the graph is compiled once at module load today.

Pick pattern 1 for simplicity and pattern 2 only when usage-count amplification actually matters. Document the choice in the repo README so the next migrator knows which shape they're looking at.

## Wiring `agent_config` into each framework

### LangGraph `create_react_agent`

```python
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from ldai.client import LDAIClient, AIAgentConfigDefault, ModelConfig, ProviderConfig

FALLBACK = AIAgentConfigDefault(
    enabled=True,
    model=ModelConfig(name="gpt-4o", parameters={"temperature": 0.3}),
    provider=ProviderConfig(name="openai"),
    instructions="You are a helpful assistant.",
)

def build_agent(ai_client: LDAIClient, user_id: str, tools: list):
    context = Context.builder(user_id).kind("user").build()
    config = ai_client.agent_config("support-agent", context, FALLBACK)

    if not config.enabled:
        return None, None

    params = config.model.parameters or {}
    llm = ChatOpenAI(
        model=config.model.name,
        temperature=params.get("temperature", 0.3),
    )

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=config.instructions,
    )
    return agent, config.create_tracker()
```

**Key points:**
- `prompt=config.instructions` — the instructions string replaces the hardcoded prompt
- `model=` and `temperature=` come from `config.model`
- A fresh tracker is minted via `config.create_tracker()` and returned alongside the agent so the caller can wire Stage 4 tracking around `agent.invoke(...)`. Each call to `create_tracker()` produces a new `runId`; the caller should treat the returned tracker as owning the execution.

### CrewAI `Agent`

```python
from crewai import Agent
from ldai.client import LDAIClient, AIAgentConfigDefault

def build_crew_agent(ai_client, user_id: str):
    context = Context.builder(user_id).kind("user").build()
    config = ai_client.agent_config("researcher-agent", context, FALLBACK)

    if not config.enabled:
        return None

    # CrewAI expects role/goal/backstory — split the instructions or store them
    # in the AI Config as three variables and pipe them in at runtime.
    return Agent(
        role="Research Analyst",
        goal="Produce a summary of recent AI Config adoption patterns.",
        backstory=config.instructions,
        llm=config.model.name,  # CrewAI accepts a string or a LangChain model
    )
```

**Pattern note:** CrewAI's `Agent` takes three separate fields. If you want to drive all three from LaunchDarkly, either:
- Use prompt **variables** on the AI Config (`{{role}}`, `{{goal}}`, `{{backstory}}`) and pass them as the `variables` argument to `agent_config(...)`
- Or store a structured JSON blob in `instructions` and parse it in the app

Prompt variables are cleaner and keep the AI Config human-readable in the UI.

### Strands `Agent`

Strands is a provider-agnostic, async-first agent SDK. The same `Agent` class runs against Anthropic, OpenAI, and Bedrock by swapping the `model` argument; tools are plain `@tool`-decorated Python functions passed through the constructor; and `SlidingWindowConversationManager` keeps short-term memory across `invoke_async` turns without external state. Agent-mode `instructions` maps directly to `Agent(system_prompt=...)`.

Strands does not ship a first-party LaunchDarkly provider package. To serve multiple providers from a single AI Config key, dispatch on `agent_config.provider.name` and construct the matching Strands model class.

**Provider dispatcher.** Drop `parameters.tools` before passing params into the Strands model class — LaunchDarkly surfaces attached tools via a flat `parameters.tools` shape in the variation payload, but Strands receives tools via the `Agent` constructor. Passing `tools` through a second time via model `params` is an error.

```python
from strands.models.anthropic import AnthropicModel
from strands.models.openai import OpenAIModel


def create_strands_model(agent_config):
    """Map an LDAIAgentConfig to the matching Strands model class by provider."""
    provider = (agent_config.provider.name if agent_config.provider else "").lower()
    model_id = agent_config.model.name
    params = dict(agent_config.model.to_dict().get("parameters") or {})
    # LD surfaces attached tools via parameters.tools; Strands takes tools via
    # Agent(tools=[...]). Drop the key before passing params to the model class.
    params.pop("tools", None)

    if provider == "anthropic":
        # AnthropicModel requires max_tokens as a kwarg, not inside params.
        max_tokens = int(
            params.pop("max_tokens", None) or params.pop("maxTokens", None) or 1024
        )
        return AnthropicModel(model_id=model_id, max_tokens=max_tokens, params=params or None)
    if provider == "openai":
        # Pass parameters through as-is — gpt-5 wants max_completion_tokens,
        # gpt-4o wants max_tokens. Keep that choice in the LD variation.
        return OpenAIModel(model_id=model_id, params=params)
    raise ValueError(f"Unsupported provider for Strands: {provider!r}")
```

**Call site.** Build the agent once per request, pull the tracker off the config, and wrap `invoke_async` with `track_duration_of` — Strands is Tier 3 (custom extractor) because there is no provider package.

```python
from strands import Agent, tool
from strands.agent.conversation_manager.sliding_window_conversation_manager import (
    SlidingWindowConversationManager,
)
from ldai.client import AIAgentConfigDefault, ModelConfig, ProviderConfig
from ldai.tracker import TokenUsage
from ldclient import Context


@tool
def get_order_status(order_id: str) -> str:
    """Look up the status of a customer order by order ID."""
    ...


FALLBACK = AIAgentConfigDefault(
    enabled=True,
    model=ModelConfig(name="gpt-5", parameters={"max_completion_tokens": 2000}),
    provider=ProviderConfig(name="openai"),
    instructions="You are a helpful assistant.",
)


def track_strands_metrics(tracker, result):
    """Record token usage from a Strands AgentResult on the LD tracker.

    accumulated_usage aggregates tokens across every provider call in the turn,
    including tool-calling round trips — unlike the single-response shape from
    Anthropic or OpenAI direct.
    """
    usage = getattr(result.metrics, "accumulated_usage", {}) or {}
    input_tokens = usage.get("inputTokens", 0)
    output_tokens = usage.get("outputTokens", 0)
    total = usage.get("totalTokens", 0) or (input_tokens + output_tokens)
    if total > 0:
        tracker.track_tokens(TokenUsage(input=input_tokens, output=output_tokens, total=total))


async def run_turn(ai_client, user_id: str, user_input: str):
    context = Context.builder(user_id).kind("user").build()
    agent_config = ai_client.agent_config("strands-agent", context, FALLBACK)

    if not agent_config.enabled:
        return disabled_response()

    agent = Agent(
        name="order-assistant",
        model=create_strands_model(agent_config),
        system_prompt=agent_config.instructions,
        tools=[get_order_status],
        conversation_manager=SlidingWindowConversationManager(window_size=40),
    )
    tracker = agent_config.create_tracker()

    try:
        result = await tracker.track_duration_of(lambda: agent.invoke_async(user_input))
        tracker.track_success()
        track_strands_metrics(tracker, result)
        return result.message["content"][0]["text"]
    except Exception:
        tracker.track_error()
        raise
```

**Key points:**
- `system_prompt=agent_config.instructions` — the instructions string replaces the hardcoded system prompt.
- `create_strands_model(agent_config)` is the provider-dispatch seam. Add a branch per provider the variation can serve.
- The tracker is Tier 3: `tracker.track_duration_of(...)` + an explicit `track_tokens` call fed by `track_strands_metrics`. See [strands-tracking.md](../../aiconfig-ai-metrics/references/strands-tracking.md) for the single-call `track_metrics_of_async` variant and the per-field breakdown of `accumulated_usage`.
- Always `ldclient.get().flush()` before process exit in short-lived scripts — trailing events can otherwise be lost.

**TypeScript caveat.** The Strands TypeScript SDK ships `BedrockModel` and `OpenAIModel` only — it cannot run Anthropic-backed variations. If the app needs to serve both OpenAI and Anthropic from a single AI Config, use the Python SDK.

### Custom `StateGraph` (bind_tools + ToolNode)

The most common LangGraph pattern in the wild is not `create_react_agent` — it's a custom `StateGraph` with a `call_model` node that does `model.bind_tools(TOOLS)`, a separate `"tools"` node that runs `ToolNode(TOOLS)`, and a conditional edge between them. This is the shape of the `langchain-ai/react-agent` template.

Two things make it different from `create_react_agent`:

1. **Tools appear in two places** — `bind_tools(TOOLS)` (so the LLM knows which tools exist) and `ToolNode(TOOLS)` (so the executor knows how to run them). Both must read from the same source.
2. **The system prompt is injected manually** in the `call_model` node body (usually as the first message in the `ainvoke([{"role": "system", ...}, *state.messages])` call), not passed as a constructor argument.

Before — the typical template shape (`src/react_agent/graph.py`, `src/react_agent/tools.py`, `src/react_agent/context.py`):

```python
# tools.py
TOOLS: List[Callable[..., Any]] = [search]

# context.py
@dataclass(kw_only=True)
class Context:
    system_prompt: str = field(default=prompts.SYSTEM_PROMPT)
    model: str = field(default="anthropic/claude-sonnet-4-5-20250929")

# graph.py
from .tools import TOOLS

async def call_model(state: State, runtime: Runtime[Context]):
    model = load_chat_model(runtime.context.model).bind_tools(TOOLS)
    system_message = runtime.context.system_prompt.format(system_time=now_iso())
    response = await model.ainvoke(
        [{"role": "system", "content": system_message}, *state.messages]
    )
    return {"messages": [response]}

builder = StateGraph(State, context_schema=Context)
builder.add_node(call_model)
builder.add_node("tools", ToolNode(TOOLS))
builder.add_edge("__start__", "call_model")
builder.add_conditional_edges("call_model", route_model_output)
builder.add_edge("tools", "call_model")
graph = builder.compile()
```

After — `call_model` reads from an AI Config fetched per invocation. `TOOLS` becomes a function that takes the config:

```python
# tools.py — unchanged module-level implementations, plus a factory
TOOL_IMPLEMENTATIONS: Dict[str, Callable[..., Any]] = {"search": search}

def build_tools_from_config(ai_config) -> List[Callable[..., Any]]:
    """Instantiate tool callables for every tool name on the AI Config."""
    names = [t.name if hasattr(t, "name") else t.get("name") for t in (ai_config.tools or [])]
    return [TOOL_IMPLEMENTATIONS[name] for name in names if name in TOOL_IMPLEMENTATIONS]


# context.py — kept as the fallback shape, not the primary source
@dataclass(kw_only=True)
class Context:
    system_prompt: str = field(default=prompts.SYSTEM_PROMPT)
    model: str = field(default="anthropic/claude-sonnet-4-5-20250929")
    user_key: str = field(default="anonymous")  # for LD targeting context


# graph.py
from ldai.client import LDAIClient, AIAgentConfigDefault, ModelConfig, ProviderConfig
from ldclient import Context as LDContext
from .tools import build_tools_from_config, TOOL_IMPLEMENTATIONS

def _build_fallback(ctx: Context) -> AIAgentConfigDefault:
    """Reuse the existing Context defaults as the fallback."""
    provider, _, model_name = ctx.model.partition("/")
    return AIAgentConfigDefault(
        enabled=True,
        model=ModelConfig(name=model_name or ctx.model, parameters={}),
        provider=ProviderConfig(name=provider or "anthropic"),
        instructions=ctx.system_prompt.format(system_time=now_iso()),
    )


async def call_model(state: State, runtime: Runtime[Context]):
    ld_context = LDContext.builder(runtime.context.user_key).kind("user").build()
    ai_config = ai_client.agent_config(
        "react-agent",
        ld_context,
        _build_fallback(runtime.context),
    )

    if not ai_config.enabled:
        return {"messages": [AIMessage(content="")]}

    tools = build_tools_from_config(ai_config)
    model = load_chat_model(ai_config.model.name).bind_tools(tools)
    instructions = ai_config.instructions
    tracker = ai_config.create_tracker()

    import time
    start = time.time()
    try:
        response = cast(
            AIMessage,
            await model.ainvoke(
                [{"role": "system", "content": instructions}, *state.messages]
            ),
        )
        tracker.track_duration(int((time.time() - start) * 1000))
        tracker.track_success()
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            from ldai.tracker import TokenUsage
            tracker.track_tokens(TokenUsage(
                input=response.usage_metadata.get("input_tokens", 0),
                output=response.usage_metadata.get("output_tokens", 0),
                total=response.usage_metadata.get("total_tokens", 0),
            ))
    except Exception:
        tracker.track_error()
        raise

    # Stash tools on state so the "tools" node picks up the same list
    return {"messages": [response], "_active_tools": tools}


def build_tools_node_factory():
    """Return a ToolNode factory that reads tools from state."""
    def dynamic_tools_node(state: State):
        tools = getattr(state, "_active_tools", None) or list(TOOL_IMPLEMENTATIONS.values())
        return ToolNode(tools).invoke(state)
    return dynamic_tools_node


builder = StateGraph(State, context_schema=Context)
builder.add_node(call_model)
builder.add_node("tools", build_tools_node_factory())
builder.add_edge("__start__", "call_model")
builder.add_conditional_edges("call_model", route_model_output)
builder.add_edge("tools", "call_model")
graph = builder.compile()
```

**What changed:**

- `TOOLS` (a static list) → `TOOL_IMPLEMENTATIONS` (a name-to-callable dict) + `build_tools_from_config(ai_config)` (a per-request builder). This is the dynamic tool factory pattern from the devrel-agents-tutorial, adapted to plain callables.
- `call_model` fetches an `AIAgentConfig` per invocation, builds tools from `ai_config.tools`, binds them, and injects `ai_config.instructions` as the system message (replacing `runtime.context.system_prompt`).
- The `"tools"` node is replaced with a factory that reads the active tool list from state — so both `bind_tools` and `ToolNode` always run against the same list. If you skip this step and leave `ToolNode(TOOLS)` hardcoded, the LLM and the executor will disagree on what's available and the graph will misbehave.
- Tracker calls wrap the provider call inside `call_model`. The snippet above uses explicit `track_duration` + `track_tokens` + `track_success` because the sample model is hand-constructed via `load_chat_model(name).bind_tools(...)` without passing variation parameters. If you switch to `create_langchain_model(ai_config).bind_tools(tools)`, variation parameters flow through and you can collapse the block to `track_metrics_of_async(lambda: model.ainvoke(...), get_ai_metrics_from_response)`. Same story on Node: `LangChainProvider.createLangChainModel(aiConfig)` + `tracker.trackMetricsOf(LangChainProvider.getAIMetricsFromResponse, ...)`.
- The existing `Context` dataclass is kept as the fallback shape — its defaults become the `AIAgentConfigDefault` values, so the app still runs exactly as before when LaunchDarkly is unreachable.

**Gotcha:** the `"tools"` node above reads `_active_tools` from state. That means your `State` TypedDict has to include it. If it doesn't, either add the field, or take the simpler route of fetching the AI Config **once at graph-compile time** (at module load) and accepting that tool changes require a restart. The per-invocation pattern above is strictly better but adds one state field.

### Custom ReAct loop

```python
def build_react_loop(ai_client, user_id: str):
    context = Context.builder(user_id).kind("user").build()
    config = ai_client.agent_config("custom-react", context, FALLBACK)

    if not config.enabled:
        return

    system_prompt = config.instructions
    model_name = config.model.name
    tracker = config.create_tracker()

    for turn in range(MAX_TURNS):
        start = time.time()
        response = my_provider.complete(
            model=model_name,
            system=system_prompt,
            messages=history,
            tools=config.tools,  # see dynamic-tool loading below
        )
        tracker.track_duration(int((time.time() - start) * 1000))
        tracker.track_tokens(extract_tokens(response))
        # ... handle tool calls, append to history, check done ...

    tracker.track_success()
```

The call site stays in your control; the AI Config just delivers `instructions`, `model.name`, `model.parameters`, and `tools`. Everything else (the loop, the history, the tool dispatch) is unchanged.

## Dynamic tool loading — the "tools factory" pattern

The devrel-agents-tutorial uses a **dynamic tool factory** that reads tool names from `config.tools` and instantiates the actual tool implementations at runtime. This decouples the AI Config (which holds tool metadata) from the application (which holds the executable code).

### The pattern

```python
# tools_impl/dynamic_tool_factory.py — adapted from devrel-agents-tutorial

def extract_tool_names(config) -> list[str]:
    """Read the list of tool names from the AI Config."""
    if not hasattr(config, "tools") or not config.tools:
        return []
    return [tool.name if hasattr(tool, "name") else tool.get("name") for tool in config.tools]


def create_dynamic_tools_from_launchdarkly(config) -> list:
    """Instantiate tool implementations for every tool name on the config."""
    tool_names = extract_tool_names(config)
    instances = []
    for name in tool_names:
        tool = _create_tool_instance(name)
        if tool is not None:
            instances.append(tool)
    return instances


def _create_tool_instance(tool_name: str):
    """Map a tool name to an actual implementation. Add one branch per tool."""
    if tool_name == "search_kb":
        from my_tools.search import SearchKBTool
        return SearchKBTool()
    elif tool_name == "calculator":
        from my_tools.calc import CalculatorTool
        return CalculatorTool()
    # ... etc
    return None
```

Then at the call site:

```python
config = ai_client.agent_config("support-agent", context, FALLBACK)
tools = create_dynamic_tools_from_launchdarkly(config)

agent = create_react_agent(
    model=build_llm(config),
    tools=tools,
    prompt=config.instructions,
)
```

**What this gives you:**

- Toggle a tool on/off by editing the AI Config in LaunchDarkly — no redeploy needed to remove a tool from production
- Roll out a new tool to 5% of users by editing targeting rules (combined with `aiconfig-targeting`)
- Keep the actual tool implementation code in the repo; only metadata lives in LaunchDarkly

### Extracting schemas from existing hardcoded tools

If your tools are defined with LangChain `@tool` or Pydantic `BaseModel` schemas, extract the JSON schema programmatically to pass to `aiconfig-tools` during Stage 3:

```python
from my_tools import search_kb  # a @tool-decorated function

schema = search_kb.args_schema.model_json_schema()
# schema is a dict ready to pass as the tool's parameters field
```

Do not hand-write the schema — LangChain already generated it from the function signature, and Pydantic will keep it in sync. The `aiconfig-tools` delegate accepts raw JSON Schema for the parameters field.

### Dynamic schemas from LaunchDarkly

The devrel tutorial also shows the reverse: reading a JSON schema **from** the AI Config and constructing a Pydantic model at runtime:

```python
from pydantic import BaseModel, Field, create_model

def _create_dynamic_tool_input(tool_config: dict) -> type[BaseModel]:
    """Build a Pydantic input schema from an AI Config tool's parameters."""
    properties = tool_config.get("properties", {})
    fields = {}
    for name, cfg in properties.items():
        py_type = {"string": str, "number": float, "integer": int, "boolean": bool}.get(
            cfg.get("type"), str
        )
        default = ... if name in tool_config.get("required", []) else None
        fields[name] = (py_type, Field(default=default, description=cfg.get("description", "")))
    return create_model("DynamicToolInput", **fields)
```

This lets LaunchDarkly change a tool's parameter schema without redeploying the app. Use it when the tool implementation is generic enough to accept any parameter shape (e.g. a proxy that forwards requests to an external API). For most tools, a static Pydantic schema in the repo is simpler.

## Routing / multi-node hint

If the framework needs to pick between multiple downstream agents (e.g. a supervisor that routes to a security agent or a support agent based on the user input), do **not** roll your own routing. Use LaunchDarkly agent graphs — the graph's edges carry the routing contract, and the supervisor's `instructions` can be auto-injected with the valid routes.

The devrel tutorial's `generic_agent.py` shows a minimal version of this:

```python
# If this node has outgoing edges with routes, inject them into instructions
if self.valid_routes:
    route_instruction = (
        f"\n\nYou must select one of these routes: {self.valid_routes}. "
        f'Return your choice in JSON format: {{"route": "<selected_route>"}}'
    )
    instructions = instructions + route_instruction
```

For the full graph pattern, read [agent-graph-reference.md](agent-graph-reference.md) — but again, single-agent migration comes first, and agent graphs are currently **Python-only** in the SDK.

## Keep the provider call in the repo

One rule that applies across all three frameworks: the **provider SDK call** (OpenAI, Anthropic, Bedrock) stays in your code. The AI Config only changes the inputs to that call — model name, instructions, parameters, tool list. It does not replace the provider SDK. That means:

- You keep full control of error handling, retries, timeouts, custom headers
- You keep full control of streaming logic and backpressure
- You keep full control of authentication (API keys, IAM roles, Bedrock Converse sessions)
- The AI Config is additive — removing it gets you back to the original hardcoded app, provided the fallback mirrors the old values
