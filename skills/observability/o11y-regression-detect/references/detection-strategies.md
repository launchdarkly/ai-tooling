# Detection Strategies Reference

This reference provides detailed guidance on how to detect metric regressions during service rollouts. It covers threshold types, consecutive-check patterns, severity classification, rolling baseline calculation, monitoring intervals, and false positive management. Use this document when configuring regression detection parameters or when you need to understand why a particular detection approach was chosen.

---

## Threshold Types

Thresholds define the boundary between "acceptable" and "regressed" for a given metric. Choosing the right threshold type is critical — too sensitive and you drown in false positives, too lenient and you miss real regressions.

### Static Thresholds

Static thresholds use a fixed, absolute value as the boundary. The metric either exceeds the value or it does not.

**How it works:** You define a hard number. For example, "error rate must not exceed 2%" or "p99 latency must stay below 800ms."

**Example configuration:**

| Metric         | Static Threshold | Unit    |
|----------------|-----------------|---------|
| Error rate     | 2.0             | percent |
| Latency p99    | 800             | ms      |
| Throughput     | 500             | req/s   |

**When to use static thresholds:**

- You have well-understood, stable services with predictable metric ranges.
- Regulatory or SLA requirements define hard limits (e.g., "error rate must never exceed 1% per our SLA").
- The metric has a clear physical or business limit that does not change over time.

**Advantages:**

- Simple to understand and explain. "The threshold is 2%. We crossed it."
- Easy to implement. No baseline computation required.
- Deterministic — the same metric value always produces the same result.

**Disadvantages:**

- Does not adapt to changing baselines. If your service normally runs at 0.1% error rate and then grows to normally run at 0.5% due to increased traffic patterns, a 2% static threshold is now further from normal than it was before, but a regression from 0.5% to 1.5% (a 3x increase) would not trigger it.
- Requires manual tuning. Someone must pick the right number, and that number may become stale.
- Poor for metrics with high natural variance (e.g., latency during peak vs. off-peak hours).

**Concrete example:** A checkout service has an SLA requiring error rates below 1%. You set a static threshold at 1%. During a rollout, error rate climbs from 0.1% to 0.8% — a significant 8x regression — but the static threshold does not fire because 0.8% < 1%. The regression goes undetected until a customer complains. This illustrates the limitation: the static threshold protects the SLA but does not detect meaningful regressions within the SLA boundary.

### Relative Thresholds

Relative thresholds define a boundary as a percentage increase above the current baseline. The threshold moves as the baseline moves.

**How it works:** You compute a baseline (e.g., the average error rate over the last 24 hours is 0.3%) and then define a threshold as "baseline + X%" or "baseline * multiplier." For example, "error rate must not exceed 200% of baseline" means the threshold is 0.6% when the baseline is 0.3%.

**Example configuration:**

| Metric         | Baseline | Relative Threshold | Computed Threshold |
|----------------|----------|--------------------|--------------------|
| Error rate     | 0.3%     | 200% of baseline   | 0.6%               |
| Latency p99    | 250ms    | 150% of baseline   | 375ms              |
| Throughput     | 1200 req/s | 70% of baseline (min) | 840 req/s       |

Note that for throughput, the threshold is a _minimum_ — you are detecting drops, not increases.

**When to use relative thresholds:**

- Most common use case. This is the default recommendation for regression detection.
- The service has a reasonably stable baseline that may shift over time.
- You want to detect meaningful changes relative to what the service normally does, not just absolute limit violations.

**Advantages:**

- Adapts to baseline changes. If the baseline shifts from 0.3% to 0.5% error rate over weeks, the threshold adjusts automatically on the next baseline computation.
- Catches regressions that static thresholds miss. A 3x increase from 0.1% to 0.3% triggers a 200% relative threshold even though absolute values are low.
- Intuitive — "twice the normal error rate" is easy to reason about.

**Disadvantages:**

- Requires baseline computation, which adds complexity.
- If the baseline itself is unhealthy (e.g., computed during a previous incident), the threshold will be too lenient.
- A very low baseline can produce thresholds that are too tight. If baseline error rate is 0.01%, then 200% of baseline is 0.02% — a difference so small it may be noise.

**Concrete example:** A payment service has a baseline p99 latency of 200ms. You set a relative threshold of 150% (300ms). During a rollout, latency climbs to 320ms. The relative threshold fires. If you had used a static threshold of 500ms (a common "safe" value), this 60% latency regression would have gone undetected.

### Adaptive Thresholds

Adaptive thresholds use a rolling baseline combined with standard deviation bands to create a dynamic boundary that accounts for natural variance in the metric.

**How it works:** You compute a rolling mean and standard deviation over a trailing window. The threshold is set at `mean + (N * standard_deviation)`. For example, with N=3 (three sigma), the threshold captures 99.7% of normal variation, and only values beyond three standard deviations trigger.

**Example configuration:**

| Metric         | Rolling Mean | Std Dev | Sigma Multiplier | Computed Threshold |
|----------------|-------------|---------|-------------------|--------------------|
| Error rate     | 0.25%       | 0.05%   | 3                 | 0.40%              |
| Latency p99    | 220ms       | 30ms    | 2.5               | 295ms              |
| Throughput     | 1100 req/s  | 100 req/s | 2               | 900 req/s (min)    |

**When to use adaptive thresholds:**

- Services with high natural variance (e.g., latency that fluctuates significantly by time of day).
- Long-running monitoring where the baseline may shift gradually during the monitoring period.
- When you need to minimize false positives without manual threshold tuning.

**Advantages:**

- Accounts for natural metric variance. A metric that is normally "spiky" gets wider bands; a stable metric gets tighter bands.
- Self-tuning — as the rolling window updates, the threshold adapts.
- Statistically grounded — three sigma thresholds have a clear probabilistic meaning.

**Disadvantages:**

- More complex to implement and explain. "The threshold is the rolling mean plus 2.5 standard deviations" is harder to communicate than "the threshold is 200% of baseline."
- The rolling window must be carefully sized (see Rolling Baseline Calculation below).
- Can be slow to detect regressions if the rolling window is long, because the regression data pulls the mean upward.
- Assumes approximately normal distribution of metric values, which may not hold for all metrics (e.g., latency distributions are often skewed).

**Concrete example:** An API gateway has p99 latency that varies between 150ms and 300ms depending on time of day. A static threshold at 400ms would miss a regression during peak hours (when baseline is already 300ms), and a relative threshold of 150% would false-positive during peak hours if the baseline was computed during off-peak. An adaptive threshold with a 4-hour rolling window and 2.5 sigma multiplier computes: mean=250ms, stddev=50ms, threshold=375ms. During peak hours (baseline ~300ms), the threshold adjusts upward. During off-peak (baseline ~150ms), it tightens. A regression that pushes latency to 450ms fires regardless of time of day.

### Comparison: When to Use Each Type

| Factor                    | Static           | Relative         | Adaptive         |
|---------------------------|------------------|------------------|------------------|
| Implementation complexity | Low              | Medium           | High             |
| Baseline required         | No               | Yes              | Yes (rolling)    |
| Adapts to baseline shifts | No               | On recomputation | Continuously     |
| Handles metric variance   | No               | Partially        | Yes              |
| False positive rate       | Medium-High      | Low-Medium       | Low              |
| Detection speed           | Immediate        | Immediate        | Slower           |
| Best for                  | SLA hard limits  | Most use cases   | Variable workloads |
| Explainability            | High             | High             | Medium           |

**Recommendation:** Start with relative thresholds (200% of baseline for error rate, 150% for latency, 70% floor for throughput). Move to adaptive thresholds only if false positive rates are unacceptable due to metric variance. Use static thresholds as a safety net for absolute limits (e.g., error rate > 50% is always critical regardless of baseline).

---

## Consecutive-Check Patterns

A threshold breach at a single point in time is not sufficient evidence of a regression. Metrics are noisy. Networks have blips. Garbage collection causes latency spikes. Consecutive-check patterns require multiple breaches before signaling a regression, dramatically reducing false positives.

### Why Single-Check Detection Fails

Consider a service with a baseline p99 latency of 200ms and a threshold of 300ms. In a typical 30-minute monitoring window with checks every minute:

- **Transient spikes:** A single garbage collection pause can push p99 latency to 350ms for one check, then it drops back to 210ms. Single-check detection would signal a false regression.
- **Noisy metrics:** Metrics aggregated over short windows (1 minute) naturally have higher variance than those over longer windows (5 minutes). A 1-minute p99 latency measurement can fluctuate 20-40% from the mean due to sampling alone.
- **Network blips:** A brief network partition or DNS timeout can cause a burst of errors that inflates the error rate for one check interval, then resolves on its own.
- **Metric collection delays:** Sometimes metrics arrive late or out of order, causing a single check to reflect an incomplete or skewed picture.

**Real-world data:** In a study of production alerting at a large SaaS provider, single-check alerting produced a false positive rate of approximately 15-25% for latency metrics and 8-12% for error rate metrics. Requiring 3 consecutive breaches reduced false positives to under 2% while adding only 2-4 minutes of detection latency.

### The 3-of-5 Pattern

The 3-of-5 pattern is the most commonly used consecutive-check approach for regression detection. It requires 3 threshold breaches within the last 5 checks to trigger.

**How it works:**

1. Maintain a sliding window of the last 5 check results (breach or no-breach).
2. After each check, count the number of breaches in the window.
3. If 3 or more of the last 5 checks are breaches, signal the regression.

**Example timeline (1-minute check interval):**

| Minute | Error Rate | Threshold (0.6%) | Breach? | Window (last 5) | Count | Signal? |
|--------|-----------|-------------------|---------|------------------|-------|---------|
| 1      | 0.3%      | 0.6%              | No      | [N]              | 0     | No      |
| 2      | 0.7%      | 0.6%              | Yes     | [N, Y]           | 1     | No      |
| 3      | 0.4%      | 0.6%              | No      | [N, Y, N]        | 1     | No      |
| 4      | 0.8%      | 0.6%              | Yes     | [N, Y, N, Y]     | 2     | No      |
| 5      | 0.9%      | 0.6%              | Yes     | [N, Y, N, Y, Y]  | 3     | Yes     |
| 6      | 0.5%      | 0.6%              | No      | [Y, N, Y, Y, N]  | 3     | Yes     |
| 7      | 0.3%      | 0.6%              | No      | [N, Y, Y, N, N]  | 2     | No      |

Notice at minute 5, the pattern triggers. At minute 7, it recovers because there are now only 2 breaches in the window.

**Why 3-of-5 specifically:**

- 3 breaches provide strong evidence — the probability of 3 random independent spikes in 5 checks is low.
- Allowing 2 non-breach checks in the window tolerates brief recoveries during a real regression (metrics can briefly dip below threshold during a genuine regression due to variance).
- With 1-minute checks, detection latency is at most 5 minutes, which is fast enough for rollout monitoring.

### The N-of-M Pattern (Generalized)

The 3-of-5 pattern is a specific instance of the general N-of-M pattern: require N breaches in the last M checks to trigger.

**Common configurations:**

| Pattern | N | M | Use Case | Detection Latency (1-min checks) | False Positive Rate |
|---------|---|---|----------|----------------------------------|---------------------|
| 2-of-3  | 2 | 3 | Fast detection, slightly higher false positives | 3 min max | Medium |
| 3-of-5  | 3 | 5 | Balanced (recommended default) | 5 min max | Low |
| 4-of-6  | 4 | 6 | Conservative, fewer false positives | 6 min max | Very Low |
| 5-of-10 | 5 | 10 | Very conservative, long-running monitors | 10 min max | Minimal |

**Choosing N and M:**

- Higher N/M ratio (e.g., 4-of-5 = 80%) means stricter — fewer false positives but slower detection.
- Lower N/M ratio (e.g., 2-of-5 = 40%) means more sensitive — faster detection but more false positives.
- The recommended sweet spot is N/M between 50% and 70%.
- M should be at least 3 to provide meaningful statistical power.
- M should not exceed about 10-15 because older data becomes less relevant.

### Sliding Window Approach

Instead of counting discrete breaches, the sliding window approach averages the metric over the window and compares the average against the threshold.

**How it works:**

1. Maintain a sliding window of the last M metric values.
2. Compute the window average.
3. If the window average exceeds the threshold, signal the regression.

**Example (5-minute sliding window, 1-minute checks):**

| Minute | Error Rate | Window Values          | Window Avg | Threshold (0.6%) | Signal? |
|--------|-----------|------------------------|-----------|-------------------|---------|
| 1      | 0.3%      | [0.3]                  | 0.30%     | 0.6%              | No      |
| 2      | 0.7%      | [0.3, 0.7]             | 0.50%     | 0.6%              | No      |
| 3      | 0.4%      | [0.3, 0.7, 0.4]        | 0.47%     | 0.6%              | No      |
| 4      | 0.8%      | [0.3, 0.7, 0.4, 0.8]   | 0.55%     | 0.6%              | No      |
| 5      | 0.9%      | [0.3, 0.7, 0.4, 0.8, 0.9] | 0.62% | 0.6%              | Yes     |

**Advantages over N-of-M:** Smoother signal, less sensitive to individual spikes.

**Disadvantages:** Slower to detect sharp regressions because a few normal values in the window drag the average down. A sudden jump from 0.3% to 2.0% error rate would take multiple checks to raise the window average above 0.6%.

**When to use:** Best for metrics that are inherently noisy and where you care about sustained trends rather than sharp transitions. Less appropriate for rollout monitoring where you want to detect regressions quickly.

### Immediate-Critical Pattern

Some thresholds are so severe that a single breach warrants immediate signaling. This is the exception to the "never signal on a single point" rule.

**When to use immediate-critical:**

- Error rate exceeds 50% (half of all requests are failing).
- Service returns zero throughput (complete outage).
- Latency exceeds 10x baseline (severe degradation).
- Health check endpoint returns unhealthy.

**Example configuration:**

| Metric         | Immediate-Critical Threshold | Rationale                        |
|----------------|-----------------------------|---------------------------------|
| Error rate     | > 50%                       | Majority of requests failing     |
| Latency p99    | > 10,000ms (10s)            | Effectively unusable             |
| Throughput     | < 10 req/s (from 1000+)     | Near-complete traffic loss       |
| Health check   | Unhealthy                   | Service self-reports failure     |

These thresholds should be set far beyond any reasonable normal variation. If an immediate-critical threshold fires, the situation is unambiguous.

---

## Severity Classification

Not all threshold breaches are equal. Severity classification enables proportional responses — a warning gets attention, a critical gets action.

### Severity Levels

**Normal** — All monitored metrics are within their thresholds. No action needed.

- Error rate: within baseline + margin
- Latency: within baseline + margin
- Throughput: above minimum floor
- Status: green. Continue monitoring.

**Warning** — A metric is approaching its threshold or has a single isolated breach. Attention warranted but no intervention needed yet.

Trigger conditions (any of):
- Metric exceeds 80% of the distance from baseline to threshold (e.g., baseline is 0.3%, threshold is 0.6%, warning at 0.54%).
- A single threshold breach occurred but consecutive-check pattern is not yet satisfied.
- Two metrics simultaneously exceed 70% of their threshold distance.

Response: Continue monitoring. Note the warning in status reports. Be prepared to escalate.

**Critical** — A sustained threshold breach confirmed by the consecutive-check pattern. Intervention likely needed.

Trigger conditions (any of):
- Consecutive-check pattern satisfied (e.g., 3-of-5 breaches) for any monitored metric.
- Immediate-critical threshold breached (single check sufficient).
- Two or more metrics simultaneously in warning state for more than M checks.

Response: Signal the regression. Provide details on which metric, current value, baseline, threshold, and number of consecutive breaches. Recommend investigation or rollback consideration.

### Mapping Metrics to Severity

Different metrics may warrant different severity mappings based on business impact:

| Metric         | Warning Trigger                  | Critical Trigger                       | Business Rationale                                  |
|----------------|----------------------------------|----------------------------------------|-----------------------------------------------------|
| Error rate     | > 150% of baseline OR > 1%      | 3-of-5 breaches above 200% of baseline | Errors directly impact users                        |
| Latency p99    | > 130% of baseline               | 3-of-5 breaches above 150% of baseline | Latency degrades UX but users can still complete tasks |
| Throughput     | < 85% of baseline                | 3-of-5 checks below 70% of baseline    | Traffic drop may indicate upstream issues or errors  |

### Escalation: Warning to Critical Progression

Severity is not static. A warning can escalate to critical, and a critical can de-escalate.

**Escalation rules:**

1. A metric in warning state that satisfies the consecutive-check pattern escalates to critical.
2. Multiple metrics in warning state simultaneously may escalate the overall status to critical (configurable — default is 2+ metrics in warning = overall critical).
3. A critical status that recovers (consecutive checks clear) de-escalates to warning, then to normal.

**De-escalation rules:**

1. A critical metric must have zero breaches in the last M checks to return to normal.
2. A warning metric must stay below 80% of threshold distance for M checks to return to normal.
3. De-escalation requires the same rigor as escalation — do not prematurely declare "all clear."

---

## Rolling Baseline Calculation

The baseline is the anchor for regression detection. A poorly computed baseline leads to either missed regressions (baseline too high) or excessive false positives (baseline too low).

### How to Compute a Rolling Baseline

1. **Select a trailing window** of metric data. For example, the last 24 hours of 1-minute metric samples = 1,440 data points.
2. **Exclude anomalies** from the window. Remove data points that are more than 3 standard deviations from the mean. This prevents previous incidents from inflating the baseline.
3. **Compute the baseline value:**
   - For error rate and latency: use the mean (or p50/median for skewed distributions).
   - For throughput: use the mean, but also compute the minimum expected value (e.g., p10) to set the floor.
4. **Compute the baseline variance:** Calculate the standard deviation. This is used for adaptive thresholds and for setting warning levels.

**Example calculation:**

Raw p99 latency data over 24 hours (1,440 samples):
- Mean: 220ms
- Median: 210ms
- Standard deviation: 35ms
- 3-sigma outlier threshold: 220 + (3 * 35) = 325ms
- Samples above 325ms: 12 (removed as anomalies)
- Recomputed mean (excluding anomalies): 215ms
- Recomputed standard deviation: 28ms
- **Baseline: 215ms**
- **Relative threshold at 150%: 322ms**
- **Adaptive threshold at 2.5 sigma: 215 + (2.5 * 28) = 285ms**

### Baseline Window Sizing

| Window Duration | Data Points (1-min) | Pros                              | Cons                                    | Recommended For              |
|-----------------|---------------------|-----------------------------------|-----------------------------------------|------------------------------|
| 1 hour          | 60                  | Very responsive to recent changes | Noisy, affected by short anomalies       | Rapid iteration, canary tests |
| 4 hours         | 240                 | Good balance                      | May miss time-of-day patterns            | Short rollouts (< 1 hour)    |
| 24 hours        | 1,440               | Captures full daily cycle         | Slow to adapt, stale if service changed  | Standard rollouts             |
| 7 days          | 10,080              | Captures weekly patterns          | Very slow to adapt, high storage         | Seasonal services             |

**Recommendation:** Use a 24-hour window for most cases. If the service has strong weekly patterns (e.g., much lower traffic on weekends), use 7 days. For rapid canary deployments, 1-4 hours may suffice.

### Time-of-Day and Day-of-Week Adjustments

Many services have predictable traffic patterns: higher load during business hours, lower on weekends. A flat baseline across all hours leads to problems:

- A baseline computed from overnight data will be too low for daytime monitoring, causing false positives.
- A baseline computed from peak hours will be too high for overnight monitoring, missing regressions.

**Solution: Bucketed baselines.**

Compute separate baselines for time-of-day buckets:

| Bucket           | Hours (UTC)  | Baseline Latency | Baseline Error Rate | Baseline Throughput |
|------------------|-------------|-------------------|---------------------|---------------------|
| Off-peak         | 00:00-06:00 | 150ms             | 0.1%                | 200 req/s           |
| Morning ramp     | 06:00-10:00 | 200ms             | 0.2%                | 800 req/s           |
| Peak             | 10:00-18:00 | 280ms             | 0.3%                | 1500 req/s          |
| Evening decline  | 18:00-00:00 | 220ms             | 0.2%                | 600 req/s           |

When monitoring at 14:00 UTC, use the "Peak" baseline. When monitoring at 03:00 UTC, use the "Off-peak" baseline. This prevents time-of-day patterns from triggering false regressions.

### Handling Baseline During Active Rollouts

During a rollout, the baseline must reflect the pre-rollout state, not the current state. If you recompute the baseline during a rollout, the regressed metrics will pollute the baseline, raising it and masking the regression.

**Rules:**

1. **Freeze the baseline** at the start of monitoring. Do not recompute it during the rollout.
2. If the rollout spans multiple hours, the frozen baseline may become stale relative to time-of-day patterns. In this case, use bucketed baselines (computed pre-rollout) and switch buckets as time progresses.
3. If the rollout is paused or rolled back, and monitoring is restarted, recompute the baseline from the post-rollback recovery period.

---

## Monitoring Intervals

The check frequency determines how quickly you can detect regressions and how much data you consume.

### Check Frequency Selection

| Interval | Checks per Hour | Detection Latency (3-of-5) | Data Volume | Best For                       |
|----------|----------------|---------------------------|-------------|-------------------------------|
| 30 sec   | 120            | 2.5 min max               | High        | Canary deployments, critical services |
| 1 min    | 60             | 5 min max                 | Moderate    | Standard rollouts (recommended) |
| 5 min    | 12             | 25 min max                | Low         | Slow rollouts, batch services  |
| 15 min   | 4              | 75 min max                | Very Low    | Long-duration background monitoring |

**Recommendation:** Use 1-minute intervals as the default. This provides a good balance between detection speed (5 minutes worst case with 3-of-5) and data volume.

### Aligning with Metric Aggregation Windows

If your metrics are aggregated in 1-minute windows, checking every 30 seconds will often return the same data point twice. Align your check interval with the metric aggregation window:

- Metric aggregation: 1-minute windows -> check every 1 minute.
- Metric aggregation: 5-minute windows -> check every 5 minutes.
- Metric aggregation: 30-second windows -> check every 30 seconds or 1 minute.

Checking more frequently than the aggregation window wastes resources and produces duplicate data points.

### Minimum Monitoring Duration

Monitoring should continue long enough to have statistical confidence that the rollout is healthy (or unhealthy).

**Guidelines:**

- Minimum: At least M checks (where M is the window size in your N-of-M pattern). With 3-of-5 and 1-minute checks, this is 5 minutes absolute minimum.
- Recommended: At least 15-30 minutes for a standard rollout. This provides 15-30 data points, enough to detect regressions and observe recovery patterns.
- For full rollouts (0% to 100%): Monitor for at least 30 minutes after reaching 100%.
- For staged rollouts (0% -> 10% -> 50% -> 100%): Monitor for at least 10-15 minutes at each stage before proceeding.

---

## False Positive Management

False positives erode trust in monitoring. If the system cries wolf repeatedly, operators will ignore it when a real regression occurs.

### Common Causes of False Positives

| Cause                          | Description                                                                                    | Frequency |
|--------------------------------|-----------------------------------------------------------------------------------------------|-----------|
| Threshold too tight            | Threshold set too close to baseline, normal variance triggers it                              | High      |
| Single-check triggering        | No consecutive-check pattern; transient spikes signal false regressions                       | High      |
| Noisy metrics                  | Short aggregation windows or low-traffic services produce metrics with high natural variance   | Medium    |
| Maintenance windows            | Planned maintenance causes metric anomalies that look like regressions                        | Medium    |
| Stale baseline                 | Baseline computed from old data that no longer reflects current service behavior               | Medium    |
| Deployment artifacts           | Brief metric anomalies during instance restarts (connection draining, cold starts)            | Low-Med   |
| Upstream dependencies          | A dependency (database, external API) has a brief issue unrelated to the rollout              | Low-Med   |
| Clock skew / metric lag        | Metrics arrive late, causing a check to see incomplete data                                   | Low       |

### Mitigation Strategies

**1. Consecutive-check patterns (most impactful)**

As described above, requiring 3-of-5 breaches reduces false positives from transient spikes by approximately 80-90%. This is the single most effective mitigation.

**2. Appropriate threshold margins**

Set thresholds with sufficient margin above baseline:

| Metric     | Minimum Recommended Margin |
|------------|---------------------------|
| Error rate | At least 2x baseline or 0.5% absolute, whichever is greater |
| Latency    | At least 1.5x baseline or 100ms absolute, whichever is greater |
| Throughput | Floor at 70% of baseline (30% drop tolerance) |

The "whichever is greater" clause prevents absurdly tight thresholds when baselines are very low.

**3. Exclude known maintenance windows**

If a maintenance window is scheduled (e.g., database migrations, infrastructure updates), either:
- Pause monitoring during the window and resume after.
- Exclude checks that fall within the maintenance window from the consecutive-check calculation.
- Use a wider threshold during the maintenance window.

**4. Warm-up period exclusion**

Immediately after a deployment starts, instances may experience cold-start effects (cache warming, JIT compilation, connection pool establishment). Exclude the first 1-2 minutes of monitoring from regression detection to avoid false positives from deployment artifacts.

**5. Minimum traffic threshold**

If throughput drops below a minimum level (e.g., < 10 req/s), error rate and latency metrics become statistically unreliable (a single slow request out of 5 produces a 20% error rate or wildly skewed latency). Set a minimum traffic threshold below which regression detection is suspended — report "insufficient data" instead of a false regression.

**Example minimum traffic thresholds:**

| Metric     | Minimum Traffic for Reliable Detection |
|------------|---------------------------------------|
| Error rate | At least 100 requests in the check window |
| Latency p99| At least 50 requests in the check window |
| Latency p50| At least 20 requests in the check window |

**6. Correlation across metrics**

A real regression typically affects multiple metrics: error rate goes up AND latency goes up AND/OR throughput goes down. If only one metric breaches its threshold while others are perfectly normal, the probability of a false positive is higher. Use cross-metric correlation as a confidence booster:

- Single metric in breach + others normal = lower confidence (may be false positive).
- Two metrics in breach simultaneously = higher confidence (likely real regression).
- All metrics in breach = very high confidence (definitely a real regression).

This correlation should influence the urgency of the signal, not whether to signal at all. A single metric in sustained breach (passing the consecutive-check pattern) should still be reported — but the report should note that other metrics are not corroborating.

**7. Regular baseline refresh**

Refresh the baseline periodically (daily or weekly) to prevent staleness. A stale baseline that no longer reflects the service's current behavior is a persistent source of false positives (if the service improved) or missed regressions (if the service degraded).
