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

  // ---------- release-policy matching hooks ----------
  // match-release-policies is a read-only preview of which policy governs a
  // flag/tags in an environment. Its `warnings` list is what tells the skill to
  // stop instead of presenting a clean `policy` rollout, so evals need to drive
  // the missing/incomplete/method cases. Keyed on `projectKey` (mirrors the
  // create-flag `restricted` hook): a magic project name selects the scenario,
  // and the default project returns the complete guarded winner from the
  // static template.
  if (toolName === "match-release-policies") {
    const env = input.environmentKey || "production";
    const project = String(input.projectKey || "");
    const criteria = {
      projectKey: project || "default",
      environmentKey: env,
      flagKey: input.flagKey || null,
      flagTags: input.flagTags || null,
      tagsSource: input.flagKey ? "flagKey" : (input.flagTags ? "flagTags" : "none"),
    };

    // A project with no configured release policies → nothing matches.
    if (/no-?release-?polic/i.test(project)) {
      return {
        matchingPolicies: [],
        winningPolicy: null,
        winningReleaseMethod: null,
        autoAttachedMetricKeys: [],
        autoAttachedMetricGroupKeys: [],
        warnings: [
          {
            code: "missing_policy",
            environmentKey: env,
            message: `No release policy matches environment "${env}". Do not record this environment as releaseType "policy" unless the user explicitly accepts manual follow-up.`,
          },
        ],
        criteria,
      };
    }

    // A policy matches but can't govern a rollout as-is (guarded, no stages).
    if (/incomplete-?polic/i.test(project)) {
      const winner = { key: "guarded-incomplete", name: "Guarded (incomplete)", releaseMethod: "guarded" };
      return {
        matchingPolicies: [winner],
        winningPolicy: winner,
        winningReleaseMethod: "guarded",
        autoAttachedMetricKeys: [],
        autoAttachedMetricGroupKeys: [],
        warnings: [
          {
            code: "incomplete_policy",
            environmentKey: env,
            policyKey: "guarded-incomplete",
            policyName: "Guarded (incomplete)",
            releaseMethod: "guarded",
            missing: ["stages"],
            message: `Release policy "Guarded (incomplete)" is guarded but missing stages. Fix the policy or use an explicit override before recording a policy-based automated rollout.`,
          },
        ],
        criteria,
      };
    }

    // A complete progressive winner, for asserting the plan describes a
    // progressive rollout accurately (not the default guarded winner).
    if (/progressive/i.test(project)) {
      const winner = { key: "progressive-default", name: "Progressive rollout", releaseMethod: "progressive" };
      return {
        matchingPolicies: [winner],
        winningPolicy: winner,
        winningReleaseMethod: "progressive",
        autoAttachedMetricKeys: [],
        autoAttachedMetricGroupKeys: [],
        warnings: [],
        criteria,
      };
    }

    // Default: the complete guarded winner from the static template.
    const rendered = walk(template, replacements);
    return {
      ...rendered,
      warnings: Array.isArray(rendered.warnings) ? rendered.warnings : [],
      criteria,
    };
  }

  // Default: stateless template render
  return walk(template, replacements);
}

module.exports = { renderMockResponse, createMockState };
