---
name: built-in-metrics
description: "Instrument an existing codebase so LaunchDarkly records config metrics (duration, tokens, success/error, tool calls). Walks the ladder (convenience function → config() with a handler package → custom handler → manual track()) and picks the lowest-ceremony option that still captures what the Monitoring tab needs."
license: Apache-2.0
compatibility: Requires `launchdarkly-ai-server` 0.3.0+ (Python) or `@launchdarkly/ai-node` 0.3.0+ (Node.js), a handler package for your provider, and an existing config.
metadata:
  author: launchdarkly
  version: "2.0.0-experimental"
---

# Agent Metrics Instrumentation

You're using a skill that gets LaunchDarkly agent metrics flowing from an existing provider call. Your job is to audit what's already there, pick the right tier from the ladder below, and implement it with the **least ceremony that still captures the metrics the Monitoring tab needs**.

The single most important thing to get right: **in the current SDKs, metrics are a side effect of routing the call through the SDK.** There is no tracker to create and no wrapper to call. If the provider call runs inside `config().invoke()` (or a convenience function), the SDK records the metrics. If it runs outside, nothing is recorded.

## What the SDK records

Every `invoke()` and `stream()` call records these events against the served variation:

| Event | Metric |
|---|---|
| `$ld:ai:duration:total` | Duration, in milliseconds |
| `$ld:ai:generation:success` / `$ld:ai:generation:error` | Generation counts and error rate |
| `$ld:ai:tokens:input`, `:output`, `:total` | Token usage, from the handler's normalized usage |
| `$ld:ai:tool_call` | One event per tool call the SDK dispatches |

The current SDKs do **not** record time to first token or user feedback. For feedback, see Tier 4.

## The four-tier ladder

Walk from the top and stop at the first tier that fits:

| Tier | Pattern | Use when |
|------|---------|----------|
| **1 — Convenience function** | `openai_messages(key, input, context)` / `openaiMessages(key, input, context)`, one per handler package | One provider in one mode, no tools, no streaming. The shortest path. |
| **2 — `config()` + handler package** | `config(key=..., handler=[...]).invoke(input, context)` / `.stream(...)` | A handler package covers your provider, and you need more than one provider or mode, tools, template variables, streaming, or background judges. |
| **3 — Custom handler** | `create_handler((provider, mode), fn)` / `createHandler([provider, mode], fn)`, passed to `config()` | No handler package fits (Gemini SDK, Bedrock via boto3, Strands, custom HTTP), or you want to keep an existing provider call as is. |
| **4 — Manual `track()`** | `get_client().track(event_key, context, result.track_data, value)` | Events the SDK doesn't record: user feedback and business outcomes. Never for duration, tokens, or success, which the SDK already records. |

## Workflow

### 1. Explore the existing call site

Before picking a tier, find the provider call and answer these questions:

- [ ] **Provider?** OpenAI, Anthropic, Bedrock, Gemini, custom HTTP? → cross-reference with the handler matrix below.
- [ ] **Framework?** Raw provider SDK, LangChain / LangGraph, OpenAI Agents SDK, Claude Agent SDK, Strands?
- [ ] **Mode?** A completion (`messages`) or an agent (`agent`)? The served variation's mode selects the handler.
- [ ] **Streaming?** Use `stream()` instead of `invoke()`. Metrics are recorded the same way, but time to first token isn't.
- [ ] **Language?** Python or Node.js? Handler coverage is the same in both.
- [ ] **Already using a config?** If not, route to `configs-create` first.
- [ ] **On a legacy SDK?** If the code imports `ldai` / `@launchdarkly/server-sdk-ai`, or calls `create_tracker()`, `track_metrics_of()`, `trackMetricsOf()`, `completion_config()`, or `create_model()`, it's on the legacy surface. Replace it as part of this work (see [Replacing legacy tracker code](#replacing-legacy-tracker-code)). For call sites with hardcoded models or prompts, hand off to `migrate` instead.

### 2. Look up your handler

Install the core package (`launchdarkly-ai-server` or `@launchdarkly/ai-node`) plus one handler package per provider and mode you serve:

| Provider / framework | Python handler package | Node.js handler package | Reference |
|---|---|---|---|
| OpenAI | `launchdarkly-ai-openai-messages`, `-openai-agents` | `@launchdarkly/ai-openai-messages`, `-openai-agents` | [openai-tracking.md](references/openai-tracking.md) |
| Anthropic | `launchdarkly-ai-claude-messages`, `-claude-agents` | `@launchdarkly/ai-claude-messages`, `-claude-agents` | [anthropic-tracking.md](references/anthropic-tracking.md) |
| LangChain / LangGraph (any provider) | `launchdarkly-ai-langchain-messages`, `-langchain-agents` | `@launchdarkly/ai-langchain-messages`, `-langchain-agents` | [langchain-tracking.md](references/langchain-tracking.md) |
| AWS Bedrock | LangChain handler + `langchain-aws`, or a custom handler | LangChain handler, or a custom handler | [bedrock-tracking.md](references/bedrock-tracking.md) |
| Gemini / Google GenAI | LangChain handler with a model factory, or a custom handler | Same | [gemini-tracking.md](references/gemini-tracking.md) |
| Strands Agents | Custom handler | Custom handler | [strands-tracking.md](references/strands-tracking.md) |
| Cohere, Mistral, custom HTTP | Custom handler | Custom handler | [anthropic-tracking.md](references/anthropic-tracking.md#tier-3--custom-handler) shows the shape |
| Any provider, streaming | `stream()` | `stream()` | [streaming-tracking.md](references/streaming-tracking.md) |

The LangChain handlers register for every provider (`"*"`) and only apply when no exact-provider handler matches.

### 3. Implement from the matching reference

Open the reference file and follow the pattern. Stop at the first tier that matches the app's shape.

Guardrails that apply to every tier:

1. **Handle disabled configs.** `invoke()` raises a `RuntimeError` when the served variation is disabled or the config can't be reached. Catch it and fall back to whatever the app does when the feature is off, or call `inspect_config(key, context)` / `inspectConfig(key, context)` first, which returns the `enabled` state without raising.
2. **Don't add tracking on top.** The SDK already records duration, tokens, success, and errors. A manual `track("$ld:ai:tokens:total", ...)` next to `invoke()` double counts.
3. **Let errors propagate.** When a handler raises, the SDK records the duration and a generation error, then re-raises to the caller. Don't catch and swallow the exception inside a custom handler, or the call is recorded as a success.
4. **Match the provider name exactly.** Handlers route on the config's provider name and mode, case-sensitively: `("OpenAI", "messages")`, `("Anthropic", "messages")`, `("Bedrock", "messages")`, `("Gemini", "messages")`. In Python the first argument to `create_handler` must be a tuple.
5. **Shut down cleanly.** Call `await shutdown()` before the process exits. It flushes pending events, then closes the client. Trailing events are at risk of being lost otherwise, in short-lived scripts and long-running services alike.

### 4. Verify

Confirm the Monitoring tab fills in:

- [ ] Run one real request through the instrumented path.
- [ ] Open the config in LaunchDarkly → **Monitoring** tab. Duration, token counts, and generation counts should appear within 1–2 minutes.
- [ ] Force an error (bad API key, unreachable endpoint) and confirm the error count increments.
- [ ] If you see generations but no tokens, the handler isn't returning usage. Custom handlers must return `{"output": ..., "usage": {"input": n, "output": n}}`.

## Replacing legacy tracker code

| Legacy | Current |
|---|---|
| `LDAIClient(ldclient.get())` / `initAi(ldClient)` | Lazy init from `LD_SDK_KEY`, or `init_client()` / `initClient()` |
| `completion_config()` / `agent_config()` + provider call | `config(key=..., handler=...).invoke(input, context)` |
| `create_model()` + `model.run()` | `config().invoke()` or a convenience function |
| `tracker.track_metrics_of(extractor, fn)` / `trackMetricsOf` | Delete. Route the call through a handler package or a custom handler. |
| `get_ai_metrics_from_response` / custom `LDAIMetrics` extractors | Delete. Handlers return normalized usage. |
| `track_duration`, `track_tokens`, `track_success`, `track_error` | Delete. Recorded on every call. |
| `track_tool_call(s)` | Delete. Recorded for each tool the SDK dispatches. |
| `track_time_to_first_token` | Not recorded by the current SDKs. |
| `track_feedback({kind})` | `get_client().track("$ld:ai:feedback:user:positive" or ":negative", context, result.track_data, 1)` (Tier 4) |
| `track_judge_result` | Attached judges record their own scores. See `online-evals`. |
| `ldclient.get().flush()` + `close()` | `await shutdown()` |

## Tier 4 — User feedback

The SDK doesn't record thumbs-up / thumbs-down, but the Monitoring tab still reads the feedback events. Keep the `track_data` from the `invoke()` result and send the event when the user responds:

```python
from ldclient import Context
from launchdarkly_ai_server import get_client

result = await config(key="support-agent", handler=handler).invoke(user_input, context)

# Later, when the user clicks thumbs up or down:
event = "$ld:ai:feedback:user:positive" if thumbs_up else "$ld:ai:feedback:user:negative"
get_client().track(event, Context.from_dict(context), result.track_data, 1)
```

```typescript
import { getClient } from '@launchdarkly/ai-node';

const result = await config({ key: 'support-agent', handler }).invoke(userInput, context);

const event = thumbsUp ? '$ld:ai:feedback:user:positive' : '$ld:ai:feedback:user:negative';
getClient().track(event, context, result.trackData, 1);
```

`track_data` identifies the config, variation, version, and model, so the feedback lands on the variation that produced the response. In Python, convert the context dict with `Context.from_dict()` before calling `track()`.

For business outcomes such as conversions or resolutions, use the `custom-metrics` skill with the same `track_data`.

## Related skills

- `configs-create` — prerequisite if the app doesn't have a config yet
- `custom-metrics` — business metrics (conversion, resolution, retention) layered on top of the agent metrics this skill captures
- `online-evals` — automatic quality scoring (LLM-as-judge) on sampled live requests; complementary to the metrics here
- `tools` — tool implementations and custom handler details
- `migrate` — Stage 4 of the hardcoded-to-AgentControl migration delegates to this skill
