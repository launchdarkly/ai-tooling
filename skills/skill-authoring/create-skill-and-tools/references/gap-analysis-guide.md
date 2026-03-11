# Gap Analysis Guide

How to survey existing skill and tool coverage, compare against the LaunchDarkly API surface, and identify meaningful gaps worth filling.

## What to Explore

### Agent-Skills Repo

Look at every skill under `skills/`. For each, capture:

| Field | What to note |
|-------|-------------|
| **Name** | The skill's directory name |
| **Category** | `feature-flags`, `ai-configs`, `skill-authoring`, etc. |
| **Workflow** | What job does it help accomplish? (one sentence) |
| **MCP tools referenced** | Every tool named in Prerequisites or Workflow steps |
| **Connections** | Does it reference other skills? Does it hand off to another skill? |

Also look at:
- `skills.json` — the generated catalog of all skills
- `README.md` — the skill table showing the full landscape
- `template/SKILL.md.template` — the expected structure for new skills

### Gram-Functions Repo

Look at every tool file under `src/tools/`. For each tool, capture:

| Field | What to note |
|-------|-------------|
| **Name** | The tool's `name` property |
| **File** | Which file it lives in (e.g., `targeting.ts`, `inventory.ts`) |
| **API endpoint** | The LaunchDarkly REST API path it calls |
| **HTTP method** | GET, POST, PATCH, DELETE |
| **Purpose** | What it does in one sentence |

Also look at:
- `src/gram.ts` — the full list of registered tools and how they're grouped
- `src/lib/api.ts` — the API client pattern (`ldFetch`, `ldPatch`)
- `src/lib/prune.ts` — how responses are pruned for agent consumption

### LaunchDarkly REST API

Scan the [API documentation](https://apidocs.launchdarkly.com) for the top-level resource categories. Common categories include:

- Feature flags
- Segments
- Environments
- Projects
- Experiments (beta)
- Metrics
- Approvals
- Code references
- Audit log
- Contexts
- Teams
- Webhooks
- Integrations

## Building the Coverage Map

Organize your findings into a table:

| API Area | Skills covering it | Tools covering it | Gap? |
|----------|-------------------|-------------------|------|
| Feature flags — create | launchdarkly-flag-create | create-flag, update-flag-settings | No |
| Feature flags — targeting | launchdarkly-flag-targeting | toggle-flag, update-rollout, update-targeting-rules, ... | No |
| Feature flags — cleanup | launchdarkly-flag-cleanup | archive-flag, delete-flag, check-removal-readiness | No |
| Feature flags — discovery | launchdarkly-flag-discovery | list-flags, get-flag, find-stale-flags, ... | No |
| Segments | (none) | (none) | **Yes** |
| Experiments | (none) | (none) | **Yes** |
| Metrics | (none) | (none) | **Yes** |

The "Gap?" column highlights areas where either:
- There are API endpoints but no tools calling them
- There are tools but no skill orchestrating them
- There is neither

## Evaluating Gaps

Not every gap is worth filling. Apply these filters:

### Is the workflow common?

Ask: "How often does a typical LaunchDarkly user encounter this?" Signals of common workflows:
- The product docs have a quickstart guide for it
- The API has multiple endpoints (CRUD + semantic patch)
- The UI has a dedicated section for it
- It's mentioned in other skills as something the user might need next

### Is the workflow complex enough for a skill?

A skill adds value when it orchestrates multiple tools with decision points. If the workflow is one API call with no decisions, a tool alone is sufficient.

Signs a workflow needs a skill:
- Multiple steps that must happen in order
- Decision points ("should I use type A or type B?")
- Safety checks before executing
- Verification after executing
- Edge cases that require different handling

### Does it connect to existing skills?

The most valuable new skills extend the lifecycle coverage. Look for:
- Gaps *between* existing skills (e.g., nothing between "configure targeting" and "clean up the flag")
- Missing entry points (e.g., "I want to target a segment" but no skill to create segments)
- Missing exit points (e.g., a skill creates something but there's no skill to manage it afterward)

### Is the API stable enough?

Check whether the API endpoints are:
- **Generally available** — safe to build against
- **Beta** (`LD-API-Version: beta` header required) — usable but may change
- **Deprecated** — do not build against

Beta APIs are acceptable but should be noted in the skill's compatibility field.

## Common Gaps to Look For

Based on how feature flag platforms are typically used, these workflows are commonly encountered:

| Workflow | Description | Why it matters |
|----------|-------------|---------------|
| **Segment management** | Create and manage reusable audience groups | Reduces targeting duplication across flags |
| **Progressive rollout** | Incrementally roll a feature from 0% to 100% | The most common release pattern |
| **Experimentation** | A/B testing with metrics and statistical analysis | Core value prop of feature flag platforms |
| **Environment promotion** | Promote flag config through dev → staging → prod | Standard deployment pipeline |
| **Approval workflows** | Request, review, and apply changes with approval gates | Required for compliance in many orgs |
| **Metric creation** | Define metrics for experiments and monitoring | Prerequisite for experimentation |

## Output Format

After completing the gap analysis, present findings as:

1. **Coverage summary** — what's covered, organized by lifecycle stage or API area
2. **Identified gaps** — each gap with a one-sentence description
3. **Candidate evaluation** — 2-3 gaps evaluated against the criteria above
4. **Recommendation** — which gap to fill first and why
