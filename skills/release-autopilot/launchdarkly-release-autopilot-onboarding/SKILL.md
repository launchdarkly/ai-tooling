---
name: launchdarkly-release-autopilot-onboarding
description: "Step-by-step onboarding wizard for LaunchDarkly Release Autopilot: pick capabilities (auto-flagging, auto-releasing, auto-cleanup, auto-archival), connect the GitHub App, map repositories to projects, choose which AI model account runs the agents (LaunchDarkly's by default, or your own Anthropic or OpenAI key), review release policies (release plans by GA), and turn on scheduled flag cleanup and archival. Use when the user wants to set up, onboard to, preview, or continue setting up Release Autopilot. For a single settings change or 'why didn't my PR get classified?', use launchdarkly-release-autopilot-settings instead."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "0.2.0-experimental"
---

# LaunchDarkly Release Autopilot Onboarding

You're using a skill that walks a user through setting up Release Autopilot. The user picks the capabilities they want, and you set up only what those capabilities need: the GitHub App, repository mappings, Vega inference, and the environment release setup for auto-releasing.

**This is a step-by-step wizard.** Ask one question at a time and wait for each answer. Gather every decision first, confirm one plan, and only then write. Release Autopilot opens and changes pull requests, and auto-releasing can ship code, so every write is production automation.

Follow the write rules of [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md) (least privilege, `owner/name` only, never `autoCleanup`, current → proposed with blast radius). Its one-at-a-time confirmations are replaced by the single itemized confirmation at [Step 7](#step-7-confirm-the-plan).

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server.

**Required MCP tools:**
- `get-release-autopilot-settings` / `update-release-autopilot-settings`
- `list-release-autopilot-github-repos`
- `list-release-autopilot-repo-settings` / `get-release-autopilot-repo-settings` / `update-release-autopilot-repo-settings`
- `get-member-self`

**Required for auto-releasing:**
- `list-release-policies`

**Used when available:**
- `list-release-plans` / `create-release-plan` / `list-metrics`: environment release plans (see [Release setup](#release-setup))
- `list-projects` / `get-project`: offer project and environment keys as options instead of asking for free text

If a required tool is missing, stop and tell the user which one. Do not invent REST calls. If any tool response includes `latestMcp.deprecated: true`, the user is connected to an older MCP server that may not have these tools: give them `latestMcp.installUrl` and stop.

If every Release Autopilot tool returns 404, the account does not have the Release Autopilot add-on enabled. Tell the user "Your account does not have the Release Autopilot add-on enabled," and stop.

## Modes

Pick the mode from the user's request before Step 0:

| Mode | Trigger | What changes |
|------|---------|--------------|
| **Setup** | "set up", "onboard", "turn on" | The full flow |
| **Preview** | "preview", "what would you change", "dry run", or a reader (see Step 1) | Run Steps 1–7 and end with the plan as a checklist for an admin. Make no writes |
| **Resume** | "continue", "pick up where we left off", or a return after a browser step | Skip the intro, re-read live state, and continue at the first unfinished step. Still stops at Step 7 and waits for "Looks good". Details: [references/modes.md](references/modes.md) |

Every mode is safe to run again. A re-run reads live state and proposes only the writes that are still needed.

## Core Principles

1. **Only set up what they picked.** Release setup matters only for auto-releasing. If the user picks auto-flagging only, skip Step 6.
2. **Least privilege by default.** Recommend auto-flagging, which always waits for a person to approve its proposed change. Auto-releasing is opt-in and you must say it can ship code.
3. **Gather, confirm, then write.** No write happens before [Step 7](#step-7-confirm-the-plan). The confirmation lists every write with its current and proposed state. This holds in every mode, including Resume and requests that already state every answer: a restated pick is an answer, never approval. Step 1's reads, including the role check, always run first.
4. **Don't ask what the account already answers.** If live state already settles a question, state the answer and move on.
5. **Never act in the user's browser.** GitHub install, GitHub authorization, release policy edits, and bring-your-own-key setup are browser steps. Give the exact link and wait for the user to say they finished.
6. **Only touch what the user named.** Never map every repo on the install. Never create release plans in environments the user did not pick.

## Speaking to the user

- Use product words ("auto-flagging", "release policy", "approval") in every message, including questions, checklists, and the final summary. Never show tool names, field names (`githubRepoId`, `autoReleasing.enabled`), HTTP status codes, step numbers, or this skill's mode names ("preview mode", "policy mode", "plan mode"); say "Here's what would change", "your account uses release policies", and "Verification", not "Step 9".
- Say "Release Autopilot" only in the welcome. After that, name the capability ("auto-flagging", "auto-releasing", "auto-cleanup", "auto-archival"), or say "these capabilities". The exceptions are the resume phrase "continue Release Autopilot setup", the name of the settings skill, and "the Release Autopilot add-on".
- Name repos as `owner/name`. Show a repository ID only for a mapped repo with no name.
- Describe each change in words ("Turn on auto-flagging for the account"), never as a tool call or a field and value, not even in parentheses for an admin. If a check after a write disagrees with it, name the change that could not be confirmed and where to check it in the LaunchDarkly UI.
- Every browser step (GitHub, bring your own key, Lifecycle or release settings) must be done while signed in as the member from Step 1. Say so when you give the link.
- State only what the reads show. Do not guess at causes (such as "installs can take a few minutes to propagate"), and do not invent UI locations: give only the pages this skill names. For an account change left for an admin, tell them to run [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md).
- Keep each message to the current step, and do not narrate tool calls.

## Workflow

When a step is complete, go to the next one unless it says to ask or wait. Treat user messages as answers to the current question, and track every decision for Step 7.

**Asking questions:** When a question has options, use `AskUserQuestion` with the labels and descriptions given below. Ask free-text questions as a normal message. If the user's request already answers a question explicitly, such as naming the repo, the project, or the capabilities, use that answer and say so instead of asking. Never infer the answer to the Step 7 confirmation.

**Links:** the question dialog covers the message above it. When a question follows a link the user must open (GitHub, bring your own key, lifecycle or release settings), put the exact URL in the question text itself, not only in the message before it.

### Step 0: Welcome the user

If the user's request is a diagnosis ("why didn't my PR get classified?", "why wasn't it auto-flagged?"), do not start this wizard, whatever the account state: follow the diagnosis in [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md#why-didnt-my-pr-get-classified). It is read-only; if it finds that nothing is set up, offer this wizard afterward.

Decide the mode from the user's first message before you write anything. Never announce the mode by name; for a preview request, say "I'll show what would change and make no changes." **In Resume mode, skip this step entirely**: do not show the intro or any part of it, and go straight to Step 1. In Setup mode, present this intro (you may lightly adapt the wording, but keep the structure). In Preview mode, replace the last line with "I'll show you every change and make none of them."

> **Release Autopilot Setup**
>
> I'll set up Release Autopilot in a few short steps: check your account, pick capabilities, connect GitHub, map repositories, choose whose AI model account runs the agents, then set up releases, flag cleanup, and archival for the capabilities you pick.
>
> Nothing changes until you approve the full plan.

Then go to Step 1. Skip any step that the account state already completes, and say why in one line.

### Step 1: Read current state

Run these reads. Do not write anything.

1. `get-member-self`: the member's `role`, and their `email`. Keep the email: every browser step must happen while signed in to LaunchDarkly as that member (see [Step 3](#step-3-connect-github)).
   - `reader` or `no_access`: switch to Preview. Tell the user: "You have read-only access, so I'll show what would change and make no changes."
   - `admin` or `owner`: can make every write in this flow.
   - Any other role, including `writer` and custom roles: may map repos in projects they can edit, but account settings need an admin or owner. In Step 7, mark account writes as "needs an admin" and leave them out of Step 8.
2. `get-release-autopilot-settings`: the account gates.
3. `list-release-autopilot-repo-settings`: repos that are already mapped.
4. `list-release-autopilot-github-repos`: repos on the GitHub App install (`owner/name` and `githubRepoId`), plus `installed` and `userAuthorized`. If either is false, the response includes a `githubConnectUrl`.

Join mapped repos to the install list by repository ID to get their names. For a mapped ID that is not on the install, tell the user, for example, "One more repository (ID 999) is mapped to project default but is no longer on the GitHub install; I'll leave it alone." Do not write the field name or change that repo. If a later step fails with a generative AI eligibility error, see [references/edge-cases.md](references/edge-cases.md).

Summarize what is already set up in two or three sentences. If the account already has a capability on or any repo mapped, ask:

- label: "Add more", description: "Keep the current setup and add capabilities, repos, or release setup"
- label: "Change one setting", description: "Hand off to the settings skill for a single change"
- label: "Diagnose a PR", description: "A PR was not classified or auto-flagged. Hand off to the settings skill"

In Preview mode, leave out "Change one setting", because that hand-off writes. For "Change one setting" or "Diagnose a PR", stop this skill and follow [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md).

### Step 2: Pick capabilities

Use `AskUserQuestion` with header "Capabilities", `multiSelect: true`:

- label: "Auto-flagging (Recommended)", description: "Reads each pull request and, when a change should ship behind a flag, opens a PR that adds the flag"
- label: "Auto-releasing", description: "After a flagged change deploys, releases it with the environment's release policy or release plan. This can ship code to users"
- label: "Auto-cleanup", description: "On a schedule, opens pull requests that remove the code for flags that are ready for removal. This removes code"
- label: "Auto-archival", description: "Archives flags that are ready to archive, after safety checks and a grace period"

Do not ask about approval. Auto-flagging always waits for a person: it posts its proposed change on the pull request, and nothing changes until someone replies `@launchdarkly approve` (or `approve flag`) or presses Approve on the check. If the user picked auto-flagging, say that in one sentence. Never send `approvalRequired`; the backend does not read it today, so turning it off would not skip that step.

Auto-cleanup and auto-archival are opt-in like auto-releasing: never recommend them by default. If the user picks no capability, stop and tell them there is nothing to set up.

### Step 3: Connect GitHub

Skip this step without mentioning GitHub if Step 1 returned `installed: true`, `userAuthorized: true`, and no `githubConnectUrl`.

Otherwise read the URL's `flow`:

- `flow=install`: the LaunchDarkly GitHub App is not installed on their GitHub organization. None of these capabilities can see a pull request until it is.
- `flow=authorize`: the App is installed, but this member has not authorized GitHub, so repos cannot be listed.

Give the user the exact URL. The link acts on whatever LaunchDarkly session the browser has, so tell them to open it while signed in as the member from Step 1 (for example, "Open it while signed in to LaunchDarkly as admin@acme.example"). Then ask header "GitHub", with the URL in the question text. The options depend on the flow:

- `flow=install`: to install, they must be a GitHub organization owner, or request the install from one. Question: "Open https://… to install the LaunchDarkly GitHub App. Done?"
  - label: "Done", description: "I installed the App"
  - label: "Need an org owner", description: "I can't install the App myself. Pause setup here"
- `flow=authorize`: the App is already installed, so no org owner is needed. They authorize with a GitHub account that is a member of the organization where the App is installed. Question: "Open https://… and authorize with a GitHub account in the organization that installed the App. Done?"
  - label: "Done", description: "I authorized GitHub"
  - label: "I can't authorize", description: "My GitHub account can't see that organization's install"

On "Done", call `list-release-autopilot-github-repos` again. If it still returns `githubConnectUrl`, do not repeat the link. The most common cause is a browser signed in to a different LaunchDarkly account or member, so the App was installed there. Ask header "Browser account", with this connection's email in the question text (for example, "This connection is signed in as admin@acme.example. Which account is your browser signed in to?"):

- label: "The same", description: "My browser is signed in as that member"
- label: "A different one", description: "My browser is signed in to another account or member"
- label: "Not sure", description: "I need to check"

For "A different one" or "Not sure", tell them to check at `/profile`, sign in as the member from Step 1, open the link again, and finish there; then list again. For "The same", check the other causes in [references/github-troubleshooting.md](references/github-troubleshooting.md). On "Need an org owner", summarize the decisions so far, repeat the exact URL for the org owner, tell the user to say "continue Release Autopilot setup" after the App is installed, and stop. On "I can't authorize", pause the same way: summarize the decisions so far, tell them to sign in to GitHub with an account that is a member of that organization (or ask an org owner to add theirs), repeat the exact URL, tell them to say "continue Release Autopilot setup" once they have authorized, and stop. See the GitHub-identity cause in [references/github-troubleshooting.md](references/github-troubleshooting.md).

Never go on to Step 4 while `list-release-autopilot-github-repos` still returns `githubConnectUrl`: an empty repo list then means GitHub is not connected, not that the repo's organization lacks the App.

### Step 4: Map repositories

1. **Choose repos.** If the current workspace has a `git remote` on the install list, offer it first. Use `AskUserQuestion` with header "Repos", `multiSelect: true`, and up to four repos from the install list, as `owner/name`. If the install has more than four repos, say the user can type any other `owner/name` from the list in Other. Use only repos that came back from `list-release-autopilot-github-repos`.

   If a repo the user wants is not on the list, its owner decides the fix: a listed owner means the App needs access to that repo, and a new owner means an org owner must install the App there (no `githubConnectUrl` appears for this case). See [references/edge-cases.md](references/edge-cases.md). Wait for "Done" and list again.
2. **Choose a project for each repo.** Each repo maps to one LaunchDarkly project, which is where auto-flagging creates flags and metrics for that repo. If `list-projects` is available, offer the projects as options. Otherwise ask for the project key.
3. **Check existing mappings** with the join from Step 1 (an unmapped repo returns 404, which is expected). Already mapped to the chosen project with matching capabilities: write nothing. Mapped to the chosen project with an unpicked capability on: record an override that turns it off. Mapped to a different project: never remap here; send the user to the settings skill to unmap first. Details: [references/edge-cases.md](references/edge-cases.md#existing-mappings).
4. **Say what starts when.** If the account already has a capability on, mapping a repo starts that automation in the repo as soon as Step 8 maps it.

### Step 5: Choose the AI model account

The agents behind these capabilities (Vega) use an AI model to read pull requests and write code changes. This step decides whose model account they use; the product calls it "inference". Most users keep the default. Before asking, tell the user in one sentence what the choice means, for example: "The agents behind auto-flagging use an AI model to read your pull requests. By default they run on LaunchDarkly's model account; you can use your own Anthropic or OpenAI key instead." Then use `AskUserQuestion` with header "AI model":

- label: "LaunchDarkly's (default)", description: "The agents use an AI model that LaunchDarkly provides and pays for. No setup"
- label: "Bring your own key", description: "The agents use your own Anthropic or OpenAI API key, for example to keep usage on your provider contract. Your provider bills you for usage"

For "Bring your own key", this is a browser step (no MCP tool reads or writes these settings). For each project, follow [references/byok.md](references/byok.md), then ask header "AI model":

- label: "Done", description: "I saved my key in the Vega settings for every project"
- label: "Use LaunchDarkly's for now", description: "Skip this. I'll switch to my own key later"

Record the answer as reported by the user, not as verified.

### Step 6: Set up releases and cleanup

Run each part of this step only for a capability the user picked in Step 2, and skip the step if they picked none of them. Never walk the user through a capability they did not pick:

- Auto-releasing picked: [Release setup](#release-setup).
- Auto-cleanup picked: [Auto-cleanup](#auto-cleanup).
- Auto-archival picked: [Auto-archival](#auto-archival).

#### Release setup

Only if the user picked auto-releasing. Otherwise skip to [Auto-cleanup](#auto-cleanup) or [Auto-archival](#auto-archival), and do not ask about environments or look up release plans or policies.

For each project from Step 4, choose environments: use `AskUserQuestion` with header "Environments", `multiSelect: true`, offering the project's environments (from `get-project`, or ask). Then check once per account whether it uses release plans or release policies.

##### Check whether the account uses release plans

Call `list-release-plans` for the first chosen environment.

- **Release policies** if the call returns 403 `Plan does not allow this operation`, or if `list-release-plans` is not available. The 403 is account-wide, so do not call it for other environments. This is the mode for every account today: auto-releasing requires a complete release policy for each environment.
- **Release plans** if the call succeeds. Environment release plans replace release policies by general availability.

##### Release policies (today)

Call `list-release-policies` for the project and show the user what it returns, including any `warnings`. Record no plan writes. This skill does not change policies.

- No warnings for the chosen environments: say that auto-releasing in this project uses those policies.
- Any warning, such as `missing_policy` or `incomplete_policy`: auto-releasing cannot work there yet. Tell the user to add or complete a release policy in the project's release settings (`/projects/{projectKey}/settings/releases` on their LaunchDarkly instance). Record a repo override that keeps auto-releasing off for each repo in that project, and say in Step 7 that they can turn it on with the settings skill once the policy is complete.

##### Release plans (by GA)

For each chosen environment, call `list-release-plans`. If a complete plan exists, show its name, phases, and metrics, and ask header "Plan":

- label: "Use this plan", description: "Keep the existing plan for this environment"
- label: "Create another", description: "Add a new plan for this environment"

To create a plan, follow [references/release-plans.md](references/release-plans.md). Record the plan and any metrics to create. Do not call `create-release-plan` or create metrics yet.

#### Auto-cleanup

Only if the user picked auto-cleanup.


Auto-cleanup is the per-project **Automated flag cleanup** setting, on the Lifecycle settings page (or the Vega settings page, for accounts where Vega has its own project settings). The MCP settings tools do not manage it yet, so never send `autoCleanup`; this is a browser step. If a later version of `get-release-autopilot-settings` returns `autoCleanup` and the update tool accepts it, set it there instead. For each project from Step 4, the link is exactly `/projects/{projectKey}/settings/lifecycle` on their LaunchDarkly instance (or `/projects/{projectKey}/settings/vega` if that page has no "Automated flag cleanup" section). Follow [references/auto-cleanup.md](references/auto-cleanup.md), then ask header "Auto-cleanup", with the link in the question text:

- label: "Done", description: "I turned on automated flag cleanup for every project"
- label: "Later", description: "Skip this. I'll turn it on from Lifecycle settings later"

Record the answer as reported by the user, and list "Done" under browser steps in Step 7.

#### Auto-archival

Only if the user picked auto-archival.


Auto-archival is the per-project **Automatic archival** setting on the Lifecycle settings page. No MCP tool manages it, so this is a browser step. For each project from Step 4, the link is exactly `/projects/{projectKey}/settings/lifecycle` on their LaunchDarkly instance. Follow [references/auto-archival.md](references/auto-archival.md), then ask header "Auto-archival", with the link in the question text:

- label: "Done", description: "I turned on automatic archival for every project"
- label: "Later", description: "Skip this, or the section isn't there yet. I'll turn it on from Lifecycle settings later"

Record the answer as reported by the user, and list "Done" under browser steps in Step 7.

### Step 7: Confirm the plan

**STOP. Do not write anything until the user explicitly confirms.** A detailed request at the start is not approval.

List every write in the order you will make it. For each write, state the current and the proposed state and the blast radius, using the wording rules from the settings skill's [Confirm before write](../launchdarkly-release-autopilot-settings/SKILL.md#confirm-before-write):

1. **Metrics and release plans** (release plans only): one line per metric to create and per environment, with the plan name, steps, advancement, and metrics.
2. **Repo mappings and overrides**: one line per repo, naming the project and the **effective** auto-flagging and auto-releasing state after every write in this plan. For a capability the user did not pick, or that cannot work yet, the mapping sends a repo override that turns it off. Say so: "Auto-releasing: off for this repository (the account has it on; this project has no release policy yet)."
3. **Account settings**: only fields that change. If auto-releasing turns on, say it can ship code.
   For a member who is not an admin or owner, list account writes under "Needs an admin" instead, and say an admin can make them with the settings skill. Do not name a settings page; there is none to point to.
4. **Browser steps the user reported done**: GitHub, the AI model choice, auto-cleanup, and auto-archival, marked as reported, not verified.
5. **Follow-ups for the user**: release policies to add, metric events to instrument.

If there are no writes, say so, list the follow-ups, and stop.

**Preview mode:** the final message contains only the heading "Changes an admin would make", the checklist (one line per change), and any follow-ups. Do not repeat the account state, and do not ask for confirmation. For example:

```
- [ ] Map acme/demo to project default, with auto-releasing off for this repository
- [ ] Turn on auto-flagging for the account
```

**Setup mode:** use `AskUserQuestion` with header "Confirm":

- label: "Looks good", description: "Make every change in this plan"
- label: "Change something", description: "Adjust the plan before you start"

Only "Looks good" approves the plan. On "Change something", ask what to change, make the change, and show the full plan again. Any other answer, including one that does not match an option, is not approval: ask the confirmation again. Do not go to Step 8 until the user selects "Looks good".

### Step 8: Apply

Make only the writes in the confirmed plan, in this order. Stop at the first failure, report it, and do not continue.

1. Release plans only: metrics recorded in Step 6, created in LaunchDarkly with [`launchdarkly-metric-create`](../../metrics/launchdarkly-metric-create/SKILL.md). Skip its instrumentation steps.
2. Release plans only: `create-release-plan` for each new plan.
3. `update-release-autopilot-repo-settings` for each repo, with `repo: "owner/name"` and `projectKey`. For each capability the user did not pick, or that cannot work yet, send `{ "enabled": false }` for it, so the repo does not inherit it from the account.
4. `update-release-autopilot-settings` with only the confirmed fields. Never send `autoCleanup`.

The order matters. When the plan creates release plans, they come first, so that no release can start without the plan the user chose. The account gates come last because turning a capability on starts automation in every mapped repo that inherits it.

If a write fails with 403, the member lacks that permission. Report which write failed, list the remaining writes as a checklist for an admin, and stop.

### Step 9: Verify

1. `get-release-autopilot-settings`: the account gates match the plan.
2. `get-release-autopilot-repo-settings` for each repo: mapped to the right project, effective auto-flagging and auto-releasing match the plan.
3. With release plans: `list-release-plans` for each environment lists the new plans. With release policies: report the policy state from Step 6.

If any change was left for an admin or failed, lead with "Partly set up: waiting on an admin" and the admin checklist, and never call the setup complete. Then report a short checklist with each item marked verified, reported by the user (browser steps the user did in this flow), or already set up (steps the flow skipped because they were already done), then the follow-ups. Tell the user how to see it work; if a change is waiting on an admin, make that conditional ("Once an admin turns on auto-flagging, open a pull request…"):

- Open a pull request in a mapped repo. Auto-flagging reads it within a few minutes and posts its proposed change on the PR; nothing changes until someone replies `@launchdarkly approve` or presses Approve on the check.
- If a PR is not classified, use [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md#why-didnt-my-pr-get-classified) to diagnose it.

## Edge Cases

| Situation | Action |
|-----------|--------|
| Every settings tool returns 404 | The account does not have the Release Autopilot add-on enabled. Tell the user and stop |
| Member role is `reader` or `no_access` | Preview mode. End with a checklist for an admin |
| Release plans return 403 | Use release policies. Create no plans |
| Repo not on the install list | Explain the GitHub fix by owner, then list again |
| GitHub still not connected after "Done" | Likely a different browser account. Follow [references/github-troubleshooting.md](references/github-troubleshooting.md) |

More cases: [references/edge-cases.md](references/edge-cases.md).

## What NOT to Do

- Don't write before Step 7's "Looks good", or at all in Preview mode.
- Don't turn on auto-releasing unless the user picked it, and never send `approvalRequired`.
- Don't map unpicked repos, iterate over the install list, or remap a repo to another project.
- Don't act in the user's browser, change release policies, or report a browser step as verified.

## References

- [references/release-plans.md](references/release-plans.md): creating environment release plans
- [references/modes.md](references/modes.md): Preview and Resume details
- [references/byok.md](references/byok.md): bring-your-own-key setup
- [references/auto-cleanup.md](references/auto-cleanup.md) / [references/auto-archival.md](references/auto-archival.md): turning on flag cleanup and archival
- [references/github-troubleshooting.md](references/github-troubleshooting.md): GitHub still not connected after the user finished
- [references/edge-cases.md](references/edge-cases.md): edge cases and existing mappings
- [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md): settings rules, write confirmations, and PR diagnosis
- [Vega inference settings](https://launchdarkly.com/docs/home/getting-started/vega#vega-inference-settings)
- [Guarded rollouts](https://launchdarkly.com/docs/home/releases/guarded-rollouts)
