# MCP Config Templates

Per-agent JSON snippets for configuring the LaunchDarkly hosted MCP server. All configurations use OAuth -- no API keys required.

Source: https://launchdarkly.com/docs/home/getting-started/mcp-hosted

## Cursor

Config file: `.cursor/mcp.json` in the project root.

### Feature management only

```json
{
  "mcpServers": {
    "LaunchDarkly feature management": {
      "url": "https://mcp.launchdarkly.com/mcp/fm",
      "headers": {}
    }
  }
}
```

### Both servers

```json
{
  "mcpServers": {
    "LaunchDarkly feature management": {
      "url": "https://mcp.launchdarkly.com/mcp/fm",
      "headers": {}
    },
    "LaunchDarkly AI Configs": {
      "url": "https://mcp.launchdarkly.com/mcp/aiconfigs",
      "headers": {}
    }
  }
}
```

**After adding the config:** enable the servers and complete OAuth in Cursor's MCP UI. Use [MCP UI links — Cursor](mcp-ui-links.md#clients) (HTTPS doc + optional `command:` links); do not rely only on nested Settings menu paths.

## Claude Code

Config file: `.mcp.json` in the project root, or `~/.claude.json` for global config.

### Feature management only

```json
{
  "mcpServers": {
    "LaunchDarkly feature management": {
      "type": "http",
      "url": "https://mcp.launchdarkly.com/mcp/fm"
    }
  }
}
```

### Both servers

```json
{
  "mcpServers": {
    "LaunchDarkly feature management": {
      "type": "http",
      "url": "https://mcp.launchdarkly.com/mcp/fm"
    },
    "LaunchDarkly AI Configs": {
      "type": "http",
      "url": "https://mcp.launchdarkly.com/mcp/aiconfigs"
    }
  }
}
```

Authorization happens automatically via OAuth prompt on first MCP tool call.

## GitHub Copilot

Configured via the GitHub web UI, not a local config file.

1. Navigate to the target repository on GitHub
2. Go to **Settings > Code and automation > Copilot > Coding agent**
3. In the **MCP configuration** section, add:

```json
{
  "mcpServers": {
    "LaunchDarkly feature management": {
      "url": "https://mcp.launchdarkly.com/mcp/fm",
      "headers": {}
    }
  }
}
```

4. Click **Save**

## Windsurf

Windsurf uses a similar MCP configuration format. Add to the agent's MCP config:

```json
{
  "mcpServers": {
    "LaunchDarkly feature management": {
      "url": "https://mcp.launchdarkly.com/mcp/fm"
    }
  }
}
```

Consult Windsurf's documentation for the exact config file location.

## Migrating from the Old Local Server

If the user has the old npx-based server configured, replace it:

**Remove this:**

```json
{
  "mcpServers": {
    "LaunchDarkly": {
      "command": "npx",
      "args": [
        "-y", "--package", "@launchdarkly/mcp-server",
        "--", "mcp", "start",
        "--api-key", "api-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      ]
    }
  }
}
```

**Replace with the hosted config for the relevant agent** (see sections above).

Also remove any `LD_ACCESS_TOKEN` or `LAUNCHDARKLY_API_KEY` environment variables that were used for the local server. The hosted server handles authentication via OAuth.

## Local server via `npx`

Use the local MCP server when hosted MCP is not available — for example, **EU or Federal** environments — or when your setup requires it. See [local MCP server docs](https://launchdarkly.com/docs/home/getting-started/mcp-local). This path uses **`LAUNCHDARKLY_ACCESS_TOKEN`** (API access token) instead of OAuth.

### Security: Protect tokens in MCP config files

Most editors (Cursor, VS Code, Claude Desktop) require **literal tokens** in MCP config — they don't expand `${VAR}` syntax. To prevent accidental commits:

1. **Add MCP config files to `.gitignore`:**
   ```
   .cursor/mcp.json
   .vscode/mcp.json
   ```
2. **Or use user-level config** (outside the repo) where the editor supports it

**Exception:** Claude Code supports `${LAUNCHDARKLY_ACCESS_TOKEN}` env var syntax — use it when available.

### Claude Code (project `.mcp.json`)

```json
{
  "mcpServers": {
    "launchdarkly": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@launchdarkly/mcp-server"],
      "env": {
        "LAUNCHDARKLY_ACCESS_TOKEN": "${LAUNCHDARKLY_ACCESS_TOKEN}"
      }
    }
  }
}
```

Set `LAUNCHDARKLY_ACCESS_TOKEN` in the environment or use your agent’s secret mechanism per [Claude Code MCP docs](https://docs.claude.com/en/docs/claude-code/mcp). For user-wide config, merge the same `mcpServers.launchdarkly` entry into `~/.claude/settings.json` if appropriate.

### Cursor (`.cursor/mcp.json`)

**Add `.cursor/mcp.json` to `.gitignore`** — Cursor requires a literal token value.

```json
{
  "mcpServers": {
    "launchdarkly": {
      "command": "npx",
      "args": ["-y", "@launchdarkly/mcp-server"],
      "env": {
        "LAUNCHDARKLY_ACCESS_TOKEN": "YOUR_ACCESS_TOKEN"
      }
    }
  }
}
```

### Claude Desktop (`claude_desktop_config.json`)

Claude Desktop config is user-level (not in repos), so token exposure risk is lower.

```json
{
  "mcpServers": {
    "launchdarkly": {
      "command": "npx",
      "args": ["-y", "@launchdarkly/mcp-server"],
      "env": {
        "LAUNCHDARKLY_ACCESS_TOKEN": "YOUR_ACCESS_TOKEN"
      }
    }
  }
}
```

### VS Code / Copilot (`.vscode/mcp.json`)

**Add `.vscode/mcp.json` to `.gitignore`** — VS Code requires a literal token value.

```json
{
  "servers": {
    "launchdarkly": {
      "command": "npx",
      "args": ["-y", "@launchdarkly/mcp-server"],
      "env": {
        "LAUNCHDARKLY_ACCESS_TOKEN": "YOUR_ACCESS_TOKEN"
      }
    }
  }
}
```

Replace `YOUR_ACCESS_TOKEN` with the user’s LaunchDarkly API access token. After editing, restart the editor or reload MCP.

### Verify (local server)

1. If you have MCP tool access, call **`list-feature-flags`** with the user’s `projectKey` (e.g. `request: { "projectKey": "YOUR_PROJECT_KEY" }`). A normal response confirms the server and token.
2. If MCP tools are not visible yet, have the user run **`ldcli flags list`** (or curl the REST API) to validate credentials independently while MCP reloads.
