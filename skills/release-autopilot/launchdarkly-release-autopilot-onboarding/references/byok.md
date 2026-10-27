# Bring your own key

Bring your own key is optional. A project that does not set it up uses LaunchDarkly managed Vega inference. No MCP tool reads or writes inference settings, so this is a browser step.

For each project, give the user `/projects/{projectKey}/settings/vega` on their LaunchDarkly instance (for example `https://app.launchdarkly.com`, or their EU or federal URL). On that page they:

1. Select bring your own key. If the account has no Anthropic or OpenAI key yet, the page links to the integration form to add one. Keys are account-wide, so later projects can reuse them.
2. Keep or change the suggested default and small models.
3. Save. LaunchDarkly checks the key with the provider before it stores the settings, and shows the cause if the check fails.

Record the result as reported by the user. It cannot be verified.
