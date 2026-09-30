---
name: launchdarkly-experiment-setup
description: "Design, set up, and run experiments in LaunchDarkly. Review the experiment design (hypothesis, metrics, randomization unit, allocation, duration), create experiments with metrics, treatments, and flag config, start iterations to collect data, swap design between iterations, and stop with a winner."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "0.3.0"
---

# LaunchDarkly Experiment Setup

You're using a skill that guides you through setting up and running experiments in LaunchDarkly. Your job is to review the experiment design with the user, create it with the right metrics, treatments, and flag config, start data collection, evolve the design between iterations when needed, and stop with a winner.

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
2. **Start the iteration** to begin data collection (`start-experiment-iteration`).
3. **Monitor** results as data accumulates (`get-experiment`).
4. **Evolve the design** mid-experiment if needed — change locked fields like `treatments`, `metrics`, or `methodology` by calling `save-and-start-experiment-iteration`, which stops the current iteration, creates a new draft with your changes, and starts it.
5. **Stop the iteration** when you have a winner or a clear call (`stop-experiment-iteration`).
6. **Ship** the winning variation.

## Core Principles

1. **Design before creation**: review the design (Step 0) before calling `create-experiment`. A fix costs a restart after data collection begins.
2. **Metrics first**: ensure the metrics you'll reference exist before creating the experiment.
3. **Clear hypothesis**: every iteration requires a `hypothesis` string; state what you expect to improve and by how much.
4. **Proper controls**: exactly one treatment must have `baseline: true`.
5. **Sufficient sample size**: let iterations run long enough for statistical significance.
6. **One change at a time**: test one variable per experiment for clear attribution.

## Workflow

### Step 0: Review the Design

Before touching any tools that write data, gather the design and review it with the user:

1. Ask for, or infer from the code and flag:
   - what change is being tested
   - which flag and rule drive it
   - who is exposed
   - what decision the result will drive
2. If the project already has experiments, skim them with `list-experiments` and `get-experiment` to match the team's conventions, such as metric naming, randomization unit, and methodology.
3. Walk through the [design review checklist](references/design-review.md): hypothesis, primary metric, guardrails, randomization unit, treatments and allocation, sample size and duration, variance reduction, exposure, and decision rule.
4. Report each item as OK or a concern, with a one-line reason and a suggested fix. Let the user accept or adjust, then carry the agreed design into Steps 1–4 unchanged.

Keep the review short when the user already has a clear design. The goal is to catch design mistakes that are costly after the iteration starts, not to add ceremony.

### Step 1: Prepare Metrics

1. Use `list-metrics` to find existing metrics.
2. If you need a new one, use `create-metric` and note the key.
3. Decide which is the **primary metric** (a single metric or a funnel group). You'll pass its key as `primarySingleMetricKey` or `primaryFunnelKey` on the iteration.

| Goal | Metric type | Example key |
|------|-------------|-------------|
| Conversion | Custom conversion | `checkout-completed` |
| Performance | Custom numeric | `page-load-time-ms` |
| Engagement | Custom conversion | `feature-clicked` |
| Revenue | Custom numeric | `order-value` |

### Step 2: Identify the Targeting Rule

You need the `ruleId` and current `flagConfigVersion` of the flag rule that will drive the experiment. Use `get-flag` on the flag (or its environment-scoped status) to find them. The fallthrough rule's id is the string `"fallthrough"`.

### Step 3: Create the Experiment

Call `create-experiment`. The top-level fields describe the experiment; the nested `iteration` object describes the first data-collection window.

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

Pass `changeJustification` if you're restarting after a prior iteration was stopped.

### Step 5: Verify

1. Call `get-experiment` and confirm `currentIteration.status === "running"`.
2. Check that treatments are present with the expected allocations.
3. Check the metric list and the primary metric.
4. Once traffic arrives, check for sample ratio mismatch, meaning the observed split doesn't match the configured allocation. If there's a large mismatch, stop and fix assignment or tracking before trusting any results.

### Step 6: Evolve the Design Mid-Experiment (when needed)

Most structural fields (treatments, metrics, methodology, hypothesis, …) are locked while an iteration is `running`. Two ways to change them:

- **Light edits while running** — `update-experiment` will let through anything `mutableFieldsByStatus` permits in the `running` state (typically just metadata like `name`, `description`, `maintainerId`, `tags`, plus appending `metrics`/`attributes`). It surfaces rejected fields under `skipped` with a reason.
- **Real design changes** — call `save-and-start-experiment-iteration`. It stops the current iteration, creates a new draft with the supplied field updates applied, and starts it in one call. Inputs match `update-experiment`, plus `changeJustification`. Mutability is checked against `not_started` since updates land on the new draft.

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
| Metric doesn't exist | Create it first with `create-metric`. |
| Flag has no variations to compare | Create flag variations before designing treatments. |
| You don't know the flag's `ruleId` / `flagConfigVersion` | Use `get-flag` or `get-flag-status-across-envs`. The fallthrough rule's id is the string `"fallthrough"`. |
| Experiment already exists | Use `list-experiments` to find it; `get-experiment` for details. |
| Need to change locked fields mid-experiment | Use `save-and-start-experiment-iteration` (single call) rather than stopping and recreating by hand. |
| `update-experiment` returns `skipped` for a field | Inspect the `currentStatus` and `allowedFields` in the response — that field isn't mutable in the current iteration status. Either stop the iteration first or use `save-and-start-experiment-iteration`. |

## What NOT to Do

- Don't create the experiment before the user has agreed on the hypothesis, primary metric, and randomization unit.
- Don't omit `iteration` on `create-experiment` — it's required.
- Don't set `baseline: true` on more than one treatment.
- Don't let `allocationPercent` values fail to sum to 100 across treatments.
- Don't try to change locked iteration fields with `update-experiment` while the iteration is `running` — reach for `save-and-start-experiment-iteration` instead.
- Don't stop iterations early — wait for statistical significance.
- Don't run multiple experiments on the same flag at the same time without a careful holdout design.
