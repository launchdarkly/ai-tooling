---
name: investigate
description: "Finds the root cause of a production problem from observability data (logs, traces, errors, sessions, metrics): scope and onset, what changed (deploys and flag changes), which host, version, route or flag variation is over-represented against a baseline, then trace, log and error evidence and blast radius. Use when the user reports a bug, an outage, an error or latency spike, an incident, or asks about patterns across application data."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "0.3.0"
---

# Investigate

You are finding out why something broke. Most investigations stall in one of three places: the window or service is wrong, a filter silently matched nothing, or the agent read raw rows before it knew which slice of traffic was bad. The sequence below avoids all three. Follow it in order, then go deeper with the companion files.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server. Tools it uses:

- Scope: `find-o11y-project`, `get-keys`, `get-incidents`
- Shape and comparison: `search-aggregations` (with `groupBy`, `compareTo`, `exact`, `series` and `formulas`), `search-service-map` (with `include: ["health"]`)
- What changed: `get-changes`
- Evidence: `get-trace`, `search-traces`, `search-logs`, `search-log-patterns`, `search-error-groups`, `get-error-group`, `search-sessions`, `get-session-details`, `search-timeline-events`
- Alerts: `get-alerts`, `get-alert-firing-history`, `get-investigation` (see [alert-investigation](../alert-investigation/SKILL.md))

If a tool is missing, the MCP server may not be connected or may be older; say so rather than working around it.

## The first five minutes

Do these six steps before reading pages of raw rows. Each one is one to three calls. Keep a short running note of the window, the filter and what each step ruled in or out.

### 1. Scope and onset

Pin down the project, the service and the time the problem started.

- **Project.** If the user did not name one, call `find-o11y-project` with the service name. Ask if there is no single clear match.
- **Service family.** One system often reports under several names (`production-api`, `staging-api`, `production-api-worker`). Call `get-keys` with `key: "service_name"` and `search: "<name>"` and pick the exact values. Filter with `services: [...]` or `service_name=(a OR b)`, not `service_name=*api*`: a `*` is a contains match and pulls in siblings.
- **Incident.** If the report names an incident (INC-123), call `get-incidents` with `incidentId`. Its `created_at` is when someone noticed, not when it began; start your window at least 2 hours earlier.
- **Onset.** Run `search-aggregations` on the failing signal (error logs, 5xx spans, error groups) over a window wider than the report, for example 6 to 24 hours, with `bucketCount` 24 to 48. Find the first bucket that departs from the line. That is your **anomaly window**; the same-length window just before it, or the same time a day or week earlier, is your **baseline**.
- **Shape.** One spike, a step up, a slow drift, or the same pattern every day? A daily pattern points to traffic or batch jobs, not a regression.

Use ISO 8601 timestamps with a timezone from here on (`2026-10-29T13:30:00Z`). `compareTo` needs them; relative dates such as `now-1h` are rejected with it.

### 2. Is it chronic, or noise?

Before hunting for a cause, check that something actually changed.

- If an alert is involved, call `get-alert-firing-history` with `lookbackDays: 7`. Dozens of firings across the week on the same group mean a chronic condition or a fragile threshold, not a new incident. See [alert-investigation](../alert-investigation/SKILL.md).
- Run the failing signal again with `compareTo: "1w"` (or `"1d"`) and `bucketCount: 1`. If the anomaly window's value is close to `previous_values`, the problem was already there last week: say so, and investigate it as a standing issue, not a regression.

### 3. What changed?

Call `get-changes` with `serviceName` (one exact `service_name` value), `startDate` 1 to 2 hours before the onset, and `endDate` just after it. Set `environmentKey` (for example `production`) and keep the window short: it merges build versions, flag changes and alert state changes, and a long window on a busy project overflows the response.

- A **version** whose `first_seen` is just before the onset is the first suspect. Note the `versionKey` it detected (`service_version`, `tags.version` or `version`); use that same key in step 4. Services differ, so do not guess it.
- A **flag change** with `evaluated_by_service: true` is the strongest flag link: the service's own spans evaluated that flag in the window. Treat other flag changes as background unless their timing is exact.
- Flag changes are read newest first up to `maxFlagChanges`; when the result is truncated, `covered_from` says how far back it reached. If that is after your onset, narrow the window rather than trusting the gap.
- No change near the onset is a finding too: look at traffic, a dependency, or one bad host next.

A change that lines up in time is a suspect, not a conclusion. Step 4 tests it.

### 4. What is over-represented now?

This is the step that finds the cause most often, and the one agents skip. Compare the share of each value of a dimension in the anomaly window against the baseline. A cause shows up as one value that holds most of the failures now but only its usual share of traffic.

1. **List candidate dimensions** with `get-keys` for the product type (`search: "host"`, `search: "version"`, `search: "route"`, `search: "region"`, `search: "pod"`). Confirm a key exists before you group or filter on it: an unknown key in a filter is dropped silently and widens the result.
2. **Break the failures down** by each candidate, one `search-aggregations` call per dimension:

   ```json
   {
     "productType": "traces",
     "startDate": "<anomaly start>", "endDate": "<anomaly end>",
     "query": "span_kind=Server has_errors=true",
     "services": ["<service>"],
     "groupBy": "host.name", "groupByLimit": 10, "bucketCount": 1,
     "compareTo": "1d"
   }
   ```

   For 5xx only, filter on the status-code key instead; services differ (`http.response.status_code`, `http.status_code`), so check which one the service sets with `get-keys search=status_code` and a filtered count before relying on it. Then run the same call without the error filter (all requests) so you can compare each value's share of failures with its share of traffic.
3. **Dimensions to try, in this order:** `host.name` (or `k8s.pod.name`), the version key from step 3, `http.route` (with `span_kind=Server`), `environment` or region, and for flag-gated code the flag variation: filter `feature_flag.key=<flag>` and group by `feature_flag.result.variationIndex` (see `traces.md`). For latency, break down `P95` of `duration` the same way and set `rankBy` to `{"aggregator":"Count","column":""}` so busy groups rank first.
4. **Error rate per value in one call.** For traces, drop the error filter and use `expressions` `[{"aggregator":"Count","column":""},{"aggregator":"Sum","column":"has_errors"}]` with `rankBy` Count: each row then has its requests and its failed spans side by side. For any other ratio, use `series` and `formulas`: series `a` all requests, series `b` failures, formula `100 * b / a`. Each series ranks its own top groups, so a value outside one series' top groups returns a null formula; raise `groupByLimit` or set `minCount` if rows come back null.
5. **Read it as shares.** "Host X served 9 % of requests and 94 % of 5xx" is a cause. "Version Y has the most errors" is not, if it also has the most traffic. When one host is bad and a new version is on many hosts, group by `[versionKey, "host.name"]` to see whether the version also runs on healthy hosts. If it does, the version is not the cause.

Do not stop at the first dimension that looks skewed when the conclusion matters; one more breakdown (the version on that host, the routes on that host) usually confirms or breaks it.

### 5. Evidence

Now pull specific records from the slice step 4 found. Add that slice to every filter (`host.name=<host>`, the version, the route).

- **Logs.** `search-log-patterns` with `query: "level=error <slice filter>"` groups thousands of lines into a few templates with counts; read those before paging `search-logs`. Set `patternKeys: ["error.message"]` when the message is generic and the detail sits in an attribute.
- **Traces.** `search-traces` with `sortColumn: "duration"` and `sortDirection: "DESC"` for the slowest, or `has_errors=true` for failed spans. Then `get-trace` with the `traceId` and the span's `timestamp` to read the tree: which span owns the time, and which child failed first.
- **Logs for one request.** `search-logs` with `query: "trace_id=<id>"` and a window of a few minutes around the span.
- **Errors.** `search-error-groups` with the slice filter and `sort: "count"`, then `get-error-group` with the `secureId` for the stack, one occurrence, and its `trace_id` and session. Set `occurrences` to list occurrences in the window.
- **Metrics on the slice.** For a bad host, `search-aggregations` with `productType: "metrics"`, `query: "host.name=<host>"` (add `metric_name=*pool*`-style words to narrow), `groupBy: "metric_name"` lists what it reports (pool sizes, CPU, memory). Filter metrics by host, not by the trace `service_name`: metric data points often carry a different service name, and the filter then matches nothing. Load the `observability/metrics` guide before reading counters or histograms.

Cite exact identifiers: trace IDs, error group secure IDs, log timestamps, host names, versions.

### 6. Blast radius

Quantify who and what was affected, over what window.

- `search-service-map` with `service: "<service>"` and `include: ["health"]` gives requests, errors, error rate and p50/p95/p99 for the service and per `http.route`. Run it for the anomaly window and for the baseline window to compare. Use `include: ["dependencies"]` to see callers that inherited the failure.
- Users and sessions: `search-error-groups` with `sort: "sessions"`, or `search-aggregations` with `CountDistinct` of a user key such as `identifier` (sessions) and `exact: true`.
- Time: first and last bad bucket, using `Min` and `Max` of `timestamp` with `bucketCount: 1` (values are Unix seconds; convert them).

## Sampling and percentiles

Trace and log aggregations read a sample unless you set `exact`. When the result says `estimated: true`, counts are scaled-up estimates and percentiles come from the sampled rows only.

- **A percentile over few rows is noise.** P99 is roughly the 1 % slowest of the rows actually read: over 100 rows that is the single slowest one, over 600 it is the sixth. Treat a P99 resting on fewer than about 200 sampled rows, or a P95 on fewer than about 50, as unreliable. Add a `Count` expression next to the percentile so you can see how many rows each bucket holds, and divide by the sample factor when the result is estimated.
- **Set `exact: true`** for short windows (a few hours), small or rare counts, distinct counts, and any number you will quote in a conclusion. `exact` cannot be combined with `series`; for an exact ratio, run the numerator and denominator as two calls.
- Prefer fewer, wider buckets for percentiles over long windows: 36 two-hour buckets of a sampled P99 swing far more than the underlying latency does.
- `includeOther` supports only `Count`, `Sum`, `Min` and `Max`. Rank by `Count` and report percentiles without it.

## Load companion files when relevant

- `logs.md`: error messages, log patterns, logs for one trace or session
- `traces.md`: request flow, latency, slow spans, span trees, flag variations on spans
- `errors.md`: error groups, stack traces, occurrences, regressions
- `sessions.md`: user journeys and frontend behavior
- `metrics.md`: `search-aggregations` options in depth (breakdowns, `compareTo`, formulas, sampling)
- `relationship-search.md`: questions about the order, absence or co-occurrence of events in a session or trace (`THEN`, `no_span`, `AND`, `OR`)

## Universal guidance

- **Plan, then let each result inform the next.** State a short plan before the first call. Re-plan after each step; do not run calls you already know the answer to.
- **Aggregate before you read rows.** `search-aggregations` and `search-log-patterns` answer "how many", "which ones" and "since when" in one call. `search-logs`, `search-traces`, `search-sessions` and `search-error-groups` return pages (at most 50 rows per call; follow `page.next_cursor` or `page` for more), which is for evidence once you know where to look, not for counting.
- **Check that a filter filtered.** An invalid clause or an unknown key is dropped, not rejected, and the result gets wider. If a "filtered" count equals the unfiltered one, the filter did nothing. See `observability/querying-patterns` for the grammar.
- **Convert units.** Trace `duration` is in nanoseconds; timestamps from `Min`/`Max` are Unix seconds.
- **Cross-reference.** Trace IDs in logs, sessions on error occurrences, versions on spans: where two products agree, you have evidence.
- **Large outputs.** When a result is saved to a file because it was too large, extract the slice you need with `jq` or `python3` instead of reading the whole file, and next time narrow the window or lower `maxTokens`.
- **Do not trust a summary over the data.** An incident summary, an earlier investigation or a responder's theory is a hypothesis. Check it with step 4; if the data disagrees, say so and show the numbers.
- **On tool failure**, try the alternative (a narrower window, a different tool) and report what you found plus the exact next query to run.

## Output

End with:

1. **Root cause** in one or two sentences, with a confidence level, and the numbers that support it (share of failures vs share of traffic, before vs after).
2. **Timeline**: onset, the change or trigger, peak, recovery, as absolute UTC times.
3. **Evidence**: trace IDs, error group IDs, log templates with counts, hosts, versions, flag keys.
4. **Blast radius**: requests, error rate, users or sessions, routes, downstream services.
5. **What was ruled out**, briefly (for example "version e63885098 also ran on 9 healthy hosts").
6. **Next steps**: at least one concrete action (roll back version X, turn flag Y off in production, drain host Z, retune alert N) and any open question with the exact query or data that would answer it.

## Related skills

- [alert-investigation](../alert-investigation/SKILL.md): start here when an alert fired.
- `observability/querying-patterns` (hosted MCP guide): the full filter grammar and its silent failures.
- `observability/metrics` (hosted MCP guide): OpenTelemetry metrics, counters and histograms.
- [create-fix-pr](../create-fix-pr/SKILL.md): turn the root cause into a pull request.
