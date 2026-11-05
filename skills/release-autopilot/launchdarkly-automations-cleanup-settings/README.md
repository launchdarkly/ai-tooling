# LaunchDarkly Automations Auto-cleanup Settings Skill

An Agent Skill for reading and changing a project's auto-cleanup settings (the "Automated flag cleanup" section of the project's Automations page) through the LaunchDarkly MCP.

## Overview

This skill teaches agents how to:

- Read a project's cleanup schedule, repositories, limits, and the flags the next run will pick up
- Turn automated flag cleanup on, change it, or turn it off, confirming every write first
- Explain why cleanup did not open a pull request for a flag

## Installation (Local)

- **Generic**: copy `skills/release-autopilot/launchdarkly-automations-cleanup-settings/` into your client's skills path

## Prerequisites

The remotely hosted LaunchDarkly MCP server must expose `get-automations-cleanup` and `update-automations-cleanup`. Without them, the skill guides the browser steps instead.

## Usage

```
Turn on automated flag cleanup for project default, weekly, in acme/web
```

```
Which flags will the next cleanup run pick up in project default?
```

```
Why didn't flag cleanup open a pull request for old-checkout?
```

## Related

- [LaunchDarkly Automations Auto-archival Settings](../launchdarkly-automations-archival-settings/)
- [LaunchDarkly Release Autopilot Onboarding](../launchdarkly-release-autopilot-onboarding/): first-time setup of every capability
- [LaunchDarkly Flag Cleanup](../../feature-flags/launchdarkly-flag-cleanup/): remove one flag's code by hand

## License

Apache-2.0
