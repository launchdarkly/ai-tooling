# LaunchDarkly AI Config Tools Skill

An Agent Skill for creating tools (function calling) and attaching them to AI Config variations. Guides identifying capabilities, creating tool schemas, and verifying attachment.

## Overview

This skill teaches agents how to:
- Identify what capabilities the AI needs
- Create tool definitions using the `create-ai-tool` MCP tool
- Attach tools to AI Config variations via `update-ai-config-variation`
- Verify tools are properly connected via `get-ai-config`

## Installation (Local)

Copy `skills/ai-configs/aiconfig-tools/` into your agent client's skills path.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

## Usage

```
Add a database search tool to our support agent config
```

```
Create tools for the content assistant to call our API
```

## Structure

```
aiconfig-tools/
├── SKILL.md
└── README.md
```

## Related

- [AI Config Create](../aiconfig-create/): Create the config before adding tools
- [AI Config Variations](../aiconfig-variations/): Manage variations that tools attach to
- [LaunchDarkly AI Configs Docs](https://docs.launchdarkly.com/home/ai-configs)

## License

Apache-2.0
