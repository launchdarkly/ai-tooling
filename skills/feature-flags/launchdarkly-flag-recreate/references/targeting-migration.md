# Targeting Migration Guide

How to reconstruct targeting from one flag onto another using the LaunchDarkly MCP tools. This is needed when a flag was created with the wrong key or variation type and must be replaced.

## Overview

There is no single tool to copy targeting between two different flags. You must read the old flag's targeting configuration and reconstruct it on the new flag using the targeting tools, one environment at a time.

## Before You Start

### Build a Variation Map

If the old and new flags have different variations (different kind, different values, or different ordering), you need a mapping from old variation indices to new ones.

**Same kind, same variations (key-only fix):**
Indices map 1:1. No translation needed.

| Old Index | New Index |
|-----------|-----------|
| 0 | 0 |
| 1 | 1 |

**Boolean to multivariate:**
The old flag had `true` (index 0) and `false` (index 1). Map each to the new variation that represents the equivalent behavior.

| Old Index | Old Value | New Index | New Value |
|-----------|-----------|-----------|-----------|
| 0 | `true` | ? | Confirm with user |
| 1 | `false` | ? | Confirm with user |

**Multivariate to boolean:**
Map each old variation to `true` (index 0) or `false` (index 1). Some information loss is expected — confirm which old variations map to which boolean value.

**Different variation values (same kind):**
Map by semantic meaning, not position. If the old flag had `["small", "large"]` and the new has `["small", "medium", "large"]`, the indices shift.

### Read the Old Flag

For each environment, call `get-flag` on the old flag and record:

```
get-flag:
  projectKey: <project>
  flagKey: <old-flag-key>
  env: <environment>
```

Note these fields from the response:
- `on` — is targeting on or off?
- `fallthrough` — the default rule (variation index or rollout weights)
- `offVariation` — which variation is served when targeting is off
- `rules` — array of custom targeting rules
- `targets` — individual user/context targets
- `prerequisites` — flags this flag depends on

## Migration Steps (Per Environment)

### 1. Set the Fallthrough

The fallthrough (default rule) determines what unmatched contexts receive.

**Single variation fallthrough:**

```
update-rollout:
  projectKey: <project>
  flagKey: <new-flag-key>
  env: <environment>
  rolloutType: variation
  variationIndex: <mapped-index>
  comment: "Migrated from <old-flag-key>"
```

**Percentage rollout fallthrough:**

Translate each weight entry using the variation map.

```
update-rollout:
  projectKey: <project>
  flagKey: <new-flag-key>
  env: <environment>
  rolloutType: percentage
  weights:
    - variationIndex: <mapped-index-A>
      percent: <percent-A>
    - variationIndex: <mapped-index-B>
      percent: <percent-B>
  comment: "Migrated from <old-flag-key>"
```

### 2. Add Custom Targeting Rules

For each rule on the old flag, add a corresponding rule on the new flag. Rules are order-sensitive — add them in the same order they appeared on the old flag.

Each rule has:
- **Clauses**: conditions that match contexts (attribute, op, values)
- **Variation or rollout**: what to serve when the rule matches

**Single-variation rule:**

```
update-targeting-rules:
  projectKey: <project>
  flagKey: <new-flag-key>
  env: <environment>
  instructions:
    - kind: addRule
      clauses:
        - attribute: <attribute>
          op: <operator>
          values: [<values>]
          contextKind: <context-kind>
      variationId: <new-variation-id>
      description: <rule-description>
  comment: "Migrated rule from <old-flag-key>"
```

**Important:** The `addRule` instruction requires a `variationId` (the variation's internal `_id` string), not a `variationIndex`. To get variation IDs, call `get-flag` on the new flag — each variation in the response includes its `_id`.

**Rollout rule:**

```
update-targeting-rules:
  projectKey: <project>
  flagKey: <new-flag-key>
  env: <environment>
  instructions:
    - kind: addRule
      clauses:
        - attribute: <attribute>
          op: <operator>
          values: [<values>]
      rolloutWeights:
        <variation-id-A>: <weight-A>
        <variation-id-B>: <weight-B>
      rolloutContextKind: <context-kind>
  comment: "Migrated rollout rule from <old-flag-key>"
```

### 3. Set the Off Variation

If the old flag used a non-default off variation (anything other than the last variation), set it on the new flag. When targeting is OFF, the flag serves this variation to all contexts.

```
update-off-variation:
  projectKey: <project>
  flagKey: <new-flag-key>
  env: <environment>
  variationIndex: <mapped-index>
  comment: "Migrated from <old-flag-key>"
```

### 4. Add Prerequisites

If the old flag has prerequisites (it depends on other flags), add them to the new flag. Use `update-prerequisites` with `addPrerequisite` instructions. Map variation indices using the same variation map if the prerequisite flag's variations changed.

```
update-prerequisites:
  projectKey: <project>
  flagKey: <new-flag-key>
  env: <environment>
  instructions:
    - kind: addPrerequisite
      key: <prerequisite-flag-key>
      variationId: <variation-id-of-prerequisite-flag>
  comment: "Migrated from <old-flag-key>"
```

**Note:** Prerequisites reference other flags by key. If you're recreating a prerequisite flag in the same migration, add the new prerequisite key, not the old one.

### 5. Add Individual Targets

Individual targets pin specific users or contexts to a variation. They override all rules.

**User targets (legacy):**

```
update-individual-targets:
  projectKey: <project>
  flagKey: <new-flag-key>
  env: <environment>
  instructions:
    - kind: addTargets
      variationId: <new-variation-id>
      values: [<user-key-1>, <user-key-2>]
  comment: "Migrated targets from <old-flag-key>"
```

**Context targets:**

```
update-individual-targets:
  projectKey: <project>
  flagKey: <new-flag-key>
  env: <environment>
  instructions:
    - kind: addContextTargets
      variationId: <new-variation-id>
      contextKind: <context-kind>
      values: [<context-key-1>, <context-key-2>]
  comment: "Migrated context targets from <old-flag-key>"
```

### 6. Toggle On

Only after all targeting is reconstructed:

```
toggle-flag:
  projectKey: <project>
  flagKey: <new-flag-key>
  env: <environment>
  on: true
  comment: "Enabling after migration from <old-flag-key>"
```

### 7. Verify

Call `get-flag` on the new flag in this environment and compare against the old flag's configuration recorded earlier. Check:
- Fallthrough matches (same variation or same rollout percentages)
- Same number of rules with equivalent clauses
- Same individual targets assigned to equivalent variations
- On/off state matches

## Handling Special Cases

### Flags That Depend on the Old Flag

If other flags list the old flag as a prerequisite, those flags need to be updated to reference the new flag key. Use `update-prerequisites` on each dependent flag to remove the old prerequisite and add the new one:

```
update-prerequisites:
  projectKey: <project>
  flagKey: <dependent-flag-key>
  env: <environment>
  instructions:
    - kind: removePrerequisite
      key: <old-flag-key>
    - kind: addPrerequisite
      key: <new-flag-key>
      variationId: <same-variation-id-as-before>
  comment: "Migrate prerequisite from <old-flag-key> to <new-flag-key>"
```

### Expiring Targets

If the old flag has expiring targets, recreate them on the new flag using `manage-expiring-targets`:

```
manage-expiring-targets:
  projectKey: <project>
  flagKey: <new-flag-key>
  env: <environment>
  action: add
  contextKey: <context-key>
  contextKind: <context-kind>
  variationId: <new-variation-id>
  expiresAt: <same-expiry-date>
```

## Migration Checklist

For each environment:

- [ ] Read old flag configuration
- [ ] Map variation indices (if kind or variations changed)
- [ ] Set fallthrough on new flag
- [ ] Set off variation (if old flag used non-default)
- [ ] Add prerequisites (if old flag had any)
- [ ] Add all custom targeting rules (in order)
- [ ] Add all individual targets
- [ ] Add expiring targets (if any)
- [ ] Toggle new flag to match old flag's on/off state
- [ ] Verify new flag configuration matches old flag
- [ ] Update code references from old key to new key

After all environments:

- [ ] All code references updated
- [ ] Code compiles and tests pass
- [ ] Update dependent flags' prerequisites to point to new key (if old flag was a prerequisite)
- [ ] Archive old flag
