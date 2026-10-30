// Assertions for the Release Autopilot onboarding suite. Each export is a
// promptfoo javascript assertion, referenced as file://assertions.js:<name>.

const WRITE_TOOLS = new Set([
  "update-release-autopilot-settings",
  "update-release-autopilot-repo-settings",
  "delete-release-autopilot-repo-settings",
  "create-release-plan",
  "create-metric",
]);

const traj = (output) => (output && output.trajectory) || [];
const writes = (output) => traj(output).filter((t) => WRITE_TOOLS.has(t.tool));
const result = (pass, reason) => ({ pass, score: pass ? 1 : 0, reason });

function isConfirmQuestion(step) {
  if (step.tool !== "ask-question") return false;
  const labels = ((step.arguments && step.arguments.options) || []).map((o) =>
    String(o.label || "").toLowerCase(),
  );
  return labels.some((l) => l.includes("looks good"));
}

// Index of the last confirm question before `limit` whose answer was "Looks good",
// or -1. Showing the confirm question is not approval; only that answer is.
function approvedConfirmBefore(steps, limit) {
  for (let i = limit - 1; i >= 0; i--) {
    const step = steps[i];
    if (!isConfirmQuestion(step)) continue;
    const ok = ((step.arguments && step.arguments.options) || [])
      .filter((o) => String(o.label || "").toLowerCase().includes("looks good"))
      .map((o) => o.id);
    if ((step.selected || []).some((id) => ok.includes(id))) return i;
  }
  return -1;
}

module.exports.noWrites = (output) => {
  const w = writes(output);
  return result(w.length === 0, w.length ? `wrote: ${w.map((t) => t.tool).join(", ")}` : "no writes");
};

module.exports.confirmsBeforeWriting = (output) => {
  const steps = traj(output);
  const firstWrite = steps.findIndex((t) => WRITE_TOOLS.has(t.tool));
  if (firstWrite === -1) return result(false, "never wrote, so the confirmed plan was not applied");
  let confirm = -1;
  for (let i = 0; i < firstWrite; i++) if (isConfirmQuestion(steps[i])) confirm = i;
  if (confirm === -1) return result(false, "wrote without a confirm question");
  const step = steps[confirm];
  const ok = ((step.arguments && step.arguments.options) || [])
    .filter((o) => String(o.label || "").toLowerCase().includes("looks good"))
    .map((o) => o.id);
  const approved = (step.selected || []).some((id) => ok.includes(id));
  return result(approved, approved ? `approved at ${confirm}, first write at ${firstWrite}` : `wrote after confirm answer ${JSON.stringify(step.selected)}`);
};

// Every repo write targets `repo` in `project` and sends enabled:false for each cap.
const mapsRepoWithOverrides = (repo, project, caps) => (output) => {
  const maps = traj(output).filter((t) => t.tool === "update-release-autopilot-repo-settings");
  if (!maps.length) return result(false, "never wrote a repo mapping");
  const wrong = maps.filter((m) => (m.arguments || {}).repo !== repo || (project && (m.arguments || {}).projectKey !== project));
  if (wrong.length) return result(false, `wrote ${wrong.map((m) => `${m.arguments.repo}@${m.arguments.projectKey}`).join(", ")}; want only ${repo}@${project}`);
  const bad = maps.filter((m) => caps.some((c) => !(m.arguments[c] && m.arguments[c].enabled === false)));
  return result(bad.length === 0, bad.length ? `missing ${caps.join("/")} enabled:false` : `${repo} written with ${caps.join("/")} off`);
};

module.exports.accountWriteLast = (output) => {
  const steps = traj(output);
  const acct = steps.findIndex((t) => t.tool === "update-release-autopilot-settings");
  if (acct === -1) return result(false, "no account write");
  const laterWrite = steps.slice(acct + 1).some((t) => WRITE_TOOLS.has(t.tool));
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
  const n = traj(output).filter((t) => t.tool === "list-release-plans").length;
  return result(n <= 1, `list-release-plans called ${n} time(s)`);
};

module.exports.repoTurnsAutoReleasingOff = mapsRepoWithOverrides("acme/demo", "default", ["autoReleasing"]);
module.exports.storefrontAutoReleasingOff = mapsRepoWithOverrides("acme/storefront", null, ["autoReleasing"]);
module.exports.noRepoWrite = noneOf(["update-release-autopilot-repo-settings", "delete-release-autopilot-repo-settings"]);

module.exports.planBeforeRepoWrite = (output) => {
  const steps = traj(output);
  const plan = steps.findIndex((t) => t.tool === "create-release-plan");
  const repo = steps.findIndex((t) => t.tool === "update-release-autopilot-repo-settings");
  if (plan === -1) return result(false, "never created a release plan");
  if (repo === -1) return result(false, "never mapped acme/demo");
  const args = steps[repo].arguments || {};
  const pass = plan < repo && args.repo === "acme/demo" && args.projectKey === "default";
  return result(pass, `plan at ${plan}, repo write at ${repo} (${args.repo}@${args.projectKey})`);
};

module.exports.plansHaveClauses = (output) => {
  const plans = traj(output).filter((t) => t.tool === "create-release-plan");
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
module.exports.noReleasePlanCreated = noneOf(["create-release-plan"]);
module.exports.noAccountWrite = noneOf(["update-release-autopilot-settings"]);

const finalText = (output) => String((output && output.response) || "");

// Raw tool and field names the skill's voice rules ban from user-facing text.
const RAW_NAMES = [
  "update-release-autopilot", "get-release-autopilot", "list-release-autopilot",
  "githubRepoId", "enabledOverride", "autoReleasing", "autoFlagging", "approvalRequired",
  "create-release-plan", "list-release-plans", "list-release-policies",
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
  const acct = steps.findIndex((t) => t.tool === "update-release-autopilot-settings");
  const repo = steps.findIndex((t) => t.tool === "update-release-autopilot-repo-settings");
  if (acct === -1) return result(false, "never attempted the account write");
  const after = steps.slice(acct + 1).filter((t) => WRITE_TOOLS.has(t.tool));
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

module.exports.cleanupQuestionHasLifecycleLink = (output) => {
  const pass = askPrompts(output).some((p) => /\/projects\/[^/\s]+\/settings\/lifecycle/.test(p));
  return result(pass, pass ? "auto-cleanup question contains the lifecycle settings link" : "no question contains /settings/lifecycle");
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
  const hit = traj(output).filter((t) => t.tool.endsWith("-repo-settings") && /^(update|delete)/.test(t.tool) && (t.arguments || {}).repo === "acme/storefront");
  return result(hit.length === 0, hit.length ? `wrote acme/storefront: ${JSON.stringify(hit[0].arguments)}` : "acme/storefront left alone");
};

module.exports.relistsAfterDone = (output) => {
  const n = traj(output).filter((t) => t.tool === "list-release-autopilot-github-repos").length;
  return result(n >= 2, `listed GitHub repos ${n} time(s)`);
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

module.exports.archivalQuestionHasLifecycleLink = (output) => {
  const pass = askPrompts(output).some((p) => /\/projects\/[^/\s]+\/settings\/lifecycle/.test(p) && /archiv/i.test(p));
  return result(pass, pass ? "auto-archival question contains the lifecycle settings link" : "no archival question contains /settings/lifecycle");
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

// A diagnosis request is answered before any setup: the agent says auto-flagging
// is off before its first question, and that question is an offer, not the
// capability picker. (An unscripted offer gets the harness's first option, so
// the flow may continue into setup; writes are then graded by confirmsBeforeWriting.)
module.exports.diagnosesBeforeOffering = (output) => {
  const steps = traj(output);
  const firstAsk = steps.findIndex((t) => t.tool === "ask-question");
  const turns = ((output && output.assistant_turns) || []).map((x) => (typeof x === "string" ? { text: x } : x || {}));
  const firstAskTurn = firstAsk === -1 ? Infinity : steps[firstAsk].turn;
  const before = turns.filter((x) => (x.turn === undefined ? true : x.turn <= firstAskTurn)).map((x) => x.text || "").join("\n").toLowerCase()
    + (firstAsk === -1 ? finalText(output).toLowerCase() : String(steps[firstAsk].arguments.prompt || "").toLowerCase());
  const saidOff = /auto-flagging (is )?(turned )?off|auto-flagging is not (turned )?on|auto-flagging isn't (turned )?on|nothing is set up|isn't set up|not set up/.test(before);
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
  const lookups = steps.filter((t) => t.tool === "list-release-plans" || t.tool === "list-release-policies");
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

// Release setup lookups for one project, valid for both modes. Every
// release-plans call names the project and one of its environments. If the
// first call is the account-wide 403, there is exactly one plans call and a
// release-policies lookup for the project (release policies, today). If it
// succeeds, no policy lookup is required (environment release plans, at GA).
const releaseSetupLookups = (projectKey, envs) => (output) => {
  const steps = traj(output);
  const plans = steps.filter((t) => t.tool === "list-release-plans");
  if (!plans.length) return result(false, "never checked release plans");
  const badPlan = plans.find((t) => (t.arguments || {}).projectKey !== projectKey || !envs.includes((t.arguments || {}).environmentKey));
  if (badPlan) return result(false, `release-plans lookup with ${JSON.stringify(badPlan.arguments)}`);
  const forbidden = /403|not allow/i.test(String(plans[0].mock_response_preview || ""));
  if (!forbidden) return result(true, `release plans available; ${plans.length} lookup(s) for ${projectKey}`);
  const policies = steps.filter((t) => t.tool === "list-release-policies");
  const okPolicies = policies.filter((t) => (t.arguments || {}).projectKey === projectKey);
  const pass = plans.length === 1 && okPolicies.length >= 1 && okPolicies.length === policies.length;
  return result(pass, `release-plans lookups: ${plans.length}; release-policies lookups for ${projectKey}: ${okPolicies.length} of ${policies.length}`);
};
module.exports.releaseSetupLookupsDefault = releaseSetupLookups("default", ["test", "production"]);

// A browser step question: a "Done" option and a settings topic (by link or by
// words), so a pre-confirm question without the right link is still caught.
const BROWSER_TOPIC = /settings\/(lifecycle|vega)|lifecycle settings|vega settings|own key|api key|flag cleanup|automatic archival|auto-archival|auto-cleanup/i;
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
  const listed = /settings\/lifecycle/.test(finalText(output));
  return result(asked === 0 && listed, `browser step questions: ${asked}; lifecycle link listed: ${listed}`);
};

// Archival-only setup needs no GitHub step and no repo mapping.
module.exports.noGithubOrMapping = (output) => {
  const steps = traj(output);
  const repoWrites = steps.filter((t) => /^(update|delete)-release-autopilot-repo-settings$/.test(t.tool)).length;
  const ghQ = steps.filter((t) => t.tool === "ask-question" && (
    /github/i.test(String((t.arguments && t.arguments.prompt) || "")) ||
    ((t.arguments && t.arguments.options) || []).some((o) => /^[\w.-]+\/[\w.-]+$/.test(String(o.label || "")))
  )).length;
  return result(repoWrites === 0 && ghQ === 0, `repo writes: ${repoWrites}; GitHub or repo-picker questions: ${ghQ}`);
};

module.exports.storefrontAutoFlaggingOn = (output) => {
  const steps = traj(output);
  const w = steps.findIndex((t) => t.tool === "update-release-autopilot-repo-settings" && (t.arguments || {}).repo === "acme/storefront" &&
    t.arguments.autoFlagging && t.arguments.autoFlagging.enabled === true);
  if (w === -1) return result(false, "did not clear the repo's auto-flagging override");
  const verified = steps.slice(w + 1).some((t) => t.tool === "get-release-autopilot-repo-settings" && (t.arguments || {}).repo === "acme/storefront");
  return result(verified, verified ? "turned auto-flagging on for acme/storefront and read it back" : "turned it on but never verified the repo's effective value");
};

module.exports.byokQuestionHasVegaLink = (output) => {
  const pass = askPrompts(output).some((p) => /\/projects\/[^/\s]+\/settings\/vega/.test(p));
  return result(pass, pass ? "bring-your-own-key question contains the Vega settings link" : "no question contains /projects/{key}/settings/vega");
};

// Preview with GitHub disconnected and auto-releasing picked lists the
// deferred release setup, not only repo mapping.
module.exports.previewListsDeferredReleaseSetup = (output) => {
  const text = finalText(output).toLowerCase();
  const mapping = /map/.test(text) && /github/.test(text);
  const release = /environment/.test(text) && /release (polic|plan)/.test(text);
  return result(mapping && release, `lists mapping after GitHub: ${mapping}; lists environments and release policies/plans: ${release}`);
};
