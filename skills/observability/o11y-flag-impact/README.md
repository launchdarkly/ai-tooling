# LaunchDarkly Flag Impact Analysis Skill

## Overview

- Teaches AI agents to correlate feature flag changes with shifts in service metrics (error rate, latency, throughput).
- Guides agents through defining before/after measurement windows around a flag change timestamp.
- Accounts for rollout percentages, confounding factors, and sample size when assessing impact.
- Produces findings with appropriate confidence levels and evidence-based language, avoiding causal claims.

## Installation (Local)

Clone this repository and reference the skill from your agent configuration:

```bash
git clone https://github.com/launchdarkly/agent-skills.git
```

Add the skill path to your agent's skill configuration:

```yaml
skills:
  - path: skills/observability/o11y-flag-impact
```

## Prerequisites

- **LaunchDarkly MCP server** with both feature flag and observability tools enabled.
- **MCP tools available:** `get-flag`, `get-service-metrics`, `get-flag-changes`. Optionally `get-metric-baselines`.
- Access to the LaunchDarkly environment where the flag change occurred.

## Usage

Ask your agent questions like:

```
"Did the new-checkout flag cause the error spike?"
```

```
"What's the impact of rolling out dark-mode to 50%?"
```

```
"Check if the recent flag change affected latency."
```

```
"The cache-bypass flag was toggled off 2 hours ago. Did error rates change?"
```

```
"Compare metrics before and after the search-v2 rollout went from 10% to 100%."
```

The agent will follow the skill's workflow to identify the flag change, define measurement windows, pull before/after metrics, assess correlation with appropriate confidence, and report findings.

## Structure

```
o11y-flag-impact/
├── SKILL.md                              # Skill definition and workflow
├── README.md                             # This file
└── references/
    └── correlation-methods.md            # Detailed reference on correlation techniques
```

## Related

- **[o11y-service-health](../o11y-service-health/)** — Establish baseline service metrics and assess overall service health. Use this skill to understand normal behavior before analyzing flag impact.
- **Feature flag skills** (`../../feature-flags/`) — Manage flag configuration, targeting rules, and lifecycle. Use alongside this skill when you need to modify a flag based on impact findings.

## License

Apache-2.0
