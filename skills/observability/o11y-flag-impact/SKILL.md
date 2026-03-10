---
name: o11y-flag-impact
description: "Retrospective analysis: compare service metrics from before and after a specific feature flag change to determine whether the flag caused a metric shift. Use when the user asks 'did flag X cause the error spike', 'what was the impact of turning on flag Y', or wants a before/after comparison of metrics around a known flag change event."
license: Apache-2.0
compatibility: Requires LaunchDarkly MCP server with both feature flag and observability tools enabled.
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# Flag Impact Analysis

You're using a skill that will guide you through correlating a feature flag change with shifts in service metrics. Your job is to identify the flag change, define measurement windows, pull before/after metrics, assess correlation, and report findings with appropriate confidence.

## Prerequisites

- **LaunchDarkly MCP server** with both feature flag and observability tools enabled.
- **Required MCP tools:**
  - `get-flag` — fetch flag configuration and change history.
  - `get-service-metrics` — fetch error rate, latency, and throughput for a specified time window.
  - `get-flag-changes` — list recent flag changes with timestamps.
- **Optional MCP tools:**
  - `get-metric-baselines` — fetch historical metric baselines for comparison.

## Core Principles

1. **Correlation is Not Causation** — Present evidence, not certainty. Use language like "likely impacted" or "correlates with," never "caused" or "definitely." Your analysis establishes correlation and assesses its strength, but cannot prove causation on its own.

2. **Windows Must Be Clean** — The before and after measurement windows must not overlap with other changes (deployments, other flag changes, infrastructure events). A contaminated window produces unreliable results. A smaller clean window is always better than a larger contaminated one.

3. **Account for Rollout Percentage** — A flag at 5% rollout will not produce a 100% metric shift. Scale your expectations to the rollout percentage. If a flag is at 10% and you see a 10% error rate increase, the per-request impact is likely much larger. Always check the rollout percentage before interpreting metric magnitude.

4. **Absence of Evidence is Evidence** — If metrics did not change after a flag toggle, that is a valid and useful finding. Report it clearly. A "no impact" result gives the team confidence that the change is safe, or rules out the flag as the cause of an issue under investigation.

## Workflow

### Step 1: Identify the Flag Change

Determine which flag changed, when it changed, and what changed (toggled on/off, rollout percentage changed, targeting rules changed).

- Use `get-flag-changes` to list recent flag changes, or use `get-flag` if you already know the flag key.
- Record the flag key, the environment (e.g., production, staging), and the exact timestamp of the change.
- Note what changed: was it toggled from off to on? Was the rollout percentage increased from 0% to 25%? Were targeting rules modified?
- Confirm the flag, environment, and timestamp with the user before proceeding.

### Step 2: Define Metric Windows

Set a "before" window (pre-change) and an "after" window (post-change) of equal duration.

- Choose window duration based on the service's traffic volume. High-traffic services can use shorter windows (30 min to 1 hour); low-traffic services need longer windows (4 to 24 hours). See [correlation-methods.md](references/correlation-methods.md) for detailed sizing guidance.
- Align the windows with the flag change timestamp. Leave a small buffer (1-5 minutes) around the change to account for propagation delay.
- Check for confounding changes in both windows: other deployments, other flag changes, infrastructure events, traffic pattern shifts. If confounders exist, shrink the windows to exclude them or note them as limitations.

### Step 3: Pull Before/After Metrics

Use `get-service-metrics` for both the before and after windows.

- Collect the following metrics for each window:
  - **Error rate** (percentage of requests resulting in errors)
  - **Latency** — p50, p95, and p99
  - **Throughput** (requests per second or per minute)
- If possible, scope metrics to the specific service or endpoint that the flag affects, rather than using aggregate service-wide metrics.
- If `get-metric-baselines` is available, pull historical baselines for additional context (e.g., what does this metric normally look like at this time of day?).
- Record the exact time ranges and metric values for your report.

### Step 4: Assess & Report

Compare before vs after across all collected metrics.

- Calculate the absolute and relative change for each metric.
- Account for the rollout percentage. If the flag is at 20% rollout and error rate increased by 1 percentage point, the per-affected-request impact is approximately 5x larger than the aggregate number suggests.
- Check confounders one more time. If you find a confounder you missed earlier, note it.
- Classify your finding:
  - **Likely impacted** — There is a clear metric shift that aligns with the flag change timing, with no (or minimal) confounders. State the evidence and confidence level.
  - **No clear impact** — Metrics are stable across both windows. The flag change does not appear to have affected the measured metrics.
  - **Insufficient data** — The window is too short, traffic is too low, or metrics are not available. Recommend waiting and re-analyzing.
- Present your findings with specific numbers: "Error rate increased from 0.12% to 1.45% (12x increase) in the 1-hour window following the flag toggle at 14:00 UTC. No other changes were detected in this window. Confidence: High."
- Include a recommended action: roll back, continue monitoring, increase rollout, or wait for more data.

## Edge Cases

| Scenario | How to Handle |
|---|---|
| Flag changed multiple times in short succession | Use the most recent stable state as the "after" starting point. Note the rapid changes and consider whether metrics had time to stabilize between changes. |
| Flag is at very low rollout percentage (< 5%) | Aggregate metrics may not show a detectable shift. Prefer segment-level analysis if available. If not, note that the rollout percentage is too low for reliable aggregate analysis. |
| No clear "before" baseline (flag was changing frequently) | Look for the longest stable period before the change of interest. If no stable period exists, note this as a limitation and lower your confidence. |
| Multiple flags changed simultaneously | Identify all flags that changed in the window. If they affect different services or code paths, you may still be able to isolate impact. If they overlap, note that attribution is ambiguous. |
| Metric shift preceded the flag change | The flag change is unlikely to be the cause. Investigate other changes that occurred before the flag change. The flag change may have been a response to the metric shift (e.g., a kill switch). |
| Service has very low traffic | Use longer windows (up to 24 hours). Accept that confidence will be lower. Consider recommending a higher rollout percentage to generate more signal. |

## What NOT to Do

- **Do not claim causation.** Your analysis establishes correlation and assesses its strength. It does not prove causation. Always use hedged language.
- **Do not ignore confounding factors.** Failing to check for other changes in the window is the single most common source of incorrect attributions.
- **Do not compare windows of different durations.** A 30-minute before window compared to a 2-hour after window will produce skewed results due to different sample sizes and time-of-day effects.
- **Do not assess impact before sufficient soak time.** If the flag changed 5 minutes ago and the service handles 10 requests per minute, you have 50 data points. Wait for adequate data.
- **Do not ignore rollout percentage when interpreting metric magnitude.** A 0.5% error rate increase with a 2% rollout is a very different signal than a 0.5% increase with a 100% rollout.

## References

- [Correlation Methods Reference](references/correlation-methods.md) — detailed guidance on window sizing, rollout-adjusted analysis, confounding factors, statistical considerations, and presenting findings.
- [Service Health Skill](../o11y-service-health/SKILL.md) — use the service health skill for establishing baseline metrics and understanding normal service behavior.
- Feature flag management skills in the `../../feature-flags/` directory — for flag configuration, targeting, and lifecycle management.
