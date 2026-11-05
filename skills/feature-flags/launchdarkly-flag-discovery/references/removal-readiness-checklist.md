# Removal Readiness Checklist

A systematic safety check to determine whether a feature flag can be safely removed. Run through this checklist before recommending flag removal to a user.

## The Checklist

### 1. Cross-Environment Status

**Check:** Use `get-flag-status-across-envs` to verify the flag's state in all environments. If you ran `get-removal-readiness`, `details.lifecycle` holds LaunchDarkly's own result: `readyForCodeRemoval`, `readyToArchive`, and the lifecycle status in each critical environment.

**Pass criteria (code removal):**
- Flag is `launched` in ALL critical environments (production, staging, etc.): targeting ON, one variation served to every context, evaluated in the last 7 days, and targeting not changed in the last 7 days. This is the rule the LaunchDarkly **Ready for cleanup** view uses.

**Pass criteria (archive only):**
- Flag is `inactive` in ALL critical environments and has no code references. There is no code to remove.

**Fail criteria:**
- Flag is `active` in any critical environment
- Flag is `new` anywhere (still being rolled out)
- Critical environments show different states (e.g., production ON, staging OFF)
- Flag is OFF in every critical environment. It is not `launched`, and it may guard a feature that was never released. Do not recommend code removal unless the user explicitly confirms that the code behind the other variations is abandoned.

### 2. Configuration Consistency

**Check:** Use `get-flags` for each critical environment and compare configurations.

**Pass criteria:**
- All critical environments are ON and serve the same `fallthrough.variation` (the same `offVariation` is not enough: see check 1)
- No targeting rules or individual targets exist in critical environments

**Caution criteria:**
- Environments serve the same variation but through different mechanisms (one via fallthrough, another via rules)
- Simple rules exist but all resolve to the same variation

**Fail criteria:**
- Critical environments serve different variations
- Complex targeting rules exist that serve multiple variations
- Individual targets override the default behavior

### 3. Dependency Check

**Check:** Look for `prerequisites` in the flag configuration. Also check if this flag appears as a prerequisite in other flags.

**Pass criteria:**
- No other flags list this flag as a prerequisite
- This flag has no prerequisites of its own (simpler removal)

**Fail criteria (hard blocker):**
- Other flags depend on this flag as a prerequisite: removing it would break their targeting logic

### 4. Code References

**Check:** If available, use `get-removal-readiness` which includes code reference statistics. Otherwise, use `get-flag-code-references` to find repositories that reference this flag.

**Pass criteria:**
- No code references found, or references only exist in the current repository (about to be cleaned up)

**Caution criteria:**
- Code references exist in multiple repositories: flag removal in code needs to be coordinated

**Note:** Code reference scanning has limitations. It tracks static string matches and may miss dynamic flag key construction (`flag-${name}`) or have false positives from comments/documentation.

### 5. Expiring Targets

**Check:** Look for scheduled expiring targets on the flag.

**Pass criteria:**
- No expiring targets scheduled

**Caution criteria:**
- Expiring targets exist: someone actively set a future removal date. Coordinate with them.

### 6. Flag Type

**Check:** The `temporary` field on the flag.

**Pass criteria:**
- Flag is marked as `temporary`: it was intended to be removed

**Caution criteria:**
- Flag is marked as `permanent`: it may be intentionally long-lived. Confirm with the user before recommending removal.

## Readiness Levels

After running the checklist, categorize the result:

### Safe
All checks pass. No blockers or warnings, and LaunchDarkly marks the flag ready for code removal (`details.lifecycle.readyForCodeRemoval` is `true`). If instead `details.lifecycle.codeAlreadyRemoved` is `true`, the flag is launched everywhere and its code references are gone: recommend archiving it.
- Recommend proceeding with code removal using the [flag cleanup skill](../launchdarkly-flag-cleanup/SKILL.md)
- Suggest archival in LaunchDarkly after code changes are deployed

### Caution
No hard blockers, but warnings exist. `caution` is not permission to remove code.
- Present each warning with context, and ask the user to confirm before you recommend code removal
- For `code_removal_readiness_unavailable`: the tool could not get LaunchDarkly's code removal verdict. Ask the user to confirm in LaunchDarkly that the flag is launched in every critical environment
- Recommend **archive** (reversible) over **delete** (permanent)
- Suggest addressing warnings first (e.g., remove code references, then re-check)

### Blocked
Hard blockers prevent safe removal. Do not recommend code removal.
- Present each blocker with specifics
- For `not_ready_for_code_removal`: LaunchDarkly does not consider the flag ready for code removal. Name the critical environments where the flag is not `launched` (from the blocker detail or `details.lifecycle.environments`)
- If `details.lifecycle.readyToArchive` is `true`: the flag is inactive everywhere and has no code references. Recommend archiving the flag in LaunchDarkly, not code removal
- For prerequisite dependencies: user must update dependent flags first
- For active targeting: the user should finish the rollout (targeting ON, one variation served to everyone) and wait 7 days without changes. Do not tell the user to turn the flag off: a flag that is off everywhere is not ready for code removal
- For active status: flag is still being used: don't remove

## Presenting Results

Structure the assessment as:

1. **Verdict**: Lead with safe / caution / blocked
2. **Blockers** (if any): Each with type and actionable detail
3. **Warnings** (if any): Each with type and context
4. **Forward value**: What variation should replace the flag in code (only if safe, or caution after the user confirms)
5. **Next steps**: What to do now (proceed with cleanup, address warnings, resolve blockers)
