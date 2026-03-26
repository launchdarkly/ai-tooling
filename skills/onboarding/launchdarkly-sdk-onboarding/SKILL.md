---
name: launchdarkly-sdk-onboarding
description: "Onboard a project to LaunchDarkly by detecting the tech stack, installing the right SDK, initializing it, validating the connection, and creating a first feature flag. Use when the user wants to add LaunchDarkly to their project, integrate an SDK, or says 'onboard me'."
license: Apache-2.0
compatibility: Requires LaunchDarkly API access token. Optionally uses the LaunchDarkly MCP server for flag creation and validation.
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# LaunchDarkly SDK Onboarding

You're using a skill that will guide you through adding LaunchDarkly to a project. Your job is to detect the tech stack, choose the right SDK, install and initialize it, validate the connection, and help the user create their first feature flag.

## Prerequisites

- A LaunchDarkly account with an API access token (or SDK key)
- A project and environment configured in LaunchDarkly
- Access to the user's codebase (read and write)

## Core Principles

1. **Detect, don't guess**: Always inspect the repo to determine the language, framework, and package manager. Never assume.
2. **Minimal changes**: Add SDK code alongside existing code. Don't restructure or refactor the user's project.
3. **Match existing patterns**: If the project already has conventions (env vars, config files, initialization patterns), follow them.
4. **Validate end-to-end**: Don't stop at installation. Confirm the SDK is actually connected to LaunchDarkly.

## Workflow

Follow these steps in order. If any step fails, go to [Step 7: Recover](#step-7-recover).

### Step 1: Detect Repository Stack

Before doing anything, understand the project.

1. Inspect the repo for language, framework, and package manager
2. Check for existing LaunchDarkly SDK usage
3. Identify the application entrypoint

See [Detect Repository Stack](references/1.0-detect.md) for detailed instructions.

### Step 2: Generate Integration Plan

Based on what you found, choose the correct SDK and plan the integration.

1. Match the detected stack to an SDK using the [SDK Recipes](references/sdk-recipes.md)
2. Identify which files need to change
3. Determine if this is a server-side, client-side, or mobile integration

See [Generate Integration Plan](references/1.1-plan.md) for detailed instructions.

### Step 3: Install Dependencies and Apply Code

Install the SDK and add initialization code to the project.

1. Install the SDK package using the project's package manager
2. Add SDK initialization code to the application entrypoint
3. Configure the SDK key via environment variables

See [Apply Code Changes](references/1.2-apply.md) for detailed instructions.

### Step 4: Start the Application

Verify the application runs with the SDK integrated.

1. Start the application using its standard run command
2. Confirm there are no import or initialization errors
3. Look for SDK initialization success in logs

See [Start the Application](references/1.3-run.md) for detailed instructions.

### Step 5: Validate SDK Connection

Confirm that LaunchDarkly sees the SDK connection.

1. Check the SDK is active using the LaunchDarkly API or MCP
2. Verify the connection in the LaunchDarkly dashboard

See [Validate SDK Connection](references/1.4-validate.md) for detailed instructions.

### Step 6: Create Your First Feature Flag

Help the user create and evaluate a feature flag.

1. Create a boolean feature flag
2. Add flag evaluation code to the project
3. Toggle the flag and observe the change

See [Create First Feature Flag](references/1.5-first-flag.md) for detailed instructions.

### Step 7: Recover

If any step fails, diagnose the issue and resume.

1. Identify the failed step and error
2. Choose a recovery action
3. Resume the workflow

See [Recovery Procedures](references/1.6-recover.md) for detailed instructions.

## Edge Cases

| Situation | Action |
|-----------|--------|
| SDK already installed | Skip to Step 4 (Run) or Step 5 (Validate) |
| Multiple languages in repo | Ask the user which target to integrate first (frontend vs backend vs mobile) |
| Monorepo | Identify the specific package/service to integrate and work within that subtree |
| No package manager detected | Provide manual install instructions from the SDK recipe |
| Application won't start | Use the recover step to diagnose; don't block on run if the user confirms the app runs separately |

## What NOT to Do

- Don't install an SDK without detecting the stack first
- Don't hardcode SDK keys in source code — always use environment variables
- Don't restructure the user's project or refactor existing code
- Don't skip validation — always confirm the SDK is connected
- Don't create flags before the SDK connection is validated

## References

- [Detect Repository Stack](references/1.0-detect.md) — How to identify language, framework, and existing SDK usage
- [Generate Integration Plan](references/1.1-plan.md) — How to choose the right SDK and plan changes
- [Apply Code Changes](references/1.2-apply.md) — How to install dependencies and add initialization code
- [Start the Application](references/1.3-run.md) — How to run the app and confirm SDK initialization
- [Validate SDK Connection](references/1.4-validate.md) — How to verify LaunchDarkly sees the SDK
- [Create First Feature Flag](references/1.5-first-flag.md) — How to create, evaluate, and toggle a flag
- [Recovery Procedures](references/1.6-recover.md) — How to diagnose failures and resume
- [SDK Recipes](references/sdk-recipes.md) — Detection patterns, install commands, and init snippets for all SDKs
