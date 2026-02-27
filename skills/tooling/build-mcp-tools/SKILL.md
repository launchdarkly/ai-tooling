---
name: build-mcp-tools
description: "Guide for designing and building MCP tools using Gram Functions. Covers philosophy, codebase architecture, tool complexity patterns, and a step-by-step workflow for creating tools that return the most meaningful information to agents."
license: Apache-2.0
compatibility: This codebase uses @gram-ai/functions with TypeScript
metadata:
  author: launchdarkly
  version: "1.0.0-experimental"
---

# Build MCP Tools

You're using a skill that will guide you through designing and building tools for this MCP server. Your job is to understand what makes a good tool, choose the right complexity level, and follow the patterns established in this codebase.

## Philosophy

### Skill-First Tool Design

Tools in this codebase are not an exhaustive API wrapper. We don't build one tool per API endpoint. Instead, we let **agent skills** drive which tools get built.

Skills describe workflows — step-by-step processes an agent follows. When a skill keeps requiring the same sequence of API calls, or when an agent would need to manually combine data from multiple sources, that's a signal to build a tool.

**Build tools that collapse agent work, not tools that mirror API endpoints.**

### Why This Matters

1. **Signal over noise.** Raw API responses include metadata agents never need (`_links`, `_access`, `_version`, timestamps). Pruning responses to only what matters reduces context window usage and improves agent decision-making.

2. **Fewer round trips.** A compound tool that makes 3 API calls and returns a structured result is always better than forcing the agent to make 3 tool calls and stitch results together. Agents are bad at multi-step orchestration; tools should absorb that complexity.

3. **Validation at the boundary.** Tools validate input before making API calls. Bad `modelConfigKey` format, empty update bodies, missing confirmation flags — catch these immediately with clear error messages instead of letting the agent discover them from cryptic API errors.

4. **Actionable descriptions.** Tool descriptions should tell agents *when* to use the tool, *what* it returns, and *what to do next*. They're not documentation — they're decision-making context for the agent.

## Architecture

### File Structure

```
src/
├── gram.ts          # Gram instance, env schema, all .tool() registrations
├── lib/
│   ├── api.ts       # ldFetch and ldPatch helpers (auth, error handling)
│   ├── constants.ts # Shared constants, API headers, validation patterns
│   ├── parse.ts     # Data extraction helpers (status, timestamps, env config)
│   ├── prune.ts     # Response pruning functions (strip metadata, reshape)
│   └── types.ts     # All TypeScript interfaces (ToolContext, Pruned* types)
└── tools/
    ├── aiconfigs.ts   # AI Config tools (CRUD + compound)
    ├── aitools.ts     # AI Tool definition tools
    ├── aivariations.ts # AI Config Variation tools
    ├── cleanup.ts     # Flag archive/delete tools
    ├── create.ts      # Flag creation tool
    ├── health.ts      # Flag health + staleness tools
    ├── inventory.ts   # Flag listing + detail tools
    ├── projects.ts    # Project management tools
    ├── readiness.ts   # Flag removal readiness assessment
    └── targeting.ts   # Targeting, rollout, toggle tools
```

### Key Conventions

- **One domain per file.** Group tools by domain (`aiconfigs.ts`, `targeting.ts`), not by complexity.
- **Exports are tool definitions.** Each tool is an exported object with `name`, `description`, `inputSchema`, and `execute`.
- **Registration in gram.ts.** All tools are imported and chained via `.tool()` in `src/gram.ts`.
- **Types in types.ts.** All `Pruned*` response interfaces and `ToolContext` live in `src/lib/types.ts`.
- **Pruning in prune.ts.** All response transformation logic lives in `src/lib/prune.ts`.
- **Input validation via Zod.** Schemas use `zod/mini` with `z.string()`, `z.number()`, `z.optional()`, etc.
- **Runtime validation via assert.** Use `assert()` from `@gram-ai/functions` for business logic validation.

## Tool Complexity Spectrum

Tools in this codebase range from simple CRUD to complex multi-step orchestrations. Understanding the spectrum helps you choose the right pattern. See `references/tool-patterns.md` for annotated code examples.

### 1. Simple CRUD

Single API call, pruned response. Use for straightforward read or write operations where the API response shape is close to what agents need.

**Examples:** `get-project` (src/tools/projects.ts), `create-ai-config` (src/tools/aiconfigs.ts), `list-ai-tools` (src/tools/aitools.ts)

**Pattern:**
1. Validate input (Zod handles most of this)
2. Make one API call via `ldFetch`
3. Prune the response
4. Return via `ctx.json()`

### 2. Read-Then-Mutate

Fetch current state, then apply a mutation. Returns before/after comparison so agents can verify the change worked.

**Examples:** `toggle-flag` (src/tools/targeting.ts), `clone-ai-config-variation` (src/tools/aivariations.ts)

**Pattern:**
1. GET current state
2. Extract relevant fields for the "before" snapshot
3. PATCH/POST the mutation
4. Return `{ previousState, newState }` or `{ source, created }`

**When to use:** Any mutation where the agent benefits from seeing what changed, or where the tool needs to read existing state to apply overrides.

### 3. Compound Reads

Multiple API calls merged into a single structured assessment. Independent calls run in parallel via `Promise.all`.

**Examples:** `get-flag-health` + `find-stale-flags` (src/tools/health.ts), `get-ai-config-health` (src/tools/aiconfigs.ts)

**Pattern:**
1. Fire independent API calls in parallel with `Promise.all`
2. Use `.catch(() => fallback)` for non-critical calls that might fail
3. Analyze results, categorize issues
4. Return structured verdict with supporting detail

**When to use:** Health checks, audits, status overviews — any time agents need a synthesized view across multiple data sources.

### 4. Multi-Step Orchestration

Sequential API calls where each step depends on the previous. The tool absorbs workflow logic that agents would otherwise handle poorly.

**Examples:** `check-removal-readiness` (src/tools/readiness.ts), `setup-ai-config` (src/tools/aiconfigs.ts)

**Pattern:**
1. Fire independent calls in parallel where possible
2. Analyze intermediate results
3. Classify outcomes (blockers, warnings, verdicts)
4. Return a structured assessment the agent can act on

**When to use:** Multi-step workflows from skills that agents currently do manually. Look for skills where Step 1-3 are always executed together.

### 5. Unified Action Tools

Single tool that handles multiple related operations via an `action` parameter.

**Examples:** `manage-expiring-targets` (src/tools/cleanup.ts)

**Pattern:**
1. Accept an `action` enum (`list`, `add`, `remove`, `update`)
2. Branch logic based on action
3. Validate action-specific required fields via `assert()`
4. Return action-appropriate response

**When to use:** When multiple related operations share context (same flag, same environment) and the agent would need to pick between 3-4 very similar tools.

### 6. Semantic Patch

LaunchDarkly-specific pattern for flag mutations that use `application/json; domain-model=launchdarkly.semanticpatch` content type. The `ldPatch` helper handles this format.

**Examples:** `toggle-flag`, `update-rollout`, `update-targeting-rules` (src/tools/targeting.ts)

**Pattern:**
1. Use `ldPatch()` instead of `ldFetch()` for mutations
2. Pass semantic patch instructions as `[{ kind: "instructionKind", ...params }]`
3. Handle 409 Conflict for approval-required environments

## Workflow: Building a New Tool

### Step 1: Analyze the Skill

Read the relevant skill in `.agents/skills/`. Identify:
- Which API calls the skill's workflow requires
- Which steps are always done together (compound tool candidate)
- What information agents need in the response

### Step 2: Choose Complexity Level

Use the spectrum above. Ask:
- Is this a single API call? -> Simple CRUD
- Does the agent need before/after? -> Read-then-mutate
- Are multiple data sources being combined? -> Compound read
- Are skill steps always sequential? -> Multi-step orchestration

### Step 3: Define the Response Type

Add `Pruned*` interfaces to `src/lib/types.ts` **before** writing the tool. This forces you to think about what agents actually need.

Rules for response types:
- Strip all `_links`, `_access`, `_version`, `_site`, `_createdAt`, `_updatedAt`
- Use `satisfies` in the return statement for compile-time checking
- Prefer flat shapes over nested when possible
- Include verdicts, summaries, and counts — not raw data dumps

### Step 4: Add Pruning Logic

If the tool needs new pruning functions, add them to `src/lib/prune.ts`. Pruning functions:
- Take raw API response objects
- Return typed, pruned shapes
- Handle missing/optional fields defensively
- Are unit-tested independently

### Step 5: Build the Tool

Add the tool to the appropriate `src/tools/*.ts` file. Follow these guidelines:

**Description:** Write 2-3 sentences. First sentence says what it does. Remaining sentences say when to use it or what to do with the result.

**Input Schema:** Use `z.string()`, `z.number()`, `z.boolean()`, `z.enum()`, `z.optional()`, `z.array()`, `z.object()`, `z.record()`. Always add explicit TypeScript types on the `execute` function's `input` parameter.

**Validation:** Use `assert()` for business logic checks (format validation, required combinations, confirmation flags). Provide clear error messages that tell the agent what to fix.

**API Calls:** Use `ldFetch` for standard REST. Use `ldPatch` for semantic patch mutations. Always pass `ctx.signal` through for cancellation support (this is handled automatically by `ldFetch`).

**Error Handling:** Use `.catch(() => fallback)` for non-critical parallel calls. Let critical failures propagate — `ldFetch` calls `ctx.fail()` on non-2xx responses.

### Step 6: Register in gram.ts

Import the tool and add a `.tool()` call in the appropriate section of `src/gram.ts`.

### Step 7: Write Tests

Add tests to the appropriate `src/__tests__/tools/*.test.ts` file:
- Use `mockFetch` for simple route-based mocking
- Use manual `globalThis.fetch` override when you need to inspect request bodies or track call order
- Always test validation gates (invalid input should throw)
- Test the happy path response shape
- For compound tools, verify the number and order of API calls

### Step 8: Verify

Run `npm run lint` and `npm test`. Fix any type errors or test failures.

## Design Principles

### Descriptions Are Agent Context

Bad: `"Get an AI config."`

Good: `"Get a specific AI Config with all variations, models, and parameters. Returns the full detail view including per-variation instructions/messages and tool attachments. Use list-ai-configs for a summary view instead."`

### Validate Early, Fail Clearly

Bad: Let the API return a 400 with a cryptic error.

Good:
```typescript
assert(
  MODEL_CONFIG_KEY_PATTERN.test(input.modelConfigKey),
  {
    error: `modelConfigKey must be in Provider.model-id format (e.g. OpenAI.gpt-4o). Got: '${input.modelConfigKey}'.`,
  },
  { status: 400 },
);
```

### Parallel When Possible

When making multiple independent API calls, always use `Promise.all`:

```typescript
const [config, tools] = await Promise.all([
  ldFetch(ctx, `/ai-configs/${key}`, { headers: LD_BETA_HEADERS }),
  ldFetch(ctx, `/ai-tools`, { params: { limit: 200 } })
    .catch((): Record<string, unknown> => ({ items: [] })),
]);
```

### Graceful Degradation

Non-critical API calls (e.g., fetching tools list for a health check) should use `.catch()` to provide fallback data so the tool still works even if one source is unavailable.

### Use `satisfies` for Type Safety

Always end return statements with `satisfies PrunedTypeName` to catch shape mismatches at compile time:

```typescript
return ctx.json({
  key: config.key,
  health: "healthy",
  issues: [],
} satisfies PrunedAIConfigHealth);
```

## What NOT to Do

- Don't build one tool per API endpoint — let skills guide tool design
- Don't return raw API responses — always prune
- Don't skip validation — agents send surprising input
- Don't use `console.log` for debugging — the runtime is serverless
- Don't add third-party dependencies when Web APIs or Node.js standard library suffice
- Don't forget to add types to `src/lib/types.ts` before writing the tool
- Don't forget to register the tool in `src/gram.ts`

## Related Skills

- `aiconfig-create` — Example of a skill that drives tool design
- `launchdarkly-flag-cleanup` — Uses compound tools (`check-removal-readiness`)
- `launchdarkly-flag-discovery` — Uses compound reads (`get-flag-health`, `find-stale-flags`)
