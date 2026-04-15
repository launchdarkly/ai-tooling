---
name: launchdarkly-flag-command
description: "Resolve `/flag` style requests into the right LaunchDarkly flag lookup flow. Use when the user types `/flag`, asks to quickly find a flag by name/key, wants a direct flag detail summary, or needs fast disambiguation between similar flags."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.0.0-experimental"
---

# LaunchDarkly Flag Command Router

You're using a skill that standardizes quick `/flag` requests. Your job is to parse the user intent, resolve the requested flag with minimal friction, return an actionable summary, and route to deeper workflows when needed.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Required MCP tools:**
- `list-flags` — search and disambiguate flag candidates
- `get-flag` — fetch detailed configuration for a resolved flag

**Optional MCP tools:**
- `get-flag-status-across-envs` — compare lifecycle status across environments
- `get-flag-health` — quick health snapshot for a single flag

## Command Contract

Treat these forms as equivalent intents:

- `/flag <query>`
- `flag <query>`
- "find flag <query>"
- "show me <query> flag"

Use `production` as the default environment unless the user specifies another environment.

## Workflow

### Step 1: Parse and Normalize Input

1. Extract the query text after `/flag`.
2. If no query is provided, ask for one concise identifier (flag key, name fragment, or tag).
3. Capture optional hints from the request:
   - Environment (`staging`, `production`, etc.)
   - Project key
   - Preference for exact key vs fuzzy search

### Step 2: Resolve the Flag

Use `list-flags` first unless the user clearly provided an exact key and project.

1. Search with `list-flags` using the query.
2. If one clear exact match exists, resolve to that flag.
3. If multiple plausible matches exist, return a short disambiguation list (key + name + state) and ask the user to pick.
4. If no matches exist, tell the user and suggest one broader query.

### Step 3: Return a Useful Summary

For a resolved flag, call `get-flag` and return:

1. Flag key and name
2. Environment state (`on`/`off`)
3. Off variation and fallthrough behavior
4. Rule/target complexity (simple vs complex)
5. Direct LaunchDarkly URL for the flag (when project + key are known)

If the user asks "is this safe to remove?" or similar, transition to the flag discovery or cleanup workflow instead of improvising a partial readiness check.

### Step 4: Route to the Right Follow-up Workflow

After returning details, route explicitly when asked:

- Creation/change request -> [flag create skill](../launchdarkly-flag-create/SKILL.md)
- Targeting/rollout change -> [flag targeting skill](../launchdarkly-flag-targeting/SKILL.md)
- Staleness/removal/readiness -> [flag discovery skill](../launchdarkly-flag-discovery/SKILL.md) and [flag cleanup skill](../launchdarkly-flag-cleanup/SKILL.md)

## Output Style

Keep `/flag` responses brief and operational:

- Start with the resolved flag (or disambiguation list)
- Include only the minimum config details needed for the next action
- End with one clear next step question when user intent is ambiguous

## Important Context

- `/flag` is a fast entrypoint, not a full lifecycle workflow.
- Prefer disambiguation over guessing when multiple flags match.
- Treat project + environment as first-class context; avoid hidden assumptions.
- When sharing rollout percentages, always use human-readable percentages.
