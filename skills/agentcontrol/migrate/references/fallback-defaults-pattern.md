# Fallback Patterns

The current AI SDKs have no fallback argument. `config().invoke()` raises `RuntimeError` when:

- the served variation is disabled, or targeting is off
- the config key doesn't exist in the environment
- no SDK key is set, or LaunchDarkly is unreachable

The application owns the fallback. Provider errors (`openai.APIError`, `anthropic.APIStatusError`, and so on) are different exception types, so catching `RuntimeError` separates "LaunchDarkly can't serve this config" from "the model call failed."

## Pattern 1: Keep the original call (start here)

The hardcoded function the migration replaces already mirrors current behavior exactly. Rename it and call it from the `except` branch:

### Python

```python
import logging
from launchdarkly_ai_server import config
from launchdarkly_ai_openai_messages import create_openai_messages_handler

logger = logging.getLogger(__name__)

chat = config(key="chat-assistant", handler=create_openai_messages_handler())

def answer_hardcoded(user_input: str) -> str:
    # The original, unmodified pre-migration code
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        temperature=0.7,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Answer concisely."},
            {"role": "user", "content": user_input},
        ],
    )
    return response.choices[0].message.content

async def answer(user_id: str, user_input: str) -> str:
    try:
        result = await chat.invoke(user_input, {"kind": "user", "key": user_id})
        return result.response
    except RuntimeError as exc:
        logger.warning("chat-assistant unavailable (%s); using hardcoded fallback", exc)
        return answer_hardcoded(user_input)
```

### Node.js

```typescript
import { config } from '@launchdarkly/ai-node';
import { createOpenAIHandler } from '@launchdarkly/ai-openai-messages';

const chat = config({ key: 'chat-assistant', handler: createOpenAIHandler() });

export async function answer(userId: string, userInput: string): Promise<string> {
  try {
    const result = await chat.invoke(userInput, { kind: 'user', key: userId });
    return result.response;
  } catch (err) {
    if (isProviderError(err)) throw err;
    console.warn('chat-assistant unavailable; using hardcoded fallback', err);
    return answerHardcoded(userInput);
  }
}
```

Node.js raises plain `Error`s for an unavailable config, so test for your provider SDK's error classes (for example `err instanceof OpenAI.APIError`) and rethrow those.

### When to use

The default for every migration. It costs nothing to write, it's already tested, and it keeps the app working through a LaunchDarkly outage, a bad SDK key in a new environment, or a variation someone disabled.

**Fallback calls aren't recorded.** Calls that take the fallback emit no `$ld:ai:*` metrics, because the SDK never ran them. Log or count fallbacks yourself if you need to see how often they happen.

## Pattern 2: Degraded response

When a disabled variation means "turn this feature off," the fallback shouldn't call a model at all:

```python
async def summarize(user_id: str, document: str) -> str | None:
    try:
        result = await summaries.invoke(document, {"kind": "user", "key": user_id})
        return result.response
    except RuntimeError:
        return None  # The UI hides the summary panel
```

### When to use

Features where "off" is a valid product state, such as an optional summary or a suggestion chip, rather than a core request path.

## Pattern 3: Check state before invoking

`inspect_config(key, context)` / `inspectConfig(key, context)` returns the served state without raising: `{"enabled": bool, "config": dict | None, "meta": ...}`. Use it to decide before doing expensive work, or to render UI that depends on whether the feature is on:

```python
from launchdarkly_ai_server import inspect_config

state = await inspect_config("chat-assistant", context)
if not state["enabled"]:
    return render_without_assistant()
```

```typescript
import { inspectConfig } from '@launchdarkly/ai-node';

const state = await inspectConfig('chat-assistant', context);
if (!state.enabled) return renderWithoutAssistant();
```

Both functions are async. `inspect_config` is an extra evaluation, so don't call it in front of every `invoke()`; the `except RuntimeError` branch already covers the same cases.

## Template placeholders

The LaunchDarkly-served prompt and the fallback use different template syntaxes, and that's fine:

- **Served prompt:** `{{name}}` placeholders, filled from the third argument to `invoke()`. No spaces inside the braces; `{{ name }}` is sent to the model literally.
- **Fallback:** the original code, with its original `.format()` call, f-string, or template literal, untouched.

```python
variables = {"system_time": datetime.now().isoformat()}
try:
    result = await chat.invoke(user_input, context, variables)
except RuntimeError:
    return answer_hardcoded(user_input, **variables)  # still uses SYSTEM_PROMPT.format(...)
```

Pass the same values to both paths, so a variable added to the served prompt doesn't silently go missing from the fallback.

## Critical rules

1. **Catch `RuntimeError` around every `invoke()` and `stream()` call on a request path.** An uncaught raise turns a LaunchDarkly configuration gap into an outage.
2. **Don't delete the original call** once LaunchDarkly is wired up. It's the fallback.
3. **Don't swallow provider errors in the fallback branch.** A failing model call should surface as an error and is recorded as one by the SDK.
4. **Don't raise at import time for a missing `LD_SDK_KEY`.** Log a warning and let the fallback serve requests.
5. **Keep the fallback in sync with intent, not with LaunchDarkly.** It represents the last known-good hardcoded behavior. Update it when you deliberately change the baseline, not every time a variation changes.
