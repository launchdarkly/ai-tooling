---
name: flag-release
description: "Start the release of an existing LaunchDarkly flag that guards a pull request's change, from the project's flag release plan, so the change releases safely after the PR merges. Honors a stated release intent (release now / hold / notBefore / segment / prerequisite): it never starts a release that would release a held environment. Use as the release step once the guarding flag exists and its code is wired. Keywords: start release, flag release, flag release plan, environment release plan, guarded rollout, progressive rollout, release intent, hold release, dark launch."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server. Operates on a flag that already exists; does not create flags or edit code.
metadata:
  author: launchdarkly
  version: "0.3.0"
---

# Start a Flag's Release

You're using a skill that takes an **existing** feature flag (created OFF) that guards a pull request's change, and starts a **flag release** for it from a **flag release plan**, so the change releases safely after the PR merges, with no human toggling a flag. A flag release plan is a project-level recipe: it lists environments in release order, and for each one it names an **environment release plan** (rollout steps and metrics) or says the environment releases immediately. A human-stated release intent sits above the plan.

This is the **release step** of the PR flag workflow, and it's deliberately atomic:

| Step | Owned by |
|------|----------|
| Decide *whether* to flag | [`should-flag-change`](../should-flag-change/SKILL.md) (advisory) |
| Create the flag + wire the code | [`launchdarkly-flag-create`](../launchdarkly-flag-create/SKILL.md) |
| **Start the release** | **this skill** |

By the time this skill runs, the flag exists (OFF) and the guarding code is wired and pushed. This skill only starts the release. It never creates flags or edits code. It can be driven directly by an automation harness, or as the final step of the [`flag-and-release-change`](../flag-and-release-change/SKILL.md) orchestrator.

**The deploy is not the release.** The merge ships the control path (flag OFF). The *release* is the flag operation that the flag release performs afterward, governed by the plans.

> **Honoring a hold is the one thing you must get right.** A flag release releases every environment in its flag release plan by that environment's `triggerType`. There is no per-call field for a hold or a date. An environment is held only when the plan leaves it out, or gives it `triggerType: "manual"` (it waits for a person). If the user holds an environment that the plan releases on its own (`flag_eval`, `webhook`, or `promotion` after a released environment), do **not** start the release with that plan. When in doubt, hold.

## Prerequisites

- The remotely hosted LaunchDarkly MCP server.
- The guarding flag already exists in LaunchDarkly, created OFF, with the agreed key/tags.
- A pull-request reference (`repoFullName` + PR number) so the release follows the right merge.

**MCP tools this skill uses:**
- `create-flag-release` — start the release from a flag release plan *(the deliverable)*. Send `projectKey`, `flagKey`, `flagReleasePlanKey`, `pullRequest: { repoFullName, number }`, and `confirm: true`. A boolean flag sends no variation IDs. A multi-variate flag sends both `startingVariationId` and `endingVariationId`. Returns `config_id`.
- `get-flag-release-plans` — list the project's flag release plans (`default: true` marks the default). Read one with `flagReleasePlanKey` for its environments, each with `triggerType` and `environmentReleasePlanKey` or `isImmediate`.
- `get-environment-release-plans` — read each environment release plan that the flag release plan names (`environmentKey` and `releasePlanKey`).
- `get-flags` — confirm the flag exists and is OFF before you start the release.
- `get-projects` (with `projectKey`) — list the project's environments when you need their keys.

`create-flag-release` and `get-flag-release-plans` are preview tools on the hosted server. If `create-flag-release` is not listed, or a call returns `tool disabled`, use the fallback: [references/auto-release.md](references/auto-release.md#fallback-without-create-flag-release).

Full release model, triggers, precedence, previewing, a missing plan, prerequisites, metric adequacy: [references/auto-release.md](references/auto-release.md).

## Plan Phase

**Start nothing in this phase.**

1. **Confirm the flag.** `get-flags` to verify the guarding flag exists and is OFF. If it doesn't exist yet, stop: creation is [`launchdarkly-flag-create`](../launchdarkly-flag-create/SKILL.md)'s job.
2. **Pick the flag release plan.** Call `get-flag-release-plans` with `projectKey`. Use the plan the user names, or else the plan with `default: true`. Read it with `flagReleasePlanKey` to get its environments in order. If the project lists only the built-in `default-release-configuration`, it has no stored plan, and that plan cannot start a release. Tell the user, and point to [`launchdarkly-release-plans`](../../release-autopilot/launchdarkly-release-plans/SKILL.md) to create one.
3. **Preview each environment.** For each environment in the plan, find what it does: `isImmediate` serves the new variation to everyone at once; an `environmentReleasePlanKey` runs that environment release plan. Read each named plan with `get-environment-release-plans` (`projectKey`, `environmentKey`, `releasePlanKey`). A plan with metrics is **guarded** (a regression rolls it back). A plan without metrics is **progressive**. For a guarded plan, check that its metrics can compare this change (see the metric-adequacy note in [references/auto-release.md](references/auto-release.md)). Note each environment's `triggerType`.
4. **Capture the human's release intent.** Ask (briefly, only if not already stated): release **on merge**, **hold**, or wait until a **`notBefore`** date? A **cohort/segment** to target first? A **prerequisite** parent flag this must not precede? Intent sits above the plans in precedence and is **honored or explicitly held, never silently dropped**.
5. **Check that the plan fits the intent.** Sort each environment that the intent names into RELEASE or HOLD, and compare with the plan. An environment that the user does not mention follows the plan; name it in the plan you present.
   - A HOLD environment fits only if the plan leaves it out or gives it `triggerType: "manual"`.
   - A RELEASE environment fits only if the plan includes it with a trigger that releases it (`flag_eval`, `webhook`, or `promotion`).
   - If the default plan does not fit, look for another listed plan that does, and propose it. If none fits, start nothing. Tell the user which environments the plan would release against the intent (or leave out), and point to [`launchdarkly-release-plans`](../../release-autopilot/launchdarkly-release-plans/SKILL.md) to create or change a plan that fits.
6. **Present the per-environment plan and stop.** Name the flag release plan. For each environment, state one of these, with the reason:
   - It releases immediately, and when (its trigger).
   - It releases with an environment release plan. Name the plan, its steps, and its metrics.
   - It is **held**: left out of the plan, or waiting for a person (`manual`). Give the date or the reason.

   Wait for confirmation; revise on feedback.

   If the user or harness already asked you to start the release and gave the intent for the environments, that request is the confirmation. Show the plan and go on to the implement phase in the same turn. An environment whose intent the user leaves unclear ("not sure yet") is HOLD. Stop for an answer only when no plan fits the intent.

## Implement Phase

Only after confirmation (or a request to start the release that already states the intent):

1. **Start the release.** Call `create-flag-release` with `projectKey`, `flagKey`, `flagReleasePlanKey`, `pullRequest: { repoFullName, number }`, and `confirm: true`. Do not copy the plans' steps or metrics anywhere: the plans stay the source. If a **prerequisite** parent flag was agreed, wire it if the MCP surface supports it; otherwise report it as a manual step.
2. **Verify.** The call returns `config_id` and the release as read back. Record `config_id`. If it returns an error that says the release was created but the read-back failed, inspect it with `get-automated-rollout-config` and do not start it again. Report only what you verified.
3. **Report** the flag release plan and `config_id`; per environment, what releases and how (plan name, steps, metrics), and what is **held** (and why); and what happens after the merge (for example: "staging serves true when the flag is first evaluated there; production then starts `guarded-prod`, 10% → 25% → 50%, and rolls back if `error-rate` regresses; production waits for a person until 2099-09-01").

## Edge Cases

| Situation | Action |
|-----------|--------|
| Flag doesn't exist yet | Stop: creation is `launchdarkly-flag-create`. |
| The flag already has an active release | LaunchDarkly returns an error that names it. Don't archive it yourself. Point the user to the existing release. |
| The project has no stored flag release plan | The built-in `default-release-configuration` cannot start a release. Point the user to `launchdarkly-release-plans` to create one. |
| No listed plan fits the intent | Start nothing. Say which environments conflict, and point to `launchdarkly-release-plans` to create or change a plan. |
| `create-flag-release` is not listed, or returns `tool disabled` | Use the [fallback](references/auto-release.md#fallback-without-create-flag-release). |
| An environment release plan has more than one phase, or targets an audience | A release starts the plan on the flag's default rule, which needs one phase for everyone. Tell the user the release will fail there; offer another plan, a hold, or a change to the plan. |
| User wants to hold, or set a `notBefore` date | Use a plan that leaves the environment out or makes it `manual`; report it as held with the reason. Never silently release against stated intent. |
| Change depends on a parent flag not yet live | Couple them with a prerequisite (set it if the MCP surface supports it); otherwise report the coupling as a required manual step. Don't let this flag release before its parent. |
| An environment release plan is guarded but has no relevant metric | Say so: a guarded rollout with no meaningful metric guards nothing. Offer a plan with an immediate release there, or point at metric setup. |

## What NOT to Do

- **Don't create the flag or edit code**: that's `launchdarkly-flag-create`. This skill only starts the release.
- **Don't turn the flag on yourself, or toggle it after the release starts.** The release owns that.
- **Don't start a release with a plan that releases a held environment.** No call field holds an environment.
- **Don't skip `get-flag-release-plans` and `get-environment-release-plans`.** Starting a release without knowing what each environment does is guessing.
- **Don't silently release against a stated hold/`notBefore`.** Honor intent or hold, never drop it.
- **Don't create, change, or delete release plans**: environment and flag release plans are managed by `launchdarkly-release-plans` (and by `launchdarkly-release-autopilot-onboarding` at setup).
- **Don't handle or print credentials.** Use the MCP server's OAuth and the user's existing git access; never read tokens from the machine.

## References

- [references/auto-release.md](references/auto-release.md): the flag release model, triggers, precedence (intent → flag release plan → environment release plan), previewing, a missing plan, prerequisites, metric adequacy, and the fallback without `create-flag-release`. *(Core of this skill.)*
- [`launchdarkly-release-plans`](../../release-autopilot/launchdarkly-release-plans/SKILL.md): read, create, and manage environment and flag release plans.
- [`launchdarkly-release-autopilot-onboarding`](../../release-autopilot/launchdarkly-release-autopilot-onboarding/SKILL.md): set up release plans for a project.
- [`launchdarkly-guarded-rollout`](../launchdarkly-guarded-rollout/SKILL.md): for a *bespoke* rollout that no release plan expresses: hold that environment here and drive the guarded rollout by hand after merge.
