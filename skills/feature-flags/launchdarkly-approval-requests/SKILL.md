---
name: launchdarkly-approval-requests
description: "Request, follow up on, and apply LaunchDarkly approval requests for flag, segment, and AgentControl Config changes. Use when a change needs approval, when the user asks whether a request was approved or declined, which requests are waiting on them, or to apply an approved request. The agent never approves or declines a request."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "0.1.1"
---

# LaunchDarkly Approval Requests

You're using a skill that takes a change through LaunchDarkly approvals: request it, hand the review to a person, check the outcome when asked, and apply it once it is approved. A person approves or declines every request in LaunchDarkly. You never do either.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server.

| Resource | Request | Check | Apply |
|---|---|---|---|
| Flag or segment | `create-approval-request` | `get-approval-requests` | `apply-approval-request` |
| AgentControl Config | `create-agent-config-approval` | `get-agent-config-approvals` | `apply-agent-config-approval` |

`get-approval-requests` with only `id` returns any request, including one for an AgentControl Config, so you never need to ask which kind of request an id belongs to.

## Core Principles

1. **A person decides.** Approving and declining happen in LaunchDarkly, by a reviewer. Never approve, never decline, and never look for another way to make a blocked change.
2. **Reviewers come from the user.** Pass only reviewers the user named, in `notifyMemberIds` and `notifyTeamKeys`. Never pick one yourself. If the tool rejects the reviewers, ask the user who should review, then call it again.
3. **Hand off, then wait.** After you create a request, the next step is the user's. Do not poll for the outcome.
4. **Apply only what is approved.** Apply a request only when its `reviewStatus` is `approved`, and only when the user asks for it.

## Workflow

### 1. Request the change

Usually a write tool reports that the environment requires approval and returns the instructions it tried. Create the request with those same instructions and a description of what the change does.

- **Reviewers.** The create tool checks whether the environment requires a reviewer. A flag needs one when its environment requires approval for flag changes. A segment always needs one. If the user named no reviewer and the tool says one is required, ask the user who should review.
- **Approval integrations.** When an integration such as ServiceNow runs the review, it takes no LaunchDarkly reviewers. Pass its form fields in `integrationConfig` instead.
- **Self-review.** When requesters cannot review their own requests, the user cannot be a reviewer on their request.
- **AgentControl Configs.** Without `env`, the request covers every environment, and LaunchDarkly applies the project's strictest approval settings.

### 2. Hand the review to the user

The create result includes `approvalRequest.url`. Open it in the user's browser when your client can, for example with `open`, `xdg-open`, or a browser tool. Show the link in your reply either way. Tell the user who was asked to review, and that you will check the outcome when they tell you the request has been reviewed.

Stop there. Do not call the check tool in a loop while you wait.

### 3. Check the outcome when the user asks

Call the check tool once, with the request's `id`. The `id` from the create result is enough on its own, and any key you pass with it must match the request's resource.

Each request has two states. Report both:

| Field | Meaning | Values |
|---|---|---|
| `reviewStatus` | the reviewers' decision | `pending`, `approved`, `declined` |
| `status` | the change itself | `pending`, `scheduled`, `completed` (applied), `failed` |

Each request lists its reviews with `kind`, `comment`, `creationDate`, and the `memberId` or `serviceTokenId` that left it. When a request is declined, give the reviewer and their reason.

For an integration-managed approval with auto-apply on, LaunchDarkly can apply the request itself once it is approved, so the one read can already show `status` as `scheduled` or `completed`. Do not read again to find out, and do not apply a request that is no longer `pending`.

### 4. Apply an approved request

When the user asks you to apply a request:

- `reviewStatus` is `approved` and `status` is `pending`: apply it with `confirm: true` and an optional comment. The flag and segment tool takes `projectKey` and `id`. The AgentControl Config tool takes only `id`.
- `reviewStatus` is `pending` or `declined`: do not apply it. Tell the user where it stands.
- `status` is already `completed` or `scheduled`: nothing is left to apply. Say so.
- `status` is `failed`: the change did not go live. Tell the user the apply failed and give the request's `description`. Do not apply it again unless the user asks.

An applied request with `scheduled: true` is not live until its `executionDate`. Say when it takes effect.

The apply tool reads the request back and returns `applied`. Report the change as live only when `applied` is `true` and you have read the resource back (`get-flags`, `get-segments`, or `get-agent-configs`) to confirm it.

When `applied` is `false` and there is no `scheduled: true`, the change is not confirmed. Say that, repeat the `message`, and do not call the apply tool again. Two cases return it: LaunchDarkly accepted the apply but the read-back failed, or the read-back shows a `status` other than `completed`. Call the check tool once and report the `status`, then leave the next step to the user.

## Finding requests

- **One flag or segment:** `get-approval-requests` with `projectKey`, `env`, and `flagKey` or `segmentKey` (never both).
- **Waiting on the user:** call `get-member-self`, then `get-approval-requests` with `projectKey`, `assignedToMemberIds` set to that id, and `reviewStatus: ["pending"]`. That filter finds only requests sent to the user by member id, so also list the project's pending requests without `assignedToMemberIds` and add each one whose `notifyTeamKeys` holds a team key from `get-member-self`'s `teams`. Combine the two lists without repeating a request `id`, and say that the result includes requests sent to the user's teams.
- **The whole project:** `get-approval-requests` with only `projectKey` lists what the project's Approvals page shows, across flags, segments, and AgentControl Configs, newest first. Narrow it by `env`, `requestedByMemberId`, `resourceKind`, `status`, or `reviewStatus`. The list is paged (20 by default, up to 200). While `nextOffset` is set, call again with it as `offset`. Read every page before you report the list as complete.
- **One AgentControl Config:** `get-agent-config-approvals` with `projectKey` and `configKey`.

Timestamps in results are UTC.

## What not to do

- Do not approve or decline a request, or ask the user for permission to do so.
- Do not retry a blocked write in the hope that it goes through.
- Do not choose reviewers the user did not name.
- Do not check the outcome repeatedly while waiting for a reviewer.
