# Tool Patterns Reference

Annotated examples from the codebase showing each tool complexity pattern. Use these as templates when building new tools.

## Pattern 1: Simple CRUD

The simplest pattern — one API call, pruned response. From `src/tools/projects.ts`:

```typescript
export const getProject = {
  name: "get-project" as const,
  description:
    "Get a LaunchDarkly project with its environments and SDK keys. " +
    "Use to retrieve SDK keys for an existing project or verify a project exists.",
  inputSchema: {
    projectKey: z.string(),
  },
  async execute(ctx: ToolContext, input: {
    projectKey: string;
  }) {
    const raw = await ldFetch<Record<string, unknown>>(
      ctx,
      `/projects/${input.projectKey}`,
      { params: { expand: "environments" } },
    );

    return ctx.json(pruneProject(raw));
  },
};
```

Key points:
- One `ldFetch` call, one `prune*` call, one `ctx.json` return
- `as const` on the name for type safety
- Explicit TypeScript type on the `input` parameter
- `params` for query string parameters

## Pattern 2: Read-Then-Mutate

Fetch current state before applying a change. Returns before/after so agents see the diff. From `src/tools/targeting.ts` (simplified):

```typescript
export const toggleFlag = {
  name: "toggle-flag" as const,
  description:
    "Turn a feature flag's targeting on or off in a specific environment. " +
    "Returns the previous and new state.",
  inputSchema: {
    projectKey: z.string(),
    flagKey: z.string(),
    env: z.string(),
    on: z.boolean(),
    comment: z.optional(z.string()),
  },
  async execute(ctx: ToolContext, input: { /* ... */ }) {
    // Step 1: Read current state
    const currentRaw = await ldFetch<Record<string, unknown>>(
      ctx,
      `/flags/${input.projectKey}/${input.flagKey}`,
      { params: { env: input.env } },
    );
    const previousState = Boolean(currentEnv?.["on"]);

    // Step 2: Apply mutation
    await ldPatch(
      ctx,
      `/flags/${input.projectKey}/${input.flagKey}`,
      [{ kind: input.on ? "turnFlagOn" : "turnFlagOff" }],
      { comment: input.comment, environmentKey: input.env },
    );

    // Step 3: Return before/after
    return ctx.json({
      key: input.flagKey,
      env: input.env,
      on: input.on,
      previousState,
    } satisfies PrunedToggleResponse);
  },
};
```

Key points:
- GET before PATCH/POST
- `previousState` captured before mutation
- `ldPatch` for semantic patch API
- Error handling for approval-required environments (409 Conflict)

## Pattern 3: Compound Read

Multiple independent API calls combined into a structured assessment. From `src/tools/aiconfigs.ts`:

```typescript
export const getAIConfigHealth = {
  name: "get-ai-config-health" as const,
  description:
    "Health check for an AI Config. Detects common issues: missing models, " +
    "missing prompts, orphaned tool references, and empty configs.",
  inputSchema: {
    projectKey: z.string(),
    configKey: z.string(),
  },
  async execute(ctx: ToolContext, input: { /* ... */ }) {
    // Step 1: Parallel API calls with graceful fallback
    const [configRaw, toolsRaw] = await Promise.all([
      ldFetch<Record<string, unknown>>(
        ctx,
        `/projects/${input.projectKey}/ai-configs/${input.configKey}`,
        { headers: LD_BETA_HEADERS },
      ),
      ldFetch<Record<string, unknown>>(
        ctx,
        `/projects/${input.projectKey}/ai-tools`,
        { params: { limit: 200 } },
      ).catch((): Record<string, unknown> => ({ items: [] })),
    ]);

    // Step 2: Analyze and categorize issues
    const config = pruneAIConfigForDetail(configRaw);
    const issues: AIConfigHealthIssue[] = [];

    for (const v of config.variations) {
      if (!v.modelConfigKey) {
        issues.push({
          type: "missing_model",
          detail: `Variation '${v.key}' has no modelConfigKey.`,
          variationKey: v.key,
        });
      }
      // ... more checks
    }

    // Step 3: Compute verdict
    let health: "healthy" | "warning" | "unhealthy";
    if (hasCriticalIssue) health = "unhealthy";
    else if (issues.length > 0) health = "warning";
    else health = "healthy";

    // Step 4: Return structured assessment
    return ctx.json({
      key: config.key,
      name: config.name,
      health,
      issues,
      variations: variationSummaries,
    } satisfies PrunedAIConfigHealth);
  },
};
```

Key points:
- `Promise.all` for independent calls
- `.catch(() => fallback)` for non-critical data sources
- Structured issue categorization
- Verdict system (healthy/warning/unhealthy or safe/caution/blocked)

## Pattern 4: Multi-Step Orchestration

The most complex pattern — 4-5 API calls, analysis, verdict. From `src/tools/readiness.ts`:

```typescript
export const checkRemovalReadiness = {
  name: "check-removal-readiness" as const,
  description:
    "Detailed safety check before removing a feature flag. Returns a readiness " +
    "verdict: 'safe', 'caution', or 'blocked'.",
  inputSchema: {
    projectKey: z.string(),
    flagKey: z.string(),
    env: z.string(),
  },
  async execute(ctx: ToolContext, input: { /* ... */ }) {
    // Step 1: Fire 5 API calls in parallel
    const [flagRaw, statusRaw, dependentRaw, expiringRaw, codeRefsRaw] = await Promise.all([
      ldFetch(ctx, `/flags/${input.projectKey}/${input.flagKey}`, ...),
      ldFetch(ctx, `/flag-statuses/${input.projectKey}/${input.env}/${input.flagKey}`),
      ldFetch(ctx, `/flags/.../dependent-flags/${input.flagKey}`)
        .catch((): Record<string, unknown> => ({ items: [] })),
      ldFetch(ctx, `/flags/.../expiring-targets/${input.env}`)
        .catch((): Record<string, unknown> => ({ items: [] })),
      ldFetch(ctx, `/code-refs/statistics/${input.flagKey}`)
        .catch((): Record<string, unknown> => ({})),
    ]);

    // Step 2: Extract and classify data
    const blockers: ReadinessIssue[] = [];
    const warnings: ReadinessIssue[] = [];

    // Check active traffic
    if (state === "active") {
      blockers.push({
        type: "active_traffic",
        detail: "Flag is actively receiving evaluation requests.",
      });
    }

    // Check dependencies
    if (dependentFlags.length > 0) {
      blockers.push({
        type: "has_dependents",
        detail: `${dependentFlags.length} flag(s) depend on this flag.`,
      });
    }

    // Step 3: Compute verdict
    let readiness: "safe" | "caution" | "blocked";
    if (blockers.length > 0) readiness = "blocked";
    else if (warnings.length > 0) readiness = "caution";
    else readiness = "safe";

    // Step 4: Return comprehensive assessment
    return ctx.json({
      key: input.flagKey,
      readiness,
      blockers,
      warnings,
      details: { ... },
    } satisfies PrunedRemovalReadiness);
  },
};
```

Key points:
- All 5 calls fire in parallel (none depend on each other)
- `.catch()` on every non-critical call
- Clear distinction between blockers (must fix) and warnings (review)
- Rich `details` section for agent follow-up actions

## Pattern 5: Validation Gates

Common validation patterns used across all tool types:

```typescript
// Format validation
assert(
  MODEL_CONFIG_KEY_PATTERN.test(input.modelConfigKey),
  {
    error: `modelConfigKey must be in Provider.model-id format ` +
      `(e.g. OpenAI.gpt-4o). Got: '${input.modelConfigKey}'.`,
  },
  { status: 400 },
);

// Required combination
assert(
  input.instructions !== undefined || input.messages !== undefined,
  {
    error: "Either 'instructions' (agent mode) or 'messages' " +
      "(completion mode) must be provided.",
  },
  { status: 400 },
);

// Confirmation for destructive operations
assert(
  input.confirm === true,
  {
    error: "Deleting an AI Config is irreversible. " +
      "Set confirm=true to proceed.",
  },
  { status: 400 },
);

// Non-empty update body
const body: Record<string, unknown> = {};
if (input.name !== undefined) body["name"] = input.name;
if (input.description !== undefined) body["description"] = input.description;
assert(
  Object.keys(body).length > 0,
  { error: "At least one field must be provided to update." },
  { status: 400 },
);
```

## Response Pruning

Example from `src/lib/prune.ts` showing how raw API responses are stripped to agent-friendly shapes:

```typescript
export function pruneAIConfigForDetail(
  raw: Record<string, unknown>,
): PrunedAIConfigDetail {
  const variations = Array.isArray(raw["variations"])
    ? (raw["variations"] as Record<string, unknown>[]).map(pruneAIConfigVariation)
    : [];

  return {
    key: String(raw["key"] ?? ""),
    name: String(raw["name"] ?? ""),
    mode: String(raw["mode"] ?? ""),
    description: String(raw["description"] ?? ""),
    tags: Array.isArray(raw["tags"]) ? (raw["tags"] as string[]) : [],
    archived: Boolean(raw["archived"]),
    variations,
  };
}
```

Key points:
- Defensive access with `String(raw["field"] ?? "")`
- `Array.isArray()` checks before mapping
- Nested pruning functions for sub-objects
- No `_links`, `_access`, `_version` in the output

## Test Patterns

Tests use Node.js built-in test runner (`node:test`) and assertions (`node:assert/strict`):

```typescript
import { describe, it, afterEach } from "node:test";
import assert from "node:assert/strict";
import { createMockCtx, mockFetch, jsonFromResponse } from "../helpers.ts";

describe("my-tool", () => {
  let cleanup: (() => void) | undefined;
  afterEach(() => { cleanup?.(); cleanup = undefined; });

  // Happy path
  it("returns expected response shape", async () => {
    cleanup = mockFetch({ "/api-path": RAW_FIXTURE });
    const ctx = createMockCtx();
    const response = await myTool.execute(ctx, { key: "test" });
    const data = await jsonFromResponse<Record<string, unknown>>(response);
    assert.equal(data["key"], "test");
  });

  // Validation gate
  it("rejects invalid input", async () => {
    const ctx = createMockCtx();
    let threw = false;
    try {
      await myTool.execute(ctx, { key: "" });
    } catch (err: unknown) {
      threw = true;
      if (err instanceof Error) {
        assert.ok(err.message.includes("expected error text"));
      }
    }
    assert.ok(threw, "Expected an error");
  });

  // Request body inspection
  it("sends correct request body", async () => {
    let capturedBody = "";
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (_input, init) => {
      if (init?.method === "POST") {
        capturedBody = typeof init.body === "string" ? init.body : "";
      }
      return Response.json(RAW_FIXTURE);
    };
    cleanup = () => { globalThis.fetch = originalFetch; };

    const ctx = createMockCtx();
    await myTool.execute(ctx, { key: "test", name: "Test" });

    const parsed = JSON.parse(capturedBody);
    assert.equal(parsed["key"], "test");
  });
});
```
