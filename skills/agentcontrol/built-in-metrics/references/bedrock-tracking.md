# AWS Bedrock Metrics Tracking

There's no Bedrock-specific handler package. Configs served from Bedrock have the provider name `Bedrock`. Use the LangChain handler, which recognizes Bedrock, or wrap your existing boto3 call in a custom handler.

## Tier 2 — LangChain handler

The LangChain handler builds a `ChatBedrockConverse` model for any config whose provider is `Bedrock`. If the variation sets a model region, it's prepended to the model ID as the inference-profile prefix.

```bash
pip install launchdarkly-ai-server launchdarkly-ai-langchain-messages langchain-aws
```

```python
from launchdarkly_ai_server import config
from launchdarkly_ai_langchain_messages import create_langchain_messages_handler

# AWS credentials come from the standard boto3 chain
result = await config(
    key="customer-support-chat",
    handler=create_langchain_messages_handler(),
).invoke(user_input, context)
```

See [langchain-tracking.md](langchain-tracking.md) for agent mode and Node.js.

## Tier 3 — Custom handler around boto3 Converse

Use this to keep an existing boto3 client, with its credentials, retries, or guardrail settings, and add no new dependencies:

```python
import asyncio
import boto3
from launchdarkly_ai_server import config, create_handler, parse_template

bedrock = boto3.client("bedrock-runtime")

async def call_bedrock(ld_config, user_input, tool_handlers, variables, history):
    messages = [{**m, "content": parse_template(m["content"], variables)} for m in ld_config.get("messages", [])]
    params = ld_config["model"].get("parameters", {})
    response = await asyncio.to_thread(
        bedrock.converse,
        modelId=ld_config["model"]["name"],
        system=[{"text": m["content"]} for m in messages if m["role"] == "system"],
        messages=[
            *[{"role": m["role"], "content": [{"text": m["content"]}]} for m in messages if m["role"] != "system"],
            {"role": "user", "content": [{"text": user_input}]},
        ],
        inferenceConfig={k: v for k, v in {
            "maxTokens": params.get("max_tokens"),
            "temperature": params.get("temperature"),
        }.items() if v is not None},
    )
    return {
        "output": "".join(b.get("text", "") for b in response["output"]["message"]["content"]),
        "usage": {
            "input": response["usage"]["inputTokens"],
            "output": response["usage"]["outputTokens"],
        },
    }

result = await config(
    key="customer-support-chat",
    handler=create_handler(("Bedrock", "messages"), call_bedrock),
).invoke(user_input, context)
```

**Node.js** with `@aws-sdk/client-bedrock-runtime`:

```typescript
import { BedrockRuntimeClient, ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { config, createHandler, parseTemplate } from '@launchdarkly/ai-node';

const bedrock = new BedrockRuntimeClient({});

const callBedrock = createHandler(['Bedrock', 'messages'], async (ldConfig, userInput, toolHandlers, variables) => {
  const messages = (ldConfig.messages ?? []).map((m) => ({ ...m, content: parseTemplate(m.content, variables ?? {}) }));
  const response = await bedrock.send(
    new ConverseCommand({
      modelId: ldConfig.model.name,
      system: messages.filter((m) => m.role === 'system').map((m) => ({ text: m.content })),
      messages: [
        ...messages
          .filter((m) => m.role !== 'system')
          .map((m) => ({ role: m.role as 'user' | 'assistant', content: [{ text: m.content }] })),
        { role: 'user', content: [{ text: userInput ?? '' }] },
      ],
    }),
  );
  return {
    output: (response.output?.message?.content ?? []).map((b) => b.text ?? '').join(''),
    usage: { input: response.usage?.inputTokens, output: response.usage?.outputTokens },
  };
});

const result = await config({ key: 'customer-support-chat', handler: callBedrock }).invoke(userInput, context);
```

The handler forwards `temperature` only when the variation sets it. Some newer models, such as Claude Haiku 5.5, reject `temperature`, so leave it out of variations that serve them.

The Converse API returns the same `usage` shape for every Bedrock model family, so one handler covers Claude, Llama, Nova, and the rest. For the older `InvokeModel` API, token counts are in model-specific response fields; return them in the same `usage` dict.
