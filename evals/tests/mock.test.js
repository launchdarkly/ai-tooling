const { test } = require("node:test");
const assert = require("node:assert/strict");

const { renderMockResponse, createMockState, templateKey } = require("../providers/_mock");

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
// setup-agent-config (stateful write)
// ---------------------------------------------------------------------------

test("setup-agent-config stores config in state and returns it", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["setup-agent-config"], {
    key: "my-bot",
    name: "My Bot",
    mode: "agent",
    variationKey: "v1",
    variationName: "V1",
    modelConfigKey: "Anthropic.claude-sonnet-4-6",
    modelName: "claude-sonnet-4-6",
    instructions: "Be helpful.",
  }, "setup-agent-config", state);

  assert.equal(result.key, "my-bot");
  assert.equal(result.mode, "agent");
  assert.equal(state.configs["my-bot"].name, "My Bot");
  assert.equal(state.configs["my-bot"].variations.length, 1);
  assert.equal(state.configs["my-bot"].variations[0].instructions, "Be helpful.");
});

// ---------------------------------------------------------------------------
// create-agent-config (stateful write)
// ---------------------------------------------------------------------------

test("create-agent-config stores config with empty variations", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agent-config"], {
    key: "new-config",
    name: "New Config",
    mode: "completion",
  }, "create-agent-config", state);

  assert.ok(state.configs["new-config"]);
  assert.deepEqual(state.configs["new-config"].variations, []);
});

// ---------------------------------------------------------------------------
// create-agent-config-variation
// ---------------------------------------------------------------------------

test("create-agent-config-variation appends to existing config", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agent-config"], {
    key: "my-config", name: "My Config", mode: "agent",
  }, "create-agent-config", state);

  renderMockResponse(TEMPLATES["create-agent-config-variation"], {
    configKey: "my-config",
    key: "v1",
    name: "Variation 1",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
    instructions: "Help the user.",
  }, "create-agent-config-variation", state);

  assert.equal(state.configs["my-config"].variations.length, 1);
  assert.equal(state.configs["my-config"].variations[0].key, "v1");
});

test("create-agent-config-variation creates stub when parent config missing", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agent-config-variation"], {
    configKey: "orphan-config",
    key: "v1",
    name: "V1",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
  }, "create-agent-config-variation", state);

  assert.ok(state.configs["orphan-config"], "stub config should be created");
  assert.equal(state.configs["orphan-config"].variations.length, 1);
});

// ---------------------------------------------------------------------------
// update-agent-config-variation
// ---------------------------------------------------------------------------

test("update-agent-config-variation patches only variation fields", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-agent-config"], {
    key: "bot",
    name: "Bot",
    mode: "agent",
    variationKey: "default",
    variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
    instructions: "Original.",
  }, "setup-agent-config", state);

  renderMockResponse(TEMPLATES["update-agent-config-variation"], {
    configKey: "bot",
    variationKey: "default",
    modelConfigKey: "OpenAI.gpt-4o-mini",
    modelName: "gpt-4o-mini",
  }, "update-agent-config-variation", state);

  const v = state.configs["bot"].variations[0];
  assert.equal(v.modelConfigKey, "OpenAI.gpt-4o-mini");
  assert.equal(v.modelName, "gpt-4o-mini");
  assert.equal(v.instructions, "Original."); // unchanged
  // input-only fields must NOT bleed into the variation
  assert.ok(!("configKey" in v), "configKey must not appear on variation");
  assert.ok(!("variationKey" in v), "variationKey must not appear on variation");
});

test("update-agent-config-variation is a no-op when config not in state", () => {
  const state = createMockState();
  // Should not throw
  assert.doesNotThrow(() =>
    renderMockResponse(TEMPLATES["update-agent-config-variation"], {
      configKey: "nonexistent",
      variationKey: "default",
      modelConfigKey: "OpenAI.gpt-4o-mini",
    }, "update-agent-config-variation", state)
  );
  assert.deepEqual(state.configs, {});
});

// ---------------------------------------------------------------------------
// get-agent-configs (stateful read)
// ---------------------------------------------------------------------------

test("get-agent-configs returns state config when present", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-agent-config"], {
    key: "bot", name: "Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
  }, "setup-agent-config", state);

  const result = renderMockResponse(TEMPLATES["get-agent-configs#configKey"], {
    configKey: "bot",
  }, "get-agent-configs", state);

  assert.equal(result.key, "bot");
  assert.equal(result.name, "Bot");
});

test("get-agent-configs loads SEED_CONFIGS when key matches", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-agent-configs#configKey"], {
    configKey: "support-chatbot",
  }, "get-agent-configs", state);

  assert.equal(result.key, "support-chatbot");
  assert.ok(result.variations.length > 0);
  // seed should now be in state for subsequent calls
  assert.ok(state.configs["support-chatbot"]);
});

test("get-agent-configs falls back to template for unknown key", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-agent-configs#configKey"], {
    configKey: "mystery-config",
  }, "get-agent-configs", state);

  assert.equal(result.key, "mystery-config"); // template substitution
});

// ---------------------------------------------------------------------------
// get-agent-configs (stateful merge)
// ---------------------------------------------------------------------------

test("get-agent-configs returns static list when state is empty", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-agent-configs"], {}, "get-agent-configs", state);
  assert.ok(result.configs.length > 0);
});

test("get-agent-configs merges state configs, state wins for duplicate keys", () => {
  const state = createMockState();
  // write over a seed key
  renderMockResponse(TEMPLATES["setup-agent-config"], {
    key: "support-chatbot",
    name: "My Custom Chatbot",
    mode: "completion",
    variationKey: "default",
    variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
  }, "setup-agent-config", state);

  const result = renderMockResponse(TEMPLATES["get-agent-configs"], {}, "get-agent-configs", state);
  const entry = result.configs.find((c) => c.key === "support-chatbot");
  assert.ok(entry, "support-chatbot should appear in list");
  assert.equal(entry.name, "My Custom Chatbot", "state entry should win over static template");
  // should appear exactly once
  const count = result.configs.filter((c) => c.key === "support-chatbot").length;
  assert.equal(count, 1);
});

test("get-agent-configs adds newly created configs not in static list", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agent-config"], {
    key: "brand-new", name: "Brand New", mode: "agent",
  }, "create-agent-config", state);

  const result = renderMockResponse(TEMPLATES["get-agent-configs"], {}, "get-agent-configs", state);
  const entry = result.configs.find((c) => c.key === "brand-new");
  assert.ok(entry);
  assert.equal(result.totalCount, result.configs.length);
});

// ---------------------------------------------------------------------------
// get-agent-configs
// ---------------------------------------------------------------------------

test("get-agent-configs reflects state when config is present", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-agent-config"], {
    key: "bot", name: "Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
    instructions: "Be helpful.",
  }, "setup-agent-config", state);

  const health = renderMockResponse(TEMPLATES["get-agent-configs#health"], {
    configKey: "bot",
    section: "health",
  }, "get-agent-configs", state);

  assert.equal(health.key, "bot");
  assert.equal(health.health, "healthy");
  assert.equal(health.variationsCount, 1);
  assert.equal(health.variations[0].hasModel, true);
  assert.equal(health.variations[0].hasPrompts, true);
});

test("get-agent-configs falls back to template for unknown key", () => {
  const state = createMockState();
  const health = renderMockResponse(TEMPLATES["get-agent-configs#health"], {
    configKey: "unknown-config",
    section: "health",
  }, "get-agent-configs", state);
  // template fallback — key should be substituted
  assert.equal(health.key, "unknown-config");
});

// ---------------------------------------------------------------------------
// create-agent-config-variation
// ---------------------------------------------------------------------------

test("create-agent-config-variation appends cloned variation to state", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-agent-config"], {
    key: "my-bot", name: "My Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
    instructions: "Original instructions.",
  }, "setup-agent-config", state);

  const result = renderMockResponse(TEMPLATES["create-agent-config-variation#clone"], {
    configKey: "my-bot",
    sourceVariationKey: "default",
    key: "cost-test",
    name: "Cost Test",
    modelConfigKey: "OpenAI.gpt-4o-mini",
    modelName: "gpt-4o-mini",
  }, "create-agent-config-variation", state);

  assert.equal(result.created.key, "cost-test");
  assert.equal(result.created.modelConfigKey, "OpenAI.gpt-4o-mini");
  assert.equal(result.source.key, "default");
  assert.equal(state.configs["my-bot"].variations.length, 2);
  assert.equal(state.configs["my-bot"].variations[1].key, "cost-test");
});

test("create-agent-config-variation reflects in subsequent get-agent-configs", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["setup-agent-config"], {
    key: "bot", name: "Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
    instructions: "Help.",
  }, "setup-agent-config", state);

  renderMockResponse(TEMPLATES["create-agent-config-variation#clone"], {
    configKey: "bot",
    sourceVariationKey: "default",
    key: "new-var",
    name: "New Variation",
  }, "create-agent-config-variation", state);

  const cfg = renderMockResponse(TEMPLATES["get-agent-configs#configKey"], {
    configKey: "bot",
  }, "get-agent-configs", state);

  assert.equal(cfg.variations.length, 2);
  assert.ok(cfg.variations.find((v) => v.key === "new-var"), "cloned variation should appear in get-agent-configs");
});

test("create-agent-config-variation works with SEED_CONFIGS source", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["create-agent-config-variation#clone"], {
    configKey: "support-chatbot",
    sourceVariationKey: "default",
    key: "experimental",
    name: "Experimental",
  }, "create-agent-config-variation", state);

  assert.equal(result.created.key, "experimental");
  assert.equal(result.source.key, "default");
  assert.ok(state.configs["support-chatbot"], "seed config should be loaded into state");
  assert.equal(state.configs["support-chatbot"].variations.length, 2);
});

test("create-agent-config-variation falls back to template when source variation not found", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agent-config"], {
    key: "my-config", name: "My Config", mode: "agent",
  }, "create-agent-config", state);

  // source variation doesn't exist — should fall back to template render, not throw
  assert.doesNotThrow(() =>
    renderMockResponse(TEMPLATES["create-agent-config-variation#clone"], {
      configKey: "my-config",
      sourceVariationKey: "nonexistent",
      key: "new-var",
      name: "New",
    }, "create-agent-config-variation", state)
  );
});

// ---------------------------------------------------------------------------
// create-flag / get-flags (flag state)
// ---------------------------------------------------------------------------

test("create-flag stores flag in state", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-flag"], {
    key: "my-new-flag",
    name: "My New Flag",
  }, "create-flag", state);

  assert.ok(state.flags["my-new-flag"]);
});

test("get-flags returns state flag when present", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-flag"], {
    key: "my-flag",
    name: "My Flag",
  }, "create-flag", state);

  const result = renderMockResponse(TEMPLATES["get-flags#flagKey"], {
    flagKey: "my-flag",
  }, "get-flags", state);

  assert.equal(result.key, "my-flag");
});

test("get-flags falls back to template substitution for unknown flag", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flags#flagKey"], {
    flagKey: "unknown-flag",
    flagName: "Unknown Flag",
  }, "get-flags", state);
  assert.equal(result.key, "unknown-flag");
});

test("get-flags resolves the template fallthrough (variation 1) for a non-federal env", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flags#flagKey"], {
    flagKey: "billing-v2",
    environmentKey: "production",
  }, "get-flags", state);
  assert.equal(result.environment.fallthrough.variation, 1); // -> false
});

test("get-flags returns the opposite fallthrough (variation 0) for a federal env", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flags#flagKey"], {
    flagKey: "billing-v2",
    environmentKey: "federal",
  }, "get-flags", state);
  assert.equal(result.environment.fallthrough.variation, 0); // -> true (diverges)
});

// ---------------------------------------------------------------------------
// stateless template rendering ({{placeholder}} substitution)
// ---------------------------------------------------------------------------

test("template substitution fills {{configKey}} and {{configName}}", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["create-agent-config"], {
    key: "my-config",
    name: "My Config",
    mode: "completion",
  }, "create-agent-config", state);
  // result from stateful handler, not template — check state
  assert.equal(state.configs["my-config"].key, "my-config");
});

test("update-agent-config uses template substitution", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["update-agent-config"], {
    configKey: "bot",
    configName: "Bot",
  }, "update-agent-config", state);
  assert.equal(result.key, "bot");
  assert.equal(result.name, "Bot");
});

// ---------------------------------------------------------------------------
// templateKey
// ---------------------------------------------------------------------------

test("templateKey picks the single-item template when a key is passed", () => {
  assert.equal(templateKey("get-flags", {}), "get-flags");
  assert.equal(templateKey("get-flags", { flagKey: "f" }), "get-flags#flagKey");
  assert.equal(templateKey("get-agent-configs", { configKey: "c" }), "get-agent-configs#configKey");
  assert.equal(templateKey("get-agent-configs", { configKey: "c", section: "health" }), "get-agent-configs#health");
  assert.equal(templateKey("create-agent-config-variation", { sourceVariationKey: "v" }), "create-agent-config-variation#clone");
  assert.equal(templateKey("toggle-flag", { flagKey: "f" }), "toggle-flag");
});

test("every templateKey mode has a template", () => {
  const modes = [
    ["get-flags", { flagKey: "f" }],
    ["get-agent-configs", { configKey: "c" }],
    ["get-agent-configs", { configKey: "c", section: "health" }],
    ["get-ai-tools", { toolKey: "t" }],
    ["get-projects", { projectKey: "p" }],
    ["get-experiments", { experimentKey: "e" }],
    ["create-agent-config-variation", { sourceVariationKey: "v" }],
  ];
  for (const [tool, input] of modes) {
    assert.ok(TEMPLATES[templateKey(tool, input)], `${tool} ${JSON.stringify(input)}`);
  }
});
