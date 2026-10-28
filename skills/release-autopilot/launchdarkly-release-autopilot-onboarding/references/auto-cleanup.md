# Auto-cleanup

Auto-cleanup runs Vega on a schedule to find flags that are ready for code removal and open pull requests that remove their code. It is set per project, in the **Automated flag cleanup** section of Lifecycle settings. The MCP settings tools do not manage it yet.

For each project, give the user `/projects/{projectKey}/settings/lifecycle` on their LaunchDarkly instance (for example `https://app.launchdarkly.com`, or their EU or federal URL). In the "Automated flag cleanup" section they:

1. Check **Enable automated flag cleanups**.
2. Choose a **Schedule frequency**: 1 day, 7 days (the default), or 30 days.
3. Set **Max cleanup jobs per run** (1–20).
4. Select the **GitHub repositories** to clean up. Suggest the repos mapped in this flow. At least one is required.
5. Optionally add **Additional context** for the cleanup agent, such as where flags are defined. Vega also follows the repo's `AGENTS.md`.
6. Click **Save**.

Cleanup jobs run with the permissions of the member who saved the settings. If that member loses access, someone else must save the settings again.

Record the result as reported by the user. It cannot be verified.

Docs: [Automated flag cleanup](https://launchdarkly.com/docs/home/flags/manage/flag-cleanup-vega#automated-flag-cleanup)
