---
name: o11y-regression-detect
description: "Continuously poll a service's metrics at repeated intervals and alert when a regression threshold is breached multiple consecutive times. Use when the user asks to 'watch', 'monitor', or 'keep an eye on' a service during a rollout. This skill performs ongoing detection over time — use o11y-service-health for a one-time metric snapshot, or guarded-rollout-create to configure automated rollback."
license: Apache-2.0
compatibility: Requires LaunchDarkly MCP server with observability tools enabled.
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# Regression Detection

You're using a skill that will guide you through monitoring a service during a rollout to detect metric regressions. Your job is to define what to monitor and at what thresholds, establish a baseline, monitor at intervals, and signal when intervention may be needed.

This skill is often used alongside the [guarded rollout skill](../../guarded-rollouts/guarded-rollout-create/SKILL.md) to automate rollback when regressions are detected, and it builds on the [service health check skill](../o11y-service-health/SKILL.md) for baseline data and health assessment.

## Prerequisites

- **LaunchDarkly MCP server** with observability tools enabled.
- **Required MCP tools:**
  - `get-service-metrics` — fetch current metric values for a service (error rate, latency, throughput).
  - `get-metric-baselines` — retrieve historical baseline data for a service's metrics.
- **Optional MCP tools:**
  - `get-flag` — check the current rollout state of a feature flag (useful for correlating regressions with rollout percentage).
  - `list-services` — enumerate available services if the user does not specify one.

## Core Principles

1. **Signal, Don't Decide** — This skill detects regressions and reports them. It does not automatically roll back, disable flags, or take corrective action. The human operator or an orchestrating agent (such as the guarded rollout skill) decides what to do with the signal.

2. **Consecutive Checks, Not Single Points** — Never signal a regression based on a single data point. Metrics are noisy; transient spikes are common. Always require multiple consecutive threshold breaches before classifying a regression as confirmed. See [detection-strategies.md](references/detection-strategies.md) for the consecutive-check patterns (3-of-5, N-of-M, and immediate-critical exceptions).

3. **Baselines Before Monitoring** — You must establish what "normal" looks like before you can detect "abnormal." Without a baseline, thresholds are arbitrary and regression detection is unreliable. Always gather baseline data before starting the monitoring loop.

4. **Severity Levels Matter** — Distinguish between warning (a metric is approaching its threshold or has a single isolated breach) and critical (a sustained breach confirmed by consecutive checks). This distinction enables proportional responses: warnings prompt attention, criticals prompt action.

## Workflow

### Step 1: Define Monitoring Parameters

Determine the following before starting:

- **Which service** to monitor. If the user does not specify, use `list-services` to identify options and ask.
- **Which metrics** to monitor. Common choices: error rate, latency p99, throughput (requests per second). Default to all three unless the user specifies otherwise.
- **Thresholds** for each metric. The user may provide these directly (e.g., "alert if error rate exceeds 2%"). If not provided:
  - Use `get-metric-baselines` to retrieve historical data.
  - Apply the relative threshold methodology from [detection-strategies.md](references/detection-strategies.md): 200% of baseline for error rate, 150% for latency, 70% floor for throughput.
- **Check interval.** Default: every 1 minute. The user may request a different interval.
- **Monitoring duration.** Default: 30 minutes. The user may specify a different duration.
- **Consecutive-check pattern.** Default: 3-of-5 (3 breaches in 5 checks to trigger critical). The user may adjust sensitivity.

Present the monitoring plan to the user for confirmation before proceeding.

### Step 2: Establish Baseline

Use `get-metric-baselines` to retrieve baseline data for the service's monitored metrics. If baselines are unavailable, use `get-service-metrics` to sample current (pre-rollout) values as the baseline.

Record for each metric:
- Baseline value (mean or median from historical data).
- Computed threshold (baseline value adjusted by the threshold multiplier).
- Warning level (80% of the distance from baseline to threshold).

**Important:** If the baseline itself looks unhealthy (e.g., error rate already elevated), flag this to the user before starting monitoring. Monitoring against an unhealthy baseline will mask further regressions.

### Step 3: Monitor at Intervals

Execute the monitoring loop:

1. **At each check interval**, call `get-service-metrics` to retrieve current values for each monitored metric.
2. **Compare** each metric against its threshold.
3. **Track** consecutive breaches using the configured pattern (default 3-of-5).
4. **Classify** the current overall status:
   - **Normal** — All metrics within thresholds. No breaches in the consecutive-check window.
   - **Warning** — A single threshold breach has occurred, or a metric is within 20% of its threshold, but the consecutive-check pattern is not yet satisfied.
   - **Critical** — The consecutive-check pattern is satisfied for at least one metric (e.g., 3 of the last 5 checks breached the threshold). Alternatively, an immediate-critical threshold was breached (e.g., error rate > 50%).
5. **Report** the status at each check. Include: check number, current metric values, threshold status (normal/breach), cumulative breach count, and overall status (normal/warning/critical).

Continue until the monitoring duration is reached or a critical status is signaled.

### Step 4: Signal When Needed

When the overall status reaches **critical**, signal the regression clearly. The signal must include:

- **Which metric** regressed (e.g., "error rate").
- **Current value** vs. **baseline** (e.g., "current: 1.8%, baseline: 0.3%").
- **Threshold breached** (e.g., "threshold: 0.6%, which is 200% of baseline").
- **Number of consecutive breaches** (e.g., "3 of the last 5 checks exceeded the threshold").
- **Recommended action** — Suggest investigation and, if appropriate, consideration of a rollback. Do not perform the rollback; let the user or orchestrating agent decide.

If monitoring completes without reaching critical status, report that the service remained healthy throughout the monitoring period, along with a summary of any warnings observed.

## Edge Cases

| Scenario | How to Handle |
|----------|--------------|
| Baseline itself is unhealthy | Alert the user before monitoring begins. Ask whether to proceed with the current baseline or wait for the service to recover. If proceeding, note that regressions relative to an already-degraded baseline may understate the true impact. |
| Metrics become unavailable during monitoring | Report the data gap. Do not count unavailable checks as breaches or as healthy. If metrics are unavailable for more than 3 consecutive checks, pause monitoring and alert the user. |
| Traffic drops to zero | Suspend regression detection for error rate and latency (these metrics are meaningless without traffic). Report the throughput drop as a critical signal — zero traffic may indicate a complete outage. |
| Threshold breach is transient | This is handled by the consecutive-check pattern. A single transient breach will appear as a warning but will not escalate to critical unless subsequent checks also breach. |
| Multiple metrics breach simultaneously | Escalate overall severity. If two or more metrics are in breach at the same time, this increases confidence that the regression is real and may warrant a more urgent signal. |
| User wants to adjust thresholds mid-monitoring | Allow it. Update the threshold values and reset the consecutive-check window for affected metrics. Log the threshold change in the monitoring report. |

## What NOT to Do

- **Don't automatically roll back.** Regression detection signals; the [guarded rollout skill](../../guarded-rollouts/guarded-rollout-create/SKILL.md) or the human operator decides whether to roll back.
- **Don't signal on a single data point.** Always use consecutive-check patterns. The only exception is immediate-critical thresholds (e.g., error rate > 50%).
- **Don't monitor without baselines.** Thresholds derived without baseline data are arbitrary and will produce unreliable results.
- **Don't ignore throughput drops.** A drop in throughput can mask other metrics — if no requests are flowing, error rate may appear low even though the service is failing.
- **Don't continue monitoring indefinitely.** Always define a monitoring duration. If the duration expires without a critical signal, report success and stop. Open-ended monitoring wastes resources and attention.

## References

- [Detection Strategies Reference](references/detection-strategies.md) — Detailed coverage of threshold types, consecutive-check patterns, severity classification, rolling baselines, monitoring intervals, and false positive management.
- [Service Health Check Skill](../o11y-service-health/SKILL.md) — Use for establishing baselines and assessing overall service health before starting regression detection.
- [Guarded Rollout Skill](../../guarded-rollouts/guarded-rollout-create/SKILL.md) — Use alongside this skill to automate rollback decisions when regressions are detected.
- [Flag Impact Analysis Skill](../o11y-flag-impact/SKILL.md) — Use after a rollout completes to analyze the overall impact of a feature flag on service metrics.
