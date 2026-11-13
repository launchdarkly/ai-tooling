# Environment release plans: starters and custom plans

Use this from [Create](../SKILL.md#create). A release plan is a recipe for one environment, made of phases, rollout steps, and metrics. A plan with metrics makes a release guarded, so a regression on a metric can roll it back. A plan without metrics is progressive: say so.

## Before you offer a starter

Check the project with reads, not questions.

1. **Randomization unit:** `search-contexts` with `kind: "user"`, `limit: 1` in that environment. If it finds contexts, use `user`. If not, call `search-contexts` with no kind to see which kinds the project stores. If it finds other kinds, ask header "Roll out by" with those kinds and `user`. If it finds none, the app has not sent contexts yet: use `user`, the kind every project has by default, and say so. A plan whose unit is not a context kind in the project cannot be created.
2. **Rollback metrics:** a guarded plan needs the unit to be available for guarded rollouts, and no read shows that. LaunchDarkly turns this on for `user` by default. For any other unit, skip this check, use no metrics, and list "make <unit> available for guarded rollouts, then add rollback metrics to the plan" as a follow-up. For `user`, call `get-metrics` with `metricUsedIn: "guarded_rollouts"`, then without it if that finds none. Keep metrics whose `analysisUnits` include the unit; others cannot measure the release. If any remain, ask header "Rollback metrics", `multiSelect: true`, with up to three of them plus "No metrics" ("Release step by step without automatic rollback").

## Starter plans

Ask header "Starter plan" with options that fit the environment, marking the first "(Recommended)":

- Production: "Progressive" ("10% → 25% → 50% of everyone, with 4-hour holds"), "Custom" ("Build the plan step by step"), and "Not now" ("Leave this environment without a release plan for now").
- Any other environment: "Progressive" ("10% → 50% of everyone, with 4-hour holds"), "Custom", and "Not now".

If the user picked rollback metrics, add "rolls back automatically if <metric names> regress" to the descriptions. Then show the full plan and ask "Looks right" or "Adjust it". For "Not now", create nothing, and list "set up a release plan for <environment>" as a follow-up.

| Starter | Key | Phases |
|---------|-----|--------|
| Progressive (non-production) | `progressive` | One phase for everyone: 10% for 4h, then 50% for 4h |
| Progressive (production) | `progressive` | One phase for everyone: 10%, 25%, 50%, each for 4h |

Every starter uses automatic advancement and `cleanupBehavior: "remove_rules_and_update_default_rule"`, so the release finishes by serving everyone. Allocations are per 100,000 (10000 = 10%). There is no 100% step, because completing the release reaches everyone. Each 4-hour hold is `durationMillis: 14400000`. `<unit>` is the randomization unit.

The phase has only the randomization unit clause, which means everyone:

```json
{ "attribute": "kind", "op": "in", "values": ["<unit>"], "contextKind": "<unit>" }
```

Rollback metrics go in `progressiveRelease.metrics`, keyed by metric key, each with automatic rollback:

```json
{ "user-error-rate": { "isGroup": false, "autoRollback": true } }
```

A plan with metrics allows at most 50000 (50%) per step, and every starter step fits. A plan without metrics allows up to 99000 per step.

## Keys

Read the environment's plans before you create one. Plan keys are unique among the project's active plans, across environments, so the same starter in two environments needs two keys. If `progressive` is taken, use `progressive-2`, then `progressive-3`, and so on. A taken key returns 409.

## Custom plans

Ask each setting as its own question, never bundled:

1. **Randomization unit**: the context kind to roll out by, such as `user` or `account`.
2. **Rollout steps**: header "Rollout", with options such as "10% → 25% → 50%, 4h holds" or "10% → 50%, 24h hold". The user can type another schedule in Other.
3. **Advancement**: header "Advance", options "Automatic" ("Move to the next step when the hold ends and metrics are healthy") and "Manual" ("A person moves each step").
4. **Metrics**: call `get-metrics`. Offer up to four relevant metrics with `multiSelect: true`. If none fit, use [`launchdarkly-metric-choose`](../../../metrics/launchdarkly-metric-choose/SKILL.md) to decide which metrics to add, and record each one to create before the plan. This creates the metric only: if the app does not send the event yet, list instrumenting it as a follow-up, and do not edit code or `.env` files.
5. **Cleanup**: header "Cleanup", options "Leave rules in place" and "Remove rules and update the default rule", each with its outcome.

Every phase needs at least one clause. Follow the `create-environment-release-plan` tool guidance for the rest.
