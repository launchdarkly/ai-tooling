---
name: launchdarkly-experiment-setup
description: "Set up and run experiments in LaunchDarkly. Create experiments with metrics, treatments, and flag config, start iterations to collect data, swap design between iterations, and stop with a winner."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "0.3.1"
---

# LaunchDarkly Experiment Setup

You're using a skill that guides you through setting up and running experiments in LaunchDarkly. Your job is to design the experiment, create it with the right metrics, treatments, and flag config, start data collection, evolve the design between iterations when needed, and stop with a winner. The flag and variations, hypothesis, control variation, randomization unit, and primary metric must come from the user. Create a metric or experiment only after they explicitly approve the full design, and start an iteration only after they explicitly say to start.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Required MCP tools:**
- `create-experiment` — create a new experiment with its initial iteration (hypothesis, metrics, treatments, flag config).
- `start-experiment-iteration` — begin collecting data for an experiment's current draft iteration.
- `get-experiment` — check experiment status, treatments, metrics, and current iteration.

**Optional MCP tools:**
- `list-experiments` — browse existing experiments in the project.
- `update-experiment` — update fields on the experiment or its current iteration. Honours `mutableFieldsByStatus`, so what's editable depends on whether the iteration is `not_started`, `running`, or `stopped`. Returns rejected inputs under `skipped`.
- `save-and-start-experiment-iteration` — the API-recommended way to change locked fields on a running experiment. Stops the current iteration, creates a new draft with the supplied field updates, and starts it in one call.
- `stop-experiment-iteration` — stop the running iteration. You must declare a winner: pass the `winningTreatmentId` (and a `winningReason`). If no variation outperformed, pick the baseline/control as the winner.
- `list-metrics`, `create-metric`, `list-metric-events` — manage metrics referenced by the experiment.

## Core Concepts

### What Are Experiments?

Experiments in LaunchDarkly measure the impact of feature flag variations on key metrics. An experiment consists of:

- **Treatments**: the flag variations being compared (control vs. test). Each treatment has an `allocationPercent`; the values across treatments should sum to 100.
- **Metrics**: what you're measuring (conversion rate, latency, revenue, etc.). One must be the primary metric.
- **Flag config**: the `flagKey`, `ruleId`, and `flagConfigVersion` of the targeting rule that drives the experiment.
- **Iteration**: a single data-collection window. Created in `not_started` status, becomes `running` when started, transitions to `stopped` when ended.
- **Holdout** (optional): a project-level group of users excluded from the experiment for baseline measurement (`holdoutId`).

### Experiment Lifecycle

1. **Create** the experiment with its first iteration (`create-experiment`).
2. **Start the iteration** to begin data collection (`start-experiment-iteration`), only after the user explicitly says to start.
3. **Monitor** results as data accumulates (`get-experiment`).
4. **Evolve the design** mid-experiment if needed — change locked fields like `treatments`, `metrics`, or `methodology` by calling `save-and-start-experiment-iteration`, which stops the current iteration, creates a new draft with your changes, and starts it. That call starts data collection, so make it only after the user explicitly says to start.
5. **Stop the iteration** when you have a winner or a clear call (`stop-experiment-iteration`).
6. **Ship** the winning variation.

## Core Principles

1. **Metrics first**: ensure the metrics you'll reference exist before creating the experiment.
2. **Clear hypothesis**: every iteration requires a `hypothesis` string from the user: what they expect to improve, and by how much if they know. If they have not given one, ask. Leave it blank until they do.
3. **Proper controls**: exactly one treatment must have `baseline: true`.
4. **Sufficient sample size**: let iterations run long enough for statistical significance.
5. **One change at a time**: test one variable per experiment for clear attribution.

## Before you create anything

These five must come from the user:

- **Flag and variations**: which flag to test, and which of its variations are in the experiment.
- **Hypothesis**: what they expect to improve, and by how much if they know.
- **Control variation**: which of those variations is the baseline (`baseline: true`).
- **Randomization unit**: the context kind the experiment randomizes on (for example `user`).
- **Primary metric**: the single metric or funnel that decides the result.

If any are missing, ask for every missing one in one message, then wait. Leave them blank until the user supplies them. `list-metrics`, `list-metric-events`, and `get-flag` are fine while you gather this; `create-metric` and `create-experiment` are not. Once the user names the flag, `get-flag` resolves `ruleId`, `flagConfigVersion`, and the variation ids they named.

Settings the user did not mention can stay on LaunchDarkly's defaults. List each default you are using in the design:

- **Traffic split**: equal `allocationPercent` across the variations the user named (two variations is 50/50). The values must sum to 100.
- **Statistics**: `methodology` `"bayesian"`.
- **Data source**: `dataSource` `"launchdarkly"`.
- **Reshuffle**: `canReshuffleTraffic` `true`.

Leave `analysisConfig` unset unless the user set it, and say that in the design. The randomization unit is never a default.

## Workflow

### Step 1: Prepare Metrics

1. Use `list-metrics` to find existing metrics. The user names the primary metric.
2. If it already exists, keep its name and key for the design review.
3. If it does not exist and it is based on a custom event, call `list-metric-events` for that event key.
   - If the event is not reaching LaunchDarkly, tell the user and ask them to trigger it first. Leave the metric uncreated, and leave the experiment uncreated.
   - If the event is arriving, carry the metric into the design review.
4. Pageview and click metrics have no custom event key, so skip `list-metric-events` for those.
5. For a new metric, the design must say what kind it is (`custom`, `pageview`, or `click`), what it is based on (event key, URL match, or click selector), and how it is measured: share of units who converted, a total count, or an average. If the user has not chosen how it is measured, ask in the design message and leave that choice blank. "yes", "looks good", and "create it" do not fill it. Only a reply that names one of those three measures does. That reply fills the blank. It is not approval: show the completed design again and ask the user to approve it.
6. Pass the user-named primary metric as `primarySingleMetricKey` or `primaryFunnelKey`.

| Goal | Metric type | Example key |
|------|-------------|-------------|
| Conversion | Custom conversion | `checkout-completed` |
| Performance | Custom numeric | `page-load-time-ms` |
| Engagement | Custom conversion | `feature-clicked` |
| Revenue | Custom numeric | `order-value` |

### Step 2: Identify the Targeting Rule

You need the `ruleId` and current `flagConfigVersion` of the flag rule that will drive the experiment. Use `get-flag` on the flag (or its environment-scoped status) to find them. The fallthrough rule's id is the string `"fallthrough"`.

### Step 3: Create the Experiment

Show the full design and wait until it is approved before calling `create-metric` or `create-experiment`. Include the flag and variations, hypothesis, control variation, other treatments, randomization unit, flag config (`flagKey`, `ruleId`, `flagConfigVersion`), and every default you are applying (traffic split, Bayesian methodology, `launchdarkly` data source, `canReshuffleTraffic: true`). For an existing primary metric, include its name and key. For a new one, include its kind, what it is based on, and how it is measured. Call `create-metric` only for a new metric you are allowed to create, and only after how it is measured is filled in, then call `create-experiment`.

"yes", "looks good", and "create it" approve a design that is already complete. They do not choose how a new metric is measured. While that choice is blank, ask again and do not call `create-metric`. A reply that only names the measure — share of units who converted, a total count, or an average — fills the blank. Show the full design again with that measure filled in, and ask for approval of the completed design. Do not call `create-metric` or `create-experiment` on that reply.

**STOP HERE** until the user's latest message approves a complete design. When how a new metric is measured is still blank, that message has to name the measure. When it only names the measure, restate the completed design and wait for approval.

Call `create-experiment`. The top-level fields describe the experiment; the nested `iteration` object describes the first data-collection window. The flag, variations, hypothesis, 50/50 split, and `"user"` randomization unit in the example below are the shape of the call, not values to copy when the user has not supplied them.

```json
{
  "projectKey": "my-project",
  "environmentKey": "production",
  "key": "checkout-flow-v2-experiment",
  "name": "Checkout Flow v2 Experiment",
  "description": "Compare the redesigned checkout against the current flow.",
  "tags": ["growth", "checkout"],
  "methodology": "bayesian",
  "iteration": {
    "hypothesis": "The redesigned checkout will lift completion rate by 3%.",
    "primarySingleMetricKey": "checkout-completed",
    "metrics": [
      { "key": "checkout-completed" },
      { "key": "checkout-time-seconds" }
    ],
    "treatments": [
      {
        "name": "Control",
        "baseline": true,
        "allocationPercent": 50,
        "parameters": [
          { "flagKey": "checkout-flow-v2", "variationId": "variation-a-id" }
        ]
      },
      {
        "name": "New Checkout",
        "baseline": false,
        "allocationPercent": 50,
        "parameters": [
          { "flagKey": "checkout-flow-v2", "variationId": "variation-b-id" }
        ]
      }
    ],
    "flags": {
      "checkout-flow-v2": {
        "ruleId": "fallthrough",
        "flagConfigVersion": 7
      }
    },
    "randomizationUnit": "user"
  }
}
```

Useful optional top-level fields:
- `holdoutId` — attach an existing holdout.
- `dataSource` — `"launchdarkly"` (default), `"snowflake"`, or `"databricks"`.
- `methodology` — `"bayesian"` (default), `"frequentist"`, or `"export_only"`.
- `analysisConfig` — set thresholds, multiple-comparison correction, or sequential testing.

Useful optional iteration fields:
- `attributes` — array of context attribute keys to slice results by (e.g. `["country", "device"]`).
- `covariateId` — covariate CSV id for stratified sampling.
- `canReshuffleTraffic` — defaults to `true`; set `false` to lock users to their initial variation when allocations change.

### Step 4: Start Data Collection

Creating the experiment leaves the iteration in `not_started`. Call `start-experiment-iteration` only after the user explicitly says to start. That same wait applies to any other call that starts an iteration.

```json
{
  "projectKey": "my-project",
  "environmentKey": "production",
  "experimentKey": "checkout-flow-v2-experiment"
}
```

Before starting, the API requires that:
- the flag is toggled on,
- the iteration has a `randomizationUnit`, and
- at least one treatment has a non-zero `allocationPercent`.

If the flag is off in that environment when the user says to start, don't change the flag. Tell the user the flag must be on in that environment, and that turning it on starts serving its variations to users there. Ask whether they want to turn it on themselves or have you do it, and wait for an explicit answer before calling any tool that changes the flag. Once the flag is on, call `get-flag` again to get the current `flagConfigVersion`, update the draft to use it, and tell the user you did, before starting.

Pass `changeJustification` if you're restarting after a prior iteration was stopped.

### Step 5: Verify

1. After the user has asked you to start, call `get-experiment` and confirm `currentIteration.status === "running"`.
2. Check that treatments are present with the expected allocations.
3. Check the metric list and the primary metric.

### Step 6: Evolve the Design Mid-Experiment (when needed)

Most structural fields (treatments, metrics, methodology, hypothesis, …) are locked while an iteration is `running`. Two ways to change them:

- **Light edits while running** — `update-experiment` will let through anything `mutableFieldsByStatus` permits in the `running` state (typically just metadata like `name`, `description`, `maintainerId`, `tags`, plus appending `metrics`/`attributes`). It surfaces rejected fields under `skipped` with a reason.
- **Real design changes** — call `save-and-start-experiment-iteration`. It stops the current iteration, creates a new draft with the supplied field updates applied, and starts it in one call. Inputs match `update-experiment`, plus `changeJustification`. Mutability is checked against `not_started` since updates land on the new draft.

`save-and-start-experiment-iteration` starts the new iteration. Show the change, then wait until the user explicitly says to start before calling it.

Example: swap the treatment allocation and add a metric in a single call.

```json
{
  "projectKey": "my-project",
  "environmentKey": "production",
  "experimentKey": "checkout-flow-v2-experiment",
  "changeJustification": "Lowering control allocation now that variant looks safe.",
  "treatments": [
    {
      "name": "Control",
      "baseline": true,
      "allocationPercent": 30,
      "parameters": [{ "flagKey": "checkout-flow-v2", "variationId": "variation-a-id" }]
    },
    {
      "name": "New Checkout",
      "baseline": false,
      "allocationPercent": 70,
      "parameters": [{ "flagKey": "checkout-flow-v2", "variationId": "variation-b-id" }]
    }
  ],
  "metrics": [
    { "key": "checkout-completed" },
    { "key": "checkout-time-seconds" },
    { "key": "checkout-error-rate" }
  ]
}
```

### Step 7: Stop the Iteration

When you've reached significance or made a call, stop the iteration. **A winning treatment is required to stop** — LaunchDarkly does not let you end an iteration without declaring a winner. Pass the winning treatment's id (returned in `get-experiment` as `_id` on each treatment) plus a `winningReason`.

If the experiment was inconclusive or no variation beat the control, declare the **baseline/control treatment as the winner** and say so in `winningReason` (e.g. "Inconclusive — no significant lift, keeping control"). There is no "stop without a winner" path.

```json
{
  "projectKey": "my-project",
  "environmentKey": "production",
  "experimentKey": "checkout-flow-v2-experiment",
  "winningTreatmentId": "treat-002",
  "winningReason": "Two weeks of data, +4.1% lift on the primary metric with PBBL > 95%."
}
```

**Report results:**
- Iteration stopped with the declared `winningTreatmentId` (the control/baseline if inconclusive).
- Lift / significance summary on the primary metric.
- Next steps (ship the winner, roll back, or start a follow-up iteration).

## Edge Cases

| Situation | Action |
|-----------|--------|
| Primary metric doesn't exist and is a custom event | Call `list-metric-events`. If the event is not reaching LaunchDarkly, tell the user and ask them to trigger it. If it is, include the new metric's kind, event key, and measurement in the design review. Call `create-metric` only after how it is measured is filled in and the design is approved. A reply that only names the measure fills that blank. Show the completed design again and ask for approval. "yes", "looks good", and "create it" do not fill a blank measure. |
| A required piece is missing | Ask for every missing required piece in one message and wait. |
| Design not approved | Show the full design and wait. `create-metric` and `create-experiment` stay uncalled. |
| User has not said to start | Leave the iteration in `not_started`. `start-experiment-iteration` and `save-and-start-experiment-iteration` stay uncalled. |
| Flag is off when the user says to start | Don't change the flag. Tell the user the flag must be on in that environment, and that turning it on starts serving its variations to users there. Ask whether they want to turn it on themselves or have you do it, and wait for an explicit answer before calling any tool that changes the flag. Once the flag is on, call `get-flag` again to get the current `flagConfigVersion`, update the draft to use it, and tell the user you did, before starting. |
| Flag has no variations to compare | Create flag variations before designing treatments. |
| You don't know the flag's `ruleId` / `flagConfigVersion` | Use `get-flag` or `get-flag-status-across-envs`. The fallthrough rule's id is the string `"fallthrough"`. |
| Experiment already exists | Use `list-experiments` to find it; `get-experiment` for details. |
| Need to change locked fields mid-experiment | Use `save-and-start-experiment-iteration` (single call) rather than stopping and recreating by hand. |
| `update-experiment` returns `skipped` for a field | Inspect the `currentStatus` and `allowedFields` in the response — that field isn't mutable in the current iteration status. Either stop the iteration first or use `save-and-start-experiment-iteration`. |

## What NOT to Do

- Don't fill in a missing flag, variation, hypothesis, control variation, randomization unit, or primary metric yourself.
- Don't call `create-metric` for a custom-event primary metric when `list-metric-events` shows the event is not reaching LaunchDarkly.
- Don't call `create-metric` or `create-experiment` before the user approves a complete design.
- Don't treat "yes", "looks good", or "create it" as choosing how a new metric is measured, and don't call `create-metric` while that choice is blank. A reply that only names the measure fills the blank. Show the completed design again and ask for approval before `create-metric` or `create-experiment`.
- Don't call `start-experiment-iteration` or `save-and-start-experiment-iteration` until the user explicitly says to start.
- Don't turn a flag on or off, or change its targeting, unless the user explicitly asks you to.
- Don't omit `iteration` on `create-experiment` — it's required.
- Don't set `baseline: true` on more than one treatment.
- Don't let `allocationPercent` values fail to sum to 100 across treatments.
- Don't try to change locked iteration fields with `update-experiment` while the iteration is `running` — reach for `save-and-start-experiment-iteration` instead.
- Don't stop iterations early — wait for statistical significance.
- Don't run multiple experiments on the same flag at the same time without a careful holdout design.
