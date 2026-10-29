/**
 * Trajectory helpers shared across every suite.
 *
 * The agent provider returns output as a parsed object (via shared/transform.js):
 *   {
 *     response: "<final agent text>",
 *     trajectory: [
 *       { tool: "get-agent-configs", arguments: {...}, turn: 1 },
 *       { tool: "setup-agent-config", arguments: {...}, turn: 2 },
 *       ...
 *     ],
 *     tools_called: ["get-agent-configs", "setup-agent-config"],
 *     turn_count: 3
 *   }
 *
 * Convention for "X happens after Y" trajectory checks:
 *   - Use the FIRST occurrence of the prerequisite (Y): tools.indexOf(Y)
 *   - Use the LAST occurrence of the verifier (X): tools.lastIndexOf(X)
 *   - Rationale: agents often call `get-foo` before AND after mutating. Using
 *     indexOf for both would silently pass against the pre-mutation call.
 *
 * NOTE: promptfoo evaluates inline `type: javascript` assertions via
 *   new Function("output", "context", "process", body)
 * which means `require` is NOT available. So this module is used by scripts
 * (aggregate, diff-changed-skills) — inline YAML assertions implement the
 * same patterns by hand using indexOf / lastIndexOf directly.
 */

function getTools(output) {
  if (!output || typeof output !== "object") return [];
  return Array.isArray(output.tools_called) ? output.tools_called : [];
}

function getTrajectory(output) {
  if (!output || typeof output !== "object") return [];
  return Array.isArray(output.trajectory) ? output.trajectory : [];
}

/** First call of a named tool. Returns { call, idx } — idx is -1 if not found. */
function firstCallOf(output, name) {
  const trajectory = getTrajectory(output);
  for (let i = 0; i < trajectory.length; i++) {
    if (trajectory[i] && trajectory[i].tool === name) {
      return { call: trajectory[i], idx: i };
    }
  }
  return { call: null, idx: -1 };
}

/** Last call of a named tool. Returns { call, idx } — idx is -1 if not found. */
function lastCallOf(output, name) {
  const trajectory = getTrajectory(output);
  for (let i = trajectory.length - 1; i >= 0; i--) {
    if (trajectory[i] && trajectory[i].tool === name) {
      return { call: trajectory[i], idx: i };
    }
  }
  return { call: null, idx: -1 };
}

function called(output, name) {
  return getTools(output).includes(name);
}

function calledAny(output, names) {
  const tools = getTools(output);
  return names.some((n) => tools.includes(n));
}

function calledNone(output, names) {
  const tools = getTools(output);
  return names.every((n) => !tools.includes(n));
}

/**
 * Assert that the LAST occurrence of `after` happens after the FIRST
 * occurrence of `before`. Returns a promptfoo-shaped grading result.
 */
function expectAfter(output, { before, after }) {
  const beforeIdx = firstCallOf(output, before).idx;
  const afterIdx = lastCallOf(output, after).idx;
  const pass = beforeIdx >= 0 && afterIdx > beforeIdx;
  return {
    pass,
    score: pass ? 1 : 0,
    reason: `${before}@${beforeIdx} ${after}@${afterIdx}`,
  };
}

/** Assert that none of the listed tools were called. */
function expectNotCalled(output, names) {
  const tools = getTools(output);
  const hits = names.filter((n) => tools.includes(n));
  const pass = hits.length === 0;
  return {
    pass,
    score: pass ? 1 : 0,
    reason: pass
      ? `correctly avoided ${names.join(", ")}`
      : `called forbidden tools: ${hits.join(", ")}`,
  };
}

/** Assert that at least one of the listed tools was called. */
function expectAnyCalled(output, names) {
  const tools = getTools(output);
  const hit = names.find((n) => tools.includes(n));
  const pass = Boolean(hit);
  return {
    pass,
    score: pass ? 1 : 0,
    reason: pass
      ? `called ${hit}`
      : `none of [${names.join(", ")}] called; tools: ${tools.join(" -> ") || "(none)"}`,
  };
}

module.exports = {
  getTools,
  getTrajectory,
  firstCallOf,
  lastCallOf,
  called,
  calledAny,
  calledNone,
  expectAfter,
  expectNotCalled,
  expectAnyCalled,
};
