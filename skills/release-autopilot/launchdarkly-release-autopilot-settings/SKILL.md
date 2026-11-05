---
name: launchdarkly-release-autopilot-settings
description: "Configure LaunchDarkly Release Autopilot settings (GitHub App auto-flagging and auto-releasing) via the hosted MCP, or diagnose why a pull request was not classified / auto-flagged. Use when the user wants to turn on auto-flagging, map a GitHub repo to a LaunchDarkly project, change Release Autopilot account defaults, unmap a repo, or asks why Release Autopilot did not classify their PR. For first-time setup (pick capabilities, connect GitHub, choose inference, review release policies), use launchdarkly-release-autopilot-onboarding instead."
license: Apache-2.0
compatibility: Requires the remotely hosted LaunchDarkly MCP server
metadata:
  author: launchdarkly
  version: "1.5.0-experimental"
---

# LaunchDarkly Release Autopilot Settings

You're using a skill that configures Release Autopilot (GitHub App code automation) through the LaunchDarkly MCP, or explains why a PR was not classified. Release Autopilot can open and change pull requests (auto-flagging) and can drive auto-releasing. Treat every write as production automation with a blast radius.

## Prerequisites

This skill requires the remotely hosted LaunchDarkly MCP server.

**Required MCP tools:**
- `get-automations`: account settings plus a page of GitHub App install repos, each with `mapped` and its effective settings. Pass `repo` for one repository, or `mapped: true` / `mapped: false` to filter.
- `update-automations`: `accountWide: true` changes account settings; `accountWide: false` with `repo` maps or overrides one repository.
- `delete-automations-repo-settings`: unmap one repository.

On a server that has not picked up the Automations rename yet, the same tools are named `get-release-autopilot`, `update-release-autopilot`, and `delete-release-autopilot-repo-settings`; use those names with the same arguments. If a call fails with "this tool has been removed from the server", ask the user to reconnect the LaunchDarkly MCP server so it loads the new tool names, then retry.

If these tools are missing, stop. Do not invent REST calls, numeric GitHub ids, or "fixes" by guessing settings.

The underlying endpoints require the Release Autopilot add-on. If every Release Autopilot tool returns 404, the account does not have the Release Autopilot add-on enabled — tell the user "Your account does not have the Release Autopilot add-on enabled," rather than retrying or falling back to REST.

## Core Principles

1. **Fail closed.** Diagnosis is read-only. Never change settings to "make classification work" unless the user confirmed that exact write after seeing current vs proposed state.
2. **Each repo's own settings decide what runs in it.** On accounts that use the project Automations settings page (`/projects/{projectKey}/settings/automations`), Release Autopilot reads only the repo's settings and does not read the account settings. There, a capability that the repo does not turn on is off. Other accounts still use the account settings too, until a migration moves them, so the account tools stay. On those accounts:
   - A capability runs in a repo only when the account has it on and the repo does not turn it off.
   - Turning a capability **off** for the account turns it off in every mapped repo.
   - Turning it **on** for the account starts it in every mapped repo that does not turn it off.

   The effective values that `get-automations` returns for a repo follow the rule that its account uses. Use them, not the account settings, to tell what runs in a repo.
3. **Confirm before every Release Autopilot write.** Account PATCH, mapping, repo overrides, and unmap all use [Confirm before write](#confirm-before-write). Only touch repos the user named.
4. **Least privilege.** Never enable auto-releasing unless the user explicitly asked to auto-release (that can ship code). Never turn `approvalRequired` off unless they explicitly asked to drop the approval gate. Never map or unmap repos they did not name. Never iterate the install list and map everything.
5. **Discover, then map.** Pass `owner/name`. Never ask for a numeric GitHub id. Prefer `git remote` of the current workspace when they say "this repo" / "this PR"; if remotes disagree (fork vs upstream), ask which one. `owner/name` resolves against the GitHub App install list only — a repo outside the install cannot be resolved or acted on, because Release Autopilot works through the App. A 404 saying the repo is not on the install, or that the App is not installed, is the answer; do not retry with other spellings or look the repo up elsewhere.
6. **`projectKey` on first map.** Required when creating a mapping; later updates can omit it.
7. **Omit `autoCleanup`.** Not part of Release Autopilot settings yet. Never send it; never copy it from a response into a PATCH.
8. **GitHub connect is a browser link.** If `get-automations` returns `githubConnectUrl`, give the user that exact URL and wait until they say they finished. Then call `get-automations` again. Do not install or authorize GitHub yourself. `flow=install` is Install GitHub App. `flow=authorize` is Authorize GitHub. Both are the same pages as the integration drawer. The user must already be logged into LaunchDarkly in that browser.

## Confirm before write

**STOP.** Do not call `update-automations` or `delete-automations-repo-settings` until the user has answered yes to the proposal in this turn. A yes from an earlier turn, or a vague "fix it" / "go ahead" that does not name the setting, is not enough.

1. Read current state first (`get-automations`, with `repo` if the change is repo-scoped).
2. State **now** vs **proposed**, in one or two sentences. Include blast radius. For a map, state the auto-flagging **and** auto-releasing that the repo gets (read the current state from `get-automations` first).
3. Wait. Do not batch the write in the same tool round as the question.

**Account change** (`update-automations` with `accountWide: true`, any field, including turning things on). These effects apply on accounts that still use the account settings (see [Core Principles](#core-principles)):

> Auto-flagging is ON for this account. Turn it OFF for all mapped repos? Auto-flagging pull requests will stop until it is turned back on.

> Auto-flagging is OFF for this account. Turn it ON for the account? Mapped repos that do not turn it off can start getting auto-flagging pull requests.

> Auto-flagging approvalRequired is ON. Turn it OFF? Auto-flagging PRs would no longer require that approval gate.

Same pattern for auto-releasing, and say that auto-releasing can ship.

**Map or change one repo** (`update-automations` with `accountWide: false`):

Always name **both** capabilities in the proposal, and send both on a new mapping: `{ "enabled": true }` or `{ "enabled": false }`. A capability the repo does not set is off on accounts that use project Automations settings, and follows the account on accounts that still use account settings. Do not confirm a map that only mentions auto-flagging.

> `launchdarkly/gonfalon` is not mapped. Map it to project `default` with auto-flagging ON and auto-releasing OFF? Release Autopilot can start classifying and opening auto-flagging PRs in that repo. Auto-releasing stays off.

> `launchdarkly/gonfalon` is not mapped. Map it to project `default` with auto-flagging ON and auto-releasing ON? Release Autopilot can start auto-flagging PRs in that repo **and** auto-releasing, which can ship.

> `launchdarkly/gonfalon` is mapped to `default` with auto-flagging effective ON and auto-releasing effective OFF. Set a repo override turning auto-flagging OFF for this repo only? Auto-releasing stays as it is (OFF).

**Unmap** (`delete-automations-repo-settings`):

> `launchdarkly/gonfalon` is mapped to project `default` with auto-flagging effective ON and auto-releasing effective OFF. Unmap it? Release Autopilot will stop auto-flagging and auto-releasing that repo until it is mapped again.

After they confirm, apply **only** the fields in the proposal. Then verify (do not use verify as the safety check).

## Choose a workflow

Route on what the user asked for, not on account state. Check these in order:

- **"Why didn't Release Autopilot classify / auto-flag my PR?"** (or similar) → [Why didn't my PR get classified?](#why-didnt-my-pr-get-classified), even on an account with nothing set up. Do not write settings in that workflow.
- **First-time setup** ("set up Release Autopilot", "onboard us", "get started") → [`launchdarkly-release-autopilot-onboarding`](../launchdarkly-release-autopilot-onboarding/SKILL.md). It gathers every decision first and confirms one plan.
- Configure / map / turn on / unmap → [Configure settings](#configure-settings).

## Why didn't my PR get classified?

Use this when the user asks why a PR was not classified, not auto-flagged, or Release Autopilot ignored the PR. **Read-only.** Check in this order. Stop at the first failure and tell them how to fix it (then [Confirm before write](#confirm-before-write) if they ask you to apply the fix). If the answer is that auto-flagging is off or the repo is not mapped, and nothing is set up yet, offer [`launchdarkly-release-autopilot-onboarding`](../launchdarkly-release-autopilot-onboarding/SKILL.md) as the way to set it up.

Identify the GitHub repo (`owner/name`) from the PR URL, `git remote`, or the name they gave. If you cannot identify one repo, ask. Do not diagnose a different repo.

1. **Is this repo mapped to a project?** `get-automations` with `repo: "owner/name"`; check `mapped` on the returned repository. If the error or response includes `githubConnectUrl`, read `flow`:
   - `flow=install`: the GitHub App is not installed, so Release Autopilot never sees the PR. That is the answer. Give the user the link and stop.
   - `flow=authorize`: this member has not authorized GitHub, so `owner/name` cannot be looked up. That is not why Release Autopilot skipped the PR. Say so, give the user the link, and resume at this step after they finish. Do not report it as the fix.

   A repo that is on the install but unmapped is a different answer. Unmapped install repos do not run Release Autopilot. Stop.
2. **Is auto-flagging effectively on for this repo?** On the repo payload, auto-flagging `enabled` is the effective value, under the rule that the account uses (see [Core Principles](#core-principles)). If it is false, that is the answer. Stop and say the cause:
   - `enabledOverride` is false: the repo turns auto-flagging off.
   - `enabledOverride` is true: the repo turns it on, so the account settings turn it off. This happens only on accounts that still use account settings.
   - `enabledOverride` is absent: the repo does not set auto-flagging. Auto-flagging needs to be turned on for this repo. If `account.autoFlagging.enabled` is false, say that an account that still uses account settings also needs it on for the account.

If both look fine (repo mapped, repo auto-flagging effective on):

- Do **not** flip settings to "try something."
- Point them at the Release Autopilot runbooks. These are internal LaunchDarkly Confluence pages (PD space); there is no public docs URL yet. Classification can still fail for reasons this MCP surface cannot see (GitHub App install on the wrong org, PR not in an installed repo, workflow/app permissions, classifier skip rules).
  - [Flag Classification (ODD) Runbook](https://launchdarkly.atlassian.net/wiki/spaces/PD/pages/5377097848/WIP+Flag+Classification+ODD+Runbook) — the classifier itself: verdicts (`not-suited`, `already-flagged`), escalations, and the per-PR ledger that records why a PR got the verdict it did.
  - [GitHub App Runbook](https://launchdarkly.atlassian.net/wiki/spaces/PD/pages/5157388373/GitHub+App+Runbook) — the PR event never reaching Release Autopilot: install scope, permissions, webhooks.
- Optional reads: `get-automations` with `repo` to confirm the repo is on the install list (`visibleOnInstall`); `autoFlagging.approvalRequired` if they expected a PR and one exists but is waiting on approval.

## Configure settings

### Step 1: Read current settings

1. `get-automations` with no filter: account settings and the first page of install repos (optional `projectKey`; install is account-wide). Page with `offset` while `hasMore` is true.
2. `get-automations` with `repo: "owner/name"` for each repo the user named.

If `githubConnectUrl` is present, give the user that link and stop this turn. Do not map until a later call omits the URL.

### Step 2: Account defaults (if needed)

If an account PATCH is needed, follow [Confirm before write](#confirm-before-write), then `update-automations` with `accountWide: true`, `confirm: true`, and **only** the confirmed fields:

- `autoFlagging.enabled` / `autoFlagging.approvalRequired` (approval is only valid here). The agent backend does not read `approvalRequired` today: every auto-flagging proposal waits for `@launchdarkly approve` either way. If a user asks to turn approval off, tell them it currently has no effect before proposing the change.
- `autoReleasing.enabled`

Do not send `autoCleanup`. Requires permission to update account Release Autopilot settings.

### Step 3: Map or override a repository

Only for repos the user named. Follow [Confirm before write](#confirm-before-write), then `update-automations` with `accountWide: false` and `confirm: true`:

1. Prefer `repo: "owner/name"`.
2. Include `projectKey` when creating a mapping.
3. Repo-level `autoFlagging` / `autoReleasing`. Send both on a new mapping (see [Map or change one repo](#confirm-before-write)). On accounts that still use account settings, a repo cannot turn on a capability the account has off.

Requires permission to update Release Autopilot repo settings on the mapped project.

### Step 4: Verify (after a confirmed write)

- `get-automations` (with `repo` for a repo-scoped change).
- Effective `enabled` must match the proposal. On accounts that still use account settings, a repo cannot be on while the account has it off.
- Mapped repos appear with `mapped: true` in `get-automations`.

To unmap: [Confirm before write](#confirm-before-write), then `delete-automations-repo-settings` with `repo` and `confirm: true`.

## Out of scope

- Auto-cleanup
- Completing GitHub OAuth inside the tool. Hand the user `githubConnectUrl` instead.
- Vega inference and bring-your-own-key setup, and environment release plans. The [onboarding skill](../launchdarkly-release-autopilot-onboarding/SKILL.md) guides both.
- Observability MCP (`github_repositories`) — do not require a second MCP server just to map a repo
- Changing classification rules, GitHub App permissions, or org install scope via this skill
