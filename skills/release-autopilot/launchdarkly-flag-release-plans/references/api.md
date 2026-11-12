# Flag release plan API

Every endpoint is in beta and needs the `LD-API-Version: beta` header on every request. Each command below is self-contained: it reads the token from `LD_ACCESS_TOKEN` and the instance from `LD_BASE_URI` (default `https://app.launchdarkly.com`), and prints the response body followed by `HTTP <status>`. Replace `PROJECT_KEY`, `PLAN_KEY`, `ENV_KEY`, and `FLAG_KEY`.

Do not add `-v` or `--trace`: they print the `Authorization` header.

## Endpoints

| Operation | Method and path | Success |
|-----------|-----------------|---------|
| List a project's plans | `GET /api/v2/projects/{projectKey}/flag-release-plans?limit=50&offset=0` | 200 |
| Get one plan | `GET /api/v2/projects/{projectKey}/flag-release-plans/{planKey}` | 200 |
| Create a plan | `POST /api/v2/projects/{projectKey}/flag-release-plans` | 201 |
| Replace a plan (full update) | `PUT /api/v2/projects/{projectKey}/flag-release-plans/{planKey}` | 200 |
| Delete a plan | `DELETE /api/v2/projects/{projectKey}/flag-release-plans/{planKey}` | 204 |
| Start a flag's release | `POST /api/v2/projects/{projectKey}/flags/{flagKey}/flag-releases` | 201 |
| An environment's release plans | `GET /api/v2/projects/{projectKey}/environments/{environmentKey}/release-plans` | 200 |
| An environment's default release plan | `GET /api/v2/projects/{projectKey}/environments/{environmentKey}/default-release-plan` | 200 |

The list returns `items`, `totalCount`, and `_links`, in creation order. `limit` is 1 to 50 (default 25). Page with `offset` while `offset + items.length < totalCount`.

## Commands

### List

```sh
curl -sS -w '\nHTTP %{http_code}\n' \
  -H "Authorization: $LD_ACCESS_TOKEN" \
  -H "LD-API-Version: beta" \
  "${LD_BASE_URI:-https://app.launchdarkly.com}/api/v2/projects/PROJECT_KEY/flag-release-plans?limit=50&offset=0"
```

### Get

```sh
curl -sS -w '\nHTTP %{http_code}\n' \
  -H "Authorization: $LD_ACCESS_TOKEN" \
  -H "LD-API-Version: beta" \
  "${LD_BASE_URI:-https://app.launchdarkly.com}/api/v2/projects/PROJECT_KEY/flag-release-plans/PLAN_KEY"
```

### Create

```sh
curl -sS -w '\nHTTP %{http_code}\n' -X POST \
  -H "Authorization: $LD_ACCESS_TOKEN" \
  -H "LD-API-Version: beta" \
  -H "Content-Type: application/json" \
  "${LD_BASE_URI:-https://app.launchdarkly.com}/api/v2/projects/PROJECT_KEY/flag-release-plans" \
  --data @- <<'JSON'
{
  "key": "default-release",
  "name": "Default release",
  "isDefault": true,
  "environments": [
    { "environmentKey": "test", "environmentReleasePlanKey": "progressive", "triggerType": "flag_eval" },
    { "environmentKey": "production", "environmentReleasePlanKey": "progressive-2", "triggerType": "flag_eval" }
  ]
}
JSON
```

Leave out `"isDefault": true` when the project already has a default.

### Replace (update)

Start from a fresh get. Send every field to keep, because anything left out is cleared, including `isDefault`. `key` is not in the body; it is in the path.

```sh
curl -sS -w '\nHTTP %{http_code}\n' -X PUT \
  -H "Authorization: $LD_ACCESS_TOKEN" \
  -H "LD-API-Version: beta" \
  -H "Content-Type: application/json" \
  "${LD_BASE_URI:-https://app.launchdarkly.com}/api/v2/projects/PROJECT_KEY/flag-release-plans/PLAN_KEY" \
  --data @- <<'JSON'
{
  "version": 1,
  "name": "Default release",
  "isDefault": true,
  "executionMode": "sequential",
  "environments": [
    { "environmentKey": "test", "environmentReleasePlanKey": "progressive", "triggerType": "flag_eval" },
    { "environmentKey": "production", "environmentReleasePlanKey": "progressive-2", "triggerType": "flag_eval" }
  ]
}
JSON
```

Copy `description`, `maintainer` (as `{ "kind": "member", "memberId": ... }` or `{ "kind": "team", "teamKey": ... }`), and `applicationKeys` from the read when the plan has them. The read returns the maintainer with names; send only the kind and the ID or key.

### Delete

```sh
curl -sS -w '\nHTTP %{http_code}\n' -X DELETE \
  -H "Authorization: $LD_ACCESS_TOKEN" \
  -H "LD-API-Version: beta" \
  "${LD_BASE_URI:-https://app.launchdarkly.com}/api/v2/projects/PROJECT_KEY/flag-release-plans/PLAN_KEY"
```

### Start a flag's release from a plan

```sh
curl -sS -w '\nHTTP %{http_code}\n' -X POST \
  -H "Authorization: $LD_ACCESS_TOKEN" \
  -H "LD-API-Version: beta" \
  -H "Content-Type: application/json" \
  "${LD_BASE_URI:-https://app.launchdarkly.com}/api/v2/projects/PROJECT_KEY/flags/FLAG_KEY/flag-releases" \
  --data @- <<'JSON'
{ "kind": "plan", "planKey": "default-release" }
JSON
```

Optional: `startingVariationId` and `endingVariationId` (for a boolean flag, false to true when left out), and `pullRequest` (`repoFullName`, `number`, optional `url`). The response is `{ "id": "..." }`. An unknown plan key returns 400.

### An environment's release plans

```sh
curl -sS -w '\nHTTP %{http_code}\n' \
  -H "Authorization: $LD_ACCESS_TOKEN" \
  -H "LD-API-Version: beta" \
  "${LD_BASE_URI:-https://app.launchdarkly.com}/api/v2/projects/PROJECT_KEY/environments/ENV_KEY/release-plans"
```

Each item has `key`, `name`, and `default` (true for the environment's default plan). Prefer the `get-environment-release-plans` MCP tool when it is available.

## Request fields

Create takes these fields. Replace takes the same fields without `key`, plus `version`.

| Field | Required | Rules |
|-------|----------|-------|
| `key` | Create only | 1 to 256 characters, `^[a-zA-Z0-9][._\-a-zA-Z0-9]*$`. Unique among the project's active plans. Cannot change |
| `name` | Yes | At most 256 characters |
| `description` | No | At most 1024 characters |
| `environments` | Yes | 1 to 50 entries, in release order, each environment once |
| `environments[].environmentKey` | Yes | An environment in the project |
| `environments[].triggerType` | Yes | `flag_eval`, `webhook`, `manual`, or `promotion`. `manual` and `promotion` need `sequential`; the first environment cannot use `promotion` |
| `environments[].environmentReleasePlanKey` | Unless immediate | A complete environment release plan in that environment |
| `environments[].isImmediate` | No | `true` releases at once with no release plan. Do not send a release plan key with it |
| `executionMode` | No | `sequential` (the default for plans) or `parallel` |
| `applicationKeys` | No | At most 25 keys. Auto-releasing uses them to choose a plan for an application |
| `isDefault` | No | Create: only when the project has no default. Replace: `true` demotes the current default; left out clears it |
| `maintainer` | No | `{ "kind": "member", "memberId": "..." }` or `{ "kind": "team", "teamKey": "..." }` |
| `version` | Replace only, optional | The version from the last read. A mismatch returns 409 and changes nothing |

A project has at most 100 active plans.

## Response

Create, get, and replace return the plan. Its version starts at 1 and goes up by 1 on each update.

```json
{
  "key": "default-release",
  "_id": "0b6c3a43-5d0e-4f43-9a8e-2f6f1d7c9e10",
  "version": 1,
  "name": "Default release",
  "isDefault": true,
  "executionMode": "sequential",
  "applicationKeys": [],
  "environments": [
    { "environmentKey": "test", "environmentReleasePlanKey": "progressive", "isImmediate": false, "triggerType": "flag_eval" },
    { "environmentKey": "production", "environmentReleasePlanKey": "progressive-2", "isImmediate": false, "triggerType": "flag_eval" }
  ]
}
```

## Errors

Errors return `{ "code": "...", "message": "..." }`. Read `message` for the reason.

| Status | When |
|--------|------|
| 400 | A field breaks a rule above; an environment is not in the project; a release plan is unknown, incomplete, or in another environment; `isDefault` on create while the project has a default; the project already has 100 plans; an unknown plan key when starting a release |
| 401 | No token, or the token is not valid |
| 403 | `Plan does not allow this operation`: the account does not have flag release plans. Any other message: the token's role lacks the action |
| 404 | The project, flag, or plan does not exist |
| 409 | Create: another active plan has the key. Replace: `version` does not match the plan's current version |
