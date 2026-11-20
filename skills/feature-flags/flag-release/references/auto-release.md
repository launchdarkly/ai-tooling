# Auto-release: flag releases & release plans

This is the mechanism behind the "release" half of the skill. The goal: once the PR
merges and the guarding flag starts evaluating, the change rolls out **on its own**,
the way the team has decided changes should roll out in each environment, with no human toggling a flag.

## The pieces

- **Flag**: the boolean gate you created (OFF everywhere). Nothing happens to users until a release turns it on.
- **Environment release plan**: a reusable recipe for one environment: phases, rollout steps, and metrics. A plan with metrics is guarded, so a regression on a metric can roll the release back. A plan without metrics is progressive. Each environment can have one **default** plan.
- **Flag release plan** (optional): a project-level recipe. It lists environments in release order. For each one it gives a `triggerType` and either an `environmentReleasePlanKey` or `isImmediate: true`. A project can have one default flag release plan. A project does not need one to release. Manage these with the [`launchdarkly-release-plans`](../../../release-autopilot/launchdarkly-release-plans/SKILL.md) skill.
- **Flag release**: one release of one flag, linked to the PR. `create-flag-release` starts it, from a flag release plan (`kind: "plan"`) or from each environment's release plan (`kind: "custom"`). On a server whose `create-flag-release` does not offer `kind: "custom"`, `create-automated-rollout-config` starts it from each environment's release plan. Its ID is the `config_id`. Inspect it later with `get-automated-rollout-config`, and change it with `update-automated-rollout-config`.

## Triggers: when an environment releases

Each environment in a release has a `triggerType`:

| `triggerType` | When the environment starts | Held? |
|---------------|-----------------------------|-------|
| `flag_eval` | When the flag is first evaluated there (after the change deploys). This is the default when the trigger is left out | No |
| `webhook` | With a linked pull request, when a deploy that includes the merge arrives. Without one, on the next deploy signal for the environment | No |
| `promotion` | When the previous environment finishes. The first environment cannot use it | No, unless the previous environment is held |
| `manual` | When a person starts it | Yes, until a person starts it |

An environment that is left out of the release is not released. These are the only two ways to hold an environment. No call has a field for a hold or a date.

## Choose how to start the release

This table is the only list of these rules. [`flag-release`](../SKILL.md) and [`launchdarkly-release-plans`](../../../release-autopilot/launchdarkly-release-plans/SKILL.md) link here.

| Situation | Start the release with |
|-----------|------------------------|
| The user names a flag release plan, or the project has a default one, and it fits the intent | `create-flag-release`, `kind: "plan"`. If the tool's schema has no `kind` argument (an older server), leave `kind` out: a plan release is the default |
| The project has no flag release plan (an empty list), or none is the default and the user names none | `create-flag-release`, `kind: "custom"`, with each environment's release plan |
| A flag release plan exists but does not fit the intent (an environment that the request excludes or holds, or a `notBefore` date) | `create-flag-release`, `kind: "custom"`, with the flag release plan's environments, plans, and triggers. Tell the user why |
| An environment that should release on merge would wait in the flag release plan | Nothing yet. Ask the user first, as [step 3 below](#release-with-environment-release-plans) says. Copying the plan keeps the wait |
| `create-flag-release` works, but `get-flag-release-plans` is not listed or returns `tool disabled` | An automated run (no one can answer): nothing. Record nothing, and say which tool was missing or disabled. An interactive run: nothing yet. Say that flag release plans cannot be read, so the gates of a default plan (for example a `manual` production gate) will not apply. Ask whether to record a `kind: "custom"` release anyway, and record it only after the user says yes |
| A `get-flag-release-plans` read returns a 403 that says the account cannot use flag release plans ("Plan does not allow this operation") | `create-flag-release`, `kind: "custom"`. Tell the user that the account has no flag release plans |
| Any other failed `get-flag-release-plans` read (a 5xx, or another 403) | Nothing. Record nothing, and tell the user which read failed: the project's default plan can hold a `manual` gate that you cannot see |
| A failed `get-environment-release-plans` read (any 403 or 5xx), or the tool is not listed | Nothing. Record nothing, and tell the user which read failed |
| `create-flag-release` is listed, but its schema does not offer `kind: "custom"` (an older server) | A plan that fits: `create-flag-release` without `kind`. Otherwise: `create-automated-rollout-config`, as [Fallback](#fallback-create-automated-rollout-config) says |
| `get-flag-release-plans` works, but `create-flag-release` is not listed | `create-automated-rollout-config`, as [Fallback](#fallback-create-automated-rollout-config) says. When a flag release plan fits, use its environments, plans, and triggers |
| The whole flag release preview is missing: neither `get-flag-release-plans` nor `create-flag-release` is listed, or both return `tool disabled` | `create-automated-rollout-config` for each environment's release plan, as [Fallback](#fallback-create-automated-rollout-config) says. Tell the user that flag release plans could not be read, so the gates of a default plan (for example a `manual` production gate) cannot be applied |
| `create-flag-release` returns `tool disabled`, with either kind | Nothing yet. Show the `create-automated-rollout-config` version, and record it only after the user confirms, as [Fallback](#fallback-create-automated-rollout-config) says |

In every row, "nothing" means: do not call `create-flag-release` or `create-automated-rollout-config`.

Releasing from each environment's release plan is a normal path, not an error. Do not ask the user to create a flag release plan before a release. You can mention it as an option for later.

If the user asks for "the default flag release plan" and the list has plans but none is the default, ask which plan to use, or offer to start from each environment's release plan. Put each plan's name, environments, and triggers in the question. Never pick the first listed plan.

A failed environment release plan read always stops the release. A failed flag release plan read stops it too. Only the 403 that says the account cannot use flag release plans continues. There are two exceptions. When `create-flag-release` works but `get-flag-release-plans` is missing or disabled, an interactive run continues after the user says yes. When the whole flag release preview is missing, the release uses the `create-automated-rollout-config` fallback, and the skill tells the user that a default plan's gates cannot be applied.

## Preview before you propose

Always read the plans, so you and the user know what each environment will do: the flag release plan (`get-flag-release-plans` with `flagReleasePlanKey`) when there is one, and each environment release plan (`get-environment-release-plans` with `environmentKey`, and `releasePlanKey` for a named plan). Read every page of a list (`hasMore`, `nextOffset`). The plans do not depend on the flag, so the preview works before the flag exists too.

- Show each environment release plan's name, rollout steps (`progressiveRelease.phases[].steps`, allocations per 100,000), advancement mode, and metrics.
- `progressiveRelease.metrics` keyed by metric key makes the plan **guarded**. Empty metrics make it **progressive**: say so, because nothing rolls it back automatically.
- A release starts an environment release plan's one phase on the flag's default rule, so the plan must have exactly one phase, for everyone (only the randomization unit clause). A flag release plan accepts only such plans. A plan with two or more phases cannot release, and a phase that targets an audience fails to start. Tell the user before you start it.
- An incomplete environment release plan (migrated from a release policy) cannot start a release. Say so when the release would use one.

**A guarded release is only as good as its metrics.** If an environment release plan is **guarded**, check that its metrics are relevant to this change: a guarded rollout with no meaningful metric guards nothing. Watch for the **net-new path** case (from `should-flag-change`'s output, if present): when the flag-off control renders nothing, feature-specific before/after comparisons are "one-armed" and can't detect a regression, so a guarded release must lean on existing global/service metrics. If the plan's metrics can't compare treatment vs. control for this change, say so and offer a plan with an immediate release for that environment (or point the user at metric setup) rather than presenting a guarded rollout that can't actually guard.

## Precedence

For each environment, precedence is:

**human release intent → flag release plan (if any) → environment release plan**

The intent picks which environments may release. The flag release plan, when there is one, says how and when each one does. The environment release plan gives the steps and metrics. If nothing releases an environment, it is held: say why.

A human's stated intent, captured before the release starts (release now / hold / `notBefore` / segment /
prerequisite), sits *above* every plan: if the user said "hold until August," you don't record that
environment with a trigger that releases it on its own, no matter what the plan would do.

**Fail closed.** Intent is honored or explicitly held, never silently dropped. When a flag release
plan cannot express the intent (an environment that the request excludes or holds, or a `notBefore`
date), start the release from each environment's release plan (`kind: "custom"`) and tell the user why. LaunchDarkly
cannot enforce a `notBefore` date: record that environment as `manual`, and say that a person must
start it on or after the date (a scheduled start is a planned follow-up). An unclear intent should
*prevent* a release, never cause one.

## Starting from a flag release plan

Call `create-flag-release` in the implement phase:

```json
{
  "projectKey": "default",
  "flagKey": "new-checkout-flow",
  "kind": "plan",
  "flagReleasePlanKey": "standard-release",
  "pullRequest": { "repoFullName": "acme/storefront", "number": 482 },
  "confirm": true
}
```

On a server whose `create-flag-release` has no `kind` argument, leave `kind` out: that server starts only from a flag release plan. The guarding flag must already exist. Send the variation IDs as [Variations](#variations) says. Always send `pullRequest` for a PR's change. Without it, a `webhook` environment starts on the next deploy signal for that environment, which can be a deploy that does not include the change. A flag can have only one active release: if it has one, the error names it. The call returns `config_id` and the release as read back. Record `config_id` in your report.

## Variations

`create-flag-release` (both kinds) and `create-automated-rollout-config` take the same variation IDs: `startingVariationId` (the variation to release from) and `endingVariationId` (the variation to release to). Each is a variation's `_id` from `get-flags`.

- A boolean flag, and the user did not choose variations: send neither. The release goes from `false` to `true`.
- The user chose the variations: send both.
- The flag is not boolean, and the user did not say which variations to release from and to: ask before you start or record the release. Put the flag's variations (name and value) in the question. Then send both.

Never send only one of the two.

## Release with environment release plans

Start a flag release with `create-flag-release` and `kind: "custom"` when the project has no flag release plan to use, when a flag release plan does not fit the intent, when the flag release plan read returns the 403 "Plan does not allow this operation", or when the user says yes after `get-flag-release-plans` is missing or disabled while `create-flag-release` works. On a server without `kind: "custom"`, do the same steps and record the result with `create-automated-rollout-config` ([Fallback](#fallback-create-automated-rollout-config)). Do not say the account lacks flag releases.

Do these steps in order:

1. **Find the environments.**
   - A flag release plan was read (it does not fit, or `create-flag-release` is not available or returns `tool disabled`): use its environments, in its order.
   - No flag release plan: use the environments that the user or harness names, in the order given. If none are named, list the project's environments with `get-projects` and ask which ones the release covers and in what order.
2. **Sort each environment into RELEASE, HOLD, or EXCLUDED.**
   - EXCLUDED: the request or harness names the target environments, and this environment is not one of them. It is not part of the release.
   - HOLD (left out of the call) when one of these is true:
     - The user holds it, with no date. This applies also when it is the only environment.
     - The user's intent for it is unclear ("not sure yet", "not confirmed").
     - The flag release plan gives it `triggerType: "promotion"`, and the environment before it is HOLD. A `promotion` environment starts only when the previous environment finishes, and a HOLD environment is not in the call, so the `promotion` environment would follow the wrong one. Step 3 can move it back to RELEASE.
     - It needs an environment release plan (it is not immediate), it has no default release plan, and neither the user nor the flag release plan names a plan for it. An immediate environment (`isImmediate` in the flag release plan, or the user asks for an immediate release) needs no release plan, so this rule does not hold it. Do not pick another plan for it, also when it is the only plan. Say that auto-release cannot run there until it has a default release plan, and point to `launchdarkly-release-plans` to set one.
   - RELEASE: every other environment. This includes a `manual` environment in the flag release plan and a `promotion` environment after it: record them with their triggers, so they wait for a person as the plan says.
   - A `notBefore` date: RELEASE with `triggerType: "manual"`. LaunchDarkly does not enforce the date. Tell the user that a person must start the environment on or after the date, and that a scheduled start is a planned follow-up. Every entry after it waits for it, whatever its trigger (see [Order](#order) in step 5).
3. **Ask before you record a wait the user did not want.** If the user wants an environment to release on merge, but the flag release plan makes it wait, record nothing yet. Ask about the first such environment in release order. Put the flag release plan's name and its environments in release order, each with its trigger, in the question:
   - The plan gives it `triggerType: "manual"` (it waits for a person): release it on merge (`flag_eval`), or keep it waiting for a person.
   - The plan gives it `promotion` after a HOLD environment: release it on merge, or keep the plan's wait. To release it on merge, give it `triggerType: "flag_eval"`. It still starts only after the entry before it in the call, if there is one. Tell the user about the changed trigger.
   - An earlier entry waits for a person (`manual`, or a `notBefore` date), and the user does not want that environment on merge. A later entry cannot start before it ([Order](#order) in step 5), so ask:
     1. Keep the plan's order and the wait. This environment follows the waiting one.
     2. Leave the earlier environments that wait for a person out of the release. A flag can have only one active release, so a person changes their targeting by hand. This environment gets `triggerType: "flag_eval"`. When no entry comes before it, it is the first entry and starts on merge. Otherwise it still starts only after the entries before it complete, and the question says so, with those entries named.

   Never reorder the plan's environments. A release whose environments differ from the plan's is a `kind: "custom"` release, as for any request that the plan cannot express.

   If the request already says to leave the earlier environment out, or to release that environment on merge without the environment it waits for when that environment is held (for example "hold dev, and release staging on merge without waiting for dev"), that is the answer: do not ask. Record the release without the left-out environment. A `promotion` environment after an EXCLUDED environment needs no question: step 5 starts the first entry on `flag_eval`. After each answer, check the later environments again. A `promotion` environment after an environment that now releases on merge follows it, and needs no question. An environment that the user did not ask to release on merge keeps the plan's trigger.
4. **If no environment is RELEASE, record nothing.** Do not call `create-flag-release` or `create-automated-rollout-config`. Report each environment as held or not part of the release, with its date or reason.
5. **Write one entry for each RELEASE environment**, in release order. Leave every HOLD and EXCLUDED environment out of `environments`. Do not add a hold or date field. Each entry has one of these two shapes, plus `triggerType`, and no other field. The entries take the same shape as in `create-automated-rollout-config`:
   - An immediate environment (`isImmediate` in the flag release plan, or the user asks for an immediate release): `{ "environmentKey": "staging" }`, with no `releaseType` and no `override`.
   - An environment with an environment release plan: `{ "environmentKey": "production", "releaseType": "policy", "environmentReleasePlanKey": "guarded-prod" }`. Use the plan that the user or the flag release plan names. Leave out `environmentReleasePlanKey` to use the environment's default release plan. Without a flag release plan, read each environment's plans with `get-environment-release-plans` to find the default.

   <a id="order"></a>**Order.** LaunchDarkly starts the entries in array order. An entry after the first starts only after the entry before it has released and completed, and its `waitBeforeReleaseMillis` has passed, whatever its trigger. So `flag_eval` on a later entry does not skip the entries before it. Never reorder the environments to get around a wait: ask as step 3 says.

   Copy each environment's `triggerType` from the flag release plan into its entry (`flag_eval`, `webhook`, `manual`, or `promotion`), unless step 3 changed it. A left-out `triggerType` means `flag_eval`, so a `webhook` environment without it starts on first evaluation, before the deploy arrives. Without a flag release plan, leave `triggerType` out unless the user names a trigger. Example: `{ "environmentKey": "production", "releaseType": "policy", "triggerType": "webhook" }`.

   If the first entry has `triggerType: "promotion"` because an environment before it is left out of the call (EXCLUDED or HOLD), send `flag_eval` for it instead: the first environment cannot use `promotion`. Never send `promotion` for the first entry. Later entries keep `promotion`, so each one follows the entry before it. Tell the user about the changed trigger.

   Never send `override` or `releaseType: "override"`, and never copy a plan's steps, stages, or metrics into the call. The plans stay the source.
6. **Check the pull request.** If no PR reference is known and any entry uses `webhook` or `flag_eval` (including a left-out trigger), stop and ask for the PR. A release whose entries all wait for a person (`manual`, or `promotion` after a `manual` entry) can start without one.
7. **Call `create-flag-release` with `kind: "custom"` in the same turn** when the user asked to start or record the release, unless step 3 is waiting for an answer. Call it once. If a flag release or rollout config already exists for this flag and PR (from an earlier call in this run, or one that the user or harness names), do not start a second one: point the user to the existing one. Send `projectKey`, `flagKey`, `kind: "custom"`, `executionMode: "sequential"` (LaunchDarkly accepts no other execution mode), the `environments` from step 5, `pullRequest: { repoFullName, number }` (left out only when step 6 lets the release start without a PR), `startingVariationId` and `endingVariationId` as [Variations](#variations) says, and `confirm: true`. If you have only the PR URL (`https://github.com/<owner>/<name>/pull/<number>`), take `repoFullName` and the number from it.

   ```json
   {
     "projectKey": "default",
     "flagKey": "new-checkout-flow",
     "kind": "custom",
     "executionMode": "sequential",
     "environments": [
       { "environmentKey": "staging", "triggerType": "flag_eval" },
       { "environmentKey": "production", "releaseType": "policy", "environmentReleasePlanKey": "guarded-prod", "triggerType": "promotion" }
     ],
     "pullRequest": { "repoFullName": "acme/storefront", "number": 482 },
     "confirm": true
   }
   ```
8. **Show any warnings to the user as they are.** `missing_default_release_plan` means the environment has no default release plan: hold it or name a plan. `create-flag-release` does not warn in that case: it creates nothing and returns an error. Then ask the user which environment release plan to use, or hold the environment, and call it again. `incomplete_release_plan` and `release_plan_unchecked` mean the plan could not start or was not checked.

### Fallback: `create-automated-rollout-config`

Use it only when `create-flag-release` is not listed, its schema does not offer `kind: "custom"`, or a call returns `tool disabled`. Do steps 1 to 8 as above, with `create-automated-rollout-config` in step 7:

- **Confirmation.** When the fallback is known in the plan phase (the tool is not listed, or has no `kind: "custom"`), show this version as the plan. The plan-phase confirmation, or a request that already asks to start the release, covers it. After a `tool disabled` result, record nothing yet: the user approved a flag release, not this version. Say that the flag release could not start, show this version with the environments and triggers in the question, and wait for the user to confirm it.
- **Duplicates.** Before the call, check that no flag release or rollout config already exists for this flag and PR, as step 7 says.
- **The call.** Call `create-automated-rollout-config` once, with the same environments in this tool's field names:

| `create-flag-release` (`kind: "custom"`) | `create-automated-rollout-config` |
|------------------------------------------|-----------------------------------|
| `environments` entries | the same |
| `pullRequest: { repoFullName, number }` | `repoFullName`, `prNumber`, and `prUrl` (`https://github.com/<owner>/<name>/pull/<number>`) |
| `executionMode`, `startingVariationId`, `endingVariationId` | the same |

Never send `releaseType: "override"` to this tool. It has no `confirm` field.

## Change a recorded release

`update-automated-rollout-config` changes a release that has not started releasing. Read it first with `get-automated-rollout-config`. Then send `projectKey`, `configId`, `confirm: true`, and the whole `environments` list: an environment you leave out is removed.

The read is snake_case and the write is camelCase. The write rejects unknown fields, so rebuild each environment from the read:

| Read (`get-automated-rollout-config`) | Write (`update-automated-rollout-config`) |
|---------------------------------------|-------------------------------------------|
| `environment_key` | `environmentKey` |
| `desired_release_type` | `releaseType` (`policy` or `override`). For an immediate release, send no `releaseType` |
| `environment_release_plan_key` | `environmentReleasePlanKey` |
| `trigger_type` | `triggerType` |
| `wait_before_release_millis` | `waitBeforeReleaseMillis` |
| `override.release_method`, `rollout_context_kind_key`, `stages`, `metric_keys`, `metric_group_keys`, `rollback_on_regression` | `override.releaseMethod`, `rolloutContextKindKey`, `stages`, `metricKeys`, `metricGroupKeys`, `rollbackOnRegression` |

Keep `releaseType: "policy"` and `environmentReleasePlanKey` for each environment that has them. Without them, a non-default plan (such as `guarded-prod`) reverts to the environment's default, or the environment becomes an override. Change only what the user asked.

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
