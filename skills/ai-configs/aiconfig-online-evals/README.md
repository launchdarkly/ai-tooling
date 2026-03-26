# LaunchDarkly AI Config Online Evaluations Skill

An Agent Skill for attaching judges to AI Config variations for automatic LLM-as-a-judge evaluation.

## Overview

This skill teaches agents how to:
- Create custom judge AI Configs with evaluation criteria
- Attach judges to AI Config variations via API
- Configure sampling rates for cost control
- Monitor evaluation results in the dashboard

## Installation (Local)

Copy `skills/ai-configs/aiconfig-online-evals/` into your agent client's skills path.

## Prerequisites

- LaunchDarkly API access token with `ai-configs:write` permission
- Existing AI Config with variations (use `aiconfig-create` skill)
- For custom judges: understanding of LLM-as-a-judge methodology

## Usage

```
Attach security and API contract judges to the model-selector config at 100% sampling
```

```
Create a custom judge that checks for scope creep in code changes
```

## Structure

```
aiconfig-online-evals/
├── SKILL.md
└── README.md
```

## Related

- [AI Config Create](../aiconfig-create/) - Create AI Configs first
- [AI Config Targeting](../aiconfig-targeting/) - Enable targeting on judges
- [AI Config Variations](../aiconfig-variations/) - Manage variations
- [Online Evaluations Docs](https://docs.launchdarkly.com/home/ai-configs/online-evaluations)

## License

Apache-2.0
