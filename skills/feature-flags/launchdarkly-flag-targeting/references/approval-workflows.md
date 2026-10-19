# Approval Workflows

Some LaunchDarkly environments require approval before a change takes effect. When that applies, a write tool such as `toggle-flag`, `update-rollout`, `update-targeting-rules`, or `copy-flag-config` makes no change and returns an error that starts with `Blocked: approval is required`.

The full workflow lives in the [approvals skill](../../launchdarkly-approvals/SKILL.md). Load it with `load-skill` (key `feature-flags/launchdarkly-approvals`) before continuing. In short:

1. **Do not retry the write.** The block message names the tool to use, usually `create-approval-request`, and the instructions to pass unchanged.
2. **Create the request** with the same `projectKey`, `flagKey`, `env`, and `instructions`, plus a clear `description`.
3. **Hand it to a human.** The result's `approvalRequest.url` opens the request in LaunchDarkly. Open it in the user's browser when your client can, and always show the link. You cannot approve or decline it.
4. **Check the outcome** with `get-approval-request` once the user says it has been reviewed, not in a loop. `reviewStatus` is `pending`, `approved`, or `declined`; `status` is `pending`, `scheduled`, `completed`, or `failed`.
5. **Apply only an approved request** with `apply-approval-request`. If the result has `scheduled: true`, the change is not live until `executionDate`. After `applied: true`, verify with `get-flag`.
