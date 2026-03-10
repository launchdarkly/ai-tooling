# Correlation Methods Reference

This document provides detailed guidance on correlating feature flag changes with shifts in service metrics. It covers window sizing, rollout-adjusted analysis, confounding factor identification, statistical considerations, metric comparison techniques, common correlation patterns, and how to present findings.

---

## Before/After Window Sizing

The foundation of flag impact analysis is comparing metrics from a "before" window (pre-change) to an "after" window (post-change). Choosing the right window size is critical to producing meaningful results.

### How to Choose Window Duration

Window duration depends on the service's traffic volume and the granularity of the metrics you are analyzing. The goal is to capture enough data points in each window to establish a reliable baseline and a reliable post-change measurement.

- **High-traffic services** (thousands of requests per minute): A 30-minute to 1-hour window on each side is often sufficient. These services generate enough data points quickly that short windows still yield statistically meaningful comparisons.
- **Medium-traffic services** (hundreds of requests per minute): Use 1-hour to 4-hour windows. This gives enough volume to smooth out natural variance while keeping the analysis tight enough to avoid confounders.
- **Low-traffic services** (fewer than 100 requests per minute): You may need 4-hour to 24-hour windows. With low traffic, short windows will have high variance and make it difficult to distinguish a real change from noise.
- **Batch or periodic services**: If a service processes requests in batches (e.g., every hour or every day), your window must span at least two full cycles to capture representative behavior.

As a general rule, each window should contain at least 1,000 data points (requests, events, or metric samples) for basic confidence, and 10,000 or more for high confidence. If your window cannot achieve this, note it as a limitation in your findings.

### Aligning Windows with the Flag Change Timestamp

Precise alignment is essential. The flag change timestamp is the dividing line between the before and after windows.

- Use the exact timestamp from the flag change event, not an approximate time.
- If the flag change was a gradual rollout (e.g., 0% to 10% over 5 minutes), treat the rollout completion time as the dividing line, or alternatively exclude the rollout transition period entirely and start the "after" window once the rollout stabilized.
- Add a small buffer (1-5 minutes) between the flag change timestamp and the start of the "after" window. This accounts for propagation delay — the time it takes for flag changes to reach all service instances. LaunchDarkly SDKs typically pick up changes within seconds to a couple of minutes, but caching, CDN delays, or long polling intervals can extend this.
- The "before" window should end at the flag change timestamp (or a minute before, to avoid the transition).

Example alignment for a 1-hour window with a flag change at 14:00 UTC:
- Before window: 12:55 to 13:55 UTC
- Buffer: 13:55 to 14:05 UTC (excluded from analysis)
- After window: 14:05 to 15:05 UTC

### Minimum Window Sizes for Statistical Relevance

Even if a service has high traffic, extremely short windows introduce noise:

| Traffic Level | Minimum Before Window | Minimum After Window | Notes |
|---|---|---|---|
| > 5,000 req/min | 15 minutes | 15 minutes | Sufficient data in short windows |
| 1,000-5,000 req/min | 30 minutes | 30 minutes | Standard minimum |
| 100-1,000 req/min | 2 hours | 2 hours | Need longer to accumulate data |
| < 100 req/min | 6 hours | 6 hours | May still be noisy; flag this |
| < 10 req/min | 24 hours | 24 hours | Results will have low confidence |

These are minimums. Larger windows are generally better, as long as they remain clean of confounders.

### Avoiding Windows That Span Other Changes

This is the most common source of false correlations. If your "before" window contains a deployment, or your "after" window contains an infrastructure change, the comparison is tainted.

- Before defining windows, check for other events: deployments, config changes, other flag changes, scaling events, incident remediation actions.
- If a confounding event exists, shrink the window to exclude it, even if this means using a smaller-than-ideal window. A smaller clean window is more valuable than a larger contaminated one.
- If the confounding event cannot be excluded without making the window too small, note it explicitly as a limitation and describe what the confounder was.

---

## Rollout-Adjusted Analysis

Feature flags are often rolled out gradually. A flag at 10% rollout means only 10% of traffic is seeing the new behavior. This has direct implications for metric analysis.

### Accounting for Percentage Rollouts

If a flag is rolled out to X% of traffic, the expected maximum impact on aggregate metrics is proportionally X% of what a full rollout would produce.

- A flag at 10% rollout that introduces a bug causing 100% error rate for affected users would increase the overall service error rate by roughly 10 percentage points (from, say, 0.1% to approximately 10.1% if the flag path is the only source of errors, or more precisely a weighted average).
- For latency, if the flag path adds 200ms of latency and is at 25% rollout, the aggregate p50 might shift less than 200ms because 75% of requests are unaffected. Percentile metrics (p95, p99) are particularly tricky here — the impact depends on where the affected traffic falls in the latency distribution.

When analyzing impact at partial rollout:

1. **Scale your expectations.** If the flag is at 5%, do not expect a 50% error rate increase to be visible in aggregate metrics. It might show up as a 2.5% increase in aggregate error rate, which could be within normal variance.
2. **Prefer segment-level metrics when available.** If your observability platform can filter metrics by a tag or attribute that corresponds to the flag variant (e.g., a request header, user segment, or context attribute), use that to compare "flag on" vs "flag off" traffic directly. This eliminates the dilution problem entirely.
3. **Calculate the expected aggregate impact.** If you know the rollout percentage and the suspected per-request impact, multiply them to get the expected aggregate impact. If the observed aggregate change matches this expected value, it strengthens the correlation.

### Segment-Level Analysis

When possible, segment metrics by the flag's targeting criteria:

- If the flag targets specific user segments (e.g., beta users, internal employees, a specific region), compare metrics for that segment against the rest.
- If the flag uses a percentage rollout, and your observability stack tags requests with the variant they received, compare metrics for variant A vs variant B directly.
- Segment-level analysis is far more powerful than aggregate analysis because it removes the dilution effect and provides a natural control group.

### Comparing Control vs Treatment Groups

If you can identify which requests were served with the flag on (treatment) vs off (control), you have the gold standard of flag impact analysis:

- Compare error rates between the two groups during the same time period. Since both groups are experiencing the same external conditions (traffic patterns, infrastructure state), differences between them are strong evidence of flag impact.
- Check that the groups are comparable in size and composition. If the flag targets a specific segment (e.g., premium users), the control group (non-premium users) may have inherently different behavior.
- Even a small difference between control and treatment, if consistent, can be meaningful — especially because both groups share the same confounders, so those factors cancel out.

---

## Confounding Factor Checklist

Before attributing a metric shift to a flag change, systematically check for other possible causes. Work through this checklist for every analysis.

### Other Deployments in the Same Window

- Check deployment logs, CI/CD pipelines, and release trackers for any code deployments during either the before or after window.
- Even deployments to other services can matter if the service you are analyzing depends on them.
- Database migrations, schema changes, and configuration deployments count as deployments.

### Other Flag Changes

- Check the flag change log for other flags that changed in the same environment during either window.
- Pay special attention to flags on the same service or that affect the same code paths.
- A common scenario: two flags change within an hour of each other, and the metric shift is attributed to the wrong one.

### Traffic Pattern Changes

- Compare overall request volume between the before and after windows. A significant traffic increase or decrease can shift error rates and latency independent of any code or flag change.
- Check for traffic spikes from marketing campaigns, external events, bot traffic, or load testing.
- Time-of-day effects: if the before window was during off-peak hours and the after window spans peak hours (or vice versa), traffic patterns alone could explain metric differences.

### Infrastructure Changes

- Check for scaling events (auto-scaling up or down), instance replacements, or cluster changes.
- Check for changes in downstream dependencies: database failovers, cache flushes, CDN changes.
- Network changes: DNS updates, load balancer configuration changes, firewall rule modifications.
- Cloud provider incidents or maintenance windows.

### External Dependencies

- Check status pages for third-party services your application depends on (payment processors, identity providers, APIs).
- DNS or certificate changes in external services.
- Rate limiting or quota changes imposed by external providers.

### Seasonal and Cyclical Effects

- Day-of-week effects: Monday traffic patterns differ from Saturday patterns.
- Time-of-day effects: early morning vs peak hours.
- Monthly cycles: billing dates, payroll periods.
- Annual cycles: holidays, tax season, back-to-school.
- Compare the after window not just to the immediately preceding before window, but also to the same time period on the previous day or week to check for cyclical patterns.

### Incident Overlap

- Check incident management systems for any ongoing or recently resolved incidents.
- An incident that was in progress during the before window (degraded baseline) or after window (external degradation) will skew the comparison.
- If the flag change was made as part of incident response (e.g., a kill switch), note that the metric shift may have started before the flag change, and the flag change may have been the remediation rather than the cause.

---

## Statistical Considerations

### Sample Size Requirements

Meaningful comparison requires sufficient data in both windows:

- For error rate analysis: you need enough total requests that the expected number of errors is at least 5-10 in each window. If your baseline error rate is 0.1% and you have 1,000 requests, you expect only 1 error — too few to draw conclusions.
- For latency analysis: at least 100 data points per window for p50, at least 1,000 for p95, and at least 10,000 for p99. Tail percentiles require many more samples to be stable.
- For throughput analysis: at least 10 measurement intervals (e.g., 10 one-minute data points) per window.

If sample sizes are insufficient, report this explicitly. A finding of "insufficient data" is valid and useful — it tells the team they need to wait longer or increase rollout percentage before drawing conclusions.

### Significance Thresholds

In a typical operational context, you are not running a formal statistical test with p-values. However, you should apply judgment about what constitutes a meaningful change:

- **Error rate**: A change of more than 2x the baseline variance is likely significant. For example, if error rate normally fluctuates between 0.08% and 0.12%, a post-change error rate of 0.25% is clearly significant. A post-change rate of 0.13% is within normal variance.
- **Latency**: For p50, a change of more than 10-20% is usually significant. For p95/p99, higher variance is normal, so look for changes of 30% or more, or compare against the historical range for those percentiles.
- **Throughput**: Changes of more than 10% that are not explained by traffic volume changes warrant investigation.

When in doubt, compare the magnitude of the observed change against the historical range (min/max over the past week or month). If the post-change value exceeds the historical range, it is likely significant.

### Effect Size Interpretation

Not all statistically detectable changes are operationally meaningful:

- A latency increase from 45ms to 47ms (4.4% increase) may be statistically detectable with large sample sizes but operationally irrelevant.
- Focus on whether the change matters to users or system reliability, not just whether it is detectable.
- Consider the metric in the context of SLOs. If latency increased but is still well within the SLO target, the finding is "detectable but within acceptable bounds."

### Multiple Comparisons Problem

When analyzing many metrics simultaneously (error rate, p50, p95, p99, throughput, etc.), some may show apparent changes by chance:

- If you check 10 metrics, there is a reasonable probability that at least one will show a notable shift purely due to random variance.
- Give more weight to changes that are consistent across related metrics (e.g., p50, p95, and p99 all increased) than to a single metric showing change while others are stable.
- If only one of many metrics shifted, consider whether there is a logical reason the flag would affect that specific metric.

---

## Metric Comparison Techniques

### Absolute Change

The simplest comparison: subtract the before value from the after value.

- Before error rate: 0.5%, After error rate: 1.2%. Absolute change: +0.7 percentage points.
- Useful for communicating impact in concrete terms. "Error rate increased by 0.7 percentage points."
- Less useful when baseline values differ significantly between services or time periods.

### Relative / Percentage Change

Express the change as a percentage of the before value.

- Before error rate: 0.5%, After error rate: 1.2%. Relative change: +140%.
- Useful for comparing impact across services with different baselines.
- Can be misleading with very small baselines: going from 0.001% to 0.003% is a 200% increase but operationally trivial.
- Always present relative change alongside absolute values to avoid misinterpretation.

### Standard Deviation Analysis

Compare the after-window value against the distribution of values in the before window:

- Calculate the mean and standard deviation of the metric during the before window.
- Express the after-window value as the number of standard deviations from the before-window mean.
- A shift of more than 2 standard deviations is notable. More than 3 is strong evidence of a real change.
- This approach naturally accounts for the metric's baseline variability.

### Trend Comparison

Rather than comparing single aggregate values, compare the trend (slope) of the metric over time:

- Was the metric already trending upward before the flag change? If so, a higher value in the after window may be a continuation of an existing trend, not a result of the flag change.
- Plot the metric over time across both windows (or describe the trend). Look for a clear inflection point at or near the flag change timestamp.
- A flat trend in the before window followed by an upward trend starting at the flag change is strong evidence of correlation.

---

## Common Correlation Patterns

### Immediate Step Change

The metric shifts abruptly at (or very shortly after) the flag change timestamp and remains at the new level.

- **What it looks like**: Error rate jumps from 0.1% to 2.5% within minutes of the flag toggle and stays at 2.5%.
- **What it suggests**: Strong correlation. The flag change likely introduced a new code path that directly affects the metric.
- **Confidence**: High, especially if the step aligns precisely with the flag change timestamp and there are no confounders.

### Gradual Degradation

The metric begins shifting after the flag change and continues to worsen over time.

- **What it looks like**: Latency is stable at 50ms before the change, then slowly climbs to 60ms over the next hour, then 80ms over the next two hours.
- **What it suggests**: The flag may have introduced a resource leak, cache pollution, connection pool exhaustion, or other progressive issue.
- **Confidence**: Medium to high. The gradual nature makes it harder to pinpoint, but if the degradation starts at the flag change, correlation is likely. Check for other causes of gradual degradation (e.g., growing queue depth, filling disk).

### Intermittent Impact

The metric is mostly stable but shows periodic spikes or anomalies after the flag change.

- **What it looks like**: Error rate is 0.1% in both windows on average, but the after window has several brief spikes to 5% that were not present before.
- **What it suggests**: The flag may have introduced a race condition, timeout sensitivity, or issue that only manifests under certain conditions (specific inputs, high load, certain user segments).
- **Confidence**: Medium. Intermittent issues are harder to attribute definitively. Look for patterns in the spikes (timing, user segment, request type).

### No-Change Confirmation

Metrics are stable across both windows with no detectable shift.

- **What it looks like**: All metrics (error rate, latency, throughput) show the same mean, variance, and trend in both windows.
- **What it suggests**: The flag change did not measurably affect the service's observable behavior within the analysis window.
- **Confidence**: Confidence in a "no impact" finding depends on window size, traffic volume, and rollout percentage. A no-change finding with a 1% rollout and 15-minute windows is weak. A no-change finding with a 100% rollout and 24-hour windows is strong.
- **Important**: This is a valid and valuable finding. Report it clearly — it gives the team confidence that the flag change is safe, or that the flag change is not the cause of an issue they are investigating.

---

## Presenting Findings

### Evidence-Based Language

Use language that reflects the strength of the evidence without overclaiming:

- **Strong evidence**: "The error rate increase from 0.1% to 2.3% aligns precisely with the flag change at 14:00 UTC, with no other changes detected in the window. This strongly suggests the flag change is responsible."
- **Moderate evidence**: "Latency increased by 15% in the after window. While the timing aligns with the flag change, a deployment to a downstream service occurred 30 minutes into the after window, which may also be a factor."
- **Weak evidence**: "There is a slight increase in p99 latency (from 450ms to 480ms), but this is within the normal daily variance for this service. The flag change may or may not be related."
- **No evidence**: "Metrics are stable across both windows. The flag change does not appear to have impacted error rate, latency, or throughput."

Avoid words like "caused," "definitely," or "proven." Prefer "correlates with," "aligns with," "likely contributed to," "consistent with," or "does not appear to have impacted."

### Confidence Levels

Assign a confidence level to your finding and explain why:

| Level | Criteria | Example |
|---|---|---|
| High | Clear metric shift, precise timing alignment, no confounders, adequate sample size, multiple metrics consistent | Error rate doubled exactly at flag change time, 2-hour clean windows, 50k requests per window |
| Medium | Metric shift present but confounders exist, or sample size is marginal, or timing is approximate | Latency increased but a deployment also happened 1 hour later; or only 500 requests in after window |
| Low | Metric shift is within normal variance, or significant confounders, or very small sample size | p99 slightly elevated but within historical range; only 50 requests in after window |
| Insufficient Data | Not enough traffic, window too short, or metrics not available | Service had 12 requests in the after window; no error rate metrics available |

### Recommended Actions Based on Findings

Tailor your recommendation to the finding:

- **High confidence of negative impact**: Recommend rolling back the flag immediately. Provide the specific metrics that support this recommendation.
- **Medium confidence of negative impact**: Recommend either rolling back as a precaution or increasing monitoring and revisiting the analysis after a longer soak period.
- **Low confidence or no clear impact**: Recommend continuing the rollout with monitoring. Suggest a follow-up analysis after the flag reaches a higher rollout percentage or after more time has passed.
- **Positive impact detected**: Note the improvement. Recommend continuing rollout and verifying that the improvement scales with rollout percentage.
- **Insufficient data**: Recommend waiting for more data before making decisions. Specify what conditions would make the analysis viable (e.g., "Re-analyze after 24 hours at 25% rollout").

Always include the specific numbers, timestamps, and window definitions in your report so that the findings can be verified or revisited.
