---
name: aiconfig-ai-metrics
description: "Instrument an existing codebase with LaunchDarkly AI Config tracking. Walks the four-tier ladder (managed runner → provider package → custom extractor + trackMetricsOf → raw manual) and picks the lowest-ceremony option that still captures duration, tokens, and success/error."
license: Apache-2.0
compatibility: Requires the LaunchDarkly server-side AI SDK (`launchdarkly-server-sdk-ai` for Python or `@launchdarkly/server-sdk-ai` for Node) and an existing AI Config.
metadata:
  author: launchdarkly
  version: "1.0.0-experimental"
---

# AI Metrics Instrumentation

You're using a skill that wires LaunchDarkly AI metrics around an existing provider call. Your job is to audit what's already there, pick the right tier from the ladder below, and implement it with the **least ceremony that still captures the metrics the Monitoring tab needs** (duration, input/output tokens, success/error, plus TTFT when streaming).

The single most important thing to get right: **default to the highest tier that fits the shape of the call**. Going lower ("just write the manual tracker calls") looks flexible but costs you drift, missed metrics, and legacy patterns the SDKs have moved past.

## The four-tier ladder

This is the order the official SDK READMEs (Python core, Node core, and every provider package) recommend. Walk from the top and stop at the first tier that fits:

| Tier | Pattern | Use when | Tracks automatically |
|------|---------|----------|----------------------|
| **1 — Managed runner** | Python: `ai_client.create_model(...)` returning a `ManagedModel`, then `await model.invoke(...)`. <br>Node: `aiClient.initChat(...)` / `aiClient.createChat(...)` returning a `TrackedChat`, then `await chat.invoke(...)`. | The call is conversational (chat history, turn-based). This is what the provider READMEs lead with. | Duration, tokens, success/error — **all of it, zero tracker calls**. |
| **2 — Provider package + `trackMetricsOf`** | `tracker.trackMetricsOf(Provider.getAIMetricsFromResponse, () => providerCall())`. Provider packages today: `@launchdarkly/server-sdk-ai-openai`, `-langchain`, `-vercel` (Node) and `launchdarkly-server-sdk-ai-openai`, `-langchain` (Python). | The shape isn't a chat loop (one-shot completion, structured output, agent step) but the framework or provider has a package. | Duration + success/error from the wrapper; tokens from the package's built-in `getAIMetricsFromResponse` extractor. |
| **3 — Custom extractor + `trackMetricsOf`** | Same `trackMetricsOf` wrapper, but you write a small function that maps the provider response to `LDAIMetrics` (tokens + success). | No provider package exists (Anthropic direct, Gemini, Cohere, custom HTTP). | Duration + success/error from the wrapper; tokens from your extractor. |
| **4 — Raw manual** | Separate calls to `trackDuration`, `trackTokens`, `trackSuccess` / `trackError`, plus `trackTimeToFirstToken` for streams. | Streaming with TTFT, unusual response shapes, partial tracking, anything Tier 2–3 can't cleanly wrap. | Only what you explicitly call — it's on you to not miss one. |

A call to `track_openai_metrics` / `trackOpenAIMetrics` / `track_bedrock_converse_metrics` / `trackBedrockConverseMetrics` / `trackVercelAISDKGenerateTextMetrics` is **Tier-2 legacy shorthand**. These helpers still exist in the SDK source but none of the current provider READMEs use them — they've been superseded by `trackMetricsOf` + `Provider.getAIMetricsFromResponse`. Do not recommend them for new code; if you see them in an existing codebase, leave them alone unless the user is already on a cleanup pass.

## Workflow

### 1. Explore the existing call site

Before picking a tier, find the provider call and answer these questions:

- [ ] **Shape?** Is it a chat loop (history + turn-based), a one-shot completion, an agent step, or something else? → drives Tier 1 vs 2.
- [ ] **Framework?** Raw provider SDK? LangChain / LangGraph? Vercel AI SDK? CrewAI? Strands? → drives which Tier-2 provider package (if any) applies.
- [ ] **Provider?** OpenAI, Anthropic, Bedrock, Gemini, Azure, custom HTTP? → cross-reference with the package availability matrix below.
- [ ] **Streaming?** If yes, you'll need TTFT tracking, which means Tier 4 for the TTFT part even if the rest is Tier 2.
- [ ] **Language?** Python or Node? Provider-package coverage differs between them.
- [ ] **Already using an AI Config?** If not, route to `aiconfig-create` first — tracking requires a tracker, which comes from `completion_config()` / `completionConfig()` / `initChat()`.

### 2. Look up your Tier-2 option

Use this matrix to decide whether Tier 2 (provider package) is available for your situation. If it's not, drop to Tier 3 (custom extractor). If the shape is chat-loop, go to Tier 1 first regardless of what's in this matrix.

| Framework / provider | Python provider package | Node provider package | Reference |
|---|---|---|---|
| OpenAI (direct SDK) | `launchdarkly-server-sdk-ai-openai` | `@launchdarkly/server-sdk-ai-openai` | [openai-tracking.md](references/openai-tracking.md) |
| LangChain / LangGraph | `launchdarkly-server-sdk-ai-langchain` | `@launchdarkly/server-sdk-ai-langchain` | [langchain-tracking.md](references/langchain-tracking.md) |
| Vercel AI SDK | — | `@launchdarkly/server-sdk-ai-vercel` | (use the Vercel provider docs) |
| AWS Bedrock (Converse or InvokeModel) | — (use LangChain-aws or custom extractor) | — (use LangChain-aws or custom extractor) | [bedrock-tracking.md](references/bedrock-tracking.md) |
| Anthropic direct SDK | — | — | [anthropic-tracking.md](references/anthropic-tracking.md) |
| Gemini / Google GenAI | — | — | [gemini-tracking.md](references/gemini-tracking.md) |
| Strands Agents | — (Tier 3 custom extractor) | — (Tier 3 custom extractor) | [strands-tracking.md](references/strands-tracking.md) |
| Cohere, Mistral, custom HTTP | — | — | Tier 3 custom extractor |
| **Any provider, streaming + TTFT** | — (Tier 4 only) | `trackStreamMetricsOf` (no TTFT) + manual TTFT | [streaming-tracking.md](references/streaming-tracking.md) |

### 3. Implement from the matching reference

Once you know the tier and the provider, open the reference file and follow the pattern. The references are written so Tier 1 is always the first example, Tier 2/3 next, and Tier 4 last. Stop at the first tier that matches the app's shape.

Guardrails that apply to every tier:

1. **Always check `config.enabled`** before making the tracked call. A disabled config means the user has flagged the feature off — you should short-circuit to whatever fallback the app uses (cached response, error, degraded path) rather than making the provider call at all.
2. **Wrap the existing call, don't rewrite it.** Tier 2 and Tier 3 are designed to slot around an unmodified provider call. If you find yourself rewriting the call to fit the tracker, you're at the wrong tier — drop down one.
3. **Errors go through the tracker too.** `trackMetricsOf` handles the success path; errors still need an explicit `tracker.trackError()` in the catch block (or a try/except around the whole thing). Tier 1 handles both paths automatically.
4. **Always flush before close.** Call `ldClient.flush()` (Python: `ldclient.get().flush()`; Node: `await ldClient.flush()`) before closing the client. Trailing events are at risk of being lost otherwise — in short-lived scripts and long-running services alike. In Node, `ldClient.close()` returns a Promise; await it.

### 4. Verify

Confirm the Monitoring tab fills in:

- [ ] Run one real request through the instrumented path.
- [ ] Open the AI Config in LaunchDarkly → **Monitoring** tab. Duration, token counts, and generation counts should appear within 1–2 minutes.
- [ ] Force an error (bad API key, zero `max_tokens`, whatever) and confirm the error count increments.
- [ ] If streaming: verify TTFT appears. If it doesn't, you probably wrapped the stream creation with `trackMetricsOf` but didn't add the manual `trackTimeToFirstToken` call — see [streaming-tracking.md](references/streaming-tracking.md).

## Quick reference: tracker methods

The tracker object (`config.tracker` / `aiConfig.tracker`) provides these methods. This is the raw API surface — most of the time you should not call the individual methods, you should use `trackMetricsOf` or a Tier-1 managed runner. The list is here so you can recognize the methods in existing code and reach for the right one when you genuinely need Tier 4.

| Method (Python ↔ Node) | Tier | What it does |
|---|---|---|
| `track_metrics_of(func, extractor)` (Python) / `trackMetricsOf(extractor, fn)` (Node) | **2 / 3** | Wraps a provider call, captures duration + success/error, calls your extractor for tokens. **This is the default generic tracker.** Note the Python and Node arg orders are reversed. |
| `track_metrics_of_async(func, extractor)` (Python) | 2 / 3 | Async variant of the above. Python: `func, extractor`. |
| `trackStreamMetricsOf(extractor, streamFn)` (Node only) | 2 / 3 | Streaming variant. Captures per-chunk usage when the extractor handles chunks. Does **not** auto-capture TTFT. |
| `track_duration(ms)` / `trackDuration(ms)` | 4 | Record latency in milliseconds. |
| `track_duration_of(fn)` / `trackDurationOf(fn)` | 4 | Wraps a callable and records duration automatically. Does not capture tokens or success — pair with explicit calls. |
| `track_tokens(TokenUsage)` / `trackTokens({input, output, total})` | 4 | Record token usage. |
| `track_time_to_first_token(ms)` / `trackTimeToFirstToken(ms)` | 4 | Record TTFT for streaming responses. |
| `track_success()` / `trackSuccess()` | 4 | Mark the generation as successful. Required for the Monitoring tab to count it. |
| `track_error()` / `trackError()` | 4 | Mark the generation as failed. Do not also call `trackSuccess()` in the same request. |
| `track_feedback({kind})` / `trackFeedback({kind})` | any | Record thumbs-up / thumbs-down from a feedback UI. Independent of the success/error path. |
| `track_openai_metrics(fn)` / `trackOpenAIMetrics(fn)` | **legacy** | Predates provider packages. Still works; do not use in new code. Replace with `trackMetricsOf(OpenAIProvider.getAIMetricsFromResponse, fn)`. |
| `track_bedrock_converse_metrics(res)` / `trackBedrockConverseMetrics(res)` | **legacy** | Same story. Do not use in new code. |
| `trackVercelAISDKGenerateTextMetrics(fn)` (Node) | **legacy** | Same story. Use `trackMetricsOf` with the Vercel provider package's extractor. |

## Related skills

- `aiconfig-create` — prerequisite if the app doesn't have an AI Config yet
- `aiconfig-custom-metrics` — business metrics (conversion, resolution, retention) layered on top of the AI metrics this skill captures
- `aiconfig-online-evals` — automatic quality scoring (LLM-as-judge) on sampled live requests; complementary to the metrics here
- `aiconfig-migrate` — Stage 4 of the hardcoded-to-AI-Configs migration delegates to this skill
