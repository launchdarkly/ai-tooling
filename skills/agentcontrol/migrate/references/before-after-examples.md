# Before/After Examples

Paired code snippets for the Stage 2 call-site swap. Each example shows the same call before extraction and after routing it through the LaunchDarkly AI SDK, with the original call kept as the fallback. Metrics are recorded automatically in every "after" version; there's no Stage 4 code to add.

---

## Example 1: Python + OpenAI — completion mode, custom handler

A typical one-shot chat app. Hardcoded model, temperature, max tokens, and system prompt. This example wraps the existing Chat Completions call in a custom handler, so the variation's `temperature` and `max_tokens` keep reaching OpenAI.

### Before

```python
from openai import OpenAI

openai_client = OpenAI()

def answer(user_question: str) -> str:
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        temperature=0.7,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Answer concisely."},
            {"role": "user", "content": user_question},
        ],
    )
    return response.choices[0].message.content
```

### After

```python
import logging
from openai import AsyncOpenAI, OpenAI
from launchdarkly_ai_server import config, create_handler, parse_template

logger = logging.getLogger(__name__)
openai_client = OpenAI()
async_openai = AsyncOpenAI()

def answer_hardcoded(user_question: str) -> str:
    # The original function, unchanged, kept as the fallback
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        temperature=0.7,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Answer concisely."},
            {"role": "user", "content": user_question},
        ],
    )
    return response.choices[0].message.content

async def call_openai(ld_config, user_input, tool_handlers, variables, history):
    # Attached tools are stored in parameters["tools"] in LaunchDarkly's format, not OpenAI's
    params = {k: v for k, v in ld_config["model"].get("parameters", {}).items() if k != "tools"}
    messages = [{**m, "content": parse_template(m["content"], variables)} for m in ld_config.get("messages", [])]
    response = await async_openai.chat.completions.create(
        model=ld_config["model"]["name"],
        messages=[*messages, {"role": "user", "content": user_input}],
        **params,
    )
    return {
        "output": response.choices[0].message.content,
        "usage": {"input": response.usage.prompt_tokens, "output": response.usage.completion_tokens},
    }

chat = config(key="chat-assistant", handler=create_handler(("OpenAI", "messages"), call_openai))

async def answer(user_id: str, user_question: str) -> str:
    try:
        result = await chat.invoke(user_question, {"kind": "user", "key": user_id})
        return result.response
    except RuntimeError:
        logger.warning("chat-assistant unavailable; using hardcoded fallback")
        return answer_hardcoded(user_question)
```

### What changed

- Model, parameters, and prompt come from the served config (`ld_config["model"]`, `ld_config["messages"]`) instead of literals
- The provider call moved into a handler, and `**params` forwards every variation parameter except `tools`, which a custom handler has to convert itself if the variation has tools
- `config()` is built once at module scope; `invoke()` evaluates targeting per request with a plain-dict context
- The original function is renamed to `answer_hardcoded` and runs when `invoke()` raises
- Duration, tokens, and success/error are recorded from the handler's return value

If you don't need to keep the Chat Completions call, `create_openai_messages_handler()` replaces `call_openai` entirely. In Python 0.2.x it doesn't forward variation parameters; see the caveat in SKILL.md Stage 2.

---

## Example 2: Node.js + Anthropic — completion mode, handler package

Anthropic separates the system message from the messages array. The Claude handler package does that split itself, and forwards the variation's parameters.

### Before

```typescript
import Anthropic from '@anthropic-ai/sdk';

const anthropic = new Anthropic();

export async function answer(userQuestion: string): Promise<string> {
  const response = await anthropic.messages.create({
    model: 'claude-sonnet-4-5',
    max_tokens: 1024,
    system: 'You are a helpful assistant. Answer concisely.',
    messages: [{ role: 'user', content: userQuestion }],
  });
  const text = response.content.find((b) => b.type === 'text');
  return text?.type === 'text' ? text.text : '';
}
```

### After

```typescript
import Anthropic from '@anthropic-ai/sdk';
import { config } from '@launchdarkly/ai-node';
import { createClaudeMessagesHandler } from '@launchdarkly/ai-claude-messages';

const anthropic = new Anthropic();

// The original function, unchanged, kept as the fallback
async function answerHardcoded(userQuestion: string): Promise<string> {
  const response = await anthropic.messages.create({
    model: 'claude-sonnet-4-5',
    max_tokens: 1024,
    system: 'You are a helpful assistant. Answer concisely.',
    messages: [{ role: 'user', content: userQuestion }],
  });
  const text = response.content.find((b) => b.type === 'text');
  return text?.type === 'text' ? text.text : '';
}

const chat = config({ key: 'chat-assistant', handler: createClaudeMessagesHandler() });

export async function answer(userId: string, userQuestion: string): Promise<string> {
  try {
    const result = await chat.invoke(userQuestion, { kind: 'user', key: userId });
    return result.response;
  } catch (err) {
    if (err instanceof Anthropic.APIError) throw err;
    console.warn('chat-assistant unavailable; using hardcoded fallback', err);
    return answerHardcoded(userQuestion);
  }
}
```

### What changed

- Hardcoded model, system prompt, and `max_tokens` are gone from the request path
- No `convertToAnthropicFormat` helper: the handler hoists system messages into Anthropic's `system` parameter
- The SDK reads `LD_SDK_KEY` and `ANTHROPIC_API_KEY` from the environment and initializes lazily
- Anthropic API errors propagate; anything else from `invoke()` means the config is unavailable, so the fallback runs

---

## Example 3: Python + LangGraph — agent mode

`create_agent` (in `langchain.agents`) takes a model, tools, and `system_prompt` — a natural fit for **agent mode**. The LangChain agents handler builds the same ReAct agent from the served config: the model from `model.name` and `model.parameters`, the system prompt from `instructions`, and the tools from the config plus `tool_handlers`. This example shows the end state after Stage 3, once the tools are attached to the config.

### Before

```python
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from my_tools import search_kb, calculator

llm = ChatOpenAI(model="gpt-4o", temperature=0.3)

agent = create_agent(
    llm,
    [search_kb, calculator],
    system_prompt=(
        "You are a technical support assistant. Use the search_kb tool to look up "
        "documentation, and the calculator tool for math. Always cite sources."
    ),
)

def run_support(user_question: str) -> str:
    result = agent.invoke({"messages": [{"role": "user", "content": user_question}]})
    return result["messages"][-1].content
```

### After

```python
import logging
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from launchdarkly_ai_server import config
from launchdarkly_ai_langchain_agents import create_langchain_agents_handler
from my_tools import search_kb, calculator

logger = logging.getLogger(__name__)

# The original agent, unchanged, kept as the fallback
fallback_agent = create_agent(
    ChatOpenAI(model="gpt-4o", temperature=0.3),
    [search_kb, calculator],
    system_prompt=(
        "You are a technical support assistant. Use the search_kb tool to look up "
        "documentation, and the calculator tool for math. Always cite sources."
    ),
)

support = config(
    key="support-agent",
    handler=create_langchain_agents_handler(),
    tool_handlers={
        "search-kb": lambda args: search_kb.invoke(args),
        "calculator": lambda args: calculator.invoke(args),
    },
)

async def run_support(user_id: str, user_question: str) -> str:
    try:
        result = await support.invoke(user_question, {"kind": "user", "key": user_id})
        return result.response
    except RuntimeError:
        logger.warning("support-agent unavailable; using hardcoded fallback")
        out = await fallback_agent.ainvoke({"messages": [{"role": "user", "content": user_question}]})
        return out["messages"][-1].content
```

### What changed

- The handler builds the agent per call from the served variation, so a model, prompt, or tool change in LaunchDarkly takes effect on the next request
- The model is built with every variation parameter; no hand-rolled `ChatOpenAI(model=...)` on the served path
- The LangChain `@tool` objects are wrapped as one-argument functions keyed by their LaunchDarkly tool keys
- One `invoke()` is one agent turn: duration and tokens cover every model call in the loop, and each tool call records `$ld:ai:tool_call`
- The original agent stays as the fallback

For variations served from a provider the LangChain handler doesn't build itself (anything other than OpenAI, Anthropic, and Bedrock), pass a model factory: `create_langchain_agents_handler(lambda cfg: ChatGoogleGenerativeAI(model=cfg["model"]["name"]))`.

---

## Rules of thumb across all three examples

1. **The request handler's logic and return shape stay the same.** Only where the model, prompt, and parameters come from changes, plus the `try` / `except RuntimeError` around `invoke()`. The signature does change: the handler becomes async and takes a context source such as `user_id`. Update every caller, or keep a sync wrapper that calls `asyncio.run()` for scripts.
2. **The fallback is the original code**, renamed. See [fallback-defaults-pattern.md](fallback-defaults-pattern.md).
3. **Build a context per request.** It's a plain dict carrying targeting inputs — user ID, plan tier, region. Reuse the attributes the app already uses for feature flags.
4. **Build `config()` once; call `invoke()` per request.** The instance holds routing and tools; each `invoke()` evaluates targeting fresh.
5. **Placeholders are `{{name}}`, no spaces,** filled from the third argument to `invoke()`. Custom handlers render them with `parse_template`.
