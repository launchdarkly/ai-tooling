import { readFileSync } from "fs";

const RESULTS_FILE = "/tmp/promptfoo-results.json";

let raw;
try {
  raw = readFileSync(RESULTS_FILE, "utf8");
} catch {
  console.error(`Could not read ${RESULTS_FILE} — did the eval run with --output?`);
  process.exit(1);
}

const data = JSON.parse(raw);
const results = data?.results?.results ?? [];

if (results.length === 0) {
  console.log("No test results found.");
  process.exit(0);
}

const GREEN = (s) => `\x1b[32m${s}\x1b[0m`;
const RED = (s) => `\x1b[31m${s}\x1b[0m`;
const DIM = (s) => `\x1b[2m${s}\x1b[0m`;
const SEP = "─".repeat(72);

console.log("\n" + SEP);
console.log("EVAL RESULTS — full LLM output");
console.log(SEP);

let posTotal = 0, posPassed = 0, negTotal = 0, negConfirmed = 0;

results.forEach((r, i) => {
  const description = r.testCase?.description ?? r.vars?.user_message?.slice(0, 60) ?? `Test ${i + 1}`;
  const isNeg = description.startsWith("[NEG]");
  const passed = r.success;

  // Mutation tests: grader sees a defective output and should FAIL
  // FAIL = grader correctly caught the defect (green)
  // PASS = grader missed the defect (red — rubric has a blind spot)
  let statusLabel;
  if (isNeg) {
    negTotal++;
    if (!passed) {
      negConfirmed++;
      statusLabel = GREEN("FAIL (grader correctly rejected defect)");
    } else {
      statusLabel = RED("PASS (grader missed defect — rubric blind spot)");
    }
  } else {
    posTotal++;
    if (passed) {
      posPassed++;
      statusLabel = GREEN("PASS");
    } else {
      statusLabel = RED("FAIL");
    }
  }

  const failedAssertions = (r.gradingResult?.componentResults ?? [])
    .filter((c) => !c.pass)
    .map((c) => c.assertion?.metric ?? c.assertion?.type ?? "?");

  console.log(`\n=== TEST ${i + 1}: ${description} ===`);
  if (r.vars?.user_message) {
    console.log(`INPUT:  ${r.vars.user_message}`);
  }
  console.log(`STATUS: ${statusLabel}`);
  if (!passed && failedAssertions.length > 0) {
    const label = isNeg ? "DETECTED" : "FAILED";
    console.log(`${label}: ${failedAssertions.join(", ")}`);
  }
  console.log("OUTPUT:");
  console.log(r.response?.output ?? "(no output)");
  console.log(SEP);
});

console.log(`\nPositive tests: ${posPassed}/${posTotal} passed`);
console.log(`Mutation tests: ${negConfirmed}/${negTotal} defects correctly detected`);

if (posPassed < posTotal) {
  console.error(`\n[CI] ${posTotal - posPassed} positive test(s) failed — exiting 1`);
  process.exitCode = 1;
}

// Token usage — read from top-level stats (most accurate source)
const stats = data?.results?.stats ?? {};
const tu = stats.tokenUsage ?? {};
const promptTokens = tu.prompt ?? 0;
const completionTokens = tu.completion ?? 0;
const gradingPromptTokens = tu.assertions?.prompt ?? 0;
const gradingCompletionTokens = tu.assertions?.completion ?? 0;

const totalPrompt = promptTokens + gradingPromptTokens;
const totalCompletion = completionTokens + gradingCompletionTokens;
const totalTokens = totalPrompt + totalCompletion;

// Claude 3 Haiku pricing (as of 2026): $0.25/M input, $1.25/M output
const INPUT_COST_PER_M = 0.25;
const OUTPUT_COST_PER_M = 1.25;
const inputCost = (totalPrompt / 1_000_000) * INPUT_COST_PER_M;
const outputCost = (totalCompletion / 1_000_000) * OUTPUT_COST_PER_M;
const totalCost = inputCost + outputCost;

console.log(`
Token Usage:
  Eval    — input: ${promptTokens.toLocaleString()}, output: ${completionTokens.toLocaleString()}
  Grading — input: ${gradingPromptTokens.toLocaleString()}, output: ${gradingCompletionTokens.toLocaleString()}
  Total   — input: ${totalPrompt.toLocaleString()}, output: ${totalCompletion.toLocaleString()} (${totalTokens.toLocaleString()} tokens)

Estimated cost (claude-3-haiku @ $0.25/M input, $1.25/M output):
  Input:  $${inputCost.toFixed(4)}
  Output: $${outputCost.toFixed(4)}
  Total:  $${totalCost.toFixed(4)}
`);
