# Log Query Patterns Reference

This reference provides detailed patterns and strategies for searching, filtering, and analyzing application logs. Use these patterns to construct effective queries, trace requests across services, and extract meaningful insights from log data.

---

## Common Search Patterns

### Error Hunting

Error hunting is the most frequent log query task. The goal is to find specific errors, understand their frequency, and identify root causes.

**Single Error Investigation**

When a user reports a specific error message or error code, start with the most unique identifier available. If they provide an exact error message, use it as a keyword filter. If they provide an error code (e.g., `ERR_CONNECTION_REFUSED`, `HTTP 502`), filter on that code combined with a severity filter of `ERROR` or higher.

A typical error hunting workflow:

1. Filter by service name and severity `ERROR` or `FATAL`.
2. Apply the narrowest reasonable time window (if the user says "this morning," use the last few hours rather than the full day).
3. Add keyword filters for specific error text if available.
4. Review the returned entries for stack traces, error codes, and contextual fields.
5. Look for patterns: are errors clustered at a specific time? Do they affect a single endpoint or many?

**Recurring Error Discovery**

When looking for error patterns rather than a single incident, use a wider time window (24 hours or more) and focus on aggregation. Group errors by message or error code to identify the most frequent issues. Look for errors that started appearing at a specific time, which may correlate with a deployment or configuration change.

**Error Spike Investigation**

If metrics or alerts indicate an error spike, query logs around the spike timestamp with a tight window (e.g., 5-10 minutes before and after). Compare error patterns during the spike with a baseline period before the spike to identify what changed.

### Request Tracing

Request tracing follows a single request as it flows through one or more services. This is essential for debugging latency issues, partial failures, and unexpected behavior.

**Single-Service Request Trace**

For tracing within a single service, search for the request identifier (request ID, session ID, or user ID) within that service's logs. Sort results chronologically to reconstruct the request lifecycle: ingress, processing steps, database calls, external API calls, and response.

**Multi-Service Distributed Trace**

For distributed systems, use the correlation ID or trace ID that propagates across service boundaries. Start by finding the initial log entry (often at the API gateway or edge service), extract the trace ID, then search across all services for that trace ID. This reconstructs the full distributed path of the request.

Key fields to look for when tracing:
- `trace_id` or `traceId`: The top-level identifier for the distributed trace.
- `span_id` or `spanId`: Identifies a specific operation within the trace.
- `parent_span_id`: Links child operations to their parent, allowing tree reconstruction.
- `request_id` or `X-Request-ID`: Often set at the edge and propagated downstream.
- `correlation_id`: Application-specific identifier linking related operations.

### User-Journey Reconstruction

Reconstructing a user's journey through the system requires searching by user identifier across services and a broader time window. This pattern is useful when investigating user-reported issues where the exact failing operation is unknown.

**Approach:**

1. Identify the user identifier: user ID, email, session ID, or IP address.
2. Set a time window covering the user's reported activity period.
3. Search across all services (or start with the most likely services) for the user identifier.
4. Sort chronologically to reconstruct the sequence of actions.
5. Look for errors, unusual latency gaps, or unexpected paths in the journey.

**Caveats:**

- User identifiers may not be present in all log entries, especially in backend services that only receive trace IDs.
- PII considerations: user email or IP may be redacted or hashed in logs.
- Session IDs change between sessions, so ensure you have the correct session.

### Pattern Detection

Pattern detection involves searching for recurring themes, anomalies, or trends in log data without a specific error in mind.

**Common Pattern Detection Scenarios:**

- **Deployment impact:** Compare error rates and types before and after a deployment timestamp.
- **Time-based patterns:** Look for errors that occur at specific times (cron jobs, batch processing, peak traffic hours).
- **Service dependency failures:** Search for timeout or connection errors to identify failing upstream or downstream dependencies.
- **Resource exhaustion:** Look for out-of-memory errors, connection pool exhaustion, disk space warnings, or thread pool saturation messages.
- **Configuration issues:** Search for configuration-related log messages after a config change, looking for parsing errors, missing values, or fallback behavior.

---

## Filter Syntax Concepts

### Severity / Level Filtering

Log severity levels follow a standard hierarchy. Filtering by severity is one of the most effective ways to reduce noise.

**Standard severity levels (from least to most severe):**

| Level    | Use Case                                                                 |
|----------|--------------------------------------------------------------------------|
| TRACE    | Extremely detailed diagnostic information, typically disabled in production |
| DEBUG    | Detailed diagnostic information useful during development                |
| INFO     | General operational messages confirming things are working as expected   |
| WARN     | Potentially harmful situations or unexpected conditions that are handled |
| ERROR    | Error events that allow the application to continue running              |
| FATAL    | Very severe errors that will likely cause the application to abort       |

**Filtering strategies:**

- For incident investigation, start with `ERROR` and `FATAL` to see what went wrong.
- If errors lack context, widen to include `WARN` to see precursor conditions.
- For request tracing, use `INFO` and above to see the request flow without debug noise.
- Avoid `DEBUG` and `TRACE` in production queries unless absolutely necessary, as they produce enormous volumes.

When filtering by severity, most systems support "this level and above" semantics. A filter of `severity >= WARN` returns `WARN`, `ERROR`, and `FATAL` entries.

### Service Filtering

Service filtering narrows results to logs from specific microservices or application components.

**Best practices:**

- Always include a service filter when you know the target service. This dramatically reduces result volume and query cost.
- Use the exact service name as registered in the logging infrastructure. Common naming conventions include `checkout-service`, `checkout_service`, or `CheckoutService`. If unsure, use the `list-services` tool to discover available service names.
- For distributed trace queries, you may need to query multiple services. Start with the known service and expand based on trace results.
- Service names may include environment prefixes or suffixes (e.g., `checkout-service-prod`, `prod.checkout-service`). Be aware of your organization's naming conventions.

### Time Window Selection

Time windows are one of the most impactful filters for query performance and relevance.

**Guidelines for selecting time windows:**

| Scenario                        | Recommended Window    |
|---------------------------------|-----------------------|
| Known incident with timestamp   | 5-15 minutes around the incident |
| "It happened this morning"      | Last 4-6 hours        |
| "It's been happening recently"  | Last 24 hours          |
| "It started after the deploy"   | Deploy time to now     |
| Pattern analysis                | 24-72 hours            |
| Regression detection            | Compare two windows: before and after |

### Field-Based Filters

Structured log fields provide precise filtering without the ambiguity of free-text search.

**Common filterable fields:**

- `service` or `service_name`: The originating service.
- `level` or `severity`: Log severity level.
- `environment` or `env`: Production, staging, development.
- `host` or `hostname`: The specific host or container.
- `endpoint` or `path`: The HTTP path or RPC method.
- `status_code` or `http_status`: HTTP response status code.
- `method` or `http_method`: HTTP method (GET, POST, etc.).
- `trace_id`, `span_id`, `request_id`: Distributed tracing identifiers.
- `user_id`, `account_id`, `tenant_id`: User and account identifiers.
- `error_code` or `error_type`: Application-specific error classification.
- `duration_ms` or `latency`: Request processing time.

When a field-based filter is available, always prefer it over free-text search. Field-based filters are indexed, faster, and produce precise results without false positives.

### Regex Patterns

Regular expressions provide flexible text matching when field-based filters are insufficient.

**Common regex patterns for log queries:**

| Pattern | Purpose | Example |
|---------|---------|---------|
| `error.*timeout` | Error messages containing "timeout" | Matches "error: connection timeout after 30s" |
| `status[_]?code[=: ]+5\d{2}` | 5xx status codes | Matches "status_code=503" or "statusCode: 500" |
| `\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b` | UUIDs | Matches trace IDs, request IDs |
| `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}` | IPv4 addresses | Matches "192.168.1.1" |
| `(OOM\|OutOfMemory\|out of memory)` | Memory exhaustion | Matches various OOM message formats |
| `(Exception\|Error\|Traceback)` | Exception indicators | Catches Java, Python, Go error patterns |
| `latency[=: ]+\d{4,}` | High latency (4+ digit ms) | Matches entries with latency >= 1000ms |

**Regex performance considerations:**

- Regex filters are computationally expensive. Always combine them with other filters (service, time window, severity) to reduce the data scanned.
- Anchor patterns when possible (`^` for start, `$` for end) to improve matching performance.
- Avoid overly broad patterns like `.*` at the start of a regex, which force scanning entire log lines.
- Prefer field-based filters over regex when the data is structured.

---

## Time Window Strategies

### Narrow Windows for Known Incidents

When you have a specific timestamp for an incident (from an alert, user report, or metric spike), use a narrow window centered on that timestamp.

**Strategy:**

1. Start with a 5-minute window around the reported time.
2. If insufficient context is found, expand to 15 minutes, then 30 minutes.
3. Look for the earliest error in the window, as this is often the root cause. Later errors may be cascading failures.

**Why narrow windows matter:**

- Faster query execution, especially on large-scale logging infrastructure.
- Less noise from unrelated log entries.
- Easier to identify the sequence of events around the incident.
- Lower cost in systems that charge per data scanned.

### Wide Windows for Pattern Detection

When investigating trends, recurring issues, or trying to establish baselines, use wider time windows.

**Strategy:**

1. Start with 24 hours for recent patterns.
2. Use 72 hours or 7 days for trend analysis.
3. Compare equal-duration windows (e.g., this week vs. last week) for regression detection.
4. Be prepared to use aggregation rather than reading individual entries, as wide windows may return millions of log lines.

### Relative vs. Absolute Times

**Relative times** (e.g., "last 1 hour", "last 24 hours") are useful for:
- Ongoing investigations where "now" is the reference point.
- Dashboards and saved queries that should always show recent data.
- Quick ad-hoc queries during incident response.

**Absolute times** (e.g., "2024-01-15 14:30:00 to 2024-01-15 15:00:00") are useful for:
- Post-incident reviews where the incident window is known.
- Comparing specific time periods.
- Reproducible queries that return the same results regardless of when they run.
- Sharing queries with colleagues who may run them at different times.

### Timezone Considerations

Timezone mismatches are a common source of confusion in log queries.

**Best practices:**

- Determine what timezone your logging infrastructure uses. Most systems store timestamps in UTC.
- When a user reports a time, clarify their timezone. "It happened at 2pm" could be any timezone.
- Convert user-reported times to UTC (or the system's native timezone) before querying.
- Be aware of daylight saving time transitions, which can cause ambiguous or missing hours.
- When presenting results to users, convert timestamps back to their local timezone for readability.

---

## Structured vs. Unstructured Log Approaches

### JSON / Structured Logs

Structured logs emit each entry as a JSON object (or other structured format) with well-defined fields.

**Example structured log entry:**
```json
{
  "timestamp": "2024-01-15T14:32:01.456Z",
  "level": "ERROR",
  "service": "checkout-service",
  "trace_id": "abc123def456",
  "span_id": "span789",
  "message": "Payment processing failed",
  "error_code": "PAYMENT_DECLINED",
  "user_id": "user-42",
  "endpoint": "/api/v1/checkout",
  "duration_ms": 1523,
  "error_details": {
    "provider": "stripe",
    "decline_code": "insufficient_funds"
  }
}
```

**Query advantages of structured logs:**

- Every field is directly filterable: `error_code = "PAYMENT_DECLINED"` is precise and fast.
- Aggregations are straightforward: count by `error_code`, average `duration_ms`, group by `endpoint`.
- No parsing required at query time, reducing CPU cost and latency.
- Fields are typed, so numeric comparisons work correctly (`duration_ms > 1000`).
- Nested fields provide rich context without cluttering the message.

### Free-Text / Unstructured Logs

Unstructured logs are human-readable text strings, often from legacy systems or simple logging configurations.

**Example unstructured log entry:**
```
2024-01-15 14:32:01.456 ERROR [checkout-service] [trace:abc123def456] Payment processing failed for user user-42 on /api/v1/checkout (1523ms): PAYMENT_DECLINED - insufficient_funds (provider: stripe)
```

**Challenges with unstructured logs:**

- Extracting fields requires regex or parsing at query time.
- Inconsistent formatting across services makes universal queries difficult.
- Free-text search may produce false positives (searching for "error" matches "error" in any context, including log messages about error handling working correctly).
- Aggregation requires field extraction first, which is slower and less reliable.

### Extracting Fields from Unstructured Logs

When working with unstructured logs, you can extract fields using patterns:

- **Regex extraction:** Define capture groups to pull out specific values. For example, `\[trace:([a-f0-9]+)\]` extracts the trace ID from the bracket notation.
- **Delimiter-based parsing:** Split on known delimiters (spaces, pipes, brackets) and reference fields by position.
- **Grok patterns:** Some logging platforms support Grok (named regex patterns) for common log formats like Apache access logs, syslog, etc.

**Tips for querying unstructured logs:**

1. Identify the most unique and specific text to search for. Prefer error codes over generic words.
2. Use surrounding context (brackets, equals signs, quotes) to reduce false positives. Search for `[ERROR]` instead of just `ERROR`.
3. Combine multiple keywords with AND semantics to narrow results. For example, `"timeout" AND "checkout-service"`.
4. If you need a field value, use regex extraction on the results rather than trying to filter by extracted values at scale.

---

## Request Tracing Patterns

### Correlation IDs

Correlation IDs are application-generated identifiers that link related operations. They differ from distributed trace IDs in that they are often business-meaningful (e.g., order ID, transaction ID) rather than randomly generated.

**Using correlation IDs for tracing:**

1. Identify the correlation ID from the user's report, an alert, or an initial log query.
2. Search for the correlation ID across all relevant services.
3. Sort results by timestamp to reconstruct the sequence.
4. Pay attention to service transitions (where one service hands off to another) as these are common failure points.

**Common correlation ID fields:**
- `order_id`, `transaction_id`: Business-level identifiers.
- `request_id`, `X-Request-ID`: HTTP-level identifiers set at the edge.
- `session_id`: Groups all operations within a user session.
- `job_id`, `batch_id`: Identifiers for background processing.

### Trace IDs and Span IDs

In distributed tracing systems (OpenTelemetry, Jaeger, Zipkin), every request gets a trace ID, and each operation within the request gets a span ID.

**Trace reconstruction from logs:**

1. Find the trace ID from an initial log entry, alert, or trace UI.
2. Query all logs with that trace ID across all services.
3. Use span IDs and parent span IDs to build the trace tree:
   - The root span has no parent span ID (or a null/empty parent).
   - Each span's `parent_span_id` points to its parent operation.
   - Spans within the same service form a local tree; spans across services link through parent references.
4. Sort by timestamp within each service, and use span relationships to understand the cross-service flow.

**What to look for in a trace:**

- **Error spans:** Spans where the log level is ERROR or where an error field is present.
- **Slow spans:** Spans with unusually high `duration_ms`, indicating latency bottlenecks.
- **Missing spans:** Gaps in the expected sequence may indicate dropped requests, services not emitting logs, or log ingestion delays.
- **Retry spans:** Multiple spans for the same operation indicate retries, which may point to flaky dependencies.

### Reconstructing Distributed Traces from Logs

When a dedicated tracing system is not available, or when traces are incomplete, you can reconstruct request flows from log entries.

**Step-by-step approach:**

1. Start at the entry point (API gateway, load balancer, or edge service).
2. Find the log entry for the incoming request. Extract any IDs: request ID, trace ID, user ID.
3. Search downstream services for that ID. If no common ID exists, use correlated timestamps and endpoint information.
4. For each service, identify the inbound log (request received) and outbound log (response sent or downstream call made).
5. Build a timeline showing the request flow, processing time at each service, and any errors encountered.

**When traces are incomplete:**

- Check for log sampling: some services may sample logs, dropping entries for certain requests.
- Check for log ingestion delays: logs from different services may arrive at different times.
- Check for log retention: if the incident is old, some logs may have been purged.
- Fall back to correlating by timestamp and endpoint when IDs are not available, but acknowledge the lower confidence of this approach.

---

## Aggregation Patterns

### Error Counts by Type

Counting errors by type helps prioritize investigation. The most frequent errors are not always the most important, but they are a good starting point.

**Approach:**

1. Query all ERROR-level logs for the target service and time window.
2. Group by error code, error type, or error message.
3. Count the occurrences in each group.
4. Sort by count descending to see the most frequent errors.
5. Look for errors with counts significantly above the baseline.

### Top Errors

Identifying the top errors gives a quick health overview of a service.

**Useful top-error views:**

- **Top errors by count:** Most frequent errors.
- **Top errors by affected users:** Errors impacting the most unique users. A low-count error affecting many users may be more important than a high-count error from a single retry loop.
- **Top new errors:** Errors that appeared for the first time in the query window, which may indicate a new bug from a recent deployment.
- **Top errors by service:** Across all services, which service is producing the most errors?

### Frequency Analysis

Frequency analysis reveals temporal patterns in log data.

**Patterns to look for:**

- **Spike analysis:** Sudden increases in error count at a specific time. Correlate with deployments, config changes, or external events.
- **Periodic patterns:** Errors that occur at regular intervals may be caused by cron jobs, batch processing, or scheduled tasks.
- **Gradual increase:** A slowly rising error rate may indicate resource exhaustion (memory leaks, disk filling up, connection pool depletion).
- **Step function:** A sudden permanent increase in error rate starting at a specific time, likely caused by a deployment or configuration change.

### Rate Calculations from Logs

Calculating error rates from logs provides a useful signal when dedicated metrics are not available.

**Basic rate calculation:**

1. Count all log entries (or all request-related entries) in a time window.
2. Count error-level entries in the same window.
3. Error rate = (error count / total count) * 100.

**Caveats:**

- Log sampling affects rate accuracy. If only 10% of requests are logged, the rate is an estimate.
- Different services may log at different verbosity levels, making cross-service rate comparisons unreliable.
- Request logs and error logs may not have a 1:1 relationship. A single request may generate multiple error log entries (e.g., retry attempts).

---

## Query Refinement Strategies

### Start Broad, Then Narrow

The most reliable approach to log queries is iterative refinement.

**Step-by-step refinement:**

1. **Broadest query:** Service + time window only. Review the result count and a sample of entries to understand the data volume and format.
2. **Add severity:** Filter to WARN and above (or ERROR and above) to focus on problems.
3. **Add keywords:** Include specific error messages, codes, or identifiers from the user's report.
4. **Add field filters:** If initial results reveal useful fields (endpoint, user ID, host), add those as filters.
5. **Narrow time window:** Once you find relevant entries, narrow the time window around them for detailed analysis.

This approach avoids the common pitfall of starting with an overly specific query that returns no results, leaving you unsure whether the issue doesn't exist or your query is wrong.

### Using Facets

Facets (also called field value distributions) show the top values for each field in your result set.

**How facets help refinement:**

- **Service facet:** Shows which services are contributing the most entries. If an unexpected service appears, it may indicate a cascading failure.
- **Severity facet:** Shows the distribution of severity levels. A high ratio of ERROR to INFO may indicate a problem.
- **Endpoint facet:** Shows which endpoints are most active in the results. Focus on the top endpoint for targeted investigation.
- **Host facet:** Shows which hosts are contributing. If a single host dominates the error count, it may be a host-specific issue (bad deploy, hardware problem, noisy neighbor).
- **Error code facet:** Shows the distribution of error types, helping prioritize which error to investigate first.

### Iterative Filtering

Iterative filtering is the process of using results from one query to inform the next.

**Common iteration patterns:**

1. **Error to trace:** Find an error entry, extract its trace ID, query for the full trace.
2. **Trace to service:** Identify which service in the trace is the origin of the failure, then query that service's logs for more detail.
3. **Service to host:** If errors are concentrated in one service, check if they are further concentrated on a specific host.
4. **Host to time:** If a specific host is problematic, look at its error timeline to identify when the issue started.
5. **Time to cause:** Once you know when the issue started, correlate with deployment logs, config changes, or external dependency status.

### Handling High-Cardinality Fields

High-cardinality fields (fields with many unique values, like user ID, request ID, or IP address) require special handling.

**Challenges:**

- Grouping by high-cardinality fields produces too many groups to be useful.
- Querying by a specific high-cardinality value is fine, but exploring all values is impractical.
- Some logging systems have performance limitations with high-cardinality group-by operations.

**Strategies:**

- **Don't group by high-cardinality fields** for exploratory analysis. Instead, group by low-cardinality fields (service, endpoint, error code, severity) first.
- **Use high-cardinality fields for targeted queries** when you have a specific value (e.g., a specific user ID from a support ticket).
- **Sample first:** If you need to understand patterns in high-cardinality data, sample a subset of entries and analyze them manually.
- **Use derived fields:** Instead of grouping by full user ID, group by user segment, account type, or geographic region if those fields are available.
- **Apply aggregation limits:** If your query platform supports it, limit group-by results to the top N values to avoid overwhelming the system and your analysis.

---

## Platform-Agnostic Tips

These tips apply regardless of your specific logging platform:

1. **Learn your platform's query language.** Every logging system has its own syntax for filters, aggregations, and transformations. Invest time in learning it to write efficient queries.
2. **Use saved queries.** For common investigation patterns, save queries as templates that can be quickly customized with specific values (time window, service name, trace ID).
3. **Understand your platform's limitations.** Know the maximum query time range, result size limits, sampling behavior, and cost model.
4. **Check log ingestion delay.** Most logging systems have a delay between when a log is emitted and when it is queryable. This delay can range from seconds to minutes. If investigating a very recent event, wait a few minutes or account for the delay in your time window.
5. **Be aware of log retention policies.** Logs older than the retention period are not available. If investigating a historical incident, verify that logs from that period are still retained.
6. **Document your investigation.** When you find something important, note the query that found it, the relevant log entries, and your interpretation. This helps with post-incident reviews and knowledge sharing.
