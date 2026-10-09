# Repairing this repo's profile

The check had no profile for this repo, so it derived one from the code at
{HEAD} ({PROFILE}): the LaunchDarkly SDKs, the repo's flag-key declarations
and wrappers, and Code References aliases if the repo has them. Before using
it, the check tested it on the files this change touches, and it doesn't
read them right:

{FINDINGS}

({LD}.)

- **GAP**: a flag key written in a changed file where the profile found no
  flag check near it. Usually the repo evaluates flags through its own
  helper the derivation didn't recognize (a hook, a wrapper method, a
  config struct). Sometimes the key is only mentioned (a log line, a test
  name, a comment): then it's not a gap, and nothing needs adding.
- **SUSPECT**: a line the profile reads as a flag check, for a key
  LaunchDarkly has no flag for. Usually a pattern matches code that isn't a
  flag check (a function with the same name, a string table). Sometimes the
  flag lives in another LaunchDarkly project: then leave it.

## What to do

Read each listed line in the checkout ({CHECKOUT}, at {HEAD}) and enough
around it to see how the value is used. Grep for the helper's definition when
you need to. Don't read or search beyond what settling these lines needs.

Then write `{RUN}/profile_fix.json`:

```json
{
  "additions": {
    "keyed_calls": [{"name": "useFeature", "arg": 0}],
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
  ([PROFILE.md](PROFILE.md)): a `keyed_calls` entry is a function or method
  whose argument `arg` is the flag key; an `extra_patterns` regex captures
  the key (group 1) on a flag-check line; `exclude_symbols` / `exclude_files`
  stop matches that aren't flag checks. Add only what the listed lines need,
  and keep each addition as narrow as reading them shows it should be.
- `examples`: every listed line you fixed, with its text copied exactly.
  `covers` is `gap` (it should now read as a flag check) or `suspect` (it
  should no longer).
- `not_a_problem`: listed lines that need no change, and why.

Then run `ld-factory.pyz profile {RUN}`. It checks each example against the commit and
re-reads the changed files with your additions. It saves the additions for
this repo only if every gap example now has a flag check and every suspect
example none; otherwise it says which line failed, once. Saved additions are
applied on top of the derived profile on every later run, so keep them to
what this repo's code needs. Then run the same `start` command again.
