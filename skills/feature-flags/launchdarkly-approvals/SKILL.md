---
name: launchdarkly-approvals
description: "Handle LaunchDarkly approval requests when a flag, segment, or AgentControl Config change needs approval: create the request, open its link so a human can approve or decline, check the outcome, and apply it once approved. Use when a write returns 'Blocked: approval is required', or when the user asks to request, check on, or apply an approval."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# LaunchDarkly Approvals

You're using a skill that will guide you through a change that needs approval. Your job is to submit the change for review, put the request in front of a human reviewer, find out whether they approved or declined it, and apply it only once it is approved.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Required MCP tools:**
- `create-approval-request`: submit a flag or segment change for review
- `list-approval-requests`: list a flag's or segment's requests in one environment, or pass `id` to read one request with its decision and `reviews`
- `apply-approval-request`: apply an approved flag or segment request

**Optional MCP tools:**
- `get-environment`: read an environment's approval settings
- `create-agent-config-approval`, `list-agent-config-approvals`, `apply-agent-config-approval`: the same workflow for AgentControl Configs

## Core Principles

1. **A human decides.** No tool approves or declines a request, and you must not look for another way to. Reviewers decide in LaunchDarkly.
2. **Open the link for the human.** Every created or listed request has a `url`. Open it in the user's browser when your client can, and always show the link.
3. **Check when told, not in a loop.** Read the request once the user says it has been reviewed, or once when you resume the task. Do not poll.
4. **Apply only what was approved.** A declined or pending request is reported, not applied. A scheduled apply is not live yet.
5. **Resubmit blocked changes unchanged.** A blocked write already contains the exact instructions to submit.

## Workflow

### Step 1: Know whether approval applies

A blocked write tells you, so this step is optional. To check ahead of a write, call `get-environment` and read:

- `approvalSettings` for flags: `required`, `minNumApprovals`, `canReviewOwnRequest`, `canApplyDeclinedChanges`, `requiredApprovalTags`
- `resourceApprovalSettings.segment` and `resourceApprovalSettings.aiconfig` for other kinds

If `canReviewOwnRequest` is false, someone other than the requester must review.

### Step 2: Create the request

When a write tool returns an error that starts with `Blocked: approval is required`, nothing was applied. Do not retry the write. The message names the tool to use and the instructions to pass:

```
Tool: create-approval-request
Input:
  projectKey: "my-project"
  flagKey: "new-checkout"        # or segmentKey for a segment, never both
  env: "production"
  instructions: [{"kind": "turnFlagOn"}]   # copied unchanged from the blocked message
  description: "Enable new checkout in production"
```

- Segment requests need at least one reviewer in `notifyMemberIds` or `notifyTeamKeys`. Flag requests take reviewers only when the user names them.
- AgentControl Config changes use `create-agent-config-approval` with `configKey` and at least one reviewer.
- If the message says no tool submits this approval, ask the user to request approval in LaunchDarkly.

### Step 3: Hand the request to a human

The result has `approvalRequest.id` and `approvalRequest.url`.

1. Open the url in the user's browser when your client can: `open <url>` on macOS, `xdg-open <url>` on Linux, `start "" "<url>"` on Windows, or a browser tool.
2. Show the link and the request id either way.
3. Tell the user who can review. Mention `minNumApprovals`, and mention that the requester cannot review their own request when `canReviewOwnRequest` is false.
4. Ask the user to tell you when the request has been reviewed.

### Step 4: Detect the outcome

When the user says the request was reviewed, read it once by id:

```
Tool: list-approval-requests
Input:
  id: "<approval-request-id>"
```

The id from create is enough on its own. If you also pass `projectKey`, `env`, and `flagKey` or `segmentKey`, they must match the request's resource. For an AgentControl Config, call `list-agent-config-approvals` with `id`. A `status` filter still applies to `list-approval-requests`, so omit it when you read by id.

The result holds that one request in the usual item shape. Its `reviews` list each review's `kind` and `comment`.

| `reviewStatus` | `status` | What to do |
|---|---|---|
| `approved` | `pending` | Offer to apply it (Step 5), or apply it if the user already asked |
| `declined` | any | Report the decline and the reviewer's `comment` from `reviews`. Do not apply |
| `pending` | `pending` | Not reviewed yet. Say so and share the url again; check again only when the user asks |
| any | `completed` | Already applied. Verify the resource (for a flag, `get-flags` with `flagKey`) |
| any | `scheduled` | Applied on a schedule; not live yet. Do not report it as live |
| any | `failed` | Applying failed. Report it and point the user to the url |

`reviewStatus` can stay `pending` after one approval when the environment needs more than one (`minNumApprovals`).

For integration-managed approvals with auto-apply on, reading the request can make LaunchDarkly apply it once approved. Read `status` from the result rather than assuming the change is still pending.

### Step 5: Apply an approved request

Apply only when `reviewStatus` is `approved` and the user wants the change made now.

```
Tool: apply-approval-request
Input:
  projectKey: "my-project"
  id: "<approval-request-id>"
  confirm: true
```

The tool reads the request back before it reports:

- `applied: true`: the change is live. Verify it, for a flag with `get-flags` and `flagKey`.
- `scheduled: true`: the change runs at `executionDate`. Do not report it as live.
- `applied: false` with a `message`: the change did not apply. Report the message.

## Finding a request later

If you no longer have the id, call `list-approval-requests` with `projectKey`, `env`, and `flagKey` or `segmentKey`. Pass `status: ["pending"]` for open requests, or `["completed"]` for applied ones. Each item has `id`, `status`, `reviewStatus`, `url`, and `reviews`. For an AgentControl Config, call `list-agent-config-approvals` with `projectKey` and `configKey`.

## What not to do

- Do not try to approve or decline a request, and do not use API workarounds to skip review.
- Do not retry a blocked write.
- Do not read the request repeatedly while waiting for a reviewer.
- Do not apply a declined or pending request.
- Do not report a scheduled change as live.

## Related

- [Flag targeting](../launchdarkly-flag-targeting/SKILL.md): the flag changes that most often need approval
