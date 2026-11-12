# Auto-archival

Auto-archival archives flags that are ready to archive, after archival safety checks and a grace period. It is set per project, in the **Automatic archival** section of the project's **Settings > Automations** page. Turning it on needs a person to confirm its risk in the browser, so onboarding always makes it a browser step. On an MCP server with `get-automations-archival` and `update-automations-archival`, the [`launchdarkly-automations-archival-settings`](../../launchdarkly-automations-archival-settings/SKILL.md) skill can read and change its other settings later.

For each project, give the user `/projects/{projectKey}/settings/automations` on their LaunchDarkly instance (for example `https://app.launchdarkly.com`, or their EU or federal URL). If the link opens the general project settings page instead, the account uses the older settings pages, and they use `/projects/{projectKey}/settings/lifecycle`. In the "Automatic archival" section they:

1. Turn on **Enable automatic archival**, and confirm in the "Enable automatic archival?" dialog.
2. Set the grace period before a ready flag is archived.
3. If the section shows **Require approval before archiving**, choose whether archivals need approval.
4. Click **Save**.

"View ready to archive flags" and "View auto-archived flags" open the flags list filtered to each set, so they can check what it will do and what it did.

If the page has no "Automatic archival" section, the account does not include the feature: record it as a follow-up, not as done.

Record the result as reported by the user. Onboarding does not verify it.
