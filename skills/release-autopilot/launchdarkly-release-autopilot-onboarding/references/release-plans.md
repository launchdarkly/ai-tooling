# Create an environment release plan

Use this from Step 6 of the onboarding skill when the account has environment release plans. A release plan is a reusable recipe for one environment, made of phases, rollout steps, and metrics. A plan with metrics makes a release guarded, so a regression on a metric can roll it back. A plan without metrics is progressive: say so.

Follow the `create-release-plan` tool guidance. Ask each setting as its own question, never bundled:

1. **Randomization unit**: the context kind to roll out by, such as `user` or `account`.
2. **Rollout steps**: header "Rollout", with options such as "1% → 10% → 50% → 100%, 4h holds" or "10% → 100%, 24h hold". The user can type another schedule in Other.
3. **Advancement**: header "Advance", options "Automatic", description "Move to the next step when the hold ends and metrics are healthy", and "Manual", description "A person moves each step".
4. **Metrics**: call `list-metrics`. Offer up to four relevant metrics with `multiSelect: true`. If none fit, use [`launchdarkly-metric-choose`](../../../metrics/launchdarkly-metric-choose/SKILL.md) to decide which metrics to add, and record each one to create. Step 8 creates them in LaunchDarkly before the plans that use them. This flow creates the metric only: if the app does not send the event yet, list instrumenting it as a follow-up, and do not edit code or `.env` files.
5. **Cleanup**: header "Cleanup", options "Leave rules in place" and "Remove rules and update the default rule", each with its outcome.

Every phase needs at least one clause. For a phase that targets everyone, use:

```json
{ "attribute": "kind", "op": "in", "values": ["<randomization unit>"], "contextKind": "<randomization unit>" }
```

`list-release-plans` hides incomplete plans that were migrated from release policies. If the user expects a plan that is missing, call it again with `includeIncomplete: true`. An incomplete plan cannot start a release, so that environment needs a new complete plan.

Always list before creating, so the new key does not collide with an active plan.
