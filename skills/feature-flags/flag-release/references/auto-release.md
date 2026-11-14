# Auto-release: flag releases & release plans

This is the mechanism behind the "release" half of the skill. The goal: once the PR
merges and the guarding flag starts evaluating, the change rolls out **on its own**,
the way the team has decided changes should roll out in each environment, with no human toggling a flag.

## The pieces

- **Flag**: the boolean gate you created (OFF everywhere). Nothing happens to users until a release turns it on.
- **Environment release plan**: a reusable recipe for one environment: phases, rollout steps, and metrics. A plan with metrics is guarded, so a regression on a metric can roll the release back. A plan without metrics is progressive. Each environment can have one **default** plan.
- **Flag release plan**: a project-level recipe. It lists environments in release order. For each one it gives a `triggerType` and either an `environmentReleasePlanKey` or `isImmediate: true`. A project can have one default flag release plan. Manage these with the [`launchdarkly-release-plans`](../../../release-autopilot/launchdarkly-release-plans/SKILL.md) skill.
- **Flag release**: one release of one flag, started by `create-flag-release` from a flag release plan and linked to the PR. Its ID is the `config_id`. Inspect it later with `get-automated-rollout-config`.

## Triggers: when an environment releases

Each environment in the flag release plan has a `triggerType`:

| `triggerType` | When the environment starts | Held? |
|---------------|-----------------------------|-------|
| `flag_eval` | When the flag is first evaluated there (after the change deploys) | No |
| `webhook` | When the deploy signal for the linked pull request arrives | No |
| `promotion` | When the previous environment finishes | No, unless the previous environment is held |
| `manual` | When a person starts it | Yes, until a person starts it |

An environment that the plan leaves out is not released. These are the only two ways to hold an environment in a flag release. `create-flag-release` has no field for a hold, a date, or a subset of the plan's environments.

## Preview before you propose

Always read the flag release plan (`get-flag-release-plans` with `flagReleasePlanKey`) and each environment release plan it names (`get-environment-release-plans` with `environmentKey` and `releasePlanKey`), so you and the user know what each environment will do. The plans do not depend on the flag, so the preview works before the flag exists too.

- Show each environment release plan's name, rollout steps (`progressiveRelease.phases[].steps`, allocations per 100,000), advancement mode, and metrics.
- `progressiveRelease.metrics` keyed by metric key makes the plan **guarded**. Empty metrics make it **progressive**: say so, because nothing rolls it back automatically.
- A release starts the plan on the flag's default rule. That needs a plan with one phase for everyone (only the randomization unit clause). A plan with several phases, or with a phase that targets an audience, fails to start. Tell the user before you start it.
- An incomplete environment release plan (migrated from a release policy) cannot start a release. Say so when the flag release plan names one.

### No usable flag release plan

- The project lists only the built-in `default-release-configuration`: it has no stored plan, and the built-in plan cannot start a release. Point the user to `launchdarkly-release-plans` (or [`launchdarkly-release-autopilot-onboarding`](../../../release-autopilot/launchdarkly-release-autopilot-onboarding/SKILL.md)) to create one.
- No listed plan fits the intent: start nothing. Name the environments that conflict, and point the user to `launchdarkly-release-plans` to create or change a plan that fits.

**A guarded release is only as good as its metrics.** If an environment release plan is **guarded**, check that its metrics are relevant to this change: a guarded rollout with no meaningful metric guards nothing. Watch for the **net-new path** case (from `should-flag-change`'s output, if present): when the flag-off control renders nothing, feature-specific before/after comparisons are "one-armed" and can't detect a regression, so a guarded release must lean on existing global/service metrics. If the plan's metrics can't compare treatment vs. control for this change, say so and offer a plan with an immediate release for that environment (or point the user at metric setup) rather than presenting a guarded rollout that can't actually guard.

## Precedence

For each environment, precedence is:

**human release intent → flag release plan → environment release plan**

The intent picks which environments may release. The flag release plan says how and when each one does. The environment release plan it names gives the steps and metrics. If nothing releases an environment, it is held: say why.

A human's stated intent, captured before the release starts (release now / hold / `notBefore` / segment /
prerequisite), sits *above* every plan: if the user said "hold until August," you don't start a release
whose plan releases that environment on its own, no matter what the plan would do.

**Fail closed.** Intent is honored or explicitly held, never silently dropped. If you can't
express a piece of intent through the plans (for example a `notBefore` date, which a `manual`
environment can only wait for), hold the environment and report the date and reason, rather than
starting a release that ignores the constraint. An unclear intent should *prevent* a release,
never cause one.

## Starting the release

Call `create-flag-release` in the implement phase:

```json
{
  "projectKey": "default",
  "flagKey": "new-checkout-flow",
  "flagReleasePlanKey": "standard-release",
  "pullRequest": { "repoFullName": "acme/storefront", "number": 482 },
  "confirm": true
}
```

The guarding flag must already exist. A boolean flag releases from `false` to `true` with no variation IDs. A multi-variate flag needs both `startingVariationId` and `endingVariationId` (the variations' `_id`). Always send `pullRequest` for a PR's change; LaunchDarkly rejects a plan with a `webhook` environment without it. A flag can have only one active release: if it has one, the error names it. The call returns `config_id` and the release as read back. Record `config_id` in your report.

## Fallback without `create-flag-release`

`create-flag-release` and `get-flag-release-plans` are preview tools on the hosted MCP server. When `create-flag-release` is not listed, or a call returns `tool disabled`, record the release with `create-automated-rollout-config`. Do not say the account lacks flag releases.

- Sort the environments into RELEASE and HOLD as above. List each RELEASE environment once, in release order, and leave every HOLD environment out of `environments`: that is the only way to hold one. Do not add a hold or date field.
- An environment with an environment release plan: `{ "environmentKey": "production", "releaseType": "policy", "environmentReleasePlanKey": "guarded-prod" }`. Leave out `environmentReleasePlanKey` to use the environment's default release plan. Without `get-flag-release-plans`, read each environment's plans with `get-environment-release-plans` and use the default, or the plan the user names. An environment with no default release plan and no named plan is held.
- An immediate environment: `{ "environmentKey": "staging" }`, with no `releaseType`.
- A `manual` environment in the flag release plan is held. Send `executionMode: "sequential"`, and `repoFullName` and `prNumber` for the PR.
- Show any warnings to the user as they are. `missing_default_release_plan` means the environment has no default release plan: hold it or name a plan. `incomplete_release_plan` and `release_plan_unchecked` mean the plan could not start or was not checked.

## Coupling to a parent flag (prerequisites)

When the change depends on another feature that isn't live yet, don't leave the ordering as a
human note: make it structural with a LaunchDarkly **prerequisite**. The dependent flag lists
the parent as a prerequisite (parent must serve its "on" variation) so the dependent can be
turned on safely: while the parent is off, the dependent stays effectively off; when the parent
releases, the dependent goes live in lockstep. This is native LaunchDarkly behavior, so it's the
right way to express "this must not go live before X." Set it via the MCP surface if it exposes
prerequisite editing; if it doesn't, report the required prerequisite as a manual step and do not
start a release that could release this flag ahead of its parent.

## Relationship to guarded rollouts

When an environment release plan is **guarded**, the release runs the
same kind of progressive, metric-monitored rollout described in the
[`launchdarkly-guarded-rollout`](../../launchdarkly-guarded-rollout/SKILL.md) skill. The
difference is that here the release plan drives it automatically, rather than a person starting it
by hand. If a change needs a *bespoke* rollout that no release plan expresses, hold that environment
here and drive the guarded rollout manually with that skill after merge.
