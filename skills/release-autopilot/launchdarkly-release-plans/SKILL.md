---
name: launchdarkly-release-plans
description: "List, create, edit, make default, and delete LaunchDarkly release plans of both kinds: environment release plans (one environment's phases, rollout steps, and rollback metrics, with starter plans) and flag release plans (a project's environments in release order, each with its environment release plan, which Release Autopilot proposes releases from on pull requests). Also starts a flag's release from a flag release plan. Use when the user wants to see, list, build, change, or remove a release plan (such as 'show me the flag release plans' or 'what release plans does production have'), set an environment's or a project's default plan, or when another skill such as Release Autopilot onboarding needs release plans planned or created. For first-time Release Autopilot setup, use launchdarkly-release-autopilot-onboarding, which follows this skill."
license: Apache-2.0
compatibility: "Uses the hosted LaunchDarkly MCP server. When the server has no tool for an operation (flag release plans before their tools reach the account, starting a flag's release, deleting an environment release plan), the user runs the REST API (beta) command that the skill shows in their own terminal."
metadata:
  author: launchdarkly
  version: "1.1.1"
---

# LaunchDarkly Release Plans

You're using a skill that reads and changes LaunchDarkly release plans. There are two kinds:

- An **environment release plan** releases a flag in one environment: its phases, rollout steps, holds, and rollback metrics. A plan with metrics is guarded, so a regression can roll the release back. A plan without metrics is progressive. Each environment can have one default plan.
- A **flag release plan** is project-level. It lists the project's environments in release order, and names the environment release plan each one releases with (or says the environment releases immediately). When Release Autopilot proposes a release on a pull request, it uses the project's flag release plans, and it proposes none when the project has none. A rollout recorded for a flag (the `flag-release` skill, `create-automated-rollout-config` with `policy`) uses each environment's default release plan and does not need a flag release plan. A project can have one default flag release plan.

Releases can ship code to users, so treat every write as production automation with a blast radius.

## Prerequisites

**MCP tools (hosted LaunchDarkly MCP server), preferred where they exist:**
- `get-environment-release-plans`: an environment's plans, each with `default`, or one plan with `releasePlanKey`
- `create-environment-release-plan`, `update-environment-release-plan` (send only the fields to change; `phases` and `metrics` each replace the whole value), and `update-default-environment-release-plan` (`default: true` sets it, `default: false` clears it; needs `confirm: true`)
- `get-flag-release-plans`: a project's flag release plans, each with `default`, or one plan with `flagReleasePlanKey`. When `hasMore` is true, pass `nextOffset` as `offset`
- `create-flag-release-plan`, `update-flag-release-plan` (send only the fields to change; `environments` and `applicationKeys` each replace the whole list; leave out `default` to keep it; needs `confirm: true`), and `delete-flag-release-plan` (needs `confirm: true`). Each write returns the plan as read back
- When the server has them: `create-flag-release` (start a flag's release from a flag release plan) and `delete-environment-release-plan` (needs `confirm: true`)
- Used for starter plans: `search-contexts` (randomization unit) and `get-metrics` (rollback metrics)

**REST API (beta), for an operation that has no MCP tool on the connected server:** flag release plans when their tools are missing, starting a flag's release without `create-flag-release`, deleting an environment release plan without `delete-environment-release-plan`, and the environment release plan changes whose MCP tool is missing. The user runs these commands, as [User-run commands](#user-run-commands) says. Every request sends `LD-API-Version: beta`. `ldcli` (3.16.0) has no command for these endpoints and no command that sends a raw request with that header, so the commands use curl. They are in [references/rest-api.md](references/rest-api.md).

**When a tool or request is not available:**
- An environment release plan tool is missing from the server: the MCP server is out of date, not the account. Tell the user to update or reconnect the LaunchDarkly MCP server. The user can run the REST equivalent from [references/rest-api.md](references/rest-api.md) instead.
- A flag release plan tool is missing from the server: the tools are still reaching accounts, so this does not mean that the account lacks flag release plans. Use the REST command for that operation, as [User-run commands](#user-run-commands) says. Do not say that the account lacks flag release plans, and do not send the user to support. Do not tell the user to update or reconnect the MCP server for these tools: they reach accounts behind a flag, not with a server update.
- `create-flag-release` or `delete-environment-release-plan` is missing: use the REST command for it.
- A read returns 403 `Plan does not allow this operation`, or a tool says the account's plan does not include that kind of release plan: it is not available on the account. Tell the user to contact LaunchDarkly support, and stop work on that kind of plan.

## Modes

| Mode | When | What you do |
|------|------|-------------|
| **Apply** | The default | Read, decide with the user, confirm, then write |
| **Read-only** | "show", "preview", "what would you change", a dry run, or a reader role | MCP reads. When a read has no MCP tool (such as the flag release plan list without its tool), ask the user to run the REST read, with the "Run this command" question in [User-run commands](#user-run-commands): the user runs it, not you. Describe the writes you would make in words, and list any REST write as an optional command for later. Never ask the user to run a write. Do not ask for confirmation |
| **Record only** | Another skill (such as Release Autopilot onboarding) plans release setup and confirms it itself | Run the reads (MCP reads, and any REST read the user runs and pastes) and ask the choices below, then return the decisions as a list of writes: an MCP write where the server has the tool, and a REST command where it does not. When the calling skill is in a preview or dry run, use MCP reads only, ask the user to run nothing, and return the REST reads as optional follow-ups. Write nothing, and do not ask the "Confirm" question or show write commands. The calling skill confirms, then makes the writes in [Write order](#write-order) |

## User-run commands

You never run a REST command, and you never use a LaunchDarkly token. The user runs each REST command in their own terminal with their own LaunchDarkly API access token. In Read-only mode, ask the user to run only REST reads, and list the write commands instead. In a calling skill's preview (Record only mode), ask the user to run nothing: list the commands instead.

1. Show the exact command in a code block, filled in with the keys and the JSON body. Say: "Run this in your terminal with your LaunchDarkly API access token in `LD_ACCESS_TOKEN`." Their shell fills in `$LD_ACCESS_TOKEN`.
2. In the same message, ask header "Run this command" with your question tool (such as `AskUserQuestion`): "Done, here's the output" ("Paste the output below, with any secrets removed") or "Skip" ("Do this later"). The user pastes the output as their answer. Ask for the output only, and do not end your turn with only the command.
   - **Put the command in the question too.** While the question is open, the user may see only the question, not your message. If the question tool has a preview for each option (such as `AskUserQuestion`'s `preview`), put the full code block in the preview of "Done, here's the output", not a reference to it (such as "the command above"). If the tool has no preview, put the full code block in the question text. Never ask "Run this command" with a question that does not show the command.
3. Read the pasted output. The last line is `HTTP <status>`, and the JSON before it is the response body. Continue from it: report a read, check a write against what was confirmed, or follow [Errors](#errors). If the output is not there or cannot be read, ask the user to run the command again and paste all of it.
4. "Skip" leaves the change undone: list the command as a follow-up.

**Never ask for a token in the chat**, and never use one that is pasted there. If the user pastes a token, do not repeat it. Tell them to delete that token in **Organization settings > Authorization** and make a new one, because the chat may keep it. To make a token, they go to **Organization settings > Authorization**, then run `export LD_ACCESS_TOKEN=<token>` in their own terminal.

## Check for a default before every create

This rule applies to every create path: a direct "create a release plan" request, [Create](#create), [Build or update the project's plan](#build-or-update-the-projects-plan), and Record only mode.

- **Environment release plan:** read the environment's plans before you create one. If the environment has a default, tell the user first: its name, and a short summary of its phases, rollout steps, and metrics. Then ask header "Default plan":
  - "Use <name>" ("Keep the current default. Create nothing")
  - "Create a new plan and make it the default" ("It replaces <name> as the default")
  - "Create a new plan, keep <name> as the default"
- **Flag release plan:** list the project's plans before you create one (`get-flag-release-plans`, or the list command that the user runs). If the project has a stored default, tell the user first: its name, and its environments in order with the release plan for each. Then ask header "Flag release plan":
  - "Update <name> (Recommended)" ("Change its environments and release plans. It stays the default")
  - "Keep <name>" ("Create nothing")
  - "Create another plan" ("A new plan that is not the default")

  Ask this question even when the request already says what to do (for example, "make it the default"). Ask it before the "Confirm" question and before any write.
- **Incomplete plans:** also name any incomplete plans, and say that they cannot start a release or be the default.
- **The built-in flag release plan:** a project with no stored flag release plans lists one built-in plan, key `default-release-configuration`. It is not a stored plan, and it is not a stored default: the project has no flag release plans yet. It cannot be read by key, changed, deleted, or used to start a release. A new plan can be the default, and it replaces the built-in one.

Ask this before any other create question, and create nothing until the user answers.

## Core Principles

1. **Read before you write.** Read the existing plans first, and reuse a plan that already does what the user wants.
2. **The question carries what it asks about.** While a question is open, the user may see only the question, not your message. When a question asks about a plan, a change, or a command you showed ("Use this plan", "Looks right", "Make this change", "Update <name>", "Run this command"), put that plan, change, or command in the question too: in the `preview` of the option that accepts it, or in the question text if the question tool has no preview. This holds in every mode, including Record only.
3. **Confirm before every write** (Apply mode). State the current and the proposed plan in words. For an MCP write, of either kind of plan, ask header "Confirm" with exactly two options, "Make this change" and "Cancel", and write only after "Make this change" in this turn. Do not add an option for another change (such as "Make it the default instead"). A different change needs its own "Confirm" question, with that change shown. For a REST write, the user runs the command, so show the change in words with the command. A detailed request is not approval, and neither is a yes from an earlier turn. A retry after a failed write needs its own confirmation.
4. **Prefer MCP tools.** Use the REST API only for an operation that has no MCP tool on the connected server.
5. **Only touch what the user named.** Never delete, demote, or edit a plan the user did not name.
6. **Speak in product words.** Say "release plan", "flag release plan", "default", and environment names. Do not show tool names, field names, HTTP status codes, or JSON to the user, except inside a command the user runs. Never mention this skill, or any skill, to the user: say what you do and why, not that a skill requires it.

## Environment release plans

### Read

`get-environment-release-plans` with `projectKey` and `environmentKey`. Report each plan's name, whether it is the default, and its phases, rollout steps, holds, and metrics. An incomplete plan (migrated from a release policy) cannot start a release or become the default: say so when you name one.

### Choose an environment's release plan

Do this for every environment that needs a plan: for the user's own request, for a flag release plan, and for onboarding in Record only mode.

1. Read the environment's plans. Use only complete plans.
2. **The environment has complete plans, and one is the default.** Propose its default plan, unless the user named another. Show it with its phases, rollout steps, and metrics. Ask header "Plan": "Use this plan" ("Keep it as this environment's default") or "Choose another" (offer the other complete plans, or a starter plan). If the plan the user keeps is not the default yet, record setting it as the default. If another plan is the default now, say that the new one replaces it as the default. The exception is a plan that a flag release plan already names for this environment: keeping it there does not change the environment's default. Record no default change for it, and do not say that it becomes the default.
3. **The environment has complete plans, and none is the default.** Show each complete plan with its phases, rollout steps, and metrics. Ask header "Plan" with one option per complete plan ("Make it this environment's default") and "Create a starter plan". Record setting the chosen plan as the default.
4. **The environment has no complete plan.** Tell the user it needs a release plan first, and offer a starter plan as [Create](#create) says. "Not now" is how the user declines. For a flag release plan, add the environment only after its plan exists (or is recorded, in Record only mode).
5. **The user declines.** Create nothing for that environment. Leave it out of any flag release plan, and say so.

Never invent a release plan key, and never point at an incomplete plan.

### Create

First apply [Check for a default before every create](#check-for-a-default-before-every-create). Continue only when the user chose to create a plan, or the environment has no default. Then offer a starter plan so the user does not build one from scratch, or a custom plan. The starter definitions, the checks to run before you offer them, and the custom questions are in [references/environment-release-plans.md](references/environment-release-plans.md):

1. **Randomization unit:** check stored contexts with `search-contexts`. Do not ask the user what reads can answer.
2. **Rollback metrics:** `get-metrics`, keeping metrics whose `analysisUnits` include the unit. Metrics make the plan guarded, and a guarded plan allows at most 50% per step.
3. **Starter:** ask header "Starter plan": "Progressive", "Custom", or "Not now". Show the full plan, and ask "Looks right" or "Adjust it", with the plan in the question ([Core Principles](#core-principles) 2). After "Adjust it", change the plan as the user asks, then show the full plan again and ask "Looks right" or "Adjust it" again, with the plan in the question. Go on to the confirmation only after "Looks right".
4. **Key:** keys are unique in the project, so if a starter's key is taken anywhere in the project (another environment, or an active plan here), add `-2`, then `-3`, until it is free.
5. Confirm, then `create-environment-release-plan`, then `update-default-environment-release-plan` with `default: true` when it becomes the default. A new default replaces the current one: say so in the confirmation.

If the create fails because the randomization unit is not available for guarded rollouts, nothing was written. Offer the same plan with no metrics, and confirm again.

### Make a plan the environment's default

Confirm, naming the plan it replaces. Then `update-default-environment-release-plan` with `releasePlanKey`, `default: true`, and `confirm: true`. The plan must be complete.

### Edit

Read the plan, change only what the user asked, and confirm the change in words. Then `update-environment-release-plan` with only the changed fields. `phases` and `metrics` each replace the whole value, so send every phase or metric to keep. Without the MCP tool, show the REST replace from [references/rest-api.md](references/rest-api.md), which is a full replace with the plan's `version`.

### Delete

Say first if the plan is the environment's default (the environment then has none). With `delete-environment-release-plan` on the server, confirm, then call it with `releasePlanKey` and `confirm: true`. Without it, the user runs the REST delete. A plan that a flag release plan still names cannot be deleted (409, or an error that names those plans): name the flag release plans that use it, and offer to change them first. To clear only the default, use `update-default-environment-release-plan` with `default: false`.

## Flag release plans

Use the flag release plan tools when the server has them: `get-flag-release-plans`, `create-flag-release-plan`, `update-flag-release-plan`, and `delete-flag-release-plan`. In Apply mode, confirm each write as [Core Principles](#core-principles) 3 says, with the plan or the change in the "Confirm" question. When the server has no tool for an operation, show the REST command for it from [references/rest-api.md](references/rest-api.md). The user runs it and pastes the output, as [User-run commands](#user-run-commands) says.

### How a flag release plan names environment release plans

- Each environment names one environment release plan by key, or releases immediately. The named plan must exist in that environment and be complete, or the write fails with a validation error.
- A flag release plan stores each environment's release plan key, so a later change to that environment's default release plan does not update the flag release plan.
- Environments are in release order. Plans are sequential by default: each environment releases after the one before it. Order non-production before production.
- **Show names, not keys.** A flag release plan read gives only the key of each environment's release plan. Before you report or show a flag release plan (in [List or show](#list-or-show), [Build or update the project's plan](#build-or-update-the-projects-plan), a confirmation, and Record only mode), read each of its environments' release plans with `get-environment-release-plans`, and use each plan's name. Never make up a name, and do not show a key as a name. If the read has no plan with that key, say that the environment names a release plan that was not found.
- Each environment's trigger decides what starts its release. Use "when the flag evaluates there" (`flag_eval`) unless the user asks for another. [references/rest-api.md](references/rest-api.md) lists the others and their rules.

### The project's default flag release plan

When auto-releasing knows the change's application, it uses the plans for that application, or the project's default when none is for it. When it does not know the application, every plan is a candidate, and with more than one it asks on the pull request which one to use.

- A new plan can be the default only when the project has no stored default. The built-in plan does not count.
- To change what the default does, edit the default plan in place: same key, still the default. Do not create a second plan unless the user asks for one.
- **With `update-flag-release-plan`:** send only the fields to change. Leave out `default` to keep the plan's default setting. `environments` replaces the whole list, so send every environment to keep, in order. `default: true` makes the plan the default and demotes the current one. `default: false` keeps the plan, and the project then has no default.
- **With a REST command:** an update is a full replace. Leaving out the default setting clears it. Always start from a fresh read, and send every field to keep.
- **A new plan that replaces the default:** a create cannot take the default from another plan. Create the plan without the default setting, then make it the default as [Make another plan the default](#make-another-plan-the-default-or-delete-one) says. Confirm both writes in one "Confirm" question, which names the default it replaces.

### List or show

`get-flag-release-plans` with `projectKey`. When `hasMore` is true, read the next page with `nextOffset` as `offset`. For one plan, add `flagReleasePlanKey`. Without the tool, show the list command, and read the pasted output (page with `offset` while more remain).

For each plan, report its name, whether it is the default, and its environments in order with the name of the release plan for each, from the environment's read ("production: Production progressive rollout", or "releases immediately"). If the list holds only the built-in plan, say that the project has no flag release plans yet.

### Build or update the project's plan

1. List the project's plans: `get-flag-release-plans`, or the list command that the user runs.
2. For each environment the user wants, in release order, choose its environment release plan as in [Choose an environment's release plan](#choose-an-environments-release-plan).
3. Decide:
   - **No stored default:** a new plan "Default release" (key `default-release`, or the next free key), as the project's default.
   - **The project has a default:** name it and its environments, and ask the "Flag release plan" question in [Check for a default before every create](#check-for-a-default-before-every-create), before the "Confirm" question and before any write. If it already has these environments, in this order, with these release plans, say so and recommend "Keep <name>". An update keeps the plan's key and its default setting. "Create another plan" creates a plan that is not the default.
4. Show the current and the new environments and release plans in words, with each release plan's name.
   - **With the tools:** ask header "Confirm", with the new plan in the preview of "Make this change". Then `create-flag-release-plan` with `key`, `name`, and `environments` (and `default: true` only when the project has no stored default), or `update-flag-release-plan` with `flagReleasePlanKey`, `environments`, and `confirm: true`. Leave `default` out of the update, so the plan stays the default.
   - **Without the tools:** show the create or replace command (with the plan's `version`).
5. Check the result: the tool's plan as read back, or the pasted response. Its environments, release plans, and default must match what you showed. If a pasted response is not there, show the get command.

If the key is taken, use the next free key, and confirm again (or show the command again). If an update says someone else changed the plan (a 409 for a stale version in a pasted response), read the plan again, show what changed, and confirm again (or show the command again).

### Make another plan the default, or delete one

- **Default:** from the read, say what changes ("Staged rollout becomes the project's default flag release plan. It replaces Fast as the default."). With the tool, ask "Confirm" with that change in the question, then `update-flag-release-plan` with `flagReleasePlanKey`, `default: true`, and `confirm: true`, and no other fields. Without the tool, show the replace command with every field from the read, the default setting on, and its `version`. Check the plan as read back, or the pasted response.
- **Stop using a plan as the default:** the same, with `default: false`. The plan stays, and the project has no default until another plan becomes the default.
- **Delete:** name the plan and say if it is the default (the project then has no default). Releases already started from it continue. With the tool, ask "Confirm", then `delete-flag-release-plan` with `flagReleasePlanKey` and `confirm: true`, and check that it returns `deleted: true`. Without the tool, show the delete command, and check for `HTTP 204`. The built-in plan cannot be deleted.

### Start a flag's release from a plan

This starts a release that can ship the flag's change to users. Name the flag, the plan, and each environment in order with its release plan. With `create-flag-release` on the server, ask "Confirm" with all of that in the question, then call it with `flagKey` and `flagReleasePlanKey`. Without it, show the command that creates the flag release from the plan. The built-in plan cannot start a release: create a flag release plan first. For a release tied to a pull request, use [`flag-release`](../../feature-flags/flag-release/SKILL.md) instead.

## Write order

Write environment release plans before anything that names them:

1. Metrics to create, with [`launchdarkly-metric-create`](../../metrics/launchdarkly-metric-create/SKILL.md)
2. Environment release plans, then each environment's default
3. The flag release plan that names them

## Errors

| Error | Meaning | What to do |
|-------|---------|------------|
| Validation error (400) | The message says why. For example: a release plan that is unknown, incomplete, or in another environment, the project already has a default flag release plan, a step over 50% in a plan with metrics, or a unit that is not available for guarded rollouts | Tell the user the reason in words, fix the request, and confirm again |
| Unauthorized (401) | A REST command: the user's token is missing, wrong, or expired | Tell the user to set `LD_ACCESS_TOKEN` in their terminal to a valid token, and run the command again |
| `Plan does not allow this operation` (403) | That kind of release plan is not on the account | Tell the user to contact LaunchDarkly support. Stop |
| Any other 403 | The role cannot do this in the project | Name the change that failed and stop. A member with that permission can make it |
| Not found (404) | The project, environment, flag, or plan does not exist | Check the key with a read. Do not create a plan to work around it |
| Conflict (409) | A taken key, a stale version (an MCP update says someone else changed the plan), or deleting an environment release plan that a flag release plan names | See the workflow for that change |
| Accepted, not confirmed | An MCP write says LaunchDarkly accepted the change, but reading it back failed or did not match | Do not make the write again. Read the plan, and report what the read shows |
| Server error (5xx) | LaunchDarkly could not complete it | Report it. A read can run again once. Before a write runs again, read again (or have the user read again), because it may have been applied |

An MCP tool returns these as an error message, not a status code: read the message. Never repeat a write in a loop.

## Out of scope

- Turning auto-releasing on or off for a repository: use [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md).
- First-time Release Autopilot setup: use [`launchdarkly-release-autopilot-onboarding`](../launchdarkly-release-autopilot-onboarding/SKILL.md).

## References

- [references/environment-release-plans.md](references/environment-release-plans.md): starter plans, the checks before them, and custom plans
- [references/rest-api.md](references/rest-api.md): REST endpoints, the MCP tool for each, curl commands, fields, and JSON examples for both kinds of plan
- In the LaunchDarkly UI: `/projects/{projectKey}/settings/releases`, with `?tab=flag-release-plans` for flag release plans
- [Guarded rollouts](https://launchdarkly.com/docs/home/releases/guarded-rollouts)
