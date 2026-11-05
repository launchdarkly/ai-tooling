---
name: launchdarkly-automations-archival-settings
description: "Read and change a LaunchDarkly project's Automations auto-archival settings via the hosted MCP. Auto-archival archives flags that are ready to archive after a grace period, or creates approval requests for them. Use when the user wants to see or change the grace period, approval requirement, run limit, recheck cadence, or notification recipients, turn automatic archival off or on, or asks why a flag was or was not archived automatically. For first-time setup of every Release Autopilot capability, use launchdarkly-release-autopilot-onboarding."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "0.1.0-experimental"
---

# LaunchDarkly Automations Auto-archival Settings

You're using a skill that reads and changes a project's auto-archival settings, from the "Automatic archival" section of the project's **Settings > Automations** page. Auto-archival archives flags without a person in the loop unless approvals are required. Treat every write as production automation with a blast radius.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server.

**Required MCP tools:**
- `get-automations-archival`: the project's archival `settings` and `automationsPage`, the link to the project's Automations page.
- `update-automations-archival`: change one or more settings, or turn archival off. Omitted fields keep their stored values. It cannot turn archival on (see [Turn it on](#turn-it-on)).

**Optional:** `get-projects` to pick the project, `search-members` to resolve notification member IDs (team keys come from the user), `get-approval-requests` for pending archival approvals.

If these tools are missing, the server has not picked them up yet. Ask the user to reconnect the LaunchDarkly MCP server once. If they are still missing, guide the browser steps in [references/browser-steps.md](references/browser-steps.md) instead. Do not invent REST calls.

If a call fails with "automatic archival is not available for this account yet", the account does not have the feature. Tell the user and stop; do not retry or try other tools.

## What the settings mean

Durations are in seconds. Show them to the user in hours or days.

| Field | Meaning |
|-------|---------|
| `enabled` | Whether automatic archival runs for the project |
| `graceSeconds` | How long a flag that is ready to archive waits before it is archived: 1 hour (3600) to 30 days (2592000) |
| `requireApproval` | `true` creates an approval request for each flag instead of archiving it directly |
| `maxArchivalsPerRun` | The most flags one run archives (1 to 100) |
| `watchCadenceSeconds` | How often watched flags are rechecked for a status change: 1 minute (60) to 7 days (604800) |
| `notifyMemberIds`, `notifyTeamKeys` | Fallback members and teams notified about archival activity. They are not owners: flags with no maintainer are never archived automatically |
| `configuredByMemberId`, `riskAcknowledgedAtSeconds` | Read-only: who last saved the settings, and when someone confirmed the risk to turn archival on |

## Core Principles

1. **Confirm before every write.** State the current and proposed values, wait for a yes that names the change in this turn, then write. A yes from an earlier turn, or a vague "go ahead", is not enough.
2. **Only a person can turn it on.** Turning archival on requires confirming its risk on the Automations page. Never claim you turned it on.
3. **Keep approvals unless asked.** Never set `requireApproval` to false unless the user explicitly asked to archive without approvals. Say that flags will then be archived without review.
4. **Lists replace.** `notifyMemberIds` and `notifyTeamKeys` replace the whole stored list. To add one recipient, read the current list and send it with the new one.
5. **Shorter means sooner.** Lowering `graceSeconds` or raising `maxArchivalsPerRun` archives more flags sooner. Say so in the proposal.

## Workflows

### Read the settings

`get-automations-archival` with `projectKey`. Report whether it is on, the grace period, whether approvals are required, the run limit, and the notification recipients.

### Change a setting

1. Read the settings with `get-automations-archival`.
2. Propose the change, for example:

   > Automatic archival in project `default` waits 1 day before archiving a ready flag. Change it to 7 days? Ready flags will stay unarchived for a week before they are archived.

3. After the user confirms, call `update-automations-archival` with `projectKey`, `confirm: true`, and only the confirmed fields.
4. The response lists `changed` and the `settings` as read back. If it reports a mismatch, or says the settings changed after they were read, show the user the current values from `get-automations-archival` and ask again before retrying.

Settings can be changed while archival is off, so a user can set them before a person turns it on.

### Turn it off

Propose it ("Turn off automatic archival for project `default`? No more flags will be archived automatically; flags already archived stay archived."), then `update-automations-archival` with `enabled: false` and `confirm: true`.

### Turn it on

The agent cannot turn archival on. If the user asks:

1. Read the settings with `get-automations-archival`, and set any other settings they asked for first (see [Change a setting](#change-a-setting)).
2. Give the user `automationsPage`. In the "Automatic archival" section, they turn on **Enable automatic archival** and confirm the "Enable automatic archival?" dialog. Turning it on requires permission to archive every flag in the project.
3. When they say it is done, call `get-automations-archival` once and report whether `enabled` is true. Do not poll.

If `update-automations-archival` returns `applied: false` with a `nextStep`, nothing changed: follow these steps.

### Why was (or wasn't) a flag archived automatically?

Read-only. Call `get-automations-archival` and check:

1. `enabled` is false: archival is off for the project.
2. The flag has no maintainer: flags with no maintainer are never archived automatically.
3. The flag is not ready to archive, or became ready less than `graceSeconds` ago.
4. `requireApproval` is true: look for a pending approval request with `get-approval-requests`.
5. More flags were ready than `maxArchivalsPerRun`: the rest wait for a later run.

Flags archived this way get the `auto-archived` tag. "View auto-archived flags" on the Automations page lists them. Do not change settings to try something.

## Errors

- **"automatic archival is not available for this account yet":** see [Prerequisites](#prerequisites).
- **403 on a write:** the member lacks permission to update the project's lifecycle settings. Say so, and stop.

## Out of scope

- Archiving or restoring one flag: use the flag tools.
- Auto-cleanup: use [`launchdarkly-automations-cleanup-settings`](../launchdarkly-automations-cleanup-settings/SKILL.md).
- Auto-flagging and auto-releasing: use [`launchdarkly-release-autopilot-settings`](../launchdarkly-release-autopilot-settings/SKILL.md).

## References

- [references/browser-steps.md](references/browser-steps.md): the same settings in the browser, for servers without these tools
