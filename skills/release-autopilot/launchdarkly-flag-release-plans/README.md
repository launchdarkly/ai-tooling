# LaunchDarkly Flag Release Plans Skill

An Agent Skill for reading and changing a project's flag release plans through the LaunchDarkly REST API. A flag release plan lists the project's environments in release order and names the environment release plan each one releases with. Auto-releasing proposes each new release from these plans.

## Overview

This skill teaches agents how to:

- List a project's flag release plans, or show one, with each environment's release plan
- Create a plan that points at environment release plans, and make it the project's default
- Change, replace the default, or delete a plan, confirming every write first
- Start a flag's release from a plan
- Handle the API's errors (key in use, validation, permission, and plan access)

## Installation (Local)

- **Generic**: copy `skills/release-autopilot/launchdarkly-flag-release-plans/` into your client's skills path

## Prerequisites

- `curl`, and an agent that can run shell commands
- A LaunchDarkly API access token in the `LD_ACCESS_TOKEN` environment variable. Export it in your own terminal before you start the agent. Never paste a token into the chat.
- `LD_BASE_URI` if your instance is not `https://app.launchdarkly.com`

The endpoints are in beta, and every request sends `LD-API-Version: beta`. The hosted MCP server has no flag release plan tools, and `ldcli` has no command for these endpoints, so the skill uses curl.

## Usage

```
Which flag release plans does project default have?
```

```
Create a flag release plan for project default: test, then production, each with its default release plan. Make it the default.
```

```
Make "Staged rollout" the default flag release plan in project default
```

## Related

- [LaunchDarkly Release Autopilot Onboarding](../launchdarkly-release-autopilot-onboarding/): first-time setup, which builds the project's flag release plan with this skill
- [LaunchDarkly Release Autopilot Settings](../launchdarkly-release-autopilot-settings/): turn auto-releasing on or off for a repository

## License

Apache-2.0
