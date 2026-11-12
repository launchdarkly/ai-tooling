---
name: launchdarkly-release-autopilot-onboarding
description: "Step-by-step onboarding wizard for LaunchDarkly Release Autopilot: pick capabilities (auto-flagging, auto-releasing, auto-cleanup, auto-archival), connect the GitHub App, map repositories to projects, choose which AI model account runs the agents (LaunchDarkly's by default, or your own Anthropic or OpenAI key), set up environment release plans (with starter plans), and turn on scheduled flag cleanup and archival. Use when the user wants to set up, onboard to, preview, or continue setting up Release Autopilot. For a single settings change or 'why didn't my PR get classified?', use launchdarkly-release-autopilot-settings instead."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.0.0"
---

# LaunchDarkly Release Autopilot Onboarding

You're using a skill that walks a user through setting up Release Autopilot. The user picks the capabilities they want, and you set up only what those capabilities need: the GitHub App, repository mappings, Vega inference, and the environment release setup for auto-releasing.

**This is a step-by-step wizard.** Ask one question at a time and wait for each answer. Gather every decision first, confirm one plan, and only then write. Release Autopilot opens and changes pull requests, and auto-releasing can ship code, so every write is production automation.

Follow the write rules of [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md) (least privilege, `owner/name` only, never `autoCleanup`, current → proposed with blast radius). Its one-at-a-time confirmations are replaced by the single itemized confirmation at [Step 7](#step-7-confirm-the-plan).

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server. Installing the LaunchDarkly plugin is the first step: it adds this skill and the MCP server. In Claude Code, run `/plugin marketplace add launchdarkly/ai-tooling`, then `/plugin install launchdarkly@launchdarkly-ai-tooling`. In Cursor, install **LaunchDarkly** from **Settings > Plugins**. Then sign in to the `launchdarkly` server when the client asks.

**Required MCP tools:**
- `get-automations` / `update-automations`: `get-automations` returns the account settings and the repos on the GitHub App install with their mappings; `update-automations` takes `accountWide: true` for account settings or `accountWide: false` with `repo` for one repository
- `get-member-self`

On a server that has not picked up the Automations rename yet, the same tools are named `get-release-autopilot`, `update-release-autopilot`, and `delete-release-autopilot-repo-settings`; use those names with the same arguments. If a call fails with "this tool has been removed from the server", ask the user to reconnect the LaunchDarkly MCP server so it loads the new tool names, then retry.

**Required for auto-releasing:**
- `get-environment-release-plans` / `create-environment-release-plan` / `update-default-environment-release-plan`: environment release plans (see [Release setup](#release-setup)). When `get-environment-release-plans` is not available, stop release setup as [Release setup](#release-setup) says, and continue with the rest

**Used when available:**
- `get-metrics`: rollback metrics for guarded release plans
- `search-contexts`: checks the randomization unit before offering a starter plan
- `get-projects` (with `projectKey` for one project and its environments): offer project and environment keys as options instead of asking for free text

If a required tool is missing, stop and tell the user which one. If no LaunchDarkly tool is available, tell the user to install or update the LaunchDarkly plugin as described above, sign in, and say "continue Release Autopilot setup". Do not invent REST calls. If any tool response includes `latestMcp.deprecated: true`, the user is connected to an older MCP server that may not have these tools: give them `latestMcp.installUrl` and stop.

If every Release Autopilot tool returns 404, the account does not have the Release Autopilot add-on enabled. Tell the user "Your account does not have the Release Autopilot add-on enabled," and stop.

## Modes

Pick the mode from the user's request before Step 0:

| Mode | Trigger | What changes |
|------|---------|--------------|
| **Setup** | "set up", "onboard", "turn on" | The full flow |
| **Preview** | "preview", "what would you change", "dry run", or a reader (see Step 1) | Run Steps 1–7 and end with the plan as a checklist for an admin. Make no writes, and never ask the user to change anything in the browser; list those steps instead |
| **Resume** | "continue", "pick up where we left off", or a return after a browser step | Skip the intro, re-read live state, and continue at the first unfinished step. Still stops at Step 7 and waits for "Looks good". Details: [references/modes.md](references/modes.md) |

Every mode is safe to run again. A re-run reads live state and proposes only the writes that are still needed.

## Core Principles

1. **Only set up what they picked.** GitHub is needed only for auto-flagging, auto-releasing, and auto-cleanup; repo mapping only for auto-flagging and auto-releasing; release setup only for auto-releasing. Skip every step the picks do not need.
2. **Least privilege by default.** Recommend auto-flagging, which always waits for a person to approve its proposed change. Auto-releasing is opt-in and you must say it can ship code.
3. **Gather, confirm, then write.** No write happens before [Step 7](#step-7-confirm-the-plan). The confirmation lists every write with its current and proposed state. This holds in every mode, including Resume and requests that already state every answer: a restated pick is an answer, never approval. Step 1's reads, including the role check, always run first.
4. **Don't ask what the account already answers.** If live state already settles a question, state the answer and move on.
5. **Never act in the user's browser, and defer browser changes.** GitHub install and authorization come early, because repo mapping needs them. Bring your own key and turning on auto-archival change settings in the browser, so they happen only after "Looks good", in [Step 8](#step-8-apply). Give the exact link and wait for the user to say they finished. Auto-cleanup is set through the MCP, in Step 8 as well.
6. **Only touch what the user named.** Never map every repo on the install. Never create release plans in environments the user did not pick.
7. **Each repo's own settings decide what runs in it.** On accounts that use the project Automations settings page, only the repo's settings count: a capability that the repo does not turn on is off. Other accounts still use the account settings too, until a migration moves them. There, a capability runs in a repo only when the account has it on and the repo does not turn it off. So each repo write turns on every picked capability, and the account write still turns on a picked capability that the account has off. The effective values that `get-automations` returns for a repo follow the rule that its account uses.

## Speaking to the user

- Use product words ("auto-flagging", "release plan", "approval") in every message, including questions, checklists, and the final summary. Never show tool names, field names (`githubRepoId`, `autoReleasing.enabled`), HTTP status codes, step numbers, or this skill's mode names ("preview mode", "plan mode"); say "Here's what would change", "your account uses release plans", and "Verification", not "Step 9".
- Say "Release Autopilot" only in the welcome. After that, name the capability ("auto-flagging", "auto-releasing", "auto-cleanup", "auto-archival"), or say "these capabilities". The exceptions are the resume phrase "continue Release Autopilot setup", the name of the settings skill, and "the Release Autopilot add-on".
- Name repos as `owner/name`. Show a repository ID only for a mapped repo with no name.
- Describe each change in words ("Turn on auto-flagging for acme/demo"), never as a tool call or a field and value, not even in parentheses for an admin. If a check after a write disagrees with it, name the change that could not be confirmed and where to check it in the LaunchDarkly UI.
- Every browser step (GitHub, bring your own key, turning on auto-archival, release settings) must be done while signed in as the member from Step 1. Say so when you give the link.
- State only what the reads show. Do not guess at causes (such as "installs can take a few minutes to propagate"), and do not invent UI locations: give only the pages this skill names. For an account change left for an admin, tell them to run [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md).
- Keep each message to the current step, and do not narrate tool calls.

## Workflow

When a step is complete, go to the next one unless it says to ask or wait. Treat user messages as answers to the current question, and track every decision for Step 7.

**Asking questions:** When a question has options, use `AskUserQuestion` with the labels and descriptions given below. Ask free-text questions as a normal message. If the user's request already answers a question explicitly, such as naming the repo, the project, or the capabilities, use that answer and say so instead of asking. Never infer the answer to the Step 7 confirmation.

**Links:** the question dialog covers the message above it. When a question follows a link the user must open (GitHub, bring your own key, Automations or release settings), put the exact URL in the question text itself, not only in the message before it.

### Step 0: Welcome the user

If the user's request is a diagnosis ("why didn't my PR get classified?", "why wasn't it auto-flagged?"), do not start this wizard, whatever the account state: follow the diagnosis in [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md#why-didnt-my-pr-get-classified). It is read-only; if it finds that nothing is set up, offer this wizard afterward.

Decide the mode from the user's first message before you write anything. Never announce the mode by name; for a preview request, say "I'll show what would change and make no changes." **In Resume mode, skip this step entirely**: do not show the intro or any part of it, and go straight to Step 1. In Setup mode, present this intro (you may lightly adapt the wording, but keep the structure). In Preview mode, replace the last line with "I'll show you every change and make none of them."

> **Release Autopilot Setup**
>
> I'll set up Release Autopilot in a few short steps: check your account, pick capabilities, connect GitHub and map repositories if your picks need them, choose whose AI model account runs the agents, then set up releases, flag cleanup, and archival for the capabilities you pick.
>
> Nothing changes until you approve the full plan.

Then go to Step 1. Skip any step that the account state already completes, and say why in one line.

### Step 1: Read current state

Run these reads. Do not write anything.

1. `get-member-self`: the member's `role`, and their `email`. Keep the email: every browser step must happen while signed in to LaunchDarkly as that member (see [Step 3](#step-3-connect-github)).
   - `reader` or `no_access`: switch to Preview. Tell the user: "You have read-only access, so I'll show what would change and make no changes."
   - `admin` or `owner`: can make every write in this flow.
   - Any other role, including `writer` and custom roles: may map repos in projects they can edit, but account settings need an admin or owner. In Step 7, mark account writes as "needs an admin" and leave them out of Step 8.
2. `get-automations`: `account` holds the account settings, and `repos` lists the repos on the GitHub App install (`repo` as `owner/name`, `githubRepoId`, `mapped`, and for mapped repos `projectKey` and the effective capabilities). When GitHub is not connected, the response includes a `githubConnectUrl`. Page through `repos` with `nextOffset` as `offset` while `hasMore` is true.

The server already joins mapped repos to the install list. For a repo with `visibleOnInstall: false` (mapped, but no longer on the install), tell the user, for example, "One more repository (ID 999) is mapped to project default but is no longer on the GitHub install; I'll leave it alone." Do not write the field name or change that repo. If a later step fails with a generative AI eligibility error, see [references/edge-cases.md](references/edge-cases.md).

Summarize what is already set up in two or three sentences. If the account already has a capability on or any repo mapped, ask:

- label: "Add more", description: "Keep the current setup and add capabilities, repos, or release setup"
- label: "Change one setting", description: "Hand off to the settings skill for a single change"
- label: "Diagnose a PR", description: "A PR was not classified or auto-flagged. Hand off to the settings skill"

In Preview mode, leave out "Change one setting", because that hand-off writes. For "Change one setting" or "Diagnose a PR", stop this skill and follow [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md).

### Step 2: Pick capabilities

Use `AskUserQuestion` with header "Capabilities", `multiSelect: true`:

- label: "Auto-flagging (Recommended)", description: "Reads each pull request and, when a change should ship behind a flag, opens a PR that adds the flag"
- label: "Auto-releasing", description: "After a flagged change deploys, releases it with the environment's release plan. This can ship code to users"
- label: "Auto-cleanup", description: "On a schedule, opens pull requests that remove the code for flags that are ready for removal. This removes code"
- label: "Auto-archival", description: "Archives flags that are ready to archive, after safety checks and a grace period"

Do not ask about approval. Auto-flagging always waits for a person: it posts its proposed change on the pull request, and nothing changes until someone replies `@launchdarkly approve` (or `approve flag`) or presses Approve on the check. If the user picked auto-flagging, say that in one sentence. Never send `approvalRequired`; the backend does not read it today, so turning it off would not skip that step.

Auto-cleanup and auto-archival are opt-in like auto-releasing: never recommend them by default. If the user picks no capability, stop and tell them there is nothing to set up.

### Step 3: Connect GitHub

Only if the user picked auto-flagging, auto-releasing, or auto-cleanup. Auto-archival alone does not need GitHub: skip Steps 3 and 4 and choose projects directly (see [Step 4](#step-4-map-repositories)).

Skip this step without mentioning GitHub if Step 1 returned no `githubConnectUrl` and no `reposError`.

A `reposError` means the install could not be read right now, not that GitHub is disconnected. Call `get-automations` once more. If it still returns `reposError`, the repos cannot be listed, so repo mapping and everything after it must wait. Say that the GitHub App install could not be read, summarize the decisions so far, tell the user to say "continue Release Autopilot setup" later, and stop. In Preview mode, do not stop: list only "Map the repos once the GitHub App install can be read" in the checklist, with no connect link and no "Connect GitHub" item, skip Step 4, and continue with the steps that do not need the repo list. The Preview paragraph below does not apply.

**Preview mode, with `githubConnectUrl`:** do not ask the user to install or authorize. List "Connect GitHub" in the Step 7 checklist with the link. Repo mapping cannot be planned until GitHub is connected, so skip Step 4 and any release setup that depends on it. If the user picked auto-flagging or auto-releasing, list "After GitHub is connected: map the repos" in the checklist; for auto-cleanup alone, ask which projects instead (as Step 4 says) and list its cleanup settings for each, noting that they need GitHub connected and are saved after "Looks good", not in the browser. If the user picked auto-releasing, also list "After mapping: choose environments and set up the release plans for project {projectKey}", because auto-releasing needs that before it can work. Continue with the steps that do not need GitHub.

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

On "Done", call `get-automations` again. If it still returns `githubConnectUrl`, do not repeat the link. The most common cause is a browser signed in to a different LaunchDarkly account or member, so the App was installed there. Ask header "Browser account", with this connection's email in the question text (for example, "This connection is signed in as admin@acme.example. Which account is your browser signed in to?"):

- label: "The same", description: "My browser is signed in as that member"
- label: "A different one", description: "My browser is signed in to another account or member"
- label: "Not sure", description: "I need to check"

For "A different one" or "Not sure", tell them to check at `/profile`, sign in as the member from Step 1, open the link again, and finish there; then list again. For "The same", check the other causes in [references/github-troubleshooting.md](references/github-troubleshooting.md). On "Need an org owner", summarize the decisions so far, repeat the exact URL for the org owner, tell the user to say "continue Release Autopilot setup" after the App is installed, and stop. On "I can't authorize", pause the same way: summarize the decisions so far, tell them to sign in to GitHub with an account that is a member of that organization (or ask an org owner to add theirs), repeat the exact URL, tell them to say "continue Release Autopilot setup" once they have authorized, and stop. See the GitHub-identity cause in [references/github-troubleshooting.md](references/github-troubleshooting.md).

Never go on to Step 4 while `get-automations` still returns `githubConnectUrl` or `reposError`: the repo list then has only mapped repos, so a missing repo does not mean that its organization lacks the App.

### Step 4: Map repositories

Only if the user picked auto-flagging or auto-releasing. If they picked only auto-cleanup or auto-archival, do not map repos: ask which projects to set up (header "Projects", `multiSelect: true`, from `get-projects`, or ask for the keys) and go to Step 5.

1. **Choose repos.** If the current workspace has a `git remote` on the install list, offer it first. Use `AskUserQuestion` with header "Repos", `multiSelect: true`, and up to four repos from the install list, as `owner/name`. If the install has more than four repos, say the user can type any other `owner/name` from the list in Other. Use only repos that came back from `get-automations`.

   If a repo the user wants is not on the list, its owner decides the fix: a listed owner means the App needs access to that repo, and a new owner means an org owner must install the App there (no `githubConnectUrl` appears for this case). See [references/edge-cases.md](references/edge-cases.md). Wait for "Done" and list again.
2. **Choose a project for each repo.** Each repo maps to one LaunchDarkly project, which is where auto-flagging creates flags and metrics for that repo. If `get-projects` is available, offer the projects as options. Otherwise ask for the project key.
3. **Check existing mappings** with the `repos` list from Step 1 (an unmapped repo has `mapped: false`). Already mapped to the chosen project with matching capabilities: write nothing. Mapped to the chosen project with an unpicked capability on: record an override that turns it off. Mapped to the chosen project with a picked capability effectively off, because the repo turns it off or (on accounts that use project Automations settings) does not set it: record a repo write that turns it on (`{ "enabled": true }`), plus the account write if the account has it off (see Core Principle 7), and say so in Step 7. The exception is a capability that cannot work yet, such as auto-releasing in a project where release setup stopped (Step 6): keep it off. Mapped to a different project: never remap here; send the user to the settings skill to unmap first. Details: [references/edge-cases.md](references/edge-cases.md#existing-mappings).
4. **Say what starts when.** On accounts that use project Automations settings, each picked capability starts in a repo as soon as Step 8 writes that repo. On accounts that still use account settings, it starts only once the account setting is also on: right after the Step 8 account write, or, if the account has it off and the user cannot write account settings, when an admin turns it on.

### Step 5: Choose the AI model account

Skip this step if the user picked only auto-archival; it runs no agents.

The agents behind these capabilities (Vega) use an AI model to read pull requests and write code changes. This step decides whose model account they use; the product calls it "inference". Most users keep the default. Before asking, tell the user in one sentence what the choice means, for example: "The agents behind auto-flagging use an AI model to read your pull requests. By default they run on LaunchDarkly's model account; you can use your own Anthropic or OpenAI key instead." Then use `AskUserQuestion` with header "AI model":

- label: "LaunchDarkly's (default)", description: "The agents use an AI model that LaunchDarkly provides and pays for. No setup"
- label: "Bring your own key", description: "The agents use your own Anthropic or OpenAI API key, for example to keep usage on your provider contract. Your provider bills you for usage"

For "Bring your own key", record the choice only. It is a browser step that changes settings, so it happens after "Looks good", in [Step 8](#step-8-apply).

### Step 6: Set up releases and cleanup

Run each part of this step only for a capability the user picked in Step 2, and skip the step if they picked none of them. Never walk the user through a capability they did not pick:

- Auto-releasing picked: [Release setup](#release-setup).
- Auto-cleanup picked: [Auto-cleanup](#auto-cleanup).
- Auto-archival picked: [Auto-archival](#auto-archival).

#### Release setup

Only if the user picked auto-releasing. Otherwise skip to [Auto-cleanup](#auto-cleanup) or [Auto-archival](#auto-archival), and do not ask about environments or look up release plans.

For each project from Step 4, choose environments: use `AskUserQuestion` with header "Environments", `multiSelect: true`, offering the project's environments (from `get-projects` with `projectKey`, or ask). An environment is production when `get-projects` marks it `critical: true`. If no chosen environment has `critical: true`, or the read does not show `critical`, ask header "Production", `multiSelect: true`, which chosen environments serve production traffic, with "None" as an option. Then call `get-environment-release-plans` for the first chosen environment only, and wait for its result before calling it for any other environment:

- It succeeds: follow [Release plans](#release-plans).
- It fails, or the tool is not available: stop release setup for this project, and create no plans. Keep auto-releasing off for each repo in the project, and list "set up release plans for this project" as a follow-up. For 403 `Plan does not allow this operation` or a missing tool, tell the user that release plans are not available on their account and to contact LaunchDarkly support. The 403 is account-wide, so do not call it for other projects. For any other error, tell the user what failed.

##### Release plans

For each chosen environment, call `get-environment-release-plans`. Auto-releasing uses the environment's default plan.

- **The environment has complete plans.** Show the default plan (or, if none is the default, each complete plan) with its phases, rollout steps, and metrics. Ask header "Plan": "Use this plan" ("Keep it as this environment's default"), or "Choose another" (offer the other complete plans, or a starter plan below). If the plan the user keeps is not the default yet, record setting it as the default. If another plan is the default now, record that the new one replaces it.
- **The environment has only incomplete plans.** An incomplete plan cannot start a release or become the default. Name them, say that, and offer a starter plan as for an environment with no plans.
- **The environment has no plans.** Offer a starter plan so the user does not build one from scratch. Each starter is a normal plan they can change later. Before offering, check the project with reads, not questions:
  1. **Randomization unit:** `search-contexts` with `kind: "user"`, `limit: 1` in that environment. If it finds contexts, use `user`. If not, call `search-contexts` with no kind to see which kinds the project stores. If it finds other kinds, ask header "Roll out by" with those kinds and `user`. If it finds none, the app has not sent contexts yet: use `user`, the kind every project has by default, and say so. A plan whose unit is not a context kind in the project cannot be created.
  2. **Rollback metrics:** a guarded plan needs the unit to be available for guarded rollouts, and no read shows that. LaunchDarkly turns this on for `user` by default. For any other unit, skip this check, use no metrics, and list "make <unit> available for guarded rollouts, then add rollback metrics to the plan" as a follow-up. For `user`, call `get-metrics` with `metricUsedIn: "guarded_rollouts"`, then without it if that finds none. Keep metrics whose `analysisUnits` include the unit. If any remain, ask header "Rollback metrics", `multiSelect: true`, with up to three of them plus "No metrics" ("Release step by step without automatic rollback"). Picked metrics make the starter guarded: a regression on one rolls the release back. They go in the plan as `{ "<metric key>": { "isGroup": false, "autoRollback": true } }`.

  Then ask header "Starter plan" with options that fit the environment, marking the first that applies "(Recommended)":
  - Production: label "Progressive", description "10% → 25% → 50% of everyone, with 4-hour holds"; label "Custom", description "Build the plan step by step".
  - Any other environment: label "Progressive", description "10% → 50% of everyone, with 4-hour holds"; label "Custom", description "Build the plan step by step".

  If the user picked rollback metrics, add "rolls back automatically if <metric names> regress" to the starters' descriptions. A plan with metrics allows at most 50000 (50%) per step, and every starter step fits. There is no 100% step: completing the release reaches everyone. Then show the full starter plan and ask "Looks right" or "Adjust it". For "Custom", follow [references/release-plans.md](references/release-plans.md). The exact starter configurations and keys are in that reference.

Record each plan to create, and record it as the environment's default. Do not call `create-environment-release-plan` or `update-default-environment-release-plan` yet.

#### Auto-cleanup

Only if the user picked auto-cleanup. For each project, call `get-automations` with `section: "cleanup"` and `projectKey`. If cleanup already runs (a schedule other than `disabled`), say so and record no change unless the user wants one. Lists replace the whole stored list, so when adding repositories to a running cleanup, record the full list: the existing `repositories` from the read plus the new ones. Otherwise ask, each as its own question:

1. **Schedule**: header "Cleanup schedule": "Weekly (Recommended)", "Daily", or "Monthly".
2. **Repositories**: which repos cleanup opens pull requests in. Offer the repos mapped in Step 4 for that project; for auto-cleanup alone, offer repos from the install list. Use only repos on the install.
3. **Pull requests per run**: header "Pull requests per run": "3 (Recommended)", "1", or "10".

Cleanup picks up flags that are ready to archive, and its jobs run with the permissions of the member who saves the settings, which is this member. Say both in Step 7. Record the settings; do not write them yet.

#### Auto-archival

Only if the user picked auto-archival. For each project, call `get-automations` with `section: "archival"` and `projectKey`. If automatic archival is already on, say so and record no change. If it is off, turning it on needs a person on the Automations page (the MCP can only turn it off or adjust it once it is on), so record a browser step for after "Looks good". If the call says automatic archival is not available, the account does not include it: list it as a follow-up.

### Step 7: Confirm the plan

**STOP. Do not write anything until the user explicitly confirms.** A detailed request at the start is not approval.

List every write in the order you will make it. For each write, state the current and the proposed state and the blast radius, using the wording rules from the settings skill's [Confirm before write](../launchdarkly-release-autopilot-settings/SKILL.md#confirm-before-write):

1. **Metrics and release plans** (release plans only): one line per metric to create and per environment, with the plan name, rollout steps, advancement, metrics, and that it becomes the environment's default. When the environment already has a default, say that the plan "replaces <current default> as the default".
2. **Repo mappings and overrides**: one line per repo, naming the project and the **effective** auto-flagging and auto-releasing state after every write in this plan. For a capability the user did not pick, or that cannot work yet, the mapping sends a repo override that turns it off. Say so: "Auto-releasing: off for this repository (the account has it on; release plans are not set up for this project)." For a picked capability that a repo override kept off, say the write turns it back on: "Auto-flagging: off → on for this repository (it was turned off for this repository only)."
3. **Account settings**: only fields that change, for a picked capability the account has off (see Core Principle 7). If auto-releasing turns on, say it can ship code.
   For a member who is not an admin or owner, list account writes under "Needs an admin" instead, and say an admin can make them with the settings skill. Do not name a settings page; there is none to point to.
4. **Auto-cleanup**: one line per project with the schedule, repositories, and pull requests per run. Say that cleanup will open pull requests that remove code, and that its jobs run with this member's permissions.
5. **Browser steps after these changes**: bring your own key and turning on auto-archival, one line per project with its link. GitHub, if the user connected it in Step 3, is marked as reported, not verified.
6. **Follow-ups for the user**: release plans to set up, metric events to instrument.

If there are no writes and no browser steps, say so, list the follow-ups, and stop.

**Preview mode:** the final message contains only the heading "Changes an admin would make", the checklist (one line per change), and any follow-ups. Do not repeat the account state, and do not ask for confirmation. For example:

```
- [ ] Map acme/demo to project default, with auto-releasing off for this repository
- [ ] Turn on auto-flagging for the account
- [ ] Turn on weekly flag cleanup for project default in acme/demo, up to 3 pull requests per run
- [ ] In the browser: turn on automatic archival at /projects/default/settings/automations
```

**Setup mode:** use `AskUserQuestion` with header "Confirm":

- label: "Looks good", description: "Make every change in this plan"
- label: "Change something", description: "Adjust the plan before you start"

Only "Looks good" approves the plan. On "Change something", ask what to change, make the change, and show the full plan again. Any other answer, including one that does not match an option, is not approval: ask the confirmation again. Do not go to Step 8 until the user selects "Looks good".

### Step 8: Apply

Make only the writes in the confirmed plan, in this order. Stop at the first failure, report it, and do not continue. If `create-environment-release-plan` fails because the randomization unit is not available for guarded rollouts, nothing else was written: offer the same starter with "No metrics" and confirm the plan again.

1. Release plans only: metrics recorded in Step 6, created in LaunchDarkly with [`launchdarkly-metric-create`](../../metrics/launchdarkly-metric-create/SKILL.md). Skip its instrumentation steps.
2. Release plans only: `create-environment-release-plan` for each new plan, then `update-default-environment-release-plan` with `default: true` for each plan recorded as an environment's default.
3. `update-automations` with `accountWide: false` for each repo, with `repo: "owner/name"` and `projectKey`. For each picked capability that can work, send `{ "enabled": true }`, because on accounts that use project Automations settings, a capability the repo does not turn on is off. For each capability the user did not pick, or that cannot work yet, send `{ "enabled": false }`, so the repo does not get it from the account settings.
4. `update-automations` with `accountWide: true` and only the confirmed fields. Never send `autoCleanup`.
5. Auto-cleanup only: `update-automations` with `projectKey` and a `cleanup` object (`schedule`, `repositories`, `maxJobsPerRun`) for each project.

`update-automations` and `update-default-environment-release-plan` require `confirm: true`; pass it only for writes in the confirmed plan.

The order matters. When the plan creates release plans, they come first, so that no release can start without the plan the user chose. The account settings come last because, on accounts that still use them, turning a capability on there starts it in every mapped repo that does not turn it off.

If a write fails with 403, the member lacks that permission. Report which write failed, list the remaining writes as a checklist for an admin, and stop.

**Browser steps.** After the writes, walk the user through each browser step from Step 7, one at a time, with the link in the question text:

- **Bring your own key:** for each project, `/projects/{projectKey}/settings/automations`, in the "Inference" section. Follow [references/byok.md](references/byok.md). Ask header "AI model": "Done" ("I saved my key in the Automations settings for every project") or "Use LaunchDarkly's for now" ("Skip this. I'll switch to my own key later").
- **Auto-archival:** for each project, exactly `/projects/{projectKey}/settings/automations`, in the "Automatic archival" section. Follow [references/auto-archival.md](references/auto-archival.md). Ask header "Auto-archival": "Done" ("I turned on automatic archival for every project") or "Later" ("Skip this. I'll turn it on from Automations settings later").

Record each answer as reported by the user. Never do these in Preview mode.

### Step 9: Verify

1. **GitHub:** `get-automations` returns neither `githubConnectUrl` nor `reposError`. Say "GitHub is connected" only then. With `reposError`, say the GitHub App install could not be read, and do not call the setup complete.
2. **Repos:** `get-automations` with `repo` for each repo: mapped to the right project, effective auto-flagging and auto-releasing match the plan. If a picked capability is still effectively off for a repo, say which and do not call the setup complete.
3. **Account:** `get-automations`: `account` matches the plan.
4. **Release plans:** `get-environment-release-plans` for each environment lists the new plans and the right default.
5. **Cleanup and archival:** `get-automations` with `section: "cleanup"` (schedule, repositories, and the flags the next run picks up) and `section: "archival"` for each project. Archival that this read shows on is verified, including after the user turned it on in the browser.

If any change was left for an admin or failed, lead with "Partly set up: waiting on an admin" and the admin checklist, and never call the setup complete. Then report:

- **What is set up, exactly:** one line per repo (`owner/name` → project, auto-flagging and auto-releasing on or off), one line per environment's default release plan, and one line per project for cleanup (schedule and repositories) and archival.
- A checklist with each item marked verified, reported by the user (browser steps the user did in this flow), or already set up (steps the flow skipped because they were already done), then the follow-ups.

Then offer the next steps, each in one line. If a change is waiting on an admin, make them conditional ("Once an admin turns on auto-flagging, …"):

- **Try it with a test pull request.** If auto-flagging is on and the current workspace is a mapped repo, ask header "Test PR": "Help me open one" or "I'll do it later". For "Help me open one", suggest a small change that should ship behind a flag, and make it on a new branch only after the user agrees. Never push to the default branch or to an existing branch. Show the diff, and open it as a draft pull request only after they approve that diff. Then tell them what to expect: auto-flagging reads it within a few minutes and posts its proposed change on the PR, and nothing changes until someone replies `@launchdarkly approve` or presses Approve on the check. Otherwise, just describe that.
- **Use LaunchDarkly from the terminal and other agents.** The LaunchDarkly MCP server comes with the plugin from [Prerequisites](#prerequisites). The CLI installs with `brew tap launchdarkly/homebrew-tap && brew install ldcli`, or `npm install -g @launchdarkly/ldcli`.
- **Flag changes before they reach a pull request.** Coding agents can add the flag themselves while writing the change, with the `should-flag-change` and `flag-and-release-change` skills (`npx skills add https://github.com/launchdarkly/ai-tooling --skill flag-and-release-change`).
- If a PR is not classified, use [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md#why-didnt-my-pr-get-classified) to diagnose it.

## Edge Cases

| Situation | Action |
|-----------|--------|
| Every settings tool returns 404 | The account does not have the Release Autopilot add-on enabled. Tell the user and stop |
| Member role is `reader` or `no_access` | Preview mode. End with a checklist for an admin |
| Environment release plans return an error, or the tool is missing | Stop release setup for that project, create no plans, keep auto-releasing off there. For the 403 `Plan does not allow this operation`, tell the user to contact LaunchDarkly support |
| Repo not on the install list | Explain the GitHub fix by owner, then list again |
| GitHub still not connected after "Done" | Likely a different browser account. Follow [references/github-troubleshooting.md](references/github-troubleshooting.md) |

More cases: [references/edge-cases.md](references/edge-cases.md).

## What NOT to Do

- Don't write before Step 7's "Looks good", or at all in Preview mode.
- Don't turn on auto-releasing unless the user picked it, and never send `approvalRequired`.
- Don't map unpicked repos, iterate over the install list, or remap a repo to another project.
- Don't act in the user's browser or report a browser step as verified (a read that confirms it, such as the archival section, is verified). Don't open a test pull request without the user's approval. Don't ask for a browser change before "Looks good" or in Preview mode.

## References

- [references/release-plans.md](references/release-plans.md): creating environment release plans
- [references/modes.md](references/modes.md): Preview and Resume details
- [references/byok.md](references/byok.md): bring-your-own-key setup
- [references/auto-cleanup.md](references/auto-cleanup.md) / [references/auto-archival.md](references/auto-archival.md): cleanup settings, and turning on archival
- [references/github-troubleshooting.md](references/github-troubleshooting.md): GitHub still not connected after the user finished
- [references/edge-cases.md](references/edge-cases.md): edge cases and existing mappings
- [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md): settings rules, write confirmations, and PR diagnosis
- [`launchdarkly-automations-cleanup-settings`](../launchdarkly-automations-cleanup-settings/SKILL.md) / [`launchdarkly-automations-archival-settings`](../launchdarkly-automations-archival-settings/SKILL.md): change auto-cleanup and auto-archival after setup
- [Vega inference settings](https://launchdarkly.com/docs/home/getting-started/vega#vega-inference-settings)
- [Guarded rollouts](https://launchdarkly.com/docs/home/releases/guarded-rollouts)
