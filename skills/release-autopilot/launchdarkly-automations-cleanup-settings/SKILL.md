---
name: launchdarkly-automations-cleanup-settings
description: "Read and change a LaunchDarkly project's Automations auto-cleanup settings via the hosted MCP. Auto-cleanup runs on a schedule and opens pull requests that remove the code for flags that are ready. Use when the user wants to turn automated flag cleanup on or off, change its schedule, repositories, flag states, job limit, or agent instructions, see which flags the next run will pick up, or asks why cleanup did not open a pull request. For first-time setup of every Release Autopilot capability, use launchdarkly-release-autopilot-onboarding."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "0.1.0-experimental"
---

# LaunchDarkly Automations Auto-cleanup Settings

You're using a skill that reads and changes a project's auto-cleanup settings, from the "Automated flag cleanup" section of the project's **Settings > Automations** page. Auto-cleanup opens pull requests in the user's GitHub repositories on a schedule. Treat every write as production automation with a blast radius.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server.

**Required MCP tools:**
- `get-automations` with `section: "cleanup"` and `projectKey`: the project's cleanup `settings`, the `upcoming` run (`enabled`, `flagKeys`, `nextRunAt` in Unix milliseconds), and `automationsPage`, the link to the project's Automations page.
- `update-automations` with `projectKey` and a `cleanup` object: change one or more settings. Omitted fields keep their stored values. Send `cleanup` on its own, without `accountWide`, `repo`, or `archival`.

**Optional:** `get-projects` to pick the project, `get-automations` to suggest the repositories already mapped to the project.

If `get-automations` has no `section` argument, or rejects `section`, the server has not picked up cleanup and archival yet. Ask the user to reconnect the LaunchDarkly MCP server once. If it still has none, guide the browser steps in [references/browser-steps.md](references/browser-steps.md) instead. Do not invent REST calls.

## What the settings mean

| Field | Meaning |
|-------|---------|
| `schedule` | `disabled` (off), `daily`, `weekly`, or `monthly` |
| `repositories` | GitHub repositories (`owner/name`) cleanup opens pull requests in |
| `maxJobsPerRun` | The most cleanup pull requests one run opens |
| `flagStates` | Which flags runs pick up: `readyToArchive` (the default), `readyForCodeRemoval`, `live` |
| `customContext` | Extra instructions for the cleanup agent, such as where flags are defined. The agent also follows the repository's `AGENTS.md` |
| `retryAttempted` | `true` retries flags that already had a cleanup pull request |
| `configuredByMemberId` | The member whose permissions cleanup jobs use. Read-only: it becomes whoever saves the settings |

## Core Principles

1. **Confirm before every write.** State the current and proposed values, wait for a yes that names the change in this turn, then write. A yes from an earlier turn, or a vague "go ahead", is not enough.
2. **Saving changes who cleanup runs as.** Every cleanup save with `update-automations` makes the calling member the one whose permissions cleanup jobs use. Say so in the proposal when `configuredByMemberId` is someone else.
3. **Lists replace.** `repositories` and `flagStates` replace the whole stored list. To add one repository, read the current list and send it with the new one. To remove one, send the list without it.
4. **Least privilege.** Only add repositories the user named. Never add every repository on the GitHub App install. Keep `flagStates` at `readyToArchive` unless the user asks for more: `live` picks up flags that are still serving.
5. **Turning it on starts pull requests.** Any schedule other than `disabled` makes LaunchDarkly open pull requests in the listed repositories, starting with the next run. A schedule with no repositories opens none.

## Workflows

### Read the settings

`get-automations` with `section: "cleanup"` and `projectKey`. Report the schedule, repositories, job limit, flag states, and who cleanup runs as. If `upcoming.enabled` is true, say when the next run is (`nextRunAt`) and which flags it will pick up (`upcoming.flagKeys`).

### Turn it on or change it

1. Read the settings: `get-automations` with `section: "cleanup"`.
2. Ask for anything the change needs and the user did not give: the schedule, and at least one repository when none is stored. Suggest the repositories mapped to the project in `get-automations`. Only the user's answer goes in.
3. Propose the change, for example:

   > Automated flag cleanup is off for project `default`. Turn it on weekly in `acme/web`, with at most 10 pull requests per run? LaunchDarkly will start opening pull requests that remove the code for flags that are ready to archive. Cleanup jobs will run with your permissions.

4. After the user confirms, call `update-automations` with `projectKey`, `confirm: true`, and a `cleanup` object holding only the confirmed fields.
5. The response lists `changed` and the `settings` as read back. If it reports a mismatch on read-back, show the user the current values from `get-automations` with `section: "cleanup"` and do not retry blindly.

### Turn it off

Propose it ("Turn off automated flag cleanup for project `default`? No new cleanup pull requests will open; open ones stay open."), then `update-automations` with `projectKey`, `cleanup: { "schedule": "disabled" }`, and `confirm: true`.

### Why didn't cleanup open a pull request?

Read-only. Call `get-automations` with `section: "cleanup"` and check in this order. Stop at the first answer.

1. `settings.schedule` is `disabled`: cleanup is off.
2. `settings.repositories` is empty: there is nowhere to open pull requests.
3. `upcoming.enabled` is false while the schedule is on: no member is set to run cleanup, or that member is no longer on the account. Someone with access must save the settings again, which makes them the member cleanup runs as.
4. The flag is not in `upcoming.flagKeys`: its state is not in `flagStates`, the run limit (`maxJobsPerRun`) is full, or it already had a cleanup pull request and `retryAttempted` is false.
5. The flag is in `upcoming.flagKeys`: it is waiting for the next run at `nextRunAt`.

If none of these explain it, point the user at the cleanup history in the "Automated flag cleanup" section of `automationsPage`. Do not change settings to try something.

## Errors

- **403:** the member lacks permission to update the project's lifecycle settings, or to view the project. Say which, and stop.
- **No `section` argument:** see [Prerequisites](#prerequisites).

## Out of scope

- Running a cleanup now, and reviewing cleanup history: both are in the "Automated flag cleanup" section of the Automations page.
- Removing one flag's code by hand: use [`launchdarkly-flag-cleanup`](../../feature-flags/launchdarkly-flag-cleanup/SKILL.md).
- Auto-archival: use [`launchdarkly-automations-archival-settings`](../launchdarkly-automations-archival-settings/SKILL.md).
- Auto-flagging and auto-releasing: use [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md).

## References

- [references/browser-steps.md](references/browser-steps.md): the same settings in the browser, for servers without these tools
- [Automated flag cleanup docs](https://launchdarkly.com/docs/home/flags/manage/flag-cleanup-vega#automated-flag-cleanup)
