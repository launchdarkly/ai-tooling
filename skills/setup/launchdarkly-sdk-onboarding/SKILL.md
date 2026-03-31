---
name: launchdarkly-sdk-onboarding
description: "Onboard a project to LaunchDarkly by detecting the tech stack, installing the right SDK, initializing it, validating the connection, and creating a first feature flag. Use when the user wants to add LaunchDarkly or feature flags to their project, integrate an SDK, or says 'onboard me'."
license: Apache-2.0
compatibility: Requires LaunchDarkly API access token or SDK key. MCP server optional; without MCP, use ldcli and direct API calls (see Prerequisites).
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# LaunchDarkly SDK Onboarding

You're using a skill that will guide you through adding LaunchDarkly to a project. Your job is to detect the tech stack, choose the right SDK, install and initialize it, validate the connection, and help the user create their first feature flag.

## Prerequisites

MCP tools are **optional** for this skill—the workflow falls back to **ldcli** (the LaunchDarkly CLI) and **direct LaunchDarkly API** calls (`GET /api/v2/projects/{projectKey}`, environment endpoints, etc.) when MCP is unavailable.

**Optional MCP tools (enhance onboarding when configured):**

- `get-environments` — list environments for a project; use the response (and related project/environment APIs as needed) to obtain SDK keys, client-side IDs, or mobile keys without manual copy-paste when the tool exposes them.
- `create-feature-flag` — create the boolean flag for [Step 5: Create Your First Feature Flag](#step-5-create-your-first-feature-flag). (Some setups or docs may label this capability `create-flag`; use the tool name your MCP server lists.)

**Other MCP tools you may use if present** (not required): `list-feature-flags`, `get-feature-flag`, `get-flag-status-across-environments`—for confirmation and validation alongside the API or dashboard.

Before starting, confirm the user can authenticate to LaunchDarkly (access token for API/MCP, or SDK keys they paste manually).

## Account and Credentials

Before starting the SDK integration, ensure the user has access to LaunchDarkly:

1. **Check for existing credentials**: Ask the user if they have a LaunchDarkly access token or SDK key.
2. **If the user has an account**: Use the LaunchDarkly API (`GET /api/v2/projects/PROJECT_KEY`) or **ldcli** (the LaunchDarkly CLI) to retrieve the project, environment, and SDK key automatically. Ask the user for permission before reading the SDK key.
3. **If the user does NOT have an account**: Prompt them to sign up at https://launchdarkly.com or log in via `ldcli login`. Guide them through creating their first project and environment if needed.
4. **SDK key types**: The project response will contain the keys you need. Use the correct key type for the SDK:
   - **SDK Key** for server-side SDKs
   - **Client-side ID** for client-side/browser SDKs
   - **Mobile Key** for mobile SDKs

## Core Principles

1. **Detect, don't guess**: Always inspect the repo to determine the language, framework, and package manager. Never assume.
2. **Minimal changes**: Add SDK code alongside existing code. Don't restructure or refactor the user's project.
3. **Match existing patterns**: If the project already has conventions (env vars, config files, initialization patterns), follow them.
4. **Validate end-to-end**: Don't stop at installation. Confirm the SDK is actually connected to LaunchDarkly.

## Workflow

Follow and enumerate **Steps 1-5** in order for the SDK integration and first flag. If any step fails, go to [Step 6: Recover](#step-6-recover).

MCP setup, `LAUNCHDARKLY.md`, and editor rules are **not** listed below as steps—they are covered in [Default follow-through](#default-follow-through-not-numbered-steps).

### Step 1: Detect Repository Stack

Before doing anything, understand the project.

1. Inspect the repo for language, framework, and package manager
2. Check for existing LaunchDarkly SDK usage
3. Identify the application entrypoint

See [Detect Repository Stack](references/1.0-detect.md) for detailed instructions.

### Step 2: Generate Integration Plan

Based on what you found, choose the correct SDK and plan the integration.

1. Match the detected stack to an SDK using the [SDK Recipes](references/sdk-recipes.md) (read **Top 10 SDKs (start here)** first when applicable)
2. Identify which files need to change
3. Determine if this is a server-side, client-side, or mobile integration

See [Generate Integration Plan](references/1.1-plan.md) for detailed instructions.

### Step 3: Install, Apply Code, and Run

Install the SDK, add initialization code, and confirm the app still starts.

1. Install the SDK package using the project's package manager
2. Add SDK initialization code to the application entrypoint
3. Configure the SDK key via environment variables
4. Start the application (you run it when possible, otherwise give the user the exact command) and **do not** continue to validation until startup is confirmed—explicit user confirmation when they run it locally; see [Start the Application](references/1.3-run.md) Step 4

See [Apply Code Changes](references/1.2-apply.md) and [Start the Application](references/1.3-run.md) for detailed instructions.

### Step 4: Validate SDK Connection

Confirm that LaunchDarkly sees the SDK connection.

1. **Prefer `ldcli sdk-active` or the REST equivalent** (see the reference). That check does **not** require a feature flag to exist yet—Step 5 comes next on purpose.
2. **Dashboard-only** validation is weak until a flag exists and is evaluated; the reference describes when to use a short **exception path** (create/evaluate a flag early) if API/CLI access is impossible.

See [Validate SDK Connection](references/1.4-validate.md) for detailed instructions.

### Step 5: Create Your First Feature Flag

Help the user create and evaluate a feature flag.

1. Create a boolean feature flag
2. Add flag evaluation code to the project
3. Toggle the flag and observe the change

See [Create First Feature Flag](references/1.5-first-flag.md) for detailed instructions.

### Step 6: Recover

If any step fails, diagnose the issue and resume.

1. Identify the failed step and error
2. Choose a recovery action
3. Resume the workflow

See [Recovery Procedures](references/1.6-recover.md) for detailed instructions.

## Default follow-through (not numbered steps)

Do these as part of finishing onboarding—same session when possible. They are **not** extra phases in the numbered workflow above; skip or defer only if the user declines or time runs out.

**LaunchDarkly MCP**

- Use MCP tools whenever they are available (see [Prerequisites](#prerequisites)); prefer them for environments and flag creation when configured.
- If the MCP server is not configured, briefly offer optional setup; do **not** block completion of Steps 1–5 on it. See [MCP Server Setup](references/1.7-mcp-setup.md).

**Setup summary (`LAUNCHDARKLY.md`)**

- Generate the repo summary per [Onboarding Summary](references/1.8-summary.md). Ask permission before writing or committing.

**Editor rules / skills**

- Add editor-specific rules or skill hooks per [Editor Rules and Skills](references/1.9-editor-rules.md) so later agent sessions follow LaunchDarkly practices. Ask permission before writing or committing.

## Edge Cases

| Situation | Action |
|-----------|--------|
| SDK already installed | Skip to Step 3 (run sub-step) or Step 4 (Validate) |
| Multiple languages in repo | Ask the user which target to integrate first (frontend vs backend vs mobile) |
| Monorepo | Identify the specific package/service to integrate and work within that subtree |
| No package manager detected | Ask the user which SDK they want to install and provide manual install instructions |
| Application won't start | Use the recover step to diagnose; don't block on run if the user confirms the app runs separately |

## What NOT to Do

- Don't install an SDK without detecting the stack first
- Don't hardcode SDK keys in source code — always use environment variables
- Don't restructure the user's project or refactor existing code
- Don't skip validation — always confirm the SDK is connected
- Don't create flags before the SDK connection is validated

## References

**Core workflow (Steps 1-5, Step 6 recover)**

- [Detect Repository Stack](references/1.0-detect.md) — How to identify language, framework, and existing SDK usage
- [Generate Integration Plan](references/1.1-plan.md) — How to choose the right SDK and plan changes
- [Apply Code Changes](references/1.2-apply.md) — How to install dependencies and add initialization code
- [Start the Application](references/1.3-run.md) — How to run the app, when the user runs it instead, and **confirm** it is up before validation (no duplicate `sdk-active` here)
- [Validate SDK Connection](references/1.4-validate.md) — How to verify LaunchDarkly sees the SDK
- [Create First Feature Flag](references/1.5-first-flag.md) — How to create, evaluate, and toggle a flag
- [Recovery Procedures](references/1.6-recover.md) — How to diagnose failures and resume

**Default follow-through**

- [MCP Server Setup](references/1.7-mcp-setup.md) — Optional MCP installation when tools are missing
- [Onboarding Summary](references/1.8-summary.md) — Template for `LAUNCHDARKLY.md`
- [Editor Rules and Skills](references/1.9-editor-rules.md) — Editor rules for ongoing flag management

**SDK index**

- [SDK Recipes](references/sdk-recipes.md) — Detection patterns, install commands, and doc links for all SDKs
- [SDK detail files](references/sdk-snippets/) — Per-SDK pointers (docs, samples, registries); ten files also include copy-paste onboarding samples (linked from each recipe in SDK Recipes)
