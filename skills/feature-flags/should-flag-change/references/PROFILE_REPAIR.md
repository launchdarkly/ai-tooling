# Repairing this repo's profile (optional)

The check had no profile for this repo, so it derived one from the code at
{HEAD} ({PROFILE}): the LaunchDarkly SDKs, the repo's flag-key declarations
and wrappers, and Code References aliases if the repo has them. It tested it
on the files this change touches, and it doesn't account for these lines:

{FINDINGS}

({LD}.)

**This repair is optional; the run doesn't wait for it.** `start` already
exited 0 with these lines as leads: the evidence notes them, and the gate
search follows the GAP lines and reports any that gate the change. Repair
only when it's worth it: the leads are many, or keep naming the same helper,
so a pattern would read them (on this run and later ones) better than
following each by hand. Otherwise skip this page and go on with `ld-factory.pyz next
{RUN}`.

- **GAP**: a flag key written in a changed file where the profile found no
  flag check near it. It may be a check through the repo's own helper the
  derivation didn't recognize (a hook, a wrapper method, a middleware, a
  config struct), or only a mention (a log field, a config or member field,
  a scope string, a test value, a comment): then it's not a gap, and nothing
  needs adding.
- **SUSPECT**: a line the profile reads as a flag check, for a key
  LaunchDarkly has no flag for. Usually a pattern matches code that isn't a
  flag check (a function with the same name, a string table). Sometimes the
  flag lives in another LaunchDarkly project: then leave it.

## What to do

If you repair: read each listed line in the checkout ({CHECKOUT}, at {HEAD}) and enough
around it to see how the value is used. Grep for the helper's definition when
you need to. Don't read or search beyond what settling these lines needs.

Then write `{RUN}/profile_fix.json`:

```json
{
  "additions": {
    "keyed_calls": [{"pattern": "\\buseFeature\\(", "key_arg": 0}],
    "extra_patterns": ["\\bisEnabled\\(\\s*['\"]([a-z0-9-]+)['\"]"],
    "resolved_patterns": [],
    "exclude_symbols": ["FlagTargetingTable"],
    "exclude_files": []
  },
  "examples": [
    {"path": "src/app/Banner.tsx", "line": 42, "text": "const show = useFeature('new-banner')", "covers": "gap"},
    {"path": "src/admin/FlagTable.tsx", "line": 17, "text": "<FlagTargetingTable flag={flagKey} />", "covers": "suspect"}
  ],
  "not_a_problem": [
    {"path": "src/log.ts", "line": 9, "why": "the key appears in a log message; nothing is evaluated"}
  ]
}
```

- `additions` uses the same fields as a profile's `evaluation` section
  ([PROFILE.md](PROFILE.md)): a `keyed_calls` entry is a call that takes the
  key as an argument, its `pattern` a regex ending at the call's opening `(`
  and `key_arg` the key's 0-based argument position; an `extra_patterns`
  regex captures the key (group 1) on a flag-check line; `exclude_symbols` / `exclude_files`
  stop matches that aren't flag checks. Add only what the listed lines need,
  and keep each addition as narrow as reading them shows it should be.
- `examples`: every listed line you fixed, with its text copied exactly.
  `covers` is `gap` (it should now read as a flag check) or `suspect` (it
  should no longer).
- `not_a_problem`: listed lines that need no change, and why.

Then run `ld-factory.pyz profile {RUN}`. It checks each example against the commit and
re-reads the changed files with your additions. It saves the additions for
this repo only if every gap example now has a flag check and every suspect
example none; otherwise it says which line failed, once, and you may fix it
once. Saved additions are applied on top of the derived profile on every later
run, so keep them to what this repo's code needs. When it's saved, run the
same `start` command again, so this run reads the change with it. When it
doesn't hold, or you stop, go on with the run as `start` left it.

A saved repair stays on this machine. To make it apply everywhere the check
runs (CI, another developer's machine), the repo's developers can commit its
`additions` to `.launchdarkly/should-i-flag.json` ([PROFILE.md](PROFILE.md)).
Say so in your summary when you repaired the profile; don't write that file
yourself.
