---
title: Editor Rules and Skills
description: Leave behind editor-specific rules that point agents at LaunchDarkly agent skills (not doc URLs) for ongoing feature flag work
---

# Editor Rules and Skills

After onboarding, do two things:

1. **Ensure the user has the relevant LaunchDarkly agent skills installed** — The goal is not “a plugin” in the abstract: the user (or agent) should have the **same skills this repository ships**, so future sessions can load them by `name`. **Standard set (install all four):**
   - `launchdarkly-flag-create`
   - `launchdarkly-flag-discovery`
   - `launchdarkly-flag-targeting`
   - `launchdarkly-flag-cleanup`  
   **Optional:** `onboarding` (for more SDK onboarding later).  
   **Preferred:** Install the **LaunchDarkly** plugin **`launchdarkly@launchdarkly-ai-tooling`** from **[github.com/launchdarkly/ai-tooling](https://github.com/launchdarkly/ai-tooling)**, which packages these skills—then confirm in the UI or CLI that those skill names are available.
   - **Claude Code:** After any required marketplace setup for that repo (see the repository README or `claude plugin` / Anthropic docs for your CLI version), install with:
     ```bash
     claude plugin install launchdarkly@launchdarkly-ai-tooling
     ```
     If the command name or flags differ in your build, use `claude plugin --help` and match the plugin coordinate above. **Verify** the four standard skills (above) show up as usable after install.
   - **Cursor:** Install or enable skills from the same distribution per current Cursor docs (marketplace / plugin UI pointing at this repo or copied folders). **Verify** the four `launchdarkly-flag-*` skills are listed or discoverable.
   - **Fallback (no plugin):** Copy skill directories from [github.com/launchdarkly/ai-tooling](https://github.com/launchdarkly/ai-tooling) (or this monorepo’s published plugin) into the user’s skills location so each folder contains a `SKILL.md` for `launchdarkly-flag-create`, `launchdarkly-flag-discovery`, `launchdarkly-flag-targeting`, and `launchdarkly-flag-cleanup`. Optional: include **`onboarding`** from this repo’s onboarding path. List any copied paths in the rules file so agents know where to read `SKILL.md`.
2. **Write an editor rule** — The rule must tell *future* agents to **read and follow** those skills for flag work. Do **not** bake in SDK documentation URLs; procedures and compatibility live in each skill’s `SKILL.md`. Deep links to SDK docs belong in `LAUNCHDARKLY.md` if you already created that summary.

## Default skill set (feature flags)

Unless the user opts out, treat **all** of these as the standard kit and mention each one in the generated rule. They are published in [github.com/launchdarkly/ai-tooling](https://github.com/launchdarkly/ai-tooling) (same four skills as in step 1 above):

| Skill `name` (frontmatter) | Purpose |
|----------------------------|---------|
| `launchdarkly-flag-create` | Create and configure flags and wire evaluation to match the codebase (MCP when required). |
| `launchdarkly-flag-discovery` | Audit flag inventory, stale or launched flags, and removal readiness. |
| `launchdarkly-flag-targeting` | Toggle flags, percentage rollouts, targeting rules, and promote config between environments. |
| `launchdarkly-flag-cleanup` | Safely remove flags from code, readiness checks, and MCP-driven cleanup workflows. |


Adjust the table only if the user explicitly wants a smaller set.

## Step 1: Detect the Editor

Check for editor configuration files in the project root:

| File/Directory | Editor |
|----------------|--------|
| `.cursor/` or `.cursorrules` | Cursor |
| `.claude/` | Claude Code (Anthropic) |
| `.github/copilot-instructions.md` | GitHub Copilot |
| `.vscode/` (without Cursor indicators) | VS Code |
| `.idea/` | JetBrains IDE — use [For JetBrains](#for-jetbrains-intellij-webstorm-rider-etc) (no dedicated template file path here) |

If you can't detect the editor, default to Claude Code and create `.claude/rules/launchdarkly.md`.

## Step 2: Create the Rules File

Base the file on the templates below. **Substitute project facts** (`{SDK_NAME}`, `{ENTRYPOINT_FILE}`, `{ENV_VAR_NAME}`) from onboarding. **Do not** add `{SDK_DOCS_URL}` or a documentation links section to this file—that is intentionally omitted so agents rely on skills + MCP.

The rule text must explicitly say: *when doing flag create, targeting, discovery, cleanup, or code removal, load the matching LaunchDarkly skill and execute its workflow* (not just “see links”).

### Shared body (use in Cursor and Claude Code)

Use this markdown block inside each template (Cursor: below the YAML frontmatter; Claude Code: from the first `#` heading).

```markdown
# LaunchDarkly Feature Flags

This project uses LaunchDarkly for feature flag management.

## SDK context (this repo)
- SDK: {SDK_NAME}
- Initialization: {ENTRYPOINT_FILE}
- Key env var: {ENV_VAR_NAME} (never hardcode secrets in source)

## Agent: use LaunchDarkly skills (required)

Ensure the **LaunchDarkly** agent skills below are installed (`launchdarkly@launchdarkly-ai-tooling` plugin from [github.com/launchdarkly/ai-tooling](https://github.com/launchdarkly/ai-tooling), or equivalent copies on disk). For any substantive flag work, **open that skill’s `SKILL.md` and follow it**—do not improvise from generic flag advice alone.

| Skill | When to use it |
|-------|------------------|
| `launchdarkly-flag-create` | User wants a new flag, code wiring, feature toggle, or experiment setup. |
| `launchdarkly-flag-discovery` | User wants flag inventory, debt/stale-flag audit, health, or removal readiness. |
| `launchdarkly-flag-targeting` | User wants who sees a flag, rollouts, targeting rules, or environment promotion. |
| `launchdarkly-flag-cleanup` | User wants a flag removed from code safely, archive/cleanup workflows, or MCP-driven removal. |

**Invocation:** Match the user’s request to the skill `description` in each skill’s frontmatter, or use the editor’s slash / plugin command for that skill if configured.

**Tools:** When a skill lists LaunchDarkly MCP tools as required, use MCP; do not skip validation steps.

## Conventions (summary)
- Prefer boolean flags unless multivariate is required; use descriptive kebab-case keys (e.g. `enable-checkout-v2`).
- Always pass a fallback when evaluating flags; use a meaningful evaluation context (user key, org, etc.).
- Server-side SDK keys stay secret; client-side IDs may appear in browser code.
- Do not evaluate flags in tight loops without caching.
- Archive or remove flag code when a flag is fully rolled out and the team agrees—use `launchdarkly-flag-cleanup` (and `launchdarkly-flag-discovery` first if assessing candidates).
```

### For Cursor (`.cursor/rules/launchdarkly.mdc`)

Create `.cursor/rules/launchdarkly.mdc`:

```markdown
---
description: LaunchDarkly feature flags — require LaunchDarkly agent skills for flag workflows
globs: []
alwaysApply: false
---

{PASTE_SHARED_BODY_HERE}
```

Replace `{PASTE_SHARED_BODY_HERE}` with the [shared body](#shared-body-use-in-cursor-and-claude-code) (no literal placeholder left in the file).

### For Claude Code (`.claude/rules/launchdarkly.md`)

Create `.claude/rules/launchdarkly.md` containing **only** the [shared body](#shared-body-use-in-cursor-and-claude-code) (no YAML frontmatter).

### For GitHub Copilot (`.github/copilot-instructions.md`)

Append to `.github/copilot-instructions.md` (create if it doesn't exist). Copilot may not load external skills the same way; still steer toward the same workflows and name the skills:

```markdown
## LaunchDarkly Feature Flags

This project uses LaunchDarkly ({SDK_NAME}) for feature flag management.
Initialization: {ENTRYPOINT_FILE}. SDK key / client ID: environment variable `{ENV_VAR_NAME}` only—never commit secrets.

For flag work, follow the LaunchDarkly agent skills when available: **`launchdarkly-flag-create`** (create + code), **`launchdarkly-flag-discovery`** (audit / inventory), **`launchdarkly-flag-targeting`** (rollouts / targeting / env promotion), **`launchdarkly-flag-cleanup`** (code removal / cleanup / MCP workflows). Read each skill’s instructions instead of guessing flag lifecycle steps.
```

### For JetBrains (IntelliJ, WebStorm, Rider, etc.)

There is **no** JetBrains-specific rules template in this reference (`.idea/` only indicates the IDE family). **Do not silently skip:** tell the user you detected JetBrains and that they should rely on **`LAUNCHDARKLY.md`** ([Onboarding Summary](1.8-summary.md)) plus installing **`launchdarkly@launchdarkly-ai-tooling`** (same as Claude Code) or copying skill folders manually.

Reasonable options to suggest:

- Keep flag workflow guidance in **`LAUNCHDARKLY.md`** and team docs the IDE already opens.
- If the team also uses GitHub Copilot in the same repo, reuse the **For GitHub Copilot** template above in `.github/copilot-instructions.md` so any tool that reads that file picks up the same guidance.
- If their JetBrains AI plugin supports a **project-level instruction file**, paste the [shared body](#shared-body-use-in-cursor-and-claude-code) there (adapt paths to your product’s docs)—this doc does not name a single standard path for all JetBrains products.

### For other editors (not Cursor, Claude Code, Copilot, VS Code, or JetBrains)

If the editor doesn't have a rules system, skip creating a rules file. Rely on `LAUNCHDARKLY.md` and tell the user which LaunchDarkly skills to install (`launchdarkly@launchdarkly-ai-tooling` or copied skill folders from [github.com/launchdarkly/ai-tooling](https://github.com/launchdarkly/ai-tooling)).

## Step 3: Fill in the Placeholders

From the onboarding session, set:

- `{SDK_NAME}` — e.g. `Node.js Server SDK`
- `{ENTRYPOINT_FILE}` — e.g. `src/index.ts`
- `{ENV_VAR_NAME}` — e.g. `LAUNCHDARKLY_SDK_KEY`

**Do not** add documentation URLs to this rules file. If you need SDK doc links for humans, put them only in `LAUNCHDARKLY.md` ([Onboarding Summary](1.8-summary.md)).

If you added or removed skills from the default table (user request), update the skill table in the shared body to match.

## Step 4: Commit the Rules

```bash
# Claude Code (most common for this skill)
git add .claude/rules/launchdarkly.md

# Cursor
git add .cursor/rules/launchdarkly.mdc

# GitHub Copilot / shared instructions
git add .github/copilot-instructions.md

# Add only the file(s) you created or changed, then:
git commit -m "chore: add LaunchDarkly feature flag management rules"
```

Ask the user for permission before committing.
