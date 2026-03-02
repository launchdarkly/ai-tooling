# LaunchDarkly AI Config Create Skill

An Agent Skill for creating AI Configs in LaunchDarkly. Guides choosing agent vs completion mode, creating the config and variations, and verifying the result.

## Overview

This skill teaches agents how to:
- Understand the use case and choose agent vs completion mode
- Create AI Configs using MCP tools (`setup-ai-config` for one-step, or `create-ai-config` + `create-ai-config-variation` for more control)
- Set up model configuration with the correct `modelConfigKey` format
- Verify creation via the tool response or `get-ai-config`

## Installation (Local)

Copy `skills/ai-configs/aiconfig-create/` into your agent client's skills path.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

## Usage

```
Create an AI config for our customer support agent
```

```
Set up an AI config for content generation using Claude
```

## Structure

```
aiconfig-create/
├── SKILL.md
└── README.md
```

## Related

- [AI Config Projects](../aiconfig-projects/): Create projects first
- [AI Config Tools](../aiconfig-tools/): Add tools after creating config
- [AI Config Variations](../aiconfig-variations/): Add more variations for experimentation
- [LaunchDarkly AI Configs Docs](https://docs.launchdarkly.com/home/ai-configs)

## License

Apache-2.0
