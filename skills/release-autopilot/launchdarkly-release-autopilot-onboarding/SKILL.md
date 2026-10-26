---
name: launchdarkly-release-autopilot-onboarding
description: "Step-by-step onboarding wizard for LaunchDarkly Release Autopilot: pick the capabilities you want (auto-flagging, auto-releasing), connect the GitHub App, map repositories to projects, choose Vega inference (LaunchDarkly managed or bring your own key), set up environment release plans, then verify. Use when the user wants to set up, onboard to, get started with, or turn on Release Autopilot for the first time. For a single settings change or 'why didn't my PR get classified?', use launchdarkly-release-autopilot-settings instead."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "0.1.0-experimental"
---

# LaunchDarkly Release Autopilot Onboarding

You're using a skill that walks a user through setting up Release Autopilot from nothing to a working setup. The user picks the capabilities they want, and you set up only what those capabilities need: the GitHub App, repository mappings, Vega inference, and environment release plans.

**This is a step-by-step wizard.** Ask one question at a time and wait for each answer. Gather every decision first, confirm one plan, and only then write. Release Autopilot opens and changes pull requests, and auto-releasing can ship code, so every write is production automation.

This skill reuses the rules of [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md) for every settings read and write. If the two disagree, the settings skill wins.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server.

**Required MCP tools:**
- `get-release-autopilot-settings` / `update-release-autopilot-settings`
- `list-release-autopilot-github-repos`
- `list-release-autopilot-repo-settings` / `get-release-autopilot-repo-settings` / `update-release-autopilot-repo-settings`

**Required for auto-releasing:**
- `list-release-plans` / `create-release-plan`
- `list-metrics` (release plans can only attach metrics that exist)

**Optional MCP tools:**
- `list-projects` / `get-project`: offer project and environment keys as options instead of asking for free text

If a required tool is missing, stop and tell the user which one. Do not invent REST calls.

Release Autopilot is in alpha. If every Release Autopilot tool returns 404, the account is not in the alpha. Tell the user and stop.

## Core Principles

1. **Only set up what they picked.** Release plans exist for auto-releasing. If the user picks auto-flagging only, skip the release plan step.
2. **Least privilege by default.** Recommend auto-flagging with approval required. Auto-releasing is opt-in and you must say it can ship code.
3. **Gather, confirm, then write.** No write happens before [Step 7](#step-7-confirm-the-plan). The confirmation lists every write with its current and proposed state.
4. **Never act in the user's browser.** GitHub install, GitHub authorization, and bring-your-own-key setup are browser steps. Give the exact link and wait for the user to say they finished.
5. **Only touch what the user named.** Never map every repo on the install. Never create release plans in environments the user did not pick.

## Workflow

**Progression rule:** When a step is complete, go to the next step. Do not stop between steps unless the step tells you to ask or wait.

**Response scoping:** During this flow, treat user messages as answers to the current question. Do not take unrelated actions until the flow is finished.

**Asking questions:** When a question has options, use `AskUserQuestion` with the labels and descriptions given below. Ask free-text questions as a normal message.

**State tracking:** Track every decision. Step 7 re-states all of them.

### Step 0: Welcome the user

Present this intro (you may lightly adapt the wording, but keep the structure):

> **Release Autopilot Setup**
>
> I'll set up Release Autopilot in a few short steps:
>
> 1. **Check your account**: I'll read your current Release Autopilot settings.
> 2. **Pick capabilities**: choose auto-flagging, auto-releasing, or both.
> 3. **Connect GitHub**: install or authorize the LaunchDarkly GitHub App.
> 4. **Map repositories**: choose which repos Release Autopilot watches, and which LaunchDarkly project each one uses.
> 5. **Choose inference**: run the agents on LaunchDarkly managed inference or on your own model provider key.
> 6. **Set up release plans** (auto-releasing only): define how each environment rolls out a change.
> 7. **Confirm the plan**: I'll show every change before I make it.
> 8. **Apply and verify**: I'll make the changes and check the result.
>
> Nothing changes until you approve the plan in step 7.

Then go to Step 1.

### Step 1: Read current state

Run these reads. Do not write anything.

1. `get-release-autopilot-settings`: the account gates.
2. `list-release-autopilot-repo-settings`: repos that are already mapped.
3. `list-release-autopilot-github-repos`: repos on the GitHub App install, or a `githubConnectUrl` if the App is not installed or the user has not authorized it.

Release Autopilot's agents need generative AI turned on for the organization. There is no MCP tool to read that setting. If a later step fails with a generative AI or Vega eligibility error, tell the user that an Admin or Owner must select **Enable generative AI use cases** in Organization settings > Security, then stop.

Summarize what is already set up in two or three sentences. If the account already has the capabilities on and repos mapped, ask:

- label: "Add more", description: "Keep the current setup and add capabilities, repos, or release plans"
- label: "Change one setting", description: "Hand off to the settings skill for a single change"
- label: "Diagnose a PR", description: "A PR was not classified or auto-flagged. Hand off to the settings skill"

For "Change one setting" or "Diagnose a PR", stop this skill and follow [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md).

### Step 2: Pick capabilities

Use `AskUserQuestion` with header "Capabilities", `multiSelect: true`:

- label: "Auto-flagging (Recommended)", description: "Release Autopilot reads each pull request and, when a change should ship behind a flag, opens a PR that adds the flag"
- label: "Auto-releasing", description: "After a flagged change deploys, Release Autopilot releases it with your environment release plans. This can ship code to users"

If the user picks auto-flagging, ask header "Approval":

- label: "Require approval (Recommended)", description: "A person approves each auto-flagging PR before Release Autopilot changes code"
- label: "No approval", description: "Release Autopilot changes PRs without an approval step"

Do not offer auto-cleanup. It is not part of the Release Autopilot settings API yet.

If the user picks neither capability, stop and tell them there is nothing to set up.

### Step 3: Connect GitHub

If Step 1 returned a `githubConnectUrl`, read its `flow`:

- `flow=install`: the LaunchDarkly GitHub App is not installed on their GitHub organization. Release Autopilot cannot see any pull request until it is.
- `flow=authorize`: the App is installed, but this member has not authorized GitHub, so repos cannot be listed.

Give the user the exact URL. Tell them to open it in a browser where they are logged in to LaunchDarkly. To install, they must be a GitHub organization owner, or they must request the install from one. Then ask header "GitHub":

- label: "Done", description: "I finished the GitHub step"
- label: "Need an org owner", description: "I can't install the App myself. Pause setup here"

On "Done", call `list-release-autopilot-github-repos` again. If it still returns `githubConnectUrl`, say so and repeat this step. On "Need an org owner", summarize the decisions so far and stop. The user can run this skill again after the App is installed.

If Step 1 returned repos and no `githubConnectUrl`, skip this step.

### Step 4: Map repositories

1. **Choose repos.** If the current workspace has a `git remote` on the install list, offer it first. Use `AskUserQuestion` with header "Repos", `multiSelect: true`, and up to four repos from the install list, as `owner/name`. If the install has more than four repos, say the user can type any other `owner/name` from the list in Other. Use only repos that came back from `list-release-autopilot-github-repos`. If a repo the user wants is not on the list, tell them to add it to the App's repository access in GitHub, then repeat Step 3's "Done" check.
2. **Choose a project for each repo.** Each repo maps to one LaunchDarkly project, which is where Release Autopilot creates flags and metrics for that repo. If `list-projects` is available, offer the projects as options. Otherwise ask for the project key.
3. **Skip repos that are already mapped** to the chosen project. Tell the user they are already set up.

### Step 5: Choose inference

Release Autopilot runs its agents on Vega. Each project has Vega inference settings. Use `AskUserQuestion` with header "Inference":

- label: "LaunchDarkly managed", description: "The agents run on a model that LaunchDarkly hosts. No setup"
- label: "Bring your own key", description: "The agents run on your own Anthropic or OpenAI account. Your provider bills you for usage"

For "LaunchDarkly managed", go to Step 6.

For "Bring your own key", there is no MCP tool for inference settings yet, so this is a browser step:

1. The key lives in the account's integration settings. Tell the user to add an Anthropic or OpenAI key there.
2. The project must then use it. For each project from Step 4, give the user `/projects/{projectKey}/settings/vega` on their LaunchDarkly instance (for example `https://app.launchdarkly.com`, or their EU or federal URL) and tell them to select their own key and save. LaunchDarkly checks the key with the provider when they save, and shows the cause if the check fails.

Then ask header "Inference":

- label: "Done", description: "I saved the inference settings for every project"
- label: "Use managed for now", description: "Skip this. I'll switch to my own key later"

You cannot read inference settings, so record the answer as the user's statement, not as verified.

### Step 6: Set up release plans (auto-releasing only)

Skip this step if the user did not pick auto-releasing.

Auto-releasing releases each change with a **release plan**: a reusable recipe for one environment, made of phases, rollout steps, and metrics. A plan with metrics makes the release guarded, so a regression on a metric can roll it back. Release plans replace project-level release policies.

For each project from Step 4:

1. **Choose environments.** Use `AskUserQuestion` with header "Environments", `multiSelect: true`, offering the project's environments (from `get-project`, or ask). Auto-releasing works in the environments that have a plan.
2. **Check existing plans.** For each chosen environment, call `list-release-plans`. If a complete plan exists, show its name, phases, and metrics, and ask header "Plan":
   - label: "Use this plan", description: "Keep the existing plan for this environment"
   - label: "Create another", description: "Add a new plan for this environment"
3. **Create a plan where needed.** Follow the `create-release-plan` tool guidance. Ask each setting as its own question, never bundled:
   1. Randomization unit: the context kind to roll out by, such as `user` or `account`.
   2. Rollout steps: offer header "Rollout" with options such as "1% → 10% → 50% → 100%, 4h holds", or "10% → 100%, 24h hold". The user can type another schedule in Other.
   3. Advancement: header "Advance", options "Automatic", description "Move to the next step when the hold ends and metrics are healthy", and "Manual", description "A person moves each step".
   4. Metrics: call `list-metrics`. Offer up to four relevant metrics with `multiSelect: true`. If none fit, follow [`launchdarkly-metric-choose`](../../metrics/launchdarkly-metric-choose/SKILL.md) and [`launchdarkly-metric-create`](../../metrics/launchdarkly-metric-create/SKILL.md) and come back. A plan without metrics is progressive, not guarded: say so.
   5. Cleanup: header "Cleanup", options "Leave rules in place" and "Remove rules and update the default rule", each with its outcome.

   Every phase needs at least one clause. For a phase that targets everyone, use `{ attribute: "kind", op: "in", values: ["<randomization unit>"], contextKind: "<randomization unit>" }`.

   Record the plan. Do not call `create-release-plan` yet.

`list-release-plans` hides incomplete plans that were migrated from release policies. If the user expects a plan that is missing, call it again with `includeIncomplete: true`. An incomplete plan cannot start a release, so it needs a new complete plan in that environment.

### Step 7: Confirm the plan

**STOP. Do not write anything until the user explicitly confirms.** A detailed request at the start is not approval.

List every write in the order you will make it. For each write, state the current and the proposed state and the blast radius, using the wording rules from the settings skill's [Confirm before write](../launchdarkly-release-autopilot-settings/SKILL.md#confirm-before-write):

1. **Release plans**: one line per environment, with the plan name, steps, advancement, and metrics.
2. **Repo mappings**: one line per repo, naming the project and **both** inherited capabilities.
3. **Account settings**: for example, "Auto-flagging: OFF → ON, approval required. Mapped repos that inherit this setting can start getting auto-flagging PRs." If auto-releasing turns on, say: "Auto-releasing: OFF → ON. This can ship code."
4. **Browser steps the user reported done**: GitHub and inference, marked as reported, not verified.

Then use `AskUserQuestion` with header "Confirm":

- label: "Looks good", description: "Make every change in this plan"
- label: "Change something", description: "Adjust the plan before you start"

On "Change something", make the change and show the full plan again. Do not go to Step 8 until the user selects "Looks good".

### Step 8: Apply

Make only the writes in the confirmed plan, in this order. Stop at the first failure, report it, and do not continue.

1. `create-release-plan` for each new plan.
2. `update-release-autopilot-repo-settings` for each repo, with `repo: "owner/name"` and `projectKey`.
3. `update-release-autopilot-settings` with only the confirmed fields. Never send `autoCleanup`.

The order matters. Release plans come first so that no release can start without the plan the user chose. The account gates come last because turning a capability on starts automation in every mapped repo that inherits it.

### Step 9: Verify

1. `get-release-autopilot-settings`: the account gates match the plan.
2. `get-release-autopilot-repo-settings` for each repo: mapped to the right project, effective auto-flagging and auto-releasing match the plan.
3. `list-release-plans` for each environment: the new plans are listed.

Report a short checklist with each item marked verified or reported by the user. Then tell the user how to see it work:

- Open a pull request in a mapped repo. Release Autopilot reads it within a few minutes. With approval required, the auto-flagging PR waits for approval.
- If a PR is not classified, use [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md#why-didnt-my-pr-get-classified) to diagnose it.

## Edge Cases

| Situation | Action |
|-----------|--------|
| Every Release Autopilot tool returns 404 | The account is not in the alpha. **STOP** and tell the user |
| `githubConnectUrl` with `flow=install` | Step 3. The user needs a GitHub org owner to install the App |
| Repo not on the install list | The App does not have access to that repo. The user adds it in GitHub, then you list again |
| Repo already mapped to a different project | Show the current mapping. Remapping changes where flags are created, so it needs its own line in Step 7 |
| Auto-releasing picked but no metrics exist | Offer the metric skills. Without metrics, the plan is progressive and nothing rolls back automatically |
| Incomplete migrated plan | Cannot start a release. Create a complete plan in that environment |
| User lacks permission for a write | Report the failed write and the missing permission. Do not retry with other settings |
| Bring your own key chosen | Browser step only. Record it as reported, never as verified |

## What NOT to Do

- Don't write before Step 7's "Looks good".
- Don't turn on auto-releasing unless the user picked it.
- Don't turn off approval for auto-flagging unless the user picked "No approval".
- Don't map repos the user did not pick, or iterate over the install list.
- Don't install or authorize GitHub, or set up a provider key, on the user's behalf.
- Don't send `autoCleanup`.
- Don't report a browser step as verified.

## References

- [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md): settings rules, write confirmations, and PR diagnosis
- [`launchdarkly-metric-choose`](../../metrics/launchdarkly-metric-choose/SKILL.md) / [`launchdarkly-metric-create`](../../metrics/launchdarkly-metric-create/SKILL.md): metrics for guarded release plans
- [Vega inference settings](https://launchdarkly.com/docs/home/getting-started/vega#vega-inference-settings)
- [Guarded rollouts](https://launchdarkly.com/docs/home/releases/guarded-rollouts)

## Example Flows

**Happy path: auto-flagging only, managed inference.**
Step 1 → nothing set up, install list has repos. Step 2 → auto-flagging, approval required. Step 3 → skipped. Step 4 → maps `acme/web` to project `web`. Step 5 → managed. Step 6 → skipped. Step 7 → two writes: map `acme/web` inheriting auto-flagging ON and auto-releasing OFF, then account auto-flagging ON with approval. Step 8 → applies. Step 9 → verified.

**Both capabilities, no GitHub App yet.**
Step 1 → `githubConnectUrl` with `flow=install`. Step 2 → both capabilities. Step 3 → user installs the App, selects "Done", repos appear. Step 4 → maps `acme/api` to `api`. Step 5 → bring your own key, user saves settings in the browser. Step 6 → `production` has no plan; creates `prod-guarded` with 1% → 10% → 50% → 100%, automatic advancement, metric `api-error-rate`. Step 7 → plan, mapping, and account writes, plus two reported browser steps. Steps 8–9 → applied and verified.

**Org owner needed: pause.**
Step 3 → `flow=install`, user selects "Need an org owner". Summarize decisions so far and stop. Nothing was written.
