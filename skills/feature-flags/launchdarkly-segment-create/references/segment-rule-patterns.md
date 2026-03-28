# Segment Rule Patterns

Reference for all semantic patch instruction shapes used when configuring segments and wiring them into flags.

All `update-segment-rules` and `update-segment-targets` calls use semantic patch. Include the header:
```
Content-Type: application/json; domain-model=launchdarkly.semanticpatch
```

The request body takes `instructions` (required), `environmentKey` (required), and `comment` (optional).

---

## update-segment-rules Instructions

### addRule

Adds a new targeting rule to the segment. The rule matches contexts that satisfy all its clauses (AND logic between clauses).

```json
{
  "kind": "addRule",
  "clauses": [
    {
      "contextKind": "user",
      "attribute": "email",
      "op": "endsWith",
      "negate": false,
      "values": ["@company.com"]
    }
  ],
  "description": "Company employees"
}
```

To include only a percentage of matching contexts:
```json
{
  "kind": "addRule",
  "clauses": [
    {
      "contextKind": "user",
      "attribute": "plan",
      "op": "in",
      "negate": false,
      "values": ["enterprise"]
    }
  ],
  "weight": 50000,
  "rolloutContextKind": "user",
  "description": "50% of enterprise users"
}
```

Weight is in thousandths of a percent: 50000 = 50%.

### removeRule

Removes a rule by its ID. The `ruleId` is the `_id` field from the segment's rules array (returned by `get-segment`).

```json
{
  "kind": "removeRule",
  "ruleId": "a902ef4a-2faf-4eaf-88e1-ecc356708a29"
}
```

### addClauses

Adds additional clauses to an existing rule (narrows the rule's match with AND logic).

```json
{
  "kind": "addClauses",
  "ruleId": "a902ef4a-2faf-4eaf-88e1-ecc356708a29",
  "clauses": [
    {
      "contextKind": "user",
      "attribute": "country",
      "op": "in",
      "negate": false,
      "values": ["US", "CA"]
    }
  ]
}
```

### removeClauses

Removes specific clauses from a rule by clause IDs.

```json
{
  "kind": "removeClauses",
  "ruleId": "a902ef4a-2faf-4eaf-88e1-ecc356708a29",
  "clauseIds": ["10a58772-3121-400f-846b-b8a04e8944ed"]
}
```

### updateClause

Replaces a clause entirely.

```json
{
  "kind": "updateClause",
  "ruleId": "a902ef4a-2faf-4eaf-88e1-ecc356708a29",
  "clauseId": "10a58772-3121-400f-846b-b8a04e8944ed",
  "clause": {
    "contextKind": "user",
    "attribute": "plan",
    "op": "in",
    "negate": false,
    "values": ["enterprise", "pro"]
  }
}
```

### addValuesToClause / removeValuesFromClause

Add or remove individual values from a clause without replacing it.

```json
{
  "kind": "addValuesToClause",
  "ruleId": "a902ef4a-2faf-4eaf-88e1-ecc356708a29",
  "clauseId": "10a58772-3121-400f-846b-b8a04e8944ed",
  "values": ["pro"]
}
```

```json
{
  "kind": "removeValuesFromClause",
  "ruleId": "a902ef4a-2faf-4eaf-88e1-ecc356708a29",
  "clauseId": "10a58772-3121-400f-846b-b8a04e8944ed",
  "values": ["pro"]
}
```

### reorderRules

Reorders all rules. The array must include every rule ID in the desired evaluation order.

```json
{
  "kind": "reorderRules",
  "ruleIds": [
    "rule-id-2",
    "rule-id-1",
    "rule-id-3"
  ]
}
```

### updateRuleDescription

Updates the display label for a rule.

```json
{
  "kind": "updateRuleDescription",
  "ruleId": "a902ef4a-2faf-4eaf-88e1-ecc356708a29",
  "description": "Enterprise users in North America"
}
```

### updateRuleRolloutAndContextKind

Changes the percentage rollout and context kind for a percentage-based rule.

```json
{
  "kind": "updateRuleRolloutAndContextKind",
  "ruleId": "a902ef4a-2faf-4eaf-88e1-ecc356708a29",
  "weight": 75000,
  "contextKind": "user"
}
```

---

## update-segment-targets Instructions

### addIncludedTargets / removeIncludedTargets

Add or remove context keys from the segment's included list.

```json
{
  "kind": "addIncludedTargets",
  "contextKind": "user",
  "values": ["user-key-abc", "user-key-def"]
}
```

```json
{
  "kind": "removeIncludedTargets",
  "contextKind": "user",
  "values": ["user-key-abc"]
}
```

### addExcludedTargets / removeExcludedTargets

Add or remove context keys from the segment's excluded list. Excluded targets are never matched by the segment, even if they would satisfy a targeting rule.

```json
{
  "kind": "addExcludedTargets",
  "contextKind": "user",
  "values": ["known-bad-user-key"]
}
```

```json
{
  "kind": "removeExcludedTargets",
  "contextKind": "user",
  "values": ["known-bad-user-key"]
}
```

---

## Clause Operators Reference

| Operator | Meaning | Example values |
|---|---|---|
| `in` | Exact match (any value in list) | `["enterprise", "pro"]` |
| `endsWith` | String ends with | `["@company.com"]` |
| `startsWith` | String starts with | `["test-"]` |
| `contains` | String contains substring | `["enterprise"]` |
| `matches` | Regex match | `[".*@company\\.com"]` |
| `lessThan` | Numeric less than | `[100]` |
| `greaterThan` | Numeric greater than | `[0]` |
| `semVerEqual` | Semantic version equals | `["2.0.0"]` |
| `semVerGreaterThan` | Semver greater than | `["1.5.0"]` |
| `semVerLessThan` | Semver less than | `["3.0.0"]` |

Set `"negate": true` on any clause to invert it (e.g., "email does NOT end with @company.com").

---

## Wiring a Segment into a Flag

After creating and configuring the segment, use the existing `update-targeting-rules` tool to add a `segmentMatch` rule to a feature flag.

### Step 1: Get the flag to find the variation _id

Use `get-flag` to retrieve the flag's variations array. Each variation has a `_id` field (a UUID string). Use this `_id` — not the variation index — when calling `update-targeting-rules`.

### Step 2: Add a segmentMatch rule

```json
{
  "kind": "addRule",
  "clauses": [
    {
      "contextKind": "user",
      "attribute": "segmentMatch",
      "op": "segmentMatch",
      "values": ["beta-testers"]
    }
  ],
  "variationId": "<variation-_id-from-get-flag>",
  "description": "Users in the beta-testers segment"
}
```

The `values` array contains segment keys. Multiple segment keys use OR logic — the rule matches if the context is in any of the listed segments.

### Step 3: Verify

Use `get-flag` again to confirm the new rule appears in the environment's targeting rules.

### Common patterns

| Goal | segmentMatch clause |
|---|---|
| Target a single segment | `"values": ["beta-testers"]` |
| Target any of multiple segments | `"values": ["beta-testers", "internal-qa"]` |
| Exclude segment members (negate) | Add `"negate": true` to the clause |
| Non-user context kind | Set `contextKind` to the correct kind (e.g., `"organization"`) |
