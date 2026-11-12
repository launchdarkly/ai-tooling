# LaunchDarkly Release Plans Skill

An Agent Skill for both kinds of LaunchDarkly release plan:

- **Environment release plans**: how a flag releases in one environment (phases, rollout steps, holds, and rollback metrics). Each environment has a default plan.
- **Flag release plans**: a project's environments in release order, each with its environment release plan. Auto-releasing proposes each release from these plans.

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

- The hosted LaunchDarkly MCP server, for environment release plans
- For flag release plans and for deleting an environment release plan: `curl`, an agent that can run shell commands, and a LaunchDarkly API access token in `LD_ACCESS_TOKEN`. Export it in your own terminal before you start the agent. Never paste a token into the chat. Set `LD_BASE_URI` if your instance is not `https://app.launchdarkly.com`.

These REST endpoints are in beta, and every request sends `LD-API-Version: beta`. The MCP server has no flag release plan tools, and `ldcli` has no command for these endpoints, so the skill uses curl.

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
