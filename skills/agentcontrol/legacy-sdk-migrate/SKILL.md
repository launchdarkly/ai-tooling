---
name: legacy-sdk-migrate
description: "Migrate an app from the legacy LaunchDarkly AI SDKs (Python `launchdarkly-server-sdk-ai` / `ldai`, Node.js `@launchdarkly/server-sdk-ai`) to the current handler-based AI SDKs (`launchdarkly-ai-server`, `@launchdarkly/ai-node` / `@launchdarkly/ai-server` plus handler packages). Use when code calls `LDAIClient`, `initAi`, `completion_config` / `completionConfig`, `agent_config` / `agentConfig`, `agent_configs`, `create_tracker` / `trackMetricsOf`, `create_judge`, `create_model`, or `agent_graph`, or when the user asks to upgrade between LaunchDarkly AI SDKs. For apps with hardcoded LLM prompts that aren't on LaunchDarkly yet, use `migrate` instead."
license: Apache-2.0
compatibility: Python 3.12+ (`launchdarkly-ai-server` 1.0.0+ with `launchdarkly-server-sdk`) or Node.js (`@launchdarkly/ai-node` 1.0.0+). No LaunchDarkly MCP tools needed; the AgentControl configs already exist.
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# Migrate from the legacy AI SDKs

You're using a skill that will guide you through moving an application from the legacy LaunchDarkly AI SDKs to the current handler-based AI SDKs. Your job is to inventory every legacy call site, map each one to its current equivalent, rewrite the code, and verify that the app still behaves the same, including when LaunchDarkly is unreachable.

The current SDKs are **not drop-in replacements**. In the legacy SDKs the app evaluates a config, builds a provider client, merges messages, calls the provider, and wraps the call in a tracker. In the current SDKs the app registers handlers and tools once, then calls `config()`, `graph()`, or a handler package's convenience function. The SDK evaluates the config, routes to the handler that matches the variation's provider and mode, calls the provider, and records metrics and OpenTelemetry spans.

Source guide: [Migrate from the legacy AI SDKs](https://launchdarkly.com/docs/sdk/ai/migration). Full before/after code for every pattern: [references/api-mapping.md](references/api-mapping.md).

## Prerequisites

- The app already uses a legacy AI SDK, and its AgentControl configs (formerly AI Configs) already exist in LaunchDarkly. The config keys, variations, tools, and judges carry over unchanged; this is a code migration only. (If the app calls an LLM provider directly with hardcoded prompts and does not use LaunchDarkly yet, use the `migrate` skill instead.)
- `LD_SDK_KEY` (server-side SDK key) and the provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...) available as environment variables. The current SDKs read them from the environment.
- **Python:** the current packages require **Python 3.12 or later** (`launchdarkly-ai-server` 1.0.0+), and the API is **async** (`await config(...).invoke(...)`). `launchdarkly-server-sdk` is required at runtime for standard initialization and `ldclient.Context` (installed via `"launchdarkly-ai-server[ld]"` / `"launchdarkly-ai-python[ld]"` or by keeping `launchdarkly-server-sdk`). Check Python 3.12+ before you start.
- **Node.js:** `@launchdarkly/ai-node` 1.0.0+ for Node (bundles `@launchdarkly/node-server-sdk`); `@launchdarkly/ai-server` plus a pre-initialized client for edge or custom runtimes.

## Core Principles

1. **Inventory before you edit.** Find every legacy import and call site first, and confirm the list with the user.
2. **Use the real export names.** Handler factories are `create_<provider>_<mode>_handler()` in Python and `create<Provider><Mode>Handler()` in Node (`createOpenAIMessagesHandler`, `createOpenAIAgentsHandler`, `create_openai_agents_handler`). Check the installed package's exports before writing an import; don't guess.
3. **Keep the fallback.** The current SDKs take no fallback argument. `invoke()` raises when the variation is disabled (targeting off) or LaunchDarkly is unreachable, so every call site that relied on `enabled=False` defaults needs an explicit `try`/`except` (or `try`/`catch`) that preserves today's degraded behavior.
4. **Delete, don't wrap.** Remove trackers, `track_*` calls, provider-client construction, message merging, and `model=config.model.name` plumbing. Leaving them in double-counts metrics.
5. **Register once.** Put handlers and tool implementations in one `Registry` (or the global registry) instead of rebuilding them at every call site.
6. **Ask before rewriting business logic.** If the app post-processes provider-specific response objects (for example `completion.choices[0].message.content`), switch to `result.response`, and ask before changing anything downstream that depends on the raw provider object.

## Workflow

### Step 1: Explore (read-only)

Find every legacy usage. Search for these patterns and record file and line for each hit:

| Language | Imports and packages | Calls |
|----------|----------------------|-------|
| Python | `launchdarkly-server-sdk-ai`, `launchdarkly-server-sdk-ai-openai`, `launchdarkly-server-sdk-ai-langchain`; `from ldai`, `from ldai_openai`, `from ldai_langchain` | `LDAIClient(`, `completion_config(`, `agent_config(`, `agent_configs(`, `judge_config(`, `create_judge(`, `create_model(`, `create_agent(`, `agent_graph(`, `create_agent_graph(`, `create_tracker(`, `track_metrics_of`, `track_duration`, `track_tokens`, `track_success`, `track_error`, `track_feedback`, `track_tool_call`, `get_ai_metrics_from_response` |
| Node.js | `@launchdarkly/server-sdk-ai`, `@launchdarkly/server-sdk-ai-openai`, `@launchdarkly/server-sdk-ai-langchain`, `@launchdarkly/server-sdk-ai-vercel` | `initAi(`, `completionConfig(`, `agentConfig(`, `agentConfigs(`, `judgeConfig(`, `createJudge(`, `createModel(`, `createAgent(`, `agentGraph(`, `createTracker(`, `.tracker`, `trackMetricsOf`, `trackStreamMetricsOf`, `trackDuration`, `trackTokens`, `trackSuccess`, `trackError`, `trackFeedback`, `getAIMetricsFromResponse`, `getAIMetricsFromStream`, `createLangChainModel` |

For each call site, also record:

- **Provider and SDK** used for the actual model call (OpenAI, Anthropic, LangChain/LangGraph, Vercel AI SDK, LiteLLM, Bedrock, Gemini, other).
- **Mode**: completion (`completion_config`) or agent (`agent_config`), and whether it streams.
- **Tools**: any function-calling loop, and the tool names it dispatches.
- **Fallback behavior**: what the code does when `enabled` is false.
- **Extras**: template variables, conversation history, judges, agent graphs, custom tracker calls such as `track_feedback`.

Present the inventory and **stop** until the user confirms it.

### Step 2: Assess

Pick a target for each call site:

| Legacy pattern | Current replacement |
|----------------|---------------------|
| One provider, one mode, manual completion call | That handler package's convenience function, for example `openai_messages()` / `openaiMessages()` |
| Config can serve several providers or modes | `config(key=..., handler=[...])` then `.invoke(user_input, context, variables)` |
| Agent mode with a tool loop | `config()` with an agent handler and `tool_handlers` / `toolHandlers`; mode comes from the variation |
| Streaming (`trackStreamMetricsOf`, manual TTFT) | `config(...).stream(...)`; iterate events (`chunk` events carry `text`; the final `done` event carries `response` and `usage`) |
| Multi-turn chat (`createChat`, message arrays you maintain) | Pass prior turns as the `history` argument (fourth positional argument) to `invoke()` / `stream()` |
| `agent_configs()` / `agentConfigs()`, `agent_graph()`, `create_agent_graph()`, managed graph runners | `graph(key, handlers=[...]).invoke(...)`, or `resolve_graph()` / `resolveGraph()` plus a native runner (`to_lang_graph` / `toLangGraph`, `to_openai_agents` / `toOpenAIAgents`, `to_claude_agents` / `toClaudeAgents`) |
| `create_judge()` / `createJudge()` / `judge_config()` | Judges attached to the config variation run automatically. For background scoring, pass `skip_judges=True` / `skipJudges: true`, hand each `judge_tasks` / `judgeTasks` item to a durable worker, run `run_judge()` / `runJudge()`, and explicitly track the returned score(s) |
| `create_model().run()` / `createModel().run()`, `create_agent()` | Same convenience function or `config().invoke()` path |
| Same handlers and tools at many call sites | One shared `Registry` passed as `registry=` |

Handler packages (each `launchdarkly-ai-<name>` in Python, `@launchdarkly/ai-<name>` in Node):

| Package suffix | Provider | Mode |
|----------------|----------|------|
| `openai-messages` | OpenAI | completion (`messages`) |
| `openai-agents` | OpenAI | agent |
| `claude-messages` | Anthropic | completion (`messages`) |
| `claude-agents` | Anthropic (Claude Agent SDK) | agent |
| `langchain-messages` / `langchain-agents` | Any LangChain chat model / LangGraph | completion / agent |
| `litellm-messages` / `litellm-agents` | Any LiteLLM provider (use for Bedrock, Gemini, and others without a dedicated package) | completion / agent |
| `vercel-messages` / `vercel-agents` | Any Vercel AI SDK provider | completion / agent |

A variation whose provider has no matching registered handler raises `Handler for provider <name> not found`. Register a handler for every provider and mode your variations can serve, or write one with `createHandler` / `create_handler` for an internal endpoint.

Confirm the plan with the user: target per call site, packages to add and remove, and how each fallback will be preserved.

### Step 3: Execute

Work one call site at a time. Full code for each step is in [references/api-mapping.md](references/api-mapping.md).

1. **Swap packages.** Remove the legacy AI packages and install the current core package plus one handler package per provider and mode.
   - Python: `pip install "launchdarkly-ai-server[ld]" launchdarkly-ai-openai-messages` (or `"launchdarkly-ai-python[ld]"`). Remove `launchdarkly-server-sdk-ai` and `launchdarkly-server-sdk-ai-*`. Keep `launchdarkly-server-sdk` installed (either directly or via the `[ld]` extra) unless the app runs on a custom runtime and passes its own client to `init_client(client=...)`.
   - Node: `npm install @launchdarkly/ai-node @launchdarkly/ai-openai-messages`. Remove `@launchdarkly/server-sdk-ai` and `@launchdarkly/server-sdk-ai-*`. `@launchdarkly/ai-node` bundles `@launchdarkly/node-server-sdk`, so keep a direct `@launchdarkly/node-server-sdk` dependency only if the app still imports it for ordinary feature flags. Edge runtimes install `@launchdarkly/ai-server` and pass their client to `initClient(client)`.
2. **Replace initialization and check content capture.** Delete `LDAIClient(...)` / `initAi(...)`. The SDK initializes lazily from `LD_SDK_KEY` on the first AI call. Call `init_client()` / `initClient()` only to pass options or pre-warm, and call `shutdown()` on exit to flush events and spans. In 1.0+, OpenTelemetry spans capture prompts, model output, tool payloads, and judge reasoning **by default** (`capture_content=True`). Ask if the app handles sensitive data and needs to opt out via `configure(options=SDKOptions(capture_content=False))` (Python) or `configure({ options: { captureContent: false } })` (Node.js).
3. **Rewrite each call and check parameter forwarding.** Replace evaluate → build messages → call provider → track with one convenience function or `config(...).invoke(user_input, context, variables)`. Read the output from `result.response`. Python contexts passed to `invoke()` / `stream()` / `graph()` are plain dicts (`{"kind": "user", "key": "user-123"}`). Handler packages forward a fixed per-handler allowlist of `model.parameters` (mapping `max_tokens` to `max_output_tokens` on OpenAI) and drop unknown keys; move app-scoped knobs to `model.custom`. If writing a custom handler (`create_handler` / `createHandler`), forward `model.parameters` through an explicit allowlist (never a raw `**params` spread or denylist alone, and never forward `tools`).
4. **Move template variables** from the `completion_config` / `agent_config` argument to the `variables` keyword (convenience functions, Python), the `{ variables }` option (convenience functions, Node), or the third argument to `invoke()`. Note that the current SDKs inject the evaluation context as `{{ldContext.*}}` (replacing legacy `{{ldctx.*}}`) and require Mustache placeholders without spaces (`{{name}}`, not `{{ name }}`).
5. **Move tools.** Register implementations by name in `tool_handlers` / `toolHandlers` or a `Registry`. Keys must match the tool names in the config variation exactly, including case. Each tool function is called with a single `args` dict/object (not unpacked keyword arguments), so wrap multi-argument functions (`lambda args: fn(**args)`) or LangChain `@tool` objects (`lambda args: tool.invoke(args)`). Delete the hand-written tool loop.
6. **Preserve fallbacks.** Wrap `invoke()` and return the app's previous fallback response when the config is disabled or LaunchDarkly is unreachable. In the `except` / `catch` block, check `(await inspect_config(key, context))["enabled"]` / `(await inspectConfig(key, context)).enabled` and re-raise when `True` so mid-run provider or tool-loop errors aren't mistaken for a disabled config. Use `inspect_config()` / `inspectConfig()` (never raises; returns `enabled`, `config`, `meta`) for health checks or to branch before invoking.
7. **Replace tracking code and convert Python `track()` contexts.** Remove legacy `create_tracker`, generation/token/duration tracking, and `get_ai_metrics_from_response` / `getAIMetricsFromResponse` helpers; `invoke()` and `stream()` record those automatically. Preserve explicit app events: replace user feedback calls with `get_client().track()` / `getClient().track()` using `result.track_data` / `result.trackData` (see [references/api-mapping.md](references/api-mapping.md#user-feedback)). **In Python, `get_client().track()` requires an `ldclient.Context` (`Context.from_dict(context)`), not the plain dict passed to `invoke()`**—passing a raw dict to `get_client().track()` silently drops the event. **Background judges are the exception:** `run_judge()` / `runJudge()` returns score data but deliberately does not call the LaunchDarkly client's `track()` method. Track every returned metric from the worker as shown in the reference.
8. **Centralize.** If two or more call sites share handlers or tools, create one `Registry` (or register on `global_registry` / `globalRegistry` at startup) and pass `registry=`.
9. **Remove dead imports and packages** once nothing references them.

### Step 4: Verify

1. **No legacy references remain:** re-run the Step 1 search. Expect zero hits for `ldai`, `server-sdk-ai`, `create_tracker`, `createTracker`, `track_metrics_of`, and `trackMetricsOf`.
2. **Build and tests pass:** run the project's type check, linter, and test suite. Update mocks that patched `LDAIClient` / `initAi` to patch `config` or the convenience function instead.
3. **Happy path:** with `LD_SDK_KEY` set, run each migrated call and confirm it returns a response from the provider the variation names.
4. **Fallback path:** with targeting off for the config (or an invalid `LD_SDK_KEY`), confirm the app returns its fallback instead of crashing.
5. **Metrics:** after a few calls, the config's Monitoring tab in LaunchDarkly shows generations, tokens, and duration for the new SDK version. If judges run in a worker, also confirm their evaluation metrics appear.
6. **Report:** list each migrated call site (file and line), packages added and removed, and anything left unmigrated with the reason.

## Edge Cases

| Situation | Action |
|-----------|--------|
| Python below 3.12 | Stop and tell the user. The current Python packages need 3.12+. |
| Synchronous Python code path (Flask, Django views, scripts) | Run the async call with `asyncio.run(...)` at the boundary, or move the handler to an async framework. Ask which. |
| App reads provider-native fields (`choices`, `tool_calls`, `stop_reason`) | Use `result.response` and `result.usage`; ask before changing downstream logic that needs the raw object. |
| Provider has no handler package (Bedrock, Gemini, Azure, internal gateway) | Use `litellm-*`, `langchain-*`, or `vercel-*`, or build a custom handler with `createHandler` / `create_handler` (match the config's provider name case-sensitively, such as `"OpenAI"`, `"Anthropic"`, `"Bedrock"`, `"Gemini"`, call `parse_template` / `parseTemplate` on raw prompt strings, and forward `model.parameters` through an explicit allowlist rather than spreading `**params`). |
| App stores custom app/tool knobs in `model.parameters` | Handler packages forward only an allowlist of model parameters and drop unknown keys. Move app-scoped knobs to `model.custom` and read them via `inspect_config()` / `inspectConfig()` or inside a custom handler (`ld_config["model"].get("custom")`). |
| App walks an agent graph by hand (`agent_graph().traverse()` / `get_edges()`) | Prefer `graph().invoke()` or a native runner (`to_lang_graph`, `to_openai_agents`, `to_claude_agents`). If keeping a custom walk with `resolve_graph()` / `resolveGraph()`, note that it returns topology only (`enabled`, `root`, `node.config`, `node.edges`, `edge.target_key`) and emits **no** telemetry unless you execute hops via `graph.run_node()` / `graph.route()` (passing `handlers=` to `resolve_graph()`) or emit the 1.0 `$ld:ai:graph:*` events yourself. Warn the user that legacy graph event keys changed (`path` → `node`, `handoff` → `handoff_success`/`handoff_failure`, `invocation` → `invocation_success`/`invocation_failure`, `total` → `total_tokens`, `tool` → `tool_call`). |
| App handles sensitive/regulated prompts or outputs (PII, PHI) | Content capture on OpenTelemetry spans is **on by default** in 1.0+ (`capture_content=True`). Disable it process-wide with `configure(options=SDKOptions(capture_content=False))` (Python) or `configure({ options: { captureContent: false } })` (Node.js), or pass `capture_content=False` / `{ captureContent: false }` to handler factories. |
| App uses `claude-agents` and relies on Claude Code built-ins or `~/.claude/settings.json` | In 1.0+, `create_claude_agents_handler()` / `createClaudeAgentsHandler()` disables built-in tools unless a `NativeTool` sentinel is attached to the variation, and loads no host settings (`setting_sources=[]`). Pass `setting_sources=["user"]` or set env vars if the app routes to Bedrock/Vertex/a gateway through `~/.claude/settings.json`. |
| App calls `track_feedback` / `trackFeedback` for thumbs up or down | Replace `tracker.track_feedback` with `get_client().track("$ld:ai:feedback:user:positive" or ":negative", Context.from_dict(context), result.track_data, 1)` in Python or `getClient().track(event, context, result.trackData, 1)` in Node.js (note: `stream()` does not currently return `track_data`). |
| Large app, gradual rollout | Migrate one call site at a time, verify it, and remove the legacy packages only after the last call site moves. |
| Judges must not add latency | `skip_judges=True` / `skipJudges: true`, then put `judge_tasks` / `judgeTasks` on a durable worker or queue. Run `run_judge()` / `runJudge()` there and track the returned score(s) with their supplied track data. |
| Agent Skills from AgentControl are needed | Agent Skills reach apps only through the current SDKs; the legacy SDKs never deliver them. |

## What NOT to Do

- Don't keep the legacy tracker around the new call. The SDK already records metrics; you'll double-count.
- Do not fire and forget `run_judge()` / `runJudge()`. A request-scoped task can be cancelled before it finishes, and the runner returns metrics for the worker to track rather than tracking them itself.
- Don't pass a default or fallback config object to `config()`; it has no such argument. Handle errors instead.
- Don't construct an OpenAI or Anthropic client to pass in. Handlers build their own clients from environment variables.
- Don't rename config keys, tools, or variations in LaunchDarkly as part of this migration.
- Don't invent export names. If an import fails, list the package's exports and use the real name.

## References

- [references/api-mapping.md](references/api-mapping.md): before/after code for initialization, completion calls, agent mode and tools, registries, streaming, history, judges, and graphs, in Python and Node.js
- [Migrate from the legacy AI SDKs](https://launchdarkly.com/docs/sdk/ai/migration)
- [Python AI SDK reference](https://launchdarkly.com/docs/sdk/ai/python) and [Node.js (server-side) AI SDK reference](https://launchdarkly.com/docs/sdk/ai/node-js)
