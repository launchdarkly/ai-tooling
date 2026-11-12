# Environment release plans

Use this from Step 6 of the onboarding skill. A release plan is a reusable recipe for one environment, made of phases, rollout steps, and metrics; auto-releasing uses the environment's default plan. A plan with metrics makes a release guarded, so a regression on a metric can roll it back. A plan without metrics is progressive: say so.

Always call `get-environment-release-plans` before creating, so the new key does not collide with an active plan (an active key returns 409). If a starter's key is taken, add `-2` (then `-3`, and so on) until the key is free. An incomplete plan cannot start a release or become the default, so an environment with only incomplete plans needs a new complete one.

## Starter plans

Offer these when an environment has no plans. Each is a normal plan the user can change later. All use automatic advancement and `cleanupBehavior: "remove_rules_and_update_default_rule"` (the release finishes by serving everyone). With no rollback metrics they are progressive; with rollback metrics they are guarded. A guarded plan allows at most 50000 (50%) per step and needs the randomization unit to be available for guarded rollouts. Allocations are per 100,000 (10000 = 10%); there is no 100% step, because completing the release reaches everyone. `<unit>` is the randomization unit, `user` unless the project uses another context kind.

| Starter | Key | Phases |
|---------|-----|--------|
| Progressive (non-production) | `progressive` | One phase for everyone: 10% for 4h, then 50% for 4h |
| Progressive (production) | `progressive` | One phase for everyone: 10%, 25%, 50%, each for 4h |
| Internal users first (production) | `internal-first` | Phase 1, internal users: one step for 4h, with the clauses below. The step is 99% (the most one step allows), or 50% with rollback metrics. Phase 2, everyone: 10%, 25%, 50%, each for 4h |

Every phase includes the randomization unit clause; alone it means everyone:

```json
{ "attribute": "kind", "op": "in", "values": ["<unit>"], "contextKind": "<unit>" }
```

The internal-users phase adds one email clause with every confirmed domain (up to 25 values):

```json
{ "attribute": "email", "op": "endsWith", "values": ["@acme.example", "@acme-corp.example"], "contextKind": "<unit>" }
```

The match is exact and case-sensitive: `dev@Acme.example` does not match `@acme.example`. Say so in the plan summary.

The email clause only works if the app sends an `email` attribute on that context kind, so the skill offers this starter only when `search-contexts` finds a context of the unit's kind with `email` set.

Rollback metrics go in `progressiveRelease.metrics`, keyed by metric key, each with automatic rollback:

```json
{ "user-error-rate": { "isGroup": false, "autoRollback": true } }
```

Use only metrics whose `analysisUnits` include the plan's randomization unit; others cannot measure the release.

Each 4-hour hold is `durationMillis: 14400000`. After Step 8 creates a starter, set it as the environment's default with `update-default-environment-release-plan` (`default: true`).

## Custom plans

Follow the `create-environment-release-plan` tool guidance. Ask each setting as its own question, never bundled:

1. **Randomization unit**: the context kind to roll out by, such as `user` or `account`.
2. **Rollout steps**: header "Rollout", with options such as "10% → 25% → 50%, 4h holds" or "10% → 50%, 24h hold". The user can type another schedule in Other.
3. **Advancement**: header "Advance", options "Automatic", description "Move to the next step when the hold ends and metrics are healthy", and "Manual", description "A person moves each step".
4. **Metrics**: call `get-metrics`. Offer up to four relevant metrics with `multiSelect: true`. If none fit, use [`launchdarkly-metric-choose`](../../../metrics/launchdarkly-metric-choose/SKILL.md) to decide which metrics to add, and record each one to create. Step 8 creates them in LaunchDarkly before the plans that use them. This flow creates the metric only: if the app does not send the event yet, list instrumenting it as a follow-up, and do not edit code or `.env` files.
5. **Cleanup**: header "Cleanup", options "Leave rules in place" and "Remove rules and update the default rule", each with its outcome.
