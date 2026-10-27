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
  const confirm = steps.findIndex(isConfirmQuestion);
  return result(
    confirm !== -1 && confirm < firstWrite,
    confirm === -1 ? "wrote without a confirm question" : `confirm at ${confirm}, first write at ${firstWrite}`,
  );
};

const repoOverridesUnpicked = (caps) => (output) => {
  const maps = traj(output).filter((t) => t.tool === "update-release-autopilot-repo-settings");
  if (!maps.length) return result(false, "never mapped a repo");
  const bad = maps.filter((m) => caps.some((c) => !(m.arguments && m.arguments[c] && m.arguments[c].enabled === false)));
  return result(bad.length === 0, bad.length ? `missing ${caps.join("/")} enabled:false on ${bad.length} mapping(s)` : "overrides sent");
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

module.exports.repoTurnsAutoReleasingOff = repoOverridesUnpicked(["autoReleasing"]);
module.exports.noReleasePlanCreated = noneOf(["create-release-plan"]);
module.exports.noAccountWrite = noneOf(["update-release-autopilot-settings"]);
