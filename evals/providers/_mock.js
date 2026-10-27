/**
 * Mock-response renderer used by the provider to fill in canned tool
 * responses from mocks/tool-responses.json before handing them back to the
 * agent through the in-process MCP server.
 *
 * Two layers:
 *
 *   1. Stateless template rendering walks the parsed mock template object,
 *      substituting `{{placeholder}}` tokens inside string leaves with values
 *      from the tool input. Quote/backslash chars in inputs are safe because
 *      substitution only touches strings.
 *
 *   2. Stateful overlay keeps an in-memory map of configs per `callApi`
 *      invocation. Write tools (create/setup/update) record into state; read
 *      tools (get-ai-config, get-ai-config-health) build their response from
 *      state when one exists, falling back to the template otherwise. This
 *      prevents the agent from believing its own writes failed when the static
 *      template returns generic placeholder data.
 */

const PLACEHOLDER_RE = /\{\{(\w+)\}\}/g;

function buildReplacements(input) {
  const safe = input || {};
  return {
    flagKey: safe.flagKey || safe.key || "unknown-flag",
    flagName: safe.flagName || safe.name || "Unknown Flag",
    configKey: safe.configKey || safe.key || "unknown-config",
    configName: safe.configName || safe.name || "Unknown Config",
    variationKey:
      safe.variationKey || safe.key || safe.sourceVariationKey || "default",
    variationName: safe.variationName || safe.name || "Default",
    toolKey: safe.toolKey || safe.key || "unknown-tool",
    modelConfigKey: safe.modelConfigKey || "OpenAI.gpt-4o",
    modelName: safe.modelName || "gpt-4o",
    mode: safe.mode || "completion",
    toolDescription: safe.description || "A tool",
    projectKey: safe.projectKey || "my-project",
    environmentKey: safe.environmentKey || safe.env || "production",
    metricKey: safe.metricKey || safe.key || "unknown-metric",
    metricName: safe.metricName || safe.name || "Unknown Metric",
    experimentKey: safe.experimentKey || safe.key || "unknown-experiment",
    experimentName: safe.experimentName || safe.name || "Unknown Experiment",
    hypothesis: safe.hypothesis || (safe.iteration && safe.iteration.hypothesis) || "",
  };
}

function renderString(value, replacements) {
  return value.replace(PLACEHOLDER_RE, (match, key) =>
    Object.prototype.hasOwnProperty.call(replacements, key)
      ? String(replacements[key])
      : match,
  );
}

function walk(node, replacements) {
  if (typeof node === "string") return renderString(node, replacements);
  if (Array.isArray(node)) return node.map((item) => walk(item, replacements));
  if (node && typeof node === "object") {
    const out = {};
    for (const k of Object.keys(node)) out[k] = walk(node[k], replacements);
    return out;
  }
  return node;
}

// ---------------------------------------------------------------------------
// Stateful overlay
// ---------------------------------------------------------------------------

const SEED_CONFIGS = {
  "support-chatbot": {
    key: "support-chatbot",
    name: "Support Chatbot",
    mode: "agent",
    description: "AI-powered support agent for customer tickets",
    tags: ["support", "production"],
    archived: false,
    variations: [
      {
        key: "default",
        name: "Default",
        modelConfigKey: "OpenAI.gpt-4o",
        modelName: "gpt-4o",
        instructions:
          "You are a helpful assistant that answers questions concisely.",
        parameters: { temperature: 0.7, max_tokens: 2048 },
        tools: [],
        status: "active",
      },
    ],
  },
  "code-reviewer": {
    key: "code-reviewer",
    name: "Code Review Assistant",
    mode: "completion",
    description: "Automated code review assistant for pull requests",
    tags: ["engineering"],
    archived: false,
    variations: [
      {
        key: "default",
        name: "Default",
        modelConfigKey: "Anthropic.claude-sonnet-4-5",
        modelName: "claude-sonnet-4-5",
        messages: [
          {
            role: "system",
            content: "You review code for bugs, style, and security issues.",
          },
        ],
        parameters: { temperature: 0.3, max_tokens: 4096 },
        tools: [],
        status: "active",
      },
    ],
  },
};

/**
 * Create fresh in-memory state for a single callApi invocation. Pass the
 * returned object to every `renderMockResponse` call so stateful tools
 * (create/update/get) share the same map.
 */
function createMockState() {
  return {
    configs: {},      // configKey -> config object
    flags: {},        // flagKey -> flag object
  };
}

// Lifecycle status for get-flag-status-across-envs. The default matches the
// environments in the get-environments mock and reports both as active, so
// flag-drift sees no cross-environment difference and flag-command gets no
// cleanup signal. `federal` is intentionally absent: the flag-drift mock
// flips that environment's fallthrough, and listing it here would make
// single-environment drift cases look divergent.
function flagStatusResponse(flagKey, productionStatus) {
  const environments = [
    { key: "test", status: "active" },
    { key: "production", status: productionStatus },
  ];
  const summary = { active: [], inactive: [], new: [], launched: [] };
  for (const env of environments) {
    if (summary[env.status]) summary[env.status].push(env.key);
  }
  return { flagKey, environments, summary };
}

const DEFAULT_METRIC_EVENTS = [
  { key: "checkout-completed", lastSeen: "2026-10-20T00:00:00.000Z" },
  { key: "page-load-ms", lastSeen: "2026-10-20T00:00:00.000Z" },
  { key: "cta-click", lastSeen: "2026-10-18T00:00:00.000Z" },
  { key: "cta-clicked-v2", lastSeen: "2026-10-18T00:00:00.000Z" },
];

// list-metric-events has no eventKey. A query of cta-clicked returns the
// similar keys only; every other call, including no query, returns the
// default list (which also contains those similar keys).
function metricEventsResponse(input) {
  const query = typeof input.query === "string" ? input.query.trim() : "";
  const events =
    query.toLowerCase() === "cta-clicked"
      ? DEFAULT_METRIC_EVENTS.filter(
          (event) => event.key === "cta-click" || event.key === "cta-clicked-v2",
        )
      : DEFAULT_METRIC_EVENTS;
  return { events, totalCount: events.length };
}

function isUserKindQuery(input) {
  if (input.kind === "user") return true;
  return typeof input.filter === "string" && /kind\s+equals\s+"?user"?/i.test(input.filter);
}

function isNotEqualsUser(input) {
  return (
    typeof input.filter === "string" &&
    /kind\s+notEquals\s+"?user"?/i.test(input.filter)
  );
}

function searchContextsResponse(input) {
  const mixed = input.projectKey === "mixed-contexts";
  if (isNotEqualsUser(input)) {
    if (mixed) {
      return {
        items: [
          {
            kind: "organization",
            key: "org-1",
            lastSeen: "2026-10-20T00:00:00.000Z",
          },
        ],
        totalCount: 1,
      };
    }
    return { items: [], totalCount: 0 };
  }
  if (isUserKindQuery(input) || (input.kind == null && input.filter == null)) {
    return {
      items: [{ kind: "user", key: "user-1", lastSeen: "2026-10-20T00:00:00.000Z" }],
      totalCount: 1,
    };
  }
  return { items: [], totalCount: 0 };
}

function checkoutActiveFlag() {
  return {
    key: "checkout-active",
    name: "Checkout active",
    kind: "multivariate",
    description: "Checkout experiment flag",
    temporary: true,
    tags: [],
    variations: [
      { _id: "var-current", value: "current", name: "Current checkout" },
      { _id: "var-new", value: "new", name: "New checkout" },
    ],
    defaults: { onVariation: 0, offVariation: 1 },
    environment: {
      on: true,
      version: 7,
      rules: [],
      targets: [],
      fallthrough: { variation: 0 },
      offVariation: 1,
    },
  };
}

function similarCheckoutFlags() {
  const flag = (key, name, on) => ({
    key,
    name,
    kind: "boolean",
    description: name,
    temporary: true,
    tags: ["checkout"],
    on,
    variations: [
      { value: true, name: "Enabled" },
      { value: false, name: "Disabled" },
    ],
  });
  return {
    flags: [
      flag("checkout-flow", "Checkout flow", true),
      flag("new-checkout", "New checkout", false),
    ],
    totalCount: 2,
    pageInfo: { limit: 20, offset: 0 },
  };
}

function runningExperiment(input) {
  return {
    key: "checkout-running",
    name: "Checkout running",
    environmentKey: input.environmentKey || input.env || "production",
    currentIteration: {
      status: "running",
      hypothesis: "The new checkout will lift completion.",
      treatments: [
        { _id: "treat-control", name: "Control", baseline: true, allocationPercent: 50 },
        { _id: "treat-treatment", name: "Treatment", baseline: false, allocationPercent: 50 },
      ],
    },
  };
}

/**
 * Render a mock response for `toolName` given `input` (raw tool arguments).
 * `state` is the per-invocation map from `createMockState()`.
 * `templates` is the full parsed mocks/tool-responses.json.
 */
function renderMockResponse(template, input, toolName, state) {
  const replacements = buildReplacements(input);

  // ---------- stateful reads ----------
  if (toolName === "get-ai-config") {
    const key = input.configKey || input.key;
    if (key) {
      if (!state.configs[key] && SEED_CONFIGS[key]) {
        state.configs[key] = JSON.parse(JSON.stringify(SEED_CONFIGS[key]));
      }
      if (state.configs[key]) return state.configs[key];
    }
  }

  if (toolName === "get-ai-config-health") {
    const key = input.configKey || input.key;
    if (key && state.configs[key]) {
      const cfg = state.configs[key];
      return {
        key: cfg.key,
        name: cfg.name,
        mode: cfg.mode,
        health: "healthy",
        variationsCount: (cfg.variations || []).length,
        issues: [],
        variations: (cfg.variations || []).map((v) => ({
          key: v.key,
          name: v.name,
          hasModel: Boolean(v.modelConfigKey),
          hasPrompts: Boolean(v.instructions || (v.messages && v.messages.length)),
          toolsAttached: (v.tools || []).length,
        })),
      };
    }
  }

  if (toolName === "list-ai-configs") {
    // Merge state configs into the static template list for consistent reads.
    // State entries always win over the static template for the same key, so
    // an agent-created (or updated) config is reflected immediately.
    const staticList = walk(template, replacements);
    const stateConfigs = Object.values(state.configs).map((c) => ({
      key: c.key,
      name: c.name,
      mode: c.mode,
      description: c.description || "",
      tags: c.tags || [],
      variationsCount: (c.variations || []).length,
      archived: c.archived || false,
    }));
    if (stateConfigs.length > 0) {
      const stateKeys = new Set(stateConfigs.map((c) => c.key));
      const staticOnly = (staticList.configs || []).filter((c) => !stateKeys.has(c.key));
      const merged = [...staticOnly, ...stateConfigs];
      return {
        ...staticList,
        configs: merged,
        totalCount: merged.length,
      };
    }
    return staticList;
  }

  if (toolName === "get-flag" || toolName === "get-feature-flag") {
    const key = input.flagKey || input.key;
    if (key && state.flags[key]) return state.flags[key];

    // Sentinel keys for the experiment-setup suite. Checked before the
    // federal fallthrough hook so they do not inherit that override.
    if (key === "missing-checkout") {
      return {
        error: "not_found",
        status: 404,
        message: "Flag 'missing-checkout' was not found in this project.",
      };
    }
    if (key === "checkout-active") return checkoutActiveFlag();

    // Cross-environment divergence hook: a `federal`-style environment serves
    // the opposite default (variation 0 / `true`) from every other environment
    // (which resolve to variation 1 / `false` via the static template). This
    // lets the flag-drift eval exercise the case where a single in-code default
    // cannot match every critical environment. No other suite queries a
    // `federal` environment, so their behavior is unchanged.
    const env = input.environmentKey || input.env;
    if (typeof env === "string" && /federal/i.test(env)) {
      const rendered = walk(template, replacements);
      if (rendered && rendered.environment) {
        rendered.environment = {
          ...rendered.environment,
          fallthrough: { variation: 0 },
        };
      }
      return rendered;
    }
  }

  // ---------- stateful writes ----------
  if (toolName === "setup-ai-config") {
    const cfg = {
      key: input.key,
      name: input.name,
      mode: input.mode,
      description: input.description || "",
      tags: input.tags || [],
      archived: false,
      variations: [
        {
          key: input.variationKey || "default",
          name: input.variationName || "Default",
          modelConfigKey: input.modelConfigKey,
          modelName: input.modelName,
          ...(input.mode === "agent"
            ? { instructions: input.instructions || "" }
            : { messages: input.messages || [] }),
          parameters: input.parameters || {},
          tools: input.tools || [],
          status: "active",
        },
      ],
    };
    state.configs[input.key] = cfg;
    return cfg;
  }

  if (toolName === "create-ai-config") {
    const cfg = {
      key: input.key,
      name: input.name,
      mode: input.mode,
      description: input.description || "",
      tags: input.tags || [],
      archived: false,
      variations: [],
    };
    state.configs[input.key] = cfg;
    return cfg;
  }

  if (toolName === "create-ai-config-variation") {
    const cfg = state.configs[input.configKey];
    const variation = {
      key: input.key,
      name: input.name,
      modelConfigKey: input.modelConfigKey,
      modelName: input.modelName,
      ...(input.instructions !== undefined
        ? { instructions: input.instructions }
        : {}),
      ...(input.messages !== undefined ? { messages: input.messages } : {}),
      parameters: input.parameters || {},
      tools: input.tools || [],
      status: "active",
    };
    if (cfg) {
      cfg.variations = [...(cfg.variations || []), variation];
    } else {
      // Parent config not in state — create a minimal stub so the variation
      // is reachable via get-ai-config and list-ai-configs. The real API
      // would 404 here; the mock recovers gracefully.
      state.configs[input.configKey] = {
        key: input.configKey,
        name: input.configKey,
        mode: "completion",
        description: "",
        tags: [],
        archived: false,
        variations: [variation],
      };
    }
    return { configKey: input.configKey, variation };
  }

  if (toolName === "update-ai-config") {
    const cfg = state.configs[input.key || input.configKey];
    if (cfg) {
      const CONFIG_FIELDS = ["name", "description", "tags", "archived"];
      for (const k of CONFIG_FIELDS) {
        if (input[k] !== undefined) cfg[k] = input[k];
      }
      return { ...cfg };
    }
    return walk(template, replacements);
  }

  if (toolName === "update-ai-config-variation") {
    const cfg = state.configs[input.configKey];
    if (cfg) {
      const VARIATION_FIELDS = [
        "key", "name", "modelConfigKey", "modelName",
        "instructions", "messages", "parameters", "tools", "status",
      ];
      cfg.variations = (cfg.variations || []).map((v) => {
        if (v.key !== input.variationKey) return v;
        const patch = {};
        for (const k of VARIATION_FIELDS) {
          if (input[k] !== undefined) patch[k] = input[k];
        }
        return { ...v, ...patch };
      });
    }
    return walk(template, replacements);
  }

  if (toolName === "clone-ai-config-variation") {
    const configKey = input.configKey;
    if (!state.configs[configKey] && SEED_CONFIGS[configKey]) {
      state.configs[configKey] = JSON.parse(JSON.stringify(SEED_CONFIGS[configKey]));
    }
    const cfg = state.configs[configKey];
    if (cfg) {
      const sourceVariation = (cfg.variations || []).find(
        (v) => v.key === input.sourceVariationKey,
      );
      if (sourceVariation) {
        const newVariation = {
          ...sourceVariation,
          key: input.key,
          name: input.name !== undefined ? input.name : sourceVariation.name,
          ...(input.modelConfigKey !== undefined ? { modelConfigKey: input.modelConfigKey } : {}),
          ...(input.modelName !== undefined ? { modelName: input.modelName } : {}),
          ...(input.instructions !== undefined ? { instructions: input.instructions } : {}),
          ...(input.messages !== undefined ? { messages: input.messages } : {}),
          ...(input.parameters !== undefined ? { parameters: input.parameters } : {}),
          ...(input.tools !== undefined ? { tools: input.tools } : {}),
          status: "active",
        };
        cfg.variations = [...(cfg.variations || []), newVariation];
        return { configKey, source: sourceVariation, created: newVariation };
      }
    }
    return walk(template, replacements);
  }

  if (toolName === "create-flag" || toolName === "create-feature-flag") {
    // Fail-closed test hook: a fixture that sets projectKey "restricted" makes
    // flag creation fail (permission denied), so an eval can assert the skill
    // stops rather than proceeding to wire code or record a release.
    if (input.projectKey === "restricted") {
      return {
        error: "forbidden",
        status: 403,
        message:
          "You do not have permission to create flags in project 'restricted'.",
      };
    }
    const flag = walk(template, replacements);
    state.flags[input.key || input.flagKey] = flag;
    return flag;
  }

  if (toolName === "get-flag-status-across-envs") {
    const flagKey = input.flagKey || "unknown-flag";
    const productionStatus = flagKey === "checkout-inactive" ? "inactive" : "active";
    return flagStatusResponse(flagKey, productionStatus);
  }

  if (toolName === "search-contexts") return searchContextsResponse(input || {});

  if (toolName === "list-metric-events") return metricEventsResponse(input || {});

  if (toolName === "list-flags" || toolName === "list-feature-flags") {
    const query = typeof input.query === "string" ? input.query.trim().toLowerCase() : "";
    if (query === "missing-checkout") return similarCheckoutFlags();
  }

  if (toolName === "get-experiment") {
    const experimentKey = input.experimentKey || input.key;
    if (experimentKey === "checkout-running") return runningExperiment(input);
  }

  // Default: stateless template render
  return walk(template, replacements);
}

module.exports = { renderMockResponse, createMockState };
