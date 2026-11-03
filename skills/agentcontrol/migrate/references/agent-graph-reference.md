# Agent Graph Reference

> **Out of scope for the main migration workflow.** Read this only after a single-agent migration works end-to-end. To create the graph itself in LaunchDarkly, use the `agent-graphs` skill.

## What an agent graph is

An **agent graph** is a directed graph where each node is its own config (with its own instructions, model, parameters, and tools) and each edge carries handoff metadata. A root node routes the request to other nodes; nodes may route further or terminate. The topology and each node's config live in LaunchDarkly, so you can change them without redeploying.

Why use it:

- **Add or remove an agent by editing LaunchDarkly**, with no redeploy
- **A/B test routing strategies** by targeting different topologies to different users
- **Roll out a new node to a percentage of traffic**
- **Attach a judge** to a node, or a graph-level judge to the final output

## Three ways to run a graph

| Option | Use when | Python | Node.js |
|---|---|---|---|
| SDK runner | You want the SDK to execute and route the graph | `graph(key, handlers=[...], tool_handlers=...)` | `graph(key, { handlers, toolHandlers })` |
| Framework-native runner | The app is already LangGraph and you want a compiled `StateGraph` | `to_lang_graph(resolve_graph(key, context=ctx), {...})` | `toLangGraph(resolveGraph(key, { context }), {...})` |
| Your own loop | You need custom routing logic | `resolve_graph(...)` + `run_node()` / `route()` | `resolveGraph(...)` + `runNode()` / `route()` |

All three record per-node `$ld:ai:*` events (each node runs through the same tracked path as `config().invoke()`) plus graph-level events: `$ld:ai:graph:invocation_success` / `:invocation_failure`, `:duration:total`, `:total_tokens`, `:node`, and `:handoff_success` / `:handoff_failure`. There is no graph tracker to call.

### SDK runner

```python
from launchdarkly_ai_server import graph
from launchdarkly_ai_openai_messages import create_openai_messages_handler

support = graph(
    "support-graph",
    handlers=[create_openai_messages_handler()],
    tool_handlers={"lookup-order": lookup_order},
)

result = await support.invoke("I was double charged", context, {"tier": "gold"})
print(result.response, result.usage)
```

```typescript
import { graph } from '@launchdarkly/ai-node';
import { createOpenAIHandler } from '@launchdarkly/ai-openai-messages';

const support = graph('support-graph', {
  handlers: [createOpenAIHandler()],
  toolHandlers: { 'lookup-order': lookupOrder },
});

const result = await support.invoke('I was double charged', context, { tier: 'gold' });
```

Each node is routed to a handler by its provider and mode, so pass one handler per provider the graph uses. `graph_judge` / `graphJudge` takes a judge config key evaluated against the final output. `stream()` is available with the same arguments.

For an all-LangChain graph, `langchain_graph(key, llm=None, **options)` / `langchainGraph(key, options, llm?)` from the `langchain-agents` package pre-binds the LangChain agent handler.

### LangGraph-native runner

```python
from launchdarkly_ai_server import resolve_graph
from launchdarkly_ai_langchain_agents import to_lang_graph

run = to_lang_graph(
    resolve_graph("support-graph", context=context),
    {"tool_handlers": {"lookup-order": lookup_order}, "context": context},
)
result = await run.invoke("I was double charged")
```

```typescript
import { resolveGraph } from '@launchdarkly/ai-node';
import { toLangGraph } from '@launchdarkly/ai-langchain-agents';

const result = await toLangGraph(resolveGraph('support-graph', { context }), {
  toolHandlers: { 'lookup-order': lookupOrder },
  context,
}).invoke('I was double charged');
```

Options go in a dict (Python) or object (Node.js) as the second argument, not as keyword arguments. Pass `context` there too, or graph events aren't recorded. `model_factory` / `modelFactory` takes a node and returns a chat model; the default is `ChatOpenAI`, so set it for Anthropic, Bedrock, or Gemini nodes.

### Your own loop

`await resolve_graph(key, context=ctx, handlers=[...])` / `await resolveGraph(key, { context, handlers })` returns a definition with `enabled`, `root`, `get_node`, `edges_from`, `get_child_nodes`, `terminal_nodes`, `traverse`, `reverse_traverse`, plus two execution primitives:

- `run_node(node, input, opts)` runs one node through the tracked invoke path. Pass `{"from": previous_node}` in `opts` to record the handoff.
- `route(node, input, opts)` asks the model to pick an outgoing edge.

Both are async and need `handlers` passed to `resolve_graph()`. The framework-native runners take the un-awaited result, as in the examples above. Check `.enabled` first: a disabled graph has no root and both primitives raise. Guard against cycles with a hop limit; the SDK doesn't stop them for you.

## Fallback

A disabled or missing graph raises `ValueError` (`Agent graph "support-graph" is disabled`), not the `RuntimeError` that `config().invoke()` raises. Keep the pre-migration pipeline as the fallback and catch both:

```python
try:
    result = await support.invoke(user_input, context)
    return result.response
except (RuntimeError, ValueError) as err:
    logger.warning("support-graph unavailable (%s); using hardcoded pipeline", err)
    return await legacy_pipeline(user_input)
```

Re-raise provider exceptions rather than swallowing them, as with single configs.

## Migrating a multi-agent app to graphs

Do this in phases:

1. **Migrate one worker first** with the single-agent workflow (audit, wrap, tools, metrics, evals). Leave the rest hardcoded.
2. **Confirm the wrapped worker runs in production** with metrics on the Monitoring tab.
3. **Migrate the supervisor** the same way, keeping its routing logic hardcoded.
4. **Create the graph in LaunchDarkly** with the `agent-graphs` skill: one node per worker plus the supervisor, edges with handoff metadata.
5. **Replace the hardcoded router** with one of the three runners above, keeping the old router as the fallback.
6. **Verify the Monitoring tab** shows graph-level metrics in addition to per-node metrics.
7. **Only then** start changing routing in LaunchDarkly and targeting topologies per segment.

Each phase is reversible: the fallback keeps the hardcoded pipeline serving traffic while a graph issue is fixed.

## Replacing legacy graph code

| Legacy (`ldai`, `@launchdarkly/server-sdk-ai`) | Current |
|---|---|
| `ai_client.agent_graph(key, ctx)` + hand-written traversal | `graph(key, ...).invoke(input, ctx)`, or `await resolve_graph(key, context=ctx, handlers=[...])` + `run_node()` |
| `graph_def.is_enabled()` | `definition.enabled` |
| `node.get_config()` / `node.get_edges()` | `node.config` / `node.edges` |
| `edge.target_config` | `edge.target_key` |
| `graph_def.get_tracker()` and every `track_*` call | Delete; graph events are recorded automatically |
| `node.get_config().create_tracker()` per node | Delete; `run_node()` records per-node metrics |
| `create_agent_graph` / `ManagedAgentGraph.run` | `graph(key, handlers=[...])` |

## Resources

- Python SDK: https://github.com/launchdarkly/python-ai-sdk
- Node.js SDK: https://github.com/launchdarkly/js-ai-sdk
- Check each repo's CHANGELOG before applying these patterns; the graph API is still evolving.
