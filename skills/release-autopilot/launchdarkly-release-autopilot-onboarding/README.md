# LaunchDarkly Release Autopilot Onboarding Skill

An Agent Skill that walks a user through setting up Release Autopilot: pick capabilities, connect the GitHub App, map repositories, choose Vega inference, and set up environment release plans.

## Overview

This skill teaches agents how to:

- Ask which capabilities the user wants (auto-flagging, auto-releasing) and set up only what those need
- Hand the user the GitHub App install or authorize link, and continue after they finish
- Map chosen `owner/name` repos to LaunchDarkly projects
- Explain whose AI model account runs the agents (LaunchDarkly's by default, or the user's own Anthropic or OpenAI key) and guide bring-your-own-key setup
- Review or create environment release plans for auto-releasing, or show release policies where plans are not available
- Confirm one plan that lists every write before making any change, then verify

## Installation (Local)

- **Generic**: copy `skills/release-autopilot/launchdarkly-release-autopilot-onboarding/` into your client's skills path

## Prerequisites

The remotely hosted LaunchDarkly MCP server must expose the Release Autopilot settings tools, and `list-release-policies` and `list-metrics` for auto-releasing (`list-release-plans` and `create-release-plan` when the account has environment release plans). Release Autopilot is in alpha, so accounts outside the alpha get 404s.

## Usage

```
Set up Release Autopilot for this repo
```

```
Onboard us to Release Autopilot with auto-flagging and auto-releasing
```

## Related

- [LaunchDarkly Release Autopilot Settings](../launchdarkly-release-autopilot-settings/): single settings changes and "why didn't my PR get classified?"
- [LaunchDarkly Metric Choose](../../metrics/launchdarkly-metric-choose/): pick metrics for guarded release plans
- [LaunchDarkly MCP Server](https://github.com/launchdarkly/mcp-server)

## License

Apache-2.0
