# API Quick Start

Create AI Configs using the LaunchDarkly API.

## Two-Step Process

LaunchDarkly requires creating the config first, then adding variations. This ensures model configuration (`modelConfigKey`) is properly set and variations display correctly in the UI. Creating everything in one call can result in variations showing "NO MODEL" or missing parameters.

1. **Create the config** — Basic metadata (key, name, mode)
2. **Create variations** — Model, prompts/instructions, parameters for each variation

## Create Config

```bash
curl -X POST \
  https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-configs \
  -H "Authorization: api-xxxxx" \
  -H "Content-Type: application/json" \
  -H "LD-API-Version: beta" \
  -d '{
    "key": "support-agent",
    "name": "Customer Support Agent",
    "mode": "agent"
  }'
```

## Create Variation (Agent Mode)

```bash
curl -X POST \
  https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-configs/{configKey}/variations \
  -H "Authorization: api-xxxxx" \
  -H "Content-Type: application/json" \
  -H "LD-API-Version: beta" \
  -d '{
    "key": "default",
    "name": "Default Configuration",
    "instructions": "You are a helpful customer support agent.",
    "modelConfigKey": "OpenAI.gpt-4o",
    "model": {
      "modelName": "gpt-4o",
      "parameters": {
        "temperature": 0.7,
        "maxTokens": 2000
      }
    }
  }'
```

## Create Variation (Completion Mode)

```bash
curl -X POST \
  https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-configs/{configKey}/variations \
  -H "Authorization: api-xxxxx" \
  -H "Content-Type: application/json" \
  -H "LD-API-Version: beta" \
  -d '{
    "key": "default",
    "name": "Default Configuration",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "{{user_prompt}}"}
    ],
    "modelConfigKey": "Anthropic.claude-sonnet-4-5",
    "model": {
      "modelName": "claude-sonnet-4-5",
      "parameters": {
        "temperature": 0.8,
        "maxTokens": 4000
      }
    }
  }'
```

## modelConfigKey Format

Required for models to show in UI: `{Provider}.{model-id}`

- `OpenAI.gpt-4o`
- `OpenAI.gpt-4o-mini`
- `Anthropic.claude-sonnet-4-5`
- `Anthropic.claude-3-5-sonnet`

## Attach Tools (After Creation)

Tools cannot be attached during config creation. PATCH the variation:

```bash
curl -X PATCH \
  https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-configs/{configKey}/variations/{variationKey} \
  -H "Authorization: api-xxxxx" \
  -H "Content-Type: application/json" \
  -H "LD-API-Version: beta" \
  -d '{
    "tools": [
      {"key": "search-database", "version": 1}
    ]
  }'
```

## Verify Config

```bash
curl -X GET \
  https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-configs/{configKey} \
  -H "Authorization: api-xxxxx" \
  -H "LD-API-Version: beta"
```

## List Models

```bash
curl -X GET \
  https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-configs/model-configs \
  -H "Authorization: api-xxxxx"
```
