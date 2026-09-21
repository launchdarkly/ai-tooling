---
name: launchdarkly-factory-settings
description: "Configure LaunchDarkly Factory settings (GitHub App auto-flagging and auto-releasing) via the hosted MCP. Use when the user wants to turn on auto-flagging, map a GitHub repo to a LaunchDarkly project, set Factory account defaults, or set up code automation without the UI."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.0.0-experimental"
---

# LaunchDarkly Factory Settings

You're using a skill that configures Factory (GitHub App code automation) the same way flag skills use the LaunchDarkly MCP. Your job is to discover GitHub repos by `owner/name`, set account defaults, map repos to projects, and verify — without asking the user for a numeric GitHub id, and without sending `autoCleanup`.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server.

**Required MCP tools:**
- `get-factory-settings` / `update-factory-settings`
- `list-factory-github-repos` (GitHub App install — mappable repos)
- `list-factory-repo-settings` (already mapped)
- `update-factory-repo-settings` / `get-factory-repo-settings` / `delete-factory-repo-settings`

If these tools are missing, the Gram/hosted MCP has not attached them yet. Do not invent REST calls or numeric `repoId`s.

Factory settings are in alpha: the underlying endpoints are gated by the `enable-factory-settings` flag and are not on LaunchDarkly's public API spec. If every Factory tool returns 404, the account is not in the alpha — tell the user rather than retrying or falling back to REST.

## Core Principles

1. **Account settings are the master gate.** A mapped repo cannot enable auto-flagging or auto-releasing if the account has that capability off. Turn the account on first, then map repos.
2. **Discover, then map.** Call `list-factory-github-repos` (or pass `owner/name`). Never ask the user for GitHub's numeric repository id.
3. **`projectKey` on first map.** The first `update-factory-repo-settings` for a repo must include `projectKey`. Later updates can omit it.
4. **Omit `autoCleanup`.** It appears on some API schemas but is not part of Factory settings yet. Never send it; never copy it from a response into a PATCH.
5. **Do not install the GitHub App via MCP.** If `list-factory-github-repos` says the app is not installed, stop and tell the user to install it in the LaunchDarkly UI.

## Workflow

### Step 1: Read current settings

1. `get-factory-settings` — account-wide auto-flagging / auto-releasing (and whether auto-flagging PRs need approval).
2. `list-factory-repo-settings` — already mapped repos (effective settings).
3. `list-factory-github-repos` — install list with `name` (`owner/name`) and `githubRepoId`. Optional `projectKey`; any project works (install is account-wide).

If the GitHub App is not installed, stop. Mapping requires an existing install.

### Step 2: Set account defaults (if needed)

Use `update-factory-settings` with only the fields that should change:

- `autoFlagging.enabled` / `autoFlagging.approvalRequired` (approval is only valid here)
- `autoReleasing.enabled`

Do not send `autoCleanup`. Requires `updateFactorySettings`.

### Step 3: Map repositories

For each repo the user named (`launchdarkly/gonfalon`, current git remote, etc.):

1. Prefer `repo: "owner/name"` on `update-factory-repo-settings`.
2. Include `projectKey` when creating the mapping.
3. Optionally set repo-level `autoFlagging` / `autoReleasing` overrides. Omitted capabilities inherit the account setting.

Requires `updateFactoryRepoSettings` on the mapped project.

### Step 4: Verify

- `get-factory-repo-settings` with the same `owner/name`.
- Confirm effective `enabled` matches intent (account off ⇒ repo cannot be on).
- `list-factory-repo-settings` should include the repo.

To unmap: `delete-factory-repo-settings` (idempotent).

## Out of scope

- Auto-cleanup
- GitHub App install / OAuth
- Vega BYOK
- Observability MCP (`github_repositories`) — do not require a second MCP server just to map a Factory repo
