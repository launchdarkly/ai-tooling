---
name: aiconfig-migrate
description: "Migrate an application with hardcoded LLM prompts to a full LaunchDarkly AI Configs implementation in five stages: extract prompts, wrap in the AI SDK, add tools, add tracking, add evals/judges. Use when the user wants to externalize model/prompt configuration, move from direct provider calls (OpenAI, Anthropic, Bedrock, Gemini) to a managed AI Config, or stage a full hardcoded-to-LaunchDarkly migration."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# Migrate to AI Configs

You're using a skill that will guide you through migrating an application from hardcoded LLM prompts to a full LaunchDarkly AI Configs implementation. Your job is to audit the existing code, extract the hardcoded model and prompt, wrap the call site in the AI SDK with a safe fallback, move tools into the config, instrument the tracker, and attach evaluations — in that order, stopping at each stage for the user to confirm.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment, and an application that already calls an LLM provider with hardcoded model, prompt, and parameter values.

**Required environment:**
- `LD_SDK_KEY` — server-side SDK key (starts with `sdk-`) from the target LaunchDarkly project

**MCP tools used directly by this skill:** none — every LaunchDarkly write happens in a focused sibling skill.

**Hand-off model.** This skill does **not** auto-invoke other skills. At each stage that needs a LaunchDarkly write, this skill prepares the inputs (config key, mode, model, prompt, tool schemas, judge keys) and then **tells the user to run the next slash-command themselves**. After the user finishes that sibling skill, return to the next step here. Treat the "Delegate" lines below as next-step instructions, not auto-handoffs.

**Sibling skills the user runs at each stage:**
- `aiconfig-projects` — pre-Stage 2, only if no project exists yet
- `aiconfig-create` — Stage 2 (creates the AI Config and first variation)
- `aiconfig-tools` — Stage 3 (creates tool definitions and attaches them)
- `aiconfig-targeting` — between Stage 2 and Stage 4 (promotes the new variation to fallthrough so the SDK actually serves it)
- `aiconfig-online-evals` — Stage 5 (attaches judges, creates custom judges)

## Core Principles

1. **Inspect before you mutate.** Every stage begins with a read-only audit. Do not touch code until Step 1 is confirmed by the user.
2. **Replace config, not business logic.** The SDK call is a drop-in for the place where the model, parameters, and prompt are *defined* — not for the provider call itself. OpenAI/Anthropic/Bedrock calls stay where they are.
3. **Fallback mirrors current behavior.** The fallback passed to `completion_config` / `agent_config` must preserve the hardcoded values you removed, so the app is unchanged if LaunchDarkly is unreachable.
4. **Stages are ordered.** Wrap before you add tools. Add tools before you track. Track before you add evals. Skipping ahead produces configs without traffic, metrics without context, and judges with nothing to score.
5. **Hand off to focused skills, manually.** Each stage that needs a LaunchDarkly write tells the user to run a sibling slash-command (`/aiconfig-create`, `/aiconfig-tools`, `/aiconfig-targeting`, `/aiconfig-online-evals`) and waits for them to come back. This skill does **not** auto-invoke other skills.

## Workflow

### Step 1: Audit the codebase (read-only)

Run the phase-1 checklist and produce a structured summary. **This step writes no code and creates no LaunchDarkly resources.**

Use [phase-1-analysis-checklist.md](references/phase-1-analysis-checklist.md) to scan:

1. **Language and package manager** — Python (pip/poetry/uv), TypeScript/JavaScript (npm/pnpm/yarn), Go, Ruby, .NET
2. **LLM provider** — OpenAI, Anthropic, Bedrock, Gemini, LangChain, LangGraph, CrewAI
3. **Existing LaunchDarkly usage** — any pre-existing `LDClient` or `ldclient` initialization to reuse
4. **Hardcoded model configs** — model name string literals, temperature / maxTokens / topP, system prompts, instruction strings
5. **Mode decision** — completion mode (chat messages array) or agent mode (single instructions string). Completion mode is the default and the only mode that supports judges attached in the UI.

**Phase 1 output** (return to user as a structured summary):

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
Proposed plan: single AI Config key `chat-assistant`, mirror fallback, Stage 3 (tools) skipped (no function calling), Stage 4 (tracking) inline, Stage 5 (evals) attach built-in accuracy judge.
```

**STOP.** Present this summary and wait for the user to confirm before proceeding to Stage 1 extract. This is the same stop point as the `AGENT-SETUP-PROMPT.md` Phase 1 pattern.

### Step 2: Extract prompts (Stage 1)

Turn the audit into a concrete migration manifest — still read-only. For each hardcoded target from Step 1, record:

- File path and line range
- Current value (model name, full prompt text, parameter dict)
- Target AI Config field (`model.name`, `model.parameters.temperature`, `messages[].content`, `instructions`)
- Whether the surrounding call uses function calling / tools (drives Stage 3)
- Whether the surrounding call has retry logic (affects where Stage 4 tracker calls go)

This manifest is the contract for the next four stages. Review it with the user. Do not mutate any files in this step.

### Step 3: Wrap the call in the AI SDK (Stage 2)

This is the first stage that writes code. It has six sub-steps.

1. **Install the AI SDK.** Detect the package manager from Step 1, then install:
   - Python: `launchdarkly-server-sdk` + `launchdarkly-server-sdk-ai`
   - Node.js/TypeScript: `@launchdarkly/node-server-sdk` + `@launchdarkly/server-sdk-ai`
   - Go: `github.com/launchdarkly/go-server-sdk/v7` + `github.com/launchdarkly/go-server-sdk/ldai`

2. **Initialize `LDAIClient` once at startup.** Reuse any existing `LDClient` — do not create a second base client. Place the initialization in the same module that owns existing app config.

   **Python:**
   ```python
   import ldclient
   from ldclient.config import Config
   from ldai.client import LDAIClient

   ldclient.set_config(Config(os.environ["LD_SDK_KEY"]))
   ai_client = LDAIClient(ldclient.get())
   ```

   **Node.js/TypeScript:**
   ```typescript
   import { init } from '@launchdarkly/node-server-sdk';
   import { initAi } from '@launchdarkly/server-sdk-ai';

   const ldClient = init(process.env.LD_SDK_KEY!);
   await ldClient.waitForInitialization({ timeout: 10 });
   const aiClient = initAi(ldClient);
   ```

3. **Hand off to `aiconfig-create`.** Print the extracted model, prompt/instructions, parameters, and mode from Step 2's manifest, then tell the user: *"Run `/aiconfig-create` with these inputs, then come back here."* Supply the config key you want the code to call (e.g. `chat-assistant`). Do not attempt to auto-invoke the sibling skill — wait for the user to finish it before continuing.

   **After `aiconfig-create` finishes, the user must also run `/aiconfig-targeting` to promote the new variation to fallthrough.** A freshly created variation returns `enabled=False` to every consumer until targeting is updated. Skip this and Stage 2 verification (sub-step 7 below) will silently take the fallback path on every request.

4. **Build the fallback.** Mirror the hardcoded values you extracted. Use `AICompletionConfigDefault` / `AIAgentConfigDefault` in Python, plain object literals in Node. See [fallback-defaults-pattern.md](references/fallback-defaults-pattern.md) for inline, file-backed, and bootstrap-generated patterns.

   **Python fallback (completion mode):**
   ```python
   from ldai.client import AICompletionConfigDefault, ModelConfig, ProviderConfig, LDMessage

   fallback = AICompletionConfigDefault(
       enabled=True,
       model=ModelConfig(name="gpt-4o", parameters={"temperature": 0.7, "maxTokens": 2000}),
       provider=ProviderConfig(name="openai"),
       messages=[LDMessage(role="system", content="You are a helpful assistant...")],
   )
   ```

5. **Replace the hardcoded call site.** Swap the hardcoded model/prompt/params for a `completion_config` / `completionConfig` (or `agent_config` / `agentConfig`) call, then read the returned fields into the existing provider call. Keep the provider call intact.

   **Python — before:**
   ```python
   response = openai_client.chat.completions.create(
       model="gpt-4o",
       temperature=0.7,
       max_tokens=2000,
       messages=[
           {"role": "system", "content": "You are a helpful assistant..."},
           {"role": "user", "content": user_input},
       ],
   )
   ```

   **Python — after:**
   ```python
   context = Context.builder(user_id).set("email", user.email).build()
   config = ai_client.completion_config("chat-assistant", context, fallback)

   if not config.enabled:
       return disabled_response()

   params = config.model.parameters or {}
   response = openai_client.chat.completions.create(
       model=config.model.name,
       temperature=params.get("temperature"),
       max_tokens=params.get("maxTokens"),
       messages=[m.to_dict() for m in (config.messages or [])] + [
           {"role": "user", "content": user_input},
       ],
   )
   ```

   **Python — after (agent mode)** — for LangGraph, CrewAI, or any framework that takes a goal/instructions string:

   ```python
   context = Context.builder(user_id).kind("user").build()
   config = ai_client.agent_config("support-agent", context, FALLBACK)

   if not config.enabled:
       return disabled_response()

   # config is a single AIAgentConfig object — NOT a (config, tracker) tuple.
   # The tracker lives at config.tracker.
   model_name = f"{config.provider.name}/{config.model.name}"
   instructions = config.instructions
   params = config.model.parameters or {}

   # Pass model_name + instructions into your framework's agent constructor.
   # Example: LangGraph create_react_agent
   # agent = create_react_agent(
   #     model=load_chat_model(model_name),
   #     tools=TOOLS,               # Stage 3 will replace this with a config.tools loader
   #     prompt=instructions,
   # )
   ```

   See [before-after-examples.md](references/before-after-examples.md) for full Python OpenAI, Node Anthropic, and LangGraph agent-mode paired snippets.

6. **Check `config.enabled`.** If it returns `False`, handle the disabled path without crashing and without calling the provider. The check is required — not optional.

7. **Verify.** Run the app with a valid `LD_SDK_KEY`; confirm the call succeeds and the response matches pre-migration output. Then temporarily set `LD_SDK_KEY=sdk-invalid` (or unset it) and confirm the fallback path runs without error. Both paths must work before moving to Stage 3.

Delegate: **`aiconfig-create`** (sub-step 3).

### Step 4: Move tools into the config (Stage 3)

Skip this step if the audited app has no function calling / tools. Otherwise:

1. **Enumerate the tools currently registered.** Common shapes to look for:

   - `openai.chat.completions.create(tools=[...])` — OpenAI direct
   - `anthropic.messages.create(tools=[...])` — Anthropic direct
   - `create_react_agent(tools=[...])` — LangGraph prebuilt ReAct
   - `Agent(tools=[...])` — CrewAI
   - **Custom `StateGraph`** — module-level `TOOLS = [...]` list referenced in **both** `model.bind_tools(TOOLS)` and `ToolNode(TOOLS)`. This is the `langchain-ai/react-agent` template shape; the list is usually in a `tools.py` module. Grep for `bind_tools(` and `ToolNode(` together — they will point at the same list.

   Record each tool's name, description, and JSON schema.

   For LangChain/LangGraph tools defined with `@tool`, extract the schema via `tool.args_schema.model_json_schema()` (or the equivalent Pydantic `model_json_schema()` call). For plain async callables used as tools (common in custom StateGraph shapes), LangChain infers the schema from the function signature at bind time — extract it via `StructuredTool.from_function(fn).args_schema.model_json_schema()`. Do not hand-write the schema.

2. **Hand off to `aiconfig-tools`.** Print the extracted tool names, descriptions, and schemas, then tell the user: *"Run `/aiconfig-tools` with these tools and the variation key, then come back here."* The sibling skill creates tool definitions (`create-ai-tool`) and attaches them to the variation (`update-ai-config-variation`). Wait for the user to finish before proceeding to sub-step 3. Do not auto-invoke.

3. **Replace the hardcoded tools array at the call site** with a read from `config.tools` (or the SDK equivalent for your language). Load the actual implementation functions dynamically from the tool names — see [agent-mode-frameworks.md](references/agent-mode-frameworks.md) for the dynamic-tool-factory pattern from the devrel agents tutorial.

   **For custom `StateGraph` shapes**, you must update **both** call sites: `.bind_tools(TOOLS)` and `ToolNode(TOOLS)` must both read from the same `config.tools`-derived list. Forgetting one leaves the LLM seeing the new tools but the executor still running the old ones, or vice versa.

4. **Verify.** Run the app; confirm the tool flows still execute correctly. `get-ai-config` (via the delegate) confirms the tools are attached server-side.

Delegate: **`aiconfig-tools`** (sub-step 2).

### Step 5: Instrument the tracker (Stage 4)

This stage has **no delegate**. The tracker wiring is inline because no existing skill covers the AI `tracker.track_*` methods — the `launchdarkly-metric-instrument` skill is for `ldClient.track()` feature metrics, which is a different API. See [sdk-ai-tracker-patterns.md](references/sdk-ai-tracker-patterns.md) for the full per-method Python + Node matrix.

1. **Locate the tracker.** It's attached to the config object returned in Stage 2: `config.tracker` (Python) or `aiConfig.tracker` (Node).

2. **Wrap the provider call** with duration, success, error, and token tracking.

   **Python — manual tracking:**
   ```python
   import time
   from ldai.tracker import TokenUsage

   start = time.time()
   try:
       response = openai_client.chat.completions.create(...)
       config.tracker.track_duration(int((time.time() - start) * 1000))
       config.tracker.track_success()
       config.tracker.track_tokens(TokenUsage(
           input=response.usage.prompt_tokens,
           output=response.usage.completion_tokens,
           total=response.usage.total_tokens,
       ))
   except Exception:
       config.tracker.track_error()
       raise
   ```

   **Node — manual tracking:**
   ```typescript
   const start = Date.now();
   try {
     const response = await openai.chat.completions.create(/* ... */);
     aiConfig.tracker.trackDuration(Date.now() - start);
     aiConfig.tracker.trackSuccess();
     aiConfig.tracker.trackTokens({
       input: response.usage?.prompt_tokens ?? 0,
       output: response.usage?.completion_tokens ?? 0,
       total: response.usage?.total_tokens ?? 0,
     });
   } catch (error) {
     aiConfig.tracker.trackError();
     throw error;
   }
   ```

3. **Prefer auto-tracking helpers where available.** They capture duration, tokens, and success/error in one call and avoid drift between manual blocks.

   | Provider | Python method | Node method |
   |----------|--------------|-------------|
   | OpenAI (any chat completion) | `tracker.track_openai_metrics(lambda: ...)` | `tracker.trackOpenAIMetrics(() => ...)` |
   | Bedrock (Converse API) | `tracker.track_bedrock_converse_metrics(response)` | `tracker.trackBedrockConverseMetrics(response)` |
   | Vercel AI SDK (`generateText`) | — | `tracker.trackVercelAISDKGenerateTextMetrics(() => ...)` |
   | LangChain (single-node model call) | **Manual** — wrap `ainvoke` in try/except and call `tracker.track_duration` + `track_success` + `track_tokens` using `response.usage_metadata` (see snippet below) | **Manual** (same pattern; LangChain.js usage metadata is standardized) |
   | LangGraph multi-node (EXPERIMENTAL) | `ldai_langchain.LDMetricsCallbackHandler` — requires `node_keys: Set[str]` and `fn_name_to_config_key: Dict[str, str]` constructor args. Marked not production-ready. Not suitable for single-node react-agent shapes. | — |
   | Custom / any other | `tracker.track_metrics_of(func, extractor)` | `tracker.trackMetricsOf(extractor, () => ...)` |

   **Do not hallucinate a `LaunchDarklyCallbackHandler` or `ldai.langchain` module.** Neither exists. The real Python package is `ldai_langchain` (underscore, top-level), it exposes `LangChainModelRunner`, `LangChainAgentRunner`, `LangChainRunnerFactory`, `LangGraphAgentGraphRunner`, and helper functions — none of which is a single-node plug-and-play callback. For the common single-node LangChain case, manual tracking via `response.usage_metadata` is the recommended path.

   **LangChain single-node manual tracking pattern** (Python):

   ```python
   import time
   from ldai.tracker import TokenUsage

   start = time.time()
   try:
       response = await model.ainvoke([
           {"role": "system", "content": config.instructions},
           *state.messages,
       ])
       config.tracker.track_duration(int((time.time() - start) * 1000))
       config.tracker.track_success()
       # LangChain standardizes token usage across providers on AIMessage.usage_metadata
       if hasattr(response, "usage_metadata") and response.usage_metadata:
           um = response.usage_metadata
           config.tracker.track_tokens(TokenUsage(
               input=um.get("input_tokens", 0),
               output=um.get("output_tokens", 0),
               total=um.get("total_tokens", 0),
           ))
   except Exception:
       config.tracker.track_error()
       raise
   ```

   `AIMessage.usage_metadata` is LangChain's standardized token usage field — it works across providers (OpenAI, Anthropic, Bedrock, Gemini) because LangChain normalizes the provider-specific shapes behind the scenes.

   There is no built-in Anthropic direct-API helper in either SDK. For Anthropic direct calls (not via LangChain), use the manual pattern from the "Node — manual tracking" block above, or switch the call through Bedrock Converse.

4. **Wire feedback tracking if the app has thumbs-up/down UI.** Both SDKs expose `trackFeedback` with a `{kind}` argument.

   **Python:**
   ```python
   from ldai.tracker import FeedbackKind
   config.tracker.track_feedback({"kind": FeedbackKind.Positive})
   ```

   **Node:**
   ```typescript
   import { LDFeedbackKind } from '@launchdarkly/server-sdk-ai';
   aiConfig.tracker.trackFeedback({ kind: LDFeedbackKind.Positive });
   ```

5. **Verify.** Hit the wrapped endpoint in staging, then open the AI Config in LaunchDarkly → Monitoring tab. Duration, token, and generation counts should appear within 1–2 minutes. If nothing shows up, walk the checklist in [sdk-ai-tracker-patterns.md](references/sdk-ai-tracker-patterns.md) under "Troubleshooting."

### Step 6: Attach evaluations (Stage 5)

1. **Decide between three evaluation paths.** This is the most commonly misunderstood stage — there are **three** paths, not two, and the right default for a migration context is often the one people skip.

   | Path | When to use | Supports agent mode? |
   |------|-------------|---------------------|
   | **Offline eval** (recommended default for migration) | Pre-ship regression: run a fixed dataset through the new variation in the LD Playground and score against baseline. Best fit for migration because you want to prove the new AI Config behaves at least as well as the hardcoded version before shipping. | Yes — all modes |
   | **UI-attached auto judges** | Attach one or more judges to a variation in the LD UI; judges run on sampled live requests automatically. Zero code changes. | Completion mode only (the UI widget is completion-only today) |
   | **Programmatic direct-judge** | Call `ai_client.create_judge(...)` inside the request handler and `judge.evaluate(input, output)` on each call. Adds per-request cost and code complexity. Best for continuous live scoring of workflows where sampled auto-judges aren't enough. | Yes — all modes (the SDK handles both identically) |

   **Most migration users should start with offline eval**, then add programmatic direct-judge only if they need continuous live scoring after the rollout is stable.

2. **For agent-mode migrations, default to offline eval.** UI-attached auto judges are completion-mode only today. The documented path for agent mode is either (a) **offline regression** via the LD Playground + Datasets (works for all modes), or (b) **programmatic direct-judge** wired into the call site. Generate a starter dataset CSV from the audit manifest (one representative input per row) and point the user at `/tutorials/offline-evals` for the Playground walkthrough. Only wire programmatic direct-judge into production code if the user explicitly asks for continuous live scoring.

3. **Hand off to `aiconfig-online-evals`** — only for UI-attached judges (completion mode) or to create custom judge AI Configs that will be referenced by the programmatic path. Tell the user: *"Run `/aiconfig-online-evals` with these inputs, then come back here."* Do not auto-invoke. Pass:
   - The parent AI Config key and variation key
   - A list of built-in judges (Accuracy, Relevance, Toxicity) or custom judge keys to create/attach
   - Target environment

   The delegate handles creating custom judge AI Configs, attaching them via the variation PATCH endpoint, and setting fallthrough on each judge config. Offline eval does **not** go through this delegate — it's a Playground workflow, not an API write.

4. **For programmatic direct-judge: wire `create_judge` + `evaluate` + `track_eval_scores`.** This is the only path at Stage 5 that writes code. The correct shape:

   ```python
   from ldai.client import AIJudgeConfigDefault

   judge = await ai_client.create_judge(
       judge_key,                               # judge AI Config key in LD
       ld_context,
       AIJudgeConfigDefault(enabled=False),     # fallback: skip eval on SDK miss
   )

   if judge and judge.enabled:
       result = await judge.evaluate(
           input_text,
           output_text,
           sampling_rate=0.25,                  # optional; default 1.0 (always eval)
       )
       if result:
           config.tracker.track_eval_scores(result.evals)
   ```

   Three rules:
   - **`create_judge` returns `Optional[Judge]`.** Always guard with `if judge and judge.enabled:` — it returns `None` if the judge AI Config is disabled for the context or the provider is missing. A direct `.evaluate()` on a `None` return will raise `AttributeError`.
   - **Pass `AIJudgeConfigDefault`**, not `AICompletionConfigDefault`. The `create_judge` `default` parameter is typed `Optional[AIJudgeConfigDefault]`; passing the completion type will not type-check and is a doc-level bug in some older examples.
   - **`sampling_rate` is a parameter on `evaluate()`**, not on `create_judge`. It defaults to `1.0` (evaluate every call). For live paths, pass something lower (0.1–0.25) to control cost.

   **Ask the user which judge AI Config key to use.** LaunchDarkly ships three built-in judges — Accuracy, Relevance, Toxicity — but the actual AI Config **keys** for the built-ins are not canonical SDK constants and aren't documented. Have the user open **AI Configs > Library** in the LD UI and copy the key of the judge they want to reference, or create a custom judge AI Config via `aiconfig-create` first.

5. **Verify.**
   - **UI-attached auto judges:** trigger a request in staging, open the Monitoring tab → "Evaluator metrics" dropdown. Scores appear within 1–2 minutes at the configured sampling rate.
   - **Programmatic direct-judge:** hit the wrapped endpoint and confirm `track_eval_scores` lands on the parent config's Monitoring tab.
   - **Offline eval:** run the dataset through the LD Playground, compare baseline vs new-variation scores side by side. No runtime wiring required.

Delegate: **`aiconfig-online-evals`** (sub-step 3, optional — only for UI-attached judges or custom-judge creation; offline eval doesn't delegate).

## Edge Cases

| Situation | Action |
|-----------|--------|
| Hardcoded prompt uses f-string / template literal interpolation | Move interpolation into AI Config prompt variables `{{ variable }}`; pass values as the last argument to `completion_config` / `completionConfig` |
| App already initializes `LDClient` for feature flags | Reuse it — pass the existing client to `LDAIClient()` / `initAi()`, do not create a second client |
| App uses LangChain `ChatOpenAI(model=...)` | Read `config.model.name` and pass it as `ChatOpenAI(model=config.model.name)`; keep LangChain for the call itself |
| Retry wrapper around the provider call | Move tracker inside the retry — failures in the same request should share one `track_error`, and success tracking should fire only after the final attempt |
| App has no tools — Stage 3 skipped | Move directly from Stage 2 verification to Stage 4 (tracking) |
| Mode mismatch: user said agent, audit shows one-shot chat | Choose completion mode unless the app uses LangGraph `create_react_agent`, CrewAI `Agent`, or a similar goal-driven framework |
| TypeScript app using Anthropic SDK | No `trackAnthropicMetrics` helper exists — use manual `trackDuration` + `trackTokens` + `trackSuccess`/`trackError` (see the Step 5 manual block) |
| Fallback would silently crash because `LD_SDK_KEY` is missing | Log a startup warning; proceed with the fallback. Never raise at import time |
| Multi-agent graph (supervisor + workers) | Stop after migrating a single agent. Agent graphs are currently **Python-only** (`launchdarkly-server-sdk-ai.agent_graph`). Read [agent-graph-reference.md](references/agent-graph-reference.md) for the graph-level migration path — it is deliberately out of this skill's main scope |
| Single-agent (ReAct, tool loop) + agent mode | Default to offline eval via the LD Playground + Datasets for Stage 5. UI-attached judges are completion-only today, and programmatic direct-judge adds per-call cost that is usually not worth it until after the migration is live and stable. Point at `/tutorials/offline-evals` |
| Tool with a Pydantic `args_schema` (LangChain `@tool`) | Extract the schema via `tool.args_schema.model_json_schema()`; do not hand-write the JSON schema for the delegate |
| Custom `StateGraph` with module-level `TOOLS` list bound via `.bind_tools(TOOLS)` and run through `ToolNode(TOOLS)` (e.g. the `langchain-ai/react-agent` template) | Find the `TOOLS` list (usually in a separate `tools.py` module). Extract schemas the same way. Swap **both** call sites — `.bind_tools(...)` and `ToolNode(...)` — to read from the same `config.tools`-derived list |
| App has already externalized config into a `Context` dataclass with env-var fallback (e.g. `react-agent` template's `context.py`) | Good news — migration is a single-layer change. Replace the `Context` dataclass consumer (`runtime.context.model`, `runtime.context.system_prompt`) with a per-request `ai_client.agent_config(...)` call. Keep the dataclass as the fallback shape (it already mirrors the hardcoded values) |

## What NOT to Do

- Don't skip Step 1 even when the user says "just wrap it." Without the audit, the fallback will drift from the hardcoded behavior.
- Don't delegate to `aiconfig-create` before extracting the prompt and model — the delegate needs them as inputs.
- Don't try to attach tools during initial `setup-ai-config`. Tool attachment is a separate step owned by `aiconfig-tools`.
- Don't use `launchdarkly-metric-instrument` for Step 5. That skill is for `ldClient.track()` feature metrics, not AI `tracker.track_*` calls — they are different APIs.
- Don't wire evals before the tracker is in place. Judges score traffic; without Stage 4 traffic, there is nothing to judge.
- Don't frame Stage 5 as "either UI or programmatic." There are **three** paths: offline eval (recommended default for migration), UI-attached auto judges (completion-mode only), and programmatic direct-judge. Offline eval is the one most people skip and usually the right starting point.
- Don't pass `sampling_rate` to `create_judge` — it's a parameter on `Judge.evaluate()`, not `create_judge()`.
- Don't hardcode judge AI Config keys (`"accuracy-judge"`, `"relevance-judge"`, etc). The built-in keys are not canonical SDK constants; ask the user to look them up in **AI Configs > Library** in the LD UI.
- Don't forget the `if judge and judge.enabled:` guard after `create_judge`. It returns `Optional[Judge]` and returns `None` when the judge config is disabled for the context.
- Don't cache the config object across requests. Call `completion_config` / `completionConfig` on each request so LaunchDarkly can re-evaluate targeting.
- Don't delete the fallback once LaunchDarkly is wired up. It is required for the `enabled=False` and SDK-unreachable paths.
- Don't claim you "delegated to `aiconfig-create`" or any other sibling skill. This skill does not auto-invoke. At each handoff, print the inputs and tell the user to run the sibling slash-command, then wait. Anything else misleads the user about what just happened.
- Don't skip the `/aiconfig-targeting` step between Stage 2 and Stage 4. A freshly created variation returns `enabled=False` until targeting promotes it to fallthrough — Stage 2 verification will silently take the fallback path on every request.
- Don't attempt a multi-agent graph migration in one pass. Migrate a single agent first; use [agent-graph-reference.md](references/agent-graph-reference.md) as the next-step read.
- Don't use `track_request()` in Python — it does not exist in `launchdarkly-server-sdk-ai`. Use `track_duration()` + `track_success()`/`track_error()` explicitly, or prefer `track_openai_metrics` / `track_metrics_of` auto-helpers.
- Don't tuple-unpack the return of `completion_config` / `agent_config` / `completionConfig` / `agentConfig`. They return a **single** config object (e.g. `AIAgentConfig`, `AICompletionConfig`), not `(config, tracker)`. The tracker is at `config.tracker`. LLMs hallucinate the tuple shape because pre-v0.x SDKs used to return one — the current API does not.
- Don't import `LaunchDarklyCallbackHandler` from `ldai.langchain` — neither the class nor the dotted module path exists. The real Python LangChain helper package is `ldai_langchain` (top-level module, underscore), and it does not expose a single-node callback handler. For single-node LangChain calls, use manual tracker wiring with `response.usage_metadata` (see `references/sdk-ai-tracker-patterns.md`).

## Related Skills

- `aiconfig-create` — called by Stage 2 to create the config
- `aiconfig-tools` — called by Stage 3 to create and attach tool definitions
- `aiconfig-online-evals` — called by Stage 5 to attach judges
- `aiconfig-variations` — add variations for A/B testing after migration is complete
- `aiconfig-targeting` — roll out new variations to users after migration is complete
- `aiconfig-update` — modify config properties as your app evolves
- `launchdarkly-metric-instrument` — for `ldClient.track()` feature metrics (NOT for AI tracker calls)

## References

- [phase-1-analysis-checklist.md](references/phase-1-analysis-checklist.md) — Step 1 audit checklist, grep patterns, SDK routing table, mode decision tree
- [before-after-examples.md](references/before-after-examples.md) — Paired hardcoded-to-wrapped snippets for Python OpenAI, Node Anthropic, Python LangGraph
- [sdk-ai-tracker-patterns.md](references/sdk-ai-tracker-patterns.md) — Every `tracker.track_*` method in Python and Node side by side, auto-helper matrix, and common gotchas
- [agent-mode-frameworks.md](references/agent-mode-frameworks.md) — How to wire `agent_config` into LangGraph, CrewAI, and custom react loops; dynamic tool loading pattern
- [fallback-defaults-pattern.md](references/fallback-defaults-pattern.md) — Three fallback patterns (inline, file-backed, bootstrap-generated) and when to use each
- [agent-graph-reference.md](references/agent-graph-reference.md) — Out-of-scope pointer doc for multi-agent migrations
