# Phase 1 Analysis Checklist

A read-only audit the skill runs in **Step 1** before touching any code. Do not write files, install packages, or create LaunchDarkly resources during this phase. Produce a structured summary and stop for user confirmation.

## What to scan

### 1. Dependency manifests (most reliable signal)

Check the top-level files for the target service:

| Language | Files |
|----------|-------|
| Python | `pyproject.toml`, `requirements.txt`, `setup.py`, `Pipfile`, `uv.lock` |
| TypeScript / JavaScript | `package.json`, `pnpm-lock.yaml`, `yarn.lock` |
| Go | `go.mod`, `go.sum` |
| Ruby | `Gemfile`, `Gemfile.lock` |
| .NET | `*.csproj`, `packages.config` |

Extract: language, package manager, and any LLM provider SDKs already installed.

### 2. Provider imports

Grep the source tree for provider SDK imports so you know which one the app actually uses (dependencies can be unused):

| Provider | Python grep | TypeScript/JS grep |
|----------|-------------|---------------------|
| OpenAI | `from openai`, `import openai` | `from 'openai'`, `require('openai')` |
| Anthropic | `from anthropic`, `import anthropic` | `from '@anthropic-ai/sdk'` |
| Bedrock | `import boto3`, `bedrock-runtime` | `@aws-sdk/client-bedrock-runtime` |
| Gemini | `from google import genai`, `google.generativeai` | `@google/generative-ai` |
| LangChain | `from langchain`, `langchain_openai`, `langchain_anthropic` | `langchain`, `@langchain/openai` |
| LangGraph | `from langgraph`, `create_react_agent` | `@langchain/langgraph` |
| CrewAI | `from crewai` | — |

### 3. Hardcoded model configs

Look for the three things that need to move into the AI Config:

1. **Model name** — grep for string literals:
   - `"gpt-4o"`, `"gpt-4o-mini"`, `"gpt-4-turbo"`, `"o1"`, `"o1-mini"`
   - `"claude-opus-"`, `"claude-sonnet-"`, `"claude-haiku-"`, `"claude-3-"`
   - `"gemini-"`, `"mistral-"`, `"meta.llama"`, `"anthropic.claude-"`
2. **Parameters** — grep for keys: `temperature=`, `max_tokens=`, `maxTokens:`, `top_p=`, `topP:`, `top_k=`, `stop_sequences=`
3. **System prompts / instructions** — grep for:
   - `"role": "system"` (OpenAI/Anthropic completion)
   - `system="` or `system:` (Anthropic top-level system)
   - `instructions="` (agent frameworks, CrewAI, LangGraph `create_react_agent(prompt=)`)
   - Long triple-quoted strings above provider calls

For each hit, record the file path, line number, and current value.

### 4. Template placeholders in prompts

Anything the app currently interpolates into a prompt at runtime must be rewritten to Mustache `{{ variable }}` syntax in Stage 2 so the fallback path renders identically to the LD-served path. Grep for:

| Shape | Example | Grep |
|-------|---------|------|
| Python `.format()` | `PROMPT.format(system_time=now)` | `\.format(` on lines near prompt constants |
| Python f-string in a prompt constant | `f"You are... {system_time}."` | `f"` at the start of prompt literals |
| Python printf-style | `"%(topic)s"` / `"%s"` with `%` substitution | `%(` in prompt strings |
| JS/TS template literals in prompt strings | `` `You are... ${var}.` `` | backtick-wrapped prompt constants |
| Hand-rolled `str.replace` | `PROMPT.replace("__VAR__", value)` | `\.replace(` on prompt strings |

Record placeholder name + where the runtime value comes from (env var, function arg, `datetime.now()`, etc.). These get routed through `variables={...}` on `completion_config` / `agent_config` calls in Stage 2, and the literal prompt string gets rewritten to `{{ placeholder }}`. Leaving a non-Mustache placeholder in the fallback is a silent regression mode: LaunchDarkly-served prompts interpolate correctly, the fallback ships unrendered.

### 5. Hardcoded app-scoped knobs

Configuration that governs *tool* or *app* behavior rather than *model* behavior — easy to miss in an audit because it looks like ordinary application config. Common shapes:

- `Context` / `Settings` dataclass fields referenced by tools (`max_search_results`, `chunk_size`, `retry_budget`, `timeout_ms`, `enable_reranking`)
- Environment variables read inside tool implementations
- Constants declared in `tools.py` or a config module that a tool reads at call time

If a value changes agent behavior between variations — it belongs in the AI Config. Stage 2 sub-step 5 (fallback) puts these in `ModelConfig(custom={...})`, **not** `parameters` (which is forwarded to the provider SDK and will crash on unknown kwargs). Tools read them via `ai_config.model.get_custom("key")`.

### 6. Existing LaunchDarkly SDK usage

If `LDClient` / `ldclient` is already initialized in the codebase, **reuse it** — do not create a second base client in Stage 2. Grep for:

- Python: `import ldclient`, `ldclient.set_config`, `ldclient.get()`
- TypeScript/JS: `@launchdarkly/node-server-sdk`, `init(LD_SDK_KEY)`, `@launchdarkly/react-client-sdk`
- Environment variables: `LD_SDK_KEY`, `LAUNCHDARKLY_SDK_KEY`, `LAUNCHDARKLY_API_KEY`

### 7. Mode decision: completion or agent

Walk the decision tree once per call site, using the call shape as the primary signal:

| Call shape | Mode |
|------------|------|
| `openai.chat.completions.create(messages=[...])` | **completion** |
| `anthropic.messages.create(system=..., messages=[...])` | **completion** |
| `bedrock.converse(messages=[...])` | **completion** |
| `create_react_agent(llm, tools, prompt=...)` | **agent** |
| `Agent(role=..., goal=..., backstory=...)` (CrewAI) | **agent** |
| Custom react loop: LLM-call → tool-call → LLM-call | **agent** |
| One-shot `llm.invoke("some question")` | **completion** |

**Default to completion mode** when unclear — it is more flexible and is the only mode that supports judges attached via the LaunchDarkly UI (Stage 5).

### 8. Monorepo / multi-service scope

If the repo contains multiple services, **ask the user which service to instrument**. Do not migrate every service in one pass.

## SDK routing table

Feeds into Stage 2 (install + wrap). Quoted from the `ai-configs-relaunch-guides/AGENT-SETUP-PROMPT.md` SDK routing table.

| Language | Base SDK | AI SDK | Docs |
|----------|----------|--------|------|
| Node.js / TypeScript | `@launchdarkly/node-server-sdk` | `@launchdarkly/server-sdk-ai` | https://docs.launchdarkly.com/sdk/ai/node-js |
| Python | `launchdarkly-server-sdk` | `launchdarkly-server-sdk-ai` | https://docs.launchdarkly.com/sdk/ai/python |
| Go | `github.com/launchdarkly/go-server-sdk/v7` | `github.com/launchdarkly/go-server-sdk/ldai` | https://docs.launchdarkly.com/sdk/ai/go |
| Ruby | `launchdarkly-server-sdk` | `launchdarkly-server-sdk-ai` | https://docs.launchdarkly.com/sdk/ai/ruby |
| .NET | `LaunchDarkly.ServerSdk` | `LaunchDarkly.ServerSdk.Ai` | https://docs.launchdarkly.com/sdk/ai/dotnet |

**Node.js provider-specific helper packages** (optional, for auto-tracking in Stage 4):

| Provider | Package | Helper |
|----------|---------|--------|
| OpenAI | `@launchdarkly/server-sdk-ai-openai` | `OpenAIProvider.getAIMetricsFromResponse` + `trackMetricsOf` |
| LangChain / LangGraph | `@launchdarkly/server-sdk-ai-langchain` | `LangChainProvider.createLangChainModel(config)` (forwards all variation parameters and handles provider-name mapping) + `LangChainProvider.getAIMetricsFromResponse` with `trackMetricsOf` |
| Vercel AI SDK | `@launchdarkly/server-sdk-ai-vercel` | `VercelAISDKProvider.getAIMetricsFromGenerateText` + `trackMetricsOf` |

Python currently ships helper packages for OpenAI (`ldai_openai`) and LangChain (`ldai_langchain`). The LangChain Python package exposes `create_langchain_model(config)` (builds a LangChain chat model from the AI Config, forwarding every variation parameter and mapping LD provider names to LangChain equivalents), `convert_messages_to_langchain`, and `get_ai_metrics_from_response` — the same package covers LangGraph. Use `create_langchain_model(config)` + `track_metrics_of_async(lambda: llm.ainvoke(messages), get_ai_metrics_from_response)` as the canonical single-call pattern. See [langchain-tracking.md](../../aiconfig-ai-metrics/references/langchain-tracking.md) for both LangChain and LangGraph patterns and [sdk-ai-tracker-patterns.md](sdk-ai-tracker-patterns.md) for the full tracker-method matrix.

## Phase 1 output format

Return this shape to the user, then **stop and wait for confirmation**:

```
Service:             <service name / path>
Language:            <Python 3.12 / Node.js 20 / Go 1.22 / ...>
Package manager:     <uv / poetry / pnpm / go mod / ...>
LLM provider:        <OpenAI / Anthropic / Bedrock / LangChain + OpenAI / ...>
Existing LD SDK:     <none / launchdarkly-server-sdk already initialized at src/ld.py:12>
Target mode:         <completion / agent>

Hardcoded migration targets:
  - <file>:<line>   model="gpt-4o"
  - <file>:<line>   temperature=0.7, max_tokens=2000
  - <file>:<line>   system="You are... {system_time}"  (27 lines, Python .format placeholder)

Template placeholders:  [{system_time} (Python .format, source=datetime.now().isoformat())]
App-scoped knobs:       [Context.max_search_results=10 (tools.py:24, reads from runtime.context)]
Tools detected:         <none / ['search', 'calculator'] at file.py:LN>
Retry wrapper:          <none / @retry(3) at file.py:LN>
Scope:                  <single service / monorepo: picked "service-x">

Proposed plan:
  Stage 1 (Extract):  Build manifest from the 3 targets above; flag placeholders for Mustache rewrite and knobs for model.custom
  Stage 2 (Wrap):     Create AI Config 'chat-assistant' in completion mode; inline fallback mirrors current values (Mustache syntax)
  Stage 3 (Tools):    Skipped (no function calling) / Attach 2 tools via aiconfig-tools
  Stage 4 (Tracking): Inline tracker wiring (track_duration + track_tokens + track_success/error) — run-scoped tracker for agent loops
  Stage 5 (Evals):    Attach built-in 'accuracy' judge at 0.25 sampling via aiconfig-online-evals
```

## STOP

Do not proceed to Stage 1 (Step 2 in the main workflow) until the user confirms:

1. The service boundary is right
2. The hardcoded targets list is complete
3. The mode choice matches their intent
4. The stage plan is acceptable (e.g. skip tools? skip evals for now?)

If the user corrects anything, update the summary and ask again. Do not proceed under ambiguity.
