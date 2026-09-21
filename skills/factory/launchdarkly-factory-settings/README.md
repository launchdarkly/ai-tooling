# LaunchDarkly Factory Settings Skill

An Agent Skill for configuring Factory (GitHub App auto-flagging and auto-releasing) through the LaunchDarkly MCP, the same way flag skills manage flags.

## Overview

This skill teaches agents how to:

- Read account-wide Factory defaults
- List GitHub App install repos as `owner/name` (not numeric ids)
- Map a repository to a LaunchDarkly project
- Override auto-flagging / auto-releasing per repo
- Unmap a repository

## Installation (Local)

- **Generic**: copy `skills/factory/launchdarkly-factory-settings/` into your client's skills path

## Prerequisites

The remotely hosted LaunchDarkly MCP server must expose the Factory settings tools (`get-factory-settings`, `list-factory-github-repos`, `update-factory-repo-settings`, and siblings). The GitHub App must already be installed; this skill does not install it.

## Usage

```
Turn on auto-flagging and map launchdarkly/gonfalon to project default
```

```
Which GitHub repos are mapped for Factory, and which can I map?
```

## Related

- [LaunchDarkly Flag Create](../../feature-flags/launchdarkly-flag-create/): Create flags after Factory is mapped
- [LaunchDarkly MCP Server](https://github.com/launchdarkly/mcp-server)
- [LaunchDarkly Docs](https://docs.launchdarkly.com)

## License

Apache-2.0
