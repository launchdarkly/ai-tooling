/**
 * A local stand-in for the LaunchDarkly REST API, for skills that call it
 * with curl (the flag release plan endpoints have no MCP tool).
 *
 * The provider starts one server per test on 127.0.0.1 and points the agent's
 * shell at it with LD_BASE_URI, with a fake LD_ACCESS_TOKEN, so no request
 * from an eval reaches a real account. Every request is recorded into the
 * trajectory as tool "ld-api" with its method, path, query, the
 * LD-API-Version header, whether the Authorization header matched, and the
 * parsed JSON body. The token value is never recorded.
 *
 * Routes follow gonfalon's automated_rollout_configs api.yaml:
 *   GET        /api/v2/projects/{p}/environments/{e}/release-plans (seeded)
 *   GET        /api/v2/projects/{p}/environments/{e}/default-release-plan (seeded)
 *   GET/POST   /api/v2/projects/{p}/flag-release-plans
 *   GET/PUT/DELETE /api/v2/projects/{p}/flag-release-plans/{key}
 *   POST       /api/v2/projects/{p}/flags/{f}/flag-releases
 * and the validation rules of the releases service: key pattern, the release
 * plan or isImmediate rule, trigger rules, one default per project, 409 on a
 * taken key or a stale version. A request without `LD-API-Version: beta` gets
 * a 400 here; that is this mock's rule, so a test catches a missing header.
 *
 * Per-test vars the provider passes in:
 *   ld_api_state.flagReleasePlans         - seed plans (FlagReleasePlan shape)
 *   ld_api_state.environmentReleasePlans  - { envKey: [planKey, ...] } that exist;
 *                                           the first is the environment's default
 *   ld_api_overrides                      - { "<METHOD> <route>": response or
 *     [responses] } where route is flag-release-plans, flag-release-plan, or
 *     flag-releases, and a response is { status, body }. An array answers
 *     successive calls; the last entry repeats. A null entry answers normally.
 */

const http = require("node:http");
const crypto = require("node:crypto");

const KEY_PATTERN = /^[a-zA-Z0-9][._\-a-zA-Z0-9]*$/;
const TRIGGERS = new Set(["flag_eval", "webhook", "manual", "promotion"]);
const MODES = new Set(["sequential", "parallel"]);
const MAX_PLANS = 100;

const clone = (v) => JSON.parse(JSON.stringify(v));
const err = (status, code, message) => ({ status, body: { code, message } });

function normalizePlan(p) {
  return {
    key: p.key,
    _id: p._id || crypto.randomUUID(),
    version: p.version || 1,
    name: p.name,
    ...(p.description ? { description: p.description } : {}),
    isDefault: Boolean(p.isDefault),
    executionMode: p.executionMode || "sequential",
    applicationKeys: p.applicationKeys || [],
    environments: (p.environments || []).map((e) => ({
      environmentKey: e.environmentKey,
      ...(e.environmentReleasePlanKey ? { environmentReleasePlanKey: e.environmentReleasePlanKey } : {}),
      isImmediate: Boolean(e.isImmediate),
      triggerType: e.triggerType || "flag_eval",
    })),
  };
}

/**
 * State for one test. `envPlanExists(envKey, planKey)` decides whether an
 * environment release plan exists; the provider adds the plans the MCP mocks
 * created this run to the seeded ones.
 */
function createLdApiState(seed = {}, envPlanExists) {
  const seededEnvPlans = seed.environmentReleasePlans || {};
  return {
    seededEnvPlans,
    plans: (seed.flagReleasePlans || []).map(normalizePlan),
    flagReleases: [],
    callCounts: {},
    envPlanExists: (env, key) =>
      (seededEnvPlans[env] || []).includes(key) || Boolean(envPlanExists && envPlanExists(env, key)),
  };
}

function routeOf(method, path) {
  let m = path.match(/^\/api\/v2\/projects\/([^/]+)\/environments\/([^/]+)\/(release-plans|default-release-plan)\/?$/);
  if (m && method === "GET") return { route: m[3], projectKey: decodeURIComponent(m[1]), environmentKey: decodeURIComponent(m[2]) };
  m = path.match(/^\/api\/v2\/projects\/([^/]+)\/flag-release-plans\/?$/);
  if (m) return { route: "flag-release-plans", projectKey: decodeURIComponent(m[1]) };
  m = path.match(/^\/api\/v2\/projects\/([^/]+)\/flag-release-plans\/([^/]+)\/?$/);
  if (m) return { route: "flag-release-plan", projectKey: decodeURIComponent(m[1]), planKey: decodeURIComponent(m[2]) };
  m = path.match(/^\/api\/v2\/projects\/([^/]+)\/flags\/([^/]+)\/flag-releases\/?$/);
  if (m && method === "POST") return { route: "flag-releases", projectKey: decodeURIComponent(m[1]), flagKey: decodeURIComponent(m[2]) };
  return null;
}

function validatePlanBody(state, body) {
  if (!body || typeof body !== "object") return err(400, "invalid_request", "request body is required");
  if (!body.name) return err(400, "invalid_request", "name is required");
  if (String(body.name).length > 256) return err(400, "invalid_request", "name must be at most 256 characters");
  if (body.executionMode !== undefined && !MODES.has(body.executionMode)) {
    return err(400, "invalid_request", `executionMode ${JSON.stringify(body.executionMode)} is not valid`);
  }
  const mode = body.executionMode || "sequential";
  const envs = body.environments;
  if (!Array.isArray(envs) || envs.length === 0) return err(400, "invalid_request", "at least one environment is required");
  if (envs.length > 50) return err(400, "invalid_request", "a flag release plan can have at most 50 environments");
  const seen = new Set();
  for (let i = 0; i < envs.length; i++) {
    const e = envs[i] || {};
    const key = e.environmentKey;
    if (!key) return err(400, "invalid_request", "environmentKey is required for each environment");
    if (seen.has(key)) return err(400, "invalid_request", `environment_key "${key}" must appear only once`);
    seen.add(key);
    if (!TRIGGERS.has(e.triggerType)) return err(400, "invalid_request", `environments[${i}].triggerType is required and must be one of flag_eval, webhook, manual, promotion`);
    if ((e.triggerType === "manual" || e.triggerType === "promotion") && mode !== "sequential") {
      return err(400, "invalid_request", `trigger_type ${e.triggerType} is only supported for sequential configs`);
    }
    if (e.triggerType === "promotion" && i === 0) {
      return err(400, "invalid_request", "the first sequential environment must not use trigger_type TRIGGER_TYPE_PROMOTION");
    }
    if (e.isImmediate) {
      if (e.environmentReleasePlanKey) {
        return err(400, "invalid_request", `environment "${key}" must not set environment_release_plan_key when is_immediate is true`);
      }
      continue;
    }
    if (!e.environmentReleasePlanKey) {
      return err(400, "invalid_request", `environment "${key}" needs an environment_release_plan_key unless is_immediate is true`);
    }
    if (!state.envPlanExists(key, e.environmentReleasePlanKey)) {
      return err(400, "invalid_request", `environment release plan "${e.environmentReleasePlanKey}" doesn't exist in this project`);
    }
  }
  return null;
}

function overrideFor(state, overrides, name) {
  if (!overrides || overrides[name] === undefined) return undefined;
  const i = state.callCounts[name] || 0;
  state.callCounts[name] = i + 1;
  const o = overrides[name];
  return Array.isArray(o) ? o[Math.min(i, o.length - 1)] : o;
}

/**
 * Answer one request. `req` is { method, path, query, headers, body } with
 * lower-case header names and a parsed body (or undefined). Returns
 * { status, body }.
 */
function handleLdApiRequest(state, req, { token, overrides } = {}) {
  const r = routeOf(req.method, req.path);
  if (!r) return err(404, "not_found", `no route for ${req.method} ${req.path} in the eval API mock`);
  if (!token || req.headers.authorization !== token) return err(401, "unauthorized", "Invalid access token");
  if (req.headers["ld-api-version"] !== "beta") {
    return err(400, "invalid_request", "this endpoint is in beta: send the LD-API-Version: beta header");
  }
  const forced = overrideFor(state, overrides, `${req.method} ${r.route}`);
  if (forced !== undefined && forced !== null) return { status: forced.status || 200, body: forced.body };

  if (r.route === "release-plans" || r.route === "default-release-plan") {
    const keys = state.seededEnvPlans[r.environmentKey] || [];
    const items = keys.map((key, i) => ({ key, name: key, environmentKey: r.environmentKey, releaseMethod: "progressive_release", version: 1, default: i === 0 }));
    if (r.route === "default-release-plan") {
      return items.length ? { status: 200, body: items[0] } : err(404, "not_found", "no default release plan");
    }
    return { status: 200, body: { items, totalCount: items.length } };
  }

  const body = req.body;
  if (r.route === "flag-release-plans" && req.method === "GET") {
    const limit = Math.min(50, Math.max(1, Number(req.query.limit) || 25));
    const offset = Math.max(0, Number(req.query.offset) || 0);
    return { status: 200, body: { items: clone(state.plans.slice(offset, offset + limit)), totalCount: state.plans.length, _links: { self: { href: req.path } } } };
  }
  if (r.route === "flag-release-plans" && req.method === "POST") {
    if (!body || !body.key) return err(400, "invalid_request", "key is required");
    if (String(body.key).length > 256 || !KEY_PATTERN.test(body.key)) return err(400, "invalid_request", `key "${body.key}" is not a valid key`);
    const invalid = validatePlanBody(state, body);
    if (invalid) return invalid;
    if (state.plans.some((p) => p.key === body.key)) {
      return err(409, "conflict", "a flag release plan with this key already exists in this project");
    }
    if (body.isDefault && state.plans.some((p) => p.isDefault)) {
      return err(400, "invalid_request", "this project already has a default flag release plan; unset it before making another plan the default");
    }
    if (state.plans.length >= MAX_PLANS) return err(400, "invalid_request", `this project already has the maximum of ${MAX_PLANS} active flag release plans`);
    const plan = normalizePlan({ ...body, version: 1, _id: undefined });
    state.plans.push(plan);
    return { status: 201, body: clone(plan) };
  }
  if (r.route === "flag-release-plan") {
    const idx = state.plans.findIndex((p) => p.key === r.planKey);
    if (idx === -1) return err(404, "not_found", "flag release plan not found");
    const current = state.plans[idx];
    if (req.method === "GET") return { status: 200, body: clone(current) };
    if (req.method === "DELETE") {
      state.plans.splice(idx, 1);
      return { status: 204, body: undefined };
    }
    if (req.method === "PUT") {
      const invalid = validatePlanBody(state, body);
      if (invalid) return invalid;
      if (body.version !== undefined && body.version !== current.version) {
        return err(409, "conflict", "the flag release plan changed since it was read: the request's version no longer matches the plan's current version; get the plan again and retry with its current version");
      }
      // Full replace: anything omitted is cleared, including isDefault.
      const next = normalizePlan({ ...body, key: current.key, _id: current._id, version: current.version + 1 });
      if (next.isDefault) for (const p of state.plans) p.isDefault = false;
      state.plans[idx] = next;
      return { status: 200, body: clone(next) };
    }
    return err(405, "method_not_allowed", `${req.method} is not allowed here`);
  }
  if (r.route === "flag-releases") {
    if (!body || (body.kind !== "plan" && body.kind !== "custom")) return err(400, "invalid_request", "kind is required");
    if (body.kind === "plan" && !state.plans.some((p) => p.key === body.planKey)) {
      return err(400, "invalid_request", `flag release plan "${body.planKey}" does not exist`);
    }
    const id = crypto.randomUUID();
    state.flagReleases.push({ id, flagKey: r.flagKey, ...clone(body) });
    return { status: 201, body: { id } };
  }
  return err(405, "method_not_allowed", `${req.method} is not allowed here`);
}

/**
 * Start the server. `record(entry)` gets one trajectory entry per request.
 * Resolves to { baseUri, close }.
 */
function startLdApiMock({ state, token, overrides, record }) {
  const server = http.createServer((request, response) => {
    const chunks = [];
    request.on("data", (c) => chunks.push(c));
    request.on("end", () => {
      const url = new URL(request.url, "http://127.0.0.1");
      const raw = Buffer.concat(chunks).toString("utf-8");
      let body;
      let parseError = false;
      if (raw) {
        try {
          body = JSON.parse(raw);
        } catch {
          parseError = true;
        }
      }
      const req = {
        method: request.method,
        path: url.pathname,
        query: Object.fromEntries(url.searchParams),
        headers: request.headers,
        body,
      };
      const out = parseError
        ? err(400, "invalid_request", "request body is not valid JSON")
        : handleLdApiRequest(state, req, { token, overrides });
      if (record) {
        record({
          method: req.method,
          path: req.path,
          query: req.query,
          apiVersion: request.headers["ld-api-version"] || null,
          authorized: Boolean(token) && request.headers.authorization === token,
          body: parseError ? raw : body,
          status: out.status,
          response: out.body,
        });
      }
      const text = out.body === undefined ? "" : JSON.stringify(out.body);
      response.writeHead(out.status, text ? { "Content-Type": "application/json" } : {});
      response.end(text);
    });
  });
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      resolve({
        baseUri: `http://127.0.0.1:${port}`,
        close: () => new Promise((done) => server.close(() => done())),
      });
    });
  });
}

module.exports = { createLdApiState, handleLdApiRequest, startLdApiMock, normalizePlan };
