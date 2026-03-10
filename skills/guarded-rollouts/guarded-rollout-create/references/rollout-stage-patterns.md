# Rollout Stage Patterns Reference

This reference covers stage progression patterns, soak time guidelines, threshold-setting methodology, rollback configuration, and stage transition criteria for guarded rollouts. Use this document when designing a rollout plan to select the right pattern, set appropriate thresholds, and avoid common pitfalls.

---

## Stage Progression Patterns

Every guarded rollout moves traffic from 0% to 100% through a series of stages. The number of stages, the percentage at each stage, and the soak time between stages depend on how much risk the change carries. Three standard patterns cover the vast majority of use cases.

### Conservative Pattern

**Stages:** 1% &rarr; 5% &rarr; 10% &rarr; 25% &rarr; 50% &rarr; 100%

| Stage | Percentage | Minimum Soak Time | Cumulative Duration |
|-------|-----------|-------------------|---------------------|
| 1     | 1%        | 24 hours          | 24 hours            |
| 2     | 5%        | 24 hours          | 48 hours            |
| 3     | 10%       | 24 hours          | 72 hours            |
| 4     | 25%       | 48 hours          | 120 hours (5 days)  |
| 5     | 50%       | 48 hours          | 168 hours (7 days)  |
| 6     | 100%      | —                 | 7+ days total       |

**When to use:**

- Payment processing systems where a bug means lost revenue or failed transactions
- Authentication and authorization flows where a regression locks users out
- Data pipeline changes where corruption propagates downstream before detection
- Core API changes that affect every downstream consumer
- Any system where the blast radius of a failure is disproportionately large relative to the percentage of traffic affected

**Why this pattern works for high-risk changes:** The 1% stage acts as a canary. At 1% traffic, even a catastrophic failure affects very few users, and the 24-hour soak ensures you capture a full diurnal traffic cycle. The gradual ramp from 5% to 25% gives you increasing confidence while keeping exposure low. The jump from 50% to 100% is the largest single increase, but by that point you have days of clean data across multiple traffic levels.

**Example — payment service rollout:**

A team is rolling out a new payment tokenization flow behind the `new-tokenization-v2` flag. The service processes 50,000 transactions per hour at peak. At 1%, that is 500 transactions per hour — enough to detect a 2% error rate increase within a few hours, but small enough that a total failure affects only 500 users in the worst hour. The 24-hour soak at each early stage ensures the team sees both peak and off-peak traffic patterns before advancing.

### Standard Pattern

**Stages:** 5% &rarr; 25% &rarr; 50% &rarr; 100%

| Stage | Percentage | Minimum Soak Time | Cumulative Duration |
|-------|-----------|-------------------|---------------------|
| 1     | 5%        | 12 hours          | 12 hours            |
| 2     | 25%       | 24 hours          | 36 hours            |
| 3     | 50%       | 24 hours          | 60 hours (2.5 days) |
| 4     | 100%      | —                 | 2.5+ days total     |

**When to use:**

- Most feature flag rollouts that change application behavior
- API endpoint additions or modifications with moderate downstream impact
- UI features that affect user workflows but not data integrity
- Backend optimizations (caching changes, query rewrites) where rollback is clean
- Changes that have passed thorough integration and staging testing

**Why this pattern works for typical changes:** Starting at 5% gives you meaningful traffic volume quickly. Most services with moderate traffic (1,000+ requests per hour) will see 50+ requests per hour at the 5% stage, which is enough to detect significant regressions within a few hours. The 12-hour initial soak captures at least half a diurnal cycle. The 24-hour soaks at 25% and 50% each capture a full cycle.

**Example — feature rollout:**

A team is rolling out a redesigned search results page behind the `search-results-v3` flag. The search service handles 10,000 queries per hour. At 5%, 500 queries per hour hit the new code path. The team monitors error rate, p99 latency, and click-through rate. After 12 clean hours at 5%, they advance to 25% (2,500 queries/hour), soak for 24 hours, then 50% for 24 hours, then 100%.

### Aggressive Pattern

**Stages:** 10% &rarr; 50% &rarr; 100%

| Stage | Percentage | Minimum Soak Time | Cumulative Duration |
|-------|-----------|-------------------|---------------------|
| 1     | 10%       | 4 hours           | 4 hours             |
| 2     | 50%       | 8 hours           | 12 hours            |
| 3     | 100%      | —                 | 12+ hours total     |

**When to use:**

- Low-risk UI changes (copy changes, color updates, layout tweaks)
- Features that have already been fully validated in a staging environment with production-like traffic
- Changes behind a flag that is already partially rolled out and you are expanding
- Rollouts in non-critical environments (internal tools, dev-facing dashboards)
- Re-rolling out a previously rolled-back change after fixing the root cause

**Why this pattern works for low-risk changes:** The 10% starting point provides immediate meaningful traffic. The 4-hour soak is long enough to detect obvious regressions (error spikes, latency jumps) but short enough to complete the rollout within a business day. This pattern assumes the change has been well-tested and the team has high confidence; the guarded rollout is a safety net, not the primary validation mechanism.

**Example — copy change rollout:**

A team is updating button labels and help text across the application behind the `updated-copy-q1` flag. The change is purely cosmetic with no logic changes. At 10%, they soak for 4 hours to confirm no unexpected errors (broken string interpolation, missing translations). At 50%, they soak for 8 hours. Total rollout completes in under a day.

---

## Soak Time Guidelines

### Why Soak Time Matters

Soak time is the minimum duration a rollout stage must run before advancing to the next stage. It exists because many failure modes are not immediately apparent:

- **Latency degradation under load:** A code path may perform well at low concurrency but degrade as connection pools saturate or caches fill.
- **Memory leaks:** Gradual memory growth may not trigger alerts for hours but will eventually cause out-of-memory crashes or garbage collection pauses.
- **Downstream cascading failures:** A change that increases load on a downstream service may not cause visible problems until that service's resources are exhausted.
- **Time-dependent bugs:** Code that runs differently based on time of day, day of week, or scheduled jobs may only fail during specific windows.
- **Traffic pattern sensitivity:** A change may work fine during off-peak hours but fail under peak load due to contention, rate limiting, or resource constraints.

### Minimum Soak Times Per Stage

These are minimums. Longer soak times are always safer.

| Risk Level    | Early Stages (< 25%) | Mid Stages (25%-50%) | Final Stage (50%-100%) |
|--------------|----------------------|----------------------|------------------------|
| Conservative | 24 hours             | 48 hours             | 48 hours               |
| Standard     | 12 hours             | 24 hours             | 24 hours               |
| Aggressive   | 4 hours              | 8 hours              | —                      |

### Traffic-Based vs Time-Based Soak

**Time-based soak** is the most common approach: wait N hours before advancing. It is simple and captures diurnal traffic patterns. Use time-based soak as the default.

**Traffic-based soak** requires a minimum number of requests (or events, or transactions) before advancing. It is useful when:

- The service has highly variable traffic (e.g., 100x difference between peak and off-peak)
- The service has very low traffic where time-based soak may not produce enough data points
- You need statistical confidence in your metrics (e.g., you need at least 10,000 requests to detect a 0.1% error rate increase)

**Recommended traffic minimums by stage:**

| Stage Percentage | Minimum Requests at Stage | Rationale |
|-----------------|--------------------------|-----------|
| 1%              | 1,000                    | Enough to detect 1%+ error rate increase with confidence |
| 5%              | 5,000                    | Enough to detect 0.5% error rate increase |
| 10%             | 10,000                   | Enough to detect 0.3% error rate increase |
| 25%+            | 25,000                   | Enough to detect 0.2% error rate increase and measure latency percentiles accurately |

If your service processes fewer than 100 requests per hour, consider using traffic-based soak with lower minimums, and accept that you will have less statistical confidence. In this case, lean toward the conservative pattern with longer time-based soaks as a supplement.

### Off-Peak Considerations

Many failure modes only manifest under peak load. A soak period that runs entirely during off-peak hours (e.g., 2 AM to 6 AM) may miss load-dependent issues. Guidelines:

- **Minimum soak of 12 hours** ensures you capture at least part of a peak period, regardless of when the stage started.
- **Minimum soak of 24 hours** ensures you capture a full peak-to-peak cycle.
- **Avoid advancing stages at night.** If a stage completes its soak time at 3 AM, wait until business hours to advance so the team is available to respond if the next stage causes issues.
- **Weekend considerations:** If your service has significantly different weekend traffic, consider extending soak times to cover at least one weekday peak if the stage started on a Friday.

### What "Sufficient Soak" Means

A stage has been sufficiently soaked when ALL of the following are true:

1. The minimum soak time for the risk level has elapsed.
2. The minimum traffic volume has been reached (if using traffic-based soak).
3. All monitored metrics have remained within their thresholds for the entire soak period (not just at the end).
4. At least one peak traffic period has occurred during the soak (for stages with 12+ hour soak times).
5. No anomalies have been observed that require investigation, even if they did not breach thresholds.

---

## Threshold-Setting Methodology

Thresholds determine when the system automatically halts or rolls back a rollout. Setting them correctly is the most important part of guarded rollout configuration. Thresholds that are too tight cause false rollbacks that erode trust in the system. Thresholds that are too loose miss real regressions.

### Error Rate Thresholds

#### Absolute vs Relative Thresholds

**Absolute threshold:** "Roll back if error rate exceeds 2%." Simple to understand but ignores the baseline. If the service already has a 1.8% error rate, a 2% threshold gives almost no room for regression detection.

**Relative threshold (baseline-relative):** "Roll back if error rate exceeds baseline + 0.5 percentage points" or "Roll back if error rate exceeds 2x baseline." Adapts to the current state of the service.

**Recommendation:** Use baseline-relative thresholds as the primary mechanism, with an absolute ceiling as a safety net.

#### Recommended Starting Points for Error Rate

| Service Baseline Error Rate | Recommended Threshold | Absolute Ceiling |
|----------------------------|----------------------|------------------|
| < 0.1%                     | Baseline + 0.5pp     | 1.0%             |
| 0.1% - 0.5%               | Baseline + 0.5pp     | 2.0%             |
| 0.5% - 1.0%               | Baseline + 1.0pp     | 3.0%             |
| 1.0% - 2.0%               | Baseline × 2.0       | 5.0%             |
| > 2.0%                     | Baseline × 1.5       | 10.0%            |

*pp = percentage points*

**Example:** A service has a baseline error rate of 0.3%. Using the table: threshold = 0.3% + 0.5pp = 0.8%, with an absolute ceiling of 2.0%. If the error rate rises to 0.9%, the rollout halts. If some unrelated issue pushes errors to 2.1%, the rollout also halts (absolute ceiling).

#### What Counts as an "Error"

Define this clearly before setting thresholds:

- HTTP 5xx responses (always)
- HTTP 4xx responses (sometimes — 400 Bad Request may indicate a contract change; 404 may indicate a routing change; 401/403 may indicate an auth regression)
- Application-level error codes returned in 200 responses (common in GraphQL and RPC systems)
- Timeouts (usually yes, as they indicate latency issues)
- Circuit breaker trips on downstream calls (yes, if monitored)

### Latency Thresholds

#### p50 vs p99 Thresholds

**p50 (median) latency** captures the typical user experience. A p50 regression means most users are affected.

**p99 latency** captures the worst-case user experience. A p99 regression may only affect 1% of users but often indicates a systemic issue (e.g., a slow database query that triggers under specific conditions).

**Recommendation:** Monitor both. Set thresholds on both. The p99 threshold should be looser than the p50 threshold because p99 is inherently noisier.

#### Recommended Starting Points for Latency

**Absolute increase limits:**

| Baseline Latency (p50) | p50 Threshold          | p99 Threshold            |
|------------------------|------------------------|--------------------------|
| < 50ms                 | Baseline + 20ms        | Baseline p99 + 100ms     |
| 50ms - 200ms           | Baseline + 50ms        | Baseline p99 + 200ms     |
| 200ms - 500ms          | Baseline + 100ms       | Baseline p99 + 500ms     |
| 500ms - 2000ms         | Baseline + 200ms       | Baseline p99 + 1000ms    |
| > 2000ms               | Baseline × 1.3         | Baseline p99 × 1.5       |

**Percentage increase limits (alternative approach):**

| Risk Level    | p50 Increase Limit | p99 Increase Limit |
|--------------|-------------------|-------------------|
| Conservative | 10%               | 25%               |
| Standard     | 20%               | 50%               |
| Aggressive   | 30%               | 75%               |

**Example:** A service has baseline p50 of 120ms and p99 of 450ms. Using the absolute increase table: p50 threshold = 120ms + 50ms = 170ms, p99 threshold = 450ms + 200ms = 650ms. Using the percentage table (standard): p50 threshold = 120ms × 1.2 = 144ms, p99 threshold = 450ms × 1.5 = 675ms. The team chooses whichever approach better fits their SLO.

### Throughput Thresholds

Throughput thresholds detect traffic drops, which can indicate that requests are failing silently, timing out, or being rejected before they are counted as errors.

#### Drop Detection

Set a throughput floor relative to the expected traffic level:

| Traffic Level          | Minimum Throughput Threshold |
|-----------------------|-----------------------------|
| < 100 requests/hour   | Baseline × 0.5 (50% drop)  |
| 100-1000 requests/hour| Baseline × 0.7 (30% drop)  |
| 1000+ requests/hour   | Baseline × 0.8 (20% drop)  |

**Important:** Throughput naturally varies with time of day. Use a time-adjusted baseline (compare to the same hour on a previous day) rather than a flat average. If your monitoring system does not support time-adjusted baselines, use the lowest normal throughput as your baseline (typically the overnight minimum) and set the threshold below that.

#### Minimum Traffic Requirements

Before any threshold evaluation is meaningful, you need enough traffic to measure. Set a minimum traffic requirement per stage:

- **At least 100 requests** before evaluating error rate thresholds
- **At least 500 requests** before evaluating latency percentile thresholds
- **At least 1 hour of traffic** before evaluating throughput thresholds

If these minimums are not met within the soak time, extend the soak time rather than advancing without data.

### How to Set Thresholds from Baseline Data

Follow this process:

1. **Collect baseline data** for at least 7 days (to capture day-of-week variation). Use `get-service-metrics` or equivalent to pull error rate, p50 latency, p99 latency, and throughput.

2. **Calculate summary statistics:**
   - Mean error rate over the period
   - Maximum error rate during the period (to understand natural spikes)
   - Mean and max p50 latency
   - Mean and max p99 latency
   - Minimum throughput (to understand natural dips)

3. **Set thresholds above the natural variation:** Your threshold must be above the maximum observed value during normal operation. If the error rate naturally spikes to 0.8% during deployments, setting a threshold at 0.7% will cause false rollbacks.

4. **Apply the formulas from the tables above** using the mean as the baseline and verifying that the resulting threshold is above the observed maximum.

5. **Add a safety margin** of 10-20% above the calculated threshold to account for natural variation not captured in the baseline period.

**Example — full threshold calculation:**

Baseline data for `checkout-service` over 7 days:
- Error rate: mean 0.4%, max 0.7% (spike during a dependency restart)
- p50 latency: mean 85ms, max 110ms (during peak hours)
- p99 latency: mean 320ms, max 580ms (during peak hours)
- Throughput: mean 5,200 req/hr, min 1,100 req/hr (overnight)

Threshold calculation:
- Error rate: baseline (0.4%) + 0.5pp = 0.9%. Check: 0.9% > 0.7% (max observed). Good. Add 10% margin: 0.99%, round to 1.0%.
- p50 latency: baseline (85ms) + 50ms = 135ms. Check: 135ms > 110ms (max observed). Good. Add 10% margin: 148ms, round to 150ms.
- p99 latency: baseline (320ms) + 200ms = 520ms. Check: 520ms < 580ms (max observed). Not good — threshold would be breached by normal traffic. Adjust to 580ms + 20% margin = 696ms, round to 700ms.
- Throughput floor: 1,100 req/hr × 0.8 = 880 req/hr.

### Threshold Adjustment Over Time

Thresholds are not set-and-forget. Adjust them:

- **After a rollout completes:** The new baseline may be different. Recalculate for the next rollout.
- **After a false rollback:** Investigate whether the threshold was too tight or the metric was legitimately anomalous. If the threshold was too tight, widen it by 10-20%.
- **After a missed regression:** Investigate whether the threshold was too loose. Tighten it based on the actual impact observed.
- **Seasonally:** Services with strong seasonal patterns (e.g., e-commerce with holiday peaks) may need different thresholds at different times of year.

---

## Rollback Configuration

### Automatic vs Manual Rollback

**Automatic rollback** means the system reverts the flag to its pre-rollout state without human intervention when a threshold is breached. This is the recommended default for all guarded rollouts.

**Manual rollback** means the system alerts the team when a threshold is breached but does not revert automatically. The team investigates and decides whether to roll back or adjust thresholds. Use manual rollback only when:

- The cost of a false rollback is very high (e.g., a data migration that is painful to undo)
- The team has high confidence in their ability to respond quickly to alerts
- The metrics being monitored are known to be noisy and thresholds cannot be set tightly enough to avoid false positives

**Recommendation:** Default to automatic rollback. Switch to manual only with explicit justification.

### Rollback Triggers

A rollback is triggered when ANY of the following occur:

1. **Threshold breach:** Any monitored metric exceeds its threshold for a sustained period (typically 5-10 minutes, not a single data point).
2. **Sustained threshold proximity:** A metric stays within 90% of its threshold for an extended period (e.g., error rate at 0.9% with a 1.0% threshold for 30+ minutes). This may indicate a slow degradation that will eventually breach.
3. **Manual trigger:** A team member manually initiates a rollback based on observations not captured by automated thresholds (e.g., customer reports, qualitative issues).
4. **Dependent service failure:** If a critical dependency goes down during a rollout, it may be prudent to roll back even if the rollout itself is not causing the issue, to reduce variables during incident response.

### What Rollback Means at Different Stages

| Stage       | Rollback Behavior                                                                 |
|-------------|-----------------------------------------------------------------------------------|
| 1% - 5%    | Revert to 0%. Impact is minimal. Investigate freely.                              |
| 10% - 25%  | Revert to 0%. Moderate number of users may notice the feature disappearing.       |
| 50%         | Revert to 0%. Significant user impact. Communicate if the feature was visible.    |
| 100%        | Guarded rollout is complete; rollback is now a manual flag toggle, not part of the guarded rollout. |

**Important:** Rolling back does not mean the feature is permanently abandoned. It means the current rollout attempt has been halted. The team should investigate, fix the root cause, and start a new guarded rollout.

---

## Stage Transition Criteria

Before advancing from one stage to the next, ALL of the following must be satisfied:

### Required Criteria

1. **All metrics within thresholds.** Every monitored metric (error rate, p50 latency, p99 latency, throughput) must be within its configured threshold. Not just "currently within threshold" — it must have been within threshold for the entire soak period (or at least 95% of it, to allow for transient spikes).

2. **Minimum soak time elapsed.** The stage must have been running for at least the configured soak time. There are no shortcuts. If the soak time is 24 hours and everything looks perfect after 6 hours, you still wait.

3. **Minimum traffic volume seen.** The stage must have processed enough traffic to make the metric evaluations statistically meaningful. See the traffic minimums in the Soak Time Guidelines section.

### Recommended Criteria

4. **No active incidents.** If there is an ongoing incident affecting the service or its dependencies, do not advance. Wait until the incident is resolved and metrics have stabilized.

5. **Team availability.** Do not advance a stage if the team will be unavailable for the next soak period (e.g., do not advance on a Friday evening if no one monitors over the weekend).

6. **No anomalies under investigation.** If someone on the team has flagged a metric pattern as "unusual but not threshold-breaching," investigate before advancing.

---

## Common Mistakes

### Thresholds Too Tight — False Rollbacks

**Symptom:** The rollout keeps getting rolled back even though there is no real problem. The team starts to distrust the guarded rollout system.

**Causes:**
- Threshold set below the natural maximum variation of the metric
- Not accounting for diurnal traffic patterns (peak hours have higher latency)
- Not accounting for periodic events (batch jobs, cache refreshes, garbage collection pauses)
- Using a flat baseline instead of a time-adjusted baseline

**Fix:** Review the baseline data. Look specifically at the maximum observed values during normal operation. Set thresholds above those maximums with a 10-20% margin.

### Thresholds Too Loose — Missing Real Issues

**Symptom:** A rollout completes but users report problems that the thresholds did not catch.

**Causes:**
- Threshold set so far above baseline that only catastrophic regressions are detected
- Monitoring the wrong metrics (e.g., monitoring overall error rate when the regression only affects a specific endpoint)
- Not monitoring enough metrics (e.g., only error rate, missing latency degradation)

**Fix:** Tighten thresholds to be closer to baseline. Add more specific metrics (per-endpoint, per-operation). Consider adding business metrics (conversion rate, completion rate) alongside technical metrics.

### Skipping Early Stages

**Symptom:** The team jumps from 0% to 25% or 50% because "the change is simple." Then a regression affects a large number of users.

**Why this happens:** Confidence bias. The team tested thoroughly in staging and believes the change is safe. But production has traffic patterns, data distributions, and edge cases that staging does not replicate.

**Fix:** Always start at a low percentage. Even the aggressive pattern starts at 10%. The early stages are cheap (low traffic, short soak times) and provide disproportionate safety value.

### Insufficient Soak Time

**Symptom:** A regression manifests hours or days after advancing past a stage.

**Causes:**
- Memory leaks that take hours to cause problems
- Cache warming effects that mask latency issues until caches expire
- Downstream services that degrade gradually under increased load
- Time-dependent code paths that only execute during specific hours

**Fix:** Respect the minimum soak times. For critical services, consider extending soak times beyond the minimums. If you have experienced late-manifesting issues in the past, add extra soak time at the stages where those issues would have been caught.

### Setting Thresholds Without Baseline Data

**Symptom:** The team picks "round numbers" for thresholds (1% error rate, 500ms latency) without knowing what the current baseline is. These numbers may be wildly wrong in either direction.

**Fix:** Always measure the baseline first. Use `get-service-metrics` or your observability platform to collect at least 7 days of data before configuring thresholds. If baseline data is truly unavailable (brand-new service, no historical metrics), use the conservative pattern with wide thresholds and plan to tighten them after the first rollout provides data.

### Ignoring Throughput Monitoring

**Symptom:** Error rate and latency look fine, but traffic has silently dropped because requests are being rejected or timing out at a layer not captured by those metrics.

**Fix:** Always include throughput monitoring. A significant drop in throughput is a signal that something is wrong, even if the requests that do succeed look healthy.

---

## Quick-Reference: Choosing a Pattern

| Question | Conservative | Standard | Aggressive |
|----------|-------------|----------|------------|
| Does a failure affect money or data integrity? | Yes | — | — |
| Has this exact change been validated with prod-like traffic? | — | — | Yes |
| Is the change purely cosmetic / copy? | — | — | Yes |
| Is this a first-time rollout of new logic? | — | Yes | — |
| Does the team have low confidence in test coverage? | Yes | — | — |
| Is the service low-traffic (< 100 req/hr)? | Yes | — | — |
| Does the team need the rollout done today? | — | — | Yes |

If multiple columns apply, choose the more conservative option.
