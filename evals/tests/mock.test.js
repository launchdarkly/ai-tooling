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
  assert.deepEqual(a, { configs: {}, flags: {}, raSettings: null, raRepos: {}, raPlans: {} });
  a.configs["x"] = {};
  assert.deepEqual(b.configs, {}); // independent
});

// ---------------------------------------------------------------------------
// setup-agentcontrol-config (stateful write)
// ---------------------------------------------------------------------------

test("setup-agentcontrol-config stores config in state and returns it", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["setup-agentcontrol-config"], {
    key: "my-bot",
    name: "My Bot",
    mode: "agent",
    variationKey: "v1",
    variationName: "V1",
    modelConfigKey: "Anthropic.claude-sonnet-4-6",
    modelName: "claude-sonnet-4-6",
    instructions: "Be helpful.",
  }, "setup-agentcontrol-config", state);

  assert.equal(result.key, "my-bot");
  assert.equal(result.mode, "agent");
  assert.equal(state.configs["my-bot"].name, "My Bot");
  assert.equal(state.configs["my-bot"].variations.length, 1);
  assert.equal(state.configs["my-bot"].variations[0].instructions, "Be helpful.");
});

// ---------------------------------------------------------------------------
// create-agentcontrol-config (stateful write)
// ---------------------------------------------------------------------------

test("create-agentcontrol-config stores config with empty variations", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agentcontrol-config"], {
    key: "new-config",
    name: "New Config",
    mode: "completion",
  }, "create-agentcontrol-config", state);

  assert.ok(state.configs["new-config"]);
  assert.deepEqual(state.configs["new-config"].variations, []);
});

// ---------------------------------------------------------------------------
// create-agentcontrol-config-variation
// ---------------------------------------------------------------------------

test("create-agentcontrol-config-variation appends to existing config", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agentcontrol-config"], {
    key: "my-config", name: "My Config", mode: "agent",
  }, "create-agentcontrol-config", state);

  renderMockResponse(TEMPLATES["create-agentcontrol-config-variation"], {
    configKey: "my-config",
    key: "v1",
    name: "Variation 1",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
    instructions: "Help the user.",
  }, "create-agentcontrol-config-variation", state);

  assert.equal(state.configs["my-config"].variations.length, 1);
  assert.equal(state.configs["my-config"].variations[0].key, "v1");
});

test("create-agentcontrol-config-variation creates stub when parent config missing", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agentcontrol-config-variation"], {
    configKey: "orphan-config",
    key: "v1",
    name: "V1",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
  }, "create-agentcontrol-config-variation", state);

  assert.ok(state.configs["orphan-config"], "stub config should be created");
  assert.equal(state.configs["orphan-config"].variations.length, 1);
});

// ---------------------------------------------------------------------------
// update-agentcontrol-config-variation
// ---------------------------------------------------------------------------

test("update-agentcontrol-config-variation patches only variation fields", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-agentcontrol-config"], {
    key: "bot",
    name: "Bot",
    mode: "agent",
    variationKey: "default",
    variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
    instructions: "Original.",
  }, "setup-agentcontrol-config", state);

  renderMockResponse(TEMPLATES["update-agentcontrol-config-variation"], {
    configKey: "bot",
    variationKey: "default",
    modelConfigKey: "OpenAI.gpt-4o-mini",
    modelName: "gpt-4o-mini",
  }, "update-agentcontrol-config-variation", state);

  const v = state.configs["bot"].variations[0];
  assert.equal(v.modelConfigKey, "OpenAI.gpt-4o-mini");
  assert.equal(v.modelName, "gpt-4o-mini");
  assert.equal(v.instructions, "Original."); // unchanged
  // input-only fields must NOT bleed into the variation
  assert.ok(!("configKey" in v), "configKey must not appear on variation");
  assert.ok(!("variationKey" in v), "variationKey must not appear on variation");
});

test("update-agentcontrol-config-variation is a no-op when config not in state", () => {
  const state = createMockState();
  // Should not throw
  assert.doesNotThrow(() =>
    renderMockResponse(TEMPLATES["update-agentcontrol-config-variation"], {
      configKey: "nonexistent",
      variationKey: "default",
      modelConfigKey: "OpenAI.gpt-4o-mini",
    }, "update-agentcontrol-config-variation", state)
  );
  assert.deepEqual(state.configs, {});
});

// ---------------------------------------------------------------------------
// get-agentcontrol-config (stateful read)
// ---------------------------------------------------------------------------

test("get-agentcontrol-config returns state config when present", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-agentcontrol-config"], {
    key: "bot", name: "Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
  }, "setup-agentcontrol-config", state);

  const result = renderMockResponse(TEMPLATES["get-agentcontrol-config"], {
    configKey: "bot",
  }, "get-agentcontrol-config", state);

  assert.equal(result.key, "bot");
  assert.equal(result.name, "Bot");
});

test("get-agentcontrol-config loads SEED_CONFIGS when key matches", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-agentcontrol-config"], {
    configKey: "support-chatbot",
  }, "get-agentcontrol-config", state);

  assert.equal(result.key, "support-chatbot");
  assert.ok(result.variations.length > 0);
  // seed should now be in state for subsequent calls
  assert.ok(state.configs["support-chatbot"]);
});

test("get-agentcontrol-config falls back to template for unknown key", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-agentcontrol-config"], {
    configKey: "mystery-config",
  }, "get-agentcontrol-config", state);

  assert.equal(result.key, "mystery-config"); // template substitution
});

// ---------------------------------------------------------------------------
// list-agentcontrol-configs (stateful merge)
// ---------------------------------------------------------------------------

test("list-agentcontrol-configs returns static list when state is empty", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["list-agentcontrol-configs"], {}, "list-agentcontrol-configs", state);
  assert.ok(result.configs.length > 0);
});

test("list-agentcontrol-configs merges state configs, state wins for duplicate keys", () => {
  const state = createMockState();
  // write over a seed key
  renderMockResponse(TEMPLATES["setup-agentcontrol-config"], {
    key: "support-chatbot",
    name: "My Custom Chatbot",
    mode: "completion",
    variationKey: "default",
    variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
  }, "setup-agentcontrol-config", state);

  const result = renderMockResponse(TEMPLATES["list-agentcontrol-configs"], {}, "list-agentcontrol-configs", state);
  const entry = result.configs.find((c) => c.key === "support-chatbot");
  assert.ok(entry, "support-chatbot should appear in list");
  assert.equal(entry.name, "My Custom Chatbot", "state entry should win over static template");
  // should appear exactly once
  const count = result.configs.filter((c) => c.key === "support-chatbot").length;
  assert.equal(count, 1);
});

test("list-agentcontrol-configs adds newly created configs not in static list", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agentcontrol-config"], {
    key: "brand-new", name: "Brand New", mode: "agent",
  }, "create-agentcontrol-config", state);

  const result = renderMockResponse(TEMPLATES["list-agentcontrol-configs"], {}, "list-agentcontrol-configs", state);
  const entry = result.configs.find((c) => c.key === "brand-new");
  assert.ok(entry);
  assert.equal(result.totalCount, result.configs.length);
});

// ---------------------------------------------------------------------------
// get-agentcontrol-config-health
// ---------------------------------------------------------------------------

test("get-agentcontrol-config-health reflects state when config is present", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-agentcontrol-config"], {
    key: "bot", name: "Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
    instructions: "Be helpful.",
  }, "setup-agentcontrol-config", state);

  const health = renderMockResponse(TEMPLATES["get-agentcontrol-config-health"], {
    configKey: "bot",
  }, "get-agentcontrol-config-health", state);

  assert.equal(health.key, "bot");
  assert.equal(health.health, "healthy");
  assert.equal(health.variationsCount, 1);
  assert.equal(health.variations[0].hasModel, true);
  assert.equal(health.variations[0].hasPrompts, true);
});

test("get-agentcontrol-config-health falls back to template for unknown key", () => {
  const state = createMockState();
  const health = renderMockResponse(TEMPLATES["get-agentcontrol-config-health"], {
    configKey: "unknown-config",
  }, "get-agentcontrol-config-health", state);
  // template fallback — key should be substituted
  assert.equal(health.key, "unknown-config");
});

// ---------------------------------------------------------------------------
// clone-agentcontrol-config-variation
// ---------------------------------------------------------------------------

test("clone-agentcontrol-config-variation appends cloned variation to state", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-agentcontrol-config"], {
    key: "my-bot", name: "My Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
    instructions: "Original instructions.",
  }, "setup-agentcontrol-config", state);

  const result = renderMockResponse(TEMPLATES["clone-agentcontrol-config-variation"], {
    configKey: "my-bot",
    sourceVariationKey: "default",
    key: "cost-test",
    name: "Cost Test",
    modelConfigKey: "OpenAI.gpt-4o-mini",
    modelName: "gpt-4o-mini",
  }, "clone-agentcontrol-config-variation", state);

  assert.equal(result.created.key, "cost-test");
  assert.equal(result.created.modelConfigKey, "OpenAI.gpt-4o-mini");
  assert.equal(result.source.key, "default");
  assert.equal(state.configs["my-bot"].variations.length, 2);
  assert.equal(state.configs["my-bot"].variations[1].key, "cost-test");
});

test("clone-agentcontrol-config-variation reflects in subsequent get-agentcontrol-config", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-agentcontrol-config"], {
    key: "bot", name: "Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
    instructions: "Help.",
  }, "setup-agentcontrol-config", state);

  renderMockResponse(TEMPLATES["clone-agentcontrol-config-variation"], {
    configKey: "bot",
    sourceVariationKey: "default",
    key: "new-var",
    name: "New Variation",
  }, "clone-agentcontrol-config-variation", state);

  const cfg = renderMockResponse(TEMPLATES["get-agentcontrol-config"], {
    configKey: "bot",
  }, "get-agentcontrol-config", state);

  assert.equal(cfg.variations.length, 2);
  assert.ok(cfg.variations.find((v) => v.key === "new-var"), "cloned variation should appear in get-agentcontrol-config");
});

test("clone-agentcontrol-config-variation works with SEED_CONFIGS source", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["clone-agentcontrol-config-variation"], {
    configKey: "support-chatbot",
    sourceVariationKey: "default",
    key: "experimental",
    name: "Experimental",
  }, "clone-agentcontrol-config-variation", state);

  assert.equal(result.created.key, "experimental");
  assert.equal(result.source.key, "default");
  assert.ok(state.configs["support-chatbot"], "seed config should be loaded into state");
  assert.equal(state.configs["support-chatbot"].variations.length, 2);
});

test("clone-agentcontrol-config-variation falls back to template when source variation not found", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agentcontrol-config"], {
    key: "my-config", name: "My Config", mode: "agent",
  }, "create-agentcontrol-config", state);

  // source variation doesn't exist — should fall back to template render, not throw
  assert.doesNotThrow(() =>
    renderMockResponse(TEMPLATES["clone-agentcontrol-config-variation"], {
      configKey: "my-config",
      sourceVariationKey: "nonexistent",
      key: "new-var",
      name: "New",
    }, "clone-agentcontrol-config-variation", state)
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
  const result = renderMockResponse(TEMPLATES["create-agentcontrol-config"], {
    key: "my-config",
    name: "My Config",
    mode: "completion",
  }, "create-agentcontrol-config", state);
  // result from stateful handler, not template — check state
  assert.equal(state.configs["my-config"].key, "my-config");
});

test("update-agentcontrol-config uses template substitution", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["update-agentcontrol-config"], {
    configKey: "bot",
    configName: "Bot",
  }, "update-agentcontrol-config", state);
  assert.equal(result.key, "bot");
  assert.equal(result.name, "Bot");
});

// ---------------------------------------------------------------------------
// Release Autopilot stateful reads (templates from the suite's own mocks)

const RA_TEMPLATES = require("../release-autopilot-onboarding/tool-mocks.json");
// ---------------------------------------------------------------------------

test("repo settings read reflects an earlier repo write", () => {
  const state = createMockState();
  const tpl = RA_TEMPLATES["get-release-autopilot-repo-settings"];
  assert.ok(renderMockResponse(tpl, { repo: "acme/demo" }, "get-release-autopilot-repo-settings", state).error);
  renderMockResponse(RA_TEMPLATES["update-release-autopilot-repo-settings"], { repo: "acme/demo", projectKey: "default", autoReleasing: { enabled: false } }, "update-release-autopilot-repo-settings", state);
  const got = renderMockResponse(tpl, { repo: "acme/demo" }, "get-release-autopilot-repo-settings", state);
  assert.equal(got.projectKey, "default");
  assert.equal(got.autoReleasing.enabled, false);
});

test("account settings read merges an earlier account write", () => {
  const state = createMockState();
  renderMockResponse(RA_TEMPLATES["update-release-autopilot-settings"], { autoFlagging: { enabled: false } }, "update-release-autopilot-settings", state);
  const got = renderMockResponse(RA_TEMPLATES["get-release-autopilot-settings"], {}, "get-release-autopilot-settings", state);
  assert.equal(got.autoFlagging.enabled, false);
  assert.equal(got.autoFlagging.approvalRequired, true);
});

test("release plans list reflects a created plan", () => {
  const state = createMockState();
  renderMockResponse(RA_TEMPLATES["create-release-plan"], { projectKey: "default", environmentKey: "production", key: "p", name: "P", progressiveRelease: { phases: [] } }, "create-release-plan", state);
  const got = renderMockResponse(RA_TEMPLATES["list-release-plans"], { projectKey: "default", environmentKey: "production" }, "list-release-plans", state);
  assert.equal(got.totalCount, 1);
  assert.equal(got.items[0].key, "p");
});

test("an error template wins over the stateful write and is not recorded", () => {
  const state = createMockState();
  const err = { error: "403: denied" };
  assert.equal(renderMockResponse(err, { autoFlagging: { enabled: true } }, "update-release-autopilot-settings", state).error, "403: denied");
  assert.equal(state.raSettings, null);
});
