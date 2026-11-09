# Legacy to current AI SDK: before and after

Each section shows the legacy pattern and its replacement in Python and Node.js. All current examples assume `LD_SDK_KEY` and the provider API keys are set in the environment.

Handler factory names follow `create_<provider>_<mode>_handler` (Python) and `create<Provider><Mode>Handler` (Node.js), for example `create_openai_messages_handler`, `create_openai_agents_handler`, `createOpenAIMessagesHandler`, `createOpenAIAgentsHandler`, `createClaudeMessagesHandler`, `createClaudeAgentsHandler`. Some published examples use other names, such as `createOpenAIHandler` or `create_openai_agent_handler`; these are not exported by the current packages.

## Contents

1. [API mapping](#api-mapping)
2. [Packages](#packages)
3. [Initialization](#initialization)
4. [Completion call: convenience function](#completion-call-convenience-function)
5. [Completion call: multi-provider handlers](#completion-call-multi-provider-handlers)
6. [Fallbacks and inspection](#fallbacks-and-inspection)
7. [Agent mode and tools](#agent-mode-and-tools)
8. [Registries](#registries)
9. [Streaming and history](#streaming-and-history)
10. [User feedback](#user-feedback)
11. [Judges](#judges)
12. [Agent graphs](#agent-graphs)

## API mapping

| Concern | Legacy | Current |
|---------|--------|---------|
| Init | `LDAIClient(ld_client)` / `initAi(ldClient)` | Lazy init from `LD_SDK_KEY`, or `init_client()` / `initClient()` |
| Completion | `completion_config()` / `completionConfig()` | `config().invoke()` or a convenience function |
| Agent | `agent_config()` / `agentConfig()` | `config().invoke()`; mode comes from the variation |
| Multi-agent | `agent_configs()` / `agentConfigs()` | `graph()` or a native framework runner |
| Managed objects | `create_model()`, `create_agent()` / `createModel().run()`, `createAgent()` | Convenience function or `config().invoke()` |
| Metrics | `create_tracker()`, `track_metrics_of`, `track_*` / `createTracker()`, `trackMetricsOf`, `track*` | Generation metrics are automatic on `invoke()` / `stream()`; a background `run_judge()` / `runJudge()` returns judge metrics that the worker must track |
| Feedback | `tracker.track_feedback()` / `tracker.trackFeedback()` | `get_client().track()` / `getClient().track()` with `result.track_data` / `result.trackData` |
| Fallback | Default config object with `enabled=False` | `try`/`except` around `invoke()`; `inspect_config()` / `inspectConfig()` to read state |
| Template variables | Fourth argument to `completion_config` / `completionConfig` | `variables=` (convenience, Python), `{ variables }` (convenience, Node), or third argument to `invoke()` (`{{name}}` without spaces; `{{ldContext.*}}` replaces `{{ldctx.*}}`) |
| Judges | `create_judge()`, `judge_config()` / `createJudge()`, `judgeConfig()` | Judges attached to the variation; `skip_judges` / `skipJudges` plus a durable worker that runs and tracks `run_judge()` / `runJudge()` results |
| Graphs | `agent_graph()`, `create_agent_graph()`, traversal helpers | `graph()`, `resolve_graph()` / `resolveGraph()` |
| Shutdown | `ld_client.close()` / `ldClient.close()` | `shutdown()` |

## Packages

| Language | Remove | Add |
|----------|--------|-----|
| Python | `launchdarkly-server-sdk-ai`, `launchdarkly-server-sdk-ai-openai`, `launchdarkly-server-sdk-ai-langchain` (imports `ldai`, `ldai_openai`, `ldai_langchain`) | `"launchdarkly-ai-server[ld]"` (or `launchdarkly-server-sdk` + `launchdarkly-ai-server`, or `"launchdarkly-ai-python[ld]"`); plus one `launchdarkly-ai-<provider>-<mode>` per handler |
| Node.js | `@launchdarkly/server-sdk-ai`, `@launchdarkly/server-sdk-ai-openai`, `@launchdarkly/server-sdk-ai-langchain`, `@launchdarkly/server-sdk-ai-vercel` | `@launchdarkly/ai-node` (bundles `@launchdarkly/node-server-sdk`), or `@launchdarkly/ai-server` for edge runtimes; plus one `@launchdarkly/ai-<provider>-<mode>` per handler |

```bash
# Python (3.12+)
pip uninstall launchdarkly-server-sdk-ai launchdarkly-server-sdk-ai-openai
pip install "launchdarkly-ai-server[ld]" launchdarkly-ai-openai-messages

# Node.js
npm uninstall @launchdarkly/server-sdk-ai @launchdarkly/server-sdk-ai-openai
npm install @launchdarkly/ai-node @launchdarkly/ai-openai-messages
```

Python modules are the package name with underscores (`launchdarkly_ai_server`, `launchdarkly_ai_openai_messages`). If you install `launchdarkly-ai-python`, import the core API from `launchdarkly_ai_python` instead.

## Initialization

Legacy:

```python
from ldclient import set_config, get
from ldclient.config import Config
from ldai import LDAIClient

set_config(Config("YOUR_SDK_KEY"))
aiclient = LDAIClient(get())
```

```typescript
import { init } from '@launchdarkly/node-server-sdk';
import { initAi } from '@launchdarkly/server-sdk-ai';

const ldClient = init('YOUR_SDK_KEY');
await ldClient.waitForInitialization({ timeout: 10 });
const aiClient = initAi(ldClient);
```

Current: delete both. The first AI call initializes the client from `LD_SDK_KEY`. Pre-warm or pass options only if needed, and always flush on exit:

```python
from launchdarkly_ai_server import init_client, shutdown

await init_client()   # optional
...
await shutdown()
```

```typescript
import { initClient, shutdown } from '@launchdarkly/ai-node';

await initClient();   // optional
// Edge or custom runtime: await initClient(preInitializedClient);
...
await shutdown();
```

If the app also evaluates ordinary feature flags, keep its existing server SDK client for those. To share one client, pass it to `init_client(client=ld_client)` / `initClient(ldClient)`.

## Completion call: convenience function

Use when the config serves one provider in one mode.

Legacy:

```python
from ldai import AICompletionConfigDefault
from ldai_openai import get_ai_metrics_from_response

config = aiclient.completion_config(
    "example-config-key",
    context,
    AICompletionConfigDefault(enabled=False),
    {"example_custom_variable": "example_custom_value"},
)
tracker = config.create_tracker()

if config.enabled:
    messages = [] if config.messages is None else config.messages
    completion = tracker.track_metrics_of(
        get_ai_metrics_from_response,
        lambda: openai_client.chat.completions.create(
            model=config.model.name,
            messages=[m.to_dict() for m in messages] + [{"role": "user", "content": user_input}],
        ),
    )
    text = completion.choices[0].message.content
```

```typescript
import { getAIMetricsFromResponse } from '@launchdarkly/server-sdk-ai-openai';

const aiConfig = await aiClient.completionConfig(
  'example-config-key',
  context,
  { enabled: false },
  { exampleCustomVariable: 'exampleCustomValue' },
);
const tracker = aiConfig.createTracker();
const response = await tracker.trackMetricsOf(getAIMetricsFromResponse, () =>
  openai.chat.completions.create({
    model: aiConfig.model?.name || 'gpt-4',
    messages: [...(aiConfig.messages || []), { role: 'user', content: userInput }],
  }),
);
const text = response.choices[0].message.content;
```

Current:

```python
from launchdarkly_ai_openai_messages import openai_messages

result = await openai_messages(
    "example-config-key",
    user_input,
    {"kind": "user", "key": "user-123"},
    variables={"example_custom_variable": "example_custom_value"},
)
text = result.response
```

```typescript
import { openaiMessages } from '@launchdarkly/ai-openai-messages';

const result = await openaiMessages(
  'example-config-key',
  userInput,
  { kind: 'user', key: 'user-123' },
  { variables: { exampleCustomVariable: 'exampleCustomValue' } },
);
const text = result.response;
```

Other convenience functions follow the same shape: `openai_agents` / `openaiAgents`, `claude_messages` / `claudeMessages`, `claude_agents` / `claudeAgents`, and so on. Check the handler package's exports.

## Completion call: multi-provider handlers

Use when variations of one config can target different providers or modes. The SDK routes to the handler that matches the variation's provider and mode.

```python
from launchdarkly_ai_server import config
from launchdarkly_ai_openai_messages import create_openai_messages_handler
from launchdarkly_ai_claude_messages import create_claude_messages_handler

result = await config(
    key="example-config-key",
    handler=[create_openai_messages_handler(), create_claude_messages_handler()],
).invoke(
    user_input,
    {"kind": "user", "key": "user-123"},
    {"example_custom_variable": "example_custom_value"},
)
print(result.response, result.usage)
```

```typescript
import { config } from '@launchdarkly/ai-node';
import { createOpenAIMessagesHandler } from '@launchdarkly/ai-openai-messages';
import { createClaudeMessagesHandler } from '@launchdarkly/ai-claude-messages';

const result = await config({
  key: 'example-config-key',
  handler: [createOpenAIMessagesHandler(), createClaudeMessagesHandler()],
}).invoke(
  userInput,
  { kind: 'user', key: 'user-123' },
  { exampleCustomVariable: 'exampleCustomValue' },
);
console.log(result.response, result.usage);
```

## Fallbacks and inspection

There is no fallback argument. `invoke()` raises when the variation is disabled (`RuntimeError: Variation '<key>' is disabled.` in Python, `Error: Variation <key> is not enabled` in Node.js) or when LaunchDarkly cannot be reached. Because handler packages also raise `RuntimeError` / `Error` when a run fails after starting (for example, hitting the tool-loop step limit), check `inspect_config()` / `inspectConfig()` in the error handler and re-raise when `enabled` is true so real run failures are not swallowed by the disabled-config fallback:

```python
from launchdarkly_ai_server import inspect_config
from launchdarkly_ai_openai_messages import openai_messages

FALLBACK = "Sorry, the assistant is unavailable right now."

try:
    result = await openai_messages("example-config-key", user_input, context)
    text = result.response
except Exception:
    if (await inspect_config("example-config-key", context))["enabled"]:
        raise
    logger.warning("AI config disabled or unreachable; using fallback")
    text = FALLBACK
```

```typescript
import { inspectConfig } from '@launchdarkly/ai-node';
import { openaiMessages } from '@launchdarkly/ai-openai-messages';

let text: string;
try {
  text = (await openaiMessages('example-config-key', userInput, context)).response;
} catch (err) {
  if ((await inspectConfig('example-config-key', context)).enabled) throw err;
  logger.warn('AI config disabled or unreachable; using fallback', err);
  text = FALLBACK;
}
```

To read state up front without raising and without calling a provider or emitting metrics, use `inspect_config()` / `inspectConfig()`. It returns `enabled`, `config` (the evaluated variation, or `None` / `null`), and `meta`:

```python
state = await inspect_config("example-config-key", context)
if not state["enabled"]:
    return FALLBACK
```

```typescript
const state = await inspectConfig('example-config-key', context);
if (!state.enabled) return FALLBACK;
```

Inspecting first and then invoking evaluates the flag twice; keep the `try`/`except` either way, because LaunchDarkly can become unreachable between the two calls.

## Agent mode and tools

Legacy agent mode used a separate evaluation call, and the app ran its own tool loop and tracked metrics:

```python
from ldai import AIAgentConfigDefault

agent = aiclient.agent_config(
    "example-config-key", context, AIAgentConfigDefault(enabled=False),
    {"example_custom_variable": "example_custom_value"},
)
if agent.enabled:
    tracker = agent.create_tracker()
    result = run_my_tool_loop(agent.instructions, tools={"get-prefs": get_preferences_fn})
    tracker.track_success()
```

```typescript
const agent = await aiClient.agentConfig(
  'example-config-key', context, { enabled: false },
  { exampleCustomVariable: 'exampleCustomValue' },
);
if (agent.enabled) {
  // agent.instructions + hand-written tool loop + agent.tracker.track*()
}
```

Current: completion and agent mode share `config()`. Register tool implementations by name; the handler runs the tool loop. Keys must match the tool names in the variation exactly, including case. Each tool function receives a single `args` dict (Python) or object (Node.js), not unpacked keyword arguments—wrap multi-argument functions (`lambda args: get_preferences_fn(**args)`) or LangChain `@tool` objects (`lambda args: get_preferences_tool.invoke(args)`).

```python
from launchdarkly_ai_server import config
from launchdarkly_ai_openai_agents import create_openai_agents_handler

result = await config(
    key="example-config-key",
    handler=[create_openai_agents_handler()],
    tool_handlers={"get-prefs": get_preferences_fn},
).invoke(
    "What are my preferences?",
    {"kind": "user", "key": "user-123"},
    {"example_custom_variable": "example_custom_value"},
)
```

```typescript
import { config } from '@launchdarkly/ai-node';
import { createOpenAIAgentsHandler } from '@launchdarkly/ai-openai-agents';

const result = await config({
  key: 'example-config-key',
  handler: [createOpenAIAgentsHandler()],
  toolHandlers: { 'get-prefs': getPreferencesFn },
}).invoke(
  'What are my preferences?',
  { kind: 'user', key: 'user-123' },
  { exampleCustomVariable: 'exampleCustomValue' },
);
```

Delete the hand-written loop, the provider tool-schema construction, and the manual `track_tool_call` / `trackToolCall` calls.

## Registries

Register handlers and tools once, then pass the registry to every call site. Use a scoped `Registry` when parts of the app need different handlers or tools, and `global_registry` / `globalRegistry` when one set fits the whole app.

```python
from launchdarkly_ai_server import Registry, config
from launchdarkly_ai_openai_messages import create_openai_messages_handler
from launchdarkly_ai_openai_agents import create_openai_agents_handler

openai_registry = Registry(
    handlers=[create_openai_messages_handler(), create_openai_agents_handler()],
    tools={"get-prefs": get_preferences_fn},
)

result = await config(key="example-config-key", registry=openai_registry).invoke(user_input, context)
```

```typescript
import { Registry, config } from '@launchdarkly/ai-node';
import { createOpenAIMessagesHandler } from '@launchdarkly/ai-openai-messages';
import { createOpenAIAgentsHandler } from '@launchdarkly/ai-openai-agents';

const openaiRegistry = new Registry({
  handlers: [createOpenAIMessagesHandler(), createOpenAIAgentsHandler()],
  tools: { 'get-prefs': getPreferencesFn },
});

const result = await config({ key: 'example-config-key', registry: openaiRegistry }).invoke(userInput, context);
```

Some providers expose built-in tools (for example Claude web search) that you assign as tool implementations instead of writing a function.

## Streaming and history

Replace `trackStreamMetricsOf` / manual time-to-first-token tracking with `stream()`. It takes the same arguments as `invoke()`.

```python
async for event in config(key="example-config-key", registry=openai_registry).stream(user_input, context):
    if event["type"] == "chunk":
        print(event["text"], end="")
    elif event["type"] == "done":
        final_text, usage = event["response"], event["usage"]
```

```typescript
for await (const event of config({ key: 'example-config-key', registry: openaiRegistry }).stream(userInput, context)) {
  if (event.type === 'chunk') process.stdout.write(event.text);
  if (event.type === 'done') console.log(event.usage);
}
```

For multi-turn chat, stop appending to a message array you merge with `config.messages`. Pass earlier turns as the fourth argument, `history`:

```python
history = [
    {"role": "user", "content": "Hi"},
    {"role": "assistant", "content": "Hello! How can I help?"},
]
result = await config(key="example-config-key", registry=openai_registry).invoke(
    user_input, context, None, history
)
```

## User feedback

The current SDKs do not have a `track_feedback` / `trackFeedback` helper on a tracker, because there is no tracker. Instead, `invoke()` returns `result.track_data` (Python) / `result.trackData` (Node.js) identifying the config, variation, version, and model. Pass it to `get_client().track()` / `getClient().track()` when the user gives thumbs up or down:

Legacy:

```python
from ldai.tracker import FeedbackKind

tracker.track_feedback({"kind": FeedbackKind.Positive})
```

```typescript
import { LDFeedbackKind } from '@launchdarkly/server-sdk-ai';

tracker.trackFeedback({ kind: LDFeedbackKind.Positive });
```

Current:

```python
from ldclient import Context
from launchdarkly_ai_server import config, get_client

result = await config(key="example-config-key", registry=openai_registry).invoke(user_input, context)

# When the user responds with thumbs up / down:
event = "$ld:ai:feedback:user:positive" if thumbs_up else "$ld:ai:feedback:user:negative"
get_client().track(event, Context.from_dict(context), result.track_data, 1)
```

```typescript
import { config, getClient } from '@launchdarkly/ai-node';

const result = await config({ key: 'example-config-key', registry: openaiRegistry }).invoke(userInput, context);

// When the user responds with thumbs up / down:
const event = thumbsUp ? '$ld:ai:feedback:user:positive' : '$ld:ai:feedback:user:negative';
getClient().track(event, context, result.trackData, 1);
```

`stream()` does not currently return `track_data`, so feedback on streamed responses cannot yet be attributed to a variation.

## Judges

Legacy apps created a judge and called it after each response. Now judges are attached to the config variation in LaunchDarkly and run inline by default on every `invoke()`. Delete `create_judge` / `createJudge` call sites once the judges are attached to the variation (ask the user to attach them if they aren't).

To keep latency low, skip inline judges and put the returned tasks on a durable
worker or queue. `run_judge()` / `runJudge()` executes the judge call but does
**not** emit the judge's evaluation metric. The worker must track the returned
score and supplied track data. Do not use a request-scoped `create_task()` or an
unobserved promise: the request can end before either the judge or its metric
finishes.

Python example for a long-lived process (use a durable queue instead when the
process can be suspended or terminated after the request):

```python
import asyncio
import threading
from ldclient import Context
from launchdarkly_ai_server import (
    config,
    get_client,
    global_registry,
    resolve_handlers,
    run_judge,
)

result = await config(
    key="example-config-key", registry=global_registry, skip_judges=True
).invoke(user_input, context)

handlers = resolve_handlers(global_registry, None) or []

def run_and_track_judge(task):
    judge_result = asyncio.run(run_judge(task, handlers))
    if judge_result and task.evaluation_metric_key:
        get_client().track(
            task.evaluation_metric_key,
            Context.from_dict(task.user_context),
            judge_result.track_data,
            judge_result.score,
        )

for task in result.judge_tasks or []:
    threading.Thread(
        target=run_and_track_judge,
        args=(task,),
        daemon=False,
    ).start()
```

Node.js worker example. Enqueue each `judgeTask` from the request handler, then
run this function in the queue consumer:

```typescript
import {
  config,
  getClient,
  globalRegistry,
  runJudge,
} from '@launchdarkly/ai-node';

const { response, judgeTasks } = await config({
  key: 'example-config-key',
  registry: globalRegistry,
  skipJudges: true,
}).invoke(userInput, context);

// Request path: enqueue the serializable task; do not run it as an unobserved promise.
for (const task of judgeTasks ?? []) {
  await judgeQueue.enqueue(task);
}

// Durable worker / queue consumer:
async function processJudgeTask(task) {
  const judgeResult = await runJudge(task, handlers);
  if (judgeResult && task.evaluationMetricKey) {
    getClient().track(
      task.evaluationMetricKey,
      task.userContext,
      judgeResult.trackData,
      judgeResult.score,
    );
  }
}
```

`handlers` is the list of provider handlers the judge configs can use. Remove
the legacy `track_judge_result` / `trackJudgeResult` calls, but preserve their
behavior with the current client's `track()` call shown above.

## Agent graphs

Replace `agent_configs` / `agentConfigs`, `agent_graph`, `create_agent_graph`, and hand-written traversal with `graph().invoke()`:

```python
from launchdarkly_ai_server import graph
from launchdarkly_ai_claude_agents import create_claude_agents_handler
from launchdarkly_ai_openai_agents import create_openai_agents_handler

result = await graph(
    "support-graph",
    handlers=[create_claude_agents_handler(), create_openai_agents_handler()],
    tool_handlers={"lookup-invoice": lookup_invoice},
).invoke("I was double charged", {"kind": "user", "key": "user-123"}, {"account_tier": "pro"})
print(result.response)
```

```typescript
import { graph } from '@launchdarkly/ai-node';
import { createClaudeAgentsHandler } from '@launchdarkly/ai-claude-agents';

const result = await graph('support-graph', {
  handlers: [createClaudeAgentsHandler()],
  toolHandlers: { 'lookup-invoice': lookupInvoice },
}).invoke('I was double charged', { kind: 'user', key: 'user-123' }, { account_tier: 'pro' });
console.log(result.response);
```

To keep running on a framework the app already uses, call `resolve_graph()` / `resolveGraph()` and pass the result to that framework's runner: `to_lang_graph` / `toLangGraph`, `to_openai_agents` / `toOpenAIAgents`, or `to_claude_agents` / `toClaudeAgents`. Check the handler package's exports and README for the exact call.
