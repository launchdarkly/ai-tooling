---
name: flag-release
description: "Record an automated rollout for an existing LaunchDarkly flag that guards a pull request's change, so the change releases safely when the PR merges. Honors a stated release intent (release now / hold / notBefore / segment / prerequisite) and otherwise releases each environment with its default environment release plan. Use as the release step once the guarding flag exists and its code is wired. Keywords: record release, automated rollout, release plan, default release plan, flag release plan, guarded rollout, progressive rollout, release intent, hold release, dark launch."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server. Operates on a flag that already exists; does not create flags or edit code.
metadata:
  author: launchdarkly
  version: "0.2.0"
---

# Record a Flag's Automated Release

You're using a skill that takes an **existing** feature flag (created OFF) that guards a pull request's change, and records an **automated rollout** so the change releases safely once the PR merges — no human toggling a flag. Each environment releases with its **default release plan** unless a human-stated release intent says otherwise.

This is the **release step** of the PR flag workflow, and it's deliberately atomic:

| Step | Owned by |
|------|----------|
| Decide *whether* to flag | [`should-flag-change`](../should-flag-change/SKILL.md) (advisory) |
| Create the flag + wire the code | [`launchdarkly-flag-create`](../launchdarkly-flag-create/SKILL.md) |
| **Record the release** | **this skill** |

By the time this skill runs, the flag exists (OFF) and the guarding code is wired and pushed. This skill only records the rollout — it never creates flags or edits code. It can be driven directly by an automation harness, or as the final step of the [`flag-and-release-change`](../flag-and-release-change/SKILL.md) orchestrator.

**The deploy is not the release.** The merge ships the control path (flag OFF); the *release* is the flag operation this rollout performs afterward, governed by the environment's release plan.

> **Honoring a hold is the one thing you must get right.** There is no "hold" release type, and **`releaseType: "policy"` is NOT a manual gate.** On merge, a `policy` environment *automatically* starts its default release plan (progressive or guarded) with **no human promotion step** — a guarded rollout still *starts on its own* the moment the PR merges. So recording a held environment as `policy` does **not** hold it; it releases it on merge, before any `notBefore` date. The only way to hold an environment is to **omit it from the `environments` array entirely**, which leaves the flag OFF there. If the user wants an environment held (or not released until a date), exclude it from the call and report it as held. When in doubt, omit.

## Prerequisites

- The remotely hosted LaunchDarkly MCP server.
- The guarding flag already exists in LaunchDarkly, created OFF, with the agreed key/tags.
- A pull-request reference (`repoFullName` + `prNumber`, or `prUrl`) so the rollout binds to the right merge.

**MCP tools this skill uses:**
- `create-automated-rollout-config` — record the rollout for the flag against the PR *(the deliverable)*. It has no field for holding, scheduling, or a `notBefore` date: every environment in its `environments` array releases on merge, and a held environment is left out.
- `get-environment-release-plans` — list an environment's release plans. The plan marked `default: true` is the plan a `policy` environment releases with. Call it for each target environment before you propose the plan.
- `get-flags` — confirm the flag exists and is OFF before recording.
- `get-projects` (with `projectKey`) — list the project's environments when none are named.

**Flag release plans.** A flag release plan is a project-level recipe that says, per environment, whether a flag releases immediately or with a named environment release plan. If the user names one, or the project has a default flag release plan, read it with the [`launchdarkly-release-plans`](../../release-autopilot/launchdarkly-release-plans/SKILL.md) skill. Do not create, change, or delete flag release plans from this skill.

Full release model — immediate vs `policy`, precedence, previewing, a missing default plan, prerequisites, metric adequacy: [references/auto-release.md](references/auto-release.md).

## Plan Phase

**Record nothing in this phase.**

1. **Confirm the flag.** `get-flags` to verify the guarding flag exists and is OFF. If it doesn't exist yet, stop — creation is [`launchdarkly-flag-create`](../launchdarkly-flag-create/SKILL.md)'s job, and recording a rollout for a missing flag fails confusingly.
2. **Pick the target environments.** Use the environments named by the user or harness. Don't hardcode a set — a given change can't always release to every environment. If none are named, enumerate the project's real keys and confirm the set rather than assuming.
3. **Preview each environment's default release plan.** Call `get-environment-release-plans` with `projectKey` and `environmentKey` for each target environment. Find the plan marked `default: true`. From it, read the rollout steps and metrics: a plan with metrics is **guarded** (a regression rolls it back), and a plan without metrics is **progressive**. For a guarded plan, check that its metrics can compare this change (see the metric-adequacy note in [references/auto-release.md](references/auto-release.md)). If a flag release plan applies, read it too: it can make an environment immediate or name another environment release plan for it.
4. **Find environments with no default release plan.** If no plan is marked default in an environment, auto-release cannot run there. Do not plan a `policy` release for it. Tell the user that the environment needs a default release plan first. To create one, point them to [`launchdarkly-release-plans`](../../release-autopilot/launchdarkly-release-plans/SKILL.md), [`launchdarkly-release-autopilot-onboarding`](../../release-autopilot/launchdarkly-release-autopilot-onboarding/SKILL.md), or the environment's release plan settings in LaunchDarkly. Plan the environment as held, or as an immediate release if the user asks for one. Do not copy the steps of a plan that is not the default into an override for it.
5. **Capture the human's release intent.** Ask (briefly, only if not already stated): release **on merge**, **hold** (recorded but not released yet), or wait until a **`notBefore`** date? A **cohort/segment** to target first? A **prerequisite** parent flag this must not precede? Intent sits above the release plans in precedence and is **honored or explicitly held — never silently dropped**.
6. **Present the per-environment plan and stop.** For each environment, state one of these, with the reason:
   - It releases immediately on merge.
   - It releases on merge with its default release plan. Name the plan, its steps, and its metrics.
   - It is **held**: omitted from the recorded config, so the flag stays OFF there.

   Wait for confirmation; revise on feedback.

## Implement Phase

Only after confirmation:

1. **Sort every target environment into exactly one bucket — RELEASE or HOLD.** Do this *before* you build the call. There is no third bucket, and no entry shape creates one.

   | Bucket | Meaning | What goes in the call |
   |--------|---------|-----------------------|
   | **RELEASE** | Goes live on merge — now, or with its default release plan | Add `{ environmentKey }` (immediate) or `{ environmentKey, releaseType: "policy" }` (default release plan) to the `environments` array |
   | **HOLD** | Not yet — waiting on a date, sign-off, segment, parent flag, or a default release plan | **Nothing.** Leave it out of `environments` entirely; name it as held in your report |

   The entry shape (immediate vs `policy`) only chooses *how* a RELEASE environment goes live — it never holds one. **Both release on merge:** an immediate entry (`environmentKey` alone, no `releaseType`) serves `true` immediately; `policy` starts that environment's default release plan automatically, with no human promotion step. "`policy` defers to the *release plan*" — not to you, and not until a date. **Do not reach for `policy` to park a held environment: it ships that environment on merge, before any `notBefore`.** The only encoding of a hold is *absence from the array*.

2. **Build `environments` from the RELEASE bucket only — then read the keys back.** The array must contain every RELEASE environment and no HOLD environment. Before you send the call, scan the `environmentKey`s in the array: if any environment you're holding appears there, delete that entry. The call has **no field for a date or a hold** — if you catch yourself wanting to add `holdUntil`, `notBefore`, or `hold` to an entry (or to keep it as `policy` "so it waits"), that is the signal the environment is HOLD: **drop the entry, don't invent a field.** The date and reason go in your report, not the call.

   Worked example — *"release staging on merge, hold production until 2026-09-01"*: staging is RELEASE, production is HOLD.

   ```json
   {
     "projectKey": "default",
     "flagKey": "new-checkout-flow",
     "environments": [{ "environmentKey": "staging" }],
     "repoFullName": "acme/storefront",
     "prNumber": 482
   }
   ```

   `production` appears nowhere in the call. You report it held until 2026-09-01, with the reason (legal sign-off). Fail closed: if an environment's intent is unclear, it's HOLD, not RELEASE.

3. **Record the rollout.** Call `create-automated-rollout-config` with `projectKey`, `flagKey`, the RELEASE-only `environments` array, and the PR reference. If a flag release plan names an environment release plan that is not the environment's default, follow [references/auto-release.md](references/auto-release.md#releasing-with-a-plan-that-is-not-the-default). If a **prerequisite** parent flag was agreed, wire it if the MCP surface supports it; otherwise report it as a manual step.
4. **Verify.** The call returns `created`, `config_id`, and the normalized per-environment plan — record `config_id`. Report only what you verified; flag anything you couldn't confirm rather than asserting it. If the call returns warnings, show them to the user as they are.
5. **Report** the per-environment release plan + `config_id`; what was **held** (and why) versus what releases on merge; and what happens on merge (e.g. "production starts its default release plan `guarded-prod` on merge, 10% → 25% → 50% and rolls back if `error-rate` regresses; staging serves true immediately; eu-production held until it has a default release plan").

## Edge Cases

| Situation | Action |
|-----------|--------|
| Flag doesn't exist yet | Stop — creation is `launchdarkly-flag-create`. Recording a rollout for a missing flag fails confusingly. |
| A rollout config already exists for this flag + PR | Don't record a second one — a duplicate confuses the scheduler. Point the user at the existing config to change the plan. |
| Registering before the PR exists | Immediate envs work without a PR, but `policy` envs need `repoFullName`/`prNumber` to trigger on merge. Prefer recording *after* the PR is open; if you record early, say `policy` won't fire until the PR is wired. |
| An environment has no default release plan | Auto-release can't run there yet. Don't record it as `policy`. Hold it, or record it as immediate if the user asks. Point the user to `launchdarkly-release-plans`, `launchdarkly-release-autopilot-onboarding`, or the environment's release plan settings to set a default plan. |
| The release plan tools are missing, or the read fails | You can't see the default plans, so don't record any `policy` environment. Tell the user what failed. On a missing tool, ask them to update or reconnect the LaunchDarkly MCP server. |
| The default plan has more than one phase, or targets an audience | Auto-release starts the plan on the flag's default rule, which needs one phase for everyone. Tell the user the release will fail there; offer an immediate release, a hold, or a change to the default plan. |
| User wants to hold, or set a `notBefore` date | Skip the releasing plan for those environments; report them as held with the reason. Never silently release against stated intent. |
| Change depends on a parent flag not yet live | Couple them with a prerequisite (set it if the MCP surface supports it); otherwise report the coupling as a required manual step. Don't let this flag release before its parent. |
| The default plan is guarded but has no relevant metric | Say so — a guarded rollout with no meaningful metric guards nothing. Recommend an immediate release, or point at metric setup. |

## What NOT to Do

- **Don't create the flag or edit code** — that's `launchdarkly-flag-create`. This skill only records the release.
- **Don't turn the flag on yourself, or toggle it after recording the config.** The rollout owns that; double-toggling causes audit noise and confuses the scheduler.
- **Don't skip `get-environment-release-plans`.** Proposing `policy` without knowing which default plan it starts is guessing.
- **Don't record `policy` for an environment with no default release plan.** Say that auto-release can't run there yet.
- **Don't silently release against a stated hold/`notBefore`.** Honor intent or hold — never drop it.
- **Don't create, change, or delete release plans** — environment and flag release plans are managed by `launchdarkly-release-plans` (and environment plans also by `launchdarkly-release-autopilot-onboarding`).
- **Don't handle or print credentials.** Use the MCP server's OAuth and the user's existing git access; never read tokens from the machine.

## References

- [references/auto-release.md](references/auto-release.md): the automated-rollout / release-plan model, immediate vs `policy`, precedence (intent → override → flag release plan → default release plan), previewing, a missing default plan, prerequisites, metric adequacy. *(Core of this skill.)*
- [`launchdarkly-release-plans`](../../release-autopilot/launchdarkly-release-plans/SKILL.md): read, create, and manage environment and flag release plans, including a missing default plan.
- [`launchdarkly-release-autopilot-onboarding`](../../release-autopilot/launchdarkly-release-autopilot-onboarding/SKILL.md): set up an environment's default release plan.
- [`launchdarkly-guarded-rollout`](../launchdarkly-guarded-rollout/SKILL.md): for a *bespoke* rollout no release plan expresses — record that env as immediate here and drive the guarded rollout by hand after merge.
