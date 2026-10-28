# LaunchDarkly Config Targeting Skill

An Agent Skill for configuring config targeting rules with the LaunchDarkly MCP server.

## Overview

This skill teaches agents how to:
- Turn targeting on/off for configs
- Add attribute-based targeting rules
- Configure percentage rollouts for A/B testing
- Set fallthrough (default) variations
- Target individual contexts or segments

## Installation (Local)

Copy `skills/agentcontrol/configs-targeting/` into your agent client's skills path.

## Prerequisites

- The LaunchDarkly MCP server (scripts without MCP need an API access token with `ai-configs:write`)
- Existing config with variations (use `configs-create` skill)
- Understanding of contexts (see `context-basic` skill)

## Usage

```
Set up targeting rules for model-selector: route sonnet requests to the Sonnet variation, mistral to Mistral, and default to Opus
```

```
Add a percentage rollout: 60% to variation A, 40% to variation B for premium users
```

## Structure

```
configs-targeting/
├── SKILL.md
└── README.md
```

## Related

- [config Create](../configs-create/) - Create configs first
- [config Variations](../configs-variations/) - Create variations to target
- [config Online Evals](../online-evals/) - Attach judges
- [Targeting Docs](https://docs.launchdarkly.com/home/ai-configs/target)

## License

Apache-2.0
