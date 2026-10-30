# Edge cases

## Edge cases

| Situation | Action |
|-----------|--------|
| Every Release Autopilot tool returns 404 | The account does not have the Release Autopilot add-on enabled. Tell the user and stop |
| Member role is `reader` or `no_access` | Preview mode. End with the plan as a checklist for an admin |
| Member role is `writer` or a custom role | Account writes are marked "needs an admin" and left out of Step 8; repo writes still run |
| A write returns 403 | Report which write failed, list the remaining writes for an admin, and stop |
| `githubConnectUrl` with `flow=install` | Step 3. The user needs a GitHub org owner to install the App |
| Repo not on the install list | Same owner as listed repos: the user grants the App access to it. New owner: an org owner installs the App on that organization. Then list again |
| Mapped repo ID not on the install list | Mapped-repo reads return only repository IDs, so join them to the install list. An ID with no match is a repo the App can no longer see, or one this member cannot see. Show it by ID with its project. Do not change it |
| Repo already mapped to a different project | Do not remap here. The user unmaps it with the settings skill, then maps it in this flow |
| `list-release-plans` returns 403 `Plan does not allow this operation` | Use release policies. Show them and their warnings, create no plans, and keep auto-releasing off for the repo where a policy is missing or incomplete |
| Auto-releasing picked but no metrics exist (release plans) | Offer the metric skills. Without metrics, the plan is progressive and nothing rolls back automatically |
| Incomplete migrated plan | Cannot start a release. Create a complete plan in that environment |
| Generative AI or Vega eligibility error | Release Autopilot's agents need generative AI turned on, and no MCP tool reads that setting. An Admin or Owner selects **Enable generative AI use cases** in Organization settings > Security. Stop |
| Bring your own key chosen | Browser step only. Record it as reported, never as verified |
| No writes needed | Say so, list follow-ups, and stop |

## Existing mappings

| Current mapping | Action |
|-----------------|--------|
| Mapped to the chosen project, effective capabilities match the user's picks | Tell the user it is already set up. Write nothing |
| Mapped to the chosen project, a capability the user did not pick is effectively on | Record a repo override that turns it off, as its own line in Step 7 |
| Mapped to the chosen project, a picked capability is effectively off because of a repo override | Record a repo write that turns it on, plus the account write if the account has it off. Verify the effective value in Step 9 |
| Mapped to a different project | Do not remap. Remapping changes where its flags are created. The user unmaps it with [`launchdarkly-release-autopilot-settings`](../../launchdarkly-release-autopilot-settings/SKILL.md), then maps it in this flow |
