# LaunchDarkly Agent Skills

LaunchDarkly's public collection of agent skills and playbooks. These skills encode repeatable workflows for working with LaunchDarkly, so coding agents can execute common tasks safely and consistently.

## What Is This Repo?

Agent Skills are modular, text-based playbooks that teach an agent how to perform a workflow. This repo is designed to be a public, open-source home for LaunchDarkly skills and to align with the emerging Agent Skills Open Standard.

## Available Skills

### Feature Flags

| Skill | Description |
|-------|-------------|
| `feature-flags/launchdarkly-flag-command` | Resolve `/flag` style requests into fast flag lookup, detail, and disambiguation |
| `feature-flags/should-flag-change` | Advisory, read-only call on whether a code change (diff/PR) should ship behind a feature flag |
| `feature-flags/launchdarkly-flag-discovery` | Audit flags, find stale/launched flags, and assess removal readiness |
| `feature-flags/launchdarkly-flag-create` | Create new feature flags in a way that fits existing codebase patterns |
| `feature-flags/launchdarkly-flag-targeting` | Control targeting, rollouts, rules, and cross-environment config |
| `feature-flags/launchdarkly-flag-cleanup` | Safely remove flags from code using LaunchDarkly as the source of truth |
| `feature-flags/launchdarkly-flag-drift` | Detect and reconcile drift between an in-code SDK fallback default and the LaunchDarkly default rule |
| `feature-flags/launchdarkly-guarded-rollout` | Configure guarded rollouts with progressive traffic, metric monitoring, and rollback |
| `feature-flags/flag-release` | Record a flag's automated release for a PR, honoring release intent and per-environment release policies |
| `feature-flags/flag-and-release-change` | End-to-end PR orchestrator: decide → create + wire the flag → record its release (composes the skills above) |
| `feature-flags/launchdarkly-flag-qualitative-feedback-setup` | Add a qualitative user feedback widget tied to a flag, adapting to the project's framework and design system |

### AgentControl

| Skill | Description |
|-------|-------------|
| `agentcontrol/configs-create` | Create configs with variations for agent or completion mode |
| `agentcontrol/migrate` | Migrate an app with hardcoded LLM prompts to AgentControl in five stages (extract, wrap, tools, tracking, evals) |
| `agentcontrol/configs-update` | Update and delete configs, manage lifecycle |
| `agentcontrol/configs-variations` | Manage config variations for A/B testing |
| `agentcontrol/tools` | Create and attach tools for function calling |
| `agentcontrol/projects` | Create and manage projects to organize configs |
| `agentcontrol/online-evals` | Attach LLM-as-a-judge evaluators to configs |
| `agentcontrol/configs-targeting` | Configure targeting rules for config rollouts |
| `agentcontrol/snippets` | Create and manage reusable prompt snippets across configs |
| `agentcontrol/agent-graphs` | Create and manage multi-agent graphs with routing and handoffs |

### Experiments

| Skill | Description |
|-------|-------------|
| `experiments/launchdarkly-experiment-setup` | Set up experiments with metrics, treatments, and data collection |

### Metrics

| Skill | Description |
|-------|-------------|
| `metrics/launchdarkly-metric-choose` | Select the right metric type for an experiment |
| `metrics/launchdarkly-metric-create` | Create metrics and instrument tracking events |
| `metrics/launchdarkly-metric-instrument` | Add tracking calls to code for existing metrics |

## Install as a Claude Code Plugin

This repo is a [Claude Code plugin](https://code.claude.com/docs/en/create-plugins). Installing it gives you all the skills above plus the LaunchDarkly MCP server.

1. Add this repo as a plugin marketplace in Claude Code:
   ```
   /plugin marketplace add launchdarkly/ai-tooling
   ```
2. Install the plugin:
   ```
   /plugin install launchdarkly@launchdarkly-ai-tooling
   ```
3. Authenticate the LaunchDarkly MCP server when prompted with your [API access token](https://docs.launchdarkly.com/home/account/api).

Once installed, skills are available as `/launchdarkly:<skill-name>` across all your projects, and the MCP server can read and modify your flags directly.

### Onboarding

| Skill | Description |
|-------|-------------|
| `onboarding` | End-to-end LaunchDarkly setup: quiet scripted flow, SDK install, first flag with a live reveal, MCP offered afterwards |
| `onboarding/mcp-configure` | Configure the LaunchDarkly hosted MCP server (OAuth, no API keys needed) |
| `onboarding/sdk-install` | Install and initialize the correct SDK via detect, plan, and apply sub-steps |

## Install as a Cursor Plugin

This repo is a [Cursor plugin](https://cursor.com/docs/plugins/building). Installing it gives you all the skills above plus the LaunchDarkly MCP server, so the agent can read and modify your flags directly.

1. Open Cursor and go to **Settings > Plugins**.
2. Search for **LaunchDarkly** in the marketplace, or install from the repo URL:
   ```
   https://github.com/launchdarkly/ai-tooling
   ```
Once installed, the skills and MCP server are available across all your projects.

## Quick Start (Local)

```bash
# Clone the repo
git clone https://github.com/launchdarkly/ai-tooling.git
cd ai-tooling

# If your agent supports skills.sh installs:
npx skills add launchdarkly/ai-tooling

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
