---
name: flag-release
description: "Start the release of an existing LaunchDarkly flag that guards a pull request's change, from the project's flag release plan, or from each environment's release plan when the project has none, so the change releases safely after the PR merges. Honors a stated release intent (release now / hold / notBefore / segment / prerequisite): it never starts a release that would release a held environment. Use as the release step once the guarding flag exists and its code is wired. Keywords: start release, flag release, flag release plan, environment release plan, guarded rollout, progressive rollout, release intent, hold release, dark launch."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server. Operates on a flag that already exists; does not create flags or edit code.
metadata:
  author: launchdarkly
  version: "0.4.0"
---

# Start a Flag's Release

You're using a skill that takes an **existing** feature flag (created OFF) that guards a pull request's change, and starts its release so the change releases safely after the PR merges, with no human toggling a flag. The skill starts a **flag release** with `create-flag-release`, in one of two ways:

- **From a flag release plan** (`kind: "plan"`). A flag release plan is an optional project-level recipe: it lists environments in release order, and for each one it names an **environment release plan** (rollout steps and metrics) or says the environment releases immediately.
- **From each environment's release plan** (`kind: "custom"`). This is the normal path for a project with no flag release plan, and for a request that a flag release plan cannot express. It names the environments to release, in order, and each one's environment release plan and trigger.

`create-automated-rollout-config` is only a fallback, for a server whose `create-flag-release` is not listed, does not offer `kind: "custom"`, or returns `tool disabled`. See [Which tool starts the release](#which-tool-starts-the-release).

A human-stated release intent sits above every plan.

This is the **release step** of the PR flag workflow, and it's deliberately atomic:

| Step | Owned by |
|------|----------|
| Decide *whether* to flag | [`should-flag-change`](../should-flag-change/SKILL.md) (advisory) |
| Create the flag + wire the code | [`launchdarkly-flag-create`](../launchdarkly-flag-create/SKILL.md) |
| **Start the release** | **this skill** |

By the time this skill runs, the flag exists (OFF) and the guarding code is wired and pushed. This skill only starts the release. It never creates flags or edits code. It can be driven directly by an automation harness, or as the final step of the [`flag-and-release-change`](../flag-and-release-change/SKILL.md) orchestrator.

**The deploy is not the release.** The merge ships the control path (flag OFF). The *release* is the flag operation that LaunchDarkly performs afterward, governed by the plans.

> **Honoring a hold is the one thing you must get right.** Each recorded environment releases by its `triggerType`. There is no per-call field for a hold or a date. An environment is held only when it is left out of the release, or has `triggerType: "manual"` (it waits for a person). Never record an environment that the user holds with a trigger that releases it on its own (`flag_eval`, `webhook`, or `promotion` after a released environment). When in doubt, hold.

## Prerequisites

- The remotely hosted LaunchDarkly MCP server.
- The guarding flag already exists in LaunchDarkly, created OFF, with the agreed key/tags.
- A pull-request reference (`repoFullName` + PR number) so the release follows the right merge. If you have only the PR URL (`https://github.com/<owner>/<name>/pull/<number>`), take `repoFullName` and the number from it. Without a PR reference, see [No pull request](#edge-cases).

**MCP tools this skill uses:**
- `create-flag-release` — start the flag release. Always send `projectKey`, `flagKey`, `confirm: true`, and the variation IDs as [references/auto-release.md](references/auto-release.md#variations) says. Send `pullRequest: { repoFullName, number }` for the PR. Only a release whose environments all wait for a person can start without a PR (see [No pull request](#edge-cases)). Returns `config_id`.
  - From a flag release plan: `kind: "plan"` and `flagReleasePlanKey`. If the tool's schema has no `kind` argument (an older server), leave `kind` out: a plan release is the default.
  - From each environment's release plan: `kind: "custom"`, `executionMode: "sequential"`, and `environments` in release order. Each entry has `environmentKey`, plus `releaseType: "policy"` for an environment with an environment release plan, and `environmentReleasePlanKey` for a named plan. An immediate environment has only `environmentKey`. Send `triggerType` only when the flag release plan or the user names one; a left-out trigger is `flag_eval`. The entries take the same shape as in `create-automated-rollout-config`. See [references/auto-release.md](references/auto-release.md#release-with-environment-release-plans).
- `create-automated-rollout-config` — the fallback only: start the release from each environment's release plan when `create-flag-release` is not listed, does not offer `kind: "custom"`, or returns `tool disabled`. Same environments and variation IDs, in this tool's own field names (see [references/auto-release.md](references/auto-release.md#fallback-create-automated-rollout-config)). Returns `config_id`.
- `get-flag-release-plans` — list the project's flag release plans (`default: true` marks the default). Read one with `flagReleasePlanKey` for its environments, each with `triggerType` and `environmentReleasePlanKey` or `isImmediate`.
- `get-environment-release-plans` — read an environment's release plans (`environmentKey`), or one plan (`releasePlanKey`).
- `get-flags` — confirm the flag exists and is OFF before you start the release.
- `get-projects` — list the projects when the user has not named one, or (with `projectKey`) list the project's environments when you need their keys.
- `update-automated-rollout-config` — change a release that has not started releasing (read it with `get-automated-rollout-config` first, then send `projectKey`, `configId`, the whole `environments` list, and `confirm: true`). The read is snake_case and the write is camelCase: rebuild each environment as [references/auto-release.md](references/auto-release.md#change-a-recorded-release) says, so a non-default plan is not reverted. Use it when the user asks to change a release, instead of recording a second one.

To edit or remove a flag release plan or an environment release plan (`update-` and `delete-` tools), use [`launchdarkly-release-plans`](../../release-autopilot/launchdarkly-release-plans/SKILL.md). This skill does not change plans.

### Which tool starts the release

`create-flag-release` and `get-flag-release-plans` are preview tools on the hosted server. `create-flag-release` offers `kind: "custom"` when its input schema lists `kind` with the value `custom`, and `environments`. Check the schema, then choose the tool and the kind with the table in [references/auto-release.md](references/auto-release.md#choose-how-to-start-the-release). That table is the only list of these rules. Do not say the account lacks flag releases.

Full release model, triggers, precedence, previewing, prerequisites, metric adequacy: [references/auto-release.md](references/auto-release.md).

## Plan Phase

**Start nothing in this phase.**

**Every question carries what it asks about.** While a question is open, the user may see only the question, not your message. Put the plan that the question is about in the question: the environments in release order, each one's trigger, and the flag release plan names. Use the `preview` of the option that accepts it, or the question text if the question tool has no preview.

1. **Confirm the project and the flag.** If the user has not named a project, list the projects with `get-projects`. If more than one exists, ask which project. Do not guess. If exactly one exists:
   - An interactive run (a person can answer): name the project and ask the user to confirm it before any write.
   - An automated run (a harness, with no one to answer) whose request names the flag and the PR: use that project, and do not stop to ask. Name the project in the plan and in the report.

   Then call `get-flags` to verify the guarding flag exists and is OFF. If it doesn't exist yet, stop: creation is [`launchdarkly-flag-create`](../launchdarkly-flag-create/SKILL.md)'s job.
2. **Choose how to start the release.** Call `get-flag-release-plans` with `projectKey`. When `hasMore` is true, read the next page with `nextOffset` as `offset`, until `hasMore` is false. If the user names a flag release plan, or the project has one with `default: true`, read it with `flagReleasePlanKey` to get its environments in order. Then choose with the table in [references/auto-release.md](references/auto-release.md#choose-how-to-start-the-release). A project with no flag release plan starts from each environment's release plan: this is a normal path, so do not ask the user to create a flag release plan first. Only a 403 that says the account cannot use flag release plans ("Plan does not allow this operation") lets the release continue without them. Any other failed read (a 5xx, or another 403) stops the release: the default plan can hold a `manual` gate that you cannot see.
3. **Preview each environment.** Find what each environment will do: `isImmediate` serves the new variation to everyone at once; an environment release plan runs its steps. Read each plan with `get-environment-release-plans` (`projectKey`, `environmentKey`, and `releasePlanKey` for a named plan). To find an environment's default plan, list its plans and read every page (`hasMore`, `nextOffset`). A plan with metrics is **guarded** (a regression rolls it back). A plan without metrics is **progressive**. For a guarded plan, check that its metrics can compare this change (see the metric-adequacy note in [references/auto-release.md](references/auto-release.md)). Note each environment's `triggerType`.

   If an environment release plan read fails (a 403 or 5xx from `get-environment-release-plans`, or the tool is not listed), start nothing and record nothing. Tell the user which read failed. Do not start a release without knowing the plan, steps, and metrics of each environment.
4. **Capture the human's release intent.** Ask (briefly, only if not already stated): release **on merge**, **hold**, or wait until a **`notBefore`** date? A **cohort/segment** to target first? A **prerequisite** parent flag this must not precede? Intent sits above the plans in precedence and is **honored or explicitly held, never silently dropped**.
5. **Check that the flag release plan fits the intent** (only when step 2 chose one). Sort each environment into RELEASE, HOLD, or EXCLUDED. When the request or harness names the target environments, every other environment is EXCLUDED. When it names none, an environment that the user does not mention follows the plan.
   - A HOLD environment fits only if the plan leaves it out, gives it `triggerType: "manual"`, or gives it `promotion` after a held environment.
   - A RELEASE environment fits only if the plan includes it with a trigger that releases it (`flag_eval`, `webhook`, or `promotion` after a released environment). A `promotion` environment after a `manual` or left-out environment waits for that environment, so it does not release on merge.
   - An EXCLUDED environment fits only if the plan leaves it out. `create-flag-release` cannot release a subset of the plan.
   - A `notBefore` date fits no flag release plan. LaunchDarkly cannot enforce the date.

   If the plan does not fit, start from each environment's release plan instead (`kind: "custom"`), and tell the user why (which environment the plan would release, or which date it cannot hold). Copy the flag release plan's environments, plans, and triggers, as [references/auto-release.md](references/auto-release.md#release-with-environment-release-plans) says.

   An environment that should release on merge but would wait in the plan is different: copying the plan keeps the wait. Record nothing and ask first, as [references/auto-release.md](references/auto-release.md#release-with-environment-release-plans) step 3 says.
6. **Present the per-environment plan.** Say how the release starts (the flag release plan's name, or "each environment's release plan"). For each environment, state one of these, with the reason:
   - It releases immediately, and when (its trigger).
   - It releases with an environment release plan. Name the plan, its steps, and its metrics.
   - It is **held**: left out, or waiting for a person (`manual`). Give the date or the reason. For a date, say that LaunchDarkly does not enforce it: a person must start the environment on or after the date. A scheduled start is a planned follow-up.
   - It is not part of this release (EXCLUDED).

   Wait for confirmation; revise on feedback. Put the per-environment plan in the confirmation question.

   If the user or harness already asked you to start the release and gave the intent for the environments, that request is the confirmation. Show the plan and go on to the implement phase in the same turn. An environment whose intent the user leaves unclear ("not sure yet") is HOLD. Stop for an answer when an environment that should release on merge would wait in the plan.

## Implement Phase

Only after confirmation (or a request to start the release that already states the intent):

1. **Start the release.**
   - From a flag release plan: call `create-flag-release` with `kind: "plan"` (left out when the schema has no `kind`), `projectKey`, `flagKey`, `flagReleasePlanKey`, `pullRequest: { repoFullName, number }`, and `confirm: true`. If the call returns `tool disabled`, record nothing yet. The user approved the flag release plan, not this version. Build the environment release plan version from the flag release plan's environments, through [references/auto-release.md](references/auto-release.md#release-with-environment-release-plans) steps 2, 3, and 6 (sort the environments, ask about a wait, check the PR). Show it, say that the flag release plan could not start, and ask the user to confirm it, with the plan in the question. After the user confirms, record it as [references/auto-release.md](references/auto-release.md#fallback-create-automated-rollout-config) says: check for an existing release, then call `create-automated-rollout-config` with that tool's field names.
   - From each environment's release plan: call `create-flag-release` with `kind: "custom"` as [references/auto-release.md](references/auto-release.md#release-with-environment-release-plans) says. On a server without `kind: "custom"`, or after a `tool disabled` result, follow [references/auto-release.md](references/auto-release.md#fallback-create-automated-rollout-config): show the version for `create-automated-rollout-config`, wait for the user to confirm it, check for an existing release, and only then call it. Tell the user which tool recorded the release.

   Do not copy the plans' steps or metrics anywhere: the plans stay the source. If a **prerequisite** parent flag was agreed, wire it if the MCP surface supports it; otherwise report it as a manual step.
2. **Verify.** The call returns `config_id` and the release as read back. Record `config_id`. If it returns an error that says the release was created but the read-back failed, inspect it with `get-automated-rollout-config` and do not start it again. Report only what you verified.
3. **Report** how the release started and `config_id`; per environment, what releases and how (plan name, steps, metrics), what is **held** (and why), and what is not part of the release; and what happens after the merge (for example: "staging serves true when the flag is first evaluated there; production then starts `guarded-prod`, 10% → 25% → 50%, and rolls back if `error-rate` regresses; dev is not part of this release"). Name any trigger you changed (for example a `promotion` environment that now starts on first evaluation because the environment before it is not part of the release).

## Edge Cases

| Situation | Action |
|-----------|--------|
| Flag doesn't exist yet | Stop: creation is `launchdarkly-flag-create`. |
| No pull request | If any environment to record uses `webhook` or `flag_eval` (including a left-out trigger, which means `flag_eval`), stop and ask for the PR: without one, the release can start before the change is deployed. A release whose environments all wait for a person (`manual`, or `promotion` after a `manual` environment) can start without one. |
| The flag already has an active release | LaunchDarkly returns an error that names it. Don't archive it yourself. Point the user to the existing release. |
| A flag release or rollout config already exists for this flag + PR | Don't start a second one, with either tool: a duplicate confuses the scheduler. Point the user to the existing config. To change it before it starts releasing, use `update-automated-rollout-config` with `confirm: true`. |
| The project is not named, and exactly one project exists | Interactive run: name it, and confirm it before any write. Automated run (no one to answer) whose request names the flag and the PR: use it without a question, and name it in the report. |
| An environment release plan read fails (403, 5xx, or `get-environment-release-plans` is not listed) | Start nothing and record nothing. Tell the user which read failed. |
| No flag release plan, a plan that does not fit, a failed flag release plan read, or a server without `create-flag-release` or `kind: "custom"` | Choose with the table in [references/auto-release.md](references/auto-release.md#choose-how-to-start-the-release). |
| The user asks for the default flag release plan, and no plan is the default | Ask which plan to use, with each plan's environments and triggers in the question, or offer to start from each environment's release plan. Never pick the first listed plan. |
| An environment that should release on merge would wait in the flag release plan | Record nothing and ask first, as [references/auto-release.md](references/auto-release.md#release-with-environment-release-plans) step 3 says. Copying the plan keeps the wait. |
| The flag is not boolean, and the user did not say which variations to release from and to | Ask, with the flag's variations in the question. See [references/auto-release.md](references/auto-release.md#variations). |
| An environment release plan has more than one phase, or targets an audience | A release starts the plan's one phase on the flag's default rule, for everyone, and a flag release plan accepts only plans with exactly one phase. Tell the user the plan cannot release there; offer another plan, a hold, or a change to the plan. |
| User wants to hold an environment (no date) | Leave it out of the release, or use a flag release plan that makes it `manual`. Report it as held with the reason. |
| User sets a `notBefore` date for an environment | Record it with `triggerType: "manual"`. Say that LaunchDarkly does not enforce the date: a person must start it on or after the date. A scheduled start is a planned follow-up. |
| Every environment is held or not part of the release | Record nothing. Report each environment and why. |
| An environment that needs a release plan has no default release plan, and neither the user nor the flag release plan names one | Hold it. Do not pick another plan, also when it is the only plan. Say that auto-release cannot run there until it has a default release plan, and point to `launchdarkly-release-plans`. |
| Change depends on a parent flag not yet live | Couple them with a prerequisite (set it if the MCP surface supports it); otherwise report the coupling as a required manual step. Don't let this flag release before its parent. |
| An environment release plan is guarded but has no relevant metric | Say so: a guarded rollout with no meaningful metric guards nothing. Offer a plan with an immediate release there, or point at metric setup. |

## What NOT to Do

- **Don't create the flag or edit code**: that's `launchdarkly-flag-create`. This skill only starts the release.
- **Don't turn the flag on yourself, or toggle it after the release starts.** The release owns that.
- **Don't record a held environment with a trigger that releases it.** No call field holds an environment.
- **Don't skip the plan reads.** Starting a release without knowing what each environment does is guessing.
- **Don't silently release against a stated hold/`notBefore`.** Honor intent or hold, never drop it.
- **Don't require a flag release plan.** A project without one releases from each environment's release plan, with `create-flag-release` and `kind: "custom"`.
- **Don't use `create-automated-rollout-config` when `create-flag-release` offers `kind: "custom"`.** It is the fallback for an older server, and the tool that changes a recorded release is `update-automated-rollout-config`.
- **Don't create, change, or delete release plans**: environment and flag release plans are managed by `launchdarkly-release-plans` (and by `launchdarkly-release-autopilot-onboarding` at setup).
- **Don't handle or print credentials.** Use the MCP server's OAuth and the user's existing git access; never read tokens from the machine.

## References

- [references/auto-release.md](references/auto-release.md): the release model, triggers, precedence (intent → flag release plan → environment release plan), previewing, starting from a flag release plan or from each environment's release plan, changing a recorded release, prerequisites, metric adequacy. *(Core of this skill.)*
- [`launchdarkly-release-plans`](../../release-autopilot/launchdarkly-release-plans/SKILL.md): read, create, and manage environment and flag release plans.
- [`launchdarkly-release-autopilot-onboarding`](../../release-autopilot/launchdarkly-release-autopilot-onboarding/SKILL.md): set up release plans for a project.
- [`launchdarkly-guarded-rollout`](../launchdarkly-guarded-rollout/SKILL.md): for a *bespoke* rollout that no release plan expresses: hold that environment here and drive the guarded rollout by hand after merge.
