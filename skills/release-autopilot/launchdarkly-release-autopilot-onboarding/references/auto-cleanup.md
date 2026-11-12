# Auto-cleanup

Auto-cleanup runs the Release Autopilot agents on a schedule to find flags that are ready for code removal and open pull requests that remove their code. It is set per project. Onboarding sets it through the MCP with `update-automations` (`projectKey` plus a `cleanup` object); [`launchdarkly-automations-cleanup-settings`](../../launchdarkly-automations-cleanup-settings/SKILL.md) changes it later.

Read the current settings first with `get-automations` (`section: "cleanup"`, `projectKey`). `settings.schedule` of `disabled` means it is off; `upcoming.flagKeys` and `nextRunAt` preview the next run.

The onboarding write sends only:

- `schedule`: `weekly` (recommended), `daily`, or `monthly`
- `repositories`: the `owner/name` repos cleanup opens pull requests in, all on the GitHub App install
- `maxJobsPerRun`: pull requests per run (3 is a safe start)

Leave `flagStates` at its default (`readyToArchive`). Lists replace the whole stored list: when adding repositories to a running cleanup, send the existing `repositories` from the read plus the new ones. Saving makes the calling member the one whose permissions cleanup jobs use; if that member loses access, someone else must save the settings again. Any schedule other than `disabled` makes LaunchDarkly open pull requests, so the Step 7 line must state the schedule, repositories, and pull requests per run.

In the UI, the same settings are in the **Automated flag cleanup** section of `/projects/{projectKey}/settings/automations`.

Docs: [Automated flag cleanup](https://launchdarkly.com/docs/home/flags/manage/flag-cleanup-vega#automated-flag-cleanup)
