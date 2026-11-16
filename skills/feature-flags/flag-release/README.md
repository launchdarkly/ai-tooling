# Flag Release Skill

An Agent Skill that starts the release of an **existing** LaunchDarkly flag guarding a pull request's change, from the project's flag release plan, or from each environment's release plan when the project has none, so the change releases safely after the PR merges.

## Overview

This skill teaches agents how to:
- Confirm the guarding flag exists and is OFF
- Choose how to start the release: from the flag release plan that the user names or the project's default (`get-flag-release-plans`), or else from each environment's release plan. Preview each environment release plan with `get-environment-release-plans` (progressive or guarded)
- Capture the human's **release intent** (release on merge / hold / `notBefore` / segment / prerequisite) and honor it: a held environment is left out of the release or waits for a person (`manual`)
- Start the release linked to the PR: with `create-flag-release` from a flag release plan, or with `create-automated-rollout-config` from each environment's release plan (a project with no flag release plan, a request that the flag release plan cannot express, or a server without `create-flag-release`)

It operates entirely through the LaunchDarkly MCP tools: it never creates flags or edits code. It's the **release step** of the PR flag workflow — after [`launchdarkly-flag-create`](../launchdarkly-flag-create/) has created and wired the flag.

## Installation (Local)

Copy `skills/feature-flags/flag-release/` into your client's skills path.

## Prerequisites

- The remotely hosted LaunchDarkly MCP server.
- The guarding flag already exists (created OFF).
- A pull-request reference (`repoFullName` + PR number).

## Usage

```
Start the release for flag `new-checkout-flow` on PR acme/storefront#482:
staging on merge, hold production until legal signs off.
```

## Structure

```
flag-release/
├── SKILL.md
├── marketplace.json
├── README.md
└── references/
    └── auto-release.md
```

## Related

- [Should Flag Change](../should-flag-change/): Decide whether a change needs a flag
- [LaunchDarkly Flag Create](../launchdarkly-flag-create/): Create + wire the flag
- [Flag & Release a PR Change](../flag-and-release-change/): The end-to-end orchestrator that composes this skill
- [LaunchDarkly Guarded Rollout](../launchdarkly-guarded-rollout/): Drive a bespoke rollout by hand
- [LaunchDarkly Release Plans](../../release-autopilot/launchdarkly-release-plans/): Read and manage environment and flag release plans
- [Release Autopilot Onboarding](../../release-autopilot/launchdarkly-release-autopilot-onboarding/): Set up a project's release plans
- [LaunchDarkly Docs](https://docs.launchdarkly.com)

## License

Apache-2.0
