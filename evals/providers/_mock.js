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
 *      tools (get-agent-configs with a configKey) build their response from
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
    configKey: safe.configKey || "unknown-config",
    configName: safe.configName || safe.name || "Unknown Config",
    variationKey:
      safe.variationKey ||
      (safe.fallthrough && safe.fallthrough.variationKey) ||
      safe.sourceVariationKey ||
      "default",
    variationName: safe.variationName || "Default",
    toolKey: safe.toolKey || safe.key || "unknown-tool",
    modelConfigKey: safe.modelConfigKey || "OpenAI.gpt-4o",
    modelName: safe.modelName || "gpt-4o",
    mode: safe.mode || "completion",
    toolDescription: safe.description || "A tool",
    projectKey: safe.projectKey || "my-project",
    newProjectKey: safe.key || "new-project",
    newProjectName: safe.name || "New Project",
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
    targeting: {},    // configKey -> { env -> on } for targeting writes this run
    raSettings: null, // Release Autopilot account settings written this run
    raRepos: {},      // owner/name -> Release Autopilot repo settings written this run
    raPlans: {},      // environmentKey -> release plans created this run
    raDefaults: {},   // environmentKey -> default release plan key set this run
    raCleanup: {},    // projectKey -> auto-cleanup settings written this run
    raArchival: {},   // projectKey -> auto-archival settings written this run
    raFlagPlans: {},  // projectKey -> stored flag release plans after a write this run
    raFlagSeen: {},   // projectKey -> stored flag release plans from the first list read
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

// experiment-setup sentinel. The exact key cta-clicked is not in that suite's
// get-metric-events template; a query for it returns the similar keys from
// the template that was passed in. Every other call falls through and returns
// that template unchanged, so another suite keeps its own event list.
function similarCtaMetricEvents(template, replacements) {
  const rendered = walk(template, replacements);
  const events = Array.isArray(rendered.events)
    ? rendered.events.filter(
        (event) => event.eventKey === "cta-click" || event.eventKey === "cta-clicked-v2",
      )
    : [];
  return {
    events,
    count: events.length,
    _note: `${events.length} event key(s) found with recent activity.`,
  };
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

function contextItem(kind, key) {
  return { kind, key, lastSeen: "2026-10-20T00:00:00.000Z" };
}

function isUnfilteredContextSearch(input) {
  const kindBlank = input.kind == null || String(input.kind).trim() === "";
  const filterBlank = input.filter == null || String(input.filter).trim() === "";
  return kindBlank && filterBlank;
}

function searchContextsResponse(input) {
  const mixed = input.projectKey === "mixed-contexts";
  if (isNotEqualsUser(input)) {
    if (mixed) {
      return { items: [contextItem("organization", "org-1")], totalCount: 1 };
    }
    return { items: [], totalCount: 0 };
  }
  if (isUserKindQuery(input)) {
    return { items: [contextItem("user", "user-1")], totalCount: 1 };
  }
  // No kind and no filter lists every stored kind: user in both projects,
  // and organization as well when other kinds are stored.
  if (isUnfilteredContextSearch(input)) {
    const items = [contextItem("user", "user-1")];
    if (mixed) items.push(contextItem("organization", "org-1"));
    return { items, totalCount: items.length };
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
 * Template key for a call. A tool that both lists and gets (get-flags,
 * get-agent-configs, ...) has one template per mode, keyed `<tool>#<mode>`.
 */
function templateKey(toolName, input) {
  const safe = input || {};
  switch (toolName) {
    case "get-flags":
      return safe.flagKey ? "get-flags#flagKey" : toolName;
    case "get-agent-configs":
      if (!safe.configKey) return toolName;
      if (safe.section === "health") return "get-agent-configs#health";
      if (safe.section === "status") return "get-agent-configs#status";
      return "get-agent-configs#configKey";
    case "get-ai-tools":
      return safe.toolKey ? "get-ai-tools#toolKey" : toolName;
    case "get-projects":
      return safe.projectKey ? "get-projects#projectKey" : toolName;
    case "get-flag-release-plans":
      return safe.flagReleasePlanKey ? "get-flag-release-plans#flagReleasePlanKey" : toolName;
    case "get-automations":
      if (safe.section === "cleanup") return "get-automations#cleanup";
      if (safe.section === "archival") return "get-automations#archival";
      return toolName;
    case "get-experiments":
      return safe.experimentKey ? "get-experiments#experimentKey" : toolName;
    case "create-agent-config":
      if (safe.resource === "variation") {
        return safe.sourceVariationKey
          ? "create-agent-config#variation-clone"
          : "create-agent-config#variation";
      }
      return safe.variationKey ? "create-agent-config#with-variation" : toolName;
    case "update-agent-config":
      if (safe.resource === "variation") return "update-agent-config#variation";
      if (safe.resource === "targeting") return "update-agent-config#targeting";
      return toolName;
    case "delete-agent-config":
      return safe.resource === "variation" ? "delete-agent-config#variation" : toolName;
    default:
      return toolName;
  }
}

/**
 * Render a mock response for `toolName` given `input` (raw tool arguments).
 * `state` is the per-invocation map from `createMockState()`.
 * `templates` is the full parsed mocks/tool-responses.json.
 */
function mergeDeep(base, patch) {
  const out = { ...(base || {}) };
  for (const [k, v] of Object.entries(patch || {})) {
    out[k] = v && typeof v === "object" && !Array.isArray(v) ? mergeDeep(out[k], v) : v;
  }
  return out;
}

// Release Autopilot settings and release plans: writes are recorded so that
// later reads (the skill's verify step) reflect them instead of the template.
// The API's step limits: every allocation is at most 99000 (99%), and a plan
// with metrics (a guarded plan) caps every step at 50000 (50%).
function releasePlanStepError(progressiveRelease) {
  const pr = progressiveRelease || {};
  const guarded = Object.keys(pr.metrics || {}).length > 0;
  const max = guarded ? 50000 : 99000;
  for (const phase of pr.phases || []) {
    for (const step of phase.steps || []) {
      if (!(step.allocation > 0) || step.allocation > max) {
        return `LaunchDarkly API error: 400: {"code":"invalid_request","message":"step allocation ${step.allocation} is out of range: ` +
          `${guarded ? "a release plan with metrics allows at most 50000 per step" : "at most 99000 per step"}"}`;
      }
    }
  }
  return null;
}

// Flag release plans, like the hosted MCP tools (mcp #522). The template (or a
// test's override) is the project's list: { flagReleasePlans: [...] }. A
// project with no stored plans lists the built-in default-release-configuration,
// which is not stored: a get, update, or delete by its key is a 404. Writes
// start from the stored plans the agent last saw (the first list read), and
// later reads reflect them.
const BUILTIN_FLAG_RELEASE_PLAN = "default-release-configuration";
const FLAG_RELEASE_PLAN_FIELDS = ["name", "description", "maintainer", "executionMode", "applicationKeys", "default", "environments"];
const flagPlanNotFound = (key) => ({ error: `LaunchDarkly API error: 404: {"code":"not_found","message":"flag release plan ${key} not found"}` });

function flagPlanItems(base) {
  if (!base || typeof base !== "object") return [];
  if (Array.isArray(base.flagReleasePlans)) return base.flagReleasePlans;
  if (Array.isArray(base.items)) return base.items;
  return base.key ? [base] : [];
}
const storedFlagPlans = (items) => items.filter((p) => p.key !== BUILTIN_FLAG_RELEASE_PLAN);

function renderFlagReleasePlans(template, args, toolName, state, replacements) {
  const project = args.projectKey;
  const written = state.raFlagPlans[project];
  const current = () => written || state.raFlagSeen[project] || [];
  if (toolName === "get-flag-release-plans") {
    const base = walk(template, replacements);
    if (base && base.error) return base;
    const items = flagPlanItems(base);
    if (!state.raFlagSeen[project]) state.raFlagSeen[project] = storedFlagPlans(items).map((p) => ({ ...p }));
    const stored = written || storedFlagPlans(items);
    if (args.flagReleasePlanKey) {
      const plan = args.flagReleasePlanKey === BUILTIN_FLAG_RELEASE_PLAN ? undefined : stored.find((p) => p.key === args.flagReleasePlanKey);
      return plan ? { ...plan } : flagPlanNotFound(args.flagReleasePlanKey);
    }
    const builtin = items.filter((p) => p.key === BUILTIN_FLAG_RELEASE_PLAN);
    const list = stored.length ? stored : (builtin.length ? builtin : [{ key: BUILTIN_FLAG_RELEASE_PLAN, name: "Default release configuration", default: true, environments: [] }]);
    return { flagReleasePlans: list.map((p) => ({ ...p })), totalCount: list.length, hasMore: false };
  }
  if (toolName === "create-flag-release-plan") {
    const plans = current();
    if (!args.key || !String(args.name || "").trim() || !Array.isArray(args.environments) || args.environments.length === 0) {
      return { error: "invalid input: key, name, and environments are required" };
    }
    if (plans.some((p) => p.key === args.key)) {
      return { error: `invalid input: flag release plan key "${args.key}" is already in use in project "${project}". Pick another key, or inspect the existing plan with get-flag-release-plans and flagReleasePlanKey.` };
    }
    if (args.default === true && plans.some((p) => p.default === true)) {
      return { error: `LaunchDarkly API error: 400: {"code":"invalid_request","message":"project ${project} already has a default flag release plan"}` };
    }
    const plan = { key: args.key, version: 1, name: args.name, default: args.default === true, executionMode: args.executionMode || "sequential",
      applicationKeys: args.applicationKeys || [], environments: args.environments };
    if (args.description !== undefined) plan.description = args.description;
    if (args.maintainer !== undefined) plan.maintainer = args.maintainer;
    state.raFlagPlans[project] = [...plans.map((p) => ({ ...p })), plan];
    return { ...plan };
  }
  if (toolName === "update-flag-release-plan" || toolName === "delete-flag-release-plan") {
    if (args.confirm !== true) {
      return { error: `Expected arguments for ${toolName}: required: projectKey, flagReleasePlanKey, confirm=true.` };
    }
    const key = args.flagReleasePlanKey;
    const plans = current().map((p) => ({ ...p }));
    const at = key === BUILTIN_FLAG_RELEASE_PLAN ? -1 : plans.findIndex((p) => p.key === key);
    if (at === -1) return flagPlanNotFound(key);
    if (toolName === "delete-flag-release-plan") {
      plans.splice(at, 1);
      state.raFlagPlans[project] = plans;
      return { deleted: true, flagReleasePlanKey: key };
    }
    const changes = {};
    for (const field of FLAG_RELEASE_PLAN_FIELDS) if (args[field] !== undefined) changes[field] = args[field];
    if (Object.keys(changes).length === 0) {
      return { error: `invalid input: provide at least one field to update: ${FLAG_RELEASE_PLAN_FIELDS.join(", ")}` };
    }
    if (changes.default === true) for (const p of plans) p.default = false;
    plans[at] = { ...plans[at], ...changes, version: (plans[at].version || 1) + 1 };
    state.raFlagPlans[project] = plans;
    return { ...plans[at] };
  }
  return undefined;
}

function renderReleaseAutopilot(template, input, toolName, state, replacements) {
  const args = input || {};
  if (/flag-release-plan/.test(toolName)) return renderFlagReleasePlans(template, args, toolName, state, replacements);
  if (toolName === "update-automations") {
    const { accountWide, repo, githubRepoId, confirm, ...rest } = args;
    // A project's auto-cleanup or auto-archival (projectKey with a cleanup or
    // archival object, no repo). Archival cannot be turned on by an agent.
    if (!repo && githubRepoId === undefined && args.projectKey && (args.cleanup || args.archival)) {
      const key = args.projectKey;
      if (args.cleanup) {
        state.raCleanup[key] = mergeDeep(state.raCleanup[key], args.cleanup);
        return { projectKey: key, changed: Object.keys(args.cleanup), settings: { ...state.raCleanup[key] } };
      }
      const current = state.raArchival[key] || {};
      if (args.archival.enabled === true && !current.enabled) {
        return { projectKey: key, changed: [], automationsPage: `/projects/${key}/settings/automations`,
          note: "Automatic archival is off. Turning it on needs a person on the Automations page." };
      }
      state.raArchival[key] = mergeDeep(current, args.archival);
      return { projectKey: key, changed: Object.keys(args.archival), settings: { ...state.raArchival[key] } };
    }
    if (accountWide === true) {
      state.raSettings = mergeDeep(state.raSettings, rest);
      return { ...state.raSettings };
    }
    if (repo) {
      state.raRepos[repo] = mergeDeep(state.raRepos[repo] || { repo }, rest);
      return { ...state.raRepos[repo] };
    }
    return undefined;
  }
  if (toolName === "get-automations" && (args.section === "cleanup" || args.section === "archival")) {
    const base = walk(template, replacements);
    if (!base || base.error) return base;
    const written = (args.section === "cleanup" ? state.raCleanup : state.raArchival)[args.projectKey];
    return written ? { ...base, settings: mergeDeep(base.settings, written) } : base;
  }
  if (toolName === "get-automations") {
    const base = walk(template, replacements);
    if (!base || base.error) return base;
    const account = mergeDeep(base.account, state.raSettings);
    const known = new Set((base.repos || []).map((r) => r.repo));
    let repos = (base.repos || []).map((r) =>
      state.raRepos[r.repo] ? mergeDeep(r, { ...state.raRepos[r.repo], mapped: true }) : r,
    );
    for (const [name, written] of Object.entries(state.raRepos)) {
      if (!known.has(name)) repos.push({ ...written, repo: name, mapped: true, visibleOnInstall: true });
    }
    if (args.githubRepoId !== undefined) repos = repos.filter((r) => r.githubRepoId === args.githubRepoId);
    else if (args.repo) repos = repos.filter((r) => r.repo === args.repo);
    if (typeof args.mapped === "boolean") repos = repos.filter((r) => r.mapped === args.mapped);
    return { ...base, account, repos, totalCount: repos.length, hasMore: false };
  }
  if ((toolName === "create-release-plan" || toolName === "create-environment-release-plan") && args.environmentKey) {
    const invalid = releasePlanStepError(args.progressiveRelease);
    if (invalid) return { error: invalid };
    const plan = { key: args.key, name: args.name, environmentKey: args.environmentKey, progressiveRelease: args.progressiveRelease };
    (state.raPlans[args.environmentKey] = state.raPlans[args.environmentKey] || []).push(plan);
    return plan;
  }
  // The list is the template's plans plus the plans created this run. A
  // default set this run (on an existing or a new plan) replaces the
  // template's default flags.
  if ((toolName === "get-release-plans" || toolName === "get-environment-release-plans") &&
      (state.raPlans[args.environmentKey] || state.raDefaults[args.environmentKey] !== undefined)) {
    const base = walk(template, replacements);
    if (base && base.error) return base;
    const created = state.raPlans[args.environmentKey] || [];
    const createdKeys = new Set(created.map((p) => p.key));
    const existing = ((base && base.items) || []).filter((p) => !createdKeys.has(p.key));
    const def = state.raDefaults[args.environmentKey];
    const items = [...existing, ...created.map((p) => ({ ...p, default: false }))].map((p) =>
      def === undefined ? p : { ...p, default: p.key === def },
    );
    return { ...(base || {}), items, totalCount: items.length };
  }
  if (toolName === "update-default-environment-release-plan" && args.environmentKey) {
    const previous = state.raDefaults[args.environmentKey];
    if (args.default === true) state.raDefaults[args.environmentKey] = args.releasePlanKey;
    else if (previous === args.releasePlanKey) delete state.raDefaults[args.environmentKey];
    return { changed: previous !== state.raDefaults[args.environmentKey], previousDefaultKey: previous || null,
      plan: { key: args.releasePlanKey, environmentKey: args.environmentKey, default: args.default === true } };
  }
  return undefined;
}

function renderMockResponse(template, input, toolName, state) {
  const replacements = buildReplacements(input);
  const mode = templateKey(toolName, input);

  // An error template on a write (for example a 403 override) wins over
  // stateful handling, so the failed write is not recorded. Reads still use
  // state: the unmapped-repo read template is itself a 404 error.
  const failedWrite = /^(update|create|delete)-/.test(toolName) && template && template.error;
  if (state && state.raRepos && !failedWrite) {
    const ra = renderReleaseAutopilot(template, input, toolName, state, replacements);
    if (ra !== undefined) return ra;
  }

  // ---------- stateful reads ----------
  if (mode === "get-agent-configs#configKey") {
    const key = input.configKey;
    if (key) {
      if (!state.configs[key] && SEED_CONFIGS[key]) {
        state.configs[key] = JSON.parse(JSON.stringify(SEED_CONFIGS[key]));
      }
      if (state.configs[key]) return state.configs[key];
    }
  }

  if (mode === "get-agent-configs#status") {
    // A targeting write this run overrides the template's `on` for that
    // environment, so re-reading status after turning targeting off agrees.
    const written = (state.targeting || {})[input.configKey];
    const out = walk(template, replacements);
    if (written && out && out.environments) {
      for (const [env, on] of Object.entries(written)) {
        if (out.environments[env]) out.environments[env] = { ...out.environments[env], on };
      }
    }
    return out;
  }

  if (mode === "get-agent-configs#health") {
    const key = input.configKey;
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

  if (mode === "get-agent-configs") {
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

  if (mode === "get-flags#flagKey") {
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
  if (mode === "create-agent-config#with-variation") {
    const cfg = {
      key: input.configKey,
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
    state.configs[input.configKey] = cfg;
    return cfg;
  }

  if (mode === "create-agent-config") {
    const cfg = {
      key: input.configKey,
      name: input.name,
      mode: input.mode,
      description: input.description || "",
      tags: input.tags || [],
      archived: false,
      variations: [],
    };
    state.configs[input.configKey] = cfg;
    return cfg;
  }

  if (mode === "create-agent-config#variation") {
    const cfg = state.configs[input.configKey];
    const variation = {
      key: input.variationKey,
      name: input.variationName,
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
      // is reachable via get-agent-configs. The real API
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

  if (mode === "update-agent-config") {
    // The server rejects archived: an AgentControl Config cannot be archived.
    if (input.archived !== undefined) {
      return {
        error: "invalid_input",
        status: 400,
        message:
          "archived is not supported: an AgentControl Config cannot be archived. " +
          "Delete it with delete-agent-config resource=config and confirm=true",
      };
    }
    const cfg = state.configs[input.configKey];
    if (cfg) {
      const CONFIG_FIELDS = [
        "name", "description", "tags", "defaultVariationKey",
        "evaluationMetricKey", "isInverted", "maintainerId", "maintainerTeamKey",
      ];
      for (const k of CONFIG_FIELDS) {
        if (input[k] !== undefined) cfg[k] = input[k];
      }
      return { ...cfg };
    }
    return walk(template, replacements);
  }

  if (mode === "update-agent-config#targeting" && !failedWrite && input.env && typeof input.on === "boolean") {
    state.targeting = state.targeting || {};
    (state.targeting[input.configKey] = state.targeting[input.configKey] || {})[input.env] = input.on;
    return walk(template, replacements);
  }

  if (mode === "update-agent-config#variation") {
    const cfg = state.configs[input.configKey];
    if (cfg) {
      const VARIATION_FIELDS = [
        "modelConfigKey", "modelName",
        "instructions", "messages", "parameters", "tools", "status",
      ];
      cfg.variations = (cfg.variations || []).map((v) => {
        if (v.key !== input.variationKey) return v;
        const patch = {};
        for (const k of VARIATION_FIELDS) {
          if (input[k] !== undefined) patch[k] = input[k];
        }
        if (input.variationName !== undefined) patch.name = input.variationName;
        return { ...v, ...patch };
      });
    }
    return walk(template, replacements);
  }

  if (mode === "create-agent-config#variation-clone") {
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
          key: input.variationKey,
          name: input.variationName !== undefined ? input.variationName : sourceVariation.name,
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

  if (mode === "create-flag") {
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

  if (toolName === "get-metric-events") {
    const query = typeof (input || {}).query === "string" ? input.query.trim().toLowerCase() : "";
    if (query === "cta-clicked") return similarCtaMetricEvents(template, replacements);
  }

  if (mode === "get-flags") {
    // experiment-setup's missing-flag case uses this project. Any list call there
    // returns the similar keys and omits the missing one. Other projects keep
    // the template they were given.
    const projectKey =
      typeof (input || {}).projectKey === "string" ? input.projectKey.trim() : "";
    if (projectKey === "exp-setup-missing-flag") return similarCheckoutFlags();
  }

  if (toolName === "get-experiments") {
    const experimentKey = input.experimentKey || input.key;
    if (experimentKey === "checkout-running") return runningExperiment(input);
  }

  // Default: stateless template render
  return walk(template, replacements);
}

/**
 * Pick a test's override for `toolName`, if the test set one through the
 * `mock_overrides` var. An object value answers every call; an array answers
 * successive calls in order and repeats its last entry. An object with
 * `by_arg` answers by the value of that tool argument: `cases[value]`, else
 * `default`. Returns undefined when the test has no override for the call, so
 * the caller falls back to the shared template.
 */
function resolveMockOverride(overrides, toolName, callIndex, args) {
  if (!overrides || typeof overrides !== "object") return undefined;
  if (!Object.prototype.hasOwnProperty.call(overrides, toolName)) return undefined;
  const value = overrides[toolName];
  if (Array.isArray(value)) {
    if (value.length === 0) return undefined;
    return value[Math.min(callIndex, value.length - 1)];
  }
  if (value && typeof value === "object" && typeof value.by_arg === "string") {
    const key = args ? args[value.by_arg] : undefined;
    const cases = value.cases || {};
    if (key !== undefined && Object.prototype.hasOwnProperty.call(cases, key)) return cases[key];
    return value.default;
  }
  return value;
}

/**
 * The `mock_overrides` key that answers this call, or undefined. A mode key
 * (`<tool>#<mode>`, see templateKey) wins. A plain tool-name key answers
 * every mode, except the get-automations cleanup and archival sections: a
 * test's repos/account payload for get-automations must not replace those
 * section templates. A `by_arg: section` override still answers them.
 */
function overrideKey(overrides, toolName, args) {
  if (!overrides || typeof overrides !== "object") return undefined;
  const has = (k) => Object.prototype.hasOwnProperty.call(overrides, k);
  const mode = templateKey(toolName, args);
  if (mode !== toolName && has(mode)) return mode;
  if (toolName === "get-automations" && mode !== toolName) {
    const plain = overrides[toolName];
    return plain && plain.by_arg === "section" ? toolName : undefined;
  }
  return has(toolName) ? toolName : undefined;
}

/**
 * The key a call is counted under for array overrides: the override key that
 * answers it, else its template key. A get-automations section read then has
 * its own counter and does not advance a tool-name array override.
 */
function callCountKey(overrides, toolName, args) {
  return overrideKey(overrides, toolName, args) || templateKey(toolName, args);
}

/**
 * Render an override with the same `{{placeholder}}` substitution as the
 * shared templates, but without the stateful overlay: an override is exactly
 * what the test wants the tool to return.
 */
function renderOverride(template, input) {
  return walk(template, buildReplacements(input));
}

module.exports = {
  renderMockResponse,
  createMockState,
  resolveMockOverride,
  overrideKey,
  callCountKey,
  renderOverride,
  templateKey,
};
