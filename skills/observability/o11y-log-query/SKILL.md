---
name: o11y-log-query
description: "Search and filter application log entries by service, time window, severity, or keyword. Use when the user wants to find a specific error message, trace a request by ID across services, look at recent log output, or search for a pattern in logs. This skill queries log text — use o11y-service-health instead for numeric metrics."
license: Apache-2.0
compatibility: Requires LaunchDarkly MCP server with observability tools enabled.
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# Log Query

You're using a skill that will guide you through searching and filtering application logs to find relevant information. Your job is to understand what the user is looking for, construct an effective query, execute it, and interpret the results.

## Prerequisites

- **LaunchDarkly MCP server** with observability tools enabled.
- **Required MCP tools:**
  - `search-logs` — Search and filter logs by service, time, severity, and keywords.
  - `get-log-entry` — Fetch full details of a specific log entry.
- **Optional MCP tools:**
  - `list-services` — List available services for discovery and name validation.

## Core Principles

1. **Start Broad, Then Narrow** — Begin with wider time windows and fewer filters, then iteratively refine your query. An overly specific initial query may return zero results, leaving you unsure whether the issue exists or your query is wrong.

2. **Context is King** — A single log line rarely tells the full story. Always look for surrounding context: preceding warnings, related entries from other services, and the sequence of events leading up to an error. Use trace IDs and correlation IDs to expand your view.

3. **Structured Queries First** — Use structured fields (severity, service, trace ID, error code) before resorting to free-text search. Structured filters are indexed, faster, and produce precise results without false positives.

4. **Time Windows Drive Cost** — Narrower time windows return faster results and reduce noise. Always apply a time window, and prefer the narrowest window that still captures the relevant context. Wide, open-ended queries are expensive and often overwhelming.

## Workflow

### Step 1: Define Search Intent

Understand what the user is looking for. Determine:

- **Target service:** Which service or services are involved?
- **Time window:** When did the issue occur? Is it ongoing?
- **Severity level:** Are we looking for errors, warnings, or all log levels?
- **Keywords / IDs:** Does the user have a specific error message, trace ID, request ID, or user ID?

If the user's intent is ambiguous, ask clarifying questions before constructing the query. Examples of clarifying questions:

- "Which service are you investigating?"
- "Do you have an approximate time when this occurred?"
- "Do you have a trace ID or request ID I can search for?"
- "Are you looking for a specific error, or trying to understand the general health of the service?"

### Step 2: Construct Query

Build the query using structured fields first, layering filters from broadest to most specific:

1. **Service filter** — Set the target service name. Use `list-services` if the exact name is unknown.
2. **Time window** — Apply the appropriate time range based on the user's report.
3. **Severity filter** — Set severity to `ERROR` or higher for error investigation, or `INFO` and above for request tracing.
4. **Keyword / pattern filters** — Add specific error messages, trace IDs, or other keywords.

See [query-patterns.md](references/query-patterns.md) for common query patterns including error hunting, request tracing, and aggregation strategies.

### Step 3: Execute & Refine

Run the query using `search-logs` and evaluate the results.

**If too many results:**
- Narrow the time window.
- Add or tighten the severity filter.
- Add a keyword or field filter to focus on the specific issue.

**If too few results (or none):**
- Widen the time window.
- Remove the most restrictive filter.
- Verify the service name spelling (use `list-services`).
- Check if the severity filter is too restrictive (e.g., FATAL-only when the issue logs as ERROR).

**If tracing a request:**
- Extract the correlation ID or trace ID from the initial results.
- Search for that ID across other services to find related entries.
- Use `get-log-entry` to fetch full details of specific entries that look relevant.

### Step 4: Interpret Results

Summarize findings for the user. Identify and communicate:

- **Error patterns and commonalities** — Are the errors related? Do they share an error code, endpoint, or root cause?
- **Timeline of events** — What happened first? What appears to be the root cause vs. cascading failures?
- **Affected services and endpoints** — Which services and endpoints are impacted?
- **Stack traces and error details** — What does the error detail reveal about the failure mechanism?
- **Recommended next steps** — Should the user fix a bug, investigate a dependency, check configuration, or scale a resource?

If deeper investigation is needed beyond log analysis, suggest using the **o11y-service-health** skill to check overall service status and metrics.

## Edge Cases

| Scenario | Approach |
|----------|----------|
| **No results found** | Widen the time window, remove filters, verify the service name with `list-services`. Confirm that logs exist for the target service and time period. |
| **Too many results to be useful** | Add severity, keyword, or field filters. Narrow the time window. Focus on a single service or endpoint. |
| **Log entries are truncated** | Use `get-log-entry` to fetch the full log entry by its ID. Truncation often hides stack traces and error details. |
| **Logs not available for time window** | The logs may be outside the retention period. Inform the user and suggest checking if extended retention or archives are available. |
| **Multiple services involved** | Use trace IDs or correlation IDs to follow the request across services. Start with the service closest to the user (API gateway or edge service) and work inward. |
| **User provides a trace ID** | Search directly for the trace ID across all services. Sort by timestamp to reconstruct the request flow. |
| **User provides an error message** | Use the error message as a keyword filter. If it is long, use the most unique portion to avoid partial match issues. |
| **User describes general symptoms** | Start with a broad error-level query on the likely service. Use facets and aggregation to identify the dominant error patterns, then drill into the most relevant one. |

## What NOT to Do

- **Don't dump raw logs without interpretation.** Always summarize and contextualize the results. The user wants insights, not a wall of log text.
- **Don't search without a time window.** Open-ended queries are expensive, slow, and return overwhelming amounts of data. Always apply a time constraint.
- **Don't assume log completeness.** Log sampling, ingestion delays, and retention policies mean that not every event is captured. Absence of evidence is not evidence of absence.
- **Don't ignore structured fields in favor of free-text search.** Structured fields are faster and more precise. Only fall back to free-text when structured fields are unavailable or insufficient.
- **Don't stop at the first error.** The first error you find may be a symptom, not the root cause. Look at the timeline to find the earliest error, and check for related entries in upstream services.
- **Don't present timestamps without timezone context.** Always clarify whether timestamps are in UTC or local time to avoid confusion.

## References

- [Log Query Patterns Reference](references/query-patterns.md) — Detailed patterns for error hunting, request tracing, aggregation, and query refinement.
- **o11y-service-health** — Use for metric-level investigation when log analysis alone is insufficient to diagnose the issue.
