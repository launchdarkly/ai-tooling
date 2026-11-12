const { test } = require("node:test");
const assert = require("node:assert/strict");

const { renderMockResponse, createMockState, templateKey } = require("../providers/_mock");

const TEMPLATES = require("../mocks/tool-responses.json");
// These four tools' default templates live with the experiment-setup suite.
// The sentinel branches in _mock.js still override them.
const SUITE_TEMPLATES = require("../experiment-setup/mocks.json");
const ORCH_TEMPLATES = require("../experiment-orchestration/mocks.json");

// ---------------------------------------------------------------------------
// createMockState
// ---------------------------------------------------------------------------

test("createMockState returns fresh empty state each call", () => {
  const a = createMockState();
  const b = createMockState();
  assert.deepEqual(a, { configs: {}, flags: {}, targeting: {}, raSettings: null, raRepos: {}, raPlans: {}, raDefaults: {}, raCleanup: {}, raArchival: {} });
  a.configs["x"] = {};
  assert.deepEqual(b.configs, {}); // independent
});

// ---------------------------------------------------------------------------
// create-agent-config with a first variation (stateful write)
// ---------------------------------------------------------------------------

test("create-agent-config with a first variation stores config in state and returns it", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["create-agent-config#with-variation"], {
    resource: "config",
    configKey: "my-bot",
    name: "My Bot",
    mode: "agent",
    variationKey: "v1",
    variationName: "V1",
    modelConfigKey: "Anthropic.claude-sonnet-4-6",
    modelName: "claude-sonnet-4-6",
    instructions: "Be helpful.",
  }, "create-agent-config", state);

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
    resource: "config",
    configKey: "new-config",
    name: "New Config",
    mode: "completion",
  }, "create-agent-config", state);

  assert.ok(state.configs["new-config"]);
  assert.deepEqual(state.configs["new-config"].variations, []);
});

// ---------------------------------------------------------------------------
// create-agent-config resource=variation
// ---------------------------------------------------------------------------

test("create-agent-config resource=variation appends to existing config", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agent-config"], {
    resource: "config",
    configKey: "my-config", name: "My Config", mode: "agent",
  }, "create-agent-config", state);

  renderMockResponse(TEMPLATES["create-agent-config#variation"], {
    resource: "variation",
    configKey: "my-config",
    variationKey: "v1",
    variationName: "Variation 1",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
    instructions: "Help the user.",
  }, "create-agent-config", state);

  assert.equal(state.configs["my-config"].variations.length, 1);
  assert.equal(state.configs["my-config"].variations[0].key, "v1");
});

test("create-agent-config resource=variation creates stub when parent config missing", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agent-config#variation"], {
    resource: "variation",
    configKey: "orphan-config",
    variationKey: "v1",
    variationName: "V1",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
  }, "create-agent-config", state);

  assert.ok(state.configs["orphan-config"], "stub config should be created");
  assert.equal(state.configs["orphan-config"].variations.length, 1);
});

// ---------------------------------------------------------------------------
// update-agent-config resource=variation
// ---------------------------------------------------------------------------

test("update-agent-config resource=variation patches only variation fields", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agent-config#with-variation"], {
    resource: "config",
    configKey: "bot",
    name: "Bot",
    mode: "agent",
    variationKey: "default",
    variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
    instructions: "Original.",
  }, "create-agent-config", state);

  renderMockResponse(TEMPLATES["update-agent-config#variation"], {
    resource: "variation",
    configKey: "bot",
    variationKey: "default",
    modelConfigKey: "OpenAI.gpt-4o-mini",
    modelName: "gpt-4o-mini",
  }, "update-agent-config", state);

  const v = state.configs["bot"].variations[0];
  assert.equal(v.modelConfigKey, "OpenAI.gpt-4o-mini");
  assert.equal(v.modelName, "gpt-4o-mini");
  assert.equal(v.instructions, "Original."); // unchanged
  // input-only fields must NOT bleed into the variation
  assert.ok(!("configKey" in v), "configKey must not appear on variation");
  assert.ok(!("variationKey" in v), "variationKey must not appear on variation");
});

test("update-agent-config resource=variation is a no-op when config not in state", () => {
  const state = createMockState();
  // Should not throw
  assert.doesNotThrow(() =>
    renderMockResponse(TEMPLATES["update-agent-config#variation"], {
      resource: "variation",
      configKey: "nonexistent",
      variationKey: "default",
      modelConfigKey: "OpenAI.gpt-4o-mini",
    }, "update-agent-config", state)
  );
  assert.deepEqual(state.configs, {});
});

// ---------------------------------------------------------------------------
// get-agent-configs (stateful read)
// ---------------------------------------------------------------------------

test("get-agent-configs returns state config when present", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agent-config#with-variation"], {
    resource: "config",
    configKey: "bot", name: "Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
  }, "create-agent-config", state);

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
  renderMockResponse(TEMPLATES["create-agent-config#with-variation"], {
    resource: "config",
    configKey: "support-chatbot",
    name: "My Custom Chatbot",
    mode: "completion",
    variationKey: "default",
    variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o",
    modelName: "gpt-4o",
  }, "create-agent-config", state);

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
    resource: "config",
    configKey: "brand-new", name: "Brand New", mode: "agent",
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
  renderMockResponse(TEMPLATES["create-agent-config#with-variation"], {
    resource: "config",
    configKey: "bot", name: "Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
    instructions: "Be helpful.",
  }, "create-agent-config", state);

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
// create-agent-config resource=variation
// ---------------------------------------------------------------------------

test("create-agent-config resource=variation appends cloned variation to state", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agent-config#with-variation"], {
    resource: "config",
    configKey: "my-bot", name: "My Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
    instructions: "Original instructions.",
  }, "create-agent-config", state);

  const result = renderMockResponse(TEMPLATES["create-agent-config#variation-clone"], {
    resource: "variation",
    configKey: "my-bot",
    sourceVariationKey: "default",
    variationKey: "cost-test",
    variationName: "Cost Test",
    modelConfigKey: "OpenAI.gpt-4o-mini",
    modelName: "gpt-4o-mini",
  }, "create-agent-config", state);

  assert.equal(result.created.key, "cost-test");
  assert.equal(result.created.modelConfigKey, "OpenAI.gpt-4o-mini");
  assert.equal(result.source.key, "default");
  assert.equal(state.configs["my-bot"].variations.length, 2);
  assert.equal(state.configs["my-bot"].variations[1].key, "cost-test");
});

test("create-agent-config resource=variation reflects in subsequent get-agent-configs", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agent-config#with-variation"], {
    resource: "config",
    configKey: "bot", name: "Bot", mode: "agent",
    variationKey: "default", variationName: "Default",
    modelConfigKey: "OpenAI.gpt-4o", modelName: "gpt-4o",
    instructions: "Help.",
  }, "create-agent-config", state);

  renderMockResponse(TEMPLATES["create-agent-config#variation-clone"], {
    resource: "variation",
    configKey: "bot",
    sourceVariationKey: "default",
    variationKey: "new-var",
    variationName: "New Variation",
  }, "create-agent-config", state);

  const cfg = renderMockResponse(TEMPLATES["get-agent-configs#configKey"], {
    configKey: "bot",
  }, "get-agent-configs", state);

  assert.equal(cfg.variations.length, 2);
  assert.ok(cfg.variations.find((v) => v.key === "new-var"), "cloned variation should appear in get-agent-configs");
});

test("create-agent-config resource=variation works with SEED_CONFIGS source", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["create-agent-config#variation-clone"], {
    resource: "variation",
    configKey: "support-chatbot",
    sourceVariationKey: "default",
    variationKey: "experimental",
    variationName: "Experimental",
  }, "create-agent-config", state);

  assert.equal(result.created.key, "experimental");
  assert.equal(result.source.key, "default");
  assert.ok(state.configs["support-chatbot"], "seed config should be loaded into state");
  assert.equal(state.configs["support-chatbot"].variations.length, 2);
});

test("create-agent-config resource=variation falls back to template when source variation not found", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-agent-config"], {
    resource: "config",
    configKey: "my-config", name: "My Config", mode: "agent",
  }, "create-agent-config", state);

  // source variation doesn't exist — should fall back to template render, not throw
  assert.doesNotThrow(() =>
    renderMockResponse(TEMPLATES["create-agent-config#variation-clone"], {
      resource: "variation",
      configKey: "my-config",
      sourceVariationKey: "nonexistent",
      variationKey: "new-var",
      variationName: "New",
    }, "create-agent-config", state)
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
    resource: "config",
    configKey: "my-config",
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

test("update-agent-config rejects archived like the server and leaves state alone", () => {
  const state = createMockState();
  state.configs["bot"] = { key: "bot", name: "Bot", tags: [] };
  const result = renderMockResponse(TEMPLATES["update-agent-config"], {
    resource: "config",
    configKey: "bot",
    archived: true,
  }, "update-agent-config", state);
  assert.equal(result.status, 400);
  assert.match(result.message, /cannot be archived/);
  assert.equal(state.configs["bot"].archived, undefined);
});

test("update-agent-config resource=config stores maintainer and default variation", () => {
  const state = createMockState();
  state.configs["bot"] = { key: "bot", name: "Bot", tags: [] };
  const result = renderMockResponse(TEMPLATES["update-agent-config"], {
    resource: "config",
    configKey: "bot",
    maintainerTeamKey: "ai-team",
    defaultVariationKey: "candidate",
  }, "update-agent-config", state);
  assert.equal(result.maintainerTeamKey, "ai-team");
  assert.equal(result.defaultVariationKey, "candidate");
});

test("get-agent-configs section=status has a template with per-environment state", () => {
  assert.equal(templateKey("get-agent-configs", { configKey: "c", section: "status" }), "get-agent-configs#status");
  const result = renderMockResponse(TEMPLATES["get-agent-configs#status"], { configKey: "bot" }, "get-agent-configs", createMockState());
  assert.equal(result.configKey, "bot");
  assert.deepEqual(Object.keys(result.environments).sort(), ["production", "staging"]);
});

// ---------------------------------------------------------------------------
// templateKey
// ---------------------------------------------------------------------------

test("templateKey picks the single-item template when a key is passed", () => {
  assert.equal(templateKey("get-flags", {}), "get-flags");
  assert.equal(templateKey("get-flags", { flagKey: "f" }), "get-flags#flagKey");
  assert.equal(templateKey("get-agent-configs", { configKey: "c" }), "get-agent-configs#configKey");
  assert.equal(templateKey("get-agent-configs", { configKey: "c", section: "health" }), "get-agent-configs#health");
  assert.equal(templateKey("create-agent-config", { resource: "variation", variationKey: "n", sourceVariationKey: "v" }), "create-agent-config#variation-clone");
  assert.equal(templateKey("create-agent-config", { resource: "variation", variationKey: "n" }), "create-agent-config#variation");
  assert.equal(templateKey("create-agent-config", { resource: "config", variationKey: "n" }), "create-agent-config#with-variation");
  assert.equal(templateKey("update-agent-config", { resource: "targeting" }), "update-agent-config#targeting");
  assert.equal(templateKey("delete-agent-config", { resource: "variation" }), "delete-agent-config#variation");
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
    ["create-agent-config", { resource: "variation", sourceVariationKey: "v" }],
    ["create-agent-config", { resource: "variation" }],
    ["create-agent-config", { resource: "config", variationKey: "v" }],
    ["update-agent-config", { resource: "variation" }],
    ["update-agent-config", { resource: "targeting" }],
    ["delete-agent-config", { resource: "variation" }],
  ];
  for (const [tool, input] of modes) {
    assert.ok(TEMPLATES[templateKey(tool, input)], `${tool} ${JSON.stringify(input)}`);
  }
});

test("every tool definition has a mock template", () => {
  for (const def of require("../tools/definitions.json")) {
    assert.ok(TEMPLATES[def.name], def.name);
  }
});

test("create-project echoes the new project's key and name", () => {
  const result = renderMockResponse(TEMPLATES["create-project"], { key: "agents", name: "Agents" }, "create-project", createMockState());
  assert.equal(result.key, "agents");
  assert.equal(result.name, "Agents");
});

test("update-agent-config targeting echoes the fallthrough variation key", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["update-agent-config#targeting"], {
    resource: "targeting",
    configKey: "bot",
    env: "production",
    fallthrough: { variationKey: "candidate" },
    confirm: true,
  }, "update-agent-config", state);
  assert.equal(result.fallthrough.variationKey, "candidate");
});

// ---------------------------------------------------------------------------
// experiment-setup sentinels
// ---------------------------------------------------------------------------

test("experiment-setup suite files own the three tools the shared catalog does not have", () => {
  const sharedDefs = require("../tools/definitions.json").map((def) => def.name);
  const suiteDefs = require("../experiment-setup/tools.json").map((def) => def.name);
  const owned = [
    "get-metric-events",
    "search-contexts",
    "save-and-start-experiment-iteration",
  ];
  for (const name of owned) {
    assert.equal(sharedDefs.includes(name), false);
    assert.equal(TEMPLATES[name], undefined);
    assert.equal(suiteDefs.includes(name), true);
    assert.ok(SUITE_TEMPLATES[name]);
  }
});

test("save-and-start returns the suite template when no sentinel matches", () => {
  const state = createMockState();
  const result = renderMockResponse(SUITE_TEMPLATES["save-and-start-experiment-iteration"], {
    projectKey: "my-project",
    environmentKey: "production",
    experimentKey: "checkout-running",
  }, "save-and-start-experiment-iteration", state);
  assert.equal(result.key, "checkout-running");
  assert.equal(result.currentIteration.status, "running");
});

test("get-flag-status-across-envs defaults to active in test and production", () => {
  const state = createMockState();
  const result = renderMockResponse(SUITE_TEMPLATES["get-flag-status-across-envs"], {
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
  const result = renderMockResponse(SUITE_TEMPLATES["get-flag-status-across-envs"], {
    projectKey: "mixed-contexts",
    flagKey: "checkout-inactive",
  }, "get-flag-status-across-envs", state);
  const production = result.environments.find((env) => env.key === "production");
  assert.equal(production.status, "inactive");
  assert.deepEqual(result.summary.inactive, ["production"]);
});

test("get-flags (flagKey) returns checkout-active on, serving one variation", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flags#flagKey"], {
    projectKey: "only-user",
    flagKey: "checkout-active",
    environmentKey: "production",
  }, "get-flags", state);
  assert.equal(result.environment.on, true);
  assert.equal(result.environment.version, 7);
  assert.equal(result.environment.fallthrough.variation, 0);
  assert.equal(result.environment.fallthrough.rollout, undefined);
  assert.equal(result.variations[0].name, "Current checkout");
});

test("get-flags (flagKey) returns not-found for missing-checkout", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flags#flagKey"], {
    projectKey: "my-project",
    flagKey: "missing-checkout",
  }, "get-flags", state);
  assert.equal(result.status, 404);
});

test("get-flags (flagKey) returns a stored flag before the missing-checkout not-found branch", () => {
  const state = createMockState();
  renderMockResponse(TEMPLATES["create-flag"], {
    key: "missing-checkout",
    name: "Missing",
  }, "create-flag", state);
  const result = renderMockResponse(TEMPLATES["get-flags#flagKey"], {
    flagKey: "missing-checkout",
  }, "get-flags", state);
  assert.equal(result.key, "missing-checkout");
  assert.equal(result.error, undefined);
});

test("get-flags list in exp-setup-missing-flag returns similar keys for any query", () => {
  const state = createMockState();
  for (const query of ["flags", "Checkout", "missing-checkout"]) {
    const result = renderMockResponse(TEMPLATES["get-flags"], {
      projectKey: "exp-setup-missing-flag",
      query,
    }, "get-flags", state);
    assert.deepEqual(
      result.flags.map((flag) => flag.key),
      ["checkout-flow", "new-checkout"],
    );
  }
});

test("get-flags list checkout query in any other project returns the shared template", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flags"], {
    projectKey: "my-project",
    query: "Checkout",
  }, "get-flags", state);
  assert.deepEqual(result, TEMPLATES["get-flags"]);
});

test("get-flags list without that query keeps the shared flag list", () => {
  const state = createMockState();
  const result = renderMockResponse(TEMPLATES["get-flags"], {
    projectKey: "web-app",
    query: "search-v2",
  }, "get-flags", state);
  assert.deepEqual(
    result.flags.map((flag) => flag.key),
    ["enable-notifications", "search-v2"],
  );
});

test("search-contexts suggests user only when no other kind is stored", () => {
  const state = createMockState();
  const users = renderMockResponse(SUITE_TEMPLATES["search-contexts"], {
    projectKey: "only-user",
    environmentKey: "production",
    kind: "user",
  }, "search-contexts", state);
  const others = renderMockResponse(SUITE_TEMPLATES["search-contexts"], {
    projectKey: "only-user",
    environmentKey: "production",
    filter: 'kind notEquals "user"',
  }, "search-contexts", state);
  assert.equal(users.totalCount, 1);
  assert.equal(users.items[0].kind, "user");
  assert.equal(others.totalCount, 0);
});

test("search-contexts with no kind filter lists every stored kind", () => {
  const state = createMockState();
  const onlyUser = renderMockResponse(SUITE_TEMPLATES["search-contexts"], {
    projectKey: "only-user",
    environmentKey: "production",
  }, "search-contexts", state);
  assert.deepEqual(onlyUser.items.map((item) => item.kind), ["user"]);
  assert.equal(onlyUser.totalCount, 1);

  const mixed = renderMockResponse(SUITE_TEMPLATES["search-contexts"], {
    projectKey: "mixed-contexts",
    environmentKey: "production",
  }, "search-contexts", state);
  assert.deepEqual(
    mixed.items.map((item) => item.kind).sort(),
    ["organization", "user"],
  );
  assert.equal(mixed.totalCount, 2);
});

test("search-contexts on mixed-contexts returns another kind", () => {
  const state = createMockState();
  const others = renderMockResponse(SUITE_TEMPLATES["search-contexts"], {
    projectKey: "mixed-contexts",
    environmentKey: "production",
    filter: 'kind notEquals "user"',
  }, "search-contexts", state);
  assert.ok(others.totalCount > 0);
  assert.equal(others.items[0].kind, "organization");
});

test("get-metric-events default returns the experiment-setup template unchanged", () => {
  const state = createMockState();
  const template = SUITE_TEMPLATES["get-metric-events"];
  const result = renderMockResponse(template, {
    projectKey: "my-project",
  }, "get-metric-events", state);
  assert.deepEqual(result, template);
  assert.deepEqual(
    result.events.map((event) => event.eventKey),
    ["checkout-completed", "page-load-ms", "cta-click", "cta-clicked-v2"],
  );
});

test("get-metric-events returns the experiment-orchestration template unchanged", () => {
  const state = createMockState();
  const template = ORCH_TEMPLATES["get-metric-events"];
  const result = renderMockResponse(template, {
    projectKey: "my-project",
    environmentKey: "production",
    query: "checkout-completed",
  }, "get-metric-events", state);
  assert.deepEqual(result, template);
  assert.equal(result.events[0].eventKey, "checkout-completed");
  assert.equal(result.events[0].lastSeen, "2026-10-28T12:00:00Z");
  assert.equal(result.totalCount, 1);
  assert.equal(result.count, undefined);
});

test("get-metric-events query cta-clicked returns similar keys only", () => {
  const state = createMockState();
  const result = renderMockResponse(SUITE_TEMPLATES["get-metric-events"], {
    projectKey: "my-project",
    environmentKey: "production",
    query: "cta-clicked",
  }, "get-metric-events", state);
  assert.deepEqual(result, {
    events: [
      { eventKey: "cta-click", eventKind: "custom", lastSeen: "1792281600000" },
      { eventKey: "cta-clicked-v2", eventKind: "custom", lastSeen: "1792281600000" },
    ],
    count: 2,
    _note: "2 event key(s) found with recent activity.",
  });
});

test("get-experiments returns a running iteration for checkout-running", () => {
  const state = createMockState();
  const running = renderMockResponse(TEMPLATES["get-experiments#experimentKey"], {
    projectKey: "my-project",
    environmentKey: "production",
    experimentKey: "checkout-running",
  }, "get-experiments", state);
  const draft = renderMockResponse(TEMPLATES["get-experiments#experimentKey"], {
    projectKey: "my-project",
    environmentKey: "production",
    experimentKey: "checkout-draft",
  }, "get-experiments", state);
  assert.equal(running.currentIteration.status, "running");
  assert.equal(draft.currentIteration.status, "not_started");
});

// ---------------------------------------------------------------------------
// Release Autopilot stateful reads (templates from the suite's own mocks)

const RA_TEMPLATES = require("../release-autopilot-onboarding/tool-mocks.json");
// ---------------------------------------------------------------------------

test("repo read reflects an earlier repo write", () => {
  const state = createMockState();
  const tpl = RA_TEMPLATES["get-automations"];
  const before = renderMockResponse(tpl, { repo: "acme/demo" }, "get-automations", state);
  assert.equal(before.repos[0].mapped, false);
  renderMockResponse(RA_TEMPLATES["update-automations"], { accountWide: false, repo: "acme/demo", projectKey: "default", autoReleasing: { enabled: false } }, "update-automations", state);
  const got = renderMockResponse(tpl, { repo: "acme/demo" }, "get-automations", state);
  assert.equal(got.repos.length, 1);
  assert.equal(got.repos[0].mapped, true);
  assert.equal(got.repos[0].projectKey, "default");
  assert.equal(got.repos[0].autoReleasing.enabled, false);
});

test("account read merges an earlier account write", () => {
  const state = createMockState();
  renderMockResponse(RA_TEMPLATES["update-automations"], { accountWide: true, autoFlagging: { enabled: false } }, "update-automations", state);
  const got = renderMockResponse(RA_TEMPLATES["get-automations"], {}, "get-automations", state);
  assert.equal(got.account.autoFlagging.enabled, false);
  assert.equal(got.account.autoFlagging.approvalRequired, true);
  assert.equal(got.repos.length, 4);
});

test("mapped filter narrows the repo list", () => {
  const got = renderMockResponse(RA_TEMPLATES["get-automations"], { mapped: false }, "get-automations", createMockState());
  assert.deepEqual(got.repos.map((r) => r.repo), ["acme/api", "acme/demo"]);
  assert.equal(got.totalCount, 2);
});

test("release plans list reflects a created plan", () => {
  const state = createMockState();
  renderMockResponse(RA_TEMPLATES["create-release-plan"], { projectKey: "default", environmentKey: "production", key: "p", name: "P", progressiveRelease: { phases: [] } }, "create-release-plan", state);
  const got = renderMockResponse(RA_TEMPLATES["get-release-plans"], { projectKey: "default", environmentKey: "production" }, "get-release-plans", state);
  assert.equal(got.totalCount, 1);
  assert.equal(got.items[0].key, "p");
});

test("an error template wins over the stateful write and is not recorded", () => {
  const state = createMockState();
  const err = { error: "403: denied" };
  assert.equal(renderMockResponse(err, { accountWide: true, autoFlagging: { enabled: true } }, "update-automations", state).error, "403: denied");
  assert.equal(state.raSettings, null);
});

test("get-agent-configs section=status reflects a targeting write for that environment", () => {
  const state = createMockState();
  const status = { configKey: "content-writer", section: "status", projectKey: "marketing" };
  const read = () =>
    renderMockResponse(TEMPLATES["get-agent-configs#status"], status, "get-agent-configs", state);
  assert.equal(read().environments.production.on, true);

  renderMockResponse(
    TEMPLATES["update-agent-config#targeting"],
    { configKey: "content-writer", resource: "targeting", env: "production", on: false, confirm: true },
    "update-agent-config",
    state,
  );
  const after = read();
  assert.equal(after.environments.production.on, false);
  assert.equal(after.environments.staging.on, true);
});

test("get-agent-configs section=status is unchanged for a different config", () => {
  const state = createMockState();
  renderMockResponse(
    TEMPLATES["update-agent-config#targeting"],
    { configKey: "content-writer", resource: "targeting", env: "production", on: false, confirm: true },
    "update-agent-config",
    state,
  );
  const other = renderMockResponse(
    TEMPLATES["get-agent-configs#status"],
    { configKey: "other-config", section: "status" },
    "get-agent-configs",
    state,
  );
  assert.equal(other.environments.production.on, true);
});

test("project cleanup write is read back by the cleanup section", () => {
  const state = createMockState();
  renderMockResponse({ ok: true }, { projectKey: "default", cleanup: { schedule: "weekly", repositories: ["acme/demo"], maxJobsPerRun: 3 }, confirm: true }, "update-automations", state);
  const got = renderMockResponse({ settings: { schedule: "disabled" } }, { section: "cleanup", projectKey: "default" }, "get-automations", state);
  assert.equal(got.settings.schedule, "weekly");
  assert.deepEqual(got.settings.repositories, ["acme/demo"]);
});

test("archival cannot be turned on by update-automations", () => {
  const state = createMockState();
  const res = renderMockResponse({ ok: true }, { projectKey: "default", archival: { enabled: true }, confirm: true }, "update-automations", state);
  assert.deepEqual(res.changed, []);
  assert.ok(res.automationsPage);
});

test("default environment release plan is reflected in the plan list", () => {
  const state = createMockState();
  renderMockResponse({}, { projectKey: "default", environmentKey: "production", key: "progressive", name: "Progressive", progressiveRelease: { phases: [] } }, "create-environment-release-plan", state);
  renderMockResponse({}, { projectKey: "default", environmentKey: "production", releasePlanKey: "progressive", default: true, confirm: true }, "update-default-environment-release-plan", state);
  const got = renderMockResponse({ items: [] }, { projectKey: "default", environmentKey: "production" }, "get-environment-release-plans", state);
  assert.equal(got.items[0].default, true);
});

test("setting an existing plan as default is reflected in the plan list", () => {
  const state = createMockState();
  const existing = { items: [{ key: "gradual", name: "Gradual", environmentKey: "production", default: false }], totalCount: 1 };
  const args = { projectKey: "default", environmentKey: "production" };
  renderMockResponse({}, { ...args, releasePlanKey: "gradual", default: true, confirm: true }, "update-default-environment-release-plan", state);
  const got = renderMockResponse(existing, args, "get-environment-release-plans", state);
  assert.equal(got.totalCount, 1);
  assert.equal(got.items[0].key, "gradual");
  assert.equal(got.items[0].default, true);
});

test("a created plan is listed beside the existing plans", () => {
  const state = createMockState();
  const existing = { items: [{ key: "gradual", name: "Gradual", environmentKey: "production", default: true }], totalCount: 1 };
  const args = { projectKey: "default", environmentKey: "production" };
  renderMockResponse({}, { ...args, key: "p", name: "P", progressiveRelease: { phases: [] } }, "create-environment-release-plan", state);
  const got = renderMockResponse(existing, args, "get-environment-release-plans", state);
  assert.deepEqual(got.items.map((p) => [p.key, p.default]), [["gradual", true], ["p", false]]);
  assert.equal(got.totalCount, 2);
});

test("every release-autopilot-onboarding tool has a mock template", () => {
  const defs = require("../release-autopilot-onboarding/tool-definitions.json");
  const shared = require("../mocks/tool-responses.json");
  const missing = (Array.isArray(defs) ? defs : defs.tools)
    .map((d) => d.name)
    .filter((name) => !(name in RA_TEMPLATES) && !(name in shared));
  assert.deepEqual(missing, []);
});

const planArgs = (allocations, metrics) => ({
  projectKey: "default", environmentKey: "production", key: "progressive", name: "Progressive",
  progressiveRelease: {
    randomizationUnit: "user",
    phases: [{ clauses: [{ attribute: "kind", op: "in", values: ["user"], contextKind: "user" }], steps: allocations.map((allocation) => ({ allocation, durationMillis: 14400000 })) }],
    metrics,
  },
});

test("a release plan with metrics is rejected above 50000 per step and not recorded", () => {
  const state = createMockState();
  const got = renderMockResponse(RA_TEMPLATES["create-environment-release-plan"], planArgs([99000], { "user-error-rate": { isGroup: false, autoRollback: true } }), "create-environment-release-plan", state);
  assert.match(got.error, /at most 50000/);
  assert.equal(state.raPlans.production, undefined);
  const ok = renderMockResponse(RA_TEMPLATES["create-environment-release-plan"], planArgs([50000], { "user-error-rate": { isGroup: false, autoRollback: true } }), "create-environment-release-plan", state);
  assert.equal(ok.error, undefined);
  assert.equal(state.raPlans.production.length, 1);
});

test("a release plan without metrics allows 99000 but not more", () => {
  const state = createMockState();
  assert.equal(renderMockResponse({}, planArgs([99000], {}), "create-environment-release-plan", state).error, undefined);
  assert.match(renderMockResponse({}, planArgs([100000], {}), "create-environment-release-plan", state).error, /at most 99000/);
});
