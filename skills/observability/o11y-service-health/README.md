# LaunchDarkly Service Health Check Skill

## Overview

- Teaches AI agents to check service health by examining error rates, latency percentiles, and throughput metrics.
- Assesses current metric values against historical baselines to determine if a service is operating normally.
- Classifies service status as **healthy**, **degraded**, or **critical** with per-metric breakdowns and evidence.
- Provides structured recommendations for next steps based on assessment results.

## Installation (Local)

Add the skill to your agent configuration by referencing the skill directory:

```yaml
skills:
  - path: skills/observability/o11y-service-health
```

## Prerequisites

- **LaunchDarkly MCP server** with observability tools enabled and configured.
- MCP tools available: `get-service-metrics`, `get-metric-baselines`, and optionally `list-services`.

## Usage

Example prompts that invoke this skill:

- "How is the checkout service doing?"
- "Is the API healthy after the last deploy?"
- "Check service health for the payments service"
- "What's the current status of the auth service?"
- "Are there any issues with the search service right now?"

## Structure

```
o11y-service-health/
├── SKILL.md
├── README.md
└── references/
    ├── metric-types.md
    └── health-assessment-criteria.md
```

| File | Description |
|------|-------------|
| `SKILL.md` | Core skill definition with workflow, principles, and edge cases |
| `README.md` | This file — overview, installation, and usage |
| `references/metric-types.md` | Detailed reference on error rate calculations, latency percentiles, throughput patterns, and common pitfalls |
| `references/health-assessment-criteria.md` | Baseline comparison techniques, threshold definitions, severity classification, and assessment methodology |

## Related

- [o11y-log-query](../o11y-log-query) — Query and analyze service logs for deeper investigation after identifying an unhealthy service.
- [LaunchDarkly MCP Server Documentation](https://docs.launchdarkly.com/) — Configuration and setup for the MCP server and observability tools.

## License

Apache-2.0
