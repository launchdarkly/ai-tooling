---
name: launchdarkly-metric-create
description: "Create a LaunchDarkly metric that measures what matters for an experiment or rollout. Use when the user wants to create a metric, track an event, measure conversion, latency, error rate, or any custom numeric or binary outcome. Guides event discovery before creation and proposes config in plain language."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.0.0-experimental"
---

# LaunchDarkly Metric Create

You're using a skill that will guide you through creating a LaunchDarkly metric. Your job is to check whether the underlying event is already flowing, propose a metric configuration in plain language, let the user confirm or adjust it, and then create and verify the metric.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Required MCP tools:**
- `create-metric` — create the metric
- `get-metric` — verify it after creation

**Optional MCP tools (enhance workflow):**
- `list-metrics` — check for existing metrics with the same event key and understand naming conventions
- `list-metric-events` — discover which event keys have recent activity before committing to one

## Workflow

### Step 1: Check for Existing Metrics

Before creating anything, use `list-metrics` to scan the project:

1. **Check for duplicates.** Search for metrics with the same event key or similar names. Avoid creating a second metric that measures the same thing — instead, flag the existing metric and ask the user if they want to reuse it.
2. **Learn the naming convention.** Are metric keys `kebab-case` or `snake_case`? Are there common tag patterns? Match what already exists.
3. **Understand the tag taxonomy.** Tags like `team:growth`, `area:checkout`, or `type:guardrail` may already exist. Suggest relevant tags based on what the user describes.

### Step 2: Resolve the Event Key

This is the most important step. LaunchDarkly metrics are event-first — a metric without events flowing is a metric that can't measure anything.

**If the user already knows the event key**, use it directly. Skip to Step 3.

**If the user isn't sure of the event key**, call `list-metric-events` to show which event keys have been received in the last 90 days:

```
list-metric-events(projectKey, environmentKey?)
```

Show the results and let the user pick. If the event key they need isn't in the list:

- Surface a clear warning: the event may not be instrumented yet.
- Ask: **"Do you want to instrument this event first, or create the metric now and wire the event up later?"**
- If they want to instrument first, pause this flow and guide them through adding a `track()` call to their codebase.
- If they want to proceed anyway, continue — and remind them at the end that events need to be flowing before this metric can produce results.

**Do not block creation** if the user prefers to proceed without confirmed event activity.

### Step 3: Propose the Metric Configuration

Before calling any API, surface a proposed configuration in plain language for the user to confirm or edit.

**Determine measure type.** Ask or infer from context:

| What the user wants to measure | Measure type | Means |
|-------------------------------|-------------|-------|
| Total times the event occurred | `count` | Raw event count per analysis unit |
| Whether each user triggered the event at all | `occurrence` | Conversion / binary (did it happen?) |
| A numeric value attached to the event | `value` | Latency, revenue, score, etc. |

**Determine success criteria:**

- **Higher is better** → `HigherThanBaseline` (conversion rate, revenue, engagement)
- **Lower is better** → `LowerThanBaseline` (latency, error rate, bounce rate)

**Use common templates as defaults** when the user's intent is clear:

| User intent | measure type | success criteria | unit |
|-------------|-------------|-----------------|------|
| API latency / page load time | `value` (average) | `LowerThanBaseline` | `ms` |
| Signup / conversion rate | `occurrence` | `HigherThanBaseline` | — |
| Error count / rate | `count` | `LowerThanBaseline` | — |
| Revenue per user | `value` (sum) | `HigherThanBaseline` | `USD` |
| Clicks or button presses | `count` | `HigherThanBaseline` | — |

**Present the proposed config** before creating — don't silently fire the API:

```
Proposed metric:
  Key:              checkout-conversion
  Name:             Checkout Conversion
  Event key:        checkout-completed
  Measure type:     occurrence (did each user complete checkout?)
  Success criteria: HigherThanBaseline
  Tags:             team:growth

Proceed, or would you like to change anything?
```

### Step 4: Create the Metric

Once the user confirms, call `create-metric`. The tool handles the translation from `measureType` to the underlying API fields — you never need to pass `isNumeric` or `unitAggregationType` directly.

```
create-metric(
  projectKey,
  key,
  name,
  eventKey,
  measureType,       // "count" | "occurrence" | "value"
  successCriteria,   // "HigherThanBaseline" | "LowerThanBaseline"
  valueAggregation?, // only for measureType="value": "average" (default) or "sum"
  unit?,             // display label: "ms", "USD", etc.
  description?,
  tags?
)
```

### Step 5: Verify

Use `get-metric` to confirm the metric was created with the right configuration:

1. **Key and name match** what was requested.
2. **measureType is correct** — double-check by reading back the `measureType` field, not just `isNumeric`.
3. **eventKey is set** to the intended value.
4. **successCriteria** is correct.

Surface a summary to the user:

```
✓ Metric created: checkout-conversion
  Event:    checkout-completed
  Measures: occurrence (conversion rate)
  Goal:     Higher is better

View in LaunchDarkly: https://app.launchdarkly.com/projects/{projectKey}/metrics/{metricKey}
```

## Measure Type Reference

The `create-metric` tool translates `measureType` to the LD API fields internally. You never need to set `isNumeric` or `unitAggregationType` directly.

| measureType | isNumeric | unitAggregationType | Use for |
|-------------|-----------|---------------------|---------|
| `count` | false | sum | Raw event counts — error rate, click count |
| `occurrence` | false | average | Conversion — did the user do the thing? |
| `value` (average) | true | average | Per-user mean — average latency, average session length |
| `value` (sum) | true | sum | Per-user total — total revenue, total items purchased |

For `value` metrics, `valueAggregation` defaults to `"average"`. Pass `valueAggregation: "sum"` for revenue or cumulative totals.

## Important Context

- **Event keys are case-sensitive.** `checkout-completed` and `Checkout-Completed` are different events. Match the key exactly as it appears in your `track()` calls.
- **Metrics without events produce no data.** A metric is only useful once its event key is actively being tracked in production (or the relevant environment). If you created the metric before instrumenting the event, remind the user.
- **Metric keys are immutable.** Once created, a metric's key cannot be changed. Choose carefully.
- **Metrics are project-scoped.** A metric created in one project is not visible in another. Make sure `projectKey` matches where the experiment or flag lives.
- **One primary metric per experiment.** When attaching this metric to an experiment, clarify whether it's the primary metric (the one that determines success or failure) or a secondary metric (a guardrail or supporting signal). See the LaunchDarkly docs for experiment setup.
