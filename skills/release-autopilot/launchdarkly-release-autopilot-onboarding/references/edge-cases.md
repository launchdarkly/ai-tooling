# Edge cases and example flows

## Edge cases

| Situation | Action |
|-----------|--------|
| Every Release Autopilot tool returns 404 | The account is not in the alpha. Stop and tell the user |
| Member role is `reader` or `no_access` | Preview mode. End with the plan as a checklist for an admin |
| Member role is `writer` or a custom role | Account writes are marked "needs an admin" and left out of Step 8; repo writes still run |
| A write returns 403 | Report which write failed, list the remaining writes for an admin, and stop |
| `githubConnectUrl` with `flow=install` | Step 3. The user needs a GitHub org owner to install the App |
| Repo not on the install list | Same owner as listed repos: the user grants the App access to it. New owner: an org owner installs the App on that organization. Then list again |
| Mapped repo ID not on the install list | Show it by ID with its project. Do not change it |
| Repo already mapped to a different project | Do not remap here. The user unmaps it with the settings skill, then maps it in this flow |
| `list-release-plans` returns 403 `Plan does not allow this operation` | Policy mode. Show release policies and their warnings, create no plans, and keep auto-releasing off for the repo where a policy is missing or incomplete |
| Auto-releasing picked but no metrics exist (plan mode) | Offer the metric skills. Without metrics, the plan is progressive and nothing rolls back automatically |
| Incomplete migrated plan | Cannot start a release. Create a complete plan in that environment |
| Bring your own key chosen | Browser step only. Record it as reported, never as verified |
| No writes needed | Say so, list follow-ups, and stop |

## Existing mappings

| Current mapping | Action |
|-----------------|--------|
| Mapped to the chosen project, effective capabilities match the user's picks | Tell the user it is already set up. Write nothing |
| Mapped to the chosen project, a capability the user did not pick is effectively on | Record a repo override that turns it off, as its own line in Step 7 |
| Mapped to a different project | Do not remap. Remapping changes where its flags are created. The user unmaps it with [`launchdarkly-release-autopilot-settings`](../../launchdarkly-release-autopilot-settings/SKILL.md), then maps it in this flow |

## Example flows

**Fresh account: auto-flagging only, managed inference.**
Step 1 → admin, nothing set up, install list has repos. Step 2 → auto-flagging, approval required. Step 3 → skipped silently. Step 4 → maps `acme/web` to project `web`. Step 5 → managed. Step 6 → skipped. Step 7 → two writes: map `acme/web` with auto-releasing off for the repo, then account auto-flagging on with approval. Steps 8–9 → applied and verified.

**Account already on, policy mode, missing policy.**
Step 1 → both capabilities on, approval required, 3 repos mapped; "Add more". Step 2 → both capabilities; approval question skipped. Step 3 → skipped silently. Step 4 → maps `acme/demo` to `demo`. Step 5 → managed. Step 6 → release plans return 403, so policy mode; `missing_policy`. Step 7 → one write: map `acme/demo` with auto-flagging on and auto-releasing off for the repo; follow-up: add a release policy. Steps 8–9 → applied and verified.

**Reader: preview only.**
Step 1 → role `reader`, so Preview mode. Steps 2–6 as usual. Step 7 → "Changes an admin would make" checklist. No writes.

**Org owner needed: pause, then resume.**
Step 3 → `flow=install`, user selects "Need an org owner". Summarize and stop. Later, "continue Release Autopilot setup" → Resume mode: Step 1 shows the App installed, and the flow continues at Step 4 with the earlier picks.
