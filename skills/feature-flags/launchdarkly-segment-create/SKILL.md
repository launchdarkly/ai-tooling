---
name: launchdarkly-segment-create
description: "Create and configure LaunchDarkly segments — reusable audience definitions for flag targeting. Use when the user wants to create a segment, add targeting rules to a segment, add individual contexts to a segment, or wire an existing segment into a feature flag's targeting rules."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.0.0-experimental"
---

# LaunchDarkly Segment Create & Configure

You're using a skill that will guide you through creating a reusable audience segment in LaunchDarkly. Your job is to explore what segments already exist, choose the right segment type, create the segment, configure its membership through rules or individual targets, and optionally wire it into a feature flag's targeting rules.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Required MCP tools:**
- `list-segments` — check what segments already exist before creating one
- `create-segment` — create a new rule-based or list-based segment in an environment
- `get-segment` — verify the segment was created and configured correctly

**Configuration tools (use the one that matches the segment's membership model):**
- `update-segment-rules` — add or modify attribute-based targeting rules
- `update-segment-targets` — add or remove individual context keys

**Optional MCP tool (to wire the segment into a flag):**
- `update-targeting-rules` — add a `segmentMatch` rule to an existing feature flag

## Core Principles

1. **Check before creating.** A segment with the same name or purpose may already exist. Avoid creating duplicates by listing segments first and checking for overlap.
2. **Segment type drives the configuration path.** Rule-based segments match contexts by attribute (email, plan tier, country). List-based segments target specific keys explicitly. The right type depends on whether the audience is defined by attributes or by identity. See [Segment Types](references/segment-types.md).
3. **Segments are environment-specific.** A segment created in `staging` does not exist in `production`. If the segment needs to exist in multiple environments, it must be created separately in each.
4. **The segment key is immutable.** Once created, the key cannot be changed. Choose it carefully — use `kebab-case`, match the project's existing naming convention, and make it descriptive.

## Workflow

### Step 1: Explore Existing Segments

Before creating anything, confirm the environment and check what already exists.

1. **Confirm the environment.** Segments are environment-specific. Always confirm which environment the user is targeting before proceeding. If not specified, ask rather than assume.
2. **List existing segments.** Use `list-segments` to scan what's there. Look for:
   - A segment that already covers the same audience (avoid duplicates)
   - Naming conventions already in use (e.g., `beta-testers`, `internal-qa`, `enterprise-accounts`)
   - Tags used to organize segments

### Step 2: Assess the Segment Type

Before creating, determine the right segment type based on what the user describes. See [Segment Types](references/segment-types.md) for the full guide.

| Audience description | Segment type | Configuration path |
|---|---|---|
| "All users with an enterprise plan" | Rule-based | `update-segment-rules` → `addRule` with attribute clause |
| "Users whose email ends in @company.com" | Rule-based | `update-segment-rules` → `addRule` with email clause |
| "These specific user keys: [list]" | List-based | `update-segment-targets` → `addIncludedTargets` |
| "Internal testers — I have their keys" | List-based | `update-segment-targets` → `addIncludedTargets` |
| "All enterprise orgs except these two" | Rule-based + exclusions | `update-segment-rules` → `addRule` + `update-segment-targets` → `addExcludedTargets` |

If in doubt, default to rule-based. It's more flexible and easier to maintain as the audience evolves.

### Step 3: Create the Segment

Use `create-segment` with the key, name, environment, and optional tags and description.

Key notes:
- Segment keys are **immutable** after creation — confirm the key before proceeding.
- Set `unbounded: false` for standard rule-based and smaller list-based segments (15,000 or fewer individual targets). Only set `unbounded: true` for larger list-based segments requiring a BigSegment store.
- Suggest tags based on the segment's purpose, team, or related feature area.

After creation, the segment is empty — it has no rules and no individual targets. Proceed to Step 4 to configure membership.

### Step 4: Configure Segment Membership

Choose the path based on the segment type from Step 2.

#### Path A: Rule-based — Use `update-segment-rules`

Add targeting rules that match contexts by attribute. See [Segment Rule Patterns](references/segment-rule-patterns.md) for instruction examples.

Supported instruction kinds:
- `addRule` — add a new targeting rule with clauses
- `removeRule` — remove a rule by ID
- `addClauses` — add additional clauses to an existing rule
- `removeClauses` — remove clauses from a rule
- `updateClause` — replace a clause entirely
- `addValuesToClause` — append values to a clause's values list
- `removeValuesFromClause` — remove specific values from a clause
- `reorderRules` — change rule evaluation order
- `updateRuleDescription` — update a rule's label
- `updateRuleRolloutAndContextKind` — change percentage and context kind for a percentage-based rule

Rules within a single rule object are ANDed. To match multiple independent conditions with OR logic, add multiple separate rules.

#### Path B: List-based — Use `update-segment-targets`

Add or remove explicit context keys. Supported instruction kinds:
- `addIncludedTargets` — include context keys (requires `contextKind` and `values`)
- `removeIncludedTargets` — remove previously included keys
- `addExcludedTargets` — explicitly exclude context keys from the segment
- `removeExcludedTargets` — remove previously excluded keys

Always include `contextKind` in the instruction. Defaults to `user` if omitted, but be explicit.

### Step 5: Wire Into a Flag (Optional)

If the user wants to use the segment in a feature flag, add a targeting rule to the flag that matches on the segment.

Use the existing `update-targeting-rules` tool with a `segmentMatch` clause:

```json
{
  "kind": "addRule",
  "clauses": [
    {
      "contextKind": "user",
      "attribute": "segmentMatch",
      "op": "segmentMatch",
      "values": ["<segment-key>"]
    }
  ],
  "variationId": "<variation-id>",
  "description": "Users in <segment-name> segment"
}
```

The `variationId` must be the `_id` field from the flag's variations array (retrieved via `get-flag`). Do not use variation index — use the `_id` string.

For non-user context kinds, set `contextKind` to match the segment's context kind.

### Step 6: Verify

After creating and configuring the segment:

1. **Fetch the segment.** Use `get-segment` to confirm:
   - `rulesCount` matches the number of rules added
   - `included`/`excluded` counts reflect the target list changes
   - `tags` and `description` are correct
2. **If wired to a flag**, use `get-flag` to confirm the rule appears in the flag's targeting rules for the correct environment.
3. **Summarize for the user.** Describe the resulting state in plain language:
   - "The `beta-testers` segment in staging now has 1 targeting rule: users whose email ends in `@example.com`. It is wired into the `new-onboarding` flag — beta testers will receive the `true` variation."

## Edge Cases

| Situation | Action |
|---|---|
| Segment key already in use | Fetch the existing segment with `get-segment` and show the user what it contains. Ask if they want to configure that segment or create a new one with a different key. |
| User wants to target multiple context kinds in one rule | Create separate rules for each context kind. A single rule's clauses all apply to the same context kind. |
| User has a list of >15,000 context keys | Use `unbounded: true` when creating the segment. Warn the user that BigSegment storage must be configured in the environment for the SDK to evaluate it correctly. |
| Wiring into a flag requires approval | The `update-targeting-rules` call will return `requiresApproval: true` with an `approvalUrl`. Surface this to the user and do not retry the change. |
| User wants the segment in multiple environments | Segments are environment-specific. The workflow must be run once per environment. The segment key and name can be identical across environments, but each is independent. |
| User wants to delete a segment | Deleting segments is out of scope for this skill. Use the LaunchDarkly UI or REST API directly. Caution: deleting a segment that is referenced by flag targeting rules will break those rules. |

## What NOT to Do

- Don't create a segment without first checking for duplicates. Step 1 exists for this reason.
- Don't use the `unbounded: true` flag for small lists — it requires a BigSegment store and adds operational complexity without benefit.
- Don't pass variation index numbers to `update-targeting-rules` when wiring a segment into a flag. The API requires the variation `_id` string. Use `get-flag` to look it up.
- Don't add API-level implementation details (segment response shapes, endpoint paths) into conversations with the user. Keep the user experience at the workflow level.
- Don't run `update-segment-rules` and `update-segment-targets` on the same PATCH request — they are separate tools targeting different instruction categories.

## References

- [Segment Types](references/segment-types.md) — Rule-based vs list-based decision guide, context kind considerations, size limits
- [Segment Rule Patterns](references/segment-rule-patterns.md) — Semantic patch instruction examples for rules, individual targets, and wiring into flag targeting
