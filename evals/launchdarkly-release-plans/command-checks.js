// Helpers for skills whose REST commands the user runs: the agent shows each
// command in a code block, the user runs it in their own terminal and pastes
// the output back (a scripted { when, text } answer). The agent never runs a
// command that uses a LaunchDarkly token. Used by this suite and by
// release-autopilot-onboarding.

const traj = (output) => (output && output.trajectory) || [];
const result = (pass, reason) => ({ pass, score: pass ? 1 : 0, reason });

const textOf = (x) => (typeof x === "string" ? x : String((x && x.text) || ""));

// User-facing text with the turn it appeared in: assistant turns, question
// prompts, and the final response (turn Infinity).
function shownText(output) {
  const items = (((output && output.assistant_turns) || [])).map((x) => ({ turn: typeof x === "object" && x.turn !== undefined ? x.turn : 0, text: textOf(x) }));
  for (const t of traj(output)) {
    if (t.tool === "ask-question") items.push({ turn: t.turn === undefined ? 0 : t.turn, text: String((t.arguments && t.arguments.prompt) || "") });
  }
  items.push({ turn: Infinity, text: String((output && output.response) || "") });
  return items;
}
const userFacingText = (output) => shownText(output).map((x) => x.text).join("\n");

// curl commands to the LaunchDarkly REST API shown to the user, each with
// its method, path, headers, parsed JSON body, and the turn it first showed.
function shownCommands(output) {
  const seen = new Map();
  for (const { turn, text } of shownText(output)) {
    for (const m of text.matchAll(/```[a-z]*\n([\s\S]*?)```/g)) {
      const block = m[1];
      if (!/\bcurl\b/.test(block) || !/\/api\/v2\//.test(block)) continue;
      const method = ((block.match(/-X\s+([A-Z]+)/) || [])[1]) || "GET";
      const path = ((block.match(/https?:\/\/[^\s"']*?(\/api\/v2\/[^\s"'?]*)/) || [])[1]) || "";
      const beta = /LD-API-Version:\s*beta/.test(block);
      let body;
      const here = block.match(/<<'?(\w+)'?\n([\s\S]*?)\n\1\b/);
      const inline = block.match(/--data(?:-raw)?\s+'([^']*)'/);
      const raw = here ? here[2] : inline ? inline[1] : null;
      if (raw) {
        try { body = JSON.parse(raw); } catch { body = undefined; }
      }
      const key = block.trim();
      if (!seen.has(key)) seen.set(key, { method, path, beta, body, block, turn });
    }
  }
  return [...seen.values()];
}

const isPlanCommand = (c, method) => c.method === method && /\/flag-release-plans(\/[^/]+)?$/.test(c.path);
const planCreates = (output) => shownCommands(output).filter((c) => c.method === "POST" && /\/flag-release-plans$/.test(c.path));
const planWrites = (output) => shownCommands(output).filter((c) => c.method !== "GET" && /\/flag-release-plans/.test(c.path));

const commands = (output) =>
  traj(output).filter((t) => t.tool === "Bash").map((t) => String((t.arguments && t.arguments.command) || ""));

// Commands the agent must never run: anything that calls the LaunchDarkly
// API or reads a token or the environment.
const AGENT_NEVER = [
  /\bcurl\b/,
  /LD_ACCESS_TOKEN/,
  /LD_BASE_URI/,
  /\bprintenv\b/,
  /(^|[;&|]\s*|\n\s*)(env|set|export -p|declare -x)\s*($|[;&|\n])/,
  /\bldcli\b/,
  /\.config\/ldcli/,
];

// Text that asks the user for the token, unless the same sentence says not to.
const ASKS_FOR_TOKEN = /\b(paste|share|send|give|provide|enter|type)\b[^.?!\n]{0,40}\b(api |access |personal )*token\b/i;
const NEGATED = /\b(never|don't|do not|not|no need|without)\b/i;
function asksForToken(text) {
  return text.split(/(?<=[.?!])\s+|\n/).some((s) => ASKS_FOR_TOKEN.test(s) && !NEGATED.test(s));
}

// The answer that marks a "Run this command" question.
const RUN_ANSWER = /done,? here'?s the output/i;

module.exports = {
  traj, result, shownText, userFacingText, shownCommands, isPlanCommand, planCreates, planWrites, commands, asksForToken, AGENT_NEVER,

  // Every REST command shown sends LD-API-Version: beta, and there was one.
  everyCommandBeta(output) {
    const cmds = shownCommands(output);
    const missing = cmds.filter((c) => !c.beta);
    return result(cmds.length > 0 && missing.length === 0,
      cmds.length === 0 ? "no REST command shown" : `${missing.length} of ${cmds.length} commands without LD-API-Version: beta`);
  },

  // The agent never ran a REST call or touched a token, and never asked for
  // the token in the chat.
  agentNeverUsesToken(output) {
    const ran = commands(output).filter((c) => AGENT_NEVER.some((re) => re.test(c)));
    const asked = asksForToken(userFacingText(output));
    return result(ran.length === 0 && !asked,
      `commands the agent ran that call the API or read a token: ${ran.length ? ran.join(" | ") : "none"}; asks for the token in the chat: ${asked}`);
  },

  // Every "Run this command" question shows the command itself, because the
  // user may see only the question while it is open. The command can be in
  // the question text or in the preview of the "Done, here's the output"
  // option. A preview on another option (such as Skip) does not count, and
  // neither does a preview that only points at the command ("full command
  // above") when the question text does not hold it. There must be at least
  // one such question.
  runQuestionShowsCommand(output) {
    const asks = traj(output).filter((t) => t.tool === "ask-question" &&
      ((t.arguments && t.arguments.options) || []).some((o) => RUN_ANSWER.test(String(o.label || ""))));
    const CODE = /```[a-z]*\n[\s\S]*?\bcurl\b[\s\S]*?\/api\/v2\/[\s\S]*?```/;
    const runPreviews = (t) => ((t.arguments || {}).options || []).filter((o) => RUN_ANSWER.test(String(o.label || ""))).map((o) => String(o.preview || ""));
    const showsCommand = (t) => [String((t.arguments || {}).prompt || ""), ...runPreviews(t)].some((x) => CODE.test(x));
    const missing = asks.filter((t) => !showsCommand(t));
    const refs = missing.filter((t) => runPreviews(t).some((p) => p.trim())).length;
    return result(asks.length > 0 && missing.length === 0,
      asks.length === 0 ? "no \"Run this command\" question" :
        `${missing.length} of ${asks.length} \"Run this command\" questions do not show the command${refs ? ` (${refs} with a preview that only points at it)` : ""}`);
  },

  // With the flag release plan tools on the server, the agent shows no REST
  // command and asks the user to run nothing.
  noCommandsShown(output) {
    const cmds = shownCommands(output);
    const runAsks = traj(output).filter((t) => t.tool === "ask-question" &&
      ((t.arguments && t.arguments.options) || []).some((o) => RUN_ANSWER.test(String(o.label || "")))).length;
    return result(cmds.length === 0 && runAsks === 0,
      `REST commands shown: ${cmds.length ? cmds.map((c) => `${c.method} ${c.path}`).join(", ") : "none"}; "Run this command" questions: ${runAsks}`);
  },

  // No write command shown: only reads.
  noWriteCommands(output) {
    const w = shownCommands(output).filter((c) => c.method !== "GET");
    return result(w.length === 0, w.length ? `write commands shown: ${w.map((c) => `${c.method} ${c.path}`).join(", ")}` : "no write commands");
  },
};
