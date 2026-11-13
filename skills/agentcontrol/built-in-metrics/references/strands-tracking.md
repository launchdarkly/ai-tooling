# Strands Agents Metrics Tracking

**There is no LaunchDarkly handler package for Strands.** Strands owns its agent loop and runs against Anthropic, OpenAI, or Bedrock by swapping the `model` argument, so wrap the agent turn in a custom handler. The SDK then records duration, success/error, and the tokens you return.

The Strands `AgentResult` exposes `metrics.accumulated_usage` (Python) / `metrics.accumulatedUsage` (Node.js), which already sums tokens across every model call in the turn, including tool-calling round trips. The key names are camelCase even in Python: `inputTokens`, `outputTokens`.

## Custom handler (agent mode)

Agent-mode configs carry `instructions` instead of `messages`. Register the same function once per provider your variations serve; `ld_config["provider"]["name"]` tells you which model class to build:

```python
from strands import Agent
from strands.models.anthropic import AnthropicModel
from strands.models.bedrock import BedrockModel
from strands.models.openai import OpenAIModel
from launchdarkly_ai_server import config, create_handler

def build_model(ld_config):
    name = ld_config["model"]["name"]
    params = {k: v for k, v in ld_config["model"].get("parameters", {}).items() if k != "tools"}
    provider = ld_config["provider"]["name"]
    if provider == "Anthropic":
        max_tokens = params.pop("max_tokens", 1024)
        # anthropic 2.x no longer accepts temperature, top_p, or top_k
        for k in ("temperature", "top_p", "top_k"):
            params.pop(k, None)
        return AnthropicModel(model_id=name, max_tokens=max_tokens, params=params or None)
    if provider == "OpenAI":
        return OpenAIModel(model_id=name, params=params)
    return BedrockModel(model_id=name, **params)

async def run_strands(ld_config, user_input, tool_handlers, variables, history):
    agent = Agent(
        model=build_model(ld_config),
        system_prompt=ld_config.get("instructions", ""),
        tools=my_strands_tools,
    )
    result = await agent.invoke_async(user_input)
    usage = result.metrics.accumulated_usage or {}
    return {
        "output": str(result),
        "usage": {"input": usage.get("inputTokens", 0), "output": usage.get("outputTokens", 0)},
    }

handlers = [create_handler((provider, "agent"), run_strands) for provider in ("Anthropic", "OpenAI", "Bedrock")]

result = await config(key="research-agent", handler=handlers).invoke(user_input, context)
```

Drop `tools` from the model parameters before passing them to the Strands model class; Strands takes tools through the `Agent` constructor.

**Tool-call metrics.** The SDK records `$ld:ai:tool_call` for the functions it hands your handler in `tool_handlers`. Tools that Strands calls directly, as in the example above, aren't recorded. To record them, pass `tool_handlers` to `config()` and build the Strands tools from the `tool_handlers` argument your handler receives, for example by wrapping each one with Strands' `@tool` decorator.

## Node.js

The Strands TypeScript SDK ships `BedrockModel` and `OpenAIModel` only, with no `AnthropicModel`. The same pattern applies: `createHandler([provider, 'agent'], fn)`, and read `result.metrics.accumulatedUsage` for tokens. Variations that serve Anthropic through Strands need the Python SDK today.

## Shut down before exit

Strands examples are often short-lived scripts. Call `await shutdown()` after the last turn so trailing events are flushed.
