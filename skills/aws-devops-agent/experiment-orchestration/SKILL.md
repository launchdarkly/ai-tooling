---
name: "experiment-orchestration"
description: "Takes a product goal through a LaunchDarkly experiment and, if it wins, a guarded rollout (or a regular rollout on plans without guarded rollouts). Uses GitHub for the code change and deployment when it is connected to the agent space; otherwise hands those steps to a person."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server in an AWS DevOps Agent space. GitHub is optional.
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# Automated Experimentation

Use this skill when you have a goal you want to move through experimentation (e.g., "increase checkout conversion by 15%", "decrease page load time by 20%").

**Core principle: experiment first, then a guarded rollout, or a regular rollout if the plan has no guarded rollouts.** Always prove a change on a small, fixed slice of traffic via an A/B experiment before rolling it out. Never roll out blind — the rollout exists only to scale a change the experiment has already shown to work.

**Execution mode:** once the goal is confirmed (Step 1), run Steps 2–8 end-to-end. Async operations (code implementation, release review, deployment, experiment monitoring, rollout monitoring) should be checked periodically, not tight-polled — see the waiting note in each step. Stop and ask the user only for a planned handoff (merging the PR; any code, review, or deploy step you hand over without GitHub) or if a step fails unrecoverably (repeated failed release reviews, deployment failure, or an inconclusive/losing experiment result).

**Approvals:** if the LaunchDarkly environment requires approval for a change (for example, to turn a flag on or off, start or stop an experiment, or start a guarded rollout), create an approval request instead of the direct change. Call the change tool directly; if the response has `requiresApproval: true`, pass the returned instructions to `create-approval-request`. Don't guess beforehand whether the environment requires approval. Tell the person who must review it. Continue only after `list-approval-requests` shows it approved, then apply it with `apply-approval-request` and go to the next step. If a reviewer rejects it, stop and report.

**GitHub:** Steps 2–5 use GitHub when it is connected to the agent space. Before Step 2, check whether you have GitHub access to the target repository. If you don't, read no code: ask the user where the change belongs, and in Step 3 give them the flag key and the change to make, then wait until they confirm the change is reviewed, merged, and deployed, and skip to Step 6. Triggering workflows and proposing fixes need the GitHub connection's Read and write permissions; with Read-only, hand those steps to the user.

**Always produce the Step 8 report on every terminal outcome.** The moment an experiment or rollout reaches a terminal outcome — winner, loser, inconclusive, or rollback — produce the full report in the same turn you announce the outcome. Don't let a casual "it worked!" substitute for the structured report.

## Step 1: Goal Clarification

Before doing anything, get answers to:

1. **What metric measures success?** *(Required)* e.g. conversion rate, page load time, bounce rate. Reserve your error-rate metric as a safety guardrail — never use it as the primary success metric.
2. **What's the target improvement?** *(Required)* e.g. 15% increase, 200ms decrease.
3. **What's the current baseline?** *(Optional — infer from production metrics if not given)*
4. **What parts of the app are in scope?** *(Optional — infer from the codebase if not given)*
5. **Any constraints?** *(Optional)* e.g. no changes to the payment flow.
6. **How much regression should roll a change back?** *(Optional — propose one per guardrail metric if not given)* Used as each metric's `regressionThreshold` in Step 7.

Questions 1–2 are required before proceeding; infer 3–6 where possible and confirm your assumptions with the user before implementing.

## Step 2: Hypothesis Generation

Explore the target repository/codebase to find a plausible change:

1. Search and read the relevant code paths.
2. Think through what UI/UX or logic change could plausibly move the chosen metric.
3. Check whether this hypothesis (or something close to it) has already been tried and failed — look at flag history or archived flags with similar naming. Avoid repeating a known failure.
4. Present the hypothesis to the user before proceeding, along with your reasoning and any inferred assumptions from Step 1.

**Before finalizing a flag key, check for collisions:** look up any candidate flag key first.
- Already fully shipped (100% one variation, no split) → already decided, pick a different hypothesis.
- Actively running an experiment → mid-flight, don't compete with it, pick a different hypothesis.
- Doesn't exist → safe to create.

## Step 3: Implementation

1. Create a boolean feature flag, OFF by default in all environments, with `defaults` of `{"onVariation": 1, "offVariation": 1}` so that it serves false even when it is on, and `clientSideAvailability` of `{"usingEnvironmentId": true, "usingMobileKey": true}` so that every SDK can read it. Name it with a clear pattern like `exp-<metric>-<short-description>` (e.g. `exp-checkout-conversion-cta-color`), lowercase with hyphens, ~50 chars max. If the project has its own flag naming conventions (for example, a required prefix or case), follow them instead.
2. If a coding agent is available, hand off the implementation to it, with instructions to gate the change behind the exact flag key from step 1. Without a coding agent or GitHub write access, give the user the flag key and the change instead, and wait for their PR (with GitHub connected) or their confirmation that it is deployed (without GitHub).
3. This step is asynchronous — check status periodically rather than looping tightly on it.
4. Once implementation completes, move to Step 4 with the resulting branch/PR. If it fails, report the error and stop.

## Step 4: Release Readiness

Run an AWS DevOps Agent release readiness code review on the PR before it merges. It runs automatically on connected repositories with **Auto trigger change review** enabled; otherwise request one.

- If it passes: ask the user to merge the PR, and wait until they confirm it is merged.
- If it fails: feed the review's specific feedback back into implementation (or to the user, if they made the change) and retry. Cap retries at a small fixed number (e.g. 3 attempts total) — if it still hasn't passed, stop and report the last failure to the user rather than retrying indefinitely.

Never skip the review. Without GitHub, ask the user to have the PR reviewed and merged.

## Step 5: Deployment

The flagged code must be running in the environment the experiment uses before Step 6 turns the flag on; otherwise the experiment measures nothing. Confirm the merged change is deployed there. If the deploy workflow runs only when triggered (for example, `workflow_dispatch`), trigger it as below.

1. Trigger the deploy workflow on the merge target branch (this needs Read and write GitHub access; otherwise ask the user to deploy and confirm when it's done). Treat "already an in-progress deployment for this ref" as expected de-duplication, not an error — don't re-trigger.
2. Check the workflow run's status periodically rather than looping tightly.
3. If a run reports "running" for far longer than normal, check the workflow run history for that commit before assuming it's still in progress.
4. **Trigger a deployment at most once per attempt.** If you're unsure whether a previous trigger succeeded, check status first — never re-trigger just because you're unsure.
5. On timeout: stop, check the CI run directly, report the situation, ask how to proceed.
6. On explicit failure: stop and report — do not proceed to the experiment.
7. On success: proceed immediately to Step 6.

## Step 6: Experiment Phase (fixed 10%)

Prove the change on a small, fixed slice of traffic. The experiment and the rollout never run at the same time: a guarded rollout can't start while an experiment is running on the flag, so Step 7 stops the experiment iteration before Phase 2 starts any rollout.

1. Turn the flag ON.
2. Configure a fixed 50/50 split across 10% of traffic (a flat allocation, not a staged ramp) on your chosen randomization unit (typically "user"). The remaining 90% of traffic is excluded from the experiment entirely.
3. Create an experiment with:
   - Exactly one primary metric: the success metric from Step 1.
   - Guardrail metric(s): always include your error-rate metric; add a performance metric (e.g. p95 page load time) too if this is a performance-focused change.
   - Treatments: control (off) at 50%, treatment (on) at 50%, allocated to 10% of total traffic.
   - An analysis that stays valid when results are checked repeatedly: `methodology: "frequentist"` with `analysisConfig.sequentialTestingEnabled: true`, or `methodology: "bayesian"`. Step 7 checks results many times, and a fixed-horizon frequentist test checked that way declares false winners.
4. Start the experiment/data collection.
5. Move to Step 7 to monitor toward a decision.

## Step 7: Monitoring & Outcome

Check status periodically — don't tight-loop. In an interactive session, check once and report progress, then pick back up later. Every MCP write needs a person to approve it, so an unattended run stops at its first write: run checks that may lead to a write in a session where someone can approve, and report progress so the next session can pick it up.

**Phase 1 — Prove the experiment at 10% (gate before any rollout):**

Watch for statistical significance on the primary metric:

- **Significant + positive lift** → experiment proven. Stop the experiment iteration with control as the winner, then move to Phase 2. Stopping serves the winner to the experiment's targeting rule (everyone, when the experiment is on the default rule), so a treatment winner would skip the guarded rollout. If the plan has no guarded rollouts, still stop with control as the winner and use the regular rollout in Phase 2.
- **Significant + negative lift** → declare a loser, stop the iteration with control as the winner, turn the flag off (do not archive it while the code still evaluates it), skip Phase 2, go straight to the Step 8 report.
- **No significance after a reasonable ceiling (e.g. 4 weeks)** → report "inconclusive, need more traffic", stop the iteration with control as the winner, and stop; don't proceed to Phase 2.

Never declare a winner off a single data point or before your stats engine confirms significance. Also require at least 100 exposures in each variation before acting on a significant result; with fewer, keep collecting data.

**Phase 2 — Guarded rollout ramp (only after Phase 1 proves the change):**

Start a guarded rollout with:
- The winning ("on") variation as the test, the original as control.
- Same randomization unit as the experiment.
- **Exactly 3 monitored stages, each below 50%** — e.g. 20% → 30% → 40%, ~60 minutes monitoring each. `rolloutWeight` is in thousandths of a percent (20% is `20000`) and `monitoringWindowMilliseconds` is in milliseconds (60 minutes is `3600000`). Don't add a 100% stage.
- `updateDefaultRuleOnCompletion: true`, so the rollout moves the default rule to the winning variation once the final stage completes cleanly.
- The same primary + guardrail metrics as the experiment, each with `onRegression` set to notify and roll back, and a `regressionThreshold` (required) from Step 1.

Track stage progression. If the rollout rolls back or stops at any point, treat it as a regression: declare failed, turn the flag off (do not archive it while the code still evaluates it), and go to the Step 8 report.

Once the final stage completes cleanly and the default rule serves the winning variation, declare a winner and go to the Step 8 report.

**If the plan has no guarded rollouts:** if `start-guarded-rollout` fails because guarded rollouts aren't available on the plan, use a regular rollout instead:
1. Read the flag's variations to find the indexes of `true` and `false`. Call `update-rollout` with `rolloutType: "variation"` and the index of `true` on the default rule. This serves the treatment to everyone at once, with no automatic rollback.
2. Check the guardrail metrics once per monitoring window, for about as long as the guarded rollout would have run (e.g. 3 hours). Reverting is a write that needs a person's approval, so run this watch in a session where someone can approve.
3. If a guardrail regresses, call `update-rollout` with the index of `false`, declare failed, and go to the Step 8 report. Otherwise, declare a winner and go to the Step 8 report.

**Retrying after a guarded rollout rollback:** a rollback isn't always caused by your monitored metrics genuinely regressing — it can also be triggered by an unrelated application error surfacing mid-ramp. Before blindly restarting after the user says they've fixed something:
1. Confirm the flag's current state (should be back to 100% control, nothing stuck mid-rollout).
2. Check the change history timing between "advanced to next stage" and "reverted." A rollback within seconds of advancing is inconsistent with a full metric-window regression and points to an external cause instead.
3. If the flag is cleanly reverted and the external cause is confirmed fixed, it's safe to restart the guarded rollout from scratch with the same parameters.
4. Don't silently retry without this check, and don't refuse to retry just because a prior attempt rolled back — a genuinely fixed external cause is a legitimate reason to retry. A metric-driven loser is not — don't retry that.

**On any terminal outcome, immediately produce the Step 8 report in the same turn** — a one-line "it worked!" note is fine as a lead-in, but the structured report must follow, not wait for a follow-up request.

## Step 8: Report

Runs automatically the instant Step 7 reaches a terminal outcome (winner, with the default rule serving it; loser; inconclusive; or rollback/failure). Use this exact structure from Experiment Report to Next Steps:

```markdown
## Experiment Report: [Goal Description]

**Date:** [YYYY-MM-DD]
**Goal:** [metric] [direction] by [target]%
**Status:** [achieved / in progress / stalled]

### Hypothesis
[What we tried and why]

### Implementation
- Flag: [flag_key]
- Files modified: [list]
- Branch: [branch name]

### Release Readiness
- [release readiness review passed after N attempt(s) / reviewed by the user]

### Experiment Phase (10% fixed split)
- Status: [proven / loser / inconclusive]
- Duration: [time]
- Metric change: [before] → [after] ([+/-]%)
- Statistical significance: [value, confidence interval]

### Rollout Phase (if reached)
- Type: [guarded rollout / regular rollout (no guarded rollouts on this plan)]
- Status: [completed / rolled_back / not started]
- Duration: [time]
- Stages reached: [N of 3 monitored stages, guarded rollout only]
- If rolled back and retried: [root cause, outcome of retry]

### Safety Metrics
- error-rate: [baseline] → [final] ([no regression / regression detected])
- [other guardrails]: [baseline] → [final] ([status])

### Next Steps
[What to do next based on the outcome]
```

## Safety Rules (the non-negotiables)

- Always present the hypothesis before implementing.
- Always have the PR reviewed before merging: the release readiness review with GitHub, or the user's review without it. Never skip it.
- **Always prove a change via a fixed small-percentage experiment before starting any rollout** — never roll out blind.
- Always include an error-rate (or equivalent "don't break prod") metric as a guardrail, separate from your success metric.
- Add a performance guardrail (e.g. p95 latency) for performance-focused changes.
- Every guarded rollout metric should be configured to both notify AND auto-rollback on regression — don't rely on notification alone. A regular rollout has no automatic rollback, so watch its guardrail metrics after rolling out.
- **Keep guarded rollout stages below 50%** and let the rollout move to 100% after the final stage — don't add an explicit 100% stage.
- Distinguish a metric-driven rollback (don't retry) from an external-cause rollback (safe to retry once fixed) before restarting a rolled-back rollout.
- Produce the Step 8 report on every terminal outcome — never defer it to a follow-up ask.
