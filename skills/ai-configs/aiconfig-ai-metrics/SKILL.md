---
name: aiconfig-ai-metrics
description: "Instrument an existing codebase with LaunchDarkly AI Config tracking. Wires the per-request tracker (duration, tokens, success/error, feedback) around provider calls for OpenAI, Anthropic, Bedrock, and streaming responses."
license: Apache-2.0
compatibility: Requires the LaunchDarkly server-side AI SDK (`launchdarkly-server-sdk-ai` for Python or `@launchdarkly/server-sdk-ai` for Node) and an existing AI Config.
metadata:
  author: launchdarkly
  version: "1.0.0-experimental"
---

# AI Metrics Instrumentation

This skill guides you through adding AI metrics tracking to a codebase. Your job is to explore, assess, and implement the right instrumentation strategy for this specific codebase.

## Workflow

### 1. Explore the Codebase

Before implementing anything, understand what you're working with:

- [ ] Find where AI/LLM calls are made (search for `openai`, `anthropic`, `bedrock`, `langchain`, etc.)
- [ ] Identify which providers are in use
- [ ] Check if LaunchDarkly SDK is already initialized
- [ ] Look for existing AI Config usage (`completion_config()`, `agent_config()`)
- [ ] Note whether calls are streaming or non-streaming
- [ ] Identify the language/runtime (Python, Node.js, Go, etc.)

### 2. Assess the Situation

Based on exploration, determine:

| Question | Why It Matters |
|----------|----------------|
| Which AI provider(s)? | Determines tracking method (automatic vs manual) |
| Streaming or batch? | Streaming requires TTFT tracking |
| AI Config already in use? | If not, see `aiconfig-sdk` skill first |
| Centralized or scattered calls? | Affects instrumentation strategy |
| Error handling in place? | Need to add `track_error()` calls |

### 3. Choose Your Implementation Path

Based on your assessment, select the appropriate reference:

| Situation | Reference |
|-----------|-----------|
| OpenAI calls (non-streaming) | `references/openai-tracking.md` |
| Anthropic calls | `references/anthropic-tracking.md` |
| AWS Bedrock | `references/bedrock-tracking.md` |
| Streaming responses | `references/streaming-tracking.md` |
| Need to query metrics data | `references/metrics-api.md` |

### 4. Implement

Follow the chosen reference to implement tracking. Key principles:

1. **Always check `config.enabled`** before making tracked calls
2. **Wrap existing calls** rather than rewriting them when possible
3. **Track errors** in exception handlers
4. **Flush in serverless** environments before function terminates

### 5. Verify

Confirm your instrumentation is working:

- [ ] Make a test call through the instrumented code path
- [ ] Check LaunchDarkly dashboard for metrics appearing
- [ ] Verify token counts look reasonable
- [ ] Confirm duration is being tracked
- [ ] Test error tracking by forcing a failure

## Quick Reference: Tracker Methods

The `config.tracker` object provides these methods:

| Method | Use Case |
|--------|----------|
| `track_openai_metrics(fn)` | Automatic tracking for OpenAI |
| `track_bedrock_converse_metrics(res)` | Automatic tracking for Bedrock |
| `track_duration_of(fn)` | Wrap any callable to track duration |
| `track_tokens(TokenUsage)` | Manual token tracking |
| `track_duration(int)` | Manual duration (ms) |
| `track_time_to_first_token(int)` | TTFT for streaming (ms) |
| `track_success()` | Mark successful |
| `track_error()` | Mark failed |

## Related Skills

- `aiconfig-sdk` - SDK setup (prerequisite if not already configured)
- `aiconfig-custom-metrics` - Business metrics beyond AI metrics
- `aiconfig-online-evals` - Automatic quality evaluation
