const { test } = require("node:test");
const assert = require("node:assert/strict");

const { renderMockResponse, createMockState } = require("../providers/_mock");

const TEMPLATES = require("../mocks/tool-responses.json");

// ---------------------------------------------------------------------------
// createMockState
// ---------------------------------------------------------------------------

test("createMockState returns fresh empty state each call", () => {
  const a = createMockState();
  const b = createMockState();
  assert.deepEqual(a, { configs: {}, flags: {} });
  a.configs["x"] = {};
  assert.deepEqual(b.configs, {}); // independent
});

// ---------------------------------------------------------------------------
// setup-ai-config (stateful write)
// ---------------------------------------------------------------------------

test("setup-ai-config stores config in state and returns it", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["setup-ai-config"], {
    key: "my-bot",
    name: "My Bot",
    mode: "agent",
    variationKey: "v1",
    variationName: "V1",
    modelConfigKey: "Anthropic.claude-sonnet-4-6",
    modelName: "claude-sonnet-4-6",
    instructions: "Be helpful.",
  }, "setup-ai-config", state);

  assert.equal(result.key, "my-bot");
  assert.equal(result.mode, "agent");
  assert.equal(state.configs["my-bot"].name, "My Bot");
  assert.equal(state.configs["my-bot"].variations.length, 1);
  assert.equal(state.configs["my-bot"].variations[0].instructions, "Be helpful.");
});

// ---------------------------------------------------------------------------
// create-ai-config (stateful write)
// ---------------------------------------------------------------------------

test("create-ai-config stores config with empty variations", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-ai-config"], {
    key: "new-config",
    name: "New Config",
    mode: "completion",
  }, "create-ai-config", state);

  assert.ok(state.configs["new-config"]);
  assert.deepEqual(state.configs["new-config"].variations, []);
});

// ---------------------------------------------------------------------------
// create-ai-config-variation
// ---------------------------------------------------------------------------

test("create-ai-config-variation appends to existing config", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-ai-config"], {
    key: "my-config", name: "My Config", mode: "agent",
  }, "create-ai-config", state);

  renderMockResponse(TEMPLATES["create-ai-config-variation"], {
    configKey: "my-config",
    key: "v1",
    name: "Variation 1",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
    instructions: "Help the user.",
  }, "create-ai-config-variation", state);

  assert.equal(state.configs["my-config"].variations.length, 1);
  assert.equal(state.configs["my-config"].variations[0].key, "v1");
});

test("create-ai-config-variation creates stub when parent config missing", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-ai-config-variation"], {
    configKey: "orphan-config",
    key: "v1",
    name: "V1",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
  }, "create-ai-config-variation", state);

  assert.ok(state.configs["orphan-config"], "stub config should be created");
  assert.equal(state.configs["orphan-config"].variations.length, 1);
});

// ---------------------------------------------------------------------------
// update-ai-config-variation
// ---------------------------------------------------------------------------

test("update-ai-config-variation patches only variation fields", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-ai-config"], {
    key: "bot",
    name: "Bot",
    mode: "agent",
    variationKey: "default",
    variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
    instructions: "Original.",
  }, "setup-ai-config", state);

  renderMockResponse(TEMPLATES["update-ai-config-variation"], {
    configKey: "bot",
    variationKey: "default",
    modelConfigKey: "OpenAI.gpt-4o-mini",
    modelName: "gpt-4o-mini",
  }, "update-ai-config-variation", state);

  const v = state.configs["bot"].variations[0];
  assert.equal(v.modelConfigKey, "OpenAI.gpt-4o-mini");
  assert.equal(v.modelName, "gpt-4o-mini");
  assert.equal(v.instructions, "Original."); // unchanged
  // input-only fields must NOT bleed into the variation
  assert.ok(!("configKey" in v), "configKey must not appear on variation");
  assert.ok(!("variationKey" in v), "variationKey must not appear on variation");
});

test("update-ai-config-variation is a no-op when config not in state", () => {
  const state = createMockState();
  // Should not throw
  assert.doesNotThrow(() =>
    renderMockResponse(TEMPLATES["update-ai-config-variation"], {
      configKey: "nonexistent",
      variationKey: "default",
      modelConfigKey: "OpenAI.gpt-4o-mini",
    }, "update-ai-config-variation", state)
  );
  assert.deepEqual(state.configs, {});
});

// ---------------------------------------------------------------------------
// get-ai-config (stateful read)
// ---------------------------------------------------------------------------

test("get-ai-config returns state config when present", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-ai-config"], {
    key: "bot", name: "Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
  }, "setup-ai-config", state);

  const result = renderMockResponse(TEMPLATES["get-ai-config"], {
    configKey: "bot",
  }, "get-ai-config", state);

  assert.equal(result.key, "bot");
  assert.equal(result.name, "Bot");
});

test("get-ai-config loads SEED_CONFIGS when key matches", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-ai-config"], {
    configKey: "support-chatbot",
  }, "get-ai-config", state);

  assert.equal(result.key, "support-chatbot");
  assert.ok(result.variations.length > 0);
  // seed should now be in state for subsequent calls
  assert.ok(state.configs["support-chatbot"]);
});

test("get-ai-config falls back to template for unknown key", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-ai-config"], {
    configKey: "mystery-config",
  }, "get-ai-config", state);

  assert.equal(result.key, "mystery-config"); // template substitution
});

// ---------------------------------------------------------------------------
// list-ai-configs (stateful merge)
// ---------------------------------------------------------------------------

test("list-ai-configs returns static list when state is empty", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["list-ai-configs"], {}, "list-ai-configs", state);
  assert.ok(result.configs.length > 0);
});

test("list-ai-configs merges state configs, state wins for duplicate keys", () => {
  const state = createMockState();
  // write over a seed key
  renderMockResponse(TEMPLATES["setup-ai-config"], {
    key: "support-chatbot",
    name: "My Custom Chatbot",
    mode: "completion",
    variationKey: "default",
    variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
  }, "setup-ai-config", state);

  const result = renderMockResponse(TEMPLATES["list-ai-configs"], {}, "list-ai-configs", state);
  const entry = result.configs.find((c) => c.key === "support-chatbot");
  assert.ok(entry, "support-chatbot should appear in list");
  assert.equal(entry.name, "My Custom Chatbot", "state entry should win over static template");
  // should appear exactly once
  const count = result.configs.filter((c) => c.key === "support-chatbot").length;
  assert.equal(count, 1);
});

test("list-ai-configs adds newly created configs not in static list", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-ai-config"], {
    key: "brand-new", name: "Brand New", mode: "agent",
  }, "create-ai-config", state);

  const result = renderMockResponse(TEMPLATES["list-ai-configs"], {}, "list-ai-configs", state);
  const entry = result.configs.find((c) => c.key === "brand-new");
  assert.ok(entry);
  assert.equal(result.totalCount, result.configs.length);
});

// ---------------------------------------------------------------------------
// get-ai-config-health
// ---------------------------------------------------------------------------

test("get-ai-config-health reflects state when config is present", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-ai-config"], {
    key: "bot", name: "Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
    instructions: "Be helpful.",
  }, "setup-ai-config", state);

  const health = renderMockResponse(TEMPLATES["get-ai-config-health"], {
    configKey: "bot",
  }, "get-ai-config-health", state);

  assert.equal(health.key, "bot");
  assert.equal(health.health, "healthy");
  assert.equal(health.variationsCount, 1);
  assert.equal(health.variations[0].hasModel, true);
  assert.equal(health.variations[0].hasPrompts, true);
});

test("get-ai-config-health falls back to template for unknown key", () => {
  const state = createMockState();
  const health = renderMockResponse(TEMPLATES["get-ai-config-health"], {
    configKey: "unknown-config",
  }, "get-ai-config-health", state);
  // template fallback — key should be substituted
  assert.equal(health.key, "unknown-config");
});

// ---------------------------------------------------------------------------
// clone-ai-config-variation
// ---------------------------------------------------------------------------

test("clone-ai-config-variation appends cloned variation to state", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-ai-config"], {
    key: "my-bot", name: "My Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
    instructions: "Original instructions.",
  }, "setup-ai-config", state);

  const result = renderMockResponse(TEMPLATES["clone-ai-config-variation"], {
    configKey: "my-bot",
    sourceVariationKey: "default",
    key: "cost-test",
    name: "Cost Test",
    modelConfigKey: "OpenAI.gpt-4o-mini",
    modelName: "gpt-4o-mini",
  }, "clone-ai-config-variation", state);

  assert.equal(result.created.key, "cost-test");
  assert.equal(result.created.modelConfigKey, "OpenAI.gpt-4o-mini");
  assert.equal(result.source.key, "default");
  assert.equal(state.configs["my-bot"].variations.length, 2);
  assert.equal(state.configs["my-bot"].variations[1].key, "cost-test");
});

test("clone-ai-config-variation reflects in subsequent get-ai-config", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-ai-config"], {
    key: "bot", name: "Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
    instructions: "Help.",
  }, "setup-ai-config", state);

  renderMockResponse(TEMPLATES["clone-ai-config-variation"], {
    configKey: "bot",
    sourceVariationKey: "default",
    key: "new-var",
    name: "New Variation",
  }, "clone-ai-config-variation", state);

  const cfg = renderMockResponse(TEMPLATES["get-ai-config"], {
    configKey: "bot",
  }, "get-ai-config", state);

  assert.equal(cfg.variations.length, 2);
  assert.ok(cfg.variations.find((v) => v.key === "new-var"), "cloned variation should appear in get-ai-config");
});

test("clone-ai-config-variation works with SEED_CONFIGS source", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["clone-ai-config-variation"], {
    configKey: "support-chatbot",
    sourceVariationKey: "default",
    key: "experimental",
    name: "Experimental",
  }, "clone-ai-config-variation", state);

  assert.equal(result.created.key, "experimental");
  assert.equal(result.source.key, "default");
  assert.ok(state.configs["support-chatbot"], "seed config should be loaded into state");
  assert.equal(state.configs["support-chatbot"].variations.length, 2);
});

test("clone-ai-config-variation falls back to template when source variation not found", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-ai-config"], {
    key: "my-config", name: "My Config", mode: "agent",
  }, "create-ai-config", state);

  // source variation doesn't exist — should fall back to template render, not throw
  assert.doesNotThrow(() =>
    renderMockResponse(TEMPLATES["clone-ai-config-variation"], {
      configKey: "my-config",
      sourceVariationKey: "nonexistent",
      key: "new-var",
      name: "New",
    }, "clone-ai-config-variation", state)
  );
});

// ---------------------------------------------------------------------------
// create-flag / get-flag (flag state)
// ---------------------------------------------------------------------------

test("create-flag stores flag in state", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-flag"], {
    key: "my-new-flag",
    name: "My New Flag",
  }, "create-flag", state);

  assert.ok(state.flags["my-new-flag"]);
});

test("get-flag returns state flag when present", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-flag"], {
    key: "my-flag",
    name: "My Flag",
  }, "create-flag", state);

  const result = renderMockResponse(TEMPLATES["get-flag"], {
    flagKey: "my-flag",
  }, "get-flag", state);

  assert.equal(result.key, "my-flag");
});

test("get-flag falls back to template substitution for unknown flag", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flag"], {
    flagKey: "unknown-flag",
    flagName: "Unknown Flag",
  }, "get-flag", state);
  assert.equal(result.key, "unknown-flag");
});

test("get-flag resolves the template fallthrough (variation 1) for a non-federal env", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flag"], {
    flagKey: "billing-v2",
    environmentKey: "production",
  }, "get-flag", state);
  assert.equal(result.environment.fallthrough.variation, 1); // -> false
});

test("get-flag returns the opposite fallthrough (variation 0) for a federal env", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flag"], {
    flagKey: "billing-v2",
    environmentKey: "federal",
  }, "get-flag", state);
  assert.equal(result.environment.fallthrough.variation, 0); // -> true (diverges)
});

// ---------------------------------------------------------------------------
// stateless template rendering ({{placeholder}} substitution)
// ---------------------------------------------------------------------------

test("template substitution fills {{configKey}} and {{configName}}", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["create-ai-config"], {
    key: "my-config",
    name: "My Config",
    mode: "completion",
  }, "create-ai-config", state);
  // result from stateful handler, not template — check state
  assert.equal(state.configs["my-config"].key, "my-config");
});

test("update-ai-config uses template substitution", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["update-ai-config"], {
    configKey: "bot",
    configName: "Bot",
  }, "update-ai-config", state);
  assert.equal(result.key, "bot");
  assert.equal(result.name, "Bot");
});

// ---------------------------------------------------------------------------
// experiment-setup sentinels
// ---------------------------------------------------------------------------

test("get-flag-status-across-envs defaults to active in test and production", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flag-status-across-envs"], {
    projectKey: "payments",
    flagKey: "billing-v2",
  }, "get-flag-status-across-envs", state);
  assert.deepEqual(
    result.environments.map((env) => [env.key, env.status]),
    [["test", "active"], ["production", "active"]],
  );
  assert.deepEqual(result.summary.active, ["test", "production"]);
  assert.deepEqual(result.summary.inactive, []);
  assert.equal(
    result.environments.some((env) => /federal/i.test(env.key)),
    false,
  );
});

test("get-flag-status-across-envs reports checkout-inactive as inactive in production", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flag-status-across-envs"], {
    projectKey: "mixed-contexts",
    flagKey: "checkout-inactive",
  }, "get-flag-status-across-envs", state);
  const production = result.environments.find((env) => env.key === "production");
  assert.equal(production.status, "inactive");
  assert.deepEqual(result.summary.inactive, ["production"]);
});

test("get-flag returns checkout-active on, serving one variation", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flag"], {
    projectKey: "only-user",
    flagKey: "checkout-active",
    environmentKey: "production",
  }, "get-flag", state);
  assert.equal(result.environment.on, true);
  assert.equal(result.environment.version, 7);
  assert.equal(result.environment.fallthrough.variation, 0);
  assert.equal(result.environment.fallthrough.rollout, undefined);
  assert.equal(result.variations[0].name, "Current checkout");
});

test("get-flag returns not-found for missing-checkout", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flag"], {
    projectKey: "my-project",
    flagKey: "missing-checkout",
  }, "get-flag", state);
  assert.equal(result.status, 404);
});

test("get-flag returns a stored flag before the missing-checkout not-found branch", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-flag"], {
    key: "missing-checkout",
    name: "Missing",
  }, "create-flag", state);
  const result = renderMockResponse(TEMPLATES["get-flag"], {
    flagKey: "missing-checkout",
  }, "get-flag", state);
  assert.equal(result.key, "missing-checkout");
  assert.equal(result.error, undefined);
});

test("list-flags query missing-checkout returns similar keys only", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["list-flags"], {
    projectKey: "my-project",
    query: "missing-checkout",
  }, "list-flags", state);
  const keys = result.flags.map((flag) => flag.key);
  assert.deepEqual(keys, ["checkout-flow", "new-checkout"]);
});

test("list-flags without that query keeps the shared flag list", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["list-flags"], {
    projectKey: "web-app",
    query: "search-v2",
  }, "list-flags", state);
  assert.deepEqual(
    result.flags.map((flag) => flag.key),
    ["enable-notifications", "search-v2"],
  );
});

test("search-contexts suggests user only when no other kind is stored", () => {
  const state = createMockState();
  const users = renderMockResponse(TEMPLATES["search-contexts"], {
    projectKey: "only-user",
    environmentKey: "production",
    kind: "user",
  }, "search-contexts", state);
  const others = renderMockResponse(TEMPLATES["search-contexts"], {
    projectKey: "only-user",
    environmentKey: "production",
    filter: 'kind notEquals "user"',
  }, "search-contexts", state);
  assert.equal(users.totalCount, 1);
  assert.equal(users.items[0].kind, "user");
  assert.equal(others.totalCount, 0);
});

test("search-contexts on mixed-contexts returns another kind", () => {
  const state = createMockState();
  const others = renderMockResponse(TEMPLATES["search-contexts"], {
    projectKey: "mixed-contexts",
    environmentKey: "production",
    filter: 'kind notEquals "user"',
  }, "search-contexts", state);
  assert.ok(others.totalCount > 0);
  assert.equal(others.items[0].kind, "organization");
});

test("list-metric-events default includes similar keys and omits cta-clicked", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["list-metric-events"], {
    projectKey: "my-project",
  }, "list-metric-events", state);
  const keys = result.events.map((event) => event.key);
  assert.deepEqual(keys, [
    "checkout-completed",
    "page-load-ms",
    "cta-click",
    "cta-clicked-v2",
  ]);
});

test("list-metric-events query cta-clicked returns similar keys only", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["list-metric-events"], {
    projectKey: "my-project",
    environmentKey: "production",
    query: "cta-clicked",
  }, "list-metric-events", state);
  assert.deepEqual(
    result.events.map((event) => event.key),
    ["cta-click", "cta-clicked-v2"],
  );
});

test("get-experiment returns a running iteration for checkout-running", () => {
  const state = createMockState();
  const running = renderMockResponse(TEMPLATES["get-experiment"], {
    projectKey: "my-project",
    environmentKey: "production",
    experimentKey: "checkout-running",
  }, "get-experiment", state);
  const draft = renderMockResponse(TEMPLATES["get-experiment"], {
    projectKey: "my-project",
    environmentKey: "production",
    experimentKey: "checkout-draft",
  }, "get-experiment", state);
  assert.equal(running.currentIteration.status, "running");
  assert.equal(draft.currentIteration.status, "not_started");
});
