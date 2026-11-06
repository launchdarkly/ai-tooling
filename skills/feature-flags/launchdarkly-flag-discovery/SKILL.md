---
name: launchdarkly-flag-discovery
description: "Audit your LaunchDarkly feature flags to understand the landscape, find stale or launched flags, and assess removal readiness. Use when the user asks about flag debt, stale flags, cleanup candidates, flag health, or wants to understand their flag inventory."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.1.0-experimental"
---

# LaunchDarkly Flag Discovery

You're using a skill that will guide you through auditing and understanding the feature flag landscape in a LaunchDarkly project. Your job is to explore the project, assess the health of its flags, identify what needs attention, and provide actionable recommendations.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server to be configured in your environment.

**Required MCP tools:**
- `get-flags`: search and browse flags with filtering by state, type, tags; with `flagKey`, get full configuration for a single flag in a specific environment
- `get-flag-status-across-envs`: check a flag's lifecycle status across all environments

**Optional MCP tools (enhance depth):**
- `search-stale-flags`: find flags that are candidates for cleanup, sorted by staleness
- `get-flag-health`: get combined health view for a single flag (merges status + config)
- `get-removal-readiness`: detailed safety check for a specific flag

## Workflow

### Step 1: Understand the Project

Before diving into flag data, establish context:

1. **Identify the project.** Confirm the `projectKey` with the user. If they haven't specified one, ask.
2. **Understand scope.** Ask the user what they're trying to accomplish:
   - Broad audit? ("What's the state of our flags?")
   - Targeted investigation? ("Is this specific flag still needed?")
   - Cleanup planning? ("What flags can we remove?")

### Step 2: Explore the Flag Landscape

Adapt your approach to the user's goal:

**For a broad audit:**
- Use `get-flags` scoped to a critical environment (default to `production`).
- Note the total count: this tells you the scale of the flag surface area.
- Filter by `state` (`live`, `deprecated`, `archived`) to segment the landscape. Lifecycle status (new, active, launched, inactive) comes from `get-flag-status-across-envs`.
- Filter by `type` (temporary vs permanent): temporary flags are the primary cleanup targets.

**For cleanup planning:**
- Use `search-stale-flags`: this is the most efficient entry point. It returns a prioritized list of cleanup candidates sorted by staleness, categorized as:
  - `never_requested`: created but never evaluated (possibly abandoned)
  - `inactive_30d`: no SDK evaluations in the specified period
  - `launched_no_changes`: fully rolled out, no recent changes
- Default `inactiveDays` is 30. Increase for conservative cleanup (60, 90) or decrease for aggressive cleanup (7, 14).
- Default `includeOnly` is `temporary`. Set to `all` to include permanent flags.

**For a targeted investigation:**
- Use `get-flag-health` for a single-flag deep dive. It merges status data with configuration context in one call, returning lifecycle state, last-requested timestamp, targeting summary, age, and whether it's temporary.
- Or use `get-flags` for the full configuration including rules, targets, and fallthrough details.

### Step 3: Assess Flag Health

For flags that need deeper investigation, assess health signals. See [Flag Health Signals](references/flag-health-signals.md) for the full interpretation guide.

Key signals to evaluate:

| Signal | What it tells you |
|--------|-------------------|
| **Lifecycle state** | Where the flag is in its journey (new -> active -> launched -> inactive) |
| **Last requested** | When an SDK last evaluated this flag: staleness indicator |
| **Targeting complexity** | Number of rules and targets: removal complexity indicator |
| **Cross-environment consistency** | Whether the flag behaves the same everywhere |
| **Flag age + temporary status** | Old temporary flags are strong cleanup candidates |

Use `get-flag-status-across-envs` to check if a flag is consistent across environments. A flag inactive in production but active in staging tells a different story than one inactive everywhere.

### Step 4: Categorize and Prioritize

Group flags into actionable categories:

1. **Ready for code removal**: Use the same rule as the **Ready for cleanup** view in the LaunchDarkly flag list. The flag is temporary, at least 30 days old, not a prerequisite of another flag, has code references, and is `launched` in every critical environment (targeting ON, one variation served to every context, evaluated in the last 7 days, targeting not changed in the last 7 days). The day counts are defaults that the project's flag lifecycle settings can change. Direct the user to the [flag cleanup skill](../launchdarkly-flag-cleanup/SKILL.md) for code removal.
2. **Ready to archive**: Temporary, at least 30 days old, not a prerequisite, `inactive` in every critical environment, and no code references. There is no code to remove. The user can archive the flag in LaunchDarkly.
3. **Needs investigation**: Active in some environments but not others, has complex targeting, or is `inactive` everywhere but still has code references. Don't recommend action without more context.
4. **Leave alone**: Active flags doing their job, or permanent flags that are intentionally long-lived.

**A flag that is OFF in every critical environment is never ready for code removal.** It is not `launched`, because `launched` requires targeting to be ON. A flag that is off everywhere often guards a feature that was never released, and hardcoding its `offVariation` deletes that feature's code. Put it in "Needs investigation" (or "Ready to archive" if it has no code references and is `inactive` everywhere). Recommend code removal only if the user explicitly confirms that the code behind the other variations is abandoned.

### Step 5: Assess Removal Readiness (When Applicable)

If the user wants to know whether a specific flag can be removed, use `get-removal-readiness`. This tool orchestrates multiple API calls in parallel and returns a structured verdict:

- **`safe`**: No blockers or warnings, and LaunchDarkly marks the flag ready for code removal (`details.lifecycle.readyForCodeRemoval` is `true`). Recommend the cleanup workflow.
- **`caution`**: Warnings exist (expiring targets, `code_already_removed`, or `code_removal_readiness_unavailable`). `caution` is not permission to remove code. Present each warning and ask the user to confirm before you recommend removal. For `code_removal_readiness_unavailable`, ask the user to confirm in LaunchDarkly that the flag is launched in every critical environment.
- **`blocked`**: The only blocker is `not_ready_for_code_removal`: LaunchDarkly does not consider the flag ready for code removal. Must resolve first. Do not recommend code removal. Give each reason from the blocker detail or `details.lifecycle.codeRemovalBlockers`, and name the critical environments where the flag is not `launched` (from `details.lifecycle.notLaunchedEnvironments`).
- **`caution` with `code_already_removed`** (`details.lifecycle.codeAlreadyRemoved: true`): the flag passes every code removal check, but LaunchDarkly finds no code references. The code is already removed, or it is in a repository that LaunchDarkly does not scan. Recommend archiving it after the cleanup is deployed everywhere the flag is evaluated.
- **`blocked` with `details.lifecycle.readyToArchive: true`**: the flag is inactive everywhere and has no code references. Recommend archiving the flag in LaunchDarkly, not code removal.

See [Removal Readiness Checklist](references/removal-readiness-checklist.md) for the full details on interpreting each signal.

### Step 6: Present Findings

Structure your response based on what the user asked for:

**For audits:** Lead with a summary (total flags, breakdown by state and type), then highlight what needs attention, then provide specific recommendations.

**For specific flags:** Lead with the verdict (healthy / needs attention / ready to remove), then support it with the signals you found.

**For cleanup planning:** Lead with the count of cleanup candidates, prioritize by confidence (safest removals first), and link to the cleanup workflow for execution.

## Important Context

- **"Launched" means fully rolled out**: targeting is on, a single variation is served to everyone, and no changes have been made recently. It doesn't mean "recently deployed."
- **"Off everywhere" is not "launched."** A flag that is OFF in every critical environment serves its `offVariation`, but LaunchDarkly does not count it as ready for code removal.
- **"Inactive" doesn't always mean safe to remove.** The flag might be used in code that hasn't shipped yet, or referenced as a prerequisite by another flag.
- **Permanent flags can be inactive on purpose.** Some flags are designed to be dormant until needed (kill switches, emergency toggles). Don't automatically flag these for cleanup.
- **Weights are scaled by 1000 in the API.** A weight of `60000` means 60%. Always convert to human-readable percentages.
- **This skill is for discovery, not action.** If the user wants to remove a flag from code, direct them to the [flag cleanup skill](../launchdarkly-flag-cleanup/SKILL.md). If they want to change targeting, direct them to the [flag targeting skill](../launchdarkly-flag-targeting/SKILL.md).

## References

- [Flag Health Signals](references/flag-health-signals.md): How to interpret lifecycle states, staleness, and health data
- [Removal Readiness Checklist](references/removal-readiness-checklist.md): Full safety assessment before recommending flag removal
