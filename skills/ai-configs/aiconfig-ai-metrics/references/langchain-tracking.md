# LangChain & LangGraph Metrics Tracking

LangChain is covered by a first-class LaunchDarkly provider package in both Python and Node. The same package is what LangGraph rides on — there is no separate LangGraph helper.

- Python: `launchdarkly-server-sdk-ai-langchain` (imported as `ldai_langchain`)
- Node: `@launchdarkly/server-sdk-ai-langchain` (exports `LangChainProvider`)

Three helpers do the heavy lifting. Use them — skipping any silently drops value that the provider package would otherwise give you.

| Helper | Purpose |
|---|---|
| `create_langchain_model(config)` (Python) / `LangChainProvider.createLangChainModel(config)` (Node) | Build a LangChain chat model from the AI Config. Forwards **all** variation parameters (temperature, max_tokens, top_p, and so on), picks the correct LangChain chat class based on `config.provider.name`, and handles provider-name mapping internally (for example, LaunchDarkly's `"gemini"` → LangChain's `"google_genai"`). |
| `build_structured_tools(config, registry)` (Python, `ldai_langchain.langchain_helper`) | Read `config.model.parameters.tools` and wrap the matching entries in your `{name: callable}` registry as LangChain `StructuredTool` instances ready for `bind_tools`. This is the first-class replacement for hand-rolled `resolve_tools` / `TOOL_REGISTRY` / `ALL_TOOLS` patterns — it handles async callables via `coroutine=` and uses the LD tool key as the `StructuredTool.name`, so `ToolNode` lookup works without extra mapping. |
| `get_ai_metrics_from_response` (top-level import) / `LangChainProvider.getAIMetricsFromResponse` (Node class method) | Extract token usage from a LangChain response. Pass as the extractor argument to `track_metrics_of` / `trackMetricsOf`. Both import forms are supported in Node; the top-level import is how Python exposes it. |

## `model.parameters` vs `model.custom` — the biggest gotcha

`create_langchain_model` forwards **every key** on `config.model.parameters` to the underlying provider SDK via `init_chat_model`. That means any app-scoped knob you want to drive from LaunchDarkly — search result limits, retry budgets, feature toggles, prompt-variable defaults — **must not** live in `parameters`, because the provider will reject unknown kwargs at runtime (e.g., `AsyncMessages.create() got an unexpected keyword argument 'max_search_results'`).

Put provider-bound fields in `model.parameters` and app-scoped fields in `model.custom`:

```python
# Read a provider-bound parameter (forwarded to the LLM SDK)
temperature = ai_config.model.get_parameter("temperature")

# Read an app-scoped knob (NOT forwarded, safe for anything)
max_search_results = ai_config.model.get_custom("max_search_results") or 10
```

**MCP caveat.** The LaunchDarkly MCP `update-ai-config-variation` tool does not currently expose the `custom` field on a variation. To set `model.custom`, PATCH the variation directly against the REST API:

```bash
curl -X PATCH \
  "https://app.launchdarkly.com/api/v2/projects/$PROJECT/ai-configs/$CONFIG_KEY/variations/$VARIATION_ID" \
  -H "Authorization: $LD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"patch":[{"op":"add","path":"/model/custom","value":{"max_search_results":10}}]}'
```

Nothing in the tracker or provider packages reads `custom` — it's a pass-through bucket for your application to pull from via `config.model.get_custom(key)`.

## Tier 2 — LangChain (single model, not a graph)

The common case: a one-shot LangChain call (ChatOpenAI, ChatAnthropic, ChatGoogleGenerativeAI, ChatBedrockConverse, etc.) against an AI Config in completion mode.

**Python:**

```python
from ldai_langchain import (
    create_langchain_model,
    convert_messages_to_langchain,
    get_ai_metrics_from_response,
)
from langchain_core.messages import HumanMessage

config = ai_client.completion_config("my-config-key", context)
if not config.enabled:
    return None

# create_langchain_model reads config.model.name + parameters and picks the
# right chat class (ChatOpenAI, ChatAnthropic, …) with no per-provider branching.
llm = create_langchain_model(config)

messages = convert_messages_to_langchain(config.messages or [])
messages.append(HumanMessage(content=user_prompt))

tracker = config.create_tracker()
try:
    completion = await tracker.track_metrics_of_async(
        lambda: llm.ainvoke(messages),
        get_ai_metrics_from_response,
    )
    return completion.content
except Exception:
    tracker.track_error()
    raise
```

**Node:**

```typescript
import { LangChainProvider } from '@launchdarkly/server-sdk-ai-langchain';
import { HumanMessage } from '@langchain/core/messages';

const aiConfig = await aiClient.completionConfig('my-config-key', context);
if (!aiConfig.enabled) return null;

// createLangChainModel picks the right chat class (ChatOpenAI, ChatAnthropic, …)
// and forwards all variation parameters.
const llm = await LangChainProvider.createLangChainModel(aiConfig);

const messages = LangChainProvider.convertMessagesToLangChain(aiConfig.messages ?? []);
messages.push(new HumanMessage(userPrompt));

const tracker = aiConfig.createTracker!();
try {
  const completion = await tracker.trackMetricsOf(
    LangChainProvider.getAIMetricsFromResponse,
    () => llm.invoke(messages),
  );
  return completion.content;
} catch (err) {
  tracker.trackError();
  throw err;
}
```

Both `create_langchain_model` and `LangChainProvider.createLangChainModel` raise at model-creation time if the matching LangChain provider integration is not installed. For example, if the variation's `provider.name` is `anthropic`, your environment needs `langchain-anthropic` (Python) or `@langchain/anthropic` (Node). The error surface is LangChain's, not LaunchDarkly's — install the missing integration and re-run.

### Why not `init_chat_model` + a custom provider-name mapping helper?

You will see examples in the wild that build the model by hand with `init_chat_model(model=config.model.name, model_provider=map_provider_to_langchain(config.provider.name))`. Do not do this. It **silently drops every parameter** set on the variation (temperature, max_tokens, top_p, stop sequences, and any new field LaunchDarkly adds later), because `init_chat_model` only receives the name and provider. `create_langchain_model` forwards the whole parameter dict.

## Tier 2 — LangGraph (agent workflows)

LangGraph's `create_react_agent` takes a `model`, `tools`, and `prompt`. Build the model the same way as the single-LangChain case — `create_langchain_model` — and pass it in. The tracker wraps the whole agent invocation, and the extractor aggregates token usage across every message the agent produced.

**Python** — agent mode with a `MemorySaver` checkpointer:

```python
from ldai.tracker import TokenUsage
from ldai_langchain import create_langchain_model, get_ai_metrics_from_response
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

agent_config = ai_client.agent_config("my-agent-key", context)
if not agent_config.enabled:
    return None

llm = create_langchain_model(agent_config)

# MemorySaver gives the ReAct agent short-term memory per thread_id.
checkpointer = MemorySaver()
agent = create_react_agent(
    llm,
    tools=[...],                     # application-owned tool handlers
    prompt=agent_config.instructions,
    checkpointer=checkpointer,
)

async def track_langgraph_metrics(tracker, func):
    """Aggregate token usage across every message the agent produced.
    wraps track_duration_of + manual success/tokens/error tracking."""
    try:
        result = await tracker.track_duration_of(func)
        tracker.track_success()
        total_in = total_out = total = 0
        for message in result.get("messages", []):
            metrics = get_ai_metrics_from_response(message)
            if metrics.usage:
                total_in += metrics.usage.input
                total_out += metrics.usage.output
                total += metrics.usage.total
        if total > 0:
            tracker.track_tokens(TokenUsage(input=total_in, output=total_out, total=total))
        return result
    except Exception:
        tracker.track_error()
        raise

result = await track_langgraph_metrics(
    agent_config.create_tracker(),
    lambda: agent.ainvoke(
        {"messages": [{"role": "user", "content": user_prompt}]},
        config={"configurable": {"thread_id": thread_id}},
    ),
)
```

**Node** — same pattern with `trackMetricsOf` + a custom aggregator:

```typescript
import { LangChainProvider } from '@launchdarkly/server-sdk-ai-langchain';
import type { LDAIMetrics } from '@launchdarkly/server-sdk-ai';
import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { MemorySaver } from '@langchain/langgraph';

const agentConfig = await aiClient.agentConfig('my-agent-key', context);
if (!agentConfig.enabled) return null;

const llm = await LangChainProvider.createLangChainModel(agentConfig);
const checkpointer = new MemorySaver();
const agent = createReactAgent({
  llm,
  tools: [/* ... */],
  prompt: agentConfig.instructions,
  checkpointer,
});

// Aggregate tokens across every message the agent produced.
const langgraphMetrics = (result: any): LDAIMetrics => {
  let input = 0, output = 0, total = 0;
  for (const message of result.messages ?? []) {
    const m = LangChainProvider.getAIMetricsFromResponse(message);
    if (m.usage) {
      input += m.usage.input ?? 0;
      output += m.usage.output ?? 0;
      total += m.usage.total ?? 0;
    }
  }
  return { success: true, usage: total > 0 ? { input, output, total } : undefined };
};

const agentTracker = agentConfig.createTracker!();
const result = await agentTracker.trackMetricsOf(
  langgraphMetrics,
  () => agent.invoke(
    { messages: [{ role: 'user', content: userPrompt }] },
    { configurable: { thread_id: threadId } },
  ),
);
```

### Why aggregate per message

`get_ai_metrics_from_response` / `getAIMetricsFromResponse` is defined on a single LangChain `AIMessage`. A LangGraph run produces N messages (model turn, tool result, model turn, tool result, final). If you pass the whole `result` to the extractor, you miss most of the token usage. Iterating and summing is deliberate — it's the same pattern the LaunchDarkly LangGraph guide uses.

## Binding AI-Config-attached tools with `build_structured_tools`

If the variation has tools attached (via `/aiconfig-tools`), use `build_structured_tools` rather than hand-rolling a `TOOL_REGISTRY` / `resolve_tools` / `ALL_TOOLS` shape. The helper reads `ai_config.model.parameters.tools`, picks the matching entries from your `{name: callable}` registry, wraps them as LangChain `StructuredTool` instances, and preserves the LD tool key as the `StructuredTool.name` (so `ToolNode(...)` lookup works without a second mapping).

```python
# tools.py — implementations only; no manual schema, no resolve_tools()
from langchain_tavily import TavilySearch

async def search(query: str) -> dict:
    """Search the web via Tavily."""
    ai_config = get_agent_config(...)
    max_results = ai_config.model.get_custom("max_search_results") or 10
    return await TavilySearch(max_results=max_results).ainvoke({"query": query})

TOOL_REGISTRY = {"search": search}

# graph.py — bind whatever the active variation exposes
from ldai_langchain import create_langchain_model, get_ai_metrics_from_response
from ldai_langchain.langchain_helper import build_structured_tools

model = create_langchain_model(ai_config)
tools = build_structured_tools(ai_config, TOOL_REGISTRY)
response = await tracker.track_metrics_of_async(
    lambda: model.bind_tools(tools).ainvoke(messages),
    get_ai_metrics_from_response,
)
```

**What you delete when you adopt this:** any module-level `ALL_TOOLS` list, any `resolve_tools(tool_keys)` helper, any hand-written JSON Schema blocks in code. The variation owns the schema; your repo owns the behavior. `ToolNode` can be seeded with every callable in the registry because the LLM only sees the filtered subset `build_structured_tools` produces.

## Tier 3 — fall through to a custom extractor

You will not usually need Tier 3 for LangChain or LangGraph — `get_ai_metrics_from_response` normalizes the response shape across providers. If the variation points at a model whose LangChain integration does not populate `usage_metadata` (rare, usually a custom integration), write a small extractor that reads whatever field the integration exposes and returns `LDAIMetrics`. This is the same fallback documented in [openai-tracking.md](openai-tracking.md) and [anthropic-tracking.md](anthropic-tracking.md).

## Tier 4 — Manual (streaming only)

LangChain streaming with TTFT tracking uses the same manual pattern as direct-SDK streaming. See [streaming-tracking.md](streaming-tracking.md).

## What NOT to do

- **Do not build the model with `init_chat_model` + a hand-rolled provider-name mapping.** The helper forwards all variation parameters; the hand-rolled version silently drops them.
- **If an existing `load_chat_model` / `init_chat_model` wrapper is already in the repo — delete it.** Do not keep it around as a convenience. Leaving it in place means every future agent in the codebase will reach for the familiar function and silently drop variation parameters. Replace imports with `create_langchain_model(ai_config)` at every call site, then remove the wrapper file.
- **Do not keep hand-rolled `TOOL_REGISTRY` / `resolve_tools` / `ALL_TOOLS` patterns once `build_structured_tools` is available.** The SDK helper replaces them. Same deletion principle as above — if a hand-rolled version sits in the repo, future code will use it instead of the SDK helper.
- **Do not put app-scoped knobs in `model.parameters`.** They will be forwarded to the provider SDK and crash at runtime with an unexpected-keyword-argument error. Use `model.custom` for anything that is not a provider-bound parameter.
- **Do not pass the full LangGraph `result` object to `get_ai_metrics_from_response`.** The extractor is defined on a single message; aggregating across `result.messages` is the correct pattern.
- **Do not assume there is a separate LangGraph provider package.** There is not. `@launchdarkly/server-sdk-ai-langchain` and `ldai_langchain` cover both.
- **Do not import `LaunchDarklyCallbackHandler` from `ldai.langchain`.** Neither the class nor the dotted module path exists in the Python package. Use the helpers above.
- **Do not re-encode tool schemas inside the fallback.** If LaunchDarkly is unreachable, the fallback should run *without* tools (or with the minimum provider-bound parameters the app needs). Putting a full `tools` array back into the fallback re-introduces the hardcoded config the migration was supposed to eliminate.
