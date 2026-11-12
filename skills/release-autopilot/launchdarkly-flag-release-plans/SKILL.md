---
name: launchdarkly-flag-release-plans
description: "List, create, change, make default, and delete a LaunchDarkly project's flag release plans through the REST API (beta), and start a flag's release from one. A flag release plan sets the order of a project's environments and the environment release plan each one releases with. Auto-releasing proposes releases from these plans. Use when the user wants to see or build a project's flag release plan, point it at environment release plans, change the project's default plan, or start a release from a plan. For first-time Release Autopilot setup, use launchdarkly-release-autopilot-onboarding."
license: Apache-2.0
compatibility: Requires curl and a LaunchDarkly API access token in LD_ACCESS_TOKEN. The hosted MCP server has no flag release plan tools, and ldcli has no command for them.
metadata:
  author: launchdarkly
  version: "0.1.0-experimental"
---

# LaunchDarkly Flag Release Plans

You're using a skill that reads and changes a project's flag release plans through the LaunchDarkly REST API. A flag release plan is a project-level plan. It lists the project's environments in release order, and for each environment it names the environment release plan that releases the flag there, or says that the environment releases immediately. Auto-releasing proposes each new release from these plans, so treat every write as production automation with a blast radius.

## Prerequisites

- **curl**, and a shell tool that can run it.
- **An API access token** in the `LD_ACCESS_TOKEN` environment variable of the shell you run commands in. `ldcli` reads the same variable. The token's role needs the create, update, or delete flag release plan action in the project for writes, and the create flag release action to start a release. Reads need access to view the project.
- **Optional:** `LD_BASE_URI` for an instance other than `https://app.launchdarkly.com` (ldcli reads it too).

The hosted LaunchDarkly MCP server has no flag release plan tools. `ldcli` (3.16.0) has no command for these endpoints and no command that sends a raw request with the `LD-API-Version: beta` header, so use curl with the commands in [references/api.md](references/api.md). Every request sends `LD-API-Version: beta`.

## Token handling

1. **Never ask for the token in the chat**, and never accept one there. If the user pastes a token, do not use it. Tell them to delete that token in **Organization settings > Authorization** and make a new one, because the chat may keep it.
2. **Never print, echo, or log the token.** Check only that it is set:

   ```sh
   if [ -n "${LD_ACCESS_TOKEN:-}" ]; then echo "LD_ACCESS_TOKEN is set"; else echo "LD_ACCESS_TOKEN is not set"; fi
   ```

   Do not run `env`, `printenv`, `set`, `ldcli config --list`, or `curl -v`; each one can show the token. Do not read ldcli's config file.
3. **If it is not set**, tell the user to create a token in **Organization settings > Authorization** and export it in their own terminal, not in the chat: `export LD_ACCESS_TOKEN=<token>`. A user who signed in with `ldcli login` exports the same token. The agent's shell gets the variable only when the agent starts after the export, so offer two options: restart the agent from that terminal, or run the commands from [references/api.md](references/api.md) themselves.
4. **If you cannot run shell commands**, give the user the exact commands to run, filled in with their keys, and stop.

## How a plan points at environment release plans

- Each environment in `environments` names one environment release plan by key, with `environmentReleasePlanKey`, or sets `isImmediate: true` to release at once with no plan. One of the two is required.
- The named plan must exist in that environment and be complete. An incomplete plan, a plan in another environment, or an unknown key returns 400.
- The flag release plan stores the key, not "the environment's default". If the environment's default plan changes later, the flag release plan keeps the old key until someone updates it.
- `environments` is in release order. Plans are `sequential` by default: each environment releases after the one before it. `parallel` releases them at the same time.
- `triggerType` decides what starts each environment's release: `flag_eval` (the flag evaluates there, usually after a deploy), `webhook` (a CI/CD deploy signal), `manual` (a person starts it), or `promotion` (the environment before it finished). `manual` and `promotion` need `sequential`, and the first environment cannot use `promotion`. Use `flag_eval` unless the user asks for another.

## The project's default plan

A project has at most one default flag release plan (`isDefault`). When auto-releasing knows the change's application, it uses the plans whose `applicationKeys` include it, or the project's default when no plan does. When it does not know the application, every plan is a candidate, and with more than one it asks on the pull request which plan to use. So a project with one plan, or one default and no others, never makes it ask.

- **Create as the default:** send `isDefault: true` only when the project has no default. Otherwise the create returns 400.
- **Replace the default:** create the new plan without `isDefault`, then update it with `isDefault: true`. That update demotes the current default.
- **Update is a full replace.** Omitting `isDefault` from an update clears it. Always start an update from a fresh read of the plan and send every field you want to keep.

## Core Principles

1. **Read before you write.** List the project's plans first. Reuse a plan that already does what the user wants.
2. **Confirm before every write.** State the current and proposed plan in words (environments in order, the release plan for each, and whether it becomes the project's default). Then ask header "Confirm" with "Make this change" and "Cancel". Write only after "Make this change" in this turn. A detailed request is not approval, and neither is a yes from an earlier turn.
3. **Read-only requests stay read-only.** For "show", "preview", "what would you change", or a dry run, make only GET requests, and list the writes you would make. Do not ask for confirmation.
4. **Only touch what the user named.** Never delete or demote a plan the user did not name.
5. **Speak in product words.** Say "flag release plan", "release plan", "default", and environment names. Do not show field names, HTTP status codes, or JSON to the user, except inside a command the user runs.

## Workflows

The commands for each request are in [references/api.md](references/api.md). Fill in the keys, and run each command as its own self-contained call: shell variables do not carry over between calls.

### List or show plans

List the project's plans (page with `offset` while more remain). For each plan, report its name, whether it is the default, and its environments in order with the release plan for each ("production: Progressive", or "releases immediately"). To show one plan, get it by key.

### Create a plan

1. List the project's plans. Note the default and any plan with the same environments.
2. For each environment, find the release plan to use. Read the environment's release plans with the `get-environment-release-plans` MCP tool if it is available, or the environment release plan endpoint in [references/api.md](references/api.md). Use the environment's default plan unless the user names another. An environment with no complete plan needs one first: create it with [`launchdarkly-release-autopilot-onboarding`](../launchdarkly-release-autopilot-onboarding/SKILL.md)'s release plan steps or in the LaunchDarkly UI, or release it immediately if the user asks.
3. Ask for anything the request does not answer: the environments and their order (non-production before production), and whether the plan becomes the project's default. Suggest the default when the project has none.
4. Choose a key from the name, such as `default-release`. If the key is taken, add `-2`, then `-3`, until it is free.
5. Confirm (Core Principle 2), then create it. When it must replace an existing default, create it without `isDefault`, then update it with `isDefault: true`, and say in the confirmation which default it replaces.
6. Get the plan by key and check that its environments, release plans, and default match what was confirmed.

### Change a plan

Get the plan, change only what the user asked, confirm, and send the full plan with an update, including `version` from the read. On a version conflict, get the plan again, show what changed, and confirm again.

### Make a plan the project's default

Get the plan. If it is already the default, say so and stop. Otherwise confirm ("Make Default release the project's default flag release plan? It replaces Staged rollout as the default."), then update it with every field from the read, `isDefault: true`, and `version`. Verify with a list: only this plan is the default.

### Delete a plan

Confirm, naming the plan and saying if it is the default (the project then has no default). Releases already started from it continue. Delete it, then list to verify.

### Start a flag's release from a plan

This starts a release that can ship the flag's change to users. Confirm the flag, the plan, and each environment in order with its release plan, then create the flag release with `kind: "plan"`. For a release tied to a pull request, use [`flag-release`](../../feature-flags/flag-release/SKILL.md) instead.

## Errors

| Status | Meaning | What to do |
|--------|---------|------------|
| 400 | Invalid request. The message says why: an unknown, incomplete, or wrong-environment release plan; a missing release plan for an environment that is not immediate; the project already has a default; 100 plans already; `promotion` on the first environment | Tell the user the reason in words, fix the request, and confirm again before you retry |
| 401 | The token is missing, wrong, or expired | Follow [Token handling](#token-handling). Do not retry with another value |
| 403 `Plan does not allow this operation` | Flag release plans are not turned on for this account | Tell the user to contact LaunchDarkly support. Stop |
| 403, any other message | The token's role cannot do this in the project | Name the action that failed and stop. A member with that permission can run the same command |
| 404 | The project, flag, or plan key does not exist | Check the key with a list. Do not create a plan to work around it |
| 409 on create | Another active plan has this key | Pick the next free key (`-2`, `-3`), confirm again, and retry |
| 409 on update | The plan changed after you read it | Get it again, show what changed, and confirm again |
| 5xx | LaunchDarkly could not complete the request | Report it. Retry a read once. Do not retry a write before you read the plans again, because it may have been applied |

Never retry a write in a loop.

## Out of scope

- Creating or changing environment release plans: use [`launchdarkly-release-autopilot-onboarding`](../launchdarkly-release-autopilot-onboarding/SKILL.md) or the LaunchDarkly UI.
- Turning auto-releasing on or off for a repository: use [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md).

## References

- [references/api.md](references/api.md): the endpoints, curl commands, fields, and JSON examples
- The project's flag release plans in the LaunchDarkly UI: `/projects/{projectKey}/settings/releases?tab=flag-release-plans`
