# Auto-archival in the browser

Use these steps only when the MCP server does not have `get-automations-archival` and `update-automations-archival`.

Give the user `/projects/{projectKey}/settings/automations` on their LaunchDarkly instance (for example `https://app.launchdarkly.com`, or their EU or federal URL). If the link opens the general project settings page instead, the account does not have the Automations page yet, and they use `/projects/{projectKey}/settings/lifecycle`. In the "Automatic archival" section they:

1. Turn on **Enable automatic archival**, and confirm in the "Enable automatic archival?" dialog.
2. Set the grace period before a ready flag is archived.
3. If the section shows **Require approval before archiving**, choose whether archivals need approval.
4. Click **Save**.

"View ready to archive flags" and "View auto-archived flags" open the flags list filtered to each set.

If the page has no "Automatic archival" section, the feature is not available for their account yet. Record the result as reported by the user. Without the tools, it cannot be verified.
