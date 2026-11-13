# SDK Metrics Patterns

The current AI SDKs have no tracker. Every `config().invoke()` and `stream()` call is one run, and the SDK records that run's metrics itself. This file covers what's recorded, how it maps onto app shapes, and how to replace legacy tracker code.

## What one `invoke()` records

| Event | Value | When |
|---|---|---|
| `$ld:ai:duration:total` | Milliseconds | Every call, success or error |
| `$ld:ai:generation:success` | 1 | The handler returned |
| `$ld:ai:generation:error` | 1 | The handler raised; the SDK then re-raises |
| `$ld:ai:tokens:input` / `:output` / `:total` | Token counts | When the handler's usage is non-zero; `total` is computed if missing |
| `$ld:ai:tool_call` | 1 per call | Each tool function the SDK dispatches |
| Judge metrics (for example `$ld:ai:judge:accuracy`) | Score | Each sampled attached judge, unless `skip_judges=True` |

Every event carries the same track data: `configKey`, `variationKey`, `version`, `modelName`, `providerName`, and a `runId` unique to the call. `result.track_data` / `result.trackData` exposes it.

**Not recorded:** time to first token and user feedback. See below for feedback.

## Mapping app shapes to runs

| App shape | One run is | Notes |
|---|---|---|
| One-shot completion | One `invoke()` | |
| Agent with a tool loop (handler package) | One `invoke()` | The handler runs up to 10 model calls; duration and tokens cover all of them |
| Custom `StateGraph`, CrewAI, Strands | One `invoke()` of a custom agent handler that runs the whole turn | Return usage summed across the turn |
| Retry wrapper | One `invoke()` | Keep retries inside the handler, so a recovered retry is one success |
| Streaming | One `stream()` | Usage comes from the `done` event |
| Multi-agent graph | One `graph().invoke()` | Per-node events plus `$ld:ai:graph:*` events |

The legacy rules about minting one tracker per turn and calling at-most-once methods in a `finalize` node collapse into one rule: **call `invoke()` once per user turn, and put the whole turn inside it.**

## User feedback

Persist `track_data` with the message, then send the feedback event when the user responds, in any process:

```python
from ldclient import Context
from launchdarkly_ai_server import get_client

# When the response is produced
store_message(message_id, result.response, track_data=result.track_data, context=context)

# Later, possibly in another service
msg = load_message(message_id)
event = "$ld:ai:feedback:user:positive" if thumbs_up else "$ld:ai:feedback:user:negative"
get_client().track(event, Context.from_dict(msg.context), msg.track_data, 1)
```

```typescript
import { getClient } from '@launchdarkly/ai-node';

const event = thumbsUp ? '$ld:ai:feedback:user:positive' : '$ld:ai:feedback:user:negative';
getClient().track(event, msg.context, msg.trackData, 1);
```

This replaces the legacy resumption-token pattern: `track_data` is a plain dict, so no rehydration step is needed.

## Replacing legacy tracker code

| Legacy | Action |
|---|---|
| `config.create_tracker()` / `aiConfig.createTracker()` | Delete |
| `track_metrics_of` / `trackMetricsOf` / `track_metrics_of_async` + extractors | Delete; route the call through a handler |
| `track_duration`, `track_duration_of`, `track_tokens`, `track_success`, `track_error` | Delete |
| `track_tool_call(s)` | Delete; pass the tools as `tool_handlers` |
| `track_time_to_first_token` | Delete; not recorded by the current SDKs |
| `track_feedback` | `get_client().track("$ld:ai:feedback:user:<positive or negative>", ...)` with `track_data` |
| `track_judge_result` | Delete; attached judges record their scores |
| `tracker.resumption_token` / `from_resumption_token` | Persist `track_data` instead |
| `ManagedModel` / `create_model()` + `run()` | `config().invoke()` |

For the full table and per-provider details, see the `built-in-metrics` skill.

## Troubleshooting: Monitoring tab shows no data

1. **Every request takes the fallback.** `invoke()` is raising `RuntimeError` and the `except` branch serves the request, so nothing is recorded. Log the exception. The usual causes are a disabled fallthrough variation (run `/configs-targeting`), a wrong config key, or a missing `LD_SDK_KEY`.
2. **The process exits before events flush.** Call `await shutdown()` before exit.
3. **Generations but no tokens.** A custom handler isn't returning `usage`, or a stream didn't request usage on its final chunk.
4. **Wrong environment.** The SDK key belongs to a different environment than the one you're viewing.
5. **Querying the metrics API directly?** `from` / `to` are Unix timestamps in milliseconds; seconds return zeros.

## Common gotchas

- Don't send `$ld:ai:duration:total`, `$ld:ai:tokens:*`, or `$ld:ai:generation:*` yourself next to `invoke()`; they double count.
- Don't catch and swallow provider exceptions inside a custom handler; the call is then recorded as a success with no output.
- In Python, `track()` needs an `ldclient` `Context`; convert the plain-dict context with `Context.from_dict()`.
