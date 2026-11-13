// Assertions for the release plans suite (environment and flag release
// plans). Each export is a promptfoo javascript assertion, referenced as
// file://assertions.js:<name>. Environment release plans go through the MCP
// mocks. Flag release plans go through the flag release plan MCP tools when
// the suite exposes them, and otherwise through REST commands the agent shows
// and the user runs (scripted pasted output), never commands the agent runs.

const checks = require("./command-checks");

const { traj, result, shownCommands, planCreates, planWrites, userFacingText } = checks;

module.exports.everyCommandBeta = checks.everyCommandBeta;
module.exports.runQuestionShowsCommand = checks.runQuestionShowsCommand;
module.exports.agentNeverUsesToken = checks.agentNeverUsesToken;
module.exports.noWriteCommands = checks.noWriteCommands;
module.exports.noCommandsShown = checks.noCommandsShown;

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

const FLAG_PLAN_WRITES = new Set(["create-flag-release-plan", "update-flag-release-plan", "delete-flag-release-plan"]);
const MCP_WRITES = new Set(["create-environment-release-plan", "update-environment-release-plan", "update-default-environment-release-plan", ...FLAG_PLAN_WRITES]);
const isMcpWrite = (t) => MCP_WRITES.has(t.tool);

// Every MCP write comes after a "Make this change" answer, and a new answer
// follows each write. Setting a plan as the default right after creating it
// is covered by the create's confirmation (for an environment release plan,
// and for a flag release plan that replaces the project's default).
const isDefaultAfterCreate = (prev, t) => Boolean(prev) && (
  (prev.tool === "create-environment-release-plan" && t.tool === "update-default-environment-release-plan" &&
    (t.arguments || {}).releasePlanKey === (prev.arguments || {}).key) ||
  (prev.tool === "create-flag-release-plan" && t.tool === "update-flag-release-plan" &&
    (t.arguments || {}).flagReleasePlanKey === (prev.arguments || {}).key && (t.arguments || {}).default === true));

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
  const raw = /environmentReleasePlanKey|isDefault|"default"|triggerType/.test(text);
  return result(listed && names && isDefault && !raw, `list command shown: ${listed}; names both plans: ${names}; says which is default: ${isDefault}; field names: ${raw}`);
};

// The create command lists test, then production, each with its default
// environment release plan, as the project's default.
module.exports.createsTestThenProduction = (output) => {
  const c = lastCreate(output);
  if (!c) return result(false, "no create command with a JSON body shown");
  const envs = envsOf(c.body);
  const pass = JSON.stringify(envs) === JSON.stringify(["test:progressive", "production:progressive-2"]) && c.body.default === true;
  return result(pass, `environments ${JSON.stringify(envs)}; default: ${c.body.default}`);
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
  const pass = b.default === true && b.name === "Staged rollout" && b.version === 3 &&
    JSON.stringify(envs) === JSON.stringify(["test", "production"]) && creates === 0;
  return result(pass, `default ${b.default}; name ${b.name}; version ${b.version}; environments ${JSON.stringify(envs)}; creates ${creates}`);
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

// Making another plan the default says which default it replaces, in a
// question asked before the default changes. The question hides the text
// above it, so assistant turns and the final reply don't count.
const saysReplaces = (tool) => (output) => {
  const steps = traj(output);
  const write = steps.findIndex((t) => t.tool === tool);
  const asked = steps.slice(0, write === -1 ? steps.length : write)
    .filter((t) => t.tool === "ask-question")
    .map((t) => JSON.stringify(t.arguments || {}))
    .join("\n");
  const pass = /replaces\s+[`"*\\]*(fast|fast rollout)[`"*\\]*\s+as\s+the\s+default/i.test(asked);
  return result(pass, pass ? "the confirmation says the plan replaces Fast as the default" : "no question before the change says the new default replaces the current one");
};
module.exports.saysReplacesDefault = saysReplaces("update-default-environment-release-plan");
module.exports.saysReplacesFlagDefault = saysReplaces("update-flag-release-plan");

// ---------------------------------------------------------------------------
// Flag release plans through the MCP tools (mcp #522).

const failed = (t) => /error|not found|already|expected arguments/i.test(String(t.mock_response_preview || ""));
const flagCalls = (output, tool) => traj(output).filter((t) => t.tool === tool);
const okFlagCalls = (output, tool) => flagCalls(output, tool).filter((t) => !failed(t));
const flagWrites = (output) => traj(output).filter((t) => FLAG_PLAN_WRITES.has(t.tool));
const envList = (envs) => (envs || []).map((e) => `${e.environmentKey}:${e.environmentReleasePlanKey || "immediate"}`);
const TEST_THEN_PROD = JSON.stringify(["test:progressive", "production:progressive-2"]);
const FLAG_TOOL_NAMES = /get-flag-release-plans|create-flag-release-plan|update-flag-release-plan|delete-flag-release-plan|flagReleasePlanKey|environmentReleasePlanKey|"default"|triggerType/;

// The list is read with the tool, and the reply reports both plans and the
// default in words, with no command and no tool or field names.
module.exports.mcpListReportsPlans = (output) => {
  const read = flagCalls(output, "get-flag-release-plans").length > 0;
  const text = String((output && output.response) || "");
  const names = /staged rollout/i.test(text) && /production only/i.test(text);
  const isDefault = /default/i.test(text);
  const raw = FLAG_TOOL_NAMES.test(text);
  const cmds = shownCommands(output).length;
  const w = flagWrites(output).length;
  return result(read && names && isDefault && !raw && cmds === 0 && w === 0,
    `list read with the tool: ${read}; names both plans: ${names}; says which is default: ${isDefault}; tool or field names: ${raw}; commands shown: ${cmds}; writes: ${w}`);
};

// The project lists only the built-in plan: the list is read first, and the
// new plan is created with test, then production, as the project's default.
module.exports.mcpCreatesDefaultPlan = (output) => {
  const steps = traj(output);
  const li = steps.findIndex((t) => t.tool === "get-flag-release-plans");
  const creates = okFlagCalls(output, "create-flag-release-plan");
  const c = creates[creates.length - 1];
  if (!c) return result(false, "no successful create-flag-release-plan call");
  const a = c.arguments || {};
  const envs = JSON.stringify(envList(a.environments));
  const ci = steps.indexOf(c);
  const touchesBuiltin = flagWrites(output).some((t) => (t.arguments || {}).flagReleasePlanKey === "default-release-configuration");
  const pass = li !== -1 && li < ci && envs === TEST_THEN_PROD && a.default === true && !touchesBuiltin;
  return result(pass, `list read first: ${li !== -1 && li < ci}; environments ${envs}; default: ${a.default}; writes to the built-in plan: ${touchesBuiltin}`);
};

// The project's default is edited in place: same key, confirm sent, test
// then production, the default kept (not sent as false), and no create.
module.exports.mcpUpdatesInPlace = (output) => {
  const ups = okFlagCalls(output, "update-flag-release-plan").filter((t) => (t.arguments || {}).flagReleasePlanKey === "staged-rollout");
  const u = ups[ups.length - 1];
  const creates = flagCalls(output, "create-flag-release-plan").length;
  if (!u) return result(false, `no successful update of staged-rollout; creates: ${creates}`);
  const a = u.arguments || {};
  const envs = JSON.stringify(envList(a.environments));
  const pass = a.confirm === true && envs === TEST_THEN_PROD && a.default !== false && creates === 0;
  return result(pass, `confirm: ${a.confirm}; environments ${envs}; default sent: ${a.default}; creates: ${creates}`);
};

// Another plan becomes the default: an update of that plan with default
// true and confirm, and no create.
module.exports.mcpPromotesDefault = (output) => {
  const ups = okFlagCalls(output, "update-flag-release-plan").filter((t) => (t.arguments || {}).flagReleasePlanKey === "staged-rollout");
  const u = ups[ups.length - 1];
  const creates = flagCalls(output, "create-flag-release-plan").length;
  const demoted = flagCalls(output, "update-flag-release-plan").some((t) => (t.arguments || {}).flagReleasePlanKey === "fast");
  if (!u) return result(false, `no successful update of staged-rollout; creates: ${creates}`);
  const a = u.arguments || {};
  const pass = a.default === true && a.confirm === true && creates === 0 && !demoted;
  return result(pass, `default: ${a.default}; confirm: ${a.confirm}; creates: ${creates}; writes to Fast: ${demoted}`);
};

// The "Make this change" question before the first flag release plan write
// carries the change: its question text, or the preview of "Make this
// change", matches every pattern.
const confirmCarries = (patterns) => (output) => {
  const steps = traj(output);
  const wi = steps.findIndex((t) => FLAG_PLAN_WRITES.has(t.tool));
  if (wi === -1) return result(false, "no flag release plan write");
  let q = null;
  for (let i = wi - 1; i >= 0; i--) if (isConfirm(steps[i])) { q = steps[i]; break; }
  if (!q) return result(false, "no \"Make this change\" question before the write");
  const a = q.arguments || {};
  const opts = (a.options || []).filter((o) => CONFIRM.test(String(o.label || "")));
  const text = [a.prompt, ...opts.map((o) => o.preview)].map((x) => String(x || "")).join("\n");
  const missing = patterns.filter((re) => !re.test(text)).map(String);
  return result(missing.length === 0, missing.length ? `the confirm question does not show ${missing.join(", ")}` : "the confirm question shows the change");
};
module.exports.confirmShowsTestThenProduction = confirmCarries([/test/i, /production/i]);
module.exports.confirmShowsStagedRollout = confirmCarries([/staged rollout/i, /default/i]);

// A detailed request is not approval: the confirm question is asked, the
// user cancels, and no flag release plan is written.
module.exports.cancelWritesNothing = (output) => {
  const asked = traj(output).some((t) => isConfirm(t));
  const w = flagWrites(output).length;
  const cmds = planWrites(output).length;
  return result(asked && w === 0 && cmds === 0, `confirm question asked: ${asked}; flag release plan writes: ${w}; write commands shown: ${cmds}`);
};

// The tools are missing (REST fallback): the agent does not say that the
// account lacks flag release plans, and does not send the user to support.
const LACKS_FEATURE = /((not (available|included|enabled)|(doesn'?t|does not) (have|include|support))[^.\n]{0,40}flag release plans|flag release plans[^.\n]{0,40}(not (available|included|enabled)|unavailable)|contact (launchdarkly )?support)/i;
module.exports.noFeatureMissingClaim = (output) => {
  const hit = (userFacingText(output).match(LACKS_FEATURE) || [])[0];
  return result(!hit, hit ? `says the account lacks the feature: "${hit}"` : "does not say the account lacks flag release plans");
};

// ---------------------------------------------------------------------------
// Findings from a live run of the skills (the blitz test).

// A flag release plan read gives only each environment's release plan key.
// The reply names each environment's release plan by its real name (from the
// environment's read), and never shows the key as a name. Code blocks don't
// count, because a command the user runs may hold a key.
const ENV_PLAN_NAMES = [/test progressive rollout/i, /production progressive rollout/i];
const ENV_PLAN_KEYS = /\b(test|prod)-progressive\b/i;
const withoutCode = (text) => String(text || "").replace(/```[\s\S]*?```/g, "").replace(/`[^`\n]*`/g, "");
const namesNotKeys = (text) => {
  const plain = withoutCode(text);
  const missing = ENV_PLAN_NAMES.filter((re) => !re.test(plain)).map(String);
  const key = (plain.match(ENV_PLAN_KEYS) || [])[0];
  return { missing, key };
};
module.exports.listUsesEnvPlanNames = (output) => {
  const steps = traj(output);
  const read = new Set(steps.filter((t) => t.tool === "get-environment-release-plans").map((t) => (t.arguments || {}).environmentKey));
  const both = read.has("test") && read.has("production");
  const { missing, key } = namesNotKeys((output && output.response) || "");
  return result(both && missing.length === 0 && !key,
    `read both environments' release plans: ${both}; names missing: ${missing.join(", ") || "none"}; key shown as a name: ${key || "none"}`);
};

// The "Make this change" question names each environment's release plan by
// its real name, not its key.
module.exports.confirmUsesEnvPlanNames = (output) => {
  const steps = traj(output);
  const q = steps.find(isConfirm);
  if (!q) return result(false, "no \"Make this change\" question");
  const a = q.arguments || {};
  const text = [a.prompt, ...(a.options || []).map((o) => o.preview)].map((x) => String(x || "")).join("\n");
  const { missing, key } = namesNotKeys(text);
  return result(missing.length === 0 && !key, `names missing from the question: ${missing.join(", ") || "none"}; key shown as a name: ${key || "none"}`);
};

// A create while the project has a default: the "Flag release plan" question
// (Keep <name> / Create another plan) comes before the "Confirm" question and
// before any flag release plan write.
const isFlagPlanQuestion = (t) => t.tool === "ask-question" && (() => {
  const labels = ((t.arguments && t.arguments.options) || []).map((o) => String(o.label || ""));
  return labels.some((l) => /^keep staged rollout/i.test(l)) && labels.some((l) => /create another plan/i.test(l));
})();
module.exports.flagPlanQuestionFirst = (output) => {
  const steps = traj(output);
  const qi = steps.findIndex(isFlagPlanQuestion);
  const ci = steps.findIndex(isConfirm);
  const wi = steps.findIndex((t) => FLAG_PLAN_WRITES.has(t.tool));
  const beforeConfirm = qi !== -1 && (ci === -1 || qi < ci);
  const beforeWrite = qi !== -1 && (wi === -1 || qi < wi);
  return result(beforeConfirm && beforeWrite,
    `"Flag release plan" question asked: ${qi !== -1}; before "Confirm": ${beforeConfirm}; before any write: ${beforeWrite}`);
};

// Every "Confirm" question has exactly two options: "Make this change" and
// "Cancel". A different change is not a third option.
module.exports.confirmHasTwoOptions = (output) => {
  const qs = traj(output).filter(isConfirm);
  const bad = qs.filter((t) => {
    const labels = ((t.arguments && t.arguments.options) || []).map((o) => String(o.label || ""));
    return labels.length !== 2 || !labels.some((l) => CONFIRM.test(l)) || !labels.some((l) => /^cancel/i.test(l));
  });
  return result(qs.length > 0 && bad.length === 0,
    qs.length === 0 ? "no \"Confirm\" question" : bad.length ? `options: ${bad.map((t) => JSON.stringify((t.arguments.options || []).map((o) => o.label))).join("; ")}` : "every confirm has Make this change and Cancel only");
};

// "Create another plan": a new plan that is not the default, and the
// project's default is not written.
module.exports.mcpCreatesAnotherPlan = (output) => {
  const c = okFlagCalls(output, "create-flag-release-plan").pop();
  if (!c) return result(false, "no successful create-flag-release-plan call");
  const a = c.arguments || {};
  const touched = flagCalls(output, "update-flag-release-plan").some((t) => (t.arguments || {}).flagReleasePlanKey === "staged-rollout");
  const pass = a.key !== "staged-rollout" && a.default !== true && !touched;
  return result(pass, `key ${a.key}; default: ${a.default}; writes to Staged rollout: ${touched}`);
};

// "Run this command" questions, and the commands each one holds (in its
// question text or the preview of an option).
const runAsks = (output) => traj(output).filter((t) => t.tool === "ask-question" && /run this command|here'?s the output/i.test(JSON.stringify(t.arguments || {})));
const commandsIn = (t) => {
  const a = t.arguments || {};
  const text = [a.prompt, ...(a.options || []).map((o) => o.preview)].map((x) => String(x || "")).join("\n");
  return checks.shownCommands({ trajectory: [], assistant_turns: [], response: text });
};

// Read-only request with the flag release plan tools missing: one "Run this
// command" question, holding the list command.
module.exports.readOnlyAsksToRunList = (output) => {
  const asks = runAsks(output);
  const holdsList = asks.length === 1 && commandsIn(asks[0]).some((c) => c.method === "GET" && /\/flag-release-plans$/.test(c.path));
  return result(asks.length === 1 && holdsList, `"Run this command" questions: ${asks.length}; the question holds the list command: ${holdsList}`);
};

// Read-only: any "Run this command" question asks for a read only.
module.exports.asksToRunOnlyReads = (output) => {
  const asks = runAsks(output);
  const writes = asks.flatMap(commandsIn).filter((c) => c.method !== "GET");
  return result(writes.length === 0, writes.length ? `asks the user to run a write: ${writes.map((c) => `${c.method} ${c.path}`).join(", ")}` : `"Run this command" questions ask for reads only (${asks.length})`);
};

// The flag release plan tools roll out behind a flag, so updating or
// reconnecting the MCP server does not add them: do not say it does.
const RECONNECT = /\b(update|updating|reconnect|reconnecting|upgrade|restart)\b[^.\n]{0,60}\bmcp\b|\bmcp server\b[^.\n]{0,60}\b(update|reconnect|upgrade|out of date|older)\b/i;
module.exports.noReconnectAdvice = (output) => {
  const hit = (userFacingText(output).match(RECONNECT) || [])[0];
  return result(!hit, hit ? `tells the user to update or reconnect: "${hit}"` : "no update or reconnect advice");
};
