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
  const wrong = maps.filter((m) => (m.arguments || {}).repo !== repo || (project && (m.arguments || {}).projectKey && m.arguments.projectKey !== project));
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
  return result(repo === -1 || plan < repo, `plan at ${plan}, repo write at ${repo}`);
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
  const hit = /setup complete|setup is complete|you're all set|is (now )?live/i.exec(text);
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
