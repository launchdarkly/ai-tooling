---
name: aiconfig-online-evals
description: Attach judges to AI Config variations for automatic LLM-as-a-judge evaluation. Create custom judges, configure sampling rates, and monitor quality scores.
compatibility: Requires LaunchDarkly API access token with ai-configs:write permission. SDK versions Python v0.18.0+ or Node.js v0.17.0+ for automatic metric recording and the consolidated `track_judge_result` / `trackJudgeResult` API.
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# AI Config Online Evaluations

Attach judges to AI Config variations for automatic quality scoring using LLM-as-a-judge methodology. Judges evaluate responses and return scores between 0.0 and 1.0.

## Prerequisites

- LaunchDarkly account with AI Configs enabled
- API access token with write permissions
- Existing AI Config with variations (use `aiconfig-create` skill)
- For automatic metric recording and the consolidated judge-result API: Python AI SDK v0.18.0+ or Node.js AI SDK v0.17.0+

## API Key Detection

1. **Check environment variables** - `LAUNCHDARKLY_API_KEY`, `LAUNCHDARKLY_API_TOKEN`, `LD_API_KEY`
2. **Check MCP config** - Claude: `~/.claude/config.json` -> `mcpServers.launchdarkly.env.LAUNCHDARKLY_API_KEY`
3. **Prompt user** - Only if detection fails

## Core Concepts

### What Are Judges?

Judges are specialized AI Configs in **judge mode** that evaluate responses from other AI Configs. They use an LLM to score outputs and return structured results:

```json
{
  "score": 0.85,
  "reasoning": "Answered correctly with one minor omission"
}
```

### Built-in Judges

LaunchDarkly provides three pre-configured judges:

| Judge | Metric Key | Measures |
|-------|-----------|----------|
| Accuracy | `$ld:ai:judge:accuracy` | How correct and grounded the response is |
| Relevance | `$ld:ai:judge:relevance` | How well it addresses the user request |
| Toxicity | `$ld:ai:judge:toxicity` | Harmful or unsafe phrasing (lower = safer) |

### Completion Mode Only

Judges can only be attached to **completion mode** AI Configs in the UI. For agent mode or custom pipelines, use programmatic evaluation via the SDK.

### Restrictions

- Cannot attach judges to judges (no recursion)
- Cannot attach multiple judges with the same metric key to a single variation
- Cannot view/edit model parameters or tools on judge variations

## Workflow

### Step 1: Create Custom Judges (Optional)

For domain-specific evaluation, create judge AI Configs:

```bash
# Create judge config
curl -X POST "https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-configs" \
  -H "Authorization: {api_token}" \
  -H "Content-Type: application/json" \
  -H "LD-API-Version: beta" \
  -d '{
    "key": "security-judge",
    "name": "Security Judge",
    "mode": "judge",
    "evaluationMetricKey": "security",
    "isInverted": false
  }'
```

> **Note:** Set `isInverted: true` for metrics like toxicity where 0.0 is better.

Then add a variation with the evaluation prompt:

```bash
curl -X POST "https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-configs/security-judge/variations" \
  -H "Authorization: {api_token}" \
  -H "Content-Type: application/json" \
  -H "LD-API-Version: beta" \
  -d '{
    "key": "default",
    "name": "Default",
    "messages": [
      {
        "role": "system",
        "content": "You are a security auditor. Score from 0.0 to 1.0:\n- 1.0: No security issues\n- 0.7-0.9: Minor issues\n- 0.4-0.6: Moderate issues\n- 0.1-0.3: Serious vulnerabilities\n- 0.0: Critical vulnerabilities\n\nCheck for: SQL injection, XSS, hardcoded secrets, command injection."
      }
    ],
    "modelConfigKey": "OpenAI.gpt-4o-mini",
    "model": {
      "parameters": {
        "temperature": 0.3
      }
    }
  }'
```

### Step 2: Attach Judges to Variations

Use the variation PATCH endpoint:

```bash
curl -X PATCH "https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-configs/{configKey}/variations/{variationKey}" \
  -H "Authorization: {api_token}" \
  -H "Content-Type: application/json" \
  -H "LD-API-Version: beta" \
  -d '{
    "judgeConfiguration": {
      "judges": [
        {"judgeConfigKey": "security-judge", "samplingRate": 1.0},
        {"judgeConfigKey": "api-contract-judge", "samplingRate": 0.5}
      ]
    }
  }'
```

> **Important:** The `judges` array **replaces all existing** judge attachments. An empty array removes all judges.

### Step 3: Set Fallthrough on Judges

Each judge AI Config needs its fallthrough set to the enabled variation. AI Configs default to the "disabled" variation (index 0).

> **Note:** `turnTargetingOn` does not work for AI Configs. Use `updateFallthroughVariationOrRollout` instead.

```bash
# First get the variation ID for "Default" from GET targeting response
curl -X PATCH "https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-configs/security-judge/targeting" \
  -H "Authorization: {api_token}" \
  -H "Content-Type: application/json; domain-model=launchdarkly.semanticpatch" \
  -H "LD-API-Version: beta" \
  -d '{
    "environmentKey": "production",
    "instructions": [{
      "kind": "updateFallthroughVariationOrRollout",
      "variationId": "your-default-variation-uuid"
    }]
  }'
```

## Python Implementation

```python
import requests
import os
from typing import Optional

class AIConfigJudges:
    """Manager for AI Config judge attachments"""

    def __init__(self, api_token: str, project_key: str):
        self.api_token = api_token
        self.project_key = project_key
        self.base_url = "https://app.launchdarkly.com/api/v2"
        self.headers = {
            "Authorization": api_token,
            "Content-Type": "application/json",
            "LD-API-Version": "beta"
        }

    def attach_judges(self, config_key: str, variation_key: str,
                      judges: list[dict]) -> dict:
        """
        Attach judges to a variation.

        Args:
            config_key: AI Config key
            variation_key: Variation key
            judges: List of {"judgeConfigKey": str, "samplingRate": float}
        """
        url = f"{self.base_url}/projects/{self.project_key}/ai-configs/{config_key}/variations/{variation_key}"

        response = requests.patch(url, headers=self.headers, json={
            "judgeConfiguration": {"judges": judges}
        })

        if response.status_code == 200:
            print(f"[OK] Attached {len(judges)} judges to {config_key}/{variation_key}")
            return response.json()
        print(f"[ERROR] {response.status_code}: {response.text}")
        return {}

    def create_judge(self, key: str, name: str, metric_key: str,
                     system_prompt: str, model: str = "OpenAI.gpt-4o-mini",
                     is_inverted: bool = False) -> dict:
        """
        Create a judge AI Config.

        Args:
            key: Judge config key
            name: Display name
            metric_key: Metric key for scoring (appears as $ld:ai:judge:{metric_key})
            system_prompt: Evaluation instructions
            is_inverted: True if lower scores are better (e.g., toxicity)
        """
        # Create config
        config_url = f"{self.base_url}/projects/{self.project_key}/ai-configs"
        response = requests.post(config_url, headers=self.headers, json={
            "key": key,
            "name": name,
            "mode": "judge",
            "evaluationMetricKey": metric_key,
            "isInverted": is_inverted
        })

        if response.status_code not in [200, 201]:
            print(f"[ERROR] Creating config: {response.text}")
            return {}

        # Create variation
        var_url = f"{self.base_url}/projects/{self.project_key}/ai-configs/{key}/variations"
        response = requests.post(var_url, headers=self.headers, json={
            "key": "default",
            "name": "Default",
            "messages": [{"role": "system", "content": system_prompt}],
            "modelConfigKey": model,
            "model": {"parameters": {"temperature": 0.3}}
        })

        if response.status_code in [200, 201]:
            print(f"[OK] Created judge: {key}")
            return response.json()
        print(f"[ERROR] Creating variation: {response.text}")
        return {}

    def set_fallthrough(self, config_key: str, environment: str,
                        variation_key: str = "default") -> bool:
        """
        Set fallthrough to enable a judge config.

        Note: turnTargetingOn doesn't work for AI Configs. Instead, set the
        fallthrough from disabled (index 0) to the enabled variation.
        """
        # Get variation ID
        url = f"{self.base_url}/projects/{self.project_key}/ai-configs/{config_key}/targeting"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            print(f"[ERROR] {response.status_code}: {response.text}")
            return False

        targeting = response.json()
        variation_id = None
        for var in targeting.get("variations", []):
            if var.get("key") == variation_key or var.get("name") == variation_key:
                variation_id = var.get("_id")
                break

        if not variation_id:
            print(f"[ERROR] Variation '{variation_key}' not found")
            return False

        # Set fallthrough
        response = requests.patch(url, headers={
            **self.headers,
            "Content-Type": "application/json; domain-model=launchdarkly.semanticpatch"
        }, json={
            "environmentKey": environment,
            "instructions": [{
                "kind": "updateFallthroughVariationOrRollout",
                "variationId": variation_id
            }]
        })

        if response.status_code == 200:
            print(f"[OK] Fallthrough set for {config_key}")
            return True
        print(f"[ERROR] {response.status_code}: {response.text}")
        return False
```

## SDK: Automatic Evaluation

When using `create_chat()` + `invoke()`, attached judges evaluate automatically:

```python
import os
import json
import asyncio
import ldclient
from ldclient import Context
from ldclient.config import Config
from ldai import LDAIClient, AICompletionConfigDefault

sdk_key = os.getenv('LAUNCHDARKLY_SDK_KEY')
ai_config_key = os.getenv('LAUNCHDARKLY_AI_CONFIG_KEY', 'sample-ai-config')

async def async_main():
    ldclient.set_config(Config(sdk_key))
    aiclient = LDAIClient(ldclient.get())

    context = (
        Context.builder('example-user-key')
        .kind('user')
        .name('Sandy')
        .build()
    )

    default_value = AICompletionConfigDefault(enabled=False)

    # create_chat() initializes with judges from AI Config
    chat = await aiclient.create_chat(ai_config_key, context, default_value, {})

    if not chat:
        print(f"AI chat configuration not enabled for: {ai_config_key}")
        return

    user_input = 'How can LaunchDarkly help me?'

    # invoke() automatically evaluates with attached judges
    chat_response = await chat.invoke(user_input)
    print("Response:", chat_response.message.content)

    # Await evaluation results
    if chat_response.evaluations and len(chat_response.evaluations) > 0:
        eval_results = await asyncio.gather(*chat_response.evaluations)
        results_to_display = [
            result.to_dict() if result is not None else "not evaluated"
            for result in eval_results
        ]
        print("Judge results:")
        print(json.dumps(results_to_display, indent=2, default=str))

    # Always flush events before closing — trailing events are at risk of being
    # lost otherwise, in short-lived scripts and long-running services alike.
    ldclient.get().flush()
    ldclient.get().close()
```

## SDK: Direct Judge Evaluation

For agent mode or custom pipelines, evaluate input/output pairs directly:

```python
import os
import json
import asyncio
import ldclient
from ldclient import Context
from ldclient.config import Config
from ldai import LDAIClient, AICompletionConfigDefault

sdk_key = os.getenv('LAUNCHDARKLY_SDK_KEY')
judge_key = os.getenv('LAUNCHDARKLY_AI_JUDGE_KEY', 'sample-ai-judge-accuracy')

async def async_main():
    ldclient.set_config(Config(sdk_key))
    aiclient = LDAIClient(ldclient.get())

    context = (
        Context.builder('example-user-key')
        .kind('user')
        .name('Sandy')
        .build()
    )

    judge_default_value = AICompletionConfigDefault(enabled=False)

    # Get judge configuration from LaunchDarkly
    judge = await aiclient.create_judge(judge_key, context, judge_default_value)

    if not judge:
        print(f"AI judge configuration not enabled for key: {judge_key}")
        return

    input_text = 'You are a helpful assistant. How can you help me?'
    output_text = 'I can answer any question you have.'

    # Evaluate the input/output pair — always returns a JudgeResult in v0.18.0+
    judge_result = await judge.evaluate(input_text, output_text)

    if not judge_result.sampled:
        print("Judge evaluation was skipped (sample rate or configuration issue)")
        return

    # Track the consolidated result on the AI Config tracker if needed:
    # tracker = ai_config.create_tracker()
    # tracker.track_judge_result(judge_result)

    print("Judge Result:")
    print(json.dumps(judge_result.to_dict(), default=str))

    # Always flush events before closing — trailing events are at risk of being
    # lost otherwise, in short-lived scripts and long-running services alike.
    ldclient.get().flush()
    ldclient.get().close()
```

> **Note:** Direct evaluation does not automatically record metrics. Obtain a tracker via `ai_config.create_tracker()` / `aiConfig.createTracker!()` and call `tracker.track_judge_result(result)` / `tracker.trackJudgeResult(result)` to record scores for the AI Config you're evaluating. (This consolidates the earlier `track_eval_scores` + `track_judge_response` pair that was removed in Python v0.18.0 / Node v0.17.0.)

## Sampling Rates

Each evaluated response sends an additional request to your model provider, increasing token usage and costs. Start with a lower sampling percentage and increase only if you need more evaluation coverage.

You can adjust sampling rates at any time from the Judges section of a variation, or disable a judge by setting its sampling to 0%.

## Viewing Results

1. Navigate to **AI Configs** > select your config
2. Click **Monitoring** tab
3. Select **Evaluator metrics** from dropdown
4. View scores by variation and time range

Results appear within 1-2 minutes of evaluation.

## Use in Guardrails and Experiments

Evaluation metrics integrate with:
- **Guarded rollouts**: Pause/revert when scores fall below threshold
- **Experiments**: Compare variations using evaluation metrics as goals

## Error Handling

| Status | Cause | Solution |
|--------|-------|----------|
| 404 | Config/variation not found | Verify keys exist |
| 400 | Invalid judge config | Check judgeConfigKey exists |
| 403 | Insufficient permissions | Check API token permissions |
| 422 | Duplicate metric key | Cannot attach multiple judges with same metric key |

## Next Steps

After attaching judges:
1. **Set fallthrough** on judge configs to an enabled variation (required)
2. **Monitor results** in Monitoring tab
3. **Adjust sampling** based on cost/coverage needs
4. **Set up guarded rollouts** for automatic regression detection

## Related Skills

- `aiconfig-create` - Create AI Configs and judges
- `aiconfig-targeting` - Configure targeting rules
- `aiconfig-variations` - Manage variations

## References

- [Online Evaluations](https://docs.launchdarkly.com/home/ai-configs/online-evaluations)
- [Custom Judges](https://docs.launchdarkly.com/home/ai-configs/custom-judges)

**Python SDK examples:**
- [direct_judge_example.py](https://github.com/launchdarkly/hello-python-ai/blob/main/examples/direct_judge_example.py) - Evaluate input/output pairs directly
- [chat_judge_example.py](https://github.com/launchdarkly/hello-python-ai/blob/main/examples/chat_judge_example.py) - Automatic evaluation with create_chat/invoke

**Node.js SDK examples:**
- [judge-evaluation](https://github.com/launchdarkly/js-core/blob/main/packages/sdk/server-ai/examples/judge-evaluation/src/index.ts) - Both direct evaluation and automatic chat-based evaluation
