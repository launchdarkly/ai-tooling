---
name: launchdarkly-release-plans
description: "List, create, edit, make default, and delete LaunchDarkly release plans of both kinds: environment release plans (one environment's phases, rollout steps, and rollback metrics, with starter plans) and flag release plans (a project's environments in release order, each with its environment release plan, which auto-releasing proposes releases from). Also starts a flag's release from a flag release plan. Use when the user wants to see, build, change, or remove a release plan, set an environment's or a project's default plan, or when another skill such as Release Autopilot onboarding needs release plans planned or created. For first-time Release Autopilot setup, use launchdarkly-release-autopilot-onboarding, which follows this skill."
license: Apache-2.0
compatibility: "Environment release plans use the hosted LaunchDarkly MCP server. Flag release plans, and deleting an environment release plan, use curl and a LaunchDarkly API access token in LD_ACCESS_TOKEN (REST API, beta)."
metadata:
  author: launchdarkly
  version: "1.0.0"
---

# LaunchDarkly Release Plans

You're using a skill that reads and changes LaunchDarkly release plans. There are two kinds:

- An **environment release plan** releases a flag in one environment: its phases, rollout steps, holds, and rollback metrics. A plan with metrics is guarded, so a regression can roll the release back. A plan without metrics is progressive. Each environment can have one default plan.
- A **flag release plan** is project-level. It lists the project's environments in release order, and names the environment release plan each one releases with (or says the environment releases immediately). Auto-releasing proposes each new release from the project's flag release plans, and proposes none when the project has none. A project can have one default flag release plan.

Releases can ship code to users, so treat every write as production automation with a blast radius.

## Prerequisites

**MCP tools (hosted LaunchDarkly MCP server), preferred where they exist:**
- `get-environment-release-plans`: an environment's plans, each with `default`, or one plan with `releasePlanKey`
- `create-environment-release-plan`, `update-environment-release-plan` (send only the fields to change; `phases` and `metrics` each replace the whole value), and `update-default-environment-release-plan` (`default: true` sets it, `default: false` clears it; needs `confirm: true`)
- Used for starter plans: `search-contexts` (randomization unit) and `get-metrics` (rollback metrics)

**REST API (beta), for what has no MCP tool:** every flag release plan operation, deleting an environment release plan, and clearing an environment's default when the MCP tool is missing. These need curl and an API access token in `LD_ACCESS_TOKEN` (see [Token handling](#token-handling)), and `LD_BASE_URI` for an instance other than `https://app.launchdarkly.com`. Every request sends `LD-API-Version: beta`. `ldcli` (3.16.0) has no command for these endpoints and no command that sends a raw request with that header, so use the curl commands in [references/rest-api.md](references/rest-api.md).

**When a tool or request is not available:**
- An environment release plan tool is missing from the server: the MCP server is out of date, not the account. Tell the user to update or reconnect the LaunchDarkly MCP server. With a token, the REST equivalent in [references/rest-api.md](references/rest-api.md) works too.
- A read returns 403 `Plan does not allow this operation`: that kind of release plan is not available on the account. Tell the user to contact LaunchDarkly support, and stop work on that kind of plan.

## Modes

| Mode | When | What you do |
|------|------|-------------|
| **Apply** | The default | Read, decide with the user, confirm, then write |
| **Read-only** | "show", "preview", "what would you change", a dry run, or a reader role | Reads only. List the writes you would make. Do not ask for confirmation |
| **Record only** | Another skill (such as Release Autopilot onboarding) plans release setup and confirms it itself | Run the reads and ask the choices below, then return the decisions as a list of writes. Write nothing and do not ask the "Confirm" question. The calling skill confirms, then makes the writes in [Write order](#write-order) |

## Token handling

1. **Never ask for the token in the chat**, and never accept one there. If the user pastes a token, do not use it. Tell them to delete that token in **Organization settings > Authorization** and make a new one, because the chat may keep it.
2. **Never print, echo, or log the token.** Check only that it is set:

   ```sh
   if [ -n "${LD_ACCESS_TOKEN:-}" ]; then echo "LD_ACCESS_TOKEN is set"; else echo "LD_ACCESS_TOKEN is not set"; fi
   ```

   Do not run `env`, `printenv`, `set`, `ldcli config --list`, or `curl -v`. Each one can show the token. Do not read ldcli's config file.
3. **If it is not set**, tell the user to create a token in **Organization settings > Authorization** and export it in their own terminal, not in the chat: `export LD_ACCESS_TOKEN=<token>`. A user who signed in with `ldcli login` exports the same token. The agent's shell gets the variable only when the agent starts after the export. So offer two options: restart the agent from that terminal, or run the commands from [references/rest-api.md](references/rest-api.md) themselves.
4. **If you cannot run shell commands**, give the user the exact commands to run, filled in with their keys.

## Core Principles

1. **Read before you write.** Read the existing plans first, and reuse a plan that already does what the user wants.
2. **Confirm before every write** (Apply mode). State the current and the proposed plan in words. Then ask header "Confirm" with "Make this change" and "Cancel". Write only after "Make this change" in this turn. A detailed request is not approval, and neither is a yes from an earlier turn. A retry after a failed write needs its own confirmation.
3. **Prefer MCP tools.** Use the REST API only for what has no MCP tool.
4. **Only touch what the user named.** Never delete, demote, or edit a plan the user did not name.
5. **Speak in product words.** Say "release plan", "flag release plan", "default", and environment names. Do not show tool names, field names, HTTP status codes, or JSON to the user, except inside a command the user runs.

## Environment release plans

### Read

`get-environment-release-plans` with `projectKey` and `environmentKey`. Report each plan's name, whether it is the default, and its phases, rollout steps, holds, and metrics. An incomplete plan (migrated from a release policy) cannot start a release or become the default: say so when you name one.

### Choose an environment's release plan

Do this for every environment that needs a plan: for the user's own request, for a flag release plan, and for onboarding in Record only mode.

1. Read the environment's plans. Use only complete plans.
2. **The environment has complete plans.** Propose its default plan, unless the user named another. Show it with its phases, rollout steps, and metrics. Ask header "Plan": "Use this plan" ("Keep it as this environment's default") or "Choose another" (offer the other complete plans, or a starter plan). If the plan the user keeps is not the default yet, record setting it as the default. If another plan is the default now, say that the new one replaces it as the default.
3. **The environment has no complete plan.** Tell the user it needs a release plan first, and offer a starter plan as [Create](#create) says. "Not now" is how the user declines. For a flag release plan, add the environment only after its plan exists (or is recorded, in Record only mode).
4. **The user declines.** Create nothing for that environment. Leave it out of any flag release plan, and say so.

Never invent a release plan key, and never point at an incomplete plan.

### Create

Offer a starter plan so the user does not build one from scratch, or a custom plan. The starter definitions, the checks to run before you offer them, and the custom questions are in [references/environment-release-plans.md](references/environment-release-plans.md):

1. **Randomization unit:** check stored contexts with `search-contexts`. Do not ask the user what reads can answer.
2. **Rollback metrics:** `get-metrics`, keeping metrics whose `analysisUnits` include the unit. Metrics make the plan guarded, and a guarded plan allows at most 50% per step.
3. **Starter:** ask header "Starter plan": "Progressive", "Custom", or "Not now". Show the full plan, and ask "Looks right" or "Adjust it".
4. **Key:** read the environment's plans first. Keys are unique in the project, so if a starter's key is taken anywhere in the project (another environment, or an active plan here), add `-2`, then `-3`, until it is free.
5. Confirm, then `create-environment-release-plan`, then `update-default-environment-release-plan` with `default: true` when it becomes the default.

If the create fails because the randomization unit is not available for guarded rollouts, nothing was written. Offer the same plan with no metrics, and confirm again.

### Make a plan the environment's default

Confirm, naming the plan it replaces. Then `update-default-environment-release-plan` with `releasePlanKey`, `default: true`, and `confirm: true`. The plan must be complete.

### Edit

Read the plan, change only what the user asked, and confirm the change in words. Then `update-environment-release-plan` with only the changed fields. `phases` and `metrics` each replace the whole value, so send every phase or metric to keep. Without the MCP tool, use the REST replace in [references/rest-api.md](references/rest-api.md), which is a full replace with the plan's `version`.

### Delete

There is no MCP tool, so use the REST delete. Confirm first, and say if the plan is the environment's default (the environment then has none). A plan that a flag release plan still names cannot be deleted (409): name the flag release plans that use it, and offer to change them first. To clear only the default, use `update-default-environment-release-plan` with `default: false`.

## Flag release plans

All flag release plan operations use the REST API in [references/rest-api.md](references/rest-api.md). Run each command as its own self-contained call, because shell variables do not carry over between calls.

### How a flag release plan names environment release plans

- Each environment names one environment release plan by key, or releases immediately. The named plan must exist in that environment and be complete, or the request returns 400.
- A flag release plan stores each environment's release plan key, so a later change to that environment's default release plan does not update the flag release plan.
- Environments are in release order. Plans are sequential by default: each environment releases after the one before it. Order non-production before production.
- Each environment's trigger decides what starts its release. Use "when the flag evaluates there" (`flag_eval`) unless the user asks for another. [references/rest-api.md](references/rest-api.md) lists the others and their rules.

### The project's default flag release plan

When auto-releasing knows the change's application, it uses the plans for that application, or the project's default when none is for it. When it does not know the application, every plan is a candidate, and with more than one it asks on the pull request which one to use.

- A new plan can be the default only when the project has no default.
- To change what the default does, edit the default plan in place: same key, still the default. Do not create a second plan unless the user asks for one.
- An update is a full replace. Leaving out the default setting clears it. Always start from a fresh read, and send every field to keep.

### List or show

List the project's plans (page while more remain). For each, report its name, whether it is the default, and its environments in order with the release plan for each ("production: Progressive", or "releases immediately").

### Build or update the project's plan

1. List the project's plans.
2. For each environment the user wants, in release order, choose its environment release plan as in [Choose an environment's release plan](#choose-an-environments-release-plan).
3. Decide:
   - **No default plan:** a new plan "Default release" (key `default-release`, or the next free key), as the project's default.
   - **The default already has these environments, in this order, with these release plans:** reuse it. Nothing to write.
   - **The default does not match:** ask header "Flag release plan": "Update <name> (Recommended)" ("Change its environments and release plans to these. It stays the default") or "Keep <name>" ("Keep using it as it is"). An update keeps the plan's key and its default setting.
4. Confirm, showing the current and the new environments and release plans. Then create, or replace the plan with its `version`.
5. Get the plan by key, and check that its environments, release plans, and default match what was confirmed.

On a 409 for a taken key, use the next free key and confirm again. On a 409 for a stale version, get the plan again, show what changed, and confirm again.

### Make another plan the default, or delete one

- **Default:** get the plan, confirm ("Make Staged rollout the project's default flag release plan? It replaces Fast as the default."), then replace it with every field from the read, the default setting on, and its `version`. List the plans to make sure only this plan is the default.
- **Delete:** confirm, naming the plan and saying if it is the default (the project then has no default). Releases already started from it continue. Then list to make sure it is gone.

### Start a flag's release from a plan

This starts a release that can ship the flag's change to users. Confirm the flag, the plan, and each environment in order with its release plan, then create the flag release from the plan. For a release tied to a pull request, use [`flag-release`](../../feature-flags/flag-release/SKILL.md) instead.

## Write order

Write environment release plans before anything that names them:

1. Metrics to create, with [`launchdarkly-metric-create`](../../metrics/launchdarkly-metric-create/SKILL.md)
2. Environment release plans, then each environment's default
3. The flag release plan that names them

## Errors

| Error | Meaning | What to do |
|-------|---------|------------|
| Validation error (400) | The message says why. For example: a release plan that is unknown, incomplete, or in another environment, the project already has a default flag release plan, a step over 50% in a plan with metrics, or a unit that is not available for guarded rollouts | Tell the user the reason in words, fix the request, and confirm again |
| Unauthorized (401) | The token is missing, wrong, or expired | Follow [Token handling](#token-handling). Do not retry with another value |
| `Plan does not allow this operation` (403) | That kind of release plan is not on the account | Tell the user to contact LaunchDarkly support. Stop |
| Any other 403 | The role cannot do this in the project | Name the change that failed and stop. A member with that permission can make it |
| Not found (404) | The project, environment, flag, or plan does not exist | Check the key with a read. Do not create a plan to work around it |
| Conflict (409) | A taken key, a stale version, or deleting an environment release plan that a flag release plan names | See the workflow for that change |
| Server error (5xx) | LaunchDarkly could not complete it | Report it. Retry a read once. Before you retry a write, read again, because it may have been applied |

Never retry a write in a loop.

## Out of scope

- Turning auto-releasing on or off for a repository: use [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md).
- First-time Release Autopilot setup: use [`launchdarkly-release-autopilot-onboarding`](../launchdarkly-release-autopilot-onboarding/SKILL.md).

## References

- [references/environment-release-plans.md](references/environment-release-plans.md): starter plans, the checks before them, and custom plans
- [references/rest-api.md](references/rest-api.md): REST endpoints, curl commands, fields, and JSON examples for both kinds of plan
- In the LaunchDarkly UI: `/projects/{projectKey}/settings/releases`, with `?tab=flag-release-plans` for flag release plans
- [Guarded rollouts](https://launchdarkly.com/docs/home/releases/guarded-rollouts)
