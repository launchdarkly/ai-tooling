# LaunchDarkly Release Autopilot Onboarding Skill

An Agent Skill that walks a user through setting up Release Autopilot: pick capabilities, connect the GitHub App, map repositories, choose which AI model account runs the agents, set up environment release plans (with starter plans), set auto-cleanup, and guide turning on auto-archival.

## Overview

This skill teaches agents how to:

- Ask which capabilities the user wants (auto-flagging, auto-releasing) and set up only what those need
- Hand the user the GitHub App install or authorize link, and continue after they finish
- Map chosen `owner/name` repos to LaunchDarkly projects
- Set auto-cleanup through the MCP, and guide turning on auto-archival on the project's Automations page
- Explain whose AI model account runs the agents (LaunchDarkly's by default, or the user's own Anthropic or OpenAI key) and guide bring-your-own-key setup
- Use or create environment release plans for auto-releasing, offering starter plans and setting each environment's default; show release policies only on accounts without release plans
- Confirm GitHub works, list exactly which repos were set up, and offer a test pull request and next steps
- Confirm one plan that lists every write before making any change, then verify

## Installation

Install the LaunchDarkly plugin first. It includes this skill and the LaunchDarkly MCP server that the skill needs.

- **Claude Code**: run `/plugin marketplace add launchdarkly/ai-tooling`, then `/plugin install launchdarkly@launchdarkly-ai-tooling`. Then open `/mcp` and sign in to the `launchdarkly` server.
- **Cursor**: open **Settings > Plugins**, search for **LaunchDarkly**, and install it.

The skill is in Claude Code plugin 1.0.3 and Cursor plugin 1.0.4 and later. With an earlier plugin, a request to set up Release Autopilot starts the SDK onboarding skill instead, so update the plugin first.

- **Other clients**: copy `skills/release-autopilot/launchdarkly-release-autopilot-onboarding/` into your client's skills path, and connect the hosted LaunchDarkly MCP server.

## Prerequisites

The remotely hosted LaunchDarkly MCP server must expose the Release Autopilot tools (`get-automations`, `update-automations`), and `get-environment-release-plans`, `create-environment-release-plan`, `update-default-environment-release-plan`, and `get-metrics` for auto-releasing (`get-release-policies` on accounts without release plans). Accounts without the Release Autopilot add-on enabled get 404s.

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
