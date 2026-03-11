# Create Skill and Supporting Tools (LaunchDarkly)

This skill guides the full process of designing a new LaunchDarkly agent skill and the MCP tools it needs -- from identifying workflow gaps through producing an implementation plan. It follows a skill-first design approach: define the workflow before building the tools.

## Overview

The workflow covers:
- Surveying existing skills and tools to build a coverage map
- Researching the LaunchDarkly REST API for uncovered workflows
- Evaluating candidate workflows on frequency, complexity, and connectivity
- Writing the skill first (referencing tools by name before they exist)
- Extracting tool requirements from the skill (names, inputs, outputs, API endpoints)
- Producing an implementation plan across both the agent-skills and gram-functions repos

## Usage

Ask:

```
I want to add a new skill to the LaunchDarkly agent-skills repo. Help me identify a workflow gap, design the skill, and plan the tools it needs.
```

Or more specifically:

```
Design a new skill for [workflow area] and figure out what MCP tools need to be built to support it.
```

## Structure

```
create-skill-and-tools/
├── SKILL.md
├── README.md
└── references/
    ├── gap-analysis-guide.md
    └── tool-extraction-guide.md
```

## Related

- [create-skill](../create-skill/) -- Detailed guidance on SKILL.md authoring, frontmatter, and validation (referenced from this skill's Step 5)
- [Agent Skills Specification](https://agentskills.io/specification)
- [LaunchDarkly REST API Docs](https://apidocs.launchdarkly.com)
