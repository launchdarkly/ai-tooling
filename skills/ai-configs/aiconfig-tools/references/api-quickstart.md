# Tools API Quick Start

Create and manage tools using the LaunchDarkly API.

**Endpoint:** `https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-tools`
Do NOT use `/ai-configs/tools` — that endpoint does not exist.

## Create a Tool

```bash
curl -X POST \
  https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-tools \
  -H "Authorization: api-xxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "search-database",
    "description": "Search the customer database",
    "schema": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "Search query"},
        "limit": {"type": "integer", "description": "Max results to return"}
      },
      "required": ["query"]
    }
  }'
```

### Optional Fields

| Field | Description |
|-------|-------------|
| `maintainerId` | User ID of the tool maintainer |
| `maintainerTeamKey` | Team key for tool ownership |
| `customParameters` | Additional custom parameters as JSON object |

## Attach to Variation

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

## List Tools

```bash
curl -X GET \
  https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-tools \
  -H "Authorization: api-xxxxx"
```

## Get Tool

```bash
curl -X GET \
  https://app.launchdarkly.com/api/v2/projects/{projectKey}/ai-tools/{toolKey} \
  -H "Authorization: api-xxxxx"
```

## Schema Format

Use JSON Schema format:

```json
{
  "type": "object",
  "properties": {
    "query": {"type": "string", "description": "Search query"},
    "limit": {"type": "integer", "description": "Max results"}
  },
  "required": ["query"]
}
```

The tool `key` and `description` are set at the top level, not inside the schema.
