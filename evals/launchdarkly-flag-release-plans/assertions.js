// Assertions for the flag release plans suite. Each export is a promptfoo
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

// Every API write comes after a "Make this change" answer, and a new answer
// follows each write that failed (a retry needs its own confirmation).
module.exports.confirmsBeforeApiWrite = (output) => {
  const steps = traj(output);
  let from = 0;
  let count = 0;
  for (let i = 0; i < steps.length; i++) {
    if (!isApiWrite(steps[i])) continue;
    count++;
    if (approvedBetween(steps, from, i) === -1) {
      return result(false, `${steps[i].arguments.method} ${steps[i].arguments.path} at ${i} without "Make this change" since the last write`);
    }
    from = i + 1;
  }
  return result(count > 0, count ? `${count} confirmed writes` : "no API write");
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
