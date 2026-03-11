# Segment Types

Reference for choosing the right segment type and understanding the constraints of each.

## Quick Decision Guide

| Audience definition | Segment type | Size limit |
|---|---|---|
| Attribute-based (email, plan, country, etc.) | Rule-based | Up to 15,000 individual overrides |
| Explicit list of known context keys | Smaller list-based | Up to 15,000 keys |
| Large list of context keys (>15,000) | Larger list-based (unbounded) | No hard limit; requires BigSegment store |
| Synced from external tool (Amplitude, Twilio, etc.) | Synced segment | Depends on store |

## Rule-Based Segments

Rule-based segments match contexts by evaluating attribute conditions. They are the most flexible type and support both targeting rules and individual target overrides.

**Best for:**
- Audiences defined by a business characteristic ("all enterprise accounts", "users in the EU", "email ends in @company.com")
- Audiences that change naturally as attributes change — no manual maintenance required
- Audiences that combine multiple conditions

**Constraints:**
- Up to 5,000 targeting rules per segment
- Up to 50,000 values across all rule clauses
- Up to 15,000 individual context targets (included + excluded combined)

**API creation:** `POST /segments` with no special fields (default is rule-based).

## Smaller List-Based Segments

Smaller list-based segments are for when you have a known, explicit list of context keys. They support both individual targets and targeting rules.

**Best for:**
- Early access programs where you have collected specific user signups
- Internal employee lists ("our 50 internal testers")
- Partner or customer lists maintained manually

**Constraints:**
- Maximum 15,000 individual context targets
- Same as rule-based for rule support (5,000 rules, 50,000 values)

**API creation:** Same as rule-based — no special fields needed unless exceeding 15,000 targets.

## Larger List-Based Segments (Unbounded / BigSegments)

Larger list-based segments are for audiences exceeding 15,000 entries. LaunchDarkly uses a different implementation ("BigSegments") to maintain performance at scale.

**Best for:**
- Large customer lists (tens of thousands to millions of entries)
- Bulk imports via CSV

**Critical requirement:** Server-side SDKs require a persistent store integration (Redis, DynamoDB, etc.) to be configured in each environment before BigSegments work. Without this, the SDK cannot evaluate BigSegment membership and will return the fallback variation.

**API creation:** Set `unbounded: true` in the POST body.

**When to flag this:** If a user mentions "we have 50,000 users" or uploads a CSV, prompt them about BigSegment store configuration before proceeding.

## Context Kinds

All segment types are context-kind-aware. Each rule clause and individual target instruction applies to one context kind.

| Situation | What to do |
|---|---|
| Targeting user contexts | Use `contextKind: "user"` (or omit — it defaults to user) |
| Targeting org/account contexts | Use `contextKind: "organization"` (or whatever the project uses) |
| Multiple kinds in one segment | Use separate rules per context kind — a single rule applies to one kind |

To find what context kinds a project uses, check existing flag targeting rules or ask the user.

## Segment vs. Flag Targeting Rules

A common question: when should you define rules in a segment vs. directly in a flag's targeting rules?

**Use a segment when:**
- The same audience applies to multiple flags
- The audience definition may change (you'd rather update one place)
- The audience has a reusable business meaning ("enterprise customers", "beta testers")

**Use flag targeting rules directly when:**
- The rule only applies to this one flag
- The rule is a one-off, experiment-specific condition
- You want to keep targeting logic close to the flag

If a user defines an audience that is already being used — or will be used — in multiple flags, suggest creating a segment and wiring it in, rather than duplicating the rule in each flag.
