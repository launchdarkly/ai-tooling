# Changelog

All notable changes to this repository will be documented in this file.

## Unreleased

- Add `release-autopilot/launchdarkly-release-autopilot-onboarding` 0.1.0-experimental: a step-by-step wizard that asks which capabilities to set up (auto-flagging, auto-releasing), hands off the GitHub App install or authorize link, maps chosen repos, guides managed or bring-your-own-key Vega inference, and reviews or creates environment release plans for auto-releasing, or uses the project's release policies where plans are not available. Release policies are required for auto-releasing today; the skill will be updated to use environment release plans by GA, when plans replace policies. One confirmed plan lists every write before any change.
- `release-autopilot/launchdarkly-release-autopilot-settings` 1.4.0-experimental: route first-time setup to the onboarding skill.
- `onboarding` 0.4.0: add `references/sdk/observability-plugin.md` and load it from the SDK install when the user asks for observability, session replay, error monitoring, logs, or tracing. Covers browser (React, JavaScript, Vue), Next.js, Node.js, React Native, Python, Ruby, Go, .NET, iOS, and Android. The plugin goes on the existing client's `plugins` option and reuses its key. `recipes.md` points to the new reference instead of its per-SDK one-liners. The request is honored at any point, including a follow-up after onboarding finished; session replay defaults to strict privacy; an SDK too old for `plugins` gets a question before any major upgrade. Adds three onboarding evals for these paths.
- Claude Code marketplace: add `version`, `author`, `homepage`, `repository`, `license`, `category`, and `keywords` to the `launchdarkly` entry in `.claude-plugin/marketplace.json` so directory listings get the same metadata as `.claude-plugin/plugin.json`. A test keeps the two in sync.
- Rename `factory/launchdarkly-factory-settings` to `release-autopilot/launchdarkly-release-autopilot-settings` and switch it to the `*-release-autopilot-*` MCP tools (Claude Code plugin 1.0.2, Cursor plugin 1.0.3). Requires a hosted MCP server that exposes the new tool names.

- `factory/launchdarkly-factory-settings`: when GitHub is not installed or this member has not authorized, hand the user `githubConnectUrl` (the integration drawer's install or authorize page) and retry after they finish.
- Claude Code plugin 1.0.1: resolve plugin directory scanner findings. Replace the flat `skills/` symlinks with an explicit `skills` list in `.claude-plugin/plugin.json`, add `icon` and `privacyPolicyUrl`, and stop skills from auto-detecting API tokens in environment variables or `~/.claude/config.json` (prefer the MCP server's OAuth; ask the user for a token when a REST call is unavoidable).
- `factory/launchdarkly-factory-settings`: confirm before account-wide writes, maps, repo overrides, and unmaps; add a read-only "why didn't my PR get classified?" path (account gate, mapping, repo override).
- Refine `experiments/launchdarkly-experiment-setup` skill to match the LaunchDarkly REST API tool shapes: nested `iteration` on create, `mutableFieldsByStatus`-aware `update-experiment`, and the new `save-and-start-experiment-iteration` + `stop-experiment-iteration` tools.
- Initial public release of LaunchDarkly agent skills
