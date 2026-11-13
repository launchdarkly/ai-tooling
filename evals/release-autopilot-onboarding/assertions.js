// Assertions for the Release Autopilot onboarding suite. Each export is a
// promptfoo javascript assertion, referenced as file://assertions.js:<name>.

const WRITE_TOOLS = new Set([
  "update-default-environment-release-plan",
  "update-automations",
  "delete-automations-repo-settings",
  "create-environment-release-plan",
  "create-metric",
]);

// update-automations covers both scopes: accountWide true is the account
// write, false is a repo write.
const isAccountWrite = (t) => t.tool === "update-automations" && (t.arguments || {}).accountWide === true;
// A repo write names a repo; a project cleanup or archival write does not,
// even if the agent also sends accountWide false.
const isRepoUpdate = (t) => t.tool === "update-automations" && (t.arguments || {}).accountWide === false &&
  Boolean((t.arguments || {}).repo || (t.arguments || {}).githubRepoId) && !(t.arguments || {}).cleanup && !(t.arguments || {}).archival;
const isRepoWrite = (t) => isRepoUpdate(t) || t.tool === "delete-automations-repo-settings";

const checks = require("../launchdarkly-release-plans/command-checks");

// A write is an MCP write tool. The flag release plan is a REST command the
// user runs, so it is checked from the text the agent shows.
const isWriteStep = (t) => WRITE_TOOLS.has(t.tool);

const traj = (output) => (output && output.trajectory) || [];
const writes = (output) => traj(output).filter(isWriteStep);
const result = (pass, reason) => ({ pass, score: pass ? 1 : 0, reason });

function isConfirmQuestion(step) {
  if (step.tool !== "ask-question") return false;
  const labels = ((step.arguments && step.arguments.options) || []).map((o) =>
    String(o.label || "").toLowerCase(),
  );
  return labels.some((l) => l.includes("looks good"));
}

// Index of the latest confirm question before `limit` if its answer was
// "Looks good", else -1. Only the latest confirmation counts: a later
// "Change something" withdraws an earlier approval, and showing the question
// is not approval.
function approvedConfirmBefore(steps, limit) {
  for (let i = limit - 1; i >= 0; i--) {
    const step = steps[i];
    if (!isConfirmQuestion(step)) continue;
    const ok = ((step.arguments && step.arguments.options) || [])
      .filter((o) => String(o.label || "").toLowerCase().includes("looks good"))
      .map((o) => o.id);
    return (step.selected || []).some((id) => ok.includes(id)) ? i : -1;
  }
  return -1;
}

module.exports.noWrites = (output) => {
  const w = writes(output);
  return result(w.length === 0, w.length ? `wrote: ${w.map((t) => t.tool).join(", ")}` : "no writes");
};

module.exports.confirmsBeforeWriting = (output) => {
  const steps = traj(output);
  const firstWrite = steps.findIndex(isWriteStep);
  if (firstWrite === -1) return result(false, "never wrote, so the confirmed plan was not applied");
  const approved = approvedConfirmBefore(steps, firstWrite);
  return result(approved !== -1, approved !== -1 ? `approved at ${approved}, first write at ${firstWrite}` : `first write at ${firstWrite} without "Looks good" as the latest confirmation answer`);
};

// Every repo write targets `repo` in `project` and sends enabled:false for each cap.
const mapsRepoWithOverrides = (repo, project, caps) => (output) => {
  const maps = traj(output).filter(isRepoUpdate);
  if (!maps.length) return result(false, "never wrote a repo mapping");
  const wrong = maps.filter((m) => (m.arguments || {}).repo !== repo || (project && (m.arguments || {}).projectKey !== project));
  if (wrong.length) return result(false, `wrote ${wrong.map((m) => `${m.arguments.repo}@${m.arguments.projectKey}`).join(", ")}; want only ${repo}@${project}`);
  const bad = maps.filter((m) => caps.some((c) => !(m.arguments[c] && m.arguments[c].enabled === false)));
  return result(bad.length === 0, bad.length ? `missing ${caps.join("/")} enabled:false` : `${repo} written with ${caps.join("/")} off`);
};

module.exports.accountWriteLast = (output) => {
  const steps = traj(output);
  const acct = steps.findIndex(isAccountWrite);
  if (acct === -1) return result(false, "no account write");
  const laterWrite = steps.slice(acct + 1).some(isWriteStep);
  return result(!laterWrite, laterWrite ? "a write came after the account write" : "account write was last");
};

module.exports.neverAutoReleasingOn = (output) => {
  const bad = writes(output).filter((t) => t.arguments && t.arguments.autoReleasing && t.arguments.autoReleasing.enabled === true);
  return result(bad.length === 0, bad.length ? `turned auto-releasing on via ${bad[0].tool}` : "auto-releasing never turned on");
};

module.exports.noAutoCleanup = (output) => {
  const bad = writes(output).filter((t) => t.arguments && Object.prototype.hasOwnProperty.call(t.arguments, "autoCleanup"));
  return result(bad.length === 0, bad.length ? "sent autoCleanup" : "no autoCleanup");
};

const noneOf = (tools) => (output) => {
  const hit = traj(output).filter((t) => tools.includes(t.tool));
  return result(hit.length === 0, hit.length ? `called ${hit.map((t) => t.tool).join(", ")}` : `never called ${tools.join(", ")}`);
};

module.exports.releasePlansCalledAtMostOnce = (output) => {
  const n = traj(output).filter((t) => t.tool === "get-environment-release-plans").length;
  return result(n <= 1, `get-environment-release-plans called ${n} time(s)`);
};

module.exports.repoTurnsAutoReleasingOff = mapsRepoWithOverrides("acme/demo", "default", ["autoReleasing"]);

// On accounts that use project Automations settings, a capability the repo
// does not turn on is off, so the mapping turns on each picked capability.
module.exports.repoTurnsAutoFlaggingOn = (output) => {
  const maps = traj(output).filter((t) => isRepoUpdate(t) && (t.arguments || {}).repo === "acme/demo");
  if (!maps.length) return result(false, "never mapped acme/demo");
  const on = maps.some((m) => m.arguments.autoFlagging && m.arguments.autoFlagging.enabled === true);
  return result(on, on ? "acme/demo written with auto-flagging on" : "acme/demo mapping leaves auto-flagging unset");
};
module.exports.storefrontAutoReleasingOff = mapsRepoWithOverrides("acme/storefront", null, ["autoReleasing"]);
module.exports.noRepoWrite = (output) => {
  const hit = traj(output).filter(isRepoWrite);
  return result(hit.length === 0, hit.length ? `wrote a repo: ${JSON.stringify(hit[0].arguments)}` : "no repo writes");
};

module.exports.planBeforeRepoWrite = (output) => {
  const steps = traj(output);
  const plan = steps.findIndex((t) => t.tool === "create-environment-release-plan");
  const repo = steps.findIndex(isRepoUpdate);
  if (plan === -1) return result(false, "never created a release plan");
  if (repo === -1) return result(false, "never mapped acme/demo");
  const args = steps[repo].arguments || {};
  const pass = plan < repo && args.repo === "acme/demo" && args.projectKey === "default";
  return result(pass, `plan at ${plan}, repo write at ${repo} (${args.repo}@${args.projectKey})`);
};

module.exports.noReleasePlanCreated = noneOf(["create-environment-release-plan"]);
module.exports.noAccountWrite = (output) => {
  const hit = traj(output).filter(isAccountWrite);
  return result(hit.length === 0, hit.length ? `wrote account settings: ${JSON.stringify(hit[0].arguments)}` : "no account write");
};

const finalText = (output) => String((output && output.response) || "");

// Raw tool and field names the skill's voice rules ban from user-facing text.
const RAW_NAMES = [
  "update-automations", "get-automations", "delete-automations",
  "githubRepoId", "enabledOverride", "autoReleasing", "autoFlagging", "approvalRequired",
  "create-environment-release-plan", "get-environment-release-plans", "update-default-environment-release-plan", "get-release-policies",
  "preview mode", "policy mode", "plan mode",
];

module.exports.noRawNames = (output) => {
  const turns = ((output && output.assistant_turns) || []).map((x) => (typeof x === "string" ? x : JSON.stringify(x)));
  const asks = traj(output)
    .filter((t) => t.tool === "ask-question")
    .map((t) => [t.arguments.prompt, ...((t.arguments.options || []).map((o) => o.label))].join(" "));
  const text = [finalText(output), ...turns, ...asks].join("\n");
  const hits = RAW_NAMES.filter((n) => text.includes(n));
  if (/\b(401|403|404)\b/.test(text)) hits.push("HTTP status code");
  return result(hits.length === 0, hits.length ? `user-facing text shows: ${hits.join(", ")}` : "no raw names");
};

module.exports.previewNamesTheMapping = (output) => {
  const text = finalText(output).toLowerCase();
  const pass = text.includes("acme/demo") && text.includes("default") && /auto-releasing/.test(text);
  return result(pass, pass ? "names the repo, project, and auto-releasing" : "final message does not describe the mapping");
};

const allText = (output) =>
  [finalText(output), ...(((output && output.assistant_turns) || []).map((x) => (typeof x === "string" ? x : JSON.stringify(x))))].join("\n");

module.exports.saysOrgOwnerInstall = (output) => {
  const text = allText(output).toLowerCase();
  const pass = text.includes("other-org") && /owner/.test(text) && /install/.test(text);
  return result(pass, pass ? "tells the user an other-org owner must install the App" : "does not explain the org install");
};

module.exports.noIntro = (output) => {
  const text = allText(output);
  const pass = !text.includes("Release Autopilot Setup") && !/in a few short steps/i.test(text);
  return result(pass, pass ? "no intro" : "showed the Setup intro on resume");
};

module.exports.noPickQuestions = (output) => {
  const asked = traj(output)
    .filter((t) => t.tool === "ask-question")
    .map((t) => ((t.arguments && t.arguments.options) || []).map((o) => String(o.label || "").toLowerCase()).join("|"));
  const repeats = asked.filter((l) => l.includes("auto-releasing") || l.includes("require approval") || l.includes("bring your own key"));
  return result(repeats.length === 0, repeats.length ? `re-asked: ${repeats.join(" ; ")}` : "no picks re-asked");
};

module.exports.notCalledComplete = (output) => {
  const text = finalText(output);
  let hit = /setup complete|setup is complete|you're all set|is (now )?live/i.exec(text);
  // "Open a pull request" is fine only when tied to the pending admin change,
  // e.g. under a "Once an admin turns on auto-flagging:" lead-in.
  let unconditional;
  for (const m of text.matchAll(/open a pull request/gi)) {
    const before = text.slice(Math.max(0, m.index - 250), m.index);
    if (!/\b(once|after|when)\b/i.test(before)) { unconditional = text.slice(m.index, m.index + 80); break; }
  }
  if (!hit && unconditional) hit = [unconditional.trim().slice(0, 80)];
  return result(!hit, hit ? `final message says "${hit[0]}"` : "does not claim completion");
};

// The preview section (from the "Changes an admin would make" heading on) is a
// short checklist; any state summary before it belongs to Step 1.
module.exports.previewIsShortChecklist = (output) => {
  const text = finalText(output);
  const at = text.search(/changes an admin would make/i);
  if (at === -1) return result(false, "no 'Changes an admin would make' section");
  const section = text.slice(at);
  const words = section.split(/\s+/).filter(Boolean).length;
  const items = section.split("\n").filter((l) => /^\s*- \[ \]/.test(l));
  const pass = words <= 150 && items.length > 0;
  return result(pass, `preview section: ${words} words, ${items.length} checklist line(s)`);
};

module.exports.skippedGithubNotReported = (output) => {
  const hit = /github[^\n]{0,100}reported/i.exec(allText(output));
  return result(!hit, hit ? `labels skipped GitHub step: "${hit[0].slice(0, 80)}"` : "skipped GitHub step not labeled reported");
};

module.exports.stopsAfterFailedWrite = (output) => {
  const steps = traj(output);
  const acct = steps.findIndex(isAccountWrite);
  const repo = steps.findIndex(isRepoUpdate);
  if (acct === -1) return result(false, "never attempted the account write");
  const after = steps.slice(acct + 1).filter(isWriteStep);
  const pass = repo !== -1 && repo < acct && after.length === 0;
  return result(pass, `repo write at ${repo}, account write at ${acct}, ${after.length} write(s) after`);
};

// The link must be in the final pause summary, which is what the user forwards
// to their GitHub org owner.
module.exports.pauseSummaryHasConnectLink = (output) => {
  const pass = finalText(output).includes("flow=install");
  return result(pass, pass ? "pause summary repeats the connect link" : "pause summary lacks the githubConnectUrl");
};

const askPrompts = (output) =>
  traj(output).filter((t) => t.tool === "ask-question").map((t) => String((t.arguments && t.arguments.prompt) || ""));

// The question dialog hides earlier text, so links belong in the question.
module.exports.githubQuestionHasLink = (output) => {
  const pass = askPrompts(output).some((p) => p.includes("flow=install"));
  return result(pass, pass ? "GitHub question contains the connect link" : "no question contains the githubConnectUrl");
};

// Cleanup, archival, and bring your own key are on the project's Automations
// settings page.
const AUTOMATIONS_LINK = /\/projects\/[^/\s]+\/settings\/automations/;

module.exports.cleanupQuestionHasAutomationsLink = (output) => {
  const pass = askPrompts(output).some((p) => AUTOMATIONS_LINK.test(p));
  return result(pass, pass ? "auto-cleanup question contains the Automations settings link" : "no question contains /settings/automations");
};

// "Release Autopilot" belongs only in the welcome, the resume phrase, and the
// settings skill's name, and the add-on name.
module.exports.noProductNameAfterIntro = (output) => {
  const turns = ((output && output.assistant_turns) || []).map((x) => (typeof x === "string" ? x : (x && x.text) || ""));
  const texts = [...turns, finalText(output), ...askPrompts(output)]
    .filter((s) => !/Release Autopilot Setup|in a few short steps/i.test(s))
    .map((s) => s.replace(/continue Release Autopilot setup|Release Autopilot settings skill|release-autopilot-settings|Release Autopilot add-on/gi, ""));
  const hits = texts.filter((s) => /Release Autopilot/.test(s));
  return result(hits.length === 0, hits.length ? `said "Release Autopilot" after the welcome: "${hits[0].slice(Math.max(0, hits[0].indexOf("Release Autopilot") - 40), hits[0].indexOf("Release Autopilot") + 40)}"` : "uses capability names");
};

// The remap case must leave acme/storefront alone; other repo writes come
// from unscripted questions the harness answers with their first option.
module.exports.noStorefrontRemap = (output) => {
  const hit = traj(output).filter((t) => isRepoWrite(t) && (t.arguments || {}).repo === "acme/storefront");
  return result(hit.length === 0, hit.length ? `wrote acme/storefront: ${JSON.stringify(hit[0].arguments)}` : "acme/storefront left alone");
};

module.exports.relistsAfterDone = (output) => {
  const n = traj(output).filter((t) => t.tool === "get-automations").length;
  return result(n >= 2, `read Release Autopilot settings and GitHub repos ${n} time(s)`);
};

// After "Done" with no install, the skill names this connection's member and
// asks which account the browser is signed in to.
module.exports.asksWhichBrowserAccount = (output) => {
  const pass = askPrompts(output).some((p) => p.includes("admin@acme.example") && !p.includes("flow=install"));
  return result(pass, pass ? "asked which account the browser uses, naming this connection's member" : "did not ask about the browser account with the member's email");
};

module.exports.saysAddOnNotEnabled = (output) => {
  const text = allText(output);
  const pass = /Release Autopilot add-on enabled/i.test(text) && !/\balpha\b/i.test(text);
  return result(pass, pass ? "says the add-on is not enabled" : "did not use the add-on wording (or mentioned the alpha)");
};

module.exports.noCapabilityQuestion = (output) => {
  const asked = traj(output).filter((t) => t.tool === "ask-question" &&
    ((t.arguments && t.arguments.options) || []).some((o) => /auto-releasing|auto-cleanup/i.test(String(o.label || ""))));
  return result(asked.length === 0, asked.length ? "started the setup wizard (asked for capabilities)" : "did not start the wizard");
};

module.exports.saysAutoFlaggingOff = (output) => {
  const text = allText(output).toLowerCase();
  const pass = /auto-flagging (is )?(turned )?off|auto-flagging is not (turned )?on|auto-flagging isn't (turned )?on/.test(text);
  return result(pass, pass ? "says auto-flagging is off for the account" : "did not say auto-flagging is off");
};

module.exports.archivalQuestionHasAutomationsLink = (output) => {
  const pass = askPrompts(output).some((p) => AUTOMATIONS_LINK.test(p) && /archiv/i.test(p));
  return result(pass, pass ? "auto-archival question contains the Automations settings link" : "no archival question contains /settings/automations");
};

// Step 6 must not walk the user through cleanup or archival they did not pick.
const asksAbout = (output, re) => askPrompts(output).filter((p) => re.test(p));
const CLEANUP = /auto-cleanup|automated flag cleanup|flag cleanup/i;
const ARCHIVAL = /auto-archival|automatic archival/i;
module.exports.noCleanupQuestion = (output) => {
  const hit = asksAbout(output, CLEANUP).filter((p) => !/capabilit/i.test(p));
  return result(hit.length === 0, hit.length ? `asked about unpicked auto-cleanup: "${hit[0].slice(0, 90)}"` : "no auto-cleanup step");
};
module.exports.noArchivalQuestion = (output) => {
  const hit = asksAbout(output, ARCHIVAL).filter((p) => !/capabilit/i.test(p));
  return result(hit.length === 0, hit.length ? `asked about unpicked auto-archival: "${hit[0].slice(0, 90)}"` : "no auto-archival step");
};

// A diagnosis request is answered before any setup: the agent gives the first
// failed check (the repo is not mapped, or auto-flagging is off) before its
// first question, and that question is an offer, not the capability picker.
// (An unscripted offer gets the harness's first option, so the flow may
// continue into setup; writes are then graded by confirmsBeforeWriting.)
module.exports.diagnosesBeforeOffering = (output) => {
  const steps = traj(output);
  const firstAsk = steps.findIndex((t) => t.tool === "ask-question");
  const turns = ((output && output.assistant_turns) || []).map((x) => (typeof x === "string" ? { text: x } : x || {}));
  const firstAskTurn = firstAsk === -1 ? Infinity : steps[firstAsk].turn;
  const before = turns.filter((x) => (x.turn === undefined ? true : x.turn <= firstAskTurn)).map((x) => x.text || "").join("\n").toLowerCase()
    + (firstAsk === -1 ? finalText(output).toLowerCase() : String(steps[firstAsk].arguments.prompt || "").toLowerCase());
  const saidOff = /auto-flagging (is )?(turned )?off|auto-flagging is not (turned )?on|auto-flagging isn't (turned )?on|nothing is set up|isn't set up|not set up|(is )?not mapped|isn't mapped|not connected to a project|isn't connected to a project/.test(before);
  const firstIsPicker = firstAsk !== -1 && ((steps[firstAsk].arguments.options || []).some((o) => /auto-releasing|auto-cleanup|auto-archival/i.test(String(o.label || ""))));
  const pass = saidOff && !firstIsPicker;
  return result(pass, `said why before asking: ${saidOff}; first question is the capability picker: ${firstIsPicker}`);
};

module.exports.noUnconfirmedWrites = (output) => {
  if (writes(output).length === 0) return result(true, "no writes");
  return module.exports.confirmsBeforeWriting(output);
};

// The agent backend ignores approvalRequired; auto-flagging always waits for
// "@launchdarkly approve". The skill never sends the field.
module.exports.neverSendsApproval = (output) => {
  const bad = writes(output).filter((t) => {
    const a = t.arguments || {};
    return (a.autoFlagging && "approvalRequired" in a.autoFlagging) || (a.autoReleasing && "approvalRequired" in a.autoReleasing);
  });
  return result(bad.length === 0, bad.length ? `sent approvalRequired via ${bad[0].tool}` : "never sent approvalRequired");
};

// Release setup runs only for auto-releasing: no environment question and no
// release plan or policy lookup otherwise.
module.exports.noReleaseSetup = (output) => {
  const steps = traj(output);
  const lookups = steps.filter((t) => t.tool === "get-environment-release-plans" || t.tool === "get-release-policies");
  const envQ = steps.filter((t) => t.tool === "ask-question" && /environment/i.test(String((t.arguments && t.arguments.prompt) || "")));
  const pass = lookups.length === 0 && envQ.length === 0;
  return result(pass, `release lookups: ${lookups.length}, environment questions: ${envQ.length}`);
};

// On flow=authorize the App is installed; the question is about authorizing,
// with no org-owner pause.
module.exports.authorizeQuestionNoOrgOwner = (output) => {
  const q = traj(output).filter((t) => t.tool === "ask-question" && String(t.arguments.prompt || "").includes("flow=authorize"));
  if (!q.length) return result(false, "no question contains the authorize link");
  const labels = (q[0].arguments.options || []).map((o) => String(o.label || ""));
  const pass = /authoriz/i.test(q[0].arguments.prompt) && !labels.some((l) => /org owner/i.test(l));
  return result(pass, `prompt mentions authorize: ${/authoriz/i.test(q[0].arguments.prompt)}; options: ${labels.join(" | ")}`);
};

// While GitHub is disconnected the wizard pauses: no repo question, and the
// final message gives the resume phrase.
module.exports.pausesBeforeMapping = (output) => {
  const repoQ = traj(output).filter((t) => t.tool === "ask-question" &&
    ((t.arguments && t.arguments.options) || []).some((o) => /\w+\/\w+/.test(String(o.label || ""))) &&
    /repo/i.test(String((t.arguments && t.arguments.prompt) || "")));
  const resume = /continue Release Autopilot setup/i.test(finalText(output));
  const pass = repoQ.length === 0 && resume;
  return result(pass, `repo questions: ${repoQ.length}; resume phrase in final message: ${resume}`);
};

// Release setup lookups for one project and the environments the case
// selects. Every release-plans call names the project and a selected
// environment. If the first call is the account-wide 403, there is exactly
// one plans call and no release policy read. If it succeeds, every selected
// environment has a successful plans lookup.
const isForbidden = (t) => /403|not allow/i.test(String(t.mock_response_preview || ""));
const releaseSetupLookups = (projectKey, selectedEnvs) => (output) => {
  const steps = traj(output);
  const plans = steps.filter((t) => t.tool === "get-environment-release-plans");
  if (!plans.length) return result(false, "never checked release plans");
  const bad = plans.find((t) => (t.arguments || {}).projectKey !== projectKey || !selectedEnvs.includes((t.arguments || {}).environmentKey));
  if (bad) return result(false, `release-plans lookup outside ${projectKey} ${JSON.stringify(selectedEnvs)}: ${JSON.stringify(bad.arguments)}`);
  if (isForbidden(plans[0])) {
    const policies = steps.filter((t) => t.tool === "get-release-policies").length;
    return result(plans.length === 1 && policies === 0, `403 path: plans lookups ${plans.length}; policy reads: ${policies}`);
  }
  const looked = new Set(plans.filter((t) => !isForbidden(t)).map((t) => t.arguments.environmentKey));
  const missing = selectedEnvs.filter((e) => !looked.has(e));
  return result(missing.length === 0, missing.length ? `release plans path: no successful lookup for ${missing.join(", ")}` : `release plans path: looked up ${[...looked].join(", ")}`);
};
// The 403 case selects Test and Production; the other case selects Production.
module.exports.releaseSetupLookupsTestProduction = releaseSetupLookups("default", ["test", "production"]);
module.exports.releaseSetupLookupsProduction = releaseSetupLookups("default", ["production"]);

// A browser step question: a "Done" option and a settings topic (by link or by
// words), so a pre-confirm question without the right link is still caught.
const BROWSER_TOPIC = /settings\/(automations|lifecycle|vega)|automations settings|lifecycle settings|vega settings|own key|api key|flag cleanup|automatic archival|auto-archival|auto-cleanup/i;
const isBrowserStepQuestion = (t) => t.tool === "ask-question" &&
  ((t.arguments && t.arguments.options) || []).some((o) => /^done\b/i.test(String(o.label || ""))) &&
  BROWSER_TOPIC.test(String((t.arguments && t.arguments.prompt) || "")) &&
  !/github/i.test(String((t.arguments && t.arguments.prompt) || ""));

// Browser steps that change settings come only after "Looks good".
module.exports.browserStepsAfterConfirm = (output) => {
  const steps = traj(output);
  const browser = steps.findIndex(isBrowserStepQuestion);
  if (browser === -1) return result(false, "no browser step question");
  const approved = approvedConfirmBefore(steps, browser);
  return result(approved !== -1, approved !== -1 ? `approved at ${approved}, first browser step at ${browser}` : `browser step at ${browser} without a "Looks good" answer before it`);
};

// Preview never asks the user to change something in the browser, and lists it.
module.exports.previewListsBrowserSteps = (output) => {
  const asked = traj(output).filter(isBrowserStepQuestion).length;
  const listed = AUTOMATIONS_LINK.test(finalText(output));
  return result(asked === 0 && listed, `browser step questions: ${asked}; Automations link listed: ${listed}`);
};

// Archival-only setup needs no GitHub step and no repo mapping.
module.exports.noGithubOrMapping = (output) => {
  const steps = traj(output);
  const repoWrites = steps.filter(isRepoWrite).length;
  const ghQ = steps.filter((t) => t.tool === "ask-question" && (
    /github/i.test(String((t.arguments && t.arguments.prompt) || "")) ||
    ((t.arguments && t.arguments.options) || []).some((o) => /^[\w.-]+\/[\w.-]+$/.test(String(o.label || "")))
  )).length;
  return result(repoWrites === 0 && ghQ === 0, `repo writes: ${repoWrites}; GitHub or repo-picker questions: ${ghQ}`);
};

module.exports.storefrontAutoFlaggingOn = (output) => {
  const steps = traj(output);
  const w = steps.findIndex((t) => isRepoUpdate(t) && (t.arguments || {}).repo === "acme/storefront" &&
    t.arguments.autoFlagging && t.arguments.autoFlagging.enabled === true);
  if (w === -1) return result(false, "did not clear the repo's auto-flagging override");
  const verified = steps.slice(w + 1).some((t) => t.tool === "get-automations" && (t.arguments || {}).repo === "acme/storefront");
  return result(verified, verified ? "turned auto-flagging on for acme/storefront and read it back" : "turned it on but never verified the repo's effective value");
};

module.exports.byokQuestionHasAutomationsLink = (output) => {
  const pass = askPrompts(output).some((p) => AUTOMATIONS_LINK.test(p));
  return result(pass, pass ? "bring-your-own-key question contains the Automations settings link" : "no question contains /projects/{key}/settings/automations");
};

// Preview with GitHub disconnected and auto-releasing picked lists the
// deferred release setup, not only repo mapping.
module.exports.previewListsDeferredReleaseSetup = (output) => {
  const text = finalText(output).toLowerCase();
  const mapping = /map/.test(text) && /github/.test(text);
  const release = /environment/.test(text) && /release plan/.test(text);
  return result(mapping && release, `lists mapping after GitHub: ${mapping}; lists environments and release plans: ${release}`);
};

// Auto-cleanup is an MCP write after "Looks good": a cleanup object for the
// project with a running schedule and acme/demo among the repositories.
module.exports.cleanupWrittenAfterConfirm = (output) => {
  const steps = traj(output);
  const w = steps.findIndex((t) => t.tool === "update-automations" && (t.arguments || {}).cleanup);
  if (w === -1) return result(false, "never wrote the cleanup settings");
  const c = steps[w].arguments.cleanup;
  const approved = approvedConfirmBefore(steps, w);
  const ok = approved !== -1 && steps[w].arguments.projectKey === "default" && c.schedule && c.schedule !== "disabled" &&
    Array.isArray(c.repositories) && c.repositories.includes("acme/demo");
  return result(ok, `cleanup write at ${w} (approved at ${approved}): ${JSON.stringify(steps[w].arguments)}`);
};

module.exports.previewListsCleanup = (output) => {
  const text = finalText(output).toLowerCase();
  const cleanupWrites = traj(output).filter((t) => t.tool === "update-automations" && (t.arguments || {}).cleanup).length;
  const listed = /cleanup/.test(text);
  return result(listed && cleanupWrites === 0, `cleanup listed: ${listed}; cleanup writes: ${cleanupWrites}`);
};

// Starter plan for production: progressive, one phase for everyone at
// 10% -> 25% -> 50% with 4-hour holds, created before the repo write and set
// as the environment's default.
module.exports.starterPlanProgressive = (output) => {
  const steps = traj(output);
  const ci = steps.findIndex((t) => t.tool === "create-environment-release-plan" && (t.arguments || {}).environmentKey === "production" &&
    !/error/i.test(String(t.mock_response_preview || "")));
  if (ci === -1) return result(false, "no production release plan created (or the create was rejected)");
  const pr = steps[ci].arguments.progressiveRelease || {};
  const phases = pr.phases || [];
  const one = phases.length === 1 && (phases[0].clauses || []).some((c) => c.attribute === "kind");
  const allocs = one ? (phases[0].steps || []).map((s) => s.allocation) : [];
  const stepsOk = JSON.stringify(allocs) === JSON.stringify([10000, 25000, 50000]) &&
    phases[0].steps.every((s) => s.durationMillis === 14400000);
  const key = steps[ci].arguments.key;
  const di = steps.findIndex((t) => t.tool === "update-default-environment-release-plan" && (t.arguments || {}).releasePlanKey === key && t.arguments.default === true);
  const ri = steps.findIndex((t) => t.tool === "update-automations" && t.arguments && t.arguments.repo);
  const pass = one && stepsOk && di > ci && (ri === -1 || ci < ri);
  return result(pass, `one phase with the kind clause: ${one}; steps ${JSON.stringify(allocs)} with 4h holds: ${stepsOk}; default set after create: ${di > ci}; plan before repo write: ${ri === -1 || ci < ri}`);
};

// A release plans read that fails with anything but the plan 403 stops
// release setup for the project: no policy read, no plan, and the repo
// keeps auto-releasing off.
module.exports.stopsReleaseSetupOnPlanError = (output) => {
  const steps = traj(output);
  const policies = steps.filter((t) => t.tool === "get-release-policies").length;
  const creates = steps.filter((t) => t.tool === "create-environment-release-plan").length;
  const releasingOn = steps.some((t) => isRepoUpdate(t) && t.arguments.autoReleasing && t.arguments.autoReleasing.enabled === true);
  return result(policies === 0 && creates === 0 && !releasingOn, `policy reads: ${policies}; plans created: ${creates}; auto-releasing turned on for a repo: ${releasingOn}`);
};

// Making another plan the default says which default it replaces.
module.exports.saysReplacesDefault = (output) => {
  const pass = /replaces\s+[`"*]*(fast|fast rollout)[`"*]*\s+as\s+the\s+default/i.test([allText(output), ...askPrompts(output)].join("\n"));
  return result(pass, pass ? "says the plan replaces Fast as the default" : "never says the new default replaces the current one");
};

// Verification confirms GitHub works, names each configured repo, and offers
// a test pull request.
module.exports.verifyReportsSetup = (output) => {
  const text = finalText(output);
  const github = /github[^.\n]{0,40}\bconnected\b/i.test(text) && !/not connected/i.test(text);
  const repo = text.includes("acme/demo");
  const testPr = /test pull request|test PR/i.test(text);
  return result(github && repo && testPr, `GitHub connected: ${github}; lists acme/demo: ${repo}; offers a test PR: ${testPr}`);
};

// Adding a repo to a running cleanup sends the whole list: existing plus new.
module.exports.cleanupKeepsExistingRepos = (output) => {
  const w = traj(output).find((t) => t.tool === "update-automations" && (t.arguments || {}).cleanup && t.arguments.cleanup.repositories);
  if (!w) return result(false, "never wrote cleanup repositories");
  const repos = w.arguments.cleanup.repositories;
  const pass = repos.includes("acme/api") && repos.includes("acme/demo");
  return result(pass, `cleanup repositories written: ${JSON.stringify(repos)}`);
};

// An environment with a complete plan the user keeps: set it as default, do
// not create another.
module.exports.existingPlanSetAsDefault = (output) => {
  const steps = traj(output);
  const created = steps.filter((t) => t.tool === "create-environment-release-plan").length;
  const def = steps.some((t) => t.tool === "update-default-environment-release-plan" && (t.arguments || {}).releasePlanKey === "gradual" && t.arguments.default === true);
  return result(created === 0 && def, `plans created: ${created}; existing plan set as default: ${def}`);
};

// Archival already on: nothing to do for it.
module.exports.noArchivalStep = (output) => {
  const steps = traj(output);
  const asked = steps.filter((t) => t.tool === "ask-question" && /automatic archival|auto-archival/i.test(String((t.arguments && t.arguments.prompt) || "")) &&
    ((t.arguments && t.arguments.options) || []).some((o) => /^done\b/i.test(String(o.label || "")))).length;
  const writes = steps.filter((t) => t.tool === "update-automations" && (t.arguments || {}).archival).length;
  return result(asked === 0 && writes === 0, `archival browser questions: ${asked}; archival writes: ${writes}`);
};

module.exports.reportListsDefaultPlan = (output) => {
  const text = finalText(output).toLowerCase();
  const pass = /default/.test(text) && /progressive/.test(text) && /production/.test(text);
  return result(pass, pass ? "report names production's default plan" : "report does not name the default plan");
};

module.exports.reportListsCleanup = (output) => {
  const text = finalText(output).toLowerCase();
  const pass = /cleanup/.test(text) && /weekly/.test(text) && text.includes("acme/demo");
  return result(pass, pass ? "report lists the cleanup schedule and repository" : "report does not list the cleanup schedule and repository");
};



// The GitHub App install cannot be read: read it once more, then pause with
// the resume phrase. No writes and no repo question.
module.exports.pausesOnReposError = (output) => {
  const steps = traj(output);
  const reads = steps.filter((t) => t.tool === "get-automations" && !(t.arguments || {}).section).length;
  const repoQ = steps.filter((t) => t.tool === "ask-question" &&
    ((t.arguments && t.arguments.options) || []).some((o) => /^[\w.-]+\/[\w.-]+$/.test(String(o.label || "")))).length;
  const resume = /continue Release Autopilot setup/i.test(finalText(output));
  const w = writes(output).length;
  return result(reads >= 2 && repoQ === 0 && resume && w === 0, `install reads: ${reads}; repo questions: ${repoQ}; resume phrase: ${resume}; writes: ${w}`);
};


// Preview with an unreadable install lists the mapping for later and no
// GitHub connect step (there is no connect link; GitHub is connected).
module.exports.previewReposErrorNoConnect = (output) => {
  const text = finalText(output);
  const mapping = /map/i.test(text) && /can be read|could not be read|cannot be read/i.test(text);
  const connect = /connect github|install the (launchdarkly )?github app|github\/connect|authorize github/i.test(text);
  const w = writes(output).length;
  return result(mapping && !connect && w === 0, `lists mapping for later: ${mapping}; Connect GitHub item: ${connect}; writes: ${w}`);
};

// Release plans not available on the account: tell the user to contact
// LaunchDarkly support, and never mention release policies.
module.exports.saysContactSupport = (output) => {
  const text = [allText(output), ...askPrompts(output)].join("\n");
  const support = /contact (launchdarkly )?support|launchdarkly support/i.test(text);
  const policy = /release polic/i.test(text);
  return result(support && !policy, `contact support: ${support}; mentions release policies: ${policy}`);
};

// A release plan tool is missing from the server: release setup is skipped
// with an update-or-reconnect message (not contact support), no plan
// writes, an explicit auto-releasing off override (not inherited from the
// account), and auto-flagging still turned on for the repo.
module.exports.missingPlanToolsSkipsRelease = (output) => {
  const steps = traj(output);
  const text = [allText(output), ...askPrompts(output)].join("\n");
  const support = /contact (launchdarkly )?support|launchdarkly support|not available on your account/i.test(text);
  const reconnect = /\b(update|reconnect)\b/i.test(text) && /mcp server/i.test(text);
  const planWrites = steps.filter((t) => /release-plan/.test(t.tool) && t.tool !== "get-environment-release-plans").length;
  const flagging = steps.filter(isRepoUpdate).some((t) => t.arguments.autoFlagging && t.arguments.autoFlagging.enabled === true);
  const releasingOff = module.exports.repoTurnsAutoReleasingOff(output);
  const pass = !support && reconnect && planWrites === 0 && flagging && releasingOff.pass;
  return result(pass, `contact support: ${support}; update or reconnect: ${reconnect}; plan writes: ${planWrites}; auto-flagging on: ${flagging}; auto-releasing off override: ${releasingOff.reason}`);
};

// ---------------------------------------------------------------------------
// Flag release plan (through launchdarkly-release-plans). Its REST commands
// are shown to the user, who runs them and pastes the output (a scripted
// { when, text } answer); the agent never runs them.

module.exports.everyCommandBeta = checks.everyCommandBeta;
module.exports.agentNeverUsesToken = checks.agentNeverUsesToken;

const lastPlanCreate = (output) => checks.planCreates(output).filter((c) => c.body).pop();
const turnOf = (steps, test) => {
  const i = steps.findIndex(test);
  return i === -1 ? undefined : steps[i].turn;
};

// The create command for the flag release plan is shown after "Looks good"
// and after production's new release plan and its default. It names that
// plan and makes it the project's default.
module.exports.flagReleasePlanAfterEnvPlans = (output) => {
  const steps = traj(output);
  const c = lastPlanCreate(output);
  if (!c) return result(false, "no flag release plan create command with a JSON body shown");
  const create = steps.findIndex((t) => t.tool === "create-environment-release-plan" && (t.arguments || {}).environmentKey === "production");
  const envKey = create === -1 ? null : steps[create].arguments.key;
  const defTurn = turnOf(steps, (t) => t.tool === "update-default-environment-release-plan" && (t.arguments || {}).environmentKey === "production" && t.arguments.default === true);
  const ci = steps.findIndex(isConfirmQuestion);
  const approved = ci !== -1 && approvedConfirmBefore(steps, ci + 1) !== -1;
  const confirmTurn = ci === -1 ? undefined : steps[ci].turn;
  const envs = c.body.environments || [];
  const points = envs.length === 1 && envs[0].environmentKey === "production" && envs[0].environmentReleasePlanKey === envKey;
  const order = defTurn !== undefined && confirmTurn !== undefined && c.turn >= defTurn && c.turn > confirmTurn;
  const pass = points && order && approved && c.body.isDefault === true;
  return result(pass, `names production's new plan ${envKey}: ${points}; shown after "Looks good" and the default: ${order}; approved: ${approved}; default: ${c.body.isDefault}`);
};

// The pasted create response is read: the report names the plan as set up.
module.exports.flagReleasePlanVerified = (output) => {
  const text = finalText(output);
  const pass = /flag release plan/i.test(text) && /default release/i.test(text) && !/not verified|could not verify/i.test(text);
  return result(pass, pass ? "the report names the flag release plan from the pasted response" : "the report does not name the flag release plan as set up");
};

// Text the user saw up to and including the Step 7 confirmation.
function textThroughConfirm(output) {
  const steps = traj(output);
  const ci = steps.findIndex(isConfirmQuestion);
  if (ci === -1) return null;
  const turn = steps[ci].turn;
  const turns = ((output && output.assistant_turns) || [])
    .filter((x) => typeof x !== "object" || x.turn === undefined || turn === undefined || x.turn <= turn)
    .map((x) => (typeof x === "string" ? x : String(x.text || "")));
  return [...turns, String((steps[ci].arguments && steps[ci].arguments.prompt) || "")].join("\n");
}

// The confirmation lists the flag release plan.
module.exports.confirmListsFlagReleasePlan = (output) => {
  const text = textThroughConfirm(output);
  if (text === null) return result(false, "no confirmation question");
  const pass = /flag release plan/i.test(text);
  return result(pass, pass ? "the confirmation lists the flag release plan" : "the confirmation does not mention the flag release plan");
};

// The user skips the flag release plan step: the report lists it as a
// follow-up with the exact command (the endpoint and the beta header).
module.exports.followUpHasFlagReleasePlanCommand = (output) => {
  const finalOnly = { trajectory: [], assistant_turns: [], response: finalText(output) };
  const cmds = checks.shownCommands(finalOnly).filter((c) => /\/api\/v2\/projects\/default\/flag-release-plans/.test(c.path));
  const beta = cmds.length > 0 && cmds.every((c) => c.beta);
  const asked = checks.asksForToken(checks.userFacingText(output));
  return result(beta && !asked, `flag release plan commands in the report: ${cmds.length}; all with the beta header: ${beta}; asks for the token: ${asked}`);
};

// Preview lists the flag release plan, writes nothing, and asks the user to
// run nothing.
module.exports.previewListsFlagReleasePlan = (output) => {
  const listed = /flag release plan/i.test(finalText(output));
  const asked = traj(output).filter((t) => t.tool === "ask-question" && /run this command/i.test(JSON.stringify(t.arguments || {}))).length;
  const w = writes(output).length;
  return result(listed && asked === 0 && w === 0, `lists the flag release plan: ${listed}; asks to run a command: ${asked}; writes: ${w}`);
};

// The project's default flag release plan does not match: after "Looks
// good", the replace command keeps its key, the default on, its version, and
// production's release plan. No create command.
module.exports.flagReleasePlanUpdatedInPlace = (output) => {
  const steps = traj(output);
  const put = checks.shownCommands(output).find((c) => c.method === "PUT" && /\/flag-release-plans\/staged-rollout$/.test(c.path));
  const posts = checks.planCreates(output).length;
  if (!put || !put.body) return result(false, `no replace command for staged-rollout; create commands: ${posts}`);
  const b = put.body;
  const envs = (b.environments || []).map((e) => `${e.environmentKey}:${e.environmentReleasePlanKey || "immediate"}`);
  const ci = steps.findIndex(isConfirmQuestion);
  const after = ci !== -1 && put.turn > steps[ci].turn && approvedConfirmBefore(steps, ci + 1) !== -1;
  const pass = b.isDefault === true && b.version === 2 && JSON.stringify(envs) === JSON.stringify(["production:gradual"]) && after && posts === 0;
  return result(pass, `isDefault ${b.isDefault}; version ${b.version}; environments ${JSON.stringify(envs)}; after "Looks good": ${after}; create commands: ${posts}`);
};

// The flag release plan is a follow-up, and auto-releasing stays on as the
// user picked: the repo write turns it on, and no write turns it off.
module.exports.autoReleasingOnWithFollowUp = (output) => {
  const repo = traj(output).filter((t) => isRepoUpdate(t) && t.arguments.repo === "acme/demo");
  const on = repo.some((t) => t.arguments.autoReleasing && t.arguments.autoReleasing.enabled === true);
  const off = repo.some((t) => t.arguments.autoReleasing && t.arguments.autoReleasing.enabled === false);
  return result(on && !off, `auto-releasing turned on for acme/demo: ${on}; turned off: ${off}`);
};

// The summary and the final report say auto-releasing proposes no release
// until the flag release plan exists.
const NO_RELEASE_UNTIL = /(proposes? no release|won'?t propose (a |any )?releases?|will not propose (a |any )?releases?|doesn'?t propose (a |any )?releases?)[^.\n]{0,60}until[^.\n]{0,40}flag release plan/i;
module.exports.notesNoReleaseUntilPlan = (output) => {
  const confirm = textThroughConfirm(output) || "";
  const inSummary = NO_RELEASE_UNTIL.test(confirm);
  const inReport = NO_RELEASE_UNTIL.test(finalText(output));
  return result(inSummary && inReport, `in the confirmation: ${inSummary}; in the final report: ${inReport}`);
};
