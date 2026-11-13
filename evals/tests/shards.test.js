const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const shards = require("../scripts/shards");
const { selectSuites } = require("../scripts/aggregate");
const { SUITES } = require("../scripts/_manifest");

const t = (description, max_turns) => ({ description, vars: max_turns === undefined ? {} : { max_turns } });

test("parseEntry and parseShard read suite#i and i/n", () => {
  assert.deepEqual(shards.parseEntry("release-autopilot-onboarding#2"), { suite: "release-autopilot-onboarding", index: 2 });
  assert.deepEqual(shards.parseEntry("configs-create"), { suite: "configs-create", index: null });
  assert.deepEqual(shards.parseShard("2/3"), { index: 2, count: 3 });
  for (const bad of ["0/3", "4/3", "1/0", "2", "a/b"]) assert.throws(() => shards.parseShard(bad), /invalid shard/);
});

test("expandMatrix replaces each sharded suite with its shard entries", () => {
  const suites = [{ suite: "a" }, { suite: "b", shards: 3 }, { suite: "c", shards: 1 }];
  assert.deepEqual(shards.expandMatrix(["a", "b", "c"], suites), ["a", "b#1", "b#2", "b#3", "c"]);
  assert.deepEqual(shards.expandMatrix([], suites), []);
});

test("shards split every test exactly once, balanced by max_turns, the same way each time", () => {
  const tests = [t("a", 30), t("b", 10), t("c", 25), t("d"), t("e", 15), t("f", 22), t("g", 12)];
  const parts = [1, 2, 3].map((i) => shards.selectTests(tests, { index: i, count: 3 }).map((x) => x.description));
  assert.deepEqual(parts.flat().sort(), tests.map((x) => x.description).sort());
  const loads = parts.map((p) => p.reduce((sum, d) => sum + (tests.find((x) => x.description === d).vars.max_turns || 20), 0));
  assert.ok(Math.max(...loads) - Math.min(...loads) <= 12, `loads ${loads}`);
  // Shards keep the suite's order, and the split does not change between calls.
  assert.deepEqual(parts, [1, 2, 3].map((i) => shards.selectTests(tests, { index: i, count: 3 }).map((x) => x.description)));
  for (const p of parts) assert.deepEqual(p, [...p].sort((x, y) => tests.findIndex((z) => z.description === x) - tests.findIndex((z) => z.description === y)));
  assert.equal(shards.selectTests(tests, null).length, tests.length);
  assert.equal(shards.selectTests(tests, { index: 1, count: 1 }).length, tests.length);
});

test("the onboarding suite's shards cover all its tests with unique descriptions", () => {
  const all = shards.loadTests(path.join(__dirname, "..", "release-autopilot-onboarding", "promptfooconfig.yaml"));
  const n = SUITES.find((s) => s.suite === "release-autopilot-onboarding").shards;
  assert.ok(n > 1);
  const seen = [];
  for (let i = 1; i <= n; i++) {
    const part = shards.selectTests(all, { index: i, count: n });
    assert.ok(part.length > 0);
    const re = new RegExp(shards.filterPattern(part, all));
    // The pattern matches this shard's tests and no other test.
    assert.deepEqual(all.filter((x) => re.test(x.description)), part);
    seen.push(...part);
  }
  assert.equal(seen.length, all.length);
});

test("filterPattern escapes descriptions and rejects missing or duplicate ones", () => {
  const all = [t('Fresh (a): "Looks good" [x]?'), t("b.c")];
  const re = new RegExp(shards.filterPattern([all[0]], all));
  assert.equal(re.test(all[0].description), true);
  assert.equal(re.test("bxc"), false);
  assert.equal(new RegExp(shards.filterPattern([all[1]], all)).test("bxc"), false);
  assert.throws(() => shards.filterPattern([], [t("x"), t("x")]), /duplicate/);
  assert.throws(() => shards.filterPattern([], [{}]), /description/);
});

test("readSuiteResults merges every shard, and reports a missing shard", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "shards-"));
  const write = (name, rows) => fs.writeFileSync(path.join(dir, name), JSON.stringify({ evalId: name, results: { results: rows } }));
  try {
    assert.match(shards.readSuiteResults(dir).error, /results\.json not found/);
    write("results.json", [{ description: "whole", success: true }]);
    assert.deepEqual(shards.readSuiteResults(dir).results.results.results.map((r) => r.description), ["whole"]);
    write("results.shard-2-of-3.json", [{ description: "b", success: false }]);
    write("results.shard-1-of-3.json", [{ description: "a", success: true }]);
    assert.match(shards.readSuiteResults(dir).error, /missing results for shard 3\/3/);
    write("results.shard-3-of-3.json", []);
    const merged = shards.readSuiteResults(dir).results;
    assert.deepEqual(merged.results.results.map((r) => r.description), ["a", "b"]);
    write("results.shard-1-of-2.json", []);
    assert.match(shards.readSuiteResults(dir).error, /different shard counts/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("selectSuites reads suite#i against the manifest and applies --shard to the rest", () => {
  const onboarding = "release-autopilot-onboarding";
  const n = SUITES.find((s) => s.suite === onboarding).shards;
  const picked = selectSuites([`${onboarding}#2`, "configs-create"]);
  assert.deepEqual(picked.map((p) => [p.suite.suite, p.shard]), [["configs-create", null], [onboarding, { index: 2, count: n }]]);
  assert.deepEqual(selectSuites(["configs-create"], { index: 1, count: 2 })[0].shard, { index: 1, count: 2 });
  assert.equal(selectSuites([onboarding])[0].shard, null);
});
