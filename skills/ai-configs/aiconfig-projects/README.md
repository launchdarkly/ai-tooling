# LaunchDarkly AI Config Projects Skill

An Agent Skill for setting up LaunchDarkly projects. Guides creating projects, retrieving SDK keys, and understanding how projects organize AI Configs and feature flags.

## Overview

This skill teaches agents how to:
- Understand what LaunchDarkly projects are and how they organize resources
- Create projects using the `create-project` MCP tool
- Retrieve existing projects and SDK keys via `get-project`
- Follow project key naming best practices

## Installation (Local)

Copy `skills/ai-configs/aiconfig-projects/` into your agent client's skills path.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

## Usage

```
Set up a LaunchDarkly project for our AI configs
```

```
Create a project for our customer support agent
```

## Structure

```
aiconfig-projects/
├── SKILL.md
└── README.md
```

## Related

- [LaunchDarkly AI Configs](https://docs.launchdarkly.com/home/ai-configs): Create AI Configs after setting up projects
- [LaunchDarkly Docs](https://docs.launchdarkly.com)
- [Agent Skills Specification](https://agentskills.io/specification)

## License

Apache-2.0
