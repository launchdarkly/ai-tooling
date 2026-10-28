# Investigating with logs

Load this file when the investigation touches application logs — error messages, log-level filters, service log patterns.

## When to reach for logs

- The user mentions a specific error string, service name, or log level
- You need to correlate a symptom with a specific moment in time
- A trace span failed and you need the structured log output around it
- You're looking for a pattern (repeated error, frequency change) before narrowing to specific records

Logs are your best tool for verbatim evidence. They're your worst tool for "what's the overall picture" — reach for `search-aggregations` instead.

## Tool guidance (`search-logs`)

The `search-logs` tool returns paginated log entries with timestamp, level, message, and core attributes.

- `startDate` is required; ISO format with timezone (e.g. `2026-01-24T15:25:19.000-08:00` or `2026-01-24T15:25:19Z`).
- `endDate` defaults to now.
- `query` is a filter expression like `message="error" AND level=error`. Empty string returns all logs in range. See query syntax below.
- `limit` defaults to 20, max 50. Do not request more.
- `direction` is `ASC` or `DESC`. Defaults to `DESC` (newest first).

**Session-scoped queries.** To pull logs from a specific session, use `secure_session_id=<id>` in the query. Set `startDate` to the session's `created_at` and `endDate` to `created_at + 3 hours`. Narrower windows will miss tail events.

## Typical patterns

1. **Error pattern search** — `query="level=error AND service_name=<svc>"`, 24h window, aggregate first with `search-aggregations` if volume is high.
2. **Specific error message** — escape quotes in the query: `query="message=\"Cannot use 'in' operator*\""`. Wildcards work.
3. **Logs around a trace** — pull the trace first, grab the timestamp and service, then `query="trace_id=<id>"` with a 1-minute window centered on the event.
4. **Service-wide health snapshot** — `search-aggregations` with `productType="logs"` and `groupBy="level"` for a time window, then drill into high-count levels with `search-logs`.

## Interpreting results

- Don't paraphrase — cite the exact log line. "The database is slow" is not actionable; `{"ts": "2026-04-20T14:23:11Z", "level": "error", "message": "pg_pool: connection timeout after 30s"}` is.
- If you see repeated errors, note the exact cadence — a burst suggests an incident onset; steady-state suggests a persistent bug.
- Log level drift often correlates with deploys or flag flips — cross-reference with `search-flag-evaluations` when a regression appears.

## Common mistakes

- Asking for 100+ entries. Max is 50. Use `search-aggregations` for aggregates.
- Forgetting to specify `startDate`. It's required.
- Wildcarding too broadly (`message="*"`) — returns everything, wastes token budget.
- Assuming attribute names. Call `get-keys(productType="Logs")` if you're unsure which field to filter on.
