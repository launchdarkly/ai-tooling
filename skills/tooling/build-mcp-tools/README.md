# Build MCP Tools Skill

An Agent Skill that teaches how to design and build tools for the LaunchDarkly MCP server using Gram Functions. Covers philosophy, architecture, tool complexity patterns, and practical workflows.

## Overview

This skill teaches agents how to:
- Analyze agent skills to identify high-value tool opportunities
- Choose the right complexity level for a tool (simple CRUD, compound read, read-then-mutate, multi-step orchestration)
- Build tools that return pruned, actionable responses instead of raw API data
- Follow the patterns established across the codebase
- Write tests that match existing conventions

## Installation (Local)

Copy `skills/build-mcp-tools/` into your agent client's skills path.

## Prerequisites

- Familiarity with TypeScript and the Gram Functions framework
- Access to the LaunchDarkly API documentation

## Usage

```
Help me build a new MCP tool for managing segments
```

```
What pattern should I use for this tool?
```

```
I need a tool that combines multiple API calls — show me how
```

## Structure

```
build-mcp-tools/
├── SKILL.md
├── README.md
└── references/
    └── tool-patterns.md
```

## Related

- [Gram Functions Docs](https://www.getgram.ai/docs/gram-functions)
- [LaunchDarkly API Docs](https://apidocs.launchdarkly.com)

## License

Apache-2.0
