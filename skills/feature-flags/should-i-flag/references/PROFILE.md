# Writing a profile for a repo

The check finds flag evaluations mechanically, so it needs to know what a
flag check looks like in this repo: which calls evaluate a flag, where keys
come from, which files ship, and which LaunchDarkly project and environments
the flags live in. That's the repo's **profile**. You don't normally write
one: for a repo without one, `ld-factory.pyz start` derives it from the code and
checks it against the change, and asks for a repair only when the check
fails ([PROFILE_REPAIR.md](PROFILE_REPAIR.md)). This page is the format, for
that repair and for a developer who wants to write a profile by hand.

The profile is data, not judgment. Write only what you find in the repo, and
check it before relying on it: a pattern that matches nothing makes every
flag in the repo invisible, and the check would read every change as
unflagged without any error.

## Where it goes

A profile written by hand goes at
`~/.cache/should-i-flag/profiles/<org>__<repo>.json`, keyed by the
repo's `origin`. It's picked up from there on every later run. Never write
it into the repo being checked.

## Steps

1. **Find how the code evaluates flags.** Search the repo (`git grep`) for
   the LaunchDarkly SDK and what wraps it:
   - SDK packages: `launchdarkly-node-server-sdk`, `@launchdarkly/node-server-sdk`,
     `launchdarkly-js-client-sdk`, `@launchdarkly/js-client-sdk`,
     `launchdarkly-react-client-sdk`, `github.com/launchdarkly/go-server-sdk`,
     `ldclient` (Python), `com.launchdarkly.sdk` (Java/Kotlin),
     `LaunchDarkly.Sdk` (.NET), `launchdarkly-server-sdk` (Ruby),
     `LaunchDarkly` (Swift).
   - Evaluation calls: `variation`, `boolVariation`, `stringVariation`,
     `numberVariation`, `jsonVariation`, `variationDetail`, Go's
     `BoolVariation` / `StringVariation` / `IntVariation` / `JSONVariation`
     (and `...Ctx`), React's `useFlags()` / `useBoolVariation`.
   - **Wrappers** the code calls instead: `isEnabled('key')`,
     `featureFlags.get('key')`, a `flags.ts` of named constants. Most repos
     have one; when they do, the wrapper is what to describe, and the SDK
     calls inside it go in `exclude_files`.
2. **Write the profile** (below), using the shapes you found.
3. **Check it:**
   `ld-factory.pyz check-profile <REPO_PATH>`.
   Every declaration and pattern should report `ok` with hits in real code.
   Fix anything that matches nothing, or matches only docs and tests.
4. Run `ld-factory.pyz start` again.

## The profile

```json
{
  "name": "acme-web",
  "repo": "acme/web",
  "flag_declarations": [
    {
      "id": "sdk-literal-keys",
      "files": ["*.ts", "*.tsx", "*.js", "*.jsx", ":!**/node_modules/**"],
      "pattern": "\\b(?:variation|boolVariation|stringVariation|numberVariation|jsonVariation|variationDetail)\\(\\s*['\"]([A-Za-z0-9][A-Za-z0-9._-]*)['\"]",
      "key_group": 1,
      "expect_at_least": 1
    }
  ],
  "evaluation": {
    "symbol_call": false,
    "keyed_calls": [
      {"pattern": "\\b\\w+\\.(?:variation|boolVariation|stringVariation|numberVariation|jsonVariation|variationDetail)\\(", "key_arg": 0}
    ],
    "search_exclude": ["**/*.md", "docs/**", "**/node_modules/**", "**/vendor/**"],
    "exclude_files": []
  },
  "roles_that_ship": ["ships", "generated"],
  "path_roles": {
    "test": ["**/*.test.*", "**/*.spec.*", "**/__tests__/**", "**/*_test.go", "**/test/**", "**/tests/**"],
    "docs": ["**/*.md", "docs/**"],
    "build_ci": [".github/**", "**/Dockerfile", "**/*.lock", "**/package-lock.json", "**/yarn.lock", "**/go.sum"],
    "generated": ["**/generated/**", "**/*.generated.*"],
    "ships_anyway": []
  },
  "codeowners": ".github/CODEOWNERS",
  "launchdarkly": {
    "project": "default",
    "decision_environments": ["production", "test"],
    "user_facing_production": ["production"],
    "non_user_audiences": ["internal", "staff", "qa"]
  }
}
```

What each part is for:

- **`flag_declarations`**: where flag keys come from, so the check knows
  which flags existed before the change (for reuse) and which the change
  adds or removes.
  - **Keys written as literals at the call** (most SDK code): use `files`
    (git pathspecs) and a `pattern` whose `key_group` captures the key. A key
    then counts as existing at a commit when code there evaluates it.
  - **A declarations file** (`export const newCheckout = 'new-checkout'`,
    a Go `const FlagX = "x"` block): use `file` instead of `files`, with
    `symbol_group` for the constant's name and `key_group` for the key, and
    describe the calls that use the constant in `evaluation` below.
- **`evaluation`**: what a flag check looks like at a call site.
  - `keyed_calls`: a call that takes the key as an argument. `pattern` ends
    at the opening `(`; `key_arg` is the argument's 0-based position (the
    Node and Go server SDKs take the key first: 0). The argument may be a
    literal, or a name bound to a literal in the same file.
  - `extra_patterns`: a call through a named constant, group 1 capturing
    the constant (`flags\.([A-Za-z0-9_]+)`). Kept even when the key isn't
    known.
  - `resolved_patterns`: the same, kept only when group 1 resolves to a
    declared flag.
  - `exclude_files`: the wrapper's own file(s), so its internal SDK calls
    aren't read as the gate for every flag. `search_exclude`: globs to ignore.
- **`path_roles`**: which changed files ship. First match wins, in the order
  `ships_anyway`, `test`, `docs`, `build_ci`, `generated`; anything else
  ships. Put migrations, SQL, and prompt or skill files that run in
  production in `ships_anyway`.
- **`codeowners`**: the CODEOWNERS path (`CODEOWNERS`, `.github/CODEOWNERS`
  or `docs/CODEOWNERS`), if there is one.
- **`launchdarkly`**: the project the repo's flags live in (look for
  `.launchdarkly/coderefs.yaml`'s `projKey`, the SDK key's environment, or
  ask your LaunchDarkly tools which project has the keys you found);
  `decision_environments`, every environment key to read;
  `user_facing_production`, the environments real users are served from
  (LaunchDarkly marks these **critical**; with none marked, use the
  production ones); `non_user_audiences`, words in segment keys that mean
  "not real users". Add `base_url` only for a LaunchDarkly instance other
  than `https://app.launchdarkly.com`.

## Limits

- **React `useFlags()`** reads flags as camel-cased properties
  (`flags.newCheckout`), which a pattern can't map back to a key. Describe
  `useBoolVariation('key')`-style calls if the code has them, and say in
  your summary that `useFlags` checks weren't recognized.
- Deeper analysis (enclosing conditionals, callers in other files) works
  best for TypeScript/JavaScript, Go and Python.
