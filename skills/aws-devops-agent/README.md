# AWS DevOps Agent

This folder holds the files that `ldcli aws-devops-agent setup` installs in an AWS DevOps Agent space. An agent space is the AWS DevOps Agent workspace that holds skills, custom agents, and MCP servers.

| File | What setup makes from it |
|------|--------------------------|
| `experiment-orchestration/SKILL.md` | The `experiment-orchestration` skill. Every agent in the space can load it. |
| `agents/experiment-orchestrator.md` | The system prompt of the `experiment-orchestrator` custom agent. The agent runs the skill with the LaunchDarkly MCP tools. |

The skill takes a product goal through a LaunchDarkly experiment and, if the experiment wins, a guarded rollout. Guarded rollouts depend on the LaunchDarkly plan; without them, the skill uses a regular rollout. The skill uses the LaunchDarkly MCP server, and GitHub for the code change and deployment when GitHub is connected to the agent space. Without GitHub, it hands those steps to a person.

## Install

Run `ldcli aws-devops-agent setup`. If ldcli isn't installed, see the [ldcli installation instructions](https://github.com/launchdarkly/ldcli#installation), or install the files by hand as described below. ldcli is needed only for setup: the skill and the custom agent use only the LaunchDarkly MCP server. Setup connects the LaunchDarkly MCP server to the agent space and installs the skill and the custom agent. For the steps, run `ldcli aws-devops-agent setup --help`.

To install the files by hand, use the AWS DevOps Agent console:

1. Add `experiment-orchestration/SKILL.md` as a skill.
2. Create a custom agent named `experiment-orchestrator`. Use `agents/experiment-orchestrator.md` as its system prompt, and attach the skill and the LaunchDarkly MCP tools.

## Change the files

ldcli embeds a copy of each file. ldcli compares the text in an agent space with the texts of earlier releases, so that it can update a copy that nobody edited. If you change a file here, copy it to ldcli and add the hash of the new text there. The files are in `internal/awsdevops/` in the [ldcli repository](https://github.com/launchdarkly/ldcli).
