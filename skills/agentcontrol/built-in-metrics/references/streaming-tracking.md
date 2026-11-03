# Streaming Metrics Tracking

Call `stream()` instead of `invoke()`. It records the same metrics as `invoke()`: duration, success/error, and tokens from the final usage. There's no separate streaming tracker and nothing to measure by hand.

**Time to first token is not recorded.** The current SDKs don't emit a TTFT event, and the stream's `done` event doesn't include the `track_data` you'd need to send one yourself. If TTFT matters, measure it in your own observability stack; the SDK's OpenTelemetry spans cover the call.

## Handler packages

The OpenAI, Anthropic, and LangChain handler packages stream natively:

```python
from launchdarkly_ai_server import config
from launchdarkly_ai_openai_messages import create_openai_messages_handler

async for event in config(key="customer-support-chat", handler=create_openai_messages_handler()).stream(
    user_input, {"kind": "user", "key": "user-123"}
):
    if event["type"] == "chunk":
        print(event["text"], end="", flush=True)
    else:
        # The final "done" event carries the full response and normalized usage
        print("\n", event["usage"])
```

```typescript
import { config } from '@launchdarkly/ai-node';
import { createOpenAIHandler } from '@launchdarkly/ai-openai-messages';

for await (const event of config({ key: 'customer-support-chat', handler: createOpenAIHandler() }).stream(
  userInput,
  { kind: 'user', key: 'user-123' },
)) {
  if (event.type === 'chunk') process.stdout.write(event.text);
  else console.log('\n', event.usage);
}
```

Structured output and streaming are mutually exclusive. `stream()` ignores any output format on the config; use `invoke()` for structured output.

## Custom handlers

Pass a stream function as the third argument to `create_handler` / `createHandler`. It yields `chunk` events, then one `done` event with the full output and the usage. The SDK records metrics from the `done` event:

```python
from openai import AsyncAzureOpenAI
from launchdarkly_ai_server import config, create_handler, parse_template

client = AsyncAzureOpenAI()

def to_messages(ld_config, user_input, variables):
    messages = [{**m, "content": parse_template(m["content"], variables)} for m in ld_config.get("messages", [])]
    return [*messages, {"role": "user", "content": user_input}]

async def call(ld_config, user_input, tool_handlers, variables, history):
    response = await client.chat.completions.create(
        model=ld_config["model"]["name"], messages=to_messages(ld_config, user_input, variables)
    )
    return {
        "output": response.choices[0].message.content,
        "usage": {"input": response.usage.prompt_tokens, "output": response.usage.completion_tokens},
    }

async def call_stream(ld_config, user_input, tool_handlers, variables, history):
    stream = await client.chat.completions.create(
        model=ld_config["model"]["name"],
        messages=to_messages(ld_config, user_input, variables),
        stream=True,
        stream_options={"include_usage": True},  # usage arrives on the final chunk
    )
    text, usage = "", {}
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            text += chunk.choices[0].delta.content
            yield {"type": "chunk", "text": chunk.choices[0].delta.content}
        if chunk.usage:
            usage = {"input": chunk.usage.prompt_tokens, "output": chunk.usage.completion_tokens}
    yield {"type": "done", "output": text, "usage": usage}

handler = create_handler(("OpenAI", "messages"), call, call_stream)

async for event in config(key="customer-support-chat", handler=handler).stream(user_input, context):
    ...
```

```typescript
import { config, createHandler } from '@launchdarkly/ai-node';

const handler = createHandler(
  ['OpenAI', 'messages'],
  async (ldConfig, userInput) => {
    /* non-streaming call, returns { output, usage } */
  },
  async function* (ldConfig, userInput) {
    let text = '';
    let usage = {};
    for await (const event of myProviderStream(ldConfig, userInput)) {
      if (event.delta) {
        text += event.delta;
        yield { type: 'chunk', text: event.delta };
      }
      // Read token counts from the provider's final stream event
      if (event.usage) usage = { input: event.usage.inputTokens, output: event.usage.outputTokens };
    }
    yield { type: 'done', output: text, usage };
  },
);
```

Without `include_usage` (or your provider's equivalent), the final usage is empty and the Monitoring tab shows generations with no tokens.
