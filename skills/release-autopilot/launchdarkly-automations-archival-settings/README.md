# LaunchDarkly Automations Auto-archival Settings Skill

An Agent Skill for reading and changing a project's auto-archival settings (the "Automatic archival" section of the project's Automations page) through the LaunchDarkly MCP.

## Overview

This skill teaches agents how to:

- Read a project's grace period, approval requirement, run limit, and notification recipients
- Change those settings or turn automatic archival off, confirming every write first
- Hand turning archival on to a person, who confirms its risk on the Automations page
- Explain why a flag was or was not archived automatically

## Installation (Local)

- **Generic**: copy `skills/release-autopilot/launchdarkly-automations-archival-settings/` into your client's skills path

## Prerequisites

The remotely hosted LaunchDarkly MCP server must expose `get-automations-archival` and `update-automations-archival`. Without them, the skill guides the browser steps instead. Accounts without automatic archival get an error saying it is not available yet.

## Usage

```
How long does automatic archival wait before archiving a flag in project default?
```

```
Require approval before automatic archival archives flags in project default
```

```
Why wasn't old-checkout archived automatically?
```

## Related

- [LaunchDarkly Automations Auto-cleanup Settings](../launchdarkly-automations-cleanup-settings/)
- [LaunchDarkly Release Autopilot Onboarding](../launchdarkly-release-autopilot-onboarding/): first-time setup of every capability

## License

Apache-2.0
