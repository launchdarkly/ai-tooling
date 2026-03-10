# Metric Types Reference

This reference covers the core metric types used in service health assessments: error rates, latency percentiles, and throughput. Understanding how each metric is calculated, what it reveals, and how to interpret it correctly is essential for accurate health checks.

## Error Rate Calculations

### Error Rate vs Error Count

Error count is the raw number of errors observed in a given time window. Error rate is the proportion of requests that resulted in an error, expressed as a percentage:

```
error_rate = (error_count / total_request_count) * 100
```

Error count alone is misleading. A service handling 10 requests per second with 5 errors is in serious trouble (50% error rate). A service handling 10,000 requests per second with 5 errors is essentially healthy (0.05% error rate). Always prefer error rate over error count when assessing health.

### 4xx vs 5xx Distinction

HTTP status codes in the 400-499 range (4xx) indicate client errors. These are requests where the client sent something invalid — a malformed payload, a missing authentication token, a request for a resource that does not exist. While a sudden spike in 4xx errors may indicate a client-side problem or a breaking API change, 4xx errors do not generally indicate that the service itself is unhealthy.

HTTP status codes in the 500-599 range (5xx) indicate server errors. These are requests where the service failed to fulfill a valid request. A 500 Internal Server Error, 502 Bad Gateway, 503 Service Unavailable, or 504 Gateway Timeout all point to problems within the service or its dependencies. 5xx errors are the primary signal for service health.

When calculating error rate for health purposes, use 5xx error rate as the primary indicator. Track 4xx error rate separately as a secondary signal. A combined error rate (4xx + 5xx) can obscure the picture — a service with a 10% combined error rate might have 9.5% 4xx (client issues) and 0.5% 5xx (service is fine), or it might have 1% 4xx and 9% 5xx (service is in trouble).

### Calculating Error Rate From Different Sources

Error rates can be derived from multiple sources, and the numbers will not always agree:

- **Load balancer metrics**: Captures all requests that reach the load balancer, including those rejected before reaching the service. Useful for the broadest view but may include errors the service never saw.
- **Application-level metrics (APM)**: Captures errors as seen by the application code. This is typically the most accurate source for service health because it reflects what the service actually experienced.
- **Log-derived error rates**: Calculated by counting error-level log entries against total request log entries. Accuracy depends on logging completeness. If the service fails to log certain errors, or logs non-error events at the error level, the rate will be skewed.
- **Synthetic monitor results**: Error rates from synthetic checks reflect availability from a specific vantage point. They are useful for validating that the service is reachable and responding correctly but represent a tiny fraction of actual traffic.

When multiple sources are available, prefer APM metrics for service health. Use load balancer metrics to cross-validate. Note discrepancies between sources — they often reveal interesting problems (for example, a load balancer showing errors that the application does not see may indicate the application is crashing before it can log the error).

### Error Rate Time Windows

Error rate should be calculated over a meaningful time window. A 1-minute window is useful for detecting acute spikes but will be noisy. A 5-minute window smooths out brief transients while still catching real problems. A 15-minute or 30-minute window provides a stable signal but may be too slow to catch fast-moving incidents.

For health checks, a 5-minute current window compared against a 1-hour or 24-hour baseline is a reasonable default.

## Latency Percentile Interpretation

### What Percentiles Mean

A percentile represents the value below which a given percentage of observations fall. For latency:

- **p50 (median)**: 50% of requests completed faster than this value, and 50% were slower. This represents the typical user experience. If p50 is 120ms, a typical request takes about 120ms.
- **p95**: 95% of requests completed faster than this value. Only 5% of requests were slower. This represents the experience of users who are having a somewhat bad time. If p95 is 500ms, then 1 in 20 requests takes longer than half a second.
- **p99**: 99% of requests completed faster than this value. Only 1% of requests were slower. This represents the tail — the worst-case experience for most users. If p99 is 2000ms, then 1 in 100 requests takes longer than 2 seconds.

### Why Each Percentile Matters

**p50** tells you about the common case. If p50 increases, the majority of your users are affected. A p50 regression is broad impact but may be moderate severity per user.

**p95** tells you about the edge of normal. Many SLOs (Service Level Objectives) are defined at p95 because it captures the experience of users who are not in the happy path. A p95 regression means a meaningful minority of users are experiencing degraded performance.

**p99** tells you about the tail. Tail latency matters because individual users make many requests during a session. If p99 is bad, a user making 100 requests will likely experience that bad latency at least once. For services that are called by other services (backend-to-backend), p99 is critical because a single slow dependency call can make the entire parent request slow.

### How to Read Percentile Distributions

When all three percentiles move together (p50, p95, and p99 all increase by a similar factor), the entire latency distribution has shifted. This usually indicates a systemic change — a slower dependency, increased load, or a code change that added latency to all requests.

When p99 increases but p50 stays flat, something is affecting only a subset of requests. This could be a specific endpoint, a specific query pattern, a database lock, or garbage collection pauses. The tail is getting worse while most requests are fine.

When p50 increases but p99 stays roughly the same, the common case got slower but the worst case did not change. This is less common but can happen when a frequently-hit code path gets slower while the already-slow paths are unchanged.

The ratio between percentiles is informative. A healthy service often has p99/p50 ratios between 3x and 10x. If p99 is 50x or 100x the p50, the service has extreme tail latency, which often indicates resource contention, lock contention, or periodic background work interfering with request processing.

### Apdex Scores

Apdex (Application Performance Index) is a standardized way to convert latency into a satisfaction score between 0 and 1. It requires defining a target latency threshold T:

- Requests completing in less than T are "satisfied"
- Requests completing between T and 4T are "tolerating"
- Requests completing in more than 4T are "frustrated"

```
apdex = (satisfied_count + (tolerating_count / 2)) / total_count
```

An Apdex score of 1.0 means all users are satisfied. A score of 0.5 means roughly half the users are having a poor experience. Scores below 0.7 generally indicate a problem.

Apdex is useful as a single summary number but it hides distribution details. Two services can have the same Apdex score with very different latency profiles. Use Apdex as a quick summary, then look at individual percentiles for detail.

## Throughput Patterns

### Requests Per Second

Throughput is measured in requests per second (req/s) or requests per minute (rpm). It tells you how much work the service is doing. Throughput alone does not indicate health, but changes in throughput provide critical context for interpreting other metrics.

### Normal Patterns

Most services exhibit predictable throughput patterns:

- **Diurnal patterns**: Traffic follows the wake/sleep cycle of users. B2C services typically peak mid-morning to early evening in the user's timezone. Traffic drops overnight.
- **Weekly patterns**: Weekday traffic often differs from weekend traffic. B2B services may see minimal weekend traffic while B2C services may see higher weekend traffic depending on the domain.
- **Seasonal patterns**: E-commerce services spike during holidays. Tax services spike in April. Event-driven services spike around specific events.

Understanding normal patterns is essential for baseline comparison. A throughput of 500 req/s might be perfectly normal at 2pm on a Tuesday but very unusual at 3am on a Sunday.

### Capacity Indicators

Throughput trends over weeks and months reveal capacity needs. If throughput is steadily increasing, the service is growing and will eventually need more capacity. If throughput has plateaued, growth may have stalled or the service may be at capacity (requests are being rejected or queued).

A sudden drop in throughput is often more alarming than a sudden increase. A drop may indicate that an upstream service stopped sending traffic (possibly because it is failing), that a load balancer is routing traffic elsewhere, or that the service is rejecting requests before they are counted.

A sudden increase in throughput may indicate a traffic spike (legitimate or attack), a retry storm from a client, or a batch job that was accidentally pointed at the production service.

### Throughput and Error Rate Correlation

Always examine throughput when evaluating error rate. Consider these scenarios:

- Error rate drops from 5% to 0.1% while throughput drops from 1000 req/s to 2 req/s. The service did not get healthier — traffic stopped arriving, and the few requests that trickle in happen to succeed. The underlying problem may still exist.
- Error rate increases from 0.1% to 2% while throughput increases from 1000 req/s to 5000 req/s. The service may be fine — it could be hitting capacity limits under unusual load. Or a traffic spike is exposing a latent bug.
- Error rate increases from 0.1% to 5% while throughput remains stable at 1000 req/s. The service is genuinely degraded. The same volume of traffic is now producing more errors.

## Metric Sources

### APM Tools

Application Performance Monitoring tools (Datadog APM, New Relic, Dynatrace, Honeycomb, Lightstep) instrument the application code to capture per-request data. They provide the most detailed and accurate view of service behavior, including per-endpoint breakdowns, dependency call latency, and error classification.

APM data is typically the best source for health assessments because it reflects what the application actually experienced.

### Custom Metrics

Services often emit custom metrics for business-specific indicators — items in cart, payments processed, search queries executed. These can be valuable secondary signals. If the service reports healthy error rates and latency but the "orders processed per minute" metric has dropped to zero, something is wrong that the standard metrics do not capture.

### Log-Derived Metrics

Metrics can be extracted from structured logs by counting events, parsing latency values from log fields, or categorizing log entries by level. Log-derived metrics are useful when APM instrumentation is not available but are inherently less precise. They depend on the service logging consistently and correctly, and the log processing pipeline introducing minimal delay.

### Infrastructure Metrics

CPU utilization, memory usage, disk I/O, network throughput, and container-level metrics describe the environment the service runs in. They do not directly measure service health but provide context. A service with high error rates and 98% CPU utilization has a different problem than a service with high error rates and 20% CPU utilization.

## Common Pitfalls

### Averaging Percentiles

Never average percentile values across instances or time windows. If instance A has a p99 of 200ms and instance B has a p99 of 800ms, the overall p99 is NOT 500ms. Percentiles must be computed from the merged data set or approximated using histogram merging techniques (like DDSketch or HDR Histogram).

If you only have pre-computed percentiles from individual sources, you can use the maximum of the individual percentiles as a rough upper bound, but this is also not accurate. The correct approach is to compute percentiles from the raw data or merged histograms.

### Comparing Different Time Windows

Comparing a 1-minute error rate against a 1-hour baseline is comparing different levels of granularity. A 1-minute window can show spikes that would be averaged out over an hour. When comparing current performance to a baseline, ensure the current window and the baseline window are computed at the same granularity, or explicitly account for the difference.

### Ignoring Throughput When Looking at Error Rates

As discussed above, error rate without throughput context is incomplete. A 0% error rate with 0 throughput is not healthy. Always check throughput alongside error rate.

### Treating All Errors Equally

A 500 Internal Server Error and a 503 Service Unavailable have different implications. A 500 often indicates a bug. A 503 often indicates the service is overloaded and deliberately shedding load. A 504 Gateway Timeout indicates a dependency is slow. Grouping all 5xx errors together for the health check is appropriate as a first pass, but investigation should distinguish between error types.

### Ignoring Error Rate Denominators

An error rate of 50% from 2 total requests is not statistically meaningful. Ensure the sample size is large enough to draw conclusions. For services with very low throughput, raw error counts may be more useful than error rates, and longer time windows may be needed to accumulate enough data for a meaningful rate.

### Using Averages Instead of Percentiles for Latency

Average latency is heavily influenced by outliers and hides the shape of the distribution. A service with an average latency of 200ms might have most requests completing in 50ms with a small number taking 5000ms. The average looks acceptable but 1 in 20 users is having a terrible experience. Always use percentiles for latency assessment.
