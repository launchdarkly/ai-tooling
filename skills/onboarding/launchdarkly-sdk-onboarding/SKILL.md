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

## Account and Credentials

Before starting the SDK integration, ensure the user has access to LaunchDarkly:

1. **Check for existing credentials**: Ask the user if they have a LaunchDarkly access token or SDK key.
2. **If the user has an account**: Use the LaunchDarkly API (`GET /api/v2/projects/PROJECT_KEY`) or `ldcli` to retrieve the project, environment, and SDK key automatically. Ask the user for permission before reading the SDK key.
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

Follow these steps in order. If any step fails, go to [Step 8: Recover](#step-8-recover).

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

### Step 7: Offer MCP Server Installation

After the SDK is working and the first flag is toggled, check if the LaunchDarkly MCP server is installed in the user's environment.

1. Check if `@launchdarkly/mcp-server` is configured in the user's MCP settings
2. If not installed, ask the user if they want to set it up
3. If yes, guide them through installation and configuration

The MCP server enables richer agent-driven workflows like flag management, targeting rules, and experimentation — all without leaving the editor.

See [MCP Server Setup](references/1.7-mcp-setup.md) for detailed instructions.

### Step 8: Recover

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
| No package manager detected | Ask the user which SDK they want to install and provide manual install instructions |
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
- [MCP Server Setup](references/1.7-mcp-setup.md) — How to install the LaunchDarkly MCP server
- [SDK Recipes](references/sdk-recipes.md) — Detection patterns, install commands, and init snippets for all SDKs
