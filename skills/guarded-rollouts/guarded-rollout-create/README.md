# LaunchDarkly Guarded Rollout Configuration Skill

## Overview

- Teaches AI agents to configure **guarded rollouts** for LaunchDarkly feature flags with automated metric monitoring and rollback
- Guides agents through designing **rollout stages** with appropriate traffic percentages and soak times based on risk level
- Provides methodology for setting **metric thresholds** (error rate, latency, throughput) derived from baseline data, not guesses
- Ensures rollouts follow a disciplined **explore, assess, execute, verify** pattern with user approval at each step

## Installation (Local)

Add this skill to your agent configuration by referencing the `SKILL.md` file:

```yaml
skills:
  - path: skills/guarded-rollouts/guarded-rollout-create/SKILL.md
```

Or copy the entire `guarded-rollout-create/` directory into your project's skills folder.

## Prerequisites

- **LaunchDarkly MCP server** with guarded rollout capabilities enabled
- MCP tools available: `create-guarded-rollout`, `get-flag`, `get-service-metrics`
- Optional MCP tools: `list-services`, `get-metric-baselines`
- Baseline metrics for the target service (use the service health check skill if baselines are not yet established)

## Usage

Invoke this skill when a user wants to safely roll out a feature flag with automated guardrails.

**Example prompts:**

```
Set up a guarded rollout for the new-checkout flag in production
```

```
Roll out dark-mode gradually with automatic rollback if errors spike
```

```
Configure a safe rollout for the payments feature with conservative stages
```

```
Create a guarded rollout for search-results-v3 — standard pattern,
monitor error rate and p99 latency
```

The skill will walk through four steps: identifying the flag and establishing baselines, designing rollout stages, defining monitoring thresholds, and configuring and verifying the rollout.

## Structure

```
guarded-rollout-create/
├── SKILL.md                              # Skill definition and workflow
├── README.md                             # This file
└── references/
    └── rollout-stage-patterns.md         # Detailed reference on stage progressions,
                                          #   soak times, threshold methodology,
                                          #   rollback config, and common mistakes
```

## Related

- [Service Health Check Skill](../../observability/o11y-service-health/SKILL.md) — establish baseline metrics before configuring a guarded rollout
- [Regression Detection Skill](../../observability/o11y-regression-detect/SKILL.md) — investigate metric anomalies during an active rollout
- [Feature Management Skills](../feature-management/) — flag creation, targeting, and lifecycle management

## License

Apache-2.0
