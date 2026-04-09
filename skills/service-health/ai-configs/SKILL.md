---
name: ai-configs
description: Generate a weekly AI Backend Service Health report for Confluence. Queries the Datadog AI Configs dashboard for SLO status, latency, and error patterns, then creates a draft Confluence page following the team's established format. Use when the user asks to write a service health report, on-call report, weekly SLO review, or AI Configs health check.
compatibility: Requires Atlassian MCP server and Datadog MCP server with appropriate permissions.
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# AI Configs Service Health Report

You're using a skill that will guide you through generating a weekly AI Backend Service Health report. Your job is to fetch the previous week's report from Confluence for format reference, query the Datadog dashboard for current metrics, generate a new report following the established pattern, and publish it as a draft.

## Prerequisites

- Atlassian MCP server configured with Confluence access to the PD space
- Datadog MCP server configured (us1 region: `mcp.datadoghq.com`)
- The user should tell you who is on call this week

## Core Principles

1. **Match the existing format**: Always fetch the most recent report and replicate its structure
2. **Data-driven**: Every claim in the report must come from Datadog queries, not assumptions
3. **Link to evidence**: Every error pattern should link to the Datadog log explorer query
4. **Draft first**: Always create as a draft so the on-call engineer can review before publishing

## Workflow

### Step 1: Fetch the Previous Report

Find and read the most recent service health report to understand the current format:

1. **Search Confluence** using CQL:
   ```
   title ~ "AI Backend Service Health" AND space = "PD"
   ```
2. **Read the most recent page** using `getConfluencePage` with `contentFormat: "markdown"`.
3. **Note the structure**: section headings, SLO table format, how errors are listed, and the on-call section.
4. **Capture the parentId and spaceId** from the page metadata for creating the new page in the same location.

### Step 2: Query Datadog for Current Metrics

Query the [AI Configs Health Dashboard](https://app.datadoghq.com/dashboard/r5c-hwh-mx5/ai-configs-product-be-service-health) for the past 7 days.

#### 2a. SLO Status

Fetch the production success rate SLO widget:

```yaml
slo_id: c2def74c83b3518291d3653c55e488c6
time_windows: [7d]
```

Record: SLI value, target threshold, error budget remaining, state (ok/warning/alert).

#### 2b. Latency

Fetch a timeseries widget for p50 and p95 latency:

```yaml
queries:
  - p50:trace.http.request{env:production,service:gonfalon-ai-configs}
  - p95:trace.http.request{env:production,service:gonfalon-ai-configs}
```

Record: average, max, and trend (stable/increasing/decreasing).

#### 2c. Monitor Status

Search for monitors related to AI Configs:

```
title:ai-configs OR title:gonfalon-ai-configs
```

Record which monitors are OK, alerting, or in warning state.

#### 2d. Error Log Patterns

Search for error log patterns in **both production and staging**:

```
((service:gonfalon @sub_service:gonfalon-ai-configs) OR service:ai-evaluator) env:<environment> status:error
```

Use `use_log_patterns: true` with a 7-day window. For each pattern, record: message, count, first/last seen.

#### 2e. 5xx Patterns

Search specifically for HTTP 500-599 patterns:

```
(service:gonfalon-ai-configs OR service:ai-evaluator) env:<environment> @http.status_code:[500 TO 599]
```

### Step 3: Generate the Report

Build the Confluence page body in markdown. Follow this structure:

```markdown
## AI Configs SLOs

| Production | Lenient Latency | STRICT LATENCY | SUCCESS RATE |
| --- | --- | --- | --- |
| Status | <GREEN/YELLOW/RED> | <GREEN/YELLOW/RED> | <GREEN/YELLOW/RED> |

## **Production**

<Summary paragraph: SLO value, error budget, monitor status>

**Latency (7-day):**
* p50: avg Xs, max Xs — <trend>
* p95: avg Xs, max Xs — <trend>

**Error log patterns (7-day):**
* [`<pattern>`](<datadog-logs-url>) — <count> occurrences. <context>.
* ...

## **Staging**

**Error log patterns (7-day):**
* [`<pattern>`](<datadog-logs-url>) — <count> occurrences. <context>.
* ...

## **Non-Green 7-Day SLOs**

* <List any SLOs not meeting target, or "All 7-day SLOs are currently green">

## **This week's on call engineer**

@<name>

## **Next week's on call engineers**

*TBD — update before end of week*
```

#### Building Datadog Log Links

For each error pattern, construct a Datadog logs explorer URL:

```
https://app.datadoghq.com/logs?query=<url-encoded-query>&from_ts=<7d-ago-ms>&to_ts=<now-ms>&live=true
```

The query should be the same service/environment filter with the pattern message in quotes.

### Step 4: Create the Confluence Page

1. **Create as draft** using `createConfluencePage`:
   - `cloudId`: `launchdarkly.atlassian.net`
   - `spaceId`: use the spaceId from Step 1 (currently `2334917956`)
   - `parentId`: use the parentId from Step 1 (currently `3549167899`)
   - `title`: `<Month> <Day> <Year> AI Backend Service Health` (e.g., "April 9 2026 AI Backend Service Health")
   - `status`: `draft`
   - `contentFormat`: `markdown`

2. **Report the draft URL** back to the user so they can review.

### Step 5: Verify

1. Confirm the page was created successfully and return the edit URL
2. Note any sections that need manual attention:
   - SLO status color macros (markdown doesn't support Confluence status macros natively)
   - "Next week's on call engineers" field
   - Any error patterns that need additional context from the on-call engineer

## Edge Cases

| Situation | Action |
|-----------|--------|
| No recent report found | Ask user for the Confluence page URL of a previous report |
| Datadog MCP not configured | Guide user through domain setup (check `mcp.json` for `${DD_MCP_DOMAIN}`) |
| SLO widget returns no data | Fall back to monitor status as a proxy for service health |
| Confluence parentId returns 404 | Search for sibling pages and use their parentId |
| User doesn't know who's on call next week | Leave "TBD" placeholder |
| Dashboard template variables needed | Use `env: production` for production, `env: staging` for staging |

## What NOT to Do

- Don't publish the page as "current" — always create as draft for review
- Don't fabricate error counts or SLO values — every number must come from Datadog
- Don't skip linking error patterns to Datadog log explorer
- Don't omit staging errors — they often foreshadow production issues
- Don't assume the report format is static — always fetch the latest report first

## Key Datadog References

- **Dashboard ID**: `r5c-hwh-mx5`
- **Production Success Rate SLO**: `c2def74c83b3518291d3653c55e488c6`
- **Catamorphic Success Rate SLO**: `acf6a206f2be598991ecf7e1b8fc5914`
- **EU Production Success Rate SLO**: `6df08a1c57f25e398891be716bea8466`
- **Confluence Space**: PD (spaceId: `2334917956`)
