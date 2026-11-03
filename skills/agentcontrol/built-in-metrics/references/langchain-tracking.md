# LangChain / LangGraph Metrics Tracking

The LangChain handler packages work with any provider. `-langchain-messages` handles completion mode and `-langchain-agents` handles agent mode (a LangGraph ReAct agent). Both register for the wildcard provider `"*"`, so they serve any config whose provider has no exact-match handler.

## Choosing the model

By default the handler builds the chat model from the config's provider and model name. It recognizes only three providers:

| Config provider | Model class | Integration package |
|---|---|---|
| `Anthropic` | `ChatAnthropic` | `langchain-anthropic` |
| `Bedrock` | `ChatBedrockConverse` | `langchain-aws` |
| anything else | `ChatOpenAI` | `langchain-openai` |

For any other provider, such as Gemini, Mistral, or Cohere, pass `llm` as a factory. Otherwise the handler sends that provider's model name to OpenAI. The factory runs after the config is evaluated, so it gets the served model name and parameters:

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from launchdarkly_ai_langchain_messages import create_langchain_messages_handler

handler = create_langchain_messages_handler(
    lambda cfg: ChatGoogleGenerativeAI(
        model=cfg["model"]["name"],
        **{k: v for k, v in cfg["model"].get("parameters", {}).items() if k != "tools"},
    )
)
```

The factory receives the raw config, so drop `tools` from the parameters: attached tool definitions are stored there in LaunchDarkly's format, and the handler binds tools separately.

You can also pass a chat model instance, if every variation uses the same model.

## Tier 1 — Convenience function

```python
from launchdarkly_ai_langchain_messages import langchain_messages

result = await langchain_messages("customer-support-chat", user_input, {"kind": "user", "key": "user-123"})
print(result.response)
```

```typescript
import { langchainMessages } from '@launchdarkly/ai-langchain-messages';

const result = await langchainMessages('customer-support-chat', userInput, { kind: 'user', key: 'user-123' });
console.log(result.response);
```

## Tier 2 — `config()` with handler packages

**Python** (`pip install launchdarkly-ai-server launchdarkly-ai-langchain-messages launchdarkly-ai-langchain-agents langchain-openai`):

```python
from launchdarkly_ai_server import config
from launchdarkly_ai_langchain_messages import create_langchain_messages_handler
from launchdarkly_ai_langchain_agents import create_langchain_agents_handler

result = await config(
    key="research-agent",
    handler=[create_langchain_messages_handler(), create_langchain_agents_handler()],
    tool_handlers={"search-docs": search_docs},
).invoke(user_input, context)
```

**Node.js** (`npm install @launchdarkly/ai-node @launchdarkly/ai-langchain-messages @launchdarkly/ai-langchain-agents @langchain/openai`):

```typescript
import { config } from '@launchdarkly/ai-node';
import { createLangChainHandler } from '@launchdarkly/ai-langchain-messages';
import { createLangChainAgentsHandler } from '@launchdarkly/ai-langchain-agents';

const result = await config({
  key: 'research-agent',
  handler: [createLangChainHandler(), createLangChainAgentsHandler()],
  toolHandlers: { 'search-docs': searchDocs },
}).invoke(userInput, context);
```

The Node.js completion-mode factory is `createLangChainHandler`, not `createLangChainMessagesHandler`.

## Existing LangGraph graphs

If the app already builds a multi-agent LangGraph `StateGraph`, model the graph as a LaunchDarkly agent graph and run it with `to_lang_graph`, which records the same `$ld:ai:*` events per node plus graph-level metrics:

```python
from launchdarkly_ai_server import resolve_graph
from launchdarkly_ai_langchain_agents import to_lang_graph

context = {"kind": "user", "key": "user-123"}

run = to_lang_graph(
    resolve_graph("support-graph", context=context),
    {"tool_handlers": {"lookup-order": lookup_order}, "context": context},
)
result = await run.invoke("I was double charged")
```

`to_lang_graph` takes its options as a dict in the second argument, not as keyword arguments. For building the graph itself, see the `agent-graphs` skill.

## Errors and tokens

The handler reads token usage from LangChain's `usage_metadata`, so tokens are recorded for any integration that populates it. If the model call raises, the SDK records a generation error and re-raises.
