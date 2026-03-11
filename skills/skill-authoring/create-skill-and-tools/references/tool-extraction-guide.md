# Tool Extraction Guide

How to derive MCP tool specifications from a skill, and how gram-functions tools are structured.

## Extracting Tool Requirements from a Skill

Walk through every step in the skill's Workflow section. At each point where the skill says "Use `tool-name`", capture:

### 1. The tool spec

For each tool referenced in the skill:

| Field | What to capture |
|-------|----------------|
| **Name** | The tool name as written in the skill (e.g., `list-segments`) |
| **Skill step** | Which workflow step references it (e.g., "Step 2: Check for existing segments") |
| **Purpose** | One sentence: what the agent uses it for |
| **Inputs** | Every parameter — name, type, required/optional, constraints |
| **Outputs** | What fields the agent actually needs in the response |
| **API endpoint** | LaunchDarkly REST API method + path |
| **Semantic patch?** | If PATCH, list the allowed instruction kinds |

### 2. Existing vs. new tools

Classify each tool:

- **Exists** — already registered in `src/gram.ts`. The skill just references it.
- **New** — must be built. This is the implementation work.
- **Extended** — exists but needs new capabilities (rare; prefer a new tool over modifying an existing one).

### 3. Shared infrastructure

Identify what the new tools need beyond the tool file itself:

- Pruning functions in `src/lib/prune.ts`
- Type definitions in `src/lib/types.ts`
- Validation helpers in `src/lib/validation.ts`
- Constants in `src/lib/constants.ts`

## Gram-Functions Tool Patterns

All tools in the gram-functions repo follow the same structure. Match these patterns when implementing new tools.

### Tool object shape

Every tool is an exported object with four properties:

```typescript
export const myTool = {
  name: "my-tool" as const,
  description: "What the tool does, written for an agent to understand when to use it.",
  inputSchema: {
    // Zod schemas for every input parameter
  },
  async execute(ctx: ToolContext, input: { /* typed input */ }) {
    // 1. Validate inputs
    // 2. Call the LaunchDarkly API
    // 3. Prune the response
    // 4. Return ctx.json(pruned)
  },
};
```

### Input schemas (Zod)

Use `zod/mini` for all input definitions:

```typescript
import * as z from "zod/mini";

inputSchema: {
  projectKey: z.string(),                              // required string
  env: z.optional(z.string()),                          // optional string
  limit: z.optional(z.number()),                        // optional number
  tags: z.optional(z.array(z.string())),                // optional string array
  confirm: z.boolean(),                                  // required boolean
  action: z.enum(["add", "remove"]),                    // enum
  instructions: z.array(z.record(z.string(), z.unknown())), // semantic patch instructions
}
```

### API calls

Two helpers in `src/lib/api.ts`:

**`ldFetch(ctx, path, options)`** — for GET, POST, DELETE:

```typescript
// GET with query params
const raw = await ldFetch<Record<string, unknown>>(
  ctx,
  `/segments/${input.projectKey}/${input.env}`,
  { params: { limit, sort: "creationDate" } },
);

// POST with body
const raw = await ldFetch<Record<string, unknown>>(
  ctx,
  `/segments/${input.projectKey}/${input.env}`,
  { method: "POST", body: JSON.stringify({ name, key, description, tags }) },
);

// DELETE
await ldFetch(ctx, `/segments/${input.projectKey}/${input.env}/${input.segmentKey}`, {
  method: "DELETE",
});
```

**`ldPatch(ctx, path, instructions, options)`** — for semantic patch:

```typescript
const raw = await ldPatch<Record<string, unknown>>(
  ctx,
  `/segments/${input.projectKey}/${input.env}/${input.segmentKey}`,
  input.instructions,
  { environmentKey: input.env, comment: input.comment },
);
```

The `ldPatch` helper automatically sets `Content-Type: application/json; domain-model=launchdarkly.semanticpatch`.

### Input validation

Use `assert()` from `@gram-ai/functions` for precondition checks:

```typescript
import { assert } from "@gram-ai/functions";

assert(input.confirm === true, {
  error: "confirm must be true to delete. This action is irreversible.",
}, { status: 400 });
```

For semantic patch instruction validation, define an allowed set:

```typescript
const ALLOWED_INSTRUCTIONS = new Set([
  "addIncludedTargets",
  "removeIncludedTargets",
  "addRule",
  "removeRule",
  // ...
]);

for (const instruction of input.instructions) {
  const kind = (instruction as Record<string, unknown>)["kind"];
  assert(
    typeof kind === "string" && ALLOWED_INSTRUCTIONS.has(kind),
    { error: `Unknown or disallowed instruction kind: ${String(kind)}` },
    { status: 400 },
  );
}
```

### Designing inputs for AI agents

Tool inputs should make the agent's job easy. Apply these principles:

**Only require what varies per call.** If a value has a sensible default (like `env` defaulting to `"production"` or `limit` defaulting to `20`), make it optional. The agent shouldn't have to specify obvious defaults every time.

**Use structured types, not raw strings.** If a parameter has a fixed set of values, use `z.enum()` instead of `z.string()`. This lets the agent know the valid options without reading documentation. For example, `z.enum(["add", "remove"])` is better than a bare string where the agent has to guess valid values.

**Keep instruction arrays flexible.** For semantic patch tools, accept `instructions` as `z.array(z.record(z.string(), z.unknown()))` rather than trying to model every instruction variant in Zod. Validate the instruction `kind` at runtime against an allowed set. This keeps the schema simple while still catching invalid instructions.

**Don't expose API implementation details.** The agent shouldn't need to know about `filter` query string syntax or weight multipliers. If the API uses `filter=query:foo,tag:bar`, accept `query` and `tags` as separate input fields and build the filter string internally. If the API uses weights from 0-100000, accept percentages from 0-100 and convert internally.

### Designing outputs for AI agents

This is the most important design decision in a tool. Raw API responses are designed for applications; pruned outputs are designed for agents. The difference matters because:

- **Every field costs tokens.** An agent's context window is finite. Returning 50 fields when only 8 are actionable wastes context that could hold user instructions, code, or other tool results.
- **Agents make decisions on outputs.** The fields you return determine what the agent can reason about. If you omit a field, the agent can't use it. If you include noise, the agent might fixate on irrelevant details.
- **Agents don't navigate links.** Fields like `_links` and `_site` are for HTTP clients to follow URLs. Agents use tools, not URLs.

Apply these principles when deciding what to keep and what to drop:

**Always drop: internal API metadata**

| Field | Why drop it |
|-------|------------|
| `_links` | Navigation URLs for HTTP clients. Agents call tools, not URLs. |
| `_access` | Permission metadata. Not relevant to the workflow task. |
| `_site` | Links to the LaunchDarkly UI. Agents don't open web pages. |
| `_version` | Internal optimistic locking version. Agents don't do conditional updates. |
| `salt`, `sel` | Hashing internals for percentage rollouts. Never relevant to agent decisions. |
| `_id` (on top-level objects) | Internal database IDs. Agents use `key` to identify resources. |

**Always keep: identity and state**

| Field | Why keep it |
|-------|------------|
| `key` | The identifier the agent uses in every subsequent tool call. Without it, the agent can't act on the resource. |
| `name` | Human-readable label the agent uses when talking to the user ("The 'Beta Testers' segment..."). |
| `description` | Helps the agent understand the resource's purpose, especially when deciding whether to reuse or create new. |
| `tags` | Used for filtering and categorization. The agent needs these to find related resources. |

**Keep when it drives a decision in the skill workflow**

| Field | When to keep | Why |
|-------|-------------|-----|
| `rules` (with clauses) | In detail views | The agent needs to see existing targeting rules to decide whether to add, modify, or leave them. |
| `included` / `excluded` (as counts) | In list views | Tells the agent how populated a segment is without dumping thousands of context keys. |
| `included` / `excluded` (truncated lists) | In detail views | The agent may need to see *who* is targeted, but cap at ~10 entries to avoid blowing up context. |
| `_flags` | In detail views | Critical for safety -- tells the agent which flags depend on this segment, which matters before modifying or deleting. |
| `unbounded` | Always | Tells the agent this is a big segment (>15k entries) which changes how it should operate. |
| `creationDate` | In list views | Helps the agent identify old vs. new segments. |
| `version` | In detail views | Lets the agent confirm whether a mutation was applied. |

**Summarize instead of dumping**

For fields that can be very large, summarize rather than return raw data:

- **Target lists**: Return a `count` and a truncated `values` array (first 10). An agent doesn't need to see 10,000 context keys to know the segment has targets.
- **Rules**: Return the full rule structure (clauses, operators, values) since agents need to reason about targeting logic, but cap the `values` array in each clause.
- **Dependent flags (`_flags`)**: Return `key` and `name` for each flag. Drop everything else about the flag -- the agent can call `get-flag` if it needs more.

### Response pruning (implementation)

Apply the above principles using prune functions:

```typescript
import { omitFields } from "../lib/prune.ts";

const PRUNED_FIELDS = ["_links", "_access", "_site", "_version", "salt", "sel"];

const pruned = omitFields(raw, PRUNED_FIELDS);
return ctx.json(pruned);
```

For list endpoints, prune each item to the summary shape:

```typescript
const items = Array.isArray(raw["items"]) ? raw["items"] as Record<string, unknown>[] : [];
return ctx.json({
  segments: items.map(pruneSegmentForList),
  totalCount: Number(raw["totalCount"] ?? items.length),
});
```

### Pruned types

Define types in `src/lib/types.ts` that represent exactly what the tool returns. The type is the contract between the tool and the agent:

```typescript
export interface PrunedSegmentListItem {
  key: string;           // identity -- used in subsequent tool calls
  name: string;          // human-readable label for agent-to-user communication
  description: string;   // helps agent decide whether to reuse
  tags: string[];        // filtering and categorization
  creationDate: number;  // age signal
  rulesCount: number;    // summary: how complex is the targeting?
  includedCount: number; // summary: how many explicit includes?
  excludedCount: number; // summary: how many explicit excludes?
  unbounded: boolean;    // big segment flag -- changes how agent operates
}
```

Use `satisfies` in the prune function to enforce the shape:

```typescript
function pruneSegmentForList(raw: Record<string, unknown>): PrunedSegmentListItem {
  return {
    key: String(raw["key"]),
    name: String(raw["name"]),
    // ...
  } satisfies PrunedSegmentListItem;
}
```

### Tool registration

In `src/gram.ts`, import and chain:

```typescript
// Tools — Segments
import { listSegments } from "./tools/segments.ts";
import { getSegment } from "./tools/segments.ts";
import { createSegment } from "./tools/segments.ts";
import { updateSegmentTargeting } from "./tools/segments.ts";
import { deleteSegment } from "./tools/segments.ts";

const gram = new Gram({ /* ... */ })
  // ... existing tools ...
  // Segments
  .tool(listSegments)
  .tool(getSegment)
  .tool(createSegment)
  .tool(updateSegmentTargeting)
  .tool(deleteSegment);
```

### File organization

Group related tools in a single file under `src/tools/`:

| File | Domain |
|------|--------|
| `inventory.ts` | list-flags, get-flag |
| `health.ts` | get-flag-health, find-stale-flags, get-flag-status-across-envs |
| `create.ts` | create-flag, update-flag-settings |
| `targeting.ts` | toggle-flag, update-rollout, update-targeting-rules, update-individual-targets, copy-flag-config |
| `cleanup.ts` | archive-flag, delete-flag, manage-expiring-targets |
| `readiness.ts` | check-removal-readiness |
| `segments.ts` | (new) list-segments, get-segment, create-segment, update-segment-targeting, delete-segment |

### Validation commands

After implementing tools:

```bash
pnpm run lint    # TypeScript type checking (tsc --noEmit)
pnpm run dev     # MCP Inspector for manual testing
```

## LaunchDarkly API Conventions

Patterns to be aware of when mapping API endpoints to tools:

- **Base path:** All endpoints are under `/api/v2/`
- **Auth:** `Authorization: Bearer <token>` header
- **Semantic patch:** PATCH with `Content-Type: application/json; domain-model=launchdarkly.semanticpatch`
- **Beta APIs:** Require `LD-API-Version: beta` header
- **Pagination:** `limit` and `offset` query params; response includes `totalCount`
- **Filtering:** Query string `filter` param with `key:value` syntax, comma-separated
- **409 responses:** May indicate approval is required; check for `approvalUrl` in the response body
