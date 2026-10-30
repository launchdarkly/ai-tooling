# Auto-archival

Auto-archival archives flags that are ready to archive, after archival safety checks and a grace period. It is set per project, in the **Automatic archival** section of Lifecycle settings. No MCP tool manages it. The section is still rolling out, so some accounts do not see it yet.

For each project, give the user `/projects/{projectKey}/settings/lifecycle` on their LaunchDarkly instance (for example `https://app.launchdarkly.com`, or their EU or federal URL). In the "Automatic archival" section they:

1. Turn on **Enable automatic archival**, and confirm in the "Enable automatic archival?" dialog.
2. Set the grace period before a ready flag is archived.
3. If the section shows **Require approval before archiving**, choose whether archivals need approval.
4. Click **Save**.

"View ready to archive flags" and "View auto-archived flags" open the flags list filtered to each set, so they can check what it will do and what it did.

If the page has no "Automatic archival" section, the feature is not available for their account yet: record it as a follow-up, not as done.

Record the result as reported by the user. It cannot be verified.
