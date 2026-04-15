---
name: sdk-install
description: "Install and initialize the correct LaunchDarkly SDK during onboarding by running nested skills in order: detect, plan, apply. Parent onboarding Step 6 is first flag."
license: Apache-2.0
compatibility: Requires a supported language/framework in the project. SDK credentials are required by [Apply](apply/SKILL.md), not for [Detect](detect/SKILL.md) / [Plan](plan/SKILL.md) alone (see parent onboarding **Prerequisites**).
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# LaunchDarkly SDK Install (onboarding)

Installs and initializes the right LaunchDarkly SDK for the user’s project by following **three nested skills in order**. **Do not** skip ahead to feature flags here—the parent [LaunchDarkly onboarding](../SKILL.md) continues with **Step 6: First feature flag** using [Create first feature flag](../first-flag/SKILL.md).

## Prerequisites

- Project context from parent **Step 1: Explore the Project** (reuse it; only re-run deep detection if something is unclear)
- **SDK key / client-side ID / mobile key:** Needed when you reach [Apply code changes](apply/SKILL.md) (env wiring). **Do not** ask the user for these during detect or plan solely because you opened this skill—follow parent onboarding: account is confirmed early; key material is collected at apply (see parent [Prerequisites](../SKILL.md#prerequisites)).

## Key types (summary)

| SDK Type    | Variable (logical)        | Source in LaunchDarkly        |
|-------------|---------------------------|-------------------------------|
| Server-side | `LAUNCHDARKLY_SDK_KEY`    | Environments → SDK key        |
| Client-side | Client-side ID (bundler-prefixed env names) | Environments → Client-side ID |
| Mobile      | `LAUNCHDARKLY_MOBILE_KEY` | Environments → Mobile key     |

**Never hardcode keys.** Full env rules, consent, and bundler tables: [Apply code changes](apply/SKILL.md) Step 2.

## Workflow — run these nested skills in order

Execute **all three** unless the [detect decision tree](detect/SKILL.md#decision-tree) short-circuits (e.g. skip to apply only). Each nested skill contains **blocking decision points** (marked `D<N> -- BLOCKING`) where you must call your structured question tool and wait for the user's response before continuing. Do NOT batch tool calls across these boundaries.

| Order | Nested skill | Role |
|-------|----------------|------|
| 1 | [Detect repository stack](detect/SKILL.md) | Language, package manager, monorepo target, entrypoint, existing LD usage |
| 2 | [Generate integration plan](plan/SKILL.md) | SDK choice, files to change, env plan -- confirm with user before edits |
| 3 | [Apply code changes](apply/SKILL.md) | Install package(s), `.env` / secrets with consent, init code, compile check (**both** tracks when [dual-SDK plan](plan/SKILL.md#dual-sdk-integrations)) |

Shared references for all steps: [SDK recipes](../references/sdk/recipes.md), [SDK snippets](../references/sdk/snippets/).

### After Step 3 completes

Continue with the parent skill:

- **Step 6:** [Create first feature flag](../first-flag/SKILL.md)

Do not add standalone “sample flag” evaluation in this skill unless the user explicitly needs a throwaway check; the parent flow creates the first flag in order.

## Guidelines

- Match existing codebase conventions for imports, config, and style.
- Prefer TypeScript in TypeScript projects.
- If the project uses a shared config layer, initialize LaunchDarkly there.
- Add `.env.example` entries when the project uses dotenv.
- **Dependency scope:** Add only LaunchDarkly SDK package(s) from the recipe unless the user **explicitly approves** upgrading or adding other packages ([Apply — Permission before changing other dependencies](apply/SKILL.md#permission-before-changing-other-dependencies)).

## Edge cases

- **Multiple environments (e.g. Next.js server + client) or user asked for frontend + backend:** Use a **dual-SDK** [plan](plan/SKILL.md#dual-sdk-integrations) and [apply](apply/SKILL.md) **both** packages and **both** inits—never summarize the second SDK as done without lockfile + entrypoint evidence.
- **Monorepo:** Integrate the package the user chose in parent onboarding; stay within that subtree.
- **SDK already installed and initialized:** Parent may skip this handoff—see parent **Edge Cases** and [detect decision tree](detect/SKILL.md#decision-tree).
- **Unsupported or uncommon stack:** Use [SDK recipes](../references/sdk/recipes.md) and the [full SDK catalog](https://launchdarkly.com/docs/sdk).

## References

- [Detect repository stack](detect/SKILL.md)
- [Generate integration plan](plan/SKILL.md)
- [Apply code changes](apply/SKILL.md)
- [SDK recipes](../references/sdk/recipes.md)
- [SDK snippets](../references/sdk/snippets/)
- [LaunchDarkly onboarding (parent)](../SKILL.md)
