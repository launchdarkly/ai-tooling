# Create the experiment (abstracted: MCP or REST)

This is **one logical step with two implementations**. Detect what's available
and use it. Only run this after the user has confirmed the draft (Step 7).

Detection order:
1. **LaunchDarkly MCP tools present** (e.g. `create-experiment`) → MCP path.
2. **Else a LaunchDarkly API token present** (`LD_API_KEY` /
   `LAUNCHDARKLY_ACCESS_TOKEN`) → REST path.
3. **Else** → hand the user the ready-to-run REST calls and the draft; stop.

You need these values, gathered in earlier steps:
- `projectKey`, `environmentKey` (from `get-environments`).
- Primary metric key (reused or newly created).
- Flag key, the variation IDs for control/treatment, the targeting `ruleId`
  (fallthrough rule id is the string `"fallthrough"`), and current
  `flagConfigVersion`.

> **Prefer delegating the mechanical details to `launchdarkly-experiment-setup`.**
> It owns the field-level rules (`mutableFieldsByStatus`, iteration lifecycle,
> stopping with a winner). This reference is the abstraction contract so this
> skill can complete the flow even when that skill isn't loaded.

---

## MCP path (preferred)

1. **Create any missing metric** — `create-metric` (or delegate to
   `launchdarkly-metric-create`). Skip if reusing an existing metric.
2. **Create the experiment with its first iteration** — `create-experiment`:

```json
{
  "projectKey": "my-project",
  "environmentKey": "production",
  "key": "redesigned-checkout-experiment",
  "name": "Redesigned Checkout Experiment",
  "description": "Test the redesigned checkout against the current flow.",
  "methodology": "bayesian",
  "iteration": {
    "hypothesis": "The redesigned checkout will lift completion ~3% for logged-in shoppers.",
    "primarySingleMetricKey": "checkout-completed",
    "metrics": [
      { "key": "checkout-completed" },
      { "key": "checkout-error-rate" }
    ],
    "treatments": [
      { "name": "Control", "baseline": true, "allocationPercent": 50,
        "parameters": [{ "flagKey": "new-checkout", "variationId": "<control-variation-id>" }] },
      { "name": "New Checkout", "baseline": false, "allocationPercent": 50,
        "parameters": [{ "flagKey": "new-checkout", "variationId": "<treatment-variation-id>" }] }
    ],
    "flags": {
      "new-checkout": { "ruleId": "fallthrough", "flagConfigVersion": 7 }
    },
    "randomizationUnit": "user"
  }
}
```

3. **Start data collection** — `start-experiment-iteration` with
   `{ projectKey, environmentKey, experimentKey }`. Requires the flag to be on,
   a `randomizationUnit`, and at least one non-zero allocation.
4. **Verify** — `get-experiment`; confirm `currentIteration.status === "running"`.

Rules that matter: exactly one treatment has `baseline: true`; allocations sum
to 100; the `iteration` object is required on create.

---

## REST fallback

Base URL `https://app.launchdarkly.com`. Header:
`Authorization: <token>` (plus `Content-Type: application/json`, and
`LD-API-Version: beta` for experiment endpoints).

**Create a metric** (skip if reusing):
```
POST /api/v2/metrics/{projectKey}
{
  "key": "checkout-completed",
  "name": "Checkout completed",
  "kind": "custom",
  "isNumeric": false,
  "eventKey": "checkout-completed",
  "successCriteria": "HigherThanBaseline"
}
```

**Create the experiment** (body mirrors the MCP `iteration`):
```
POST /api/v2/projects/{projectKey}/environments/{environmentKey}/experiments
{
  "key": "redesigned-checkout-experiment",
  "name": "Redesigned Checkout Experiment",
  "methodology": "bayesian",
  "iteration": {
    "hypothesis": "The redesigned checkout will lift completion ~3% for logged-in shoppers.",
    "primarySingleMetricKey": "checkout-completed",
    "metrics": [{ "key": "checkout-completed" }, { "key": "checkout-error-rate" }],
    "treatments": [
      { "name": "Control", "baseline": true, "allocationPercent": 50,
        "parameters": [{ "flagKey": "new-checkout", "variationId": "<control-variation-id>" }] },
      { "name": "New Checkout", "baseline": false, "allocationPercent": 50,
        "parameters": [{ "flagKey": "new-checkout", "variationId": "<treatment-variation-id>" }] }
    ],
    "flags": { "new-checkout": { "ruleId": "fallthrough", "flagConfigVersion": 7 } },
    "randomizationUnit": "user"
  }
}
```

**Start the iteration:**
```
POST /api/v2/projects/{projectKey}/environments/{environmentKey}/experiments/{experimentKey}/iterations
```
then `PATCH` the experiment to set the current iteration to running (see the
OpenAPI spec for the exact instruction body).

**Verify:**
```
GET /api/v2/projects/{projectKey}/environments/{environmentKey}/experiments/{experimentKey}
```

CRUD reality check: **metrics support full CRUD** (create/read/update/delete).
**Experiments support create/read/update + iterations, but no delete** — you
manage an experiment's life through its iterations, not by deleting it.

For exact request/response schemas, see the OpenAPI spec:
`https://launchdarkly.com/docs/api/other/get-openapi-spec` (tags: *Metrics*,
*Experiments*).

---

## No access at all

Present the draft plus the two `POST` calls above with the user's real values
filled in, and tell them they can either run them with an API token or open the
experiment in the LaunchDarkly UI. Point them at `launchdarkly-experiment-setup`
to finish and to run the iteration lifecycle.
