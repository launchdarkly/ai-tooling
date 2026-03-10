# LaunchDarkly Log Query Skill

## Overview

- Teaches AI agents to search and filter application logs effectively.
- Guides agents through constructing queries, tracing requests across services, and debugging issues using log data.
- Covers error hunting, request tracing, user-journey reconstruction, and pattern detection.
- Provides detailed reference material on query patterns, filter syntax, and refinement strategies.

## Installation (Local)

Add the skill to your agent configuration by referencing the skill directory:

```yaml
skills:
  - path: skills/observability/o11y-log-query
```

## Prerequisites

- **LaunchDarkly MCP server** with observability tools enabled.
- **MCP tools available:**
  - `search-logs` — Search and filter logs by service, time, severity, and keywords.
  - `get-log-entry` — Fetch full details of a specific log entry.
  - `list-services` (optional) — List available services for discovery.

## Usage

**Find errors in a specific service:**

> "Find errors in the checkout service from the last hour"

The agent will query ERROR-level logs for `checkout-service` with a 1-hour time window, summarize the errors found, and identify patterns or root causes.

**Trace a request across services:**

> "Trace request abc-123 across services"

The agent will search for the request ID across all services, reconstruct the request flow chronologically, and highlight any errors or latency issues in the trace.

**Investigate current production issues:**

> "What errors are happening in production right now?"

The agent will query recent ERROR-level logs across services, identify the most frequent error types, and provide a prioritized summary of active issues.

**Debug a specific error:**

> "Why are we getting PAYMENT_DECLINED errors?"

The agent will search for the error code, analyze affected endpoints and users, check the timeline for when errors started, and suggest possible causes.

## Structure

```
o11y-log-query/
├── SKILL.md                          # Skill definition and workflow
├── README.md                         # This file
└── references/
    └── query-patterns.md             # Detailed log query patterns reference
```

## Related

- **o11y-service-health** — Check overall service health using metrics and dashboards. Use when log analysis alone is insufficient.
- **LaunchDarkly MCP Server** — Provides the underlying `search-logs`, `get-log-entry`, and `list-services` tools.

## License

Apache-2.0
