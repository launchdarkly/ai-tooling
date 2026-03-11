---
name: create-skill-and-tools
description: "Design and plan a new LaunchDarkly agent skill and its supporting MCP tools from scratch. Use when someone wants to add a new workflow skill to the agent-skills repo and needs to identify what tools to build, define their inputs and outputs, and produce an implementation plan. Guides a skill-first design approach: define the workflow before building the tools."
license: Apache-2.0
compatibility: Works in repositories following the Agent Skills open standard
metadata:
  author: launchdarkly
  version: "1.0.0-experimental"
---

# Design a New Skill and Its Supporting Tools

You're using a skill that will guide you through the full process of designing a new LaunchDarkly agent skill and the MCP tools it needs. Your job is to survey existing coverage, research the domain, identify a workflow gap, write the skill first to define the ideal experience, then extract tool requirements from it and produce a concrete implementation plan.

This skill follows a **skill-first design** approach: define the workflow before building the tools. The skill becomes the spec for what tools to build, why they exist, and how they compose together.

## Prerequisites

- Access to the LaunchDarkly agent-skills repo (or a fork)
- Access to the LaunchDarkly gram-functions repo (where MCP tools are implemented)
- Access to the [LaunchDarkly REST API docs](https://apidocs.launchdarkly.com)
- Python 3.x (for validation scripts)

## Core Principles

1. **Survey before you build.** You cannot find a gap without knowing both sides: what skills and tools already exist, and what the API makes possible. Always start by exploring both repos and the API docs.
2. **Skill-first design.** Write the workflow before the tools exist. Reference tools by name in the skill even when they haven't been built yet. The skill defines the ideal user experience; the tools are built to fulfill it.
3. **Evaluate candidates on real criteria.** Not every gap is worth filling. Assess candidates by how common the workflow is, whether tools exist or need to be built, and how the skill connects to existing ones.
4. **Extract, don't invent.** Tool requirements come from walking through the skill and asking "what does the agent need to call here?" Each tool should trace back to a specific skill step.

## Workflow

### Step 1: Survey Existing Coverage

Before identifying gaps, build a clear picture of what already exists. Do these in parallel:

1. **Explore the agent-skills repo.**
   - Read every skill under `skills/` — note the category, name, what workflow it covers, and what MCP tools it references
   - Produce a coverage summary: "these workflows are covered by skills"
   - Note how skills connect to each other (e.g., flag-create leads to flag-targeting leads to flag-cleanup)

2. **Explore the gram-functions repo.**
   - Read `src/tools/` — every tool file, what it does, what API endpoints it calls
   - Read `src/gram.ts` — what tools are registered on the Gram instance
   - Produce a tool inventory: "these tools exist, calling these API endpoints"

3. **Scan the LaunchDarkly REST API docs.**
   - Fetch the [API documentation](https://apidocs.launchdarkly.com) and identify the top-level resource categories
   - Compare against the tool inventory — which API areas have no tools at all?

**Output of this step:** A coverage map showing which workflows have skills, which API areas have tools, and where the gaps are.

See [Gap Analysis Guide](references/gap-analysis-guide.md) for what to look for and how to compare.

### Step 2: Research Uncovered Workflows

For each gap identified in Step 1, dig deeper:

1. **Read the API docs** for the uncovered area. Fetch the specific endpoint documentation — methods, parameters, request bodies, response shapes. Pay attention to semantic patch instructions if the API supports them.

2. **Read the product docs** for the same area. The API docs tell you what's *possible*; the product docs tell you what users *actually do* and why. Look for:
   - Quickstart guides (they encode the most common workflow)
   - Use case examples
   - Terminology and concepts users need to understand

3. **Identify the real-world workflows** that live in each gap. A workflow is a sequence of steps a user goes through to accomplish something, not just a single API call. Good workflows have:
   - A clear starting point ("I want to...")
   - Multiple steps that compose together
   - Decision points where the user needs guidance
   - A verifiable end state

### Step 3: Evaluate Candidates and Choose

Present 2-3 candidate workflows and evaluate each against these criteria:

| Criteria | What to assess |
|----------|---------------|
| **Frequency** | How often do users encounter this workflow? Is it something every team does, or niche? |
| **Complexity** | Does the workflow have enough steps and decisions to benefit from a guided skill? Simple one-tool workflows don't need a skill. |
| **Tool readiness** | Do the MCP tools already exist, or do they need to be built? More existing tools = faster to ship. |
| **Connectivity** | Does this fill a gap between existing skills? Does it extend the lifecycle coverage? |
| **API depth** | Is the API surface rich enough to support a meaningful skill? Are there semantic patch instructions, multiple endpoints, filtering options? |

For each candidate, state:
- The workflow in one sentence
- Which criteria it scores well on and which it doesn't
- Your recommendation and why

Let the user choose before proceeding.

### Step 4: Deep-Dive on the Chosen Workflow

Once a workflow is chosen, gather the implementation details. Do these in parallel:

1. **Fetch the specific API endpoint docs.** For every endpoint in the chosen area, document:
   - HTTP method and path
   - Required and optional parameters
   - Request body structure
   - Available semantic patch instructions (if applicable)
   - Response shape

2. **Read existing tool and skill source code for patterns.** Understand how to match conventions:
   - In gram-functions: how tools define input schemas (Zod), call the API (`ldFetch`/`ldPatch`), prune responses, and handle errors
   - In agent-skills: how skills structure their workflow, frontmatter, core principles, edge cases, references
   - Read `template/SKILL.md.template` for the expected skill structure

**Output of this step:** The raw material needed to write the skill and define the tools — API contracts, implementation patterns, and domain knowledge.

See [Tool Extraction Guide](references/tool-extraction-guide.md) for the patterns to follow.

### Step 5: Write the Skill First

Now create the skill. This is the most important ordering decision in this entire workflow: **the skill is written before any tools are designed or built.** The skill defines the ideal workflow from the user's perspective. The tools exist to serve the skill, not the other way around. If you skip this step or reorder it after tool design, you end up with tools that don't compose into a coherent workflow.

1. **Create the skill directory** under `skills/<category>/<skill-name>/` with `SKILL.md`, `README.md`, and `references/`.

2. **Define what the skill enables.** Before writing anything, articulate in one sentence what this skill makes possible. Follow this pattern from existing skills:
   - "An Agent Skill for **safely automating feature flag cleanup workflows** using LaunchDarkly as the source of truth."
   - "An Agent Skill for **introducing new feature flags into a codebase**, matching existing patterns and conventions."
   - "An Agent Skill for **controlling feature flag targeting, rollouts, and rules** in LaunchDarkly."

   The one-liner should state: what the agent can now do (the action), in what context (the domain), and why it matters (the value). This sentence becomes the README opener and informs the SKILL.md description.

3. **Write SKILL.md** following the template and existing skill patterns:
   - Frontmatter: `name` (must match directory), `description` (keyword-rich, includes "when to use"), `compatibility`, `metadata`
   - Job-to-be-done intro: one sentence describing what the skill guides the user through
   - Prerequisites: list every MCP tool the skill will reference, even ones that don't exist yet
   - Core principles: 3-4 principles specific to this domain
   - Workflow: numbered steps following the Explore → Assess → Execute → Verify pattern
   - Edge cases: table of situations and how to handle them
   - What NOT to do: anti-patterns specific to this domain
   - References: links to reference files

4. **Write reference files** in `references/` for:
   - Domain-specific guidance (types, concepts, decision tables)
   - API patterns (semantic patch instruction examples, common request shapes)

5. **Write README.md** following the established pattern. The README is how humans and agents identify what the skill does at a glance. Follow this structure:
   - **Title**: `# LaunchDarkly [Domain] Skill`
   - **One-liner**: The "An Agent Skill for..." sentence from sub-step 2
   - **Overview**: "This skill teaches agents how to:" followed by 3-5 concrete bullet points describing the capabilities the skill enables
   - **Usage**: 2-3 natural language prompts a user would say to trigger the skill (e.g., `Create a beta-testers segment for the new feature`)
   - **Structure**: Directory tree showing the skill's files
   - **Related**: Links to connected skills and LaunchDarkly docs

6. **Validate the skill:**
   ```bash
   python3 scripts/validate_skills.py
   python3 scripts/generate_catalog.py
   ```

The key here: **reference tools by name in the skill even though they don't exist yet.** The skill defines the ideal workflow. If a step needs to "list all segments in the environment," write it as "Use `list-segments` to check what already exists." This creates the tool contract.

See the existing [create-skill](../create-skill/SKILL.md) for detailed guidance on SKILL.md authoring, frontmatter, and validation.

### Step 6: Extract Tool Requirements from the Skill

Now that the skill exists, walk through the SKILL.md you wrote in Step 5 and pull out every tool it references. The tool requirements come *from* the skill — each tool traces back to a specific workflow step. For each tool, define:

1. **Name** — the tool name as referenced in the skill (e.g., `list-segments`)
2. **Skill step** — which workflow step references it and why
3. **Purpose** — what the tool does in one sentence
4. **Inputs** — every parameter with its type, whether it's required or optional, and any constraints
5. **Outputs** — what the pruned response looks like (fields the agent actually needs)
6. **API endpoint** — the LaunchDarkly REST API method and path it maps to
7. **Semantic patch instructions** — if applicable, the allowed instruction kinds

Organize this as a tool specification table. This becomes the implementation spec for the gram-functions repo.

Also identify:
- **Existing tools the skill reuses** — tools that already exist and just need to be referenced (e.g., `update-targeting-rules` for wiring a segment into a flag)
- **New tools the skill needs** — tools that must be built
- **Shared infrastructure** — pruning functions, types, validation helpers that the new tools need

See [Tool Extraction Guide](references/tool-extraction-guide.md) for how to derive tool specs from a skill.

### Step 7: Produce the Implementation Plan

Assemble everything into a concrete plan. **The plan must reflect the skill-first execution order** — the skill is written and validated first, then the tools are built to fulfill the contracts defined by the skill. Do not reorganize tracks to put tools before the skill.

**Phase 1: The skill (agent-skills repo)**

Lead the plan with the one-liner from Step 5 sub-step 2 — the "An Agent Skill for..." sentence. This is the first thing anyone reading the plan should see. It answers "what gap are we filling?" in one sentence before any implementation details. For example:

> An Agent Skill for creating and managing reusable audience segments in LaunchDarkly, reducing targeting duplication across feature flags.

Then list:
- Skill files created (SKILL.md, README.md, references/)
- The workflow the skill defines and what tools it references by name
- Changes to repo docs (README.md table)
- Validation results from `validate_skills.py` and `generate_catalog.py`

This is the spec. The tools below exist to serve it.

**Phase 2: Build the tools (gram-functions repo)**

For each tool the skill references, the plan should include:
- Tool name, traced back to the skill step that needs it
- Input schema, output shape, and API endpoint
- Tool file to create (e.g., `src/tools/segments.ts`)
- Pruning helpers to add (`src/lib/prune.ts`)
- Types to add (`src/lib/types.ts`)
- Gram instance registration (`src/gram.ts`)
- Validation: `pnpm run lint`, `pnpm run dev`

**Phase 3: End-to-end test**

A concrete scenario that exercises the skill and tools together (e.g., "Create a beta-testers segment and gate a feature behind it"). This proves the skill's workflow works with the tools it defined.

## Edge Cases

| Situation | Action |
|-----------|--------|
| No clear gap exists | The current skills may be sufficient. Don't force a new skill — report that coverage is strong and suggest incremental improvements to existing skills instead. |
| Gap exists but API doesn't support it | Document the gap but don't build the skill. A skill without working tools is misleading. |
| Tools already exist but no skill | Skip the tool-building track. Write only the skill to orchestrate existing tools. This is the fastest path. |
| Multiple strong candidates | Present them with tradeoffs and let the user choose. Don't pick for them unless asked. |
| Chosen workflow is too broad | Break it into multiple skills. Each skill should cover one coherent workflow, not an entire domain. |
| API is in beta | Note this in the skill's compatibility field and tool descriptions. Use the `LD-API-Version: beta` header where required. |

## What NOT to Do

- Don't build tools before writing the skill, and don't present tools before the skill in the implementation plan. The skill defines what tools are needed. If the plan puts tools first, the ordering is wrong — go back and restructure it with the skill as Phase 1.
- Don't skip the survey step. Without knowing existing coverage, you'll duplicate work or miss how the new skill connects to others.
- Don't evaluate candidates only on technical feasibility. A tool that's easy to build but covers a workflow nobody uses isn't worth the maintenance cost.
- Don't put API implementation details in SKILL.md. Move semantic patch instruction examples, request shapes, and endpoint specifics to reference files.
- Don't create a skill that's just a thin wrapper around one tool. If the workflow is a single API call, the tool itself is sufficient — a skill adds value when it orchestrates multiple tools with decision points.

## References

- [Gap Analysis Guide](references/gap-analysis-guide.md) — How to survey existing coverage and identify meaningful gaps
- [Tool Extraction Guide](references/tool-extraction-guide.md) — How to derive tool specs from a skill, gram-functions patterns, and API mapping
