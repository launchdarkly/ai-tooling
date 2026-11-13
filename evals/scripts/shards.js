#!/usr/bin/env node
/**
 * Shard selection for eval suites.
 *
 * Shards. A suite with `shards: N` in _manifest.js runs as N CI matrix jobs,
 * "<suite>#1" to "<suite>#N". Each job runs only its share of the tests. The
 * split is deterministic: tests go, heaviest first (vars.max_turns, default
 * 20), to the shard with the lowest total so far, so each shard gets about
 * the same number of agent turns. Each shard writes
 * results.shard-<i>-of-<N>.json, and aggregate.js merges them into one score.
 *
 * CLI (used by the workflow):
 *   node scripts/shards.js matrix '<JSON array of suite slugs>'
 *     prints the JSON array of matrix entries, with each sharded suite
 *     replaced by "<suite>#1" ... "<suite>#N".
 */

const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_WEIGHT = 20;

/** "suite#2" -> { suite, index: 2 }; "suite" -> { suite, index: null }. */
function parseEntry(entry) {
  const m = String(entry).match(/^([^#]+)#(\d+)$/);
  return m ? { suite: m[1], index: Number(m[2]) } : { suite: String(entry), index: null };
}

/** "2/3" -> { index: 2, count: 3 }. Throws on anything else. */
function parseShard(value) {
  const m = String(value).match(/^(\d+)\/(\d+)$/);
  const index = m && Number(m[1]);
  const count = m && Number(m[2]);
  if (!m || count < 1 || index < 1 || index > count) {
    throw new Error(`invalid shard "${value}": use i/n with 1 <= i <= n`);
  }
  return { index, count };
}

/** Expands each sharded suite slug into its "<suite>#i" entries. */
function expandMatrix(slugs, suites) {
  const out = [];
  for (const slug of slugs) {
    const s = suites.find((x) => x.suite === slug);
    const n = (s && s.shards) || 1;
    if (n > 1) for (let i = 1; i <= n; i++) out.push(`${slug}#${i}`);
    else out.push(slug);
  }
  return out;
}

const weightOf = (t) => Number((t && t.vars && t.vars.max_turns) || DEFAULT_WEIGHT);

/**
 * Indices (into `tests`) that shard `index` of `count` runs. Heaviest test
 * first to the lightest shard; ties go to the earlier test and the lower
 * shard, so the split depends only on the tests.
 */
function shardIndices(tests, index, count) {
  const order = tests.map((t, i) => i).sort((a, b) => weightOf(tests[b]) - weightOf(tests[a]) || a - b);
  const loads = new Array(count).fill(0);
  const owner = new Array(tests.length);
  for (const i of order) {
    let best = 0;
    for (let s = 1; s < count; s++) if (loads[s] < loads[best]) best = s;
    owner[i] = best;
    loads[best] += weightOf(tests[i]);
  }
  return tests.map((t, i) => i).filter((i) => owner[i] === index - 1);
}

/** The tests shard ({ index, count }) runs; every test without a shard. */
function selectTests(tests, shard = null) {
  if (!shard || shard.count <= 1) return tests.slice();
  return shardIndices(tests, shard.index, shard.count).map((i) => tests[i]);
}

const escapeRegExp = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * A promptfoo --filter-pattern that matches exactly the given tests by
 * description. Descriptions must be present and unique in the suite.
 */
function filterPattern(selected, all) {
  const seen = new Set();
  for (const t of all) {
    if (!t.description) throw new Error("every test needs a description to be selected");
    if (seen.has(t.description)) throw new Error(`duplicate test description: ${t.description}`);
    seen.add(t.description);
  }
  return `^(?:${selected.map((t) => escapeRegExp(t.description)).join("|")})$`;
}

/** Loads a suite's inline tests from its promptfooconfig.yaml. */
function loadTests(configPath) {
  const yaml = require("js-yaml");
  const config = yaml.load(fs.readFileSync(configPath, "utf-8")) || {};
  if (!Array.isArray(config.tests)) {
    throw new Error(`${configPath}: tests must be an inline list to shard`);
  }
  return config.tests;
}

const shardFile = (index, count) => `results.shard-${index}-of-${count}.json`;

/** Result files a suite directory holds, as { name, index, count }. */
function listShardFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .map((name) => ({ name, m: name.match(/^results\.shard-(\d+)-of-(\d+)\.json$/) }))
    .filter((x) => x.m)
    .map((x) => ({ name: x.name, index: Number(x.m[1]), count: Number(x.m[2]) }));
}

const resultRows = (r) => {
  const rows = (r && r.results && r.results.results) || (r && r.results) || [];
  return Array.isArray(rows) ? rows : [];
};

/** Combines shard result files into one results object. */
function mergeResults(parts) {
  const first = parts[0] || {};
  return { ...first, results: { ...(first.results || {}), results: parts.flatMap(resultRows) } };
}

/**
 * Reads the suite's results. With shard files present, every shard 1..N
 * must be there; they are merged. Otherwise results.json is read.
 * Returns { results } or { error }.
 */
function readSuiteResults(dir) {
  const shards = listShardFiles(dir);
  if (shards.length > 0) {
    const counts = [...new Set(shards.map((s) => s.count))];
    if (counts.length > 1) return { error: `shard files from different shard counts: ${shards.map((s) => s.name).join(", ")}` };
    const n = counts[0];
    const missing = [];
    for (let i = 1; i <= n; i++) if (!shards.find((s) => s.index === i)) missing.push(i);
    if (missing.length > 0) return { error: `missing results for shard ${missing.map((i) => `${i}/${n}`).join(", ")}` };
    try {
      const parts = shards.sort((a, b) => a.index - b.index).map((s) => JSON.parse(fs.readFileSync(path.join(dir, s.name), "utf-8")));
      return { results: mergeResults(parts) };
    } catch (e) {
      return { error: `failed to parse shard results: ${e.message}` };
    }
  }
  const file = path.join(dir, "results.json");
  if (!fs.existsSync(file)) return { error: "results.json not found — run with --run first" };
  try {
    return { results: JSON.parse(fs.readFileSync(file, "utf-8")) };
  } catch (e) {
    return { error: `failed to parse results.json: ${e.message}` };
  }
}

module.exports = {
  parseEntry, parseShard, expandMatrix, shardIndices, selectTests, filterPattern,
  loadTests, shardFile, listShardFiles, mergeResults, readSuiteResults,
};

if (require.main === module) {
  const [cmd, arg] = process.argv.slice(2);
  if (cmd === "matrix") {
    const { SUITES } = require("./_manifest");
    process.stdout.write(JSON.stringify(expandMatrix(JSON.parse(arg || "[]"), SUITES)) + "\n");
  } else {
    process.stderr.write("Usage: shards.js matrix '<JSON array of suite slugs>'\n");
    process.exit(2);
  }
}
