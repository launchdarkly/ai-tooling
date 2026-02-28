# LaunchDarkly Agent Skills

LaunchDarkly's public collection of AI agent skills and playbooks. These skills encode repeatable workflows for working with LaunchDarkly, so coding agents can execute common tasks safely and consistently.

## What Is This Repo?

Agent Skills are modular, text-based playbooks that teach an agent how to perform a workflow. This repo is designed to be a public, open-source home for LaunchDarkly skills and to align with the emerging Agent Skills Open Standard.

## Available Skills

### Feature Flags

| Skill | Description |
|-------|-------------|
| `feature-flags/launchdarkly-flag-discovery` | Audit flags, find stale/launched flags, and assess removal readiness |
| `feature-flags/launchdarkly-flag-create` | Create new feature flags in a way that fits existing codebase patterns |
| `feature-flags/launchdarkly-flag-targeting` | Control targeting, rollouts, rules, and cross-environment config |
| `feature-flags/launchdarkly-flag-cleanup` | Safely remove flags from code using LaunchDarkly as the source of truth |
| `feature-flags/launchdarkly-flag-recreate` | Recreate a misconfigured flag when the key or variation type was set incorrectly |

### AI Configs

| Skill | Description |
|-------|-------------|
| `ai-configs/aiconfig-create` | Create AI Configs with variations for agent or completion mode |
| `ai-configs/aiconfig-update` | Update and delete AI Configs, manage lifecycle |
| `ai-configs/aiconfig-variations` | Manage AI Config variations for A/B testing |
| `ai-configs/aiconfig-tools` | Create and attach tools for function calling |
| `ai-configs/aiconfig-projects` | Create and manage projects to organize AI Configs |

### Skill Authoring

| Skill | Description |
|-------|-------------|
| `skill-authoring/create-skill` | Add a new skill following conventions — explore existing skills, create with workflow pattern, verify with validation scripts |

## Install as a Cursor Plugin

This repo is a [Cursor plugin](https://cursor.com/docs/plugins/building). Installing it gives you all the skills above plus the LaunchDarkly MCP server, so the agent can read and modify your flags directly.

1. Open Cursor and go to **Settings > Plugins**.
2. Search for **LaunchDarkly** in the marketplace, or install from the repo URL:
   ```
   https://github.com/launchdarkly/agent-skills
   ```
Once installed, the skills and MCP server are available across all your projects.

## Quick Start (Local)

```bash
# Clone the repo
git clone https://github.com/launchdarkly/agent-skills.git
cd agent-skills

# If your agent supports skills.sh installs:
npx skills add launchdarkly/agent-skills

# Or manually copy a skill into your agent's skills path:
cp -r skills/feature-flags/launchdarkly-flag-cleanup <your-agent-skills-dir>/
```

Then ask your agent something like:

```
Which feature flags are stale and should be cleaned up?
```

```
Create a feature flag for the new checkout flow
```

```
Roll out dark-mode to 25% of users in production
```

```
Remove the `new-checkout-flow` feature flag from this codebase
```

## Install via skills.sh CLI

```bash
npx skills add <owner/repo>
```

## Contributing

See `CONTRIBUTING.md` for how to add new skills and the conventions we follow.

## License

Apache-2.0
