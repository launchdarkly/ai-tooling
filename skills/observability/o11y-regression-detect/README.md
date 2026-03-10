# LaunchDarkly Regression Detection Skill

## Overview

- Teaches AI agents to monitor services during feature flag rollouts and detect metric regressions in real time.
- Uses consecutive-check patterns (e.g., 3-of-5) to confirm regressions and avoid false positives from transient metric spikes.
- Classifies regression severity into normal, warning, and critical levels to enable proportional responses.
- Signals regressions with full context (metric, current value, baseline, threshold, breach count) so operators or orchestrating agents can make informed decisions.

## Installation (Local)

Add the skill to your agent configuration by referencing the skill directory:

```yaml
skills:
  - path: skills/observability/o11y-regression-detect
```

Or copy the skill directory into your project's skills folder:

```bash
cp -r skills/observability/o11y-regression-detect /path/to/your/project/skills/
```

## Prerequisites

- **LaunchDarkly MCP server** with observability tools enabled.
- MCP tools available: `get-service-metrics`, `get-metric-baselines`.
- Optional MCP tools: `get-flag`, `list-services`.

## Usage

Invoke the skill by asking your agent to monitor a service during a rollout. Examples:

```
"Watch the checkout service during this rollout and alert me if metrics regress."
```

```
"Monitor error rates while we roll out the new payment flow. Use a 2% threshold."
```

```
"Alert me if latency crosses 500ms during the dark-mode rollout."
```

```
"Monitor the search service for the next 20 minutes — check every 2 minutes and flag any throughput drops."
```

The agent will define monitoring parameters, establish a baseline, run checks at the configured interval, and signal if a regression is detected.

## Structure

```
o11y-regression-detect/
├── SKILL.md                            # Skill definition and workflow
├── README.md                           # This file
└── references/
    └── detection-strategies.md         # Detailed reference on thresholds, consecutive-check patterns, severity, baselines, and false positive management
```

## Related

- [Service Health Check Skill](../o11y-service-health/) — Assess overall service health and establish metric baselines before starting regression detection.
- [Guarded Rollout Skill](../../guarded-rollouts/guarded-rollout-create/) — Automate rollback decisions based on regression detection signals from this skill.
- [Flag Impact Analysis Skill](../o11y-flag-impact/) — Analyze the post-rollout impact of a feature flag on service metrics.

## License

Apache-2.0
