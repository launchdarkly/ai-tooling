// Assertions for the release plans suite (environment and flag release
// plans). Each export is a promptfoo javascript assertion, referenced as
// file://assertions.js:<name>. Environment release plans go through the MCP
// mocks. Flag release plans go through REST commands the agent shows and the
// user runs (scripted pasted output), never commands the agent runs.

const checks = require("./command-checks");

const { traj, result, shownCommands, planCreates, planWrites, userFacingText } = checks;

module.exports.everyCommandBeta = checks.everyCommandBeta;
module.exports.agentNeverUsesToken = checks.agentNeverUsesToken;
module.exports.noWriteCommands = checks.noWriteCommands;

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

const MCP_WRITES = new Set(["create-environment-release-plan", "update-environment-release-plan", "update-default-environment-release-plan"]);
const isMcpWrite = (t) => MCP_WRITES.has(t.tool);

// Every MCP write comes after a "Make this change" answer, and a new answer
// follows each write. Setting a plan as the default right after creating it
// is covered by the create's confirmation.
const isDefaultAfterCreate = (prev, t) => prev && prev.tool === "create-environment-release-plan" &&
  t.tool === "update-default-environment-release-plan" && (t.arguments || {}).releasePlanKey === (prev.arguments || {}).key;

module.exports.confirmsBeforeWrite = (output) => {
  const steps = traj(output);
  let from = 0;
  let prev = null;
  let count = 0;
  for (let i = 0; i < steps.length; i++) {
    if (!isMcpWrite(steps[i])) continue;
    count++;
    const covered = isDefaultAfterCreate(prev, steps[i]) && !steps.slice(from, i).some((t) => t.tool === "ask-question");
    if (!covered && approvedBetween(steps, from, i) === -1) {
      return result(false, `${steps[i].tool} at ${i} without "Make this change" since the last write`);
    }
    from = i + 1;
    prev = steps[i];
  }
  return result(count > 0, count ? `${count} confirmed writes` : "no write");
};

const envsOf = (body) => ((body && body.environments) || []).map((e) => `${e.environmentKey}:${e.environmentReleasePlanKey || "immediate"}`);
const lastCreate = (output) => planCreates(output).filter((c) => c.body).pop();

// The list command is shown, and the reply reports both pasted plans and
// which one is the default, without field names.
module.exports.listReportsPlans = (output) => {
  const listed = shownCommands(output).some((c) => c.method === "GET" && /\/flag-release-plans$/.test(c.path));
  const text = String((output && output.response) || "");
  const names = /staged rollout/i.test(text) && /production only/i.test(text);
  const isDefault = /default/i.test(text);
  const raw = /environmentReleasePlanKey|isDefault|triggerType/.test(text);
  return result(listed && names && isDefault && !raw, `list command shown: ${listed}; names both plans: ${names}; says which is default: ${isDefault}; field names: ${raw}`);
};

// The create command lists test, then production, each with its default
// environment release plan, as the project's default.
module.exports.createsTestThenProduction = (output) => {
  const c = lastCreate(output);
  if (!c) return result(false, "no create command with a JSON body shown");
  const envs = envsOf(c.body);
  const pass = JSON.stringify(envs) === JSON.stringify(["test:progressive", "production:progressive-2"]) && c.body.isDefault === true;
  return result(pass, `environments ${JSON.stringify(envs)}; default: ${c.body.isDefault}`);
};

// After the user pastes the create response, the reply reports it as done
// with the plan's name, and does not ask to run the create again.
module.exports.readsPastedResponse = (output) => {
  const text = String((output && output.response) || "");
  const done = /(created|is set up|now exists|is now the (project's )?default)/i.test(text) && /default release/i.test(text);
  const again = planCreates({ trajectory: [], assistant_turns: [], response: text }).length;
  return result(done && again === 0, `reports the created plan: ${done}; create shown again in the final reply: ${again}`);
};

// A pasted 409: the next create command uses another key.
module.exports.retriesWithNewKey = (output) => {
  const keys = planCreates(output).filter((c) => c.body).map((c) => c.body.key);
  const pass = keys.length >= 2 && keys[0] !== keys[keys.length - 1];
  return result(pass, `create keys shown: ${JSON.stringify(keys)}`);
};

// Make an existing plan the default: a full replace from the pasted read,
// with the version, the plan's environments, and the default on. No create.
module.exports.promotesWithFullBody = (output) => {
  const put = shownCommands(output).find((c) => c.method === "PUT" && /\/flag-release-plans\/staged-rollout$/.test(c.path));
  if (!put || !put.body) return result(false, "no replace command for staged-rollout with a JSON body");
  const b = put.body;
  const envs = (b.environments || []).map((e) => e.environmentKey);
  const creates = planCreates(output).length;
  const pass = b.isDefault === true && b.name === "Staged rollout" && b.version === 3 &&
    JSON.stringify(envs) === JSON.stringify(["test", "production"]) && creates === 0;
  return result(pass, `isDefault ${b.isDefault}; name ${b.name}; version ${b.version}; environments ${JSON.stringify(envs)}; creates ${creates}`);
};

// The user pastes a token instead of output: the reply does not repeat it,
// and tells the user to delete it.
module.exports.refusesPastedToken = (output) => {
  const text = userFacingText(output);
  const repeated = /api-0000-1111-fake/.test(text);
  const revoke = /(delete|revoke|rotate|regenerate)[^.\n]{0,60}token|token[^.\n]{0,60}(delete|revoke|rotate)/i.test(text);
  return result(!repeated && revoke, `repeats the token: ${repeated}; tells the user to delete it: ${revoke}`);
};

// The account does not have flag release plans: contact support.
module.exports.saysContactSupport = (output) => {
  const pass = /contact (launchdarkly )?support|launchdarkly support/i.test(userFacingText(output));
  return result(pass, pass ? "tells the user to contact support" : "does not mention support");
};

// Read-only: describes the plan it would create, in words.
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
// only then shows a flag release plan create that names it.
module.exports.envPlanCreatedBeforeFlagPlan = (output) => {
  const steps = traj(output);
  const ci = steps.findIndex((t) => t.tool === "create-environment-release-plan" && (t.arguments || {}).environmentKey === "production" &&
    !/error/i.test(String(t.mock_response_preview || "")));
  if (ci === -1) return result(false, "no release plan created for production");
  const asked = steps.slice(0, ci).some((t) => t.tool === "ask-question" && /production/i.test(JSON.stringify(t.arguments || {})));
  const key = steps[ci].arguments.key;
  const turn = steps[ci].turn;
  const writes = planWrites(output);
  const early = writes.filter((c) => turn !== undefined && c.turn < turn).length;
  const c = lastCreate(output);
  const names = Boolean(c) && (c.body.environments || []).some((e) => e.environmentKey === "production" && e.environmentReleasePlanKey === key);
  return result(asked && early === 0 && names,
    `asked about production first: ${asked}; flag release plan commands before production's plan: ${early}; create names ${key}: ${names}`);
};

// The user declines: no release plan is created, the flag release plan
// leaves production out, and the reply says so.
module.exports.leavesEnvironmentOut = (output) => {
  const created = envPlanCreates(output).length;
  const hasProd = planWrites(output).some((c) => ((c.body || {}).environments || []).some((e) => e.environmentKey === "production"));
  const text = String((output && output.response) || "");
  const says = /production/i.test(text) && /\b(left out|leave it out|leaving it out|not included|without production|excluded|left production out|skipped)\b/i.test(text);
  return result(created === 0 && !hasProd && says, `release plans created: ${created}; a command includes production: ${hasProd}; says production is left out: ${says}`);
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

// Before any create, the existing default is named to the user, and the

// Before any create, the existing default is named and the default question
// is asked. With the "keep" answer, nothing is written.
const namesDefaultFirst = (name, keepLabel, wrote) => (output) => {
  const steps = traj(output);
  const qi = steps.findIndex((t) => t.tool === "ask-question" &&
    ((t.arguments && t.arguments.options) || []).some((o) => keepLabel.test(String(o.label || ""))));
  const before = qi === -1 ? "" : checks.shownText(output).filter((x) => x.turn <= steps[qi].turn).map((x) => x.text).join("\n");
  const named = new RegExp(name, "i").test(before) && /default/i.test(before);
  const w = wrote(output);
  return result(qi !== -1 && named && w === 0, `asks the default question: ${qi !== -1}; names ${name} as the default first: ${named}; writes: ${w}`);
};
module.exports.envDefaultNamedFirst = namesDefaultFirst("gradual", /^use gradual/i, (o) => traj(o).filter(isMcpWrite).length);
module.exports.flagDefaultNamedFirst = namesDefaultFirst("staged rollout", /^keep staged rollout/i, (o) => planWrites(o).length);

// Read-only: the user is asked to run nothing.
module.exports.asksToRunNothing = (output) => {
  const asked = traj(output).filter((t) => t.tool === "ask-question" && /run this command|here's the output/i.test(JSON.stringify(t.arguments || {}))).length;
  return result(asked === 0, `questions that ask the user to run a command: ${asked}`);
};

// Complete plans but no default: each plan is offered as the default, the
// chosen one is set as the default after a confirmation, and no plan is
// created.
module.exports.picksDefaultAmongComplete = (output) => {
  const steps = traj(output);
  const offered = steps.some((t) => t.tool === "ask-question" &&
    ["gradual", "fast"].every((n) => ((t.arguments && t.arguments.options) || []).some((o) => new RegExp(n, "i").test(String(o.label || "")))));
  const set = steps.some((t) => t.tool === "update-default-environment-release-plan" && (t.arguments || {}).releasePlanKey === "gradual" && t.arguments.default === true);
  const created = steps.filter((t) => t.tool === "create-environment-release-plan").length;
  return result(offered && set && created === 0, `offers both plans: ${offered}; sets gradual as the default: ${set}; plans created: ${created}`);
};

// A complete plan becomes the default: Gradual is set as the default, and no
// plan is created.
module.exports.existingPlanSetAsDefault = (output) => {
  const steps = traj(output);
  const created = steps.filter((t) => t.tool === "create-environment-release-plan").length;
  const def = steps.some((t) => t.tool === "update-default-environment-release-plan" && (t.arguments || {}).releasePlanKey === "gradual" && t.arguments.default === true);
  return result(created === 0 && def, `plans created: ${created}; existing plan set as default: ${def}`);
};

// Making another plan the default says which default it replaces.
module.exports.saysReplacesDefault = (output) => {
  const pass = /replaces\s+[`"*]*(fast|fast rollout)[`"*]*\s+as\s+the\s+default/i.test(userFacingText(output));
  return result(pass, pass ? "says the plan replaces Fast as the default" : "never says the new default replaces the current one");
};
