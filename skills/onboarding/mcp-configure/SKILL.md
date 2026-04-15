---
name: mcp-configure
description: "Configure the LaunchDarkly hosted MCP server during onboarding. Use when the parent LaunchDarkly onboarding skill reaches Step 4 (MCP). Supports Cursor, Claude Code, Windsurf, GitHub Copilot, and other MCP-compatible agents. OAuth authentication; no API keys for the hosted server."
license: Apache-2.0
compatibility: Requires an MCP-compatible coding agent and a LaunchDarkly account
metadata:
  author: launchdarkly
  version: "0.1.0"
---

# LaunchDarkly MCP Server Configuration (onboarding)

Configures the LaunchDarkly hosted MCP server so flag management skills and onboarding can use MCP tools. Uses OAuth for authentication — no API keys needed for the hosted server.

This skill is nested under [LaunchDarkly onboarding](../SKILL.md); the parent skill's **Step 4** hands off here. **Hosted MCP** is the default. For **federal/EU** or other cases where hosted is unavailable, use the **Local server via `npx`** section in [MCP Config Templates](references/mcp-config-templates.md) and [local MCP server docs](https://launchdarkly.com/docs/home/getting-started/mcp-local).

## Prerequisites

- A LaunchDarkly account (sign up at [https://app.launchdarkly.com/signup?source=agent](https://app.launchdarkly.com/signup?source=agent))
- An MCP-compatible coding agent

## Hosted MCP Servers

LaunchDarkly provides two hosted MCP servers. For onboarding, only the feature management server is required.

| Server             | URL                                          | Purpose              |
| ------------------ | -------------------------------------------- | -------------------- |
| Feature management | `https://mcp.launchdarkly.com/mcp/fm`        | Manage feature flags |
| AI Configs         | `https://mcp.launchdarkly.com/mcp/aiconfigs` | Manage AI Configs    |

## Workflow

### Step 1: Detect the Agent

If the parent onboarding skill already identified the agent, use that context. Otherwise infer from agent-specific directories, config files, and the tools available to you at runtime. Do not ask the user — pick the strongest match.

### Step 2: Try Quick Install

The fastest path is the quick install link. Present it to the user:

**Feature management:** [https://mcp.launchdarkly.com/mcp/fm/install](https://mcp.launchdarkly.com/mcp/fm/install)

**AI Configs (optional):** [https://mcp.launchdarkly.com/mcp/aiconfigs/install](https://mcp.launchdarkly.com/mcp/aiconfigs/install)

**Important: tell the user what to expect after clicking the link.** The install link may open in the browser, but the authorization or "add server" prompt typically appears **back in the coding environment** (the editor or host app where the agent runs), not in the browser. Immediately after presenting the link, include guidance like:

- After clicking the link, watch your coding environment (the editor where this conversation is running) for an approval dialog, an "add MCP server" prompt, or a tools/integrations panel notification.
- The browser may start the OAuth flow, but you'll likely need to confirm or approve the server in the editor itself.
- **If no prompt appears:** check the editor's MCP, integrations, or tools settings area to see if the server was added but needs to be enabled. If it's not there at all, fall back to manual setup (Step 3 below).

If the quick install link doesn't work (agent doesn't support it, or user prefers manual setup), proceed to Step 3.

### Step 3: Manual Configuration

Locate the MCP config file for the detected agent and add the hosted server entry. See [MCP Config Templates](references/mcp-config-templates.md) for the exact JSON per agent.

| Agent          | Config file location                                       |
| -------------- | ---------------------------------------------------------- |
| Cursor         | `.cursor/mcp.json` (project) or global Cursor settings     |
| Claude Code    | `.mcp.json` (project) or `~/.claude.json` (global)         |
| GitHub Copilot | Repo **Settings** on GitHub.com → Copilot → Cloud agent → MCP (see [MCP UI links](references/mcp-ui-links.md)) |
| Windsurf       | Agent-specific MCP config                                  |

**Only add the feature management server for onboarding.** Add the AI Configs server only if the user explicitly needs it.

### Step 4: Agent-Specific Authorization

After writing the config, some agents need extra steps. **Do not** send users through long manual menu paths only—use [MCP UI links](references/mcp-ui-links.md) (HTTPS docs + `command:` shortcuts for VS Code / Cursor).

**Cursor:**

1. Open MCP in Cursor using the [Cursor MCP doc link and in-app shortcuts](references/mcp-ui-links.md#clients) (e.g. Settings search via `command:` link when clickable).
2. Toggle on **LaunchDarkly feature management** (or the name from your config).
3. Click **Connect** to authorize with the LaunchDarkly account.

**VS Code (when applicable):**

- Use [VS Code MCP doc + `mcp.json` / Settings links](references/mcp-ui-links.md#clients); trust or start the server if prompted.

**Claude Code:**

- Authorization happens automatically on first MCP tool call via OAuth prompt. File-based setup: [Claude Code MCP doc](https://docs.claude.com/en/docs/claude-code/mcp).

**GitHub Copilot:**

- Click **Save** after adding the MCP configuration in repo settings. Use the [GitHub Copilot MCP doc](https://docs.github.com/en/copilot/customizing-copilot/extending-copilot-coding-agent-with-mcp) for the exact **Settings** path on github.com.

### Step 5: Restart and Auto-Verify

MCP tools are only available to the agent after a restart or refresh — newly added MCP servers do not appear mid-session.

1. **Tell the user to enable the server and restart.** Before restarting, they need to make sure the MCP server is toggled on and authorized in their editor's MCP settings (e.g. in Cursor: toggle on the LaunchDarkly server and click **Connect**). Then restart or refresh the agent — be specific about how: "Restart Cursor" / "reload Claude Code" / "refresh the Copilot agent" depending on what you detected in Step 1. After the user restarts, the conversation will resume in a new turn.
2. **On the next turn, probe silently.** Call a lightweight MCP tool (e.g. `list-feature-flags` with the user's project key). Do not ask the user whether MCP is working — just try it.
   - **Success** (normal response, even an empty flag list): MCP is live. Note it in the onboarding log and continue.
   - **Failure** (tool not found, auth error, timeout): fall back to ldcli/API. Note the fallback in the onboarding log. Do **not** block the rest of onboarding — Steps 5-6 must still be completable without MCP.
3. **If the probe fails**, briefly tell the user MCP isn't available yet and that you'll use ldcli/API instead. Offer a one-liner they can try later to re-enable MCP (e.g. "You can set up MCP anytime by clicking [quick install link] and restarting").
4. If the failure looks like a config issue (wrong file path, missing OAuth, server not enabled), mention the likely cause so the user can fix it on their own time — but do not block progress.

For **local `npx` server** verification, see [MCP Config Templates — Verify (local server)](references/mcp-config-templates.md#verify-local-server).

## Local MCP: Access Token Setup

When the user needs the **local `npx` server** (federal/EU or other cases where hosted MCP is unavailable), the server requires a `LAUNCHDARKLY_ACCESS_TOKEN`. This is a sensitive credential.

First, tell the user how to create a token if they don't already have one:

> Create an API access token at [app.launchdarkly.com/settings/authorization/tokens/new](https://app.launchdarkly.com/settings/authorization/tokens/new). Give it a descriptive name (e.g. "MCP server") and at minimum the **Reader** role. Copy the token — you won't be able to see it again after leaving the page.

Then ask how they want to add the token to the MCP config:

**D4-LOCAL -- BLOCKING:** Call your structured question tool now.
- question: "The local MCP server needs an API access token to authenticate with LaunchDarkly. You can create one at app.launchdarkly.com/settings/authorization/tokens/new. Once you have the token, how would you like to add it to your MCP config? We recommend adding it yourself — there is a non-zero risk when an AI agent handles secrets, as tokens may persist in conversation history, logs, or model context."
- options:
  - "I'll add the token to the config myself — just tell me which file and variable"
  - "I have the token ready — go ahead and help me wire up the config"
- STOP. Do not write the question as text. Do not write any token value to a config file before the user selects an option.

**If the user adds the token themselves:**
1. Tell them the config file path for their agent (see [MCP Config Templates](references/mcp-config-templates.md))
2. Tell them to set `LAUNCHDARKLY_ACCESS_TOKEN` as the value — either as an environment variable or directly in the config file
3. Remind them to add the config file to `.gitignore` if the token is inline
4. Wait for them to confirm, then proceed to Step 5 (Restart and Auto-Verify)

**If the user wants agent-assisted setup:**
1. Ensure the config file is in `.gitignore` before writing
2. Write the config per [MCP Config Templates](references/mcp-config-templates.md)
3. Remind the user that the token will be visible in the config file and conversation history
4. Proceed to Step 5 (Restart and Auto-Verify)

## Edge Cases

- **User already has MCP configured:** Verify by checking for existing LD MCP entries in the config. If present and working, skip configuration.
- **User has the old npx-based local server:** Migrate them. Remove the old `npx @launchdarkly/mcp-server` entry and any `LD_ACCESS_TOKEN` env vars. Replace with the hosted server config.
- **Federal or EU instances:** The hosted MCP server is not available for federal or EU environments. Use [local MCP server docs](https://launchdarkly.com/docs/home/getting-started/mcp-local) and the **Local server via `npx`** section in [MCP Config Templates](references/mcp-config-templates.md). Follow the [Local MCP: Access Token Setup](#local-mcp-access-token-setup) flow for token handling.
- **Agent not in known list:** Provide the generic pattern: the user needs to add an MCP server entry pointing to `https://mcp.launchdarkly.com/mcp/fm` using whatever format their agent expects.
- **User opts out of MCP during onboarding:** Document that choice and continue with the parent skill's ldcli/API fallbacks for environments and flags; do not block SDK work.

## What NOT to Do

- Don't configure the old npx-based local server by default. Prefer the hosted server for standard regions.
- Don't ask for or store API keys for the hosted server. The hosted server uses OAuth.
- Don't add both servers by default. Only add AI Configs if the user asks for it.
- Don't handle the access token for local MCP without asking the user first via the D4-LOCAL decision point.

## References

- [MCP UI links](references/mcp-ui-links.md) — HTTPS + `command:` links to open MCP settings (Cursor, VS Code, Claude Code, Windsurf, GitHub)
- [MCP Config Templates](references/mcp-config-templates.md) — hosted OAuth JSON per agent; **Local server via `npx`** fallback; migration from old local server
- [Official MCP docs](https://launchdarkly.com/docs/home/getting-started/mcp-hosted) — full hosted setup guide
