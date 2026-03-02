# Skill Structure Guide

How LaunchDarkly skills are organized and what content belongs where.

## Directory Layout

```
skills/
├── <category>/           # e.g., feature-flags, ai-configs, skill-authoring
│   └── <skill-name>/     # e.g., launchdarkly-flag-create
│       ├── SKILL.md      # Required: main workflow guide
│       ├── README.md     # Optional: short description
│       ├── marketplace.json  # Optional: for marketplace publishing
│       └── references/   # Optional: detailed guides
│           ├── guide-1.md
│           └── guide-2.md
```

## SKILL.md Structure

Follow this pattern (see `template/SKILL.md.template`):

### 1. Frontmatter
```yaml
---
name: skill-name          # Must match directory name
description: "..."        # Clear, keyword-rich
compatibility: "..."      # Requirements
metadata:
  author: launchdarkly
  version: "0.1.0"
---
```

### 2. Job-to-Be-Done Intro

Start with a sentence like:

> You're using a skill that will guide you through [the job]. Your job is to explore [what], assess [what], choose the right path, execute, and verify it was done correctly.

### 3. Prerequisites

- What's required to use this skill
- MCP tools, API access, permissions

### 4. Core Principles

3–4 short principles that guide the workflow.

### 5. Workflow

Numbered steps (Step 1, Step 2, …):

- **Step 1: Explore**: Understand the situation before acting
- **Step 2: Assess**: Decide the right approach
- **Step 3: Execute**: Do the work (link to references)
- **Step 4: Verify**: Confirm completion (agent performs checks)

Each step should be actionable. Link to references for detailed implementation.

### 6. Edge Cases

Table: `| Situation | Action |`

### 7. What NOT to Do

Bullet list of anti-patterns.

### 8. References

Links to `references/*.md` files.

## When to Use References

Move content to `references/` when:

- Implementation details (API patterns, code examples)
- Long decision tables or guides
- Stack-specific or use-case-specific content
- Content that would make SKILL.md exceed ~500 lines

Keep in SKILL.md:

- The workflow steps
- Core principles
- Decision tables (if short)
- Edge cases
- Verification steps

## Workflow Pattern

All skills follow:

1. **Explore**: Don't assume. Look at the codebase, existing config, or context first.
2. **Assess**: Based on exploration, decide the right path.
3. **Choose**: Pick references that match the situation.
4. **Execute**: Follow the reference to do the work.
5. **Verify**: Actually perform checks (API calls, scripts) and report results.

## Naming Conventions

- **Skill name:** `lowercase-with-hyphens` (e.g., `launchdarkly-flag-create`)
- **Category:** `lowercase-with-hyphens` (e.g., `feature-flags`)
- **Reference files:** `kebab-case.md` (e.g., `sdk-patterns.md`)
- **Name length:** Under 64 characters
- **Description length:** Under 1024 characters

## Validation

The `validate_skills.py` script checks:

- Frontmatter exists and is valid
- Required fields: `name`, `description`, `compatibility`
- `name` matches directory name
- Name and description length limits
- No excluded directories

Run before every commit:
```bash
python3 scripts/validate_skills.py
```
