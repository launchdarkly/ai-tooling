---
name: launchdarkly-flag-recreate
description: "Recreate a misconfigured LaunchDarkly feature flag when the key or variation type was set wrong. Use when a flag has a typo in its key, the wrong kind (boolean vs multivariate), or incorrect variation values that cannot be changed after creation."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# LaunchDarkly Flag Recreate

You're using a skill that will guide you through recreating a misconfigured feature flag. Flag keys and variation types are immutable after creation, so when they're wrong, the only fix is to create a new flag with the correct configuration and migrate everything over. Your job is to capture the old flag's full state, create a correct replacement, migrate targeting across environments, update code references, and archive the old flag.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Required MCP tools:**
- `get-flag` — read the misconfigured flag's full configuration per environment
- `create-flag` — create the replacement flag with the correct key/kind/variations
- `toggle-flag` — set on/off state per environment on the new flag
- `update-rollout` — set fallthrough rules on the new flag
- `update-targeting-rules` — reconstruct custom targeting rules on the new flag
- `update-individual-targets` — reconstruct individual targets on the new flag
- `get-flag-status-across-envs` — check the old flag's status in all environments

**Optional MCP tools (enhance workflow):**
- `archive-flag` — archive the old flag after migration
- `list-flags` — verify naming conventions in the project
- `update-flag-settings` — copy metadata (tags, description) if needed
- `update-off-variation` — set the off variation when the old flag used a non-default one
- `update-prerequisites` — migrate prerequisites onto the new flag; update dependent flags to point to the new key

## Core Principles

1. **Capture Before You Create**: Read the old flag's full configuration before making any changes. You need a complete picture of targeting across all environments.
2. **One Environment at a Time**: Migrate targeting environment by environment. Verify each before moving on.
3. **Don't Rush the Cutover**: The new flag starts OFF. Only toggle it on in an environment after targeting is fully reconstructed there.
4. **Keep the Old Flag Until Verified**: Don't archive or delete the old flag until the new one is confirmed working in all environments.

## Workflow

### Step 1: Explore the Old Flag

Get the full picture of the misconfigured flag before doing anything.

1. **Get the flag configuration.** Use `get-flag` for each environment the flag is used in. Record:
   - Flag key, name, kind, description, tags, temporary status
   - Variations (values and names)
   - Per-environment: on/off state, fallthrough, rules, individual targets, off variation, prerequisites

2. **Check status across environments.** Use `get-flag-status-across-envs` to see which environments are active, inactive, or launched.

3. **Search the codebase for references.** Find all places the old flag key appears:
   - SDK evaluation calls
   - Constants/enums
   - Tests
   - Configuration files

4. **Summarize what you found.** Present the user with:
   - The flag's current configuration
   - Which environments have active targeting
   - How many code references exist
   - The complexity of migration (simple if no targeting, complex if rules/targets exist)

### Step 2: Assess the Correction

Determine exactly what needs to change and confirm with the user.

| What's Wrong | What to Fix |
|-------------|-------------|
| Typo in the key | New key with correct spelling; same kind, variations, and metadata |
| Wrong kind (boolean instead of multivariate) | New kind; user must define the correct variations |
| Wrong kind (multivariate instead of boolean) | Switch to boolean; variations become `true`/`false` |
| Wrong variation values | Same kind; new variations with correct values |
| Multiple issues | Fix all at once in the new flag |

**Confirm with the user:**
- What should the new flag key be?
- If changing kind: what variations should the new flag have?
- If the old flag has targeting rules that reference specific variation indices, how should those map to the new variations?

### Step 3: Create the Replacement Flag

Use `create-flag` with the corrected configuration.

```
create-flag:
  projectKey: <same project>
  name: <same name or corrected name>
  key: <corrected key>
  kind: <corrected kind>
  description: <same description>
  temporary: <same value>
  tags: <same tags>
  variations: <corrected variations if multivariate>
```

After creation, use `get-flag` on the new flag to verify it was created with the right configuration. The new flag will be OFF in all environments.

### Step 4: Migrate Targeting

For each environment that had active targeting on the old flag, reconstruct the targeting on the new flag. Work through one environment at a time.

**Migration order:**
1. **Non-production environments first** — start with dev/staging to validate the process
2. **Production last** — only after you've verified the pattern works

**Per environment, in order:**

1. **Set the fallthrough (default rule).** Use `update-rollout` to match the old flag's fallthrough. If the old flag served a single variation, set `rolloutType: "variation"`. If it used a percentage rollout, set `rolloutType: "percentage"` with matching weights.

2. **Set the off variation (if non-default).** If the old flag used a different off variation than the default (last variation), use `update-off-variation` to set it on the new flag. When targeting is OFF, the flag serves this variation.

3. **Add prerequisites (if any).** If the old flag has prerequisites (depends on other flags), use `update-prerequisites` to add the same prerequisites to the new flag.

4. **Add custom targeting rules.** Use `update-targeting-rules` with `addRule` instructions for each rule from the old flag. Reconstruct clauses and variation assignments.

5. **Add individual targets.** Use `update-individual-targets` with `addTargets` or `addContextTargets` instructions for each targeting entry.

6. **Toggle on.** Once targeting is reconstructed, use `toggle-flag` to turn the new flag on in this environment.

7. **Verify.** Use `get-flag` on the new flag in this environment to confirm the targeting matches the old flag.

See [Targeting Migration Guide](references/targeting-migration.md) for detailed instructions on reconstructing each type of targeting.

**Important:** If the variation type changed (boolean to multivariate or vice versa), variation indices will be different. You must map old variation indices to new ones before reconstructing rules and fallthrough. Confirm this mapping with the user.

### Step 5: Update Code References

After the new flag is live, update all code references from the old key to the new key.

1. **Replace the flag key** in all locations found in Step 1.
2. **Update variation handling** if the kind or variation values changed:
   - Boolean to multivariate: replace boolean checks with value comparisons
   - Multivariate to boolean: replace value comparisons with boolean checks
   - Same kind, different values: update any hardcoded variation value references
3. **Update constants/enums** if the flag key is defined in a constants file.
4. **Update tests** to reference the new key and variation values.

### Step 6: Archive the Old Flag

Once the new flag is verified and all code references are updated:

1. **Confirm with the user** before archiving. Verify:
   - New flag is ON and serving correctly in all needed environments
   - All code references point to the new key
   - The old flag is no longer being evaluated (check status)

2. **Archive the old flag** using `archive-flag`. This is reversible — prefer it over `delete-flag`.

### Step 7: Verify

Confirm the full migration is complete:

1. **New flag exists** with correct key, kind, and variations. Use `get-flag`.
2. **Targeting matches** in all environments. Compare with the configuration captured in Step 1.
3. **Code compiles and lints.** Run the project's build/lint step.
4. **Old flag is archived.** Confirm with `get-flag` (should show archived status or error).
5. **Report results:**
   - Old flag key and what was wrong
   - New flag key and what was corrected
   - Environments migrated
   - Code files updated
   - Any issues or follow-ups needed

## Edge Cases

| Situation | Action |
|-----------|--------|
| Old flag has no targeting (just defaults) | Simple — create new flag and update code references only |
| Old flag has complex rules across many environments | Migrate non-prod first, verify, then prod |
| Old flag has prerequisites (it depends on other flags) | Use `update-prerequisites` to add the same prerequisites to the new flag per environment |
| Old flag is a prerequisite for other flags | Use `update-prerequisites` on each dependent flag to replace the old key with the new key before archiving |
| Variation index mapping changed | Build an explicit old-index → new-index map, confirm with user |
| Old flag has expiring targets | Note them, recreate on the new flag using `manage-expiring-targets` |
| Old flag is actively serving production traffic | Coordinate with user — may need the new flag to go live before the old one goes off |
| Environment requires approval for changes | `toggle-flag` will return `requiresApproval: true` — inform the user |
| Kind changed from boolean to multivariate | All existing `boolVariation()` calls must change to `variation()` with value comparison |
| Only the key is wrong, targeting is complex | Consider if a key typo is tolerable vs the cost of migrating complex targeting |

## What NOT to Do

- Don't delete the old flag before the new one is fully verified and serving traffic
- Don't migrate production first — always start with non-production environments
- Don't assume variation indices map 1:1 when the kind or variations changed
- Don't skip confirming the new configuration with the user before creating
- Don't leave the old flag active after migration — archive it to avoid confusion
- Don't batch all environment migrations into one step — go one at a time and verify

## Tool Stubs

The following tools are referenced by this skill but may not yet exist. Stub definitions for implementers:

### `update-off-variation`

**Description:** Set the off variation for a flag in a specific environment. When targeting is OFF, the flag serves this variation to all contexts. Defaults to the last variation if not set.

**Input:**

| Parameter   | Type   | Required | Description                                         |
|-------------|--------|----------|-----------------------------------------------------|
| projectKey  | string | Yes      | Project key                                         |
| flagKey     | string | Yes      | Flag key                                            |
| env         | string | Yes      | Environment key                                    |
| variationIndex | number | Yes   | Zero-based index of the variation to serve when off |
| comment     | string | No       | Optional change comment                             |

**Returns:** Confirmation of the update (key, env, offVariation index).

**Example call:**
- name: `update-off-variation`
- input: `{ "projectKey": "my-project", "flagKey": "new-flag-key", "env": "production", "variationIndex": 0 }`

### `update-prerequisites`

**Description:** Add or remove prerequisites for a flag in a specific environment. Prerequisites are other flags that must evaluate to specific variations before this flag is evaluated.

**Input:**

| Parameter   | Type   | Required | Description                                                                 |
|-------------|--------|----------|-----------------------------------------------------------------------------|
| projectKey  | string | Yes      | Project key                                                                 |
| flagKey     | string | Yes      | Flag key                                                                    |
| env         | string | Yes      | Environment key                                                             |
| instructions | array | Yes     | Semantic patch instructions: `addPrerequisite` (key, variationId) or `removePrerequisite` (key) |
| comment     | string | No       | Optional change comment                                                      |

**Returns:** Updated prerequisites list for the flag in that environment.

**Example call:**
- name: `update-prerequisites`
- input: `{ "projectKey": "my-project", "flagKey": "new-flag-key", "env": "production", "instructions": [{ "kind": "addPrerequisite", "key": "parent-flag", "variationId": "abc123" }] }`

## References

- [Targeting Migration Guide](references/targeting-migration.md) — Step-by-step instructions for reconstructing targeting rules, rollouts, and individual targets on the new flag
