# SDK AI Tracker Patterns

The main novel content of this skill — a per-method reference for the LaunchDarkly AI Config tracker in Python and Node side by side. **No existing skill covers this.** The `launchdarkly-metric-instrument` skill is for `ldClient.track()` feature metrics, which is a different API.

All method names and signatures below are verified against `launchdarkly-server-sdk-ai` (Python) and `@launchdarkly/server-sdk-ai` (`js-core/packages/sdk/server-ai`) main branches. If a method is not listed, it does not exist — do not invent it.

## Two tracker classes

| Class | Where it lives | When you use it |
|-------|----------------|-----------------|
| `LDAIConfigTracker` (Python) / `LDAIConfigTracker` (Node) | Attached to each AI Config object as `config.tracker` / `aiConfig.tracker` | **Per-request tracking.** Call from inside your request handler, around the provider call. This is the one this skill wires in Stage 4. |
| `AIGraphTracker` (Python only) | Returned from `graph.get_tracker()` after `ai_client.agent_graph(key, context)` | **Graph-level tracking.** Covers path, handoffs, total tokens, latency for a multi-node traversal. See [agent-graph-reference.md](agent-graph-reference.md). Python-only — Node SDK has no graph support yet. |

This doc focuses on `LDAIConfigTracker`. For `AIGraphTracker`, see the graph reference.

## Config tracker methods — Python ↔ Node

### `track_success` / `trackSuccess`

Record a successful generation. Required — the Monitoring tab does not populate without it.

```python
config.tracker.track_success()
```
```typescript
aiConfig.tracker.trackSuccess();
```

No arguments. Call once per request after the provider call returns.

### `track_error` / `trackError`

Record a failed generation. Required for error-rate metrics.

```python
config.tracker.track_error()
```
```typescript
aiConfig.tracker.trackError();
```

Call from the exception path. Do not also call `track_success` in the same request.

### `track_duration` / `trackDuration`

Record latency in milliseconds. Measure wall-clock time across the provider call.

```python
import time
start = time.time()
response = openai_client.chat.completions.create(...)
config.tracker.track_duration(int((time.time() - start) * 1000))
```
```typescript
const start = Date.now();
const response = await openai.chat.completions.create(/* ... */);
aiConfig.tracker.trackDuration(Date.now() - start);
```

**Python note:** there is no `track_request()` context-manager method on `LDAIConfigTracker`. Some older guides show it; it does not exist. Use `track_duration` + `track_success`/`track_error` explicitly, or use `track_duration_of` / `track_metrics_of` (below) which wrap the whole thing.

### `track_tokens` / `trackTokens`

Record token usage. The shape is `(input, output, total)` in both SDKs.

```python
from ldai.tracker import TokenUsage

config.tracker.track_tokens(TokenUsage(
    input=response.usage.prompt_tokens,
    output=response.usage.completion_tokens,
    total=response.usage.total_tokens,
))
```
```typescript
aiConfig.tracker.trackTokens({
  input: response.usage?.prompt_tokens ?? 0,
  output: response.usage?.completion_tokens ?? 0,
  total: response.usage?.total_tokens ?? 0,
});
```

Token field names vary by provider. OpenAI's `usage.prompt_tokens` is the input count; Anthropic's `usage.input_tokens` is. Always pull from the provider response, not from a re-tokenization.

### `track_time_to_first_token` / `trackTimeToFirstToken`

For streaming calls, record the time from request-start to first-chunk.

```python
config.tracker.track_time_to_first_token(time_to_first_token_ms)
```
```typescript
aiConfig.tracker.trackTimeToFirstToken(timeToFirstTokenMs);
```

Skip for non-streaming calls. See the "Streaming" section below.

### `track_feedback` / `trackFeedback`

Record user feedback (thumbs-up/down). Both SDKs take a `{kind}` object with a `FeedbackKind` enum.

```python
from ldai.tracker import FeedbackKind
config.tracker.track_feedback({"kind": FeedbackKind.Positive})
config.tracker.track_feedback({"kind": FeedbackKind.Negative})
```
```typescript
import { LDFeedbackKind } from '@launchdarkly/server-sdk-ai';
aiConfig.tracker.trackFeedback({ kind: LDFeedbackKind.Positive });
aiConfig.tracker.trackFeedback({ kind: LDFeedbackKind.Negative });
```

Wire this only when the app has a UI that captures the signal — e.g. thumbs-up/down buttons on each response. Persist the `tracker` reference alongside the message so the feedback call lands on the same config that produced the response.

### `track_tool_call` / (Node: no per-call method)

**Python only.** Records a tool invocation on the config that issued it.

```python
config.tracker.track_tool_call("search_kb")
# Optional: associate with a graph execution
config.tracker.track_tool_call("search_kb", graph_key="support-flow")
```

The Node tracker has no individual `trackToolCall` method — tool-call metrics flow through the `trackMetricsOf` wrapper (the extractor can count tool calls on the response and include them in the `LDAIMetrics` it returns). If you need per-tool-name granularity on Node today, track it as custom data via the base SDK's `ldClient.track()`.

### `track_tool_calls` / (Python only, batch)

```python
config.tracker.track_tool_calls(["search_kb", "calculator"])
```

Iterable variant. Call once per request with the full list of tools invoked.

### `track_eval_scores` / `trackEvalScores`

Record judge scores from a programmatic evaluation. See SKILL.md Step 6 and `aiconfig-online-evals`.

The full programmatic direct-judge pattern (Python):

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

**Rules for the Python shape:**

- `create_judge` returns `Optional[Judge]` — guard with `if judge and judge.enabled:` before calling `.evaluate`. A direct `.evaluate()` on a `None` return raises `AttributeError`.
- The `default` argument is typed `Optional[AIJudgeConfigDefault]`. Do not pass `AICompletionConfigDefault` even though some older examples show it — the type is strict.
- `sampling_rate` is a parameter on `Judge.evaluate()`, **not** on `create_judge`. It defaults to `1.0` (evaluate every call). Internally the SDK does `if random.random() > sampling_rate: return None`, so `evaluate()` can return `None` at the sampling layer too — hence the `if result:` guard around `track_eval_scores`.
- The second parameter of `.evaluate()` is a keyword-only `sampling_rate` — positional `input_text` and `output_text` come first.

Node equivalent:

```typescript
aiConfig.tracker.trackEvalScores(judgeResponse.evals);
```

(The Node SDK exposes the same `trackEvalScores` method but the judge-creation side of the API is evolving — verify against the current `@launchdarkly/server-sdk-ai` source before writing Node code against it.)

Only needed when you call `create_judge(...).evaluate(...)` directly. Automatic evaluation via `create_chat()` + `invoke()` records scores without this call.

### `track_judge_response` / `trackJudgeResponse`

Record the full structured response from a judge (raw scores + reasoning).

```python
config.tracker.track_judge_response(judge_response)
```
```typescript
aiConfig.tracker.trackJudgeResponse(judgeResponse);
```

Use alongside `track_eval_scores` if you want both the numeric scores and the judge's reasoning text stored.

## Auto-tracking helpers

The canonical tracking surface is **`trackMetricsOf` composed with a provider-package `getAIMetricsFromResponse` extractor** (Tier 2) — or, one level up, the managed runners (`ManagedModel` / `TrackedChat` / `initChat`) which track everything automatically and don't require any tracker calls at all (Tier 1). Both Python and Node SDK READMEs document this tiering exclusively as of this writing.

Legacy single-purpose helpers (`track_openai_metrics`, `track_bedrock_converse_metrics`, `trackVercelAISDKGenerateTextMetrics`) still exist in the SDK source, but no current README uses them. **Do not introduce them in new code.** They're listed below with a `[legacy]` tag so you can recognize them in existing codebases, not so you'll reach for them.

### Python

| Helper | Signature | Tier | Notes |
|--------|-----------|------|-------|
| `track_metrics_of(func, extractor)` | `tracker.track_metrics_of(func, extractor)` | **2 / 3** | **Canonical generic wrapper.** Sync. Calls `extractor(result)` to get an `LDAIMetrics` object; records tokens + duration + success. Use a provider package's `Provider.get_ai_metrics_from_response` as the extractor for Tier 2, or write a small custom function for Tier 3. |
| `track_metrics_of_async(func, extractor)` | `await tracker.track_metrics_of_async(async_func, extractor)` | 2 / 3 | Async variant. |
| `track_duration_of(func)` | `tracker.track_duration_of(lambda: provider_call())` | 4 | Wraps a sync callable; captures duration only. Pair with explicit `track_tokens` + `track_success`. Useful when the response shape makes `track_metrics_of` awkward. |
| `track_openai_metrics(func)` | `tracker.track_openai_metrics(lambda: openai_client.chat.completions.create(...))` | **[legacy]** | Predates the `ldai_openai` provider package. Replace with `track_metrics_of(call_openai, OpenAIProvider.get_ai_metrics_from_response)`. |
| `track_bedrock_converse_metrics(res)` | `tracker.track_bedrock_converse_metrics(bedrock_response)` | **[legacy]** | Predates `track_metrics_of`. Replace with a Converse extractor passed to `track_metrics_of`. See [bedrock-tracking.md](../../aiconfig-ai-metrics/references/bedrock-tracking.md). |

Example — OpenAI via `track_metrics_of` + the provider package extractor (current pattern):
```python
from ldai_openai import OpenAIProvider

def call_openai():
    return openai_client.chat.completions.create(
        model=config.model.name,
        messages=[m.to_dict() for m in config.messages or []],
    )

completion = config.tracker.track_metrics_of(
    call_openai,
    OpenAIProvider.get_ai_metrics_from_response,
)
```

Example — custom extractor for Anthropic direct (Tier 3):
```python
from ldai.providers.types import LDAIMetrics, TokenUsage

def anthropic_extractor(response) -> LDAIMetrics:
    return LDAIMetrics(
        success=True,
        usage=TokenUsage(
            total=response.usage.input_tokens + response.usage.output_tokens,
            input=response.usage.input_tokens,
            output=response.usage.output_tokens,
        ),
    )

response = config.tracker.track_metrics_of(
    lambda: anthropic_client.messages.create(...),
    anthropic_extractor,
)
```

### Node.js / TypeScript

| Helper | Signature | Tier | Notes |
|--------|-----------|------|-------|
| `trackMetricsOf<T>(extractor, func)` | `await tracker.trackMetricsOf((result) => extractor(result), async () => ...)` | **2 / 3** | **Canonical generic wrapper.** `extractor` maps provider response → `LDAIMetrics`. Use a provider package's `Provider.getAIMetricsFromResponse` for Tier 2 (`@launchdarkly/server-sdk-ai-openai`, `-langchain`, `-vercel`) or a small custom function for Tier 3. |
| `trackStreamMetricsOf<T>(extractor, streamCreator)` | `tracker.trackStreamMetricsOf(async (chunks) => extractor(chunks), () => createStream())` | 2 / 3 | Stream variant. Does **not** capture TTFT automatically — if you need TTFT, use the manual pattern in [streaming-tracking.md](../../aiconfig-ai-metrics/references/streaming-tracking.md). |
| `trackDurationOf<T>(func)` | `await tracker.trackDurationOf(async () => ...)` | 4 | Wraps an async callable; captures duration only. Pair with explicit `trackTokens` + `trackSuccess`. |
| `trackOpenAIMetrics<T>(func)` | `await tracker.trackOpenAIMetrics(async () => openai.chat.completions.create(...))` | **[legacy]** | Predates `@launchdarkly/server-sdk-ai-openai`. Replace with `trackMetricsOf(OpenAIProvider.getAIMetricsFromResponse, () => ...)`. |
| `trackBedrockConverseMetrics<T>(res)` | `tracker.trackBedrockConverseMetrics(bedrockResponse)` | **[legacy]** | Replace with a Converse extractor passed to `trackMetricsOf`. |
| `trackVercelAISDKGenerateTextMetrics<T>(func)` | `await tracker.trackVercelAISDKGenerateTextMetrics(async () => generateText({...}))` | **[legacy]** | Replace with `trackMetricsOf` + `VercelAISDKProvider.getAIMetricsFromResponse` from `@launchdarkly/server-sdk-ai-vercel`. |

Example — OpenAI via `trackMetricsOf` + the provider package (current pattern):
```typescript
import { OpenAIProvider } from '@launchdarkly/server-sdk-ai-openai';

const response = await aiConfig.tracker.trackMetricsOf(
  OpenAIProvider.getAIMetricsFromResponse,
  () => openai.chat.completions.create({
    model: aiConfig.model?.name ?? 'gpt-4o',
    messages: [...(aiConfig.messages ?? []), { role: 'user', content: userPrompt }],
  }),
);
```

Example — LangChain via `trackMetricsOf` (works for any model LangChain wraps, including Anthropic and Bedrock):
```typescript
import { LangChainProvider } from '@launchdarkly/server-sdk-ai-langchain';

const llm = await LangChainProvider.createLangChainModel(aiConfig);
const response = await aiConfig.tracker.trackMetricsOf(
  LangChainProvider.getAIMetricsFromResponse,
  () => llm.invoke(messages),
);
```

### Tier 1 — Managed runners (mention)

For chat-loop applications, both SDKs expose a higher-level API that handles tracking end-to-end with no tracker calls at all:

- Python: `ai_client.create_model(...)` → `ManagedModel`, then `await model.invoke(user_input)`
- Node: `aiClient.initChat(...)` / `aiClient.createChat(...)` → `TrackedChat`, then `await chat.invoke(userInput)`

The managed runner handles message history, provider dispatch (via the installed provider package — OpenAI, LangChain, Vercel), and tracker wiring. If the migration target is conversational, this is the right tier and you don't need anything from the tables above.

### Anthropic has no provider package today

Neither `@launchdarkly/server-sdk-ai-anthropic` nor `launchdarkly-server-sdk-ai-anthropic` exists as of this writing. For Anthropic direct calls, write a custom extractor and pass it to `track_metrics_of` / `trackMetricsOf` — see the Python example above or the full walk-through in [anthropic-tracking.md](../../aiconfig-ai-metrics/references/anthropic-tracking.md). If the app is open to LangChain, routing Anthropic through `ChatAnthropic` and the LangChain provider package recovers Tier 2 with zero extractor code.

## Tier decision table

| Situation | Tier | Pattern |
|-----------|------|---------|
| Chat loop (history, turn-based), any provider with a package | **1** | `ManagedModel` / `TrackedChat` / `initChat` — no tracker calls |
| OpenAI direct SDK, non-chat shape | **2** | `trackMetricsOf(OpenAIProvider.getAIMetricsFromResponse, fn)` |
| LangChain / LangGraph (any underlying model), non-chat shape | **2** | `trackMetricsOf(LangChainProvider.getAIMetricsFromResponse, fn)` |
| Vercel AI SDK, non-chat shape (Node only) | **2** | `trackMetricsOf` with the Vercel provider package's extractor |
| Anthropic direct SDK | **3** | Custom extractor reading `response.usage.input_tokens` / `output_tokens` |
| Bedrock Converse (no provider package) | **3** | Custom extractor reading `response.usage.inputTokens` / `outputTokens` (or route via LangChain for Tier 2) |
| Gemini / Google GenAI, Cohere, custom HTTP | **3** | Custom extractor |
| Streaming response with TTFT required | **4** | Manual `trackTimeToFirstToken` + `trackDuration` + `trackTokens` + `trackSuccess` — see [streaming-tracking.md](../../aiconfig-ai-metrics/references/streaming-tracking.md) |
| Streaming response without TTFT (Node) | **2 / 3** | `trackStreamMetricsOf(extractor, streamFn)` |

## Streaming responses

Streaming is trickier because duration and tokens aren't known until the stream completes.

**Python — manual pattern for streaming OpenAI:**
```python
import time

start = time.time()
first_chunk_time = None
input_tokens = 0
output_tokens = 0

stream = openai_client.chat.completions.create(stream=True, ...)
for chunk in stream:
    if first_chunk_time is None:
        first_chunk_time = time.time()
        config.tracker.track_time_to_first_token(int((first_chunk_time - start) * 1000))
    # accumulate output tokens from chunk.usage if provider emits them
    # or use a tokenizer for an estimate

config.tracker.track_duration(int((time.time() - start) * 1000))
config.tracker.track_tokens(TokenUsage(input=input_tokens, output=output_tokens, total=input_tokens + output_tokens))
config.tracker.track_success()
```

**Node — use `trackStreamMetricsOf`:**
```typescript
const stream = await aiConfig.tracker.trackStreamMetricsOf(
  () => openai.chat.completions.create({ stream: true, /* ... */ }),
  async (s) => {
    // Drain the stream and extract LDAIMetrics
    return extractMetricsFromDrainedStream(s);
  },
);
```

## Where tracker calls should live

- **Inside a retry wrapper**, not outside it. If your request has 3 retry attempts and 2 fail + 1 succeeds, you want 1 `track_success`. Putting the tracker outside the retry would cause 3 events or 0.
- **Per request**, not cached across requests. `config.tracker` is attached to a per-request `config` object. Do not stash it in module scope.
- **Before any return statement.** A tracker call that never runs (because an early return bypasses it) produces silent data loss. Use try/finally in complex handlers if needed.
- **After the provider returns**, not before. Duration measured from before the provider call; tokens and success/error from the response.

## Troubleshooting: Monitoring tab shows no data

Run the checklist in order. Each step rules out one cause.

1. **SDK key** — is `LD_SDK_KEY` the server-side key (starts with `sdk-`), not the client-side key or the API key?
2. **Enabled check** — is `config.enabled` / `aiConfig.enabled` `True`? A disabled config will not record traffic. Check the AI Config's targeting in LaunchDarkly and confirm the context matches a rule that serves an enabled variation.
3. **Any tracker call at all** — did `track_success` / `trackSuccess` fire? Without at least one generation-level call, the Monitoring tab has nothing to show. Log a one-liner next to the call to confirm it runs.
4. **Config key match** — is the string passed to `completion_config` / `completionConfig` exactly the same as the AI Config key in LaunchDarkly? Keys are case-sensitive.
5. **Mode match** — if the code calls `completion_config` but the AI Config in LaunchDarkly is in agent mode (or vice versa), the SDK call will error out. Check the mode in the UI.
6. **Flush on shutdown** — on short-lived processes (tests, scripts), call `ld_client.flush()` before exit. Long-running servers flush automatically on an interval.
7. **Data delay** — the Monitoring tab updates within 1–2 minutes. If you just deployed, wait and retry before debugging further.
8. **SDK version** — some tracker methods were added in later minor versions. `track_feedback`, `track_eval_scores`, and the auto-helpers require Python v0.14.0+ or Node v0.16.1+.
9. **Debug logging** — enable SDK debug logging (`LD_LOG_LEVEL=debug` / `setLevel('debug')`) to see evaluation results and tracker calls in stdout.
10. **Error path silent** — are you catching exceptions that swallow tracker errors? The tracker should never raise, but if a custom wrapper catches everything, confirm the call fires by logging before and after.

## Common gotchas

- **`track_tokens` token shape.** The Python `TokenUsage` dataclass requires `total` to be set — it is not derived. Compute `total = input + output` if the provider doesn't return one.
- **`track_feedback` lifecycle.** The feedback call must be made on the *same tracker* that produced the response. Store `config.tracker` alongside the message in your DB or session so a thumbs-up later still routes to the right config.
- **OpenAI streaming tokens.** OpenAI only emits `usage` in the final chunk when `stream_options={"include_usage": True}` is passed. Without that flag, you have to tokenize manually — `tiktoken` for OpenAI models.
- **Anthropic token field names.** Anthropic uses `response.usage.input_tokens` and `output_tokens`, not `prompt_tokens`/`completion_tokens`. Do not copy the OpenAI shape.
- **Bedrock Converse response shape.** `response["usage"]["inputTokens"]` (camelCase, not snake). The auto-helper handles this — prefer it over manual extraction.
- **Retry loops and `track_duration`.** If you wrap the whole retry in `track_duration`, the value includes backoff sleeps. Either measure only the final-attempt provider call, or document that duration includes retries — don't leave it ambiguous.
- **Do not cache `config.tracker`.** Each `completion_config` / `agent_config` call returns a new tracker tied to that request's variation. Caching the tracker means future feedback, evals, or token counts land on the wrong config.
