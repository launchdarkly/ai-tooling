# Gemini / Google GenAI Metrics Tracking

There's no Gemini-specific handler package. Configs served from Gemini have the provider name `Gemini`. Use the LangChain handler with a model factory, or wrap your existing `google-genai` call in a custom handler.

## Tier 2 — LangChain handler with a model factory

The LangChain handler doesn't build Gemini models by default; without a factory it would send the Gemini model name to OpenAI. Pass a factory that builds `ChatGoogleGenerativeAI` from the served config:

```bash
pip install launchdarkly-ai-server launchdarkly-ai-langchain-messages langchain-google-genai
```

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from launchdarkly_ai_server import config
from launchdarkly_ai_langchain_messages import create_langchain_messages_handler

gemini = create_langchain_messages_handler(
    lambda cfg: ChatGoogleGenerativeAI(
        model=cfg["model"]["name"],
        **{k: v for k, v in cfg["model"].get("parameters", {}).items() if k != "tools"},
    )
)

# Reads GOOGLE_API_KEY from the environment
result = await config(key="customer-support-chat", handler=gemini).invoke(user_input, context)
```

If other variations of the same config use OpenAI or Anthropic, pass their exact-provider handlers too. They take precedence over the LangChain wildcard, so the factory only runs for Gemini variations.

## Tier 3 — Custom handler around `google-genai`

```python
from google import genai
from google.genai import types
from launchdarkly_ai_server import config, create_handler, parse_template

client = genai.Client()  # reads GOOGLE_API_KEY

async def call_gemini(ld_config, user_input, tool_handlers, variables, history):
    messages = [{**m, "content": parse_template(m["content"], variables)} for m in ld_config.get("messages", [])]
    params = ld_config["model"].get("parameters", {})
    response = await client.aio.models.generate_content(
        model=ld_config["model"]["name"],
        contents=[
            *[
                types.Content(role="model" if m["role"] == "assistant" else "user", parts=[types.Part(text=m["content"])])
                for m in messages
                if m["role"] != "system"
            ],
            types.Content(role="user", parts=[types.Part(text=user_input)]),
        ],
        config=types.GenerateContentConfig(
            system_instruction="\n".join(m["content"] for m in messages if m["role"] == "system") or None,
            temperature=params.get("temperature"),
            max_output_tokens=params.get("max_tokens"),
        ),
    )
    usage = response.usage_metadata
    return {
        "output": response.text or "",
        "usage": {"input": usage.prompt_token_count or 0, "output": usage.candidates_token_count or 0},
    }

result = await config(
    key="customer-support-chat",
    handler=create_handler(("Gemini", "messages"), call_gemini),
).invoke(user_input, context)
```

**Node.js** with `@google/genai`:

```typescript
import { GoogleGenAI } from '@google/genai';
import { config, createHandler, parseTemplate } from '@launchdarkly/ai-node';

const ai = new GoogleGenAI({});

const callGemini = createHandler(['Gemini', 'messages'], async (ldConfig, userInput, toolHandlers, variables) => {
  const messages = (ldConfig.messages ?? []).map((m) => ({ ...m, content: parseTemplate(m.content, variables ?? {}) }));
  const response = await ai.models.generateContent({
    model: ldConfig.model.name,
    contents: [
      ...messages
        .filter((m) => m.role !== 'system')
        .map((m) => ({ role: m.role === 'assistant' ? 'model' : 'user', parts: [{ text: m.content }] })),
      { role: 'user', parts: [{ text: userInput ?? '' }] },
    ],
    config: {
      systemInstruction: messages.filter((m) => m.role === 'system').map((m) => m.content).join('\n') || undefined,
    },
  });
  return {
    output: response.text ?? '',
    usage: {
      input: response.usageMetadata?.promptTokenCount ?? 0,
      output: response.usageMetadata?.candidatesTokenCount ?? 0,
    },
  };
});

const result = await config({ key: 'customer-support-chat', handler: callGemini }).invoke(userInput, context);
```

Gemini calls the assistant role `model` and takes the system prompt as `system_instruction`, so map both from the config's messages. For Vertex AI, configs use the provider name `Vertex`; register the same function with `("Vertex", "messages")` and a `genai.Client(vertexai=True, ...)`.
