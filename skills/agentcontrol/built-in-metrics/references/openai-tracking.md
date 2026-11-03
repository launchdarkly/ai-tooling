# OpenAI Metrics Tracking

OpenAI has first-class handler packages in both Python and Node.js: `-openai-messages` for completion mode (Responses API) and `-openai-agents` for agent mode (OpenAI Agents SDK). Walk the tiers from top to bottom and stop at the first one that fits.

## Tier 1 — Convenience function

One provider, one mode, no tools. Duration, tokens, and success/error are recorded with no extra code.

**Python** (`pip install launchdarkly-ai-server launchdarkly-ai-openai-messages`):

```python
from launchdarkly_ai_openai_messages import openai_messages

# Reads LD_SDK_KEY and OPENAI_API_KEY from the environment
result = await openai_messages(
    "customer-support-chat",
    user_input,
    {"kind": "user", "key": "user-123"},
)
print(result.response)
```

**Node.js** (`npm install @launchdarkly/ai-node @launchdarkly/ai-openai-messages`):

```typescript
import { openaiMessages } from '@launchdarkly/ai-openai-messages';

const result = await openaiMessages('customer-support-chat', userInput, {
  kind: 'user',
  key: 'user-123',
});
console.log(result.response);
```

## Tier 2 — `config()` with handler packages

Use this when you need tools, template variables, streaming, background judges, or more than one mode. The served variation's mode picks the handler.

**Python:**

```python
from launchdarkly_ai_server import config, shutdown
from launchdarkly_ai_openai_messages import create_openai_messages_handler
from launchdarkly_ai_openai_agents import create_openai_agent_handler

support = config(
    key="customer-support-chat",
    handler=[create_openai_messages_handler(), create_openai_agent_handler()],
    tool_handlers={"lookup-order": lookup_order},
)

result = await support.invoke(user_input, context, {"tier": "premium"})
print(result.response)

await shutdown()  # before the process exits
```

**Node.js:**

```typescript
import { config, shutdown } from '@launchdarkly/ai-node';
import { createOpenAIHandler } from '@launchdarkly/ai-openai-messages';
import { createOpenAIAgentHandler } from '@launchdarkly/ai-openai-agents';

const support = config({
  key: 'customer-support-chat',
  handler: [createOpenAIHandler(), createOpenAIAgentHandler()],
  toolHandlers: { 'lookup-order': lookupOrder },
});

const result = await support.invoke(userInput, context, { tier: 'premium' });
console.log(result.response);

await shutdown();
```

**Errors.** If the OpenAI call fails, the SDK records the duration and a generation error, then re-raises. Let it propagate to your own error handling; don't add tracking calls.

**Parameters in Python.** `launchdarkly-ai-openai-messages` 0.2.x sends no variation parameters to OpenAI, so `temperature`, `max_output_tokens`, and the rest are ignored. The Node.js handler forwards them, mapping `max_tokens` to `max_output_tokens`. If a Python variation depends on its parameters, use a custom handler (Tier 3) and check the CHANGELOG for changes.

## Tier 3 — Custom handler (Azure OpenAI, LiteLLM, custom clients)

The handler packages create their own OpenAI client, so they don't cover Azure OpenAI deployments, OpenAI-compatible proxies such as LiteLLM, or a client with custom retries. Keep your existing call and wrap it in a custom handler. The SDK records the metrics from the usage you return:

```python
from openai import AsyncAzureOpenAI
from launchdarkly_ai_server import config, create_handler, parse_template

client = AsyncAzureOpenAI()  # reads AZURE_OPENAI_* from the environment

async def call_azure(ld_config, user_input, tool_handlers, variables, history):
    params = {k: v for k, v in ld_config["model"].get("parameters", {}).items() if k != "tools"}
    messages = [{**m, "content": parse_template(m["content"], variables)} for m in ld_config.get("messages", [])]
    response = await client.chat.completions.create(
        model=ld_config["model"]["name"],
        messages=[*messages, {"role": "user", "content": user_input}],
        **params,
    )
    return {
        "output": response.choices[0].message.content,
        "usage": {
            "input": response.usage.prompt_tokens,
            "output": response.usage.completion_tokens,
        },
    }

result = await config(
    key="customer-support-chat",
    handler=create_handler(("OpenAI", "messages"), call_azure),
).invoke(user_input, context)
```

```typescript
import { AzureOpenAI } from 'openai';
import { config, createHandler, parseTemplate } from '@launchdarkly/ai-node';

const client = new AzureOpenAI();

const callAzure = createHandler(['OpenAI', 'messages'], async (ldConfig, userInput, toolHandlers, variables) => {
  const { tools, ...params } = ldConfig.model.parameters ?? {};
  const messages = (ldConfig.messages ?? []).map((m) => ({ ...m, content: parseTemplate(m.content, variables ?? {}) }));
  const response = await client.chat.completions.create({
    model: ldConfig.model.name,
    messages: [...messages, { role: 'user', content: userInput ?? '' }],
    ...params,
  });
  return {
    output: response.choices[0].message.content,
    usage: { input: response.usage?.prompt_tokens, output: response.usage?.completion_tokens },
  };
});

const result = await config({ key: 'customer-support-chat', handler: callAzure }).invoke(userInput, context);
```

The provider name in `create_handler` must match the config's model provider exactly (`"OpenAI"`). A custom handler with an exact provider name takes precedence over the LangChain wildcard handler.

Two things every custom handler must do: render `{{name}}` placeholders with `parse_template` / `parseTemplate`, which the handler packages do for you, and drop `tools` from `model.parameters`, where attached tool definitions are stored in LaunchDarkly's format and rejected by the provider.

## Streaming

Use `stream()` instead of `invoke()`. See [streaming-tracking.md](streaming-tracking.md).
