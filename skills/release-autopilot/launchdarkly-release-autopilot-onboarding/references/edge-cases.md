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
| `get-environment-release-plans` returns 403 `Plan does not allow this operation` | Release plans are not available on the account. Tell the user to contact LaunchDarkly support. Stop release setup for that project, create no plans, and keep auto-releasing off for its repos |
| A release plan tool (`get-environment-release-plans`, `create-environment-release-plan`, `update-default-environment-release-plan`) is not on the server | The MCP server is out of date, not the account. Tell the user to update or reconnect the LaunchDarkly MCP server. Skip release setup, keep auto-releasing off for every repo, list it as a follow-up, and continue with the other capabilities |
| A flag release plan tool (`get-flag-release-plans`, `create-flag-release-plan`, `update-flag-release-plan`) is not on the server | The tools are still reaching accounts. Keep release setup, and use the user-run commands for the flag release plan. Do not say that the account lacks flag release plans, and do not send the user to support |
| The flag release plan list holds only `default-release-configuration` | The built-in plan. The project has no flag release plans yet, so record a new "Default release" plan as the project's default |
| Auto-releasing picked but no metrics exist (release plans) | Offer the metric skills. Without metrics, the plan is progressive and nothing rolls back automatically |
| Incomplete migrated plan | Cannot start a release. Create a complete plan in that environment |
| Generative AI or Vega eligibility error | Release Autopilot's agents need generative AI turned on, and no MCP tool reads that setting. An Admin or Owner selects **Enable generative AI use cases** in Organization settings > Security. Stop |
| Environment has no release plans | Offer a starter plan with [`launchdarkly-release-plans`](../../launchdarkly-release-plans/SKILL.md#create) and make it the environment's default |
| Bring your own key chosen | Browser step only. Record it as reported, never as verified |
| No writes and no browser steps needed | Say so, list follow-ups, and stop. A plan with only browser steps or auto-cleanup settings still goes through the Step 7 confirmation and the Step 8 browser steps |

## Existing mappings

| Current mapping | Action |
|-----------------|--------|
| Mapped to the chosen project, effective capabilities match the user's picks | Tell the user it is already set up. Write nothing |
| Mapped to the chosen project, a capability the user did not pick is effectively on | Record a repo override that turns it off, as its own line in Step 7 |
| Mapped to the chosen project, a picked capability is effectively off because the repo turns it off, or because the repo does not set it on an account that uses project Automations settings | Record a repo write that turns it on, plus the account write if the account has it off. Verify the effective value in Step 9 |
| Mapped to a different project | Do not remap. Remapping changes where its flags are created. The user unmaps it with [`launchdarkly-release-autopilot-settings`](../../launchdarkly-release-autopilot-settings/SKILL.md), then maps it in this flow |
