---
name: migrate
description: "Migrate an application with hardcoded LLM prompts to a full LaunchDarkly AgentControl implementation in five stages: audit the code, wrap the call, move the tools, verify metrics, attach evaluators. Use when the user wants to externalize model/prompt configuration, move from direct provider calls (OpenAI, Anthropic, Bedrock, Gemini, Strands) to a managed config, migrate off the legacy LaunchDarkly AI SDK, or stage a full hardcoded-to-LaunchDarkly migration."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server. Code examples use `launchdarkly-ai-server` 0.3.0+ (Python) or `@launchdarkly/ai-node` 0.3.0+ (Node.js).
metadata:
  author: launchdarkly
  version: "0.2.0"
---

# Migrate to AgentControl

You're using a skill that will guide you through migrating an application from hardcoded LLM prompts to a full LaunchDarkly AgentControl implementation. Your job is to run the migration in **five stages**, stopping at each stage for the user to confirm:

1. **Audit the code** — read-only scan that produces a structured list of everything hardcoded (prompt, model, parameters, tools, app-scoped knobs).
2. **Wrap the call** — install the SDK, create the config in LaunchDarkly, and route the provider call through `config().invoke()`, keeping the original call as the fallback.
3. **Move the tools** — extract each tool's JSON schema, attach it to the config, and pass the implementations to the SDK as tool handlers.
4. **Verify metrics** — confirm duration, tokens, and success/error reach the Monitoring tab, and add feedback or business metrics if the app needs them.
5. **Attach evaluators** — either offline evals via the Playground + Datasets, or judges that score sampled traffic automatically.

> **⚠️ Three first-run failure modes to avoid.**
>
> 1. **Placeholders with spaces.** The SDK fills `{{name}}` and `{{user.name}}` only. `{{ name }}` with spaces is sent to the model as literal text. Rewrite every placeholder without spaces in Stage 2.
> 2. **No fallback.** `invoke()` has no fallback argument. It raises `RuntimeError` when the variation is disabled, the config key doesn't exist, or LaunchDarkly is unreachable. Keep the original hardcoded call and run it from an `except RuntimeError` branch, or the app goes down with LaunchDarkly.
> 3. **Fallthrough not flipped after `/configs-create`.** A freshly created config's fallthrough points at an auto-generated disabled variation, so every `invoke()` raises until `/configs-targeting` runs. Flip it before Stage 2 verification.

## How the current SDK changes the migration

The SDK now owns the provider call. You evaluate a config and invoke it in one step, and a **handler** calls the provider. Metrics are recorded on every call, so there's no tracker to create or scope. What that means for each stage:

| Concern | Current SDK |
|---|---|
| Provider call | A handler package (OpenAI, Anthropic, LangChain) or a custom handler that wraps your existing call |
| Fallback | Your own code, run when `invoke()` raises `RuntimeError` |
| Template variables | Third argument to `invoke()`; `{{name}}` placeholders, no spaces |
| Tools | `tool_handlers={"tool-key": fn}` on `config()`; the handler runs the tool loop |
| Metrics | Automatic: duration, tokens, success/error, tool calls |
| Judges | Attached judges run inside `invoke()`; `skip_judges=True` + `run_judge()` for background work |
| Multi-agent | `graph()`, or `resolve_graph()` + a native runner such as `to_lang_graph` |

If the app already uses the legacy LaunchDarkly AI SDK (`ldai`, `@launchdarkly/server-sdk-ai`, `completion_config()`, `create_tracker()`), this skill also covers that move: treat the legacy calls as the "hardcoded" targets in Stage 1. The `built-in-metrics` skill has a legacy-to-current mapping table.

## Coverage — which shapes are well-trodden vs require extrapolation

The skill is optimized for Python and Node.js / TypeScript. The current AI SDKs exist for Python and Node.js only.

| Shape | Python | Node.js | Reference |
|-------|--------|---------|-----------|
| One-shot completion (direct OpenAI / Anthropic call) | ✅ Worked example | ✅ Worked example | [before-after-examples.md](references/before-after-examples.md) |
| Bedrock / Gemini / custom HTTP direct call | ✅ Custom handler | ✅ Custom handler | `built-in-metrics` per-provider references |
| LangChain single-call | ✅ Handler package | ✅ Handler package | [agent-mode-frameworks.md § LangChain](references/agent-mode-frameworks.md) |
| LangGraph prebuilt agent (Python `create_agent`, Node `createReactAgent`) | ✅ Worked example | ✅ Worked example | [before-after-examples.md](references/before-after-examples.md), [agent-mode-frameworks.md § LangGraph prebuilt](references/agent-mode-frameworks.md) |
| LangGraph custom `StateGraph` | ✅ Custom agent handler | ⚠️ Translate from Python | [agent-mode-frameworks.md § Custom `StateGraph`](references/agent-mode-frameworks.md) |
| CrewAI | ✅ Custom agent handler | — (not a Node framework) | [agent-mode-frameworks.md § CrewAI](references/agent-mode-frameworks.md) |
| Strands | ✅ Custom agent handler | ⚠️ BedrockModel + OpenAIModel only | [agent-mode-frameworks.md § Strands](references/agent-mode-frameworks.md) |
| Custom ReAct loop | ✅ Replace with SDK tool loop | ✅ Same | [agent-mode-frameworks.md § Custom ReAct loop](references/agent-mode-frameworks.md) |
| Streaming (SSE / WebSocket) | ✅ `stream()` | ✅ `stream()` | `built-in-metrics` streaming reference |
| Multi-agent graph (supervisor + workers) | ⚠️ Out of main scope | ⚠️ Out of main scope | [agent-graph-reference.md](references/agent-graph-reference.md) |
| Other agent frameworks (Pydantic AI, DSPy, AutoGen, LlamaIndex) | ⚠️ Custom agent handler | ⚠️ Same | [agent-mode-frameworks.md § Framework-agnostic rules](references/agent-mode-frameworks.md) |
| Go, Ruby, .NET | ℹ️ Legacy SDKs only | ℹ️ Legacy SDKs only | [phase-1-analysis-checklist.md § SDK routing table](references/phase-1-analysis-checklist.md) |

**Reading the key:** ✅ = follow the skill verbatim; ⚠️ = the architecture applies but you'll translate idioms or cross-reference another skill; ℹ️ = this skill doesn't cover it.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment, and an application that already calls an LLM provider with hardcoded model, prompt, and parameter values.

**Required environment:**
- `LD_SDK_KEY` — server-side SDK key (starts with `sdk-`) from the target LaunchDarkly project. The SDK reads this variable, not `LAUNCHDARKLY_SDK_KEY`.

**MCP tools used directly by this skill:** none — every LaunchDarkly write happens in a focused sibling skill.

**Check the SDK CHANGELOG before applying any pattern.** The SDKs are in beta and may have breaking changes. Before you start, skim the latest CHANGELOG for anything that contradicts the pattern you're about to apply:

- Python: https://github.com/launchdarkly/python-ai-sdk
- Node.js: https://github.com/launchdarkly/js-ai-sdk

If a CHANGELOG entry post-dates this skill and changes an API you're about to use, the CHANGELOG wins — and the skill should be updated.

**Hand-off model.** This skill does **not** auto-invoke other skills. At each stage that needs a LaunchDarkly write, this skill prepares the inputs (config key, mode, model, prompt, tool schemas, judge keys) and then **tells the user to run the next slash-command themselves**. After the user finishes that sibling skill, return to the next step here.

**Sibling skills the user runs at each stage:**
- `projects` — pre-Stage 2, only if no project exists yet
- `configs-create` — Stage 2 (creates the config and first variation)
- `configs-targeting` — right after `configs-create` (promotes the new variation to fallthrough so the SDK actually serves it)
- `tools` — Stage 3 (creates tool definitions and attaches them)
- `online-evals` — Stage 5 (attaches judges, creates custom judges)

## Core Principles

1. **Inspect before you mutate.** Every stage begins with a read-only audit. Do not touch code until Step 1 is confirmed by the user.
2. **Move the source of config, not the business logic.** The request handler, its inputs, and its return shape stay the same. What changes is where the model, prompt, and parameters come from, and that the provider call runs inside a handler.
3. **The fallback is the current behavior.** Keep the original hardcoded call as a function and run it when `invoke()` raises, so the app is unchanged if LaunchDarkly is unreachable.
4. **Stages are ordered.** Wrap before you add tools. Add tools before you verify metrics. Verify metrics before you add evals.
5. **Hand off to focused skills, manually.** Each stage that needs a LaunchDarkly write tells the user to run a sibling slash-command and waits for them to come back.

## Workflow

### Minimum viable migration

Stages 1–4 are independently shippable. **A migration that stops after Stage 4 is complete, production-ready, and delivers the core value** — externalized prompts and model config, targeting, variation A/B testing, and Monitoring-tab metrics. Stage 5 (evaluators) is a quality-of-life addition, not a gate.

### Step 1: Audit the codebase (Stage 1)

This stage is **read-only** — no code writes, no LaunchDarkly resources created. Scan the repo and produce a structured manifest of every hardcoded value that needs to move, then hand it back to the user for confirmation.

Use [phase-1-analysis-checklist.md](references/phase-1-analysis-checklist.md) to scan:

1. **Language and package manager** — Python (pip/poetry/uv) or TypeScript/JavaScript (npm/pnpm/yarn)
2. **LLM provider and framework** — OpenAI, Anthropic, Bedrock, Gemini, LangChain, LangGraph, CrewAI, Strands
3. **Existing LaunchDarkly usage** — an `LDClient` / `ldclient` initialization to reuse, and any legacy AI SDK usage to replace
4. **Hardcoded model configs** — model name string literals, temperature / max_tokens / top_p, system prompts, instruction strings
5. **Template placeholders in prompts** — `.format()` calls, f-strings, JS/TS template literals, `%(var)s`, hand-rolled `str.replace("__VAR__", ...)`, and existing Mustache with spaces (`{{ var }}`). Flag each placeholder name and its runtime-value source; all get rewritten to `{{var}}` in Stage 2.
6. **Externalized prompt files** — YAML / JSON / TOML / Markdown / `.prompt` / `.j2` files **and** prompt-template registries (`langchain.hub.pull(...)`, LangSmith `client.pull_prompt(...)`). See [phase-1-analysis-checklist.md § 4](references/phase-1-analysis-checklist.md).
7. **Hardcoded app-scoped knobs** — search-result limits, retry budgets, tool-timeout overrides, feature toggles. These belong in `model.custom` on the variation, not `model.parameters`, which the handlers forward to the provider SDK.
8. **Mode decision** — completion mode (messages array) or agent mode (single instructions string). The variation's mode picks the handler at runtime.

For each hardcoded target, record:

- File path and line range
- Current value (model name, full prompt text, parameter dict)
- Target config field (`model.name`, `model.parameters.temperature`, `messages[].content`, `instructions`)
- Whether the surrounding call uses function calling / tools (drives Stage 3)
- Whether the surrounding call has retry logic (stays in the handler, around the provider call)

**Stage 1 output** (return to user as a structured summary):

```
Language: Python 3.12
Package manager: uv
LLM provider: OpenAI
Existing LD SDK: none
Target mode: completion
Hardcoded targets:
  - src/chat.py:42   model="gpt-4o"
  - src/chat.py:43   temperature=0.7, max_tokens=2000
  - src/chat.py:45   system="You are a helpful assistant..."
Externalized prompt files: none
Prompt-template registries: none
Coverage totals: 3 hardcoded code targets · 0 externalized prompt files · 0 registry pulls
Proposed plan: single config key `chat-assistant`, OpenAI handler package, original call kept as fallback, Stage 3 (tools) skipped (no function calling), Stage 5 attach built-in accuracy judge.
```

**STOP.** Present this summary, state the coverage totals out loud (e.g. "I found **N** hardcoded code targets and **M** externalized prompt files — does that match what you expected?"), and wait for the user to reply with one of four explicit forms:

- **`confirm`** — proceed to Stage 2.
- **`add: <files or paths>`** — re-run the audit with the new locations and present an updated summary.
- **`fix: <correction>`** — update a target in the list (provider, mode, prompt content, etc.) and ask again.
- **`stop`** — pause the migration here.

Do not interpret any other word — including `skip`, `next`, `go`, `ok`, `proceed` — as confirmation; ask the user to pick one of the four forms. **This is the most important checkpoint in the workflow.**

### Step 2: Wrap the call in the AI SDK (Stage 2)

This is the first stage that writes code. It has eight sub-steps.

1. **Delete hand-rolled model wrappers the audit flagged.** `load_chat_model(f"{provider}/{name}")` and similar one-argument `init_chat_model(...)` wrappers (shipped with `langchain-ai/react-agent` and its derivatives) drop every variation parameter. Delete the function and its module; the LangChain handler package replaces it. Hand-rolled `resolve_tools` / `TOOL_REGISTRY` helpers get replaced by `tool_handlers` in Stage 3.

2. **Install the AI SDK.** Detect the package manager from Step 1, then install the core package plus one handler package per provider and mode:
   - Python: `launchdarkly-ai-server` + `launchdarkly-ai-openai-messages`, `-openai-agents`, `-claude-messages`, `-claude-agents`, `-langchain-messages`, or `-langchain-agents`
   - Node.js/TypeScript: `@launchdarkly/ai-node` + `@launchdarkly/ai-openai-messages`, `-openai-agents`, `-claude-messages`, `-claude-agents`, `-langchain-messages`, or `-langchain-agents`
   - Bedrock, Gemini, and custom HTTP: no handler package; use the LangChain handler or a custom handler (see `built-in-metrics`)

   Pin exact versions; the SDKs are in beta.

3. **Initialize the client.** The SDK initializes lazily from `LD_SDK_KEY` on the first call, so a plain app needs no init code. Call `init_client()` / `initClient()` at startup only to fail fast or pass options. If the app already has an `LDClient` for feature flags, hand it to the SDK instead of creating a second one:

   ```python
   from launchdarkly_ai_server import init_client, shutdown

   await init_client(client=ldclient.get())   # reuse the app's existing client
   # ... on process exit:
   await shutdown()                             # flushes events, then closes the client
   ```

   ```typescript
   import { initClient, shutdown } from '@launchdarkly/ai-node';

   await initClient(ldClient); // reuse the app's existing client
   // ... on process exit:
   await shutdown();
   ```

   Without a key, `init_client()` and every `invoke()` raise `RuntimeError`. Don't let that crash startup: log a warning and let the fallback in sub-step 6 handle requests.

4. **Hand off to `configs-create`, then `configs-targeting`.** Print the extracted model, prompt/instructions, parameters, and mode from the Stage 1 manifest, then tell the user: *"Run `/configs-create` with these inputs, then `/configs-targeting` to serve the new variation, then come back here."* Supply the config key the code will call (e.g. `chat-assistant`). Wait for the user to finish.

5. **Rewrite template placeholders.** If the hardcoded prompt interpolates runtime values with `.format()`, f-strings, JS template literals, or any other syntax (`{system_time}`, `${userName}`, `%(topic)s`, `{{ topic }}`), rewrite every placeholder to `{{name}}` with no spaces, in the prompt you send to `/configs-create`. Pass the values as the third argument to `invoke()`:

   **Before:**
   ```python
   SYSTEM_PROMPT = "You are a helpful assistant. The time is {system_time}."
   prompt = SYSTEM_PROMPT.format(system_time=datetime.now().isoformat())
   ```

   **After (prompt in the config):** `You are a helpful assistant. The time is {{system_time}}.`

   ```python
   result = await chat.invoke(user_input, context, {"system_time": datetime.now().isoformat()})
   ```

   The renderer supports dot paths (`{{user.name}}`) and leaves unknown or spaced placeholders as literal text. Every call also gets the evaluation context as `{{ldContext.key}}`, `{{ldContext.name}}`, and so on. Prompts written for the legacy SDK's `{{ldctx.*}}` need renaming.

6. **Keep the original call as the fallback.** Rename the existing hardcoded function (e.g. `answer` → `answer_hardcoded`) and leave it untouched. It is the fallback, and it already mirrors current behavior exactly. See [fallback-defaults-pattern.md](references/fallback-defaults-pattern.md) for the variants.

7. **Route the call site through `config().invoke()`.** Build the config instance once at module scope, and invoke it per request with the user's context:

   **Python — before:**
   ```python
   def answer(user_input: str) -> str:
       response = openai_client.chat.completions.create(
           model="gpt-4o",
           temperature=0.7,
           max_tokens=2000,
           messages=[
               {"role": "system", "content": "You are a helpful assistant..."},
               {"role": "user", "content": user_input},
           ],
       )
       return response.choices[0].message.content
   ```

   **Python — after:**
   ```python
   from launchdarkly_ai_server import config
   from launchdarkly_ai_openai_messages import create_openai_messages_handler

   chat = config(key="chat-assistant", handler=create_openai_messages_handler())

   async def answer(user_id: str, user_input: str) -> str:
       try:
           result = await chat.invoke(user_input, {"kind": "user", "key": user_id})
           return result.response
       except RuntimeError:
           logger.warning("chat-assistant unavailable; using hardcoded fallback")
           return answer_hardcoded(user_input)
   ```

   The context is a plain dict (`{"kind": "user", "key": ..., "name": ...}`), not an `ldclient` `Context`. Reuse the attributes the app already uses for feature-flag targeting.

   > **⚠️ Python handlers don't forward every model parameter.** In `launchdarkly-ai-openai-messages` 0.2.x, the handler sends no variation parameters to OpenAI, so `temperature`, `max_tokens`, and the rest are ignored. `launchdarkly-ai-claude-messages` forwards only `max_tokens`. The Node.js handlers and the Python LangChain handlers forward them all. If the hardcoded call depends on its parameters, use a custom handler (below) or the LangChain handler in Python until this changes, and confirm the behavior against the CHANGELOG.

   **If the provider has no handler package, or the call has logic you must keep** (retries, prompt caching, a proxy, Azure OpenAI), wrap the existing call in a custom handler instead. The handler receives the served config as a dict, so the hardcoded literals become reads from it:

   ```python
   from launchdarkly_ai_server import config, create_handler, parse_template

   async def call_openai(ld_config, user_input, tool_handlers, variables, history):
       params = ld_config["model"].get("parameters", {})
       messages = [
           {**m, "content": parse_template(m["content"], variables)} for m in ld_config.get("messages", [])
       ]
       response = openai_client.chat.completions.create(
           model=ld_config["model"]["name"],
           temperature=params.get("temperature"),
           max_tokens=params.get("max_tokens"),
           messages=[*messages, {"role": "user", "content": user_input}],
       )
       return {
           "output": response.choices[0].message.content,
           "usage": {"input": response.usage.prompt_tokens, "output": response.usage.completion_tokens},
       }

   chat = config(key="chat-assistant", handler=create_handler(("OpenAI", "messages"), call_openai))
   ```

   Custom handlers get the raw prompt, so render placeholders with `parse_template` / `parseTemplate`. The provider name in `create_handler` must match the config's provider exactly (`"OpenAI"`, `"Anthropic"`, `"Bedrock"`, `"Gemini"`), and in Python the first argument must be a tuple.

   **Agent mode** — for LangGraph, CrewAI, Strands, or any framework that takes an instructions string: use an agent-mode handler package (`-openai-agents`, `-claude-agents`, `-langchain-agents`) or a custom handler registered for `(provider, "agent")` that reads `ld_config["instructions"]`. See [agent-mode-frameworks.md](references/agent-mode-frameworks.md).

   See [before-after-examples.md](references/before-after-examples.md) for full Python OpenAI, Node.js Anthropic, and LangGraph agent-mode paired snippets.

8. **Verify.** Run the app with a valid `LD_SDK_KEY`; confirm the call succeeds and the response matches pre-migration output. Then unset `LD_SDK_KEY` (or set `LD_SDK_KEY=sdk-invalid`) and confirm the fallback runs without error. Both paths must work before moving to Stage 3. To check what's being served without invoking, call `await inspect_config(key, context)` / `await inspectConfig(key, context)`; it returns `enabled`, the parsed config, and the variation metadata without raising.

Delegate: **`configs-create`** and **`configs-targeting`** (sub-step 4).

### Step 3: Move tools into the config (Stage 3)

Skip this step if the audited app has no function calling / tools. Otherwise:

1. **Enumerate the tools currently registered.** Common shapes to look for:

   - `openai.chat.completions.create(tools=[...])` — OpenAI direct
   - `anthropic.messages.create(tools=[...])` — Anthropic direct
   - `create_agent(llm, tools=[...], system_prompt=...)` — LangGraph prebuilt (Python, `langchain.agents`)
   - `createReactAgent({ llm, tools: [...] })` — LangGraph.js prebuilt
   - `Agent(tools=[...])` — CrewAI or Strands
   - **Custom `StateGraph`** — a module-level `TOOLS = [...]` list referenced in **both** `model.bind_tools(TOOLS)` and `ToolNode(TOOLS)`

   Record each tool's name, description, and JSON schema. For LangChain `@tool` tools, extract the schema with `tool.args_schema.model_json_schema()`; for plain callables, `StructuredTool.from_function(fn).args_schema.model_json_schema()`. Do not hand-write the schema.

2. **Hand off to `tools`.** Print the extracted tool names, descriptions, and schemas, then tell the user: *"Run `/tools` with these tools and the variation key, then come back here."* Wait for the user to finish.

3. **Pass the implementations as tool handlers.** Map each LaunchDarkly tool key to its function on the `config()` call, and delete the hardcoded tools array. The handler package converts the config's tool schemas for the provider, runs the tool loop (up to 10 model calls), and records a `$ld:ai:tool_call` event per call:

   ```python
   chat = config(
       key="chat-assistant",
       handler=create_openai_messages_handler(),
       tool_handlers={
           "search-kb": lambda args: search_kb(args["query"]),
           "calculator": lambda args: calculate(args["expression"]),
       },
   )
   ```

   ```typescript
   const chat = config({
     key: 'chat-assistant',
     handler: createOpenAIHandler(),
     toolHandlers: {
       'search-kb': (args) => searchKb(args.query),
       calculator: (args) => calculate(args.expression),
     },
   });
   ```

   Each function receives one argument, the parsed arguments dict, and may be sync or async. Keys must match the tool keys in LaunchDarkly exactly; a tool the model calls with no matching function raises `No handler registered for tool "x"`. For LangChain `@tool` objects, wrap them: `{"search-kb": lambda args: search_kb.invoke(args)}`. The `tools` skill covers the full contract.

   **For custom `StateGraph` shapes and custom handlers**, the handler receives tracked tool functions in its `tool_handlers` argument. Build **both** the `.bind_tools(...)` list and the `ToolNode(...)` from that argument, so the model and the executor see the same tools — see [agent-mode-frameworks.md § Custom `StateGraph`](references/agent-mode-frameworks.md).

4. **Verify.** Run the app; confirm the tool flows still execute correctly and `$ld:ai:tool_call` events appear for the config.

Delegate: **`tools`** (sub-step 2).

### Step 4: Verify metrics (Stage 4)

Every `invoke()` and `stream()` call records duration, input/output/total tokens, generation success or error, and one event per dispatched tool call, all attributed to the served variation. There is no tracker to create. This stage confirms the data flows and adds the two things the SDK doesn't record.

1. **Check the Monitoring tab.** Hit the wrapped endpoint in staging, then open the config in LaunchDarkly → **Monitoring**. Duration, token, and generation counts should appear within 1–2 minutes. Force an error (bad provider key) and confirm the error count increments; the SDK records the error and re-raises.
2. **If tokens are missing**, the handler isn't returning usage. Custom handlers must return `{"output": ..., "usage": {"input": n, "output": n}}`. For streaming, enable usage on the final chunk (`stream_options={"include_usage": True}` for OpenAI).
3. **Wire feedback if the app has thumbs-up/down UI.** The SDK doesn't record feedback. Store the result's `track_data` with the message and send the event when the user responds:

   ```python
   from ldclient import Context
   from launchdarkly_ai_server import get_client

   event = "$ld:ai:feedback:user:positive" if thumbs_up else "$ld:ai:feedback:user:negative"
   get_client().track(event, Context.from_dict(context), result.track_data, 1)
   ```

   `track_data` is a plain dict, so it can be persisted and sent from a different process than the one that produced the response.
4. **Time to first token isn't recorded** by the current SDKs. Don't hand-roll it.
5. **Business metrics** (conversion, resolution) go through the `custom-metrics` skill, using the same `track_data`.

Delegate: none required. Point the user at **`built-in-metrics`** for per-provider details and at **`custom-metrics`** for business metrics. See [sdk-ai-tracker-patterns.md](references/sdk-ai-tracker-patterns.md) for what's recorded and how legacy tracker code maps.

### Step 5: Attach evaluations (Stage 5)

1. **Decide between three evaluation paths.**

   | Path | When to use | Supports agent mode? |
   |------|-------------|---------------------|
   | **Offline eval** (recommended default for migration) | Pre-ship regression: run a fixed dataset through the new variation in the LD Playground and score against baseline. | Yes — all modes |
   | **Attached judges** | Attach judges to a variation; `invoke()` runs them on sampled requests and records the scores. Zero code changes. | Yes, when attached through the API; the UI widget is completion-mode only |
   | **Background judges** | Same attached judges, but `skip_judges=True` returns them as `judge_tasks` so a worker runs them off the request path. | Yes |

   **Most migration users should start with offline eval**, then attach judges once the rollout is stable.

2. **Offline eval shape for a migration.** Generate a starter dataset CSV from the audit manifest (one representative input per row) and point the user at the [Offline Evals guide](https://launchdarkly.com/docs/home/agentcontrol/offline-evaluations).
   - Run the variation that mirrors the pre-migration hardcoded behavior against the dataset first — this is the baseline.
   - Clone it into a second variation pointing at a **different model family**. The comparison is most informative across families, not across siblings.
   - Attach the built-in **Accuracy** judge with a pass threshold of **0.85**, and run both variations against the same dataset.
   - Promote the winner to fallthrough via `/configs-targeting` only if it beats the baseline on Accuracy and does not regress on Relevance or Toxicity.

   Write this shape into the project's `datasets/README.md` (or equivalent) so the comparison is reproducible.

3. **Hand off to `online-evals`** for attached judges. Tell the user: *"Run `/online-evals` with these inputs, then come back here."* Pass the config key, variation key, the built-in judges or custom judge keys to attach, and the target environment. Every judge's provider needs a handler in the `handler` list, alongside the config's own.

4. **For background judges**, pass `skip_judges=True` and hand each task to a worker. The `online-evals` skill has the full worker, including the Python `Context.from_dict()` conversion `track()` needs:

   ```python
   result = await config(key="chat-assistant", handler=handlers, skip_judges=True).invoke(user_input, context)
   for task in result.judge_tasks or []:
       asyncio.create_task(run_judge_worker(task))
   ```

5. **Verify.**
   - **Attached judges:** trigger a request in staging, open the Monitoring tab → "Evaluator metrics". Scores appear within 1–2 minutes at the configured sampling rate. `result.judge_results` shows the scores in code.
   - **Offline eval:** run the dataset through the LD Playground, compare baseline vs new-variation scores side by side.

Delegate: **`online-evals`** (sub-step 3, optional — offline eval doesn't delegate).

## Edge Cases

| Situation | Action |
|-----------|--------|
| App already initializes `LDClient` for feature flags | Reuse it — `init_client(client=ldclient.get())` / `initClient(ldClient)`. Do not create a second client |
| App is on the legacy AI SDK (`ldai`, `@launchdarkly/server-sdk-ai`) | Treat `completion_config` / `agent_config` / `create_tracker` call sites as Stage 1 targets. Replace with `config().invoke()`, delete tracker code, and replace `*ConfigDefault` fallbacks with the original-call fallback |
| App uses LangChain `ChatOpenAI(model=...)` | Use the LangChain handler package. For providers it doesn't build itself (anything but OpenAI, Anthropic, Bedrock), pass a model factory: `create_langchain_messages_handler(lambda cfg: ChatX(model=cfg["model"]["name"], **cfg["model"].get("parameters", {})))` |
| Retry wrapper around the provider call | Keep it inside a custom handler, around the provider call. The SDK records one generation per `invoke()`, however many retries happen inside |
| App has no tools — Stage 3 skipped | Move directly from Stage 2 verification to Stage 4 |
| Mode mismatch: user said agent, audit shows one-shot chat | Choose completion mode unless the app uses a prebuilt agent (`create_agent`, `createReactAgent`), CrewAI, Strands, or a similar goal-driven framework |
| App uses Strands Agents | Agent mode, custom handler registered for each provider the variations serve. See [agent-mode-frameworks.md § Strands](references/agent-mode-frameworks.md) |
| Strands app on TypeScript | TS SDK ships `BedrockModel` and `OpenAIModel` only — cannot serve Anthropic-backed variations |
| `LD_SDK_KEY` is missing at startup | Log a warning; the `except RuntimeError` fallback serves every request. Never raise at import time |
| Multi-agent graph (supervisor + workers) | Stop after migrating a single agent. Read [agent-graph-reference.md](references/agent-graph-reference.md) for the graph-level path |
| Tool with a Pydantic `args_schema` (LangChain `@tool`) | Extract the schema via `tool.args_schema.model_json_schema()`; do not hand-write it |
| App-scoped knob a tool needs per variation | Store it in `model.custom`. A custom handler reads `ld_config["model"]["custom"]`; with a handler package, read it once per request with `await inspect_config(key, context)` and close over it in the tool function you pass to `tool_handlers` |
| App has a `Context` dataclass with env-var fallbacks for model and prompt (e.g. `react-agent`'s `context.py`) | Move the values into the config and the original call path. Keep the dataclass only as the fallback's source of values, not as a second runtime source |

## What NOT to Do

### Fallback and config lifetime (most common failure mode)

- **Don't call `invoke()` without a fallback.** It raises `RuntimeError` for a disabled variation, a missing config key, a missing SDK key, or an unreachable LaunchDarkly. Catch `RuntimeError` specifically; provider errors are different exception types and should keep propagating.
- **Don't delete the original hardcoded call.** It's the fallback. Rename it, don't remove it.
- **Don't build a `config()` instance per request.** Build it once at module scope; `invoke()` evaluates targeting fresh on every call.
- **Don't call `invoke()` more than once per user turn** for the same logical request. Each call is a flag evaluation and a recorded generation. For an agent, one turn is one `invoke()` call; the handler runs the loop.

### Templates

- **Don't write placeholders with spaces.** `{{ name }}` is sent literally; write `{{name}}`.
- **Don't keep `{{ldctx.*}}`** from legacy prompts; the current variable is `{{ldContext.*}}`.
- **Don't skip `parse_template` in a custom handler.** The handler receives the raw prompt.

### LangChain / LangGraph patterns

- **If the repo contains a `load_chat_model(f"{provider}/{name}")` helper, delete it — don't just avoid using it.** It drops every variation parameter. The LangChain handler packages build the model with the served parameters.
- **Same rule for hand-rolled `resolve_tools` / `TOOL_REGISTRY` / `ALL_TOOLS` helpers.** Replace them with `tool_handlers`.
- **Don't put app-scoped knobs in `model.parameters`.** The handlers forward every parameter to the provider SDK, so `max_search_results` crashes the provider call. Use `model.custom`.
- **Don't re-encode tool schemas in the fallback.** The fallback is the original call, with whatever tools it had.

### Stage / handoff discipline

- Don't skip Step 1 even when the user says "just wrap it."
- Don't delegate to `configs-create` before extracting the prompt and model.
- Don't claim you "delegated to `configs-create`" or any other sibling skill. Print the inputs, tell the user to run the slash-command, then wait.
- Don't skip `/configs-targeting` after `/configs-create`. A freshly created config serves a disabled variation, so `invoke()` raises and every request takes the fallback.
- Don't attempt a multi-agent graph migration in one pass.

### Metrics and evaluations

- **Don't add tracker or `track()` calls for duration, tokens, success, or tool calls.** The SDK records them; manual events double count.
- Don't use `launchdarkly-metric-instrument` for agent metrics. That skill is for feature-flag metrics.
- Don't hardcode built-in judge config keys. Ask the user to copy them from **AgentControl > Library** in the LD UI.
- Don't attach judges without a handler for the judge's provider in the `handler` list.

## Related Skills

- `configs-create` — called by Stage 2 to create the config
- `configs-targeting` — called right after `configs-create`, and later to roll out new variations
- `tools` — called by Stage 3 to create and attach tool definitions
- `built-in-metrics` — per-provider handler details and the legacy tracker mapping
- `custom-metrics` — business metrics on top of the built-in ones
- `online-evals` — called by Stage 5 to attach judges
- `configs-variations` — add variations for A/B testing after migration is complete
- `configs-update` — modify config properties as your app evolves

## References

- [phase-1-analysis-checklist.md](references/phase-1-analysis-checklist.md) — Step 1 audit checklist, grep patterns, SDK routing table, mode decision tree
- [before-after-examples.md](references/before-after-examples.md) — Paired hardcoded-to-wrapped snippets for Python OpenAI, Node.js Anthropic, Python LangGraph
- [sdk-ai-tracker-patterns.md](references/sdk-ai-tracker-patterns.md) — What the SDK records, feedback, and the legacy tracker mapping
- [agent-mode-frameworks.md](references/agent-mode-frameworks.md) — Agent-mode handlers for LangGraph, CrewAI, Strands, and custom loops
- [fallback-defaults-pattern.md](references/fallback-defaults-pattern.md) — Fallback patterns now that `invoke()` raises instead of returning a default
- [agent-graph-reference.md](references/agent-graph-reference.md) — Out-of-scope pointer doc for multi-agent migrations
