# Approval Workflows

Some LaunchDarkly environments require approval before changes take effect. This is an Enterprise feature configured per environment. When this happens, mutation tools like `toggle-flag`, `update-rollout`, `update-targeting-rules`, `update-flag-targeting`, and `copy-flag-config` return `requiresApproval: true` instead of making the change directly.

The [`launchdarkly-approval-requests`](../../launchdarkly-approval-requests/SKILL.md) skill covers the whole flow: creating the request, choosing reviewers, handing the review to a person, checking the outcome, and applying an approved request only when the user asks. Load it when a change is blocked. This page covers only what a targeting tool returns.

## Detecting Approval Requirements

Any mutation tool response may include these fields when a change is blocked:

- `requiresApproval: true`: the change was blocked and needs approval
- `environmentKey`: the environment that requires approval
- `message`: a human-readable explanation
- `instructions`: the semantic patch instructions that were attempted. Pass these unchanged to `create-approval-request`.

## What the Agent Should NOT Do

- **Do NOT retry the direct change**: If a change was blocked, retrying the same mutation will also be blocked.
- **Do NOT skip informing the user**: Always tell the user that approval is required and what the next steps are.
- **Do NOT approve, decline, or bypass**: A person approves every request. Never use workarounds or alternative API calls to skip approval.
