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

const PASS = "\x1b[32mPASS\x1b[0m";
const FAIL = "\x1b[31mFAIL\x1b[0m";
const SEP = "─".repeat(72);

console.log("\n" + SEP);
console.log("EVAL RESULTS — full LLM output");
console.log(SEP);

results.forEach((r, i) => {
  const description = r.description ?? r.vars?.user_message?.slice(0, 60) ?? `Test ${i + 1}`;
  const status = r.success ? PASS : FAIL;
  const failedAssertions = (r.gradingResult?.componentResults ?? [])
    .filter((c) => !c.pass)
    .map((c) => c.assertion?.metric ?? c.assertion?.type ?? "?");

  console.log(`\n=== TEST ${i + 1}: ${description} ===`);
  if (r.vars?.user_message) {
    console.log(`INPUT:  ${r.vars.user_message}`);
  }
  console.log(`STATUS: ${status}`);
  if (failedAssertions.length > 0) {
    console.log(`FAILED: ${failedAssertions.join(", ")}`);
  }
  console.log("OUTPUT:");
  console.log(r.response?.output ?? "(no output)");
  console.log(SEP);
});

const total = results.length;
const passed = results.filter((r) => r.success).length;
console.log(`\nSummary: ${passed}/${total} passed\n`);
