---
name: launchdarkly-flag-cleanup
description: "Safely remove a feature flag from code while preserving production behavior. Use when the user wants to remove a flag from code, delete flag references, or create a PR that hardcodes the winning variation after a rollout is complete."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.1.0-experimental"
---

# LaunchDarkly Flag Cleanup

You're using a skill that will guide you through safely removing a feature flag from a codebase while preserving production behavior. Your job is to explore the codebase to understand how the flag is used, query LaunchDarkly to determine the correct forward value, remove the flag code cleanly, and verify the result.

If you haven't already identified which flag to clean up, use the [flag discovery skill](../launchdarkly-flag-discovery/SKILL.md) first to audit the landscape and find candidates.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Required MCP tools:**
- `check-removal-readiness`: detailed safety check (orchestrates flag config, cross-env status, dependencies, code references, and expiring targets in parallel)
- `get-flag`: fetch flag configuration for a specific environment

**Optional MCP tools:**
- `archive-flag`: archive the flag in LaunchDarkly after code removal
- `delete-flag`: permanently delete the flag (irreversible, prefer archive)

## Core Principles

1. **Safety First**: Always preserve current production behavior.
2. **LaunchDarkly as Source of Truth**: Never guess the forward value. Query the actual configuration.
3. **Follow Conventions**: Respect existing code style and structure.
4. **Minimal Change**: Only remove flag-related code. No unrelated refactors.

## Workflow

### Step 1: Explore the Codebase

Before touching LaunchDarkly or removing code, understand how this flag is used in the codebase.

1. **Find all references to the flag key.** Search for the flag key string (e.g., `new-checkout-flow`) across the codebase. Check for:
   - Direct SDK evaluation calls (`variation()`, `boolVariation()`, `useFlags()`, etc.)
   - Constants/enums that reference the key
   - Wrapper/service patterns that abstract the SDK
   - Configuration files, tests, and documentation
   - See [SDK Patterns](references/sdk-patterns.md) for the full list of patterns by language

2. **Understand the branching.** For each reference, identify:
   - What code runs when the flag is `true` (or variation A)?
   - What code runs when the flag is `false` (or variation B)?
   - Are there side effects, early returns, or nested conditions?

3. **Note the scope.** How many files, components, or modules does this flag touch? A flag used in one `if` block is simpler than one threaded through multiple layers.

### Step 2: Run the Removal Readiness Check

Use `check-removal-readiness` to get a detailed safety assessment. This single tool call orchestrates multiple checks in parallel:
- Flag configuration and targeting state
- Cross-environment status
- Dependent flags (prerequisites)
- Expiring targets
- Code reference statistics

The tool returns a readiness verdict:

**`safe`**: No blockers or warnings. Proceed with removal.

**`caution`**: No hard blockers but warnings exist (e.g., code references in other repos, expiring targets scheduled, flag marked as permanent). Present warnings and let the user decide.

**`blocked`**: Hard blockers prevent safe removal (e.g., dependent flags, actively receiving requests, targeting is on with active rules). Present blockers: the user must resolve them first.

#### Also apply LaunchDarkly's "Ready for cleanup" rule

The verdict alone is not enough. Use the same rule as the **Ready for cleanup** view in the LaunchDarkly flag list. A flag is ready for code removal only when all of these are true:

1. The flag is **temporary**.
2. The flag was **created at least 30 days ago**.
3. **No other flag uses it as a prerequisite.**
4. The flag is **`launched` in every critical environment**. `launched` means:
   - targeting is **ON**,
   - every context gets the **same single variation** (no percentage rollout, and no rules or individual targets that serve a different variation),
   - an SDK **evaluated the flag in the last 7 days**, and
   - the flag's targeting was **not changed in the last 7 days**.
5. The flag has **code references**. This is true here, because you found them in Step 1.

The day counts are the defaults. A project can change them, and it can turn off the temporary, prerequisite, and single-variation checks, in its flag lifecycle settings.

Use `get-flag` in each critical environment and the lifecycle status from `check-removal-readiness` to check items 1 to 4.

**A flag that is OFF in a critical environment is not `launched`, so it is not ready for code removal.** This is true even when every critical environment is OFF and serves the same `offVariation`. A flag that is off everywhere often guards a feature that was never released. If you hardcode the `offVariation`, you delete the code for that feature. LaunchDarkly lists a flag that is off everywhere, has had no evaluations recently, and has no code references as **ready to archive**, not as ready for code removal.

If any item is false, stop and tell the user which items fail, even when the verdict is `safe`. Do not offer to continue unless the user explicitly asks to remove the flag anyway. For a flag that is off everywhere, continue only if the user explicitly confirms that the code behind the other variations is abandoned and must be deleted. Record that confirmation in the PR description.

### Step 3: Determine the Forward Value

Use `get-flag` to fetch the flag configuration in each critical environment. The **forward value** is the variation that replaces the flag in code.

| Scenario | Forward Value |
|----------|---------------|
| All critical envs ON, same fallthrough, no rules/targets | Use `fallthrough.variation` |
| All critical envs OFF, same offVariation | **NOT READY**: the flag is not `launched` (see Step 2). Stop and inform the user. Use `offVariation` only after the user explicitly confirms that the code behind the other variations is abandoned. |
| Critical envs differ in ON/OFF state | **NOT SAFE**: stop and inform the user |
| Critical envs serve different variations | **NOT SAFE**: stop and inform the user |

### Step 4: Present the Cleanup Plan

Before modifying any code, present a summary to the user and wait for confirmation:

1. **The forward value** — which variation will be hardcoded and why (based on the flag's current state).
2. **All code references found** — file paths and line numbers from Step 1.
3. **Planned changes** — for each reference, describe what will be removed and what will be kept.
4. **Readiness verdict** — the result from `check-removal-readiness` (safe, caution, or blocked), any warnings, and whether the flag meets the "Ready for cleanup" rule in Step 2. If the flag is off in every critical environment, say so and say that the user confirmed the code behind the other variations is abandoned.
5. **LaunchDarkly action** — confirm the flag will be archived after code changes are complete.

**Do not proceed with code changes until the user explicitly confirms.**

### Step 5: Remove the Flag from Code

Now execute the removal using what you learned in Step 1.

1. **Replace flag evaluations with the forward value.**
   - Preserve the code branch matching the forward value
   - Remove the dead branch entirely
   - If the flag value was assigned to a variable, replace the variable with the literal value or inline it

2. **Clean up dead code.**
   - Remove imports, constants, and type definitions that only existed for the flag
   - Remove functions, components, or files that only existed for the dead branch
   - Check for orphaned exports, hooks, helpers, styles, and test files
   - If the repo uses an unused-export tool (Knip, ts-prune, lint rules), run it and remove any flag-related orphans

3. **Don't over-clean.**
   - Only remove code directly related to the flag
   - Don't refactor, optimize, or "improve" surrounding code
   - Don't change formatting or style of untouched code

**Example transformation (boolean flag, forward value = `true`):**

```typescript
// Before
const showNewCheckout = await ldClient.variation('new-checkout-flow', user, false);
if (showNewCheckout) {
  return renderNewCheckout();
} else {
  return renderOldCheckout();
}

// After
return renderNewCheckout();
```

### Step 6: Create Pull Request

Use the template in [references/pr-template.md](references/pr-template.md) for a structured PR description. The PR should clearly communicate:
- What flag was removed and why
- What the forward value is and why it's correct
- The readiness assessment results (from `check-removal-readiness`)
- What code was removed and what behavior is preserved
- Whether other repos still reference this flag

### Step 7: Verify

Before considering the job done:

1. **Code compiles and lints.** Run the project's build and lint steps.
2. **Tests pass.** If the flag was used in tests, the tests should be updated to reflect the hardcoded behavior.
3. **No remaining references.** Search the codebase one more time for the flag key to make sure nothing was missed.
4. **PR is complete.** The description covers the readiness assessment, forward value rationale, and any cross-repo coordination needed.

## Edge Cases

| Situation | Action |
|-----------|--------|
| Flag not found in LaunchDarkly | Inform user, check for typos in the key |
| Flag already archived | Ask if code cleanup is still needed (flag is gone from LD but code may still reference it) |
| Flag is OFF in every critical environment | Not ready for code removal (not `launched`). Stop and tell the user. Continue with `offVariation` only if the user explicitly confirms that the code behind the other variations is abandoned |
| Multiple SDK patterns in codebase | Search all patterns: `variation()`, `boolVariation()`, `variationDetail()`, `allFlags()`, `useFlags()`, plus any wrappers |
| Dynamic flag keys (`flag-${id}`) | Warn that automated removal may be incomplete: manual review required |
| Different default values in code vs LD | Flag as inconsistency in the PR description |
| Orphaned exports/files remain after removal | Run unused-export checks and remove dead files |

## What NOT to Do

- Don't change code unrelated to flag cleanup.
- Don't refactor or optimize beyond flag removal.
- Don't remove flags still being actively rolled out.
- Don't treat a flag that is OFF everywhere as ready for removal. It is not `launched`, and it may guard a feature that was never released.
- Don't guess the forward value: always query LaunchDarkly.

## After Cleanup

Once the PR is merged and deployed:
1. **Archive the flag in LaunchDarkly** using `archive-flag`. Archival is reversible; deletion is not. Always archive first.
2. **Notify other teams** if `check-removal-readiness` reported code references in other repositories.
3. **If the flag had targeting changes pending,** they can be ignored: the flag is being removed.

## References

- [PR Template](references/pr-template.md): Structured PR description for flag removal
- [SDK Patterns](references/sdk-patterns.md): Flag evaluation patterns by language/framework
- [Flag Discovery](../launchdarkly-flag-discovery/SKILL.md): Find cleanup candidates before using this skill
- [Flag Targeting](../launchdarkly-flag-targeting/SKILL.md): If you need to change targeting instead of removing
