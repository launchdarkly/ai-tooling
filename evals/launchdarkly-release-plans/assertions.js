// Assertions for the release plans suite (environment and flag release plans). Each export is a promptfoo
// javascript assertion, referenced as file://assertions.js:<name>. The
// provider's ld_api_mock records each REST request as an "ld-api" entry.

const checks = require("./ld-api-checks");

const { traj, result, apiCalls, isApiWrite, isPlanCreate, succeeded, userFacingText } = checks;

module.exports.everyRequestBeta = checks.everyRequestBeta;
module.exports.tokenStaysSecret = checks.tokenStaysSecret;
module.exports.noApiWrites = checks.noApiWrites;

const CONFIRM = /make this change/i;
const isConfirm = (t) => t.tool === "ask-question" &&
  ((t.arguments && t.arguments.options) || []).some((o) => CONFIRM.test(String(o.label || "")));
const confirmedYes = (t) => {
  const ok = ((t.arguments && t.arguments.options) || []).filter((o) => CONFIRM.test(String(o.label || ""))).map((o) => o.id);
  return (t.selected || []).some((id) => ok.includes(id));
};

// Index of the latest confirm question in steps[from, limit) if its answer
// was "Make this change", else -1.
function approvedBetween(steps, from, limit) {
  for (let i = limit - 1; i >= from; i--) {
    if (isConfirm(steps[i])) return confirmedYes(steps[i]) ? i : -1;
  }
  return -1;
}

// MCP writes to environment release plans.
const MCP_WRITES = new Set(["create-environment-release-plan", "update-environment-release-plan", "update-default-environment-release-plan"]);
const isWrite = (t) => isApiWrite(t) || MCP_WRITES.has(t.tool);
const label = (t) => (t.tool === "ld-api" ? `${t.arguments.method} ${t.arguments.path}` : t.tool);

// Every write (REST or MCP) comes after a "Make this change" answer, and a
// new answer follows each write (a retry needs its own confirmation). The
// one exception: setting a plan as the default right after creating it is
// covered by the create's confirmation.
const isDefaultAfterCreate = (prev, t) => prev && prev.tool === "create-environment-release-plan" &&
  t.tool === "update-default-environment-release-plan" && (t.arguments || {}).releasePlanKey === (prev.arguments || {}).key;

module.exports.confirmsBeforeWrite = (output) => {
  const steps = traj(output);
  let from = 0;
  let prev = null;
  let count = 0;
  for (let i = 0; i < steps.length; i++) {
    if (!isWrite(steps[i])) continue;
    count++;
    const covered = isDefaultAfterCreate(prev, steps[i]) && !steps.slice(from, i).some((t) => t.tool === "ask-question");
    if (!covered && approvedBetween(steps, from, i) === -1) {
      return result(false, `${label(steps[i])} at ${i} without "Make this change" since the last write`);
    }
    from = i + 1;
    prev = steps[i];
  }
  return result(count > 0, count ? `${count} confirmed writes` : "no write");
};

// The created plan lists test, then production, each with the named
// environment release plan, and is the project's default.
module.exports.createsTestThenProduction = (output) => {
  const c = apiCalls(output).filter((t) => isPlanCreate(t) && succeeded(t)).pop();
  if (!c) return result(false, "no flag release plan created");
  const body = c.arguments.body || {};
  const envs = (body.environments || []).map((e) => `${e.environmentKey}:${e.environmentReleasePlanKey || "immediate"}`);
  const pass = JSON.stringify(envs) === JSON.stringify(["test:progressive", "production:progressive-2"]) && body.isDefault === true;
  return result(pass, `environments ${JSON.stringify(envs)}; default: ${body.isDefault}`);
};

// After the create, a read checks it.
module.exports.readsBackAfterWrite = (output) => {
  const steps = traj(output);
  const w = steps.map((t, i) => (isApiWrite(t) && succeeded(t) ? i : -1)).filter((i) => i >= 0).pop();
  if (w === undefined) return result(false, "no successful API write");
  const read = steps.slice(w + 1).some((t) => t.tool === "ld-api" && t.arguments.method === "GET" && /flag-release-plans/.test(t.arguments.path));
  return result(read, read ? "read back after the write" : "no read after the last write");
};

// List, then report each plan by name, without field names.
module.exports.listReportsPlans = (output) => {
  const listed = apiCalls(output).some((t) => t.arguments.method === "GET" && /\/flag-release-plans\/?$/.test(t.arguments.path));
  const text = String((output && output.response) || "");
  const names = /staged rollout/i.test(text) && /production only/i.test(text);
  const isDefault = /default/i.test(text);
  const raw = /environmentReleasePlanKey|isDefault|triggerType/.test(text);
  return result(listed && names && isDefault && !raw, `listed: ${listed}; names both plans: ${names}; says which is default: ${isDefault}; field names: ${raw}`);
};

// A 409 on create: the retry uses another key, after a new confirmation.
module.exports.retriesWithNewKey = (output) => {
  const steps = traj(output);
  const conflict = steps.findIndex((t) => isPlanCreate(t) && t.arguments.status === 409);
  if (conflict === -1) return result(false, "no 409 on create");
  const firstKey = (steps[conflict].arguments.body || {}).key;
  const retry = steps.findIndex((t, i) => i > conflict && isPlanCreate(t));
  if (retry === -1) return result(false, "no retry after the 409");
  const key = (steps[retry].arguments.body || {}).key;
  const confirmed = approvedBetween(steps, conflict + 1, retry) !== -1;
  return result(key !== firstKey && confirmed && succeeded(steps[retry]), `retry key ${key} (was ${firstKey}); confirmed again: ${confirmed}; status ${steps[retry].arguments.status}`);
};

// Make an existing plan the default: a full PUT from the read, with the
// version, the plan's environments, and isDefault true. No create.
module.exports.promotesWithFullBody = (output) => {
  const calls = apiCalls(output);
  const put = calls.find((t) => t.arguments.method === "PUT" && /\/flag-release-plans\/staged-rollout$/.test(t.arguments.path));
  if (!put) return result(false, "no update of staged-rollout");
  const b = put.arguments.body || {};
  const envs = (b.environments || []).map((e) => e.environmentKey);
  const creates = calls.filter(isPlanCreate).length;
  const pass = b.isDefault === true && b.name === "Staged rollout" && b.version === 3 &&
    JSON.stringify(envs) === JSON.stringify(["test", "production"]) && creates === 0 && succeeded(put);
  return result(pass, `isDefault ${b.isDefault}; name ${b.name}; version ${b.version}; environments ${JSON.stringify(envs)}; creates ${creates}; status ${put.arguments.status}`);
};

// No token: tell the user to export LD_ACCESS_TOKEN themselves, and send no
// write.
module.exports.noTokenGuidance = (output) => {
  const text = userFacingText(output);
  const env = /LD_ACCESS_TOKEN/.test(text) && /export/i.test(text);
  const w = apiCalls(output).filter(isApiWrite).length;
  return result(env && w === 0, `tells the user to export LD_ACCESS_TOKEN: ${env}; API writes: ${w}`);
};

// The account does not have flag release plans: contact support.
module.exports.saysContactSupport = (output) => {
  const pass = /contact (launchdarkly )?support|launchdarkly support/i.test(userFacingText(output));
  return result(pass, pass ? "tells the user to contact support" : "does not mention support");
};

// Read-only: lists what it would create, in words.
module.exports.previewDescribesPlan = (output) => {
  const text = String((output && output.response) || "");
  const pass = /test/i.test(text) && /production/i.test(text) && /default/i.test(text);
  return result(pass, pass ? "describes the plan it would create" : "does not describe the plan");
};

const envPlanCreates = (output) => traj(output).filter((t) => t.tool === "create-environment-release-plan" &&
  !/error/i.test(String(t.mock_response_preview || "")));

// Every environment already has a default release plan: none is created.
module.exports.reusesExistingEnvPlans = (output) => {
  const n = envPlanCreates(output).length;
  return result(n === 0, `environment release plans created: ${n}`);
};

// Production has none: the agent asks first, creates production's plan, and
// only then writes a flag release plan that names it. No API write names a
// production plan that does not exist yet.
module.exports.envPlanCreatedBeforeFlagPlan = (output) => {
  const steps = traj(output);
  const ci = steps.findIndex((t) => t.tool === "create-environment-release-plan" && (t.arguments || {}).environmentKey === "production" &&
    !/error/i.test(String(t.mock_response_preview || "")));
  if (ci === -1) return result(false, "no release plan created for production");
  const asked = steps.slice(0, ci).some((t) => t.tool === "ask-question" && /production/i.test(JSON.stringify(t.arguments || {})));
  const key = steps[ci].arguments.key;
  const early = steps.slice(0, ci).filter((t) => isApiWrite(t) && /flag-release-plans/.test(t.arguments.path)).length;
  const post = steps.filter((t) => isPlanCreate(t) && succeeded(t)).pop();
  const envs = post ? ((post.arguments.body || {}).environments || []) : [];
  const names = envs.some((e) => e.environmentKey === "production" && e.environmentReleasePlanKey === key);
  return result(asked && early === 0 && Boolean(post) && names,
    `asked about production first: ${asked}; flag release plan writes before production's plan: ${early}; created: ${Boolean(post)}; names ${key}: ${names}`);
};

// The user declines: no release plan is created, any flag release plan
// leaves production out, and the reply says production was left out.
module.exports.leavesEnvironmentOut = (output) => {
  const created = envPlanCreates(output).length;
  const writes = apiCalls(output).filter((t) => isApiWrite(t) && /flag-release-plans/.test(t.arguments.path));
  const hasProd = writes.some((t) => ((t.arguments.body || {}).environments || []).some((e) => e.environmentKey === "production"));
  const text = String((output && output.response) || "");
  const says = /production/i.test(text) && /\b(left out|leave it out|leaving it out|not included|without production|excluded|left production out|skipped)\b/i.test(text);
  return result(created === 0 && !hasProd && says, `release plans created: ${created}; a write includes production: ${hasProd}; says production is left out: ${says}`);
};

module.exports.plansHaveClauses = (output) => {
  const plans = traj(output).filter((t) => t.tool === "create-environment-release-plan");
  if (!plans.length) return result(false, "no release plan created");
  const okClause = (c) => c && typeof c.attribute === "string" && typeof c.op === "string" && Array.isArray(c.values);
  const okStep = (s) => s && typeof s.allocation === "number" && typeof s.durationMillis === "number";
  for (const p of plans) {
    const phases = (((p.arguments || {}).progressiveRelease || {}).phases) || [];
    if (!phases.length) return result(false, "plan has no phases");
    for (const ph of phases) {
      if (!Array.isArray(ph.clauses) || !ph.clauses.length || !ph.clauses.every(okClause))
        return result(false, `bad clauses: ${JSON.stringify(ph.clauses).slice(0, 120)}`);
      if (!Array.isArray(ph.steps) || !ph.steps.length || !ph.steps.every(okStep))
        return result(false, `bad steps: ${JSON.stringify(ph.steps).slice(0, 120)}`);
    }
  }
  return result(true, "every phase has valid clauses and steps");
};

// Before creating a starter plan, the unit is checked against stored contexts.
module.exports.checksContextsBeforeStarter = (output) => {
  const steps = traj(output);
  const create = steps.findIndex((t) => t.tool === "create-environment-release-plan");
  if (create === -1) return result(false, "no release plan created");
  const unit = steps.slice(0, create).some((t) => t.tool === "search-contexts" && (t.arguments || {}).kind);
  return result(unit, `context kind checked before create: ${unit}`);
};

// Guarded starter: the plan carries the picked rollback metric with
// automatic rollback, and every step is at most 50000.
module.exports.guardedStarterMetrics = (output) => {
  const p = traj(output).find((t) => t.tool === "create-environment-release-plan");
  if (!p) return result(false, "no release plan created");
  const pr = p.arguments.progressiveRelease || {};
  const m = (pr.metrics || {})["user-error-rate"];
  const capped = (pr.phases || []).every((ph) => (ph.steps || []).every((s) => s.allocation > 0 && s.allocation <= 50000));
  const pass = Boolean(m && m.autoRollback === true && m.isGroup === false) && capped;
  return result(pass, `metrics: ${JSON.stringify(pr.metrics || {})}; every step at most 50000: ${capped}`);
};

// A project with no stored contexts still gets a starter, randomized by user.
module.exports.starterUnitIsUser = (output) => {
  const p = traj(output).find((t) => t.tool === "create-environment-release-plan");
  if (!p) return result(false, "no release plan created");
  const unit = ((p.arguments || {}).progressiveRelease || {}).randomizationUnit;
  return result(unit === "user", `randomization unit: ${unit}`);
};

// Standalone starter for production: one phase for everyone, 10/25/50 with
// 4-hour holds, created after a confirmation, then set as the default.
module.exports.productionStarterProgressive = (output) => {
  const steps = traj(output);
  const ci = steps.findIndex((t) => t.tool === "create-environment-release-plan" && (t.arguments || {}).environmentKey === "production" &&
    !/error/i.test(String(t.mock_response_preview || "")));
  if (ci === -1) return result(false, "no production release plan created");
  const phases = ((steps[ci].arguments.progressiveRelease || {}).phases) || [];
  const one = phases.length === 1 && (phases[0].clauses || []).some((c) => c.attribute === "kind");
  const allocs = one ? (phases[0].steps || []).map((x) => x.allocation) : [];
  const holds = one && (phases[0].steps || []).every((x) => x.durationMillis === 14400000);
  const key = steps[ci].arguments.key;
  const di = steps.findIndex((t) => t.tool === "update-default-environment-release-plan" && (t.arguments || {}).releasePlanKey === key && t.arguments.default === true);
  const pass = one && holds && JSON.stringify(allocs) === JSON.stringify([10000, 25000, 50000]) && di > ci;
  return result(pass, `one phase for everyone: ${one}; steps ${JSON.stringify(allocs)}; 4h holds: ${holds}; default set after create: ${di > ci}`);
};

// Starters in two environments get different keys (keys are unique in the
// project), and the second takes the -2 suffix.
module.exports.starterKeysDoNotCollide = (output) => {
  const creates = traj(output).filter((t) => t.tool === "create-environment-release-plan");
  const keys = creates.map((t) => (t.arguments || {}).key);
  const envs = new Set(creates.map((t) => (t.arguments || {}).environmentKey));
  const pass = envs.has("test") && envs.has("production") && new Set(keys).size === keys.length && keys.includes("progressive") && keys.includes("progressive-2");
  return result(pass, `keys ${JSON.stringify(keys)} for ${JSON.stringify([...envs])}`);
};
