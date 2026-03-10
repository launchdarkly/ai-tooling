---
name: o11y-service-health
description: "Pull error rate, latency percentiles (p50/p95/p99), and throughput metrics for a service and classify its status as healthy, degraded, or critical. Use when the user asks 'how is <service> doing', wants a metric snapshot before a rollout, or needs to confirm whether a service is currently healthy or degraded."
license: Apache-2.0
compatibility: Requires LaunchDarkly MCP server with observability tools enabled.
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# Service Health Check

You're using a skill that will guide you through checking the health of a service by examining its key metrics. Your job is to identify the service, pull its health metrics, assess them against baselines, and summarize the overall status.

## Prerequisites

- **LaunchDarkly MCP server** with observability tools enabled and configured.
- **Required MCP tools**:
  - `get-service-metrics` — Fetch error rate, latency percentiles, and throughput for a given service and time window.
  - `get-metric-baselines` — Retrieve historical baseline data for a service's metrics.
- **Optional MCP tools**:
  - `list-services` — Discover available services and their identifiers.

## Core Principles

1. **Metrics in Context** — Raw numbers mean nothing without baselines. An error rate of 2% is healthy for one service and a five-alarm fire for another. Always compare current values against established baselines before drawing conclusions.

2. **Three Pillars** — Always check error rate, latency, AND throughput together. A low error rate with zero throughput is not healthy. High latency with dropping throughput suggests a different problem than high latency with stable throughput. No single metric tells the full story.

3. **Time Windows Matter** — Use the appropriate time window for the question being asked. A deployment health check needs a short post-deploy window compared against the pre-deploy period. An incident triage needs the most recent minutes. A general health check needs enough data to be statistically meaningful.

4. **Signal not Diagnosis** — Health checks identify symptoms, not root causes. The output of this skill is "the service is degraded because error rate is elevated" — not "the service is degraded because the database connection pool is exhausted." Diagnosis is a separate investigation step.

## Workflow

### Step 1: Identify the Service

Determine which service to check. If the user has specified a service name, confirm it matches a known service. If the user is unsure or wants to browse, use `list-services` to discover available services and present the options.

- Accept service names, service IDs, or common aliases.
- If the service name is ambiguous (multiple matches), ask the user to clarify.
- If the service is not found, inform the user and suggest checking the service name or using `list-services`.

### Step 2: Pull Health Metrics

Use `get-service-metrics` to fetch the following for the identified service:

- **Error rate**: 4xx rate and 5xx rate, separately.
- **Latency**: p50, p95, and p99 values.
- **Throughput**: Requests per second.

Pull metrics for two time windows:
- **Current window**: The most recent 5 minutes (or the window appropriate to the question — see Core Principles).
- **Comparison window**: The equivalent time window from 24 hours ago, or a recent baseline period.

See [metric-types.md](references/metric-types.md) for detailed guidance on how each metric is calculated and interpreted.

### Step 3: Assess Against Baselines

Use `get-metric-baselines` to retrieve historical baseline data for the service. If baseline data is available:

- Compare each current metric value against its baseline range.
- Classify each metric as **normal**, **elevated**, or **critical** based on how far it deviates from the baseline.

If baseline data is not available:

- Fall back to static default thresholds (see [health-assessment-criteria.md](references/health-assessment-criteria.md) for defaults).
- Note in the output that the assessment is low-confidence due to missing baselines.

Apply the severity classification rules from [health-assessment-criteria.md](references/health-assessment-criteria.md):
- Assess each metric category independently.
- Combine into an overall status using the worst-metric-wins rule.
- Adjust for throughput context (do not trust error rate if throughput is near zero).

### Step 4: Summarize Status

Present the findings to the user in a clear, structured format:

- **Overall status**: Healthy, Degraded, or Critical.
- **Per-metric breakdown**:
  - Error rate (5xx): current value, baseline value, severity.
  - Error rate (4xx): current value, baseline value, note if unusual.
  - Latency (p50, p95, p99): current values, baseline values, severity.
  - Throughput: current value, baseline value, severity.
- **Notable changes from baseline**: Call out any metric that has changed significantly, even if it has not crossed a severity threshold.
- **Recommended next steps**:
  - If healthy: No action needed. Optionally suggest setting up ongoing monitoring.
  - If degraded: Suggest investigating the elevated metrics. Recommend checking recent deployments, dependency health, or using the log query skill for deeper analysis.
  - If critical: Recommend immediate investigation. Highlight the most affected metrics and suggest starting points for diagnosis.

## Edge Cases

| Scenario | How to Handle |
|----------|---------------|
| Service not found | Inform the user the service was not found. Suggest checking the service name or using `list-services` to discover available services. |
| No baseline data available | Fall back to static default thresholds. Clearly note in the output that the assessment is low-confidence. Recommend establishing baselines for future checks. |
| Metrics partially available | Assess what is available and note what is missing. For example, if latency data is present but error rate is not, assess latency and flag that error rate data was unavailable. |
| Service returning zero throughput | Flag this as a critical finding regardless of error rate or latency values. Zero throughput means the service is not processing requests, which may indicate it is down, unreachable, or has no traffic routed to it. |
| Metric spike is expected (deploy in progress) | If the user indicates a deployment is in progress, note that metric fluctuations during deployment are expected. Suggest re-checking after the deployment stabilizes (typically 5-15 minutes post-deploy). |

## What NOT to Do

- **Don't diagnose root cause.** This skill identifies that a service is unhealthy and which metrics are affected. Root cause analysis is a separate investigation. Point the user toward log analysis or dependency tracing rather than speculating about causes.
- **Don't compare services to each other.** Each service has its own baseline and its own definition of normal. A 200ms p50 latency is excellent for one service and terrible for another. Always compare a service against its own history.
- **Don't alert on a single data point.** A single metric value in a 1-minute window can be noisy. Look at trends over the assessment window. If only one data point is elevated and the surrounding points are normal, it is likely a transient spike rather than a real problem.
- **Don't ignore throughput.** It is tempting to focus on error rate and latency because they directly measure user experience. But throughput provides essential context. Low errors with low traffic may mean the problem is upstream. High errors with high traffic may mean the service is overwhelmed.

## References

- [Metric Types Reference](references/metric-types.md) — Detailed guide to error rate calculations, latency percentile interpretation, throughput patterns, and common pitfalls.
- [Health Assessment Criteria](references/health-assessment-criteria.md) — Baseline comparison techniques, threshold definitions, severity classification, and assessment methodology.
- For deeper investigation after identifying an unhealthy service, see the `o11y-log-query` skill for querying and analyzing service logs.
