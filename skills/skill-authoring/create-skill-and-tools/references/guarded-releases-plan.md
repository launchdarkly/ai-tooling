# Guarded Releases Skill — Implementation Plan

This plan follows the create-skill-and-tools workflow for building a LaunchDarkly skill for **guarded releases** (guarded rollouts).

---

## 1. Coverage Summary & Gap Analysis

### What Guarded Releases Are

Guarded rollouts progressively increase traffic to a new flag or AI Config variation over time while **monitoring chosen metrics for regressions**. If LaunchDarkly detects a regression before reaching 100%, it can stop the release and optionally roll back automatically.

Key differences from basic percentage rollouts:
- **Metric monitoring** — Track errors, latency, conversions, etc.
- **Regression detection** — Configurable thresholds; LaunchDarkly compares new vs. original variation
- **Automatic rollback** — Optional; reverts when regression is detected
- **Minimum context requirements** — Each step needs enough contexts; otherwise auto-rollback

### Current Coverage

| API Area | Skills | Tools | Gap? |
|----------|--------|-------|------|
| Feature flags — targeting (basic) | launchdarkly-flag-targeting | toggle-flag, update-rollout, update-targeting-rules, ... | No |
| Feature flags — guarded rollouts | **(none)** | **(none)** | **Yes** |
| Metrics | **(none)** | **(none)** | **Yes** |

### Why This Gap Matters

- **Progressive rollout** is listed in the gap-analysis-guide as "the most common release pattern"
- Guarded rollouts are the safer, metric-aware variant of that pattern
- Prerequisites (metrics) are also uncovered — no `list-metrics` or `get-metric` tools exist
- Connects to existing skills: flag-create → flag-targeting → **guarded-rollout** → flag-cleanup

---

## 2. Workflow Definition (Skill-First)

The skill guides the agent through:

1. **Prerequisites check** — Flag exists, metrics exist, no conflicting rollouts/experiments
2. **Metric selection** — Choose which metrics to monitor (list available, pick)
3. **Configuration** — Context kind, target variation, regression thresholds, duration, automatic rollback
4. **Start rollout** — Create guarded rollout (toggle on or update fallthrough with guarded rollout config)
5. **Monitor** — Check status, progress, metric performance
6. **Manage** — Stop early, dismiss regression, or roll back if needed

---

## 3. Tool Requirements (Extracted from Skill)

### Existing Tools to Reuse

| Tool | Purpose |
|------|---------|
| `get-flag` | Understand current state, variations, fallthrough before starting |
| `toggle-flag` | Turn flag on (can be combined with guarded rollout config) |
| `update-rollout` | Update fallthrough (can be combined with guarded rollout config) |

### New Tools Required

| Tool | Skill Step | Purpose | API Endpoint | Status |
|------|------------|---------|--------------|--------|
| `list-metrics` | Step 2: Metric selection | List metrics for a project so the agent can help the user choose what to monitor | `GET /api/v2/projects/{projectKey}/metrics` | **New** |
| `get-metric` | Step 2: Metric detail | Get a single metric's definition (key, name, event kind, etc.) | `GET /api/v2/projects/{projectKey}/metrics/{metricKey}` | **New** |
| `start-guarded-rollout` | Step 4: Start rollout | Create a guarded rollout when toggling on or updating fallthrough | `PATCH /api/v2/flags/{projectKey}/{flagKey}` (semantic patch) | **New** |
| `get-guarded-rollout-status` | Step 5: Monitor | Get rollout progress, metric performance, regression state | TBD — may be in `get-flag` expand or separate endpoint | **New** |
| `stop-guarded-rollout` | Step 6: Manage | Stop monitoring early or roll back; choose variation to serve after stop | `PATCH /api/v2/flags/{projectKey}/{flagKey}` (semantic patch) | **New** |
| `dismiss-regression` | Step 6: Manage | Dismiss a regression alert to continue the rollout | `PATCH` (semantic patch) — exact instruction TBD | **New** |

### API Research Notes

- **Guarded rollouts** are configured via the existing [Update feature flag](https://launchdarkly.com/api/feature-flags/patch-feature-flag) API (product docs reference this).
- The **exact semantic patch instructions** for guarded rollouts (e.g., `startGuardedRollout`, `stopGuardedRollout`) are not fully documented in public sources. Implementation will require:
  - Checking the [OpenAPI spec](https://app.launchdarkly.com/api/v2/openapi.json) for feature flag patch instructions
  - Or consulting LaunchDarkly internal API docs / support
- **Metrics API** is documented: `GET /api/v2/projects/{projectKey}/metrics` with pagination, filter, sort.
- **Guarded rollouts** may require `LD-API-Version: beta` header if the feature is in beta.

---

## 4. Tool Specifications (Detailed)

### `list-metrics`

| Field | Value |
|-------|-------|
| **Inputs** | `projectKey` (required), `limit` (optional, default 20), `offset` (optional), `query` (optional, search), `tags` (optional, filter) |
| **Outputs** | `metrics`: array of `{ key, name, description?, tags?, eventKind?, isNumeric? }`, `totalCount` |
| **File** | `src/tools/metrics.ts` (new) |

### `get-metric`

| Field | Value |
|-------|-------|
| **Inputs** | `projectKey`, `metricKey` |
| **Outputs** | `key`, `name`, `description`, `tags`, `eventKind`, `isNumeric`, `unitAggregationType?`, etc. (pruned) |
| **File** | `src/tools/metrics.ts` |

### `start-guarded-rollout`

| Field | Value |
|-------|-------|
| **Inputs** | `projectKey`, `flagKey`, `env`, `metricKeys` (array), `targetVariationIndex`, `contextKind` (optional, default "user"), `rolloutDurationMinutes` (optional), `automaticRollback` (optional, default true), `comment` (optional) |
| **Outputs** | `key`, `env`, `status`, `targetVariation`, `metrics`, `rolloutDuration`, etc. |
| **File** | `src/tools/guarded-rollouts.ts` (new) |
| **Note** | May need to combine with `toggle-flag` or `update-rollout`; exact instruction structure TBD |

### `get-guarded-rollout-status`

| Field | Value |
|-------|-------|
| **Inputs** | `projectKey`, `flagKey`, `env` |
| **Outputs** | `status`, `progressPercent`, `contextsServed`, `metrics` (each: `key`, `relativeDifference`, `regressionDetected`), `rollbackOccurred` |
| **File** | `src/tools/guarded-rollouts.ts` |
| **Note** | May require `expand=insights` or similar on `get-flag`; or a dedicated guarded-rollouts endpoint |

### `stop-guarded-rollout`

| Field | Value |
|-------|-------|
| **Inputs** | `projectKey`, `flagKey`, `env`, `serveVariationIndex` (which variation to serve after stop), `comment` (optional) |
| **Outputs** | `key`, `env`, `previousStatus`, `newState` (variation now served to all) |
| **File** | `src/tools/guarded-rollouts.ts` |

### `dismiss-regression`

| Field | Value |
|-------|-------|
| **Inputs** | `projectKey`, `flagKey`, `env`, `metricKey` (which metric's regression to dismiss), `comment` (optional) |
| **Outputs** | `key`, `env`, `metricKey`, `dismissed` |
| **File** | `src/tools/guarded-rollouts.ts` |

---

## 5. Implementation Plan

### Phase 1: Build the Skill (agent-skills repo)

1. **Create skill directory**: `skills/feature-flags/launchdarkly-guarded-releases/`
2. **Create SKILL.md** with:
   - Frontmatter: `name: launchdarkly-guarded-releases`, description including "guarded rollout", "metric monitoring", "regression detection"
   - Prerequisites: list `get-flag`, `toggle-flag`, `update-rollout`, `list-metrics`, `get-metric`, `start-guarded-rollout`, `get-guarded-rollout-status`, `stop-guarded-rollout`, `dismiss-regression`
   - Workflow: 6 steps (prerequisites → metric selection → config → start → monitor → manage)
   - Edge cases: migration flags, prerequisite flags, approval workflows, no metrics available
   - References: `references/guarded-rollout-concepts.md`, `references/guarded-rollout-api-patterns.md`
3. **Create README.md** — short catalog description
4. **Create references/**:
   - `guarded-rollout-concepts.md` — metrics, regression thresholds, context kinds, duration
   - `guarded-rollout-api-patterns.md` — semantic patch examples (once API is confirmed)
5. **Update repo**:
   - Add to `skills.json` (via `generate_catalog.py`)
   - Add row to main `README.md` skill table
6. **Validate**: `python3 scripts/validate_skills.py` and `python3 scripts/generate_catalog.py`

### Phase 2: Build the Tools (gram-functions repo)

**Track A: Metrics (prerequisite for guarded rollouts)**

1. Create `src/tools/metrics.ts`:
   - `listMetrics` — `list-metrics`
   - `getMetric` — `get-metric`
2. Add prune helpers in `src/lib/prune.ts` for metric list/detail
3. Add types in `src/lib/types.ts`: `PrunedMetricListItem`, `PrunedMetricDetail`
4. Register in `src/gram.ts`

**Track B: Guarded Rollouts (API-dependent)**

1. **API discovery** (blocking): Resolve exact semantic patch instructions for:
   - Starting a guarded rollout (with metrics, context kind, duration, etc.)
   - Stopping a guarded rollout
   - Dismissing a regression
   - Check if `get-flag` with `expand` returns rollout status or if a separate endpoint exists
2. Create `src/tools/guarded-rollouts.ts`:
   - `startGuardedRollout` — `start-guarded-rollout`
   - `getGuardedRolloutStatus` — `get-guarded-rollout-status`
   - `stopGuardedRollout` — `stop-guarded-rollout`
   - `dismissRegression` — `dismiss-regression`
3. Add prune helpers and types
4. Add `LD_BETA_HEADERS` or similar if guarded rollout API is beta
5. Register in `src/gram.ts`

**Validation**: `pnpm run lint`, `pnpm run dev` (MCP Inspector)

### Phase 3: End-to-End Test

Scenario: "Start a guarded rollout for flag X in production, monitoring error rate and latency, with automatic rollback."

1. Use `list-metrics` to find error and latency metrics
2. Use `get-flag` to confirm flag state and variations
3. Use `start-guarded-rollout` with chosen metrics
4. Use `get-guarded-rollout-status` to verify progress
5. (Optional) Use `stop-guarded-rollout` or `dismiss-regression` to exercise management

---

## 6. Dependencies & Risks

| Risk | Mitigation |
|------|-------------|
| Guarded rollout API instructions not documented | Check OpenAPI spec; contact LaunchDarkly if needed; implement metrics tools first (standalone value) |
| Beta API | Add `LD-API-Version: beta` header; document in skill compatibility |
| Guardian plan required | Document in skill: "Guarded rollouts require Guardian plan; all accounts have limited trial" |

---

## 7. Recommended Execution Order

1. **Metrics tools first** — `list-metrics` and `get-metric` are standalone useful and unblock the skill's prerequisite step.
2. **Skill authoring** — Write the skill referencing all tools (including guarded rollout tools) so the workflow is defined.
3. **API research** — Resolve guarded rollout patch instructions before implementing guarded-rollouts.ts.
4. **Guarded rollout tools** — Implement once API is clear.
5. **Integration test** — Run the full scenario.
