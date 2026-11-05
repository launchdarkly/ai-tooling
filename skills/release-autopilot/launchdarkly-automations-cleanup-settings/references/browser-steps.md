# Auto-cleanup in the browser

Use these steps only when the MCP server does not have `get-automations-cleanup` and `update-automations-cleanup`.

Give the user `/projects/{projectKey}/settings/automations` on their LaunchDarkly instance (for example `https://app.launchdarkly.com`, or their EU or federal URL). If the link opens the general project settings page instead, the account does not have the Automations page yet: they use `/projects/{projectKey}/settings/lifecycle`, or `/projects/{projectKey}/settings/vega` if that page has no "Automated flag cleanup" section. In the "Automated flag cleanup" section they:

1. Check **Enable automated flag cleanups**.
2. Choose a **Schedule frequency**.
3. Set **Max cleanup jobs per run**.
4. Select the **GitHub repositories** to clean up. At least one is required.
5. Optionally add **Additional context** for the cleanup agent.
6. Click **Save**.

Record the result as reported by the user. Without the tools, it cannot be verified.
