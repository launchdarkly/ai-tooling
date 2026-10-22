# Anthropic Metrics Tracking

Anthropic has handler packages in both Python and Node.js: `-claude-messages` for completion mode (Messages API) and `-claude-agents` for agent mode (Claude Agent SDK). Walk the tiers from top to bottom and stop at the first one that fits.

## Tier 1 — Convenience function

**Python** (`pip install launchdarkly-ai-server launchdarkly-ai-claude-messages`):

```python
from launchdarkly_ai_claude_messages import claude_messages

# Reads LD_SDK_KEY and ANTHROPIC_API_KEY from the environment
result = await claude_messages("customer-support-chat", user_input, {"kind": "user", "key": "user-123"})
print(result.response)
```

**Node.js** (`npm install @launchdarkly/ai-node @launchdarkly/ai-claude-messages`):

```typescript
import { claudeMessages } from '@launchdarkly/ai-claude-messages';

const result = await claudeMessages('customer-support-chat', userInput, { kind: 'user', key: 'user-123' });
console.log(result.response);
```

## Tier 2 — `config()` with handler packages

```python
from launchdarkly_ai_server import config
from launchdarkly_ai_claude_messages import create_claude_messages_handler
from launchdarkly_ai_claude_agents import create_claude_agents_handler

result = await config(
    key="customer-support-chat",
    handler=[create_claude_messages_handler(), create_claude_agents_handler()],
).invoke(user_input, context)
```

```typescript
import { config } from '@launchdarkly/ai-node';
import { createClaudeMessagesHandler } from '@launchdarkly/ai-claude-messages';
import { createClaudeAgentsHandler } from '@launchdarkly/ai-claude-agents';

const result = await config({
  key: 'customer-support-chat',
  handler: [createClaudeMessagesHandler(), createClaudeAgentsHandler()],
}).invoke(userInput, context);
```

## Tier 3 — Custom handler

Use a custom handler to keep an existing Anthropic call, for example one with custom retries, prompt caching, or a proxy. The same shape works for any provider without a handler package (Cohere, Mistral, custom HTTP): call the model, then return the text and the token counts.

```python
from anthropic import AsyncAnthropic
from launchdarkly_ai_server import config, create_handler

client = AsyncAnthropic()

async def call_anthropic(ld_config, user_input, tool_handlers, variables, history):
    messages = ld_config.get("messages", [])
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    response = await client.messages.create(
        model=ld_config["model"]["name"],
        max_tokens=ld_config["model"].get("parameters", {}).get("max_tokens", 1024),
        system=system,
        messages=[
            *[m for m in messages if m["role"] != "system"],
            {"role": "user", "content": user_input},
        ],
    )
    return {
        "output": "".join(b.text for b in response.content if b.type == "text"),
        "usage": {"input": response.usage.input_tokens, "output": response.usage.output_tokens},
    }

result = await config(
    key="customer-support-chat",
    handler=create_handler(("Anthropic", "messages"), call_anthropic),
).invoke(user_input, context)
```

```typescript
import Anthropic from '@anthropic-ai/sdk';
import { config, createHandler } from '@launchdarkly/ai-node';

const client = new Anthropic();

const callAnthropic = createHandler(['Anthropic', 'messages'], async (ldConfig, userInput) => {
  const messages = ldConfig.messages ?? [];
  const response = await client.messages.create({
    model: ldConfig.model.name,
    max_tokens: Number(ldConfig.model.parameters?.max_tokens ?? 1024),
    system: messages.filter((m) => m.role === 'system').map((m) => m.content).join('\n'),
    messages: [
      ...messages.filter((m) => m.role !== 'system').map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content })),
      { role: 'user', content: userInput ?? '' },
    ],
  });
  return {
    output: response.content.flatMap((b) => (b.type === 'text' ? [b.text] : [])).join(''),
    usage: { input: response.usage.input_tokens, output: response.usage.output_tokens },
  };
});

const result = await config({ key: 'customer-support-chat', handler: callAnthropic }).invoke(userInput, context);
```

Anthropic's API takes the system prompt as a separate `system` parameter, so split it out of the config's messages. If the handler raises, the SDK records a generation error and re-raises.

## Streaming

Use `stream()` instead of `invoke()`. See [streaming-tracking.md](streaming-tracking.md).
