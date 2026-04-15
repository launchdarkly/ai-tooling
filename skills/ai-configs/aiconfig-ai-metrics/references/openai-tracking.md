# OpenAI Metrics Tracking

OpenAI is covered by a first-class LaunchDarkly provider package in both Python and Node. Walk the tiers from top to bottom and stop at the first one that fits the call shape.

## Tier 1 — Managed runner (chat apps)

The simplest path for conversational OpenAI calls. Zero tracker calls — duration, tokens, and success/error are all captured by `invoke()`.

**Python** — `ManagedModel` via `ai_client.create_model()`:

```python
from ldclient import Context
from ldai import LDAIClient, AICompletionConfigDefault, ModelConfig, LDMessage, ProviderConfig

default_config = AICompletionConfigDefault(
    enabled=True,
    model=ModelConfig(name="gpt-4o"),
    provider=ProviderConfig(name="openai"),
    messages=[LDMessage(role="system", content="You are a helpful assistant.")],
)

async def handle_turn(ai_client: LDAIClient, context: Context, user_input: str) -> str:
    model = await ai_client.create_model(
        "customer-support-chat",
        context,
        default_config,
    )
    if not model:
        return "Feature is currently unavailable."
    response = await model.invoke(user_input)
    return response.message.content
```

**Node** — `TrackedChat` via `aiClient.initChat()`:

```typescript
import { init } from '@launchdarkly/node-server-sdk';
import { initAi } from '@launchdarkly/server-sdk-ai';

const ldClient = init(process.env.LD_SDK_KEY!);
const aiClient = initAi(ldClient);

async function handleTurn(context: LDContext, userInput: string): Promise<string> {
  const chat = await aiClient.initChat(
    'customer-support-chat',
    context,
    {
      enabled: true,
      model: { name: 'gpt-4o' },
      provider: { name: 'openai' },
      messages: [{ role: 'system', content: 'You are a helpful assistant.' }],
    },
  );
  if (!chat) return 'Feature is currently unavailable.';
  const response = await chat.invoke(userInput);
  return response.message.content;
}
```

Tracking is handled inside `invoke()`. You do not need `trackMetricsOf`, `trackSuccess`, or `trackTokens` at this tier.

## Tier 2 — Provider package + `trackMetricsOf` (non-chat shapes)

Use this when the call isn't a chat loop (one-shot completion, structured output, batch job, agent step). The provider package exposes a static `getAIMetricsFromResponse` that knows how to pull tokens out of an OpenAI response; you compose it with the generic `trackMetricsOf` wrapper.

**Python** — `launchdarkly-server-sdk-ai-openai`:

```python
from ldai_openai import OpenAIProvider

ai_config = ai_client.completion_config("my-config-key", context, default_config)
if not ai_config.enabled:
    return None

provider = await OpenAIProvider.create(ai_config)
response = await provider.invoke_model(ai_config.messages)
return response.message.content
```

`OpenAIProvider.invoke_model()` also tracks automatically. If you need finer-grained control (e.g., you want to supply your own OpenAI client with custom retries), use the raw SDK + `track_metrics_of`:

```python
import openai
from ldai_openai import OpenAIProvider

client = openai.OpenAI()

ai_config = ai_client.completion_config("my-config-key", context, default_config)
if not ai_config.enabled:
    return None

def call_openai():
    return client.chat.completions.create(
        model=ai_config.model.name,
        messages=[
            {"role": "system", "content": ai_config.messages[0].content},
            {"role": "user", "content": user_prompt},
        ],
    )

response = ai_config.tracker.track_metrics_of(
    call_openai,
    OpenAIProvider.get_ai_metrics_from_response,
)
return response.choices[0].message.content
```

**Node** — `@launchdarkly/server-sdk-ai-openai`:

```typescript
import { OpenAI } from 'openai';
import { OpenAIProvider } from '@launchdarkly/server-sdk-ai-openai';

const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

const aiConfig = await aiClient.completionConfig('my-config-key', context, defaultConfig);
if (!aiConfig.enabled) return null;

const response = await aiConfig.tracker.trackMetricsOf(
  OpenAIProvider.getAIMetricsFromResponse,
  () => client.chat.completions.create({
    model: aiConfig.model!.name,
    messages: [
      ...aiConfig.messages,
      { role: 'user', content: userPrompt },
    ],
  }),
);
return response.choices[0].message.content;
```

**Error handling.** `trackMetricsOf` records `success: true` on return and lets exceptions propagate. Wrap with try/catch to capture errors:

```typescript
try {
  const response = await aiConfig.tracker.trackMetricsOf(
    OpenAIProvider.getAIMetricsFromResponse,
    () => client.chat.completions.create({ /* ... */ }),
  );
  return response.choices[0].message.content;
} catch (err) {
  aiConfig.tracker.trackError();
  throw err;
}
```

Python follows the same shape with `try` / `except` and `config.tracker.track_error()`.

## Tier 3 — Custom extractor (fallback)

You should not need Tier 3 for OpenAI — the provider package covers it. If you're using a fork, a drop-in replacement (LiteLLM, Azure OpenAI via raw HTTP), or something the provider package doesn't recognize, write a small extractor:

```python
from ldai.providers.types import LDAIMetrics, TokenUsage

def my_openai_extractor(response) -> LDAIMetrics:
    return LDAIMetrics(
        success=True,
        usage=TokenUsage(
            total=response.usage.total_tokens,
            input=response.usage.prompt_tokens,
            output=response.usage.completion_tokens,
        ),
    )

response = ai_config.tracker.track_metrics_of(call_openai, my_openai_extractor)
```

## Tier 4 — Manual (streaming only)

For OpenAI streaming calls you need manual tracking because the current provider packages don't capture TTFT. See [streaming-tracking.md](streaming-tracking.md) for the full pattern. The short version: the helper that looks like it should work (`trackStreamMetricsOf` in Node) captures tokens from stream chunks but does not record TTFT, so you still need a manual `trackTimeToFirstToken` call on the first content chunk.

## Legacy: `track_openai_metrics` / `trackOpenAIMetrics`

You may see existing code that calls `config.tracker.track_openai_metrics(lambda: openai.chat.completions.create(...))` or the Node equivalent. These helpers still work but are no longer the recommended pattern — they predate the provider packages and the generic `trackMetricsOf` + `getAIMetricsFromResponse` composition. **Do not introduce them in new code.** If you're migrating an existing codebase, leave them in place unless the user has specifically asked for a cleanup pass — the migration from the legacy helper to the new pattern is mechanical but not free.
