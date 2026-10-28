# Investigating with metrics

Load this file when you need aggregation across a large dataset — unique users, counts by dimension, time-bucketed trends — or before building a graph.

## When to reach for aggregations

- You want to aggregate across hundreds or thousands of records (paginating is expensive and lossy)
- You're looking for trends over time (error-rate spike, latency regression, traffic shift)
- You need to group by a dimension (errors by service, sessions by city, latency by span_name)
- You're sizing the problem before drilling in with `search-logs`, `search-traces`, `search-error-groups`, or `search-sessions`

## Tool guidance (`search-aggregations`)

The `search-aggregations` tool returns bucketed aggregated values, suitable for charting and analysis.

- `productType` is required; one of `errors`, `traces`, `logs`, `sessions` (`requests` is accepted as an alias for `traces`).
- `startDate` is required; ISO format.
- `endDate` defaults to now.
- `query` is an attribute filter — e.g. `error EXISTS AND service_name=foo`.
- `groupBy` is an attribute to group results by (e.g. `message`, `service_name`). Single field.

Note: across **different** product types, the same attribute keys work — query `search-aggregations` with `productType="sessions"` and `groupBy="identifier"` for session-grouping analogous to `productType="logs"` with `groupBy="level"`.

## Keep the bucket count small

When requesting aggregations, use coarser intervals or fewer groupings — bloated responses exceed the context window. Prefer 10–30 buckets over 1000; prefer a single `groupBy` over multi-dimension pivots.

## Typical patterns

1. **Rate trends** — `productType="errors"`, 24-hour window, groupBy `service_name` → top offending services.
2. **Unique-count queries** — count unique users in a session set: `search-aggregations` with `productType="sessions"`, `groupBy="identifier"`. Don't paginate through individual sessions.
3. **Before/after comparison** — run twice with adjacent time windows, compare the bucket counts to detect regressions.
4. **Pre-chart sizing** — before `create-graph`, run a `search-aggregations` query to verify the data shape is what you expect (non-empty, reasonable bucket distribution).

## Pairing with `get-keys`

Before aggregating on an unfamiliar attribute, call `get-keys` for the product type to see which grouping keys exist. Attribute names vary — `service_name` vs `service.name` vs `serviceName`.

## Interpreting results

- **Coarse-first, then drill.** A metrics bucket showing "errors up 300% in service X" is a starting point; follow with `search-error-groups` and `search-logs` to get the specific errors.
- **Correlate trends with deploys, flag flips, traffic patterns.** A shift that starts at a specific minute often points to an external trigger.
- **Cite the metric type, grouping, and bucket range** when presenting findings.

## Common mistakes

- Paginating records when you should aggregate. If the goal is a count or distinct, use `search-aggregations` with `groupBy`.
- Requesting too many buckets or nested groupings. Blow the context window and you lose your investigation.
- Skipping `get-keys` and guessing attribute names. Wrong name returns an empty metric — silently.
