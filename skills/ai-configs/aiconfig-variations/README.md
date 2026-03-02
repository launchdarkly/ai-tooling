# LaunchDarkly AI Config Variations Skill

An Agent Skill for creating and managing AI Config variations to experiment with different models, prompts, and parameters.

## Overview

This skill teaches agents how to:
- Design experiments (model comparison, prompt optimization, parameter tuning)
- Create variations using `clone-ai-config-variation` (recommended) or `create-ai-config-variation`
- Verify variations exist with correct configuration via `get-ai-config`

## Installation (Local)

Copy `skills/ai-configs/aiconfig-variations/` into your agent client's skills path.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

## Usage

```
Add a GPT-4o-mini variation to test cost savings
```

```
Create variations to compare Claude vs GPT-4 for our agent
```

## Structure

```
aiconfig-variations/
├── SKILL.md
└── README.md
```

## Related

- [AI Config Create](../aiconfig-create/): Create the config first
- [AI Config Update](../aiconfig-update/): Modify existing variations
- [AI Config Tools](../aiconfig-tools/): Attach tools to variations
- [LaunchDarkly AI Configs Docs](https://docs.launchdarkly.com/home/ai-configs)

## License

Apache-2.0
