# Health Assessment Criteria

This reference defines how to assess service health by comparing current metrics against baselines, applying severity thresholds, and generating a composite health status. It covers baseline techniques, threshold definitions, severity classification, and common assessment patterns.

## Baseline Comparison Techniques

A baseline is the expected value or range for a metric under normal operating conditions. Without a baseline, you cannot determine whether a metric value is normal, elevated, or critical. Raw numbers are meaningless in isolation — an error rate of 2% might be perfectly normal for one service and a severe regression for another.

### Historical Baselines

The simplest baseline is a historical average: what was this metric's value over the past N days? A 7-day rolling average captures a full week of patterns. A 30-day rolling average captures monthly patterns but may be too slow to reflect recent changes (such as a new deployment that legitimately changed the service's behavior).

Historical baselines work well for stable services with predictable traffic. They work poorly for services undergoing rapid change, services with highly variable traffic, or newly deployed services with insufficient history.

### Rolling Averages

A rolling average continuously updates as new data arrives. Common windows include:

- **1-hour rolling average**: Responsive but noisy. Useful for detecting acute changes but will flag brief transients.
- **4-hour rolling average**: Balances responsiveness and stability. Good for intra-day comparisons.
- **24-hour rolling average**: Captures a full diurnal cycle. Useful for comparing "right now" against "the same general time yesterday."
- **7-day rolling average**: Captures weekly patterns. Useful for comparing "Tuesday afternoon" against "recent Tuesday afternoons."

When computing rolling averages for baselines, exclude known anomaly periods (incidents, maintenance windows, traffic spikes) to prevent them from skewing the baseline.

### Time-of-Day and Day-of-Week Adjustments

Many services have strong temporal patterns. A service might handle 5,000 req/s at 2pm and 200 req/s at 3am. Comparing a 3am metric value against a 24-hour average that includes peak hours will produce misleading results.

Time-of-day adjusted baselines compare the current metric against the same time window on previous days. For example, compare today's 2pm-3pm error rate against the 2pm-3pm error rate from the past 7 Tuesdays (if today is Tuesday). This accounts for both diurnal and weekly patterns.

Day-of-week adjustments are particularly important for B2B services where weekday traffic differs dramatically from weekend traffic. A throughput drop on Saturday that would be alarming on a Tuesday is completely expected.

### Percentile-Based Baselines

Instead of using a single average as the baseline, use a percentile range. For example, the baseline for error rate might be defined as "the p5 to p95 range of error rate values observed during equivalent time windows over the past 14 days." Any current value within that range is normal. Values above p95 are elevated. Values above p99 are critical.

Percentile-based baselines handle variance naturally. A service with highly variable latency will have a wide baseline range, reducing false alarms. A service with very stable latency will have a narrow range, making even small deviations visible.

## Threshold Definitions

### Static Thresholds

Static thresholds are fixed values that do not change over time. Examples:

| Metric | Warning Threshold | Critical Threshold |
|--------|------------------|--------------------|
| 5xx error rate | > 1% | > 5% |
| p99 latency | > 2000ms | > 5000ms |
| p50 latency | > 500ms | > 1500ms |
| Throughput drop | > 30% below baseline | > 60% below baseline |

Static thresholds are simple to implement and easy to understand. However, they do not account for service-specific norms. A 1% error rate threshold is too sensitive for a service that normally runs at 0.8% and too lenient for a service that normally runs at 0.01%.

Use static thresholds as defaults when no baseline data is available, and replace them with dynamic thresholds as baseline data accumulates.

### Dynamic Thresholds

Dynamic thresholds are computed from baseline data. A common approach is to define thresholds as multiples of the baseline standard deviation:

- **Warning**: Current value exceeds baseline mean + 2 standard deviations
- **Critical**: Current value exceeds baseline mean + 3 standard deviations

This approach (similar to Bollinger Bands in financial analysis) adapts to each service's normal variance. A noisy service will have wider thresholds; a stable service will have tighter thresholds.

For error rates, which are bounded at 0 and typically right-skewed, a multiplicative threshold often works better than additive:

- **Warning**: Current error rate exceeds 3x the baseline error rate
- **Critical**: Current error rate exceeds 10x the baseline error rate

For throughput drops, express thresholds as percentage deviations from baseline:

- **Warning**: Throughput is more than 25% below the baseline for this time window
- **Critical**: Throughput is more than 50% below the baseline for this time window

### Setting Thresholds From Baselines

A practical approach to setting thresholds from baseline data:

1. Collect metric values for the same time-of-day and day-of-week over the past 14 to 28 days.
2. Remove outliers (values during known incidents or maintenance).
3. Compute the p50 (median), p90, p95, and p99 of the collected values.
4. Set the warning threshold at the p95 of historical values.
5. Set the critical threshold at a value significantly above p99 (for example, 2x the p99 value).

This method ensures that thresholds reflect what the service actually does, not what someone guesses it should do.

### Common Defaults

When no baseline data is available and you need to make an initial assessment, these defaults provide a reasonable starting point:

**Error Rate (5xx)**:
- Healthy: < 0.5%
- Degraded: 0.5% to 5%
- Critical: > 5%

**Latency (p50)**:
- Healthy: < 200ms
- Degraded: 200ms to 1000ms
- Critical: > 1000ms

**Latency (p99)**:
- Healthy: < 1000ms
- Degraded: 1000ms to 5000ms
- Critical: > 5000ms

**Throughput change from expected**:
- Healthy: within 20% of expected
- Degraded: 20% to 50% deviation
- Critical: > 50% deviation

These defaults are intentionally loose. They should be replaced with service-specific thresholds as soon as baseline data is available. Services with strict SLOs will need much tighter thresholds.

## Severity Classification

### Definitions

**Healthy**: All metrics are within their expected baseline ranges. No action is required. The service is operating normally.

**Degraded**: One or more metrics are outside their normal range but not at critical levels. The service is still functioning but with reduced quality. Users may experience slower responses or occasional errors. Investigation is warranted, and the team should be aware, but this is not an emergency.

**Critical**: One or more metrics are far outside their normal range. The service is experiencing significant issues that are likely affecting users. Immediate investigation and response are needed.

### Mapping Metrics to Severity

Each metric generates its own severity assessment. The rules for mapping a metric value to a severity level:

**Error Rate Severity**:
- Healthy: Error rate is within the baseline range (or below the warning threshold)
- Degraded: Error rate exceeds the warning threshold but is below the critical threshold
- Critical: Error rate exceeds the critical threshold

**Latency Severity**:
- Evaluate p50, p95, and p99 independently
- If any latency percentile exceeds its critical threshold, latency severity is critical
- If any latency percentile exceeds its warning threshold (and none are critical), latency severity is degraded
- Otherwise, latency severity is healthy

**Throughput Severity**:
- Healthy: Throughput is within the expected range
- Degraded: Throughput has deviated significantly from baseline (warning threshold)
- Critical: Throughput has deviated dramatically from baseline (critical threshold)
- Note: Both drops AND unexpected spikes in throughput should be flagged

### Multi-Metric Severity Combining Rules

When combining individual metric severities into an overall service health status, use these rules:

**Rule 1: Worst metric wins (default)**
The overall severity is the worst severity across all metrics. If error rate is healthy, latency is degraded, and throughput is healthy, the overall status is degraded.

**Rule 2: Corroboration for critical**
To reduce false alarms, require at least two metrics to be elevated before declaring the overall status critical. If only one metric is critical and the others are healthy, the overall status is degraded (not critical). This rule acknowledges that a single metric spike may be a measurement artifact.

**Rule 3: Throughput-adjusted error assessment**
If throughput is critically low (near zero), do not trust error rate calculations — the sample size is too small. In this case, the critical signal is the throughput loss itself, not the error rate.

The recommended default is Rule 1 (worst metric wins) for simplicity and safety. Rule 2 can be applied when false alarm reduction is a priority and the cost of a delayed critical assessment is acceptable.

## Assessment Methodology

### Single Metric Assessment

To assess a single metric:

1. Retrieve the current value for the metric over the assessment window (typically 5 minutes).
2. Retrieve the baseline value for the same metric, adjusted for time-of-day and day-of-week if possible.
3. Compare the current value to the baseline.
4. Determine the severity based on how far the current value deviates from the baseline.
5. Record the current value, baseline value, deviation percentage, and resulting severity.

Example: Current p99 latency is 1200ms. Baseline p99 for this time window is 400ms. The current value is 3x the baseline (200% increase). If the warning threshold is 2x and the critical threshold is 5x, the severity is degraded.

### Composite Health Score

A composite health score combines multiple metrics into a single numerical value. One approach:

1. Assign each metric a score from 0 (critical) to 100 (healthy).
2. Apply weighting factors based on metric importance.
3. Compute a weighted average.

Suggested weights:
- Error rate (5xx): 40%
- Latency (p99): 25%
- Latency (p50): 15%
- Throughput stability: 20%

A composite score above 80 is healthy. Between 50 and 80 is degraded. Below 50 is critical.

The composite score is useful for dashboards and trend tracking. For incident triage, the individual metric breakdowns are more useful than the composite number because they point to specific problem areas.

### Weighting Factors

Default weights can be adjusted based on service characteristics:

- **User-facing API services**: Weight error rate and p50 latency more heavily. Users experience error rates and median latency directly.
- **Backend processing services**: Weight throughput and p99 latency more heavily. Processing services need to maintain throughput, and tail latency can cause cascading timeouts.
- **Real-time streaming services**: Weight throughput most heavily. A throughput drop in a streaming service may indicate data loss.

### Confidence Levels

The confidence of a health assessment depends on data quality:

- **High confidence**: Baseline data is available from at least 7 days of equivalent time windows. Current data covers a full assessment window with high throughput (large sample size). All three metric categories (error rate, latency, throughput) have data.
- **Medium confidence**: Baseline data is available but limited (fewer than 7 data points). Current data is complete. Most metric categories have data.
- **Low confidence**: No baseline data available (using static defaults). Current data is sparse (low throughput or partial coverage). One or more metric categories are missing.

Always report the confidence level alongside the health assessment so that consumers of the assessment know how much to trust it.

## Common Assessment Patterns

### Deployment Health Check

When assessing health after a deployment:

1. Compare the post-deployment window (starting from deploy completion) against the pre-deployment window (the period immediately before the deploy).
2. Use a short current window (5-15 minutes post-deploy) and a longer comparison window (1-4 hours pre-deploy).
3. Pay special attention to error rate changes — even small increases immediately after a deploy are significant because they correlate with the change.
4. Check for latency distribution shifts. A new code path or dependency change may shift the entire distribution.
5. Verify throughput is stable — a deploy that causes a throughput drop may indicate crash-looping instances or failed health checks.

Deployment health checks should have lower thresholds than normal monitoring because any regression correlated with a deploy is likely caused by the deploy.

### Incident Triage Assessment

When assessing health during an incident:

1. Focus on the most recent data (1-5 minute windows).
2. Compare against the period just before the incident started (if the start time is known) or against the same time yesterday.
3. Identify which metrics are most affected — this points toward the problem domain.
4. Check for correlated changes across metrics. If error rate and latency both spiked at the same time, they likely share a cause.
5. Check throughput to understand the blast radius — if throughput dropped, the problem may be preventing requests from reaching the service.

During incident triage, speed matters more than precision. A quick directional assessment ("error rate is 10x normal, latency is 3x normal, throughput is stable") is more valuable than a precise composite score.

### Ongoing Monitoring Assessment

For routine health monitoring (periodic checks, dashboard updates):

1. Use longer assessment windows (15-30 minutes) for stability.
2. Compare against well-established baselines (7-28 day rolling baselines, time-adjusted).
3. Track trends over time — is the service gradually getting slower? Is the error rate slowly creeping up?
4. Flag any metric that has been in the degraded range for an extended period (more than 1 hour) even if it has not reached the critical threshold. Sustained degradation warrants investigation.

### Insufficient Data Assessment

When baseline data is unavailable or the service is new:

1. Fall back to static thresholds (see Common Defaults above).
2. Clearly flag that the assessment is low-confidence due to missing baselines.
3. Use the current assessment as the beginning of baseline data collection.
4. If the service has been running for at least a few hours, use the recent history as a short-term baseline (better than nothing, but note the limited data).
5. Recommend establishing a proper baseline period before relying on health assessments for alerting or automated responses.
