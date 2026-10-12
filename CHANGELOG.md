# Changelog

All notable changes to this repository will be documented in this file.

## Unreleased

- `factory/launchdarkly-factory-settings`: when GitHub is not installed or this member has not authorized, hand the user `githubConnectUrl` (the integration drawer's install or authorize page) and retry after they finish.
- Claude Code plugin 1.0.1: resolve plugin directory scanner findings. Replace the flat `skills/` symlinks with an explicit `skills` list in `.claude-plugin/plugin.json`, add `icon` and `privacyPolicyUrl`, and stop skills from auto-detecting API tokens in environment variables or `~/.claude/config.json` (prefer the MCP server's OAuth; ask the user for a token when a REST call is unavoidable).
- `factory/launchdarkly-factory-settings`: confirm before account-wide writes, maps, repo overrides, and unmaps; add a read-only "why didn't my PR get classified?" path (account gate, mapping, repo override).
- Refine `experiments/launchdarkly-experiment-setup` skill to match the LaunchDarkly REST API tool shapes: nested `iteration` on create, `mutableFieldsByStatus`-aware `update-experiment`, and the new `save-and-start-experiment-iteration` + `stop-experiment-iteration` tools.
- Initial public release of LaunchDarkly agent skills
