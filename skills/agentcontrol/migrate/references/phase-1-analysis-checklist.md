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
| LangGraph | `from langgraph`, `from langchain.agents import create_agent`, `create_react_agent` (deprecated) | `@langchain/langgraph`, `createReactAgent` |
| CrewAI | `from crewai` | — |

### 3. Hardcoded model configs

Look for the three things that need to move into the config:

1. **Model name** — grep for string literals:
   - `"gpt-4o"`, `"gpt-4o-mini"`, `"gpt-4-turbo"`, `"o1"`, `"o1-mini"`
   - `"claude-opus-"`, `"claude-sonnet-"`, `"claude-haiku-"`, `"claude-3-"`
   - `"gemini-"`, `"mistral-"`, `"meta.llama"`, `"anthropic.claude-"`
2. **Parameters** — grep for keys: `temperature=`, `max_tokens=`, `maxTokens:`, `top_p=`, `topP:`, `top_k=`, `stop_sequences=`
3. **System prompts / instructions** — grep for:
   - `"role": "system"` (OpenAI/Anthropic completion)
   - `system="` or `system:` (Anthropic top-level system)
   - `instructions="` (agent frameworks, CrewAI, LangGraph Python `create_agent(system_prompt=)` or legacy `create_react_agent(prompt=)`, LangGraph.js `createReactAgent({ prompt })`)
   - Long triple-quoted strings above provider calls

For each hit, record the file path, line number, and current value.

### 4. External prompt files & registries

Prompts often live outside `.py` / `.ts` source. **Open every plausible config file and read it before declaring the audit complete** — code-only grep will miss prompts loaded from YAML, prompt-template registries, or framework-specific manifests, and the resulting config will not cover the real prompt surface area.

**File-extension scan targets** (run from repo root):

- `**/*.yaml`, `**/*.yml`
- `**/*.json` (exclude `package.json`, `package-lock.json`, `tsconfig.json`, `*.lock`)
- `**/*.toml` (exclude `pyproject.toml` already covered in §1)
- `**/*.md` under `prompts/`, `templates/`, `agents/`, `personas/`
- `**/*.prompt`, `**/*.prompty`, `**/*.j2`, `**/*.jinja`, `**/*.tmpl`

**Content signals to grep inside those files**:

- Keys named `system`, `system_prompt`, `instructions`, `prompt`, `template`, `role`, `goal`, `backstory`, `persona`, `messages`
- Mustache (`{{ }}`) or Jinja (`{% %}`) blocks suggesting a prompt template
- Long multi-line string values (>200 chars) under any of those keys

**Framework-specific shapes to call out by name**:

| Framework | Where prompts live |
|-----------|---------------------|
| **CrewAI** | `agents.yaml` and `tasks.yaml` carry `role` / `goal` / `backstory` / `description` / `expected_output` per agent or task |
| **LangChain** | `.prompt` files (Promptfile format); any `langchain.hub.pull("name/key")` call — pulled prompts are remote and must either be inlined into the config or replaced with a `messages` array sourced from the hub at audit time |
| **LangSmith** | `client.pull_prompt(...)` calls referencing a remote prompt repo |
| **Pydantic / Settings** | classes with `prompt_*` fields backed by env vars or YAML overlays (Hydra / OmegaConf / Dynaconf) |
| **Helm / k8s ConfigMap** | prompts stored as values overrides — search `values*.yaml` and `templates/*configmap*.yaml` |

**For each hit, record**: file path, line range, the key holding the prompt, the loader call site that reads it, and any template placeholder syntax (Mustache vs Jinja vs Python `.format()`). The placeholder rewrite in Stage 2 sub-step 5 needs to know the source syntax to convert it to `{{name}}`.

If the app already loads a fallback config file at startup, distinguish it from prompts that flow into the provider call. Only the latter migrates into the config; the fallback stays as the code path that runs when `invoke()` raises (see [fallback-defaults-pattern.md](fallback-defaults-pattern.md)).

### 5. Template placeholders in prompts

Anything the app currently interpolates into a prompt at runtime must be rewritten to `{{variable}}` syntax, with no spaces inside the braces, in Stage 2. The SDK fills only `{{name}}` and `{{dotted.name}}`; `{{ name }}` reaches the model as literal text. Grep for:

| Shape | Example | Grep |
|-------|---------|------|
| Python `.format()` | `PROMPT.format(system_time=now)` | `\.format(` on lines near prompt constants |
| Python f-string in a prompt constant | `f"You are... {system_time}."` | `f"` at the start of prompt literals |
| Python printf-style | `"%(topic)s"` / `"%s"` with `%` substitution | `%(` in prompt strings |
| JS/TS template literals in prompt strings | `` `You are... ${var}.` `` | backtick-wrapped prompt constants |
| Hand-rolled `str.replace` | `PROMPT.replace("__VAR__", value)` | `\.replace(` on prompt strings |
| Mustache or Jinja with spaces | `{{ user_name }}` | `\{\{ ` and ` \}\}` |
| Legacy context variable | `{{ldctx.name}}` | `ldctx` |

Record placeholder name + where the runtime value comes from (env var, function arg, `datetime.now()`, etc.). In Stage 2 these values are passed as the third argument to `invoke()`, and the prompt in the config is written as `{{placeholder}}`. Context attributes are available as `{{ldContext.attr}}`; the legacy name `ldctx` is not filled. A placeholder that isn't rewritten is a silent failure: the model receives the literal braces.

### 6. Hardcoded app-scoped knobs

Configuration that governs *tool* or *app* behavior rather than *model* behavior — easy to miss in an audit because it looks like ordinary application config. Common shapes:

- `Context` / `Settings` dataclass fields referenced by tools (`max_search_results`, `chunk_size`, `retry_budget`, `timeout_ms`, `enable_reranking`)
- Environment variables read inside tool implementations
- Constants declared in `tools.py` or a config module that a tool reads at call time

If a value changes agent behavior between variations, it belongs in the config's `model.custom`, **not** `model.parameters`. Handler packages forward parameters to the provider SDK, which rejects unknown keys. A custom handler reads knobs from `ld_config["model"].get("custom", {})`; code outside a handler reads them from `(await inspect_config(key, context))["config"]["model"]["custom"]`. Keep the current values as defaults in code so the fallback path behaves the same.

### 7. Existing LaunchDarkly SDK usage

If `LDClient` / `ldclient` is already initialized in the codebase, **reuse it**: pass it to `init_client(client=ldclient.get())` in Python or `initClient(ldClient)` in Node.js rather than creating a second client. Grep for:

- Python: `import ldclient`, `ldclient.set_config`, `ldclient.get()`
- TypeScript/JS: `@launchdarkly/node-server-sdk`, `init(LD_SDK_KEY)`, `@launchdarkly/react-client-sdk`
- Environment variables: `LD_SDK_KEY`, `LAUNCHDARKLY_SDK_KEY`, `LAUNCHDARKLY_API_KEY`. The AI SDK reads `LD_SDK_KEY`; flag any other name for renaming or explicit passing.
- Legacy AI SDK: `from ldai`, `LDAIClient`, `@launchdarkly/server-sdk-ai`, `completion_config`, `completionConfig`, `agent_config`, `create_tracker`, `createTracker`, `track_metrics_of`, `trackMetricsOf`. Every hit is a Stage 1 target.

### 8. Mode decision: completion or agent

Walk the decision tree once per call site, using the call shape as the primary signal:

| Call shape | Mode |
|------------|------|
| Direct provider call with `messages=[...]` (OpenAI, Anthropic, Bedrock Converse) | **completion** |
| `create_agent(llm, tools, system_prompt=...)` (Python, `langchain.agents`) or `create_react_agent(llm, tools, prompt=...)` (Python, deprecated) | **agent** |
| `createReactAgent({ llm, tools, prompt })` (Node, `@langchain/langgraph/prebuilt`) | **agent** |
| CrewAI `Agent(role=..., goal=..., backstory=...)` | **agent** |
| Custom react loop: LLM-call → tool-call → LLM-call | **agent** |

**Default to completion mode** when unclear. A completion-mode handler still runs tool loops when tools are attached, and judges can be attached to configs in either mode (Stage 5).

### 9. Monorepo / multi-service scope

If the repo contains multiple services, **ask the user which service to instrument**. Do not migrate every service in one pass.

## SDK routing table

Feeds into Stage 2 (install + wrap). The current AI SDKs exist for Python and Node.js.

| Language | Core package | Docs |
|----------|--------------|------|
| Python | `launchdarkly-ai-server` (bundles `launchdarkly-server-sdk`) | https://launchdarkly.com/docs/sdk/ai/python |
| Node.js / TypeScript | `@launchdarkly/ai-node` (bundles `@launchdarkly/node-server-sdk`) | https://launchdarkly.com/docs/sdk/ai/node-js |
| Go, Ruby, .NET | Legacy AI SDKs only; out of scope for this skill | https://launchdarkly.com/docs/sdk/ai |

**Handler packages.** Pick one per provider and mode found in §2 and §8. Python names start with `launchdarkly-ai-`; Node.js names start with `@launchdarkly/ai-`.

| Provider in the app | Completion mode | Agent mode |
|---|---|---|
| OpenAI | `openai-messages` | `openai-agents` |
| Anthropic | `claude-messages` | `claude-agents` |
| LangChain / LangGraph, any model | `langchain-messages` | `langchain-agents` |
| Bedrock, Gemini, Vertex | `langchain-messages` with a model factory, or a custom handler | `langchain-agents`, or a custom agent handler |
| Azure OpenAI, LiteLLM, custom HTTP, other frameworks | Custom handler with `create_handler` / `createHandler` | Custom agent handler |

No handler factory accepts a pre-built provider client, so any app that configures its client specially (Azure endpoints, proxies, custom base URLs) needs a custom handler that reuses that client. See [sdk-ai-tracker-patterns.md](sdk-ai-tracker-patterns.md) for what the SDK records and the `built-in-metrics` skill's per-provider references for handler code.

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

Externalized prompt files:   <none / 3 files: prompts/agents.yaml (CrewAI), prompts/system.md, config/prompts.json>
Prompt-template registries:  <none / langchain.hub.pull("rlm/rag-prompt") at app.py:14>
Template placeholders:       [{system_time} (Python .format, source=datetime.now().isoformat())]
App-scoped knobs:            [Context.max_search_results=10 (tools.py:24, reads from runtime.context)]
Tools detected:              <none / ['search', 'calculator'] at file.py:LN>
Retry wrapper:               <none / @retry(3) at file.py:LN>
Scope:                       <single service / monorepo: picked "service-x">

Coverage totals:             N hardcoded code targets · M externalized prompt files · K registry pulls

Proposed plan:
  Stage 1 (Audit):    Read-only manifest of hardcoded targets; flag placeholders for {{name}} rewrite and knobs for model.custom
  Stage 2 (Wrap):     Install SDK + OpenAI handler package, create config 'chat-assistant', route the call through invoke(), keep the original call as fallback
  Stage 3 (Tools):    Skipped (no function calling) / Attach 2 tools via tools, pass tool_handlers
  Stage 4 (Metrics):  Confirm automatic metrics on the Monitoring tab; add thumbs-up/down feedback events
  Stage 5 (Evals):    Attach built-in 'accuracy' judge at 0.25 sampling via online-evals
```

## STOP

Do not proceed to Stage 2 until the user confirms all of:

1. The service boundary is right
2. The hardcoded targets list is complete
3. The mode choice matches their intent
4. The stage plan is acceptable (e.g. skip tools? skip evals for now?)
5. **Coverage check.** State the totals out loud: "I scanned the repo and found **N** hardcoded code targets, **M** externalized prompt files, and **K** registry pulls. If you expected more (e.g. you know there's a `prompts/` directory, a CrewAI `agents.yaml`, or a config service I didn't reach), tell me where to look before we proceed." A number the user can react to surfaces under-detection that a yes/no on a list cannot.

**Reply with one of:**

- **`confirm`** — the audit looks complete; proceed to Stage 2.
- **`add: <files or paths>`** — I missed something; here's where to look. (Re-run the audit with the new locations and present an updated summary.)
- **`fix: <correction>`** — a target in the list is wrong (provider, mode, prompt content, etc.). (Update the summary and ask again.)
- **`stop`** — pause the migration here.

Do not interpret any other word — including `skip`, `next`, `go`, `ok`, `proceed` — as confirmation. If the reply doesn't match one of the four forms above, ask the user to pick one. Do not proceed under ambiguity.
