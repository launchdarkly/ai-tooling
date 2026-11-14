# LaunchDarkly Release Plans Skill

An Agent Skill for both kinds of LaunchDarkly release plan:

- **Environment release plans**: how a flag releases in one environment (phases, rollout steps, holds, and rollback metrics). Each environment has a default plan.
- **Flag release plans**: a project's environments in release order, each with its environment release plan. Release Autopilot proposes releases on pull requests from these plans. A rollout recorded for a flag (the `flag-release` skill) uses each environment's default release plan instead.

## Overview

This skill teaches agents how to:

- List and show both kinds of plan, and each environment's and project's default
- Create environment release plans from starter plans (progressive, or guarded with rollback metrics) or step by step, after checking the randomization unit and metrics
- Build or update the project's flag release plan from existing environment release plans, and prompt for a release plan first when an environment has none
- Edit, make default, and delete both kinds of plan, confirming every write first
- Start a flag's release from a flag release plan
- Plan without writing ("record only"), for skills such as Release Autopilot onboarding that confirm and write later

## Installation (Local)

- **Generic**: copy `skills/release-autopilot/launchdarkly-release-plans/` into your client's skills path

## Prerequisites

- The hosted LaunchDarkly MCP server, for both kinds of plan. Its flag release plan tools are still reaching accounts.
- When the server has no tool for an operation (flag release plans without their tools, starting a flag's release, deleting an environment release plan): the agent shows the REST command, and you run it in your own terminal with your LaunchDarkly API access token in `LD_ACCESS_TOKEN`, then paste the output back. The agent never runs these commands. Never paste a token into the chat.

These REST endpoints are in beta, and every command sends `LD-API-Version: beta`. `ldcli` has no command for these endpoints, so the commands use curl.

## Usage

```
Which release plans does production in project default have?
```

```
Create a release plan for production in project default and make it the default
```

```
Build the flag release plan for project default: test, then production, as the default
```

## Related

- [LaunchDarkly Release Autopilot Onboarding](../launchdarkly-release-autopilot-onboarding/): first-time setup, which follows this skill for release plans
- [LaunchDarkly Release Autopilot Settings](../launchdarkly-release-autopilot-settings/): turn auto-releasing on or off for a repository

## License

Apache-2.0
