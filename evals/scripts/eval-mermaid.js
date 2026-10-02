#!/usr/bin/env node
// eval-mermaid.js — turn a promptfoo results.json into a PR comment: one Mermaid
// flowchart per test case (GitHub renders it inline), a summary of what's
// failing, and an auto-generated fix-prompt the skill owner can paste into
// Claude. Styled in the house "warm" palette.
//
// Usage: node eval-mermaid.js <results.json> <out-basename> [suite] [skillDir]
//   writes <out-basename>.md            (paste into / auto-post on the PR)
//   writes <out-basename>.preview.html  (open locally to see it rendered)
const fs = require("fs");
const path = require("node:path");
const [, , inPath, outBase, suiteArg, skillDirArg] = process.argv;
if (!inPath || !outBase) { console.error("usage: node eval-mermaid.js <results.json> <out-basename> [suite] [skillDir]"); process.exit(1); }

const raw = JSON.parse(fs.readFileSync(inPath, "utf8"));
const rows = raw.results?.results || raw.results || [];
const suite = suiteArg || path.basename(path.dirname(inPath));
const skillDir = skillDirArg || `skills/**/${suite}`;
const suiteName = raw.config?.description || suite;

const WRITE = /^(create|update|toggle|delete|start|stop|archive)/;
const cls = (t) => /ask-question/.test(t) ? "ask" : WRITE.test(t) ? "write" : "read";
const clean = (s, n = 64) => String(s ?? "").replace(/\s+/g, " ").replace(/["\[\](){}|]/g, "").trim().slice(0, n);
// Prose (the request, the pass/fail label) renders sans-serif; tool nodes stay
// in the diagram's global monospace font. GitHub may drop the inline span (its
// mermaid sanitizes HTML), in which case prose falls back to monospace — tools,
// the thing that MUST be monospace, are correct either way.
const SANS = "Segoe UI, system-ui, -apple-system, sans-serif";
const sans = (s) => `<span style='font-family: ${SANS}'>${s}</span>`;
// Break long text into lines at word boundaries so nothing is clipped (GitHub
// mermaid honors <br/>), instead of relying on auto-wrap.
const wrapText = (s, width = 46) => {
  const out = [];
  let line = "";
  for (const w of String(s).split(" ")) {
    if ((line + " " + w).trim().length > width) { if (line) out.push(line); line = w; }
    else line = line ? line + " " + w : w;
  }
  if (line) out.push(line);
  return out.join("<br/>");
};

// Dark slate + violet + emerald palette (matches alohaninja's PR diagrams)
const INIT = "%%{init: {'theme':'base','themeVariables':{'background':'#0f172a','primaryColor':'#1e293b','primaryBorderColor':'#8b5cf6','primaryTextColor':'#e2e8f0','lineColor':'#64748b','fontFamily':'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace','fontSize':'13px'},'flowchart':{'htmlLabels':true}}}%%";
const CLASSDEFS = [
  "classDef start fill:#1e293b,stroke:#8b5cf6,color:#c4b5fd;",   // violet — the input
  "classDef read fill:#1e293b,stroke:#475569,color:#94a3b8;",   // muted slate — read/inspect
  "classDef ask fill:#1e293b,stroke:#3b82f6,color:#93c5fd;",    // blue — ask the user
  "classDef write fill:#1e293b,stroke:#fb7185,color:#fda4af;",  // rose — a write it shouldn't make
  "classDef passEnd fill:#064e3b,stroke:#10b981,color:#6ee7b7;",// emerald — path passed
  "classDef failEnd fill:#1e293b,stroke:#f43f5e,color:#fda4af;",// rose — path failed
];

// short remedy hints per known assertion metric (fallback = the grader reason)
const HINTS = {
  no_writes: "The skill calls write tools (create-/update-/toggle-). Make it advisory / handoff-only: never write, emit the handoff and stop.",
  mismatch_caught: "The skill isn't catching a metric/outcome mismatch. Verify the primary metric matches the predicted outcome before composing.",
  nonreal_handled: "The skill builds for non-real / self-test input. Gate junk / self-test inputs up front and confirm intent before building.",
  resolution_quality: "Improve how the skill surfaces and confirms an existing resource before proposing a new one.",
  coaches_missing_element: "The skill should ask for the missing high-value element before proceeding.",
};

const comps = (t) => (t.gradingResult?.componentResults || [])
  .filter((c) => (c.assertion?.weight ?? 1) !== 0 && c.assertion?.type !== "latency");

function mermaid(t) {
  const traj = t.response?.output?.trajectory || [];
  // Who kicks off the path: `initiator: user | llm` per test (default user).
  const initiator = String(t.testCase?.vars?.initiator || "user").toLowerCase();
  const startLabel = initiator === "llm" || initiator === "agent" ? "🤖 AGENT REQUEST" : "🧑 USER REQUEST";
  // Full text — no truncation; wrapping is handled by the mermaid init config.
  const scenario = wrapText(clean(t.testCase?.vars?.user_request || "(no input)", 400));
  const failed = comps(t).filter((c) => !c.pass);
  // start + end are prose → sans-serif; tool nodes stay in the global monospace.
  const nodes = [`s(["${sans(startLabel + "<br/>" + scenario)}"]):::start`];
  traj.forEach((step, i) => nodes.push(`n${i}["${clean(step.tool + (step.arguments?.query ? " · " + step.arguments.query : ""), 200)}"]:::${cls(step.tool)}`));
  const endTxt = t.success ? "✅ passed" : `❌ failed · ${failed.length} check${failed.length === 1 ? "" : "s"}`;
  nodes.push(`e(["${sans(endTxt)}"]):::${t.success ? "passEnd" : "failEnd"}`);
  const ids = ["s", ...traj.map((_, i) => "n" + i), "e"];
  // Left-to-right (keeps the PR from scrolling vertically on long paths).
  return `${INIT}\nflowchart LR\n  ${nodes.join("\n  ")}\n  ${ids.join(" --> ")}\n  ${CLASSDEFS.join("\n  ")}`;
}

// ---- assemble PR comment markdown ----
const passed = rows.filter((r) => r.success).length;
let md = `<!-- eval-golden-paths -->\n## 🧪 Eval golden paths — \`${suite}\`\n\n`;
md += `**${passed}/${rows.length} paths passing.** Each diagram is one flow the eval runs against the skill — `;
md += `red = a write the skill shouldn't make, green endpoint = the path passed.\n\n`;

for (const t of rows) {
  const desc = clean(t.testCase?.description || "", 90);
  const failed = comps(t).filter((c) => !c.pass);
  md += `### ${t.success ? "✅" : "❌"} ${desc}\n\n\`\`\`mermaid\n${mermaid(t)}\n\`\`\`\n`;
  if (failed.length) {
    md += `\n_Failing checks:_ ` + failed.map((c) => `**${c.assertion?.metric}** — ${clean(c.reason, 120)}`).join(" · ") + `\n`;
  }
  md += `\n`;
}

// ---- failure summary + auto fix-prompt ----
const allFailing = [];
for (const t of rows) for (const c of comps(t)) if (!c.pass) allFailing.push({ case: t.testCase?.description || "", metric: c.assertion?.metric || c.assertion?.type, reason: c.reason || "" });

if (allFailing.length) {
  const metrics = [...new Set(allFailing.map((f) => f.metric))];
  md += `<details>\n<summary>🔧 Fix prompt — paste into Claude to address the failures</summary>\n\n\`\`\`\n`;
  md += `You're editing the LaunchDarkly agent skill at ${skillDir}/SKILL.md.\n`;
  md += `An eval (${suite}) flagged these checks as failing. Update the SKILL.md so each\n`;
  md += `passes, keeping the existing structure and voice and making changes minimal:\n\n`;
  metrics.forEach((m, i) => { md += `${i + 1}. ${m}: ${HINTS[m] || "see the failing cases below."}\n`; });
  md += `\nFailing cases and the grader's reason:\n`;
  allFailing.forEach((f) => { md += `- [${clean(f.case, 60)}] ${f.metric}: ${clean(f.reason, 140)}\n`; });
  md += `\nAfter editing, re-run to confirm:\n  cd evals && npm run eval:${suite}\n`;
  md += `\`\`\`\n</details>\n`;
}

fs.writeFileSync(outBase + ".md", md);

// ---- local preview (renders the same Mermaid via CDN) ----
const previewBlocks = rows.map((t) => {
  const desc = (t.testCase?.description || "").replace(/[&<>]/g, "");
  return `<h3>${t.success ? "✅" : "❌"} ${desc}</h3><pre class="mermaid">\n${mermaid(t)}\n</pre>`;
}).join("\n");
const html = `<!doctype html><meta charset="utf-8"><title>Eval golden paths — ${suite}</title>
<style>body{font:14px Segoe UI,system-ui,-apple-system,sans-serif;max-width:1000px;margin:32px auto;padding:0 20px;color:#e2e8f0;background:#0f172a}h1{font-size:22px}h3{margin-top:28px;color:#c4b5fd}</style>
<h1>🧪 Eval golden paths — ${suite}</h1><p>${passed}/${rows.length} paths passing · this is exactly what the Mermaid renders in the PR.</p>
${previewBlocks}
<script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";mermaid.initialize({startOnLoad:true,securityLevel:"loose"});</script>`;
fs.writeFileSync(outBase + ".preview.html", html);
console.log("wrote", outBase + ".md", "and", outBase + ".preview.html", "(" + rows.length + " cases," , allFailing.length, "failing checks)");
