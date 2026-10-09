# should-i-flag

Decides whether a committed code change should ship behind a LaunchDarkly
feature flag. A fixed decision tree asks narrow questions about the change;
the skill answers what it can from git and LaunchDarkly, the agent answers the
rest by written procedures from evidence the skill gathers, and every answer's
citations are checked against the code. The same answers always give the same
result.

- **Advisory and read-only.** It never creates or changes flags or edits the
  repository it checks.
- **Needs** a git checkout with the change committed, `python3` (3.10+,
  standard library only) and `git`. LaunchDarkly flag state is read with
  `LAUNCHDARKLY_API_KEY` or the agent's LaunchDarkly tools, and the skill works
  without either.
- **Falls back** to `should-flag-change` when it can't run.
- **Output:** a plain-English report ending in a `recommend-flag` JSON block,
  the same shape `should-flag-change` produces.

## Command line

`ld-factory.pyz` is the whole program in one file (a Python zip application: the
engine, the decision tree and its data). It runs every step (`start`, `gates`,
`risks`, `readers`, `next`, `answer`, `decide`, `check-profile`);
`ld-factory.pyz --help` lists them. Put it on `PATH` (for example
`ln -s "$PWD/ld-factory.pyz" /usr/local/bin/ld-factory.pyz`) or call it by path.
SKILL.md describes the order.

## Settings

| Variable | Default | What it sets |
|---|---|---|
| `LAUNCHDARKLY_API_KEY` | unset | Read flag state directly; without it the agent fetches flags with its own tools. |
| `SHOULD_I_FLAG_PROFILES` | unset | Folders (separated like `PATH`) of repo profiles, `<name>.json`, each naming its `repo` and optionally a `launchdarkly` section (instance, project, environments). |
| `SHOULD_I_FLAG_RUNS` | `~/.cache/should-i-flag/` | Where run folders go. |

A repo without a profile gets one derived from its code on each run, checked
against the change, and repaired by the agent only when that check fails
([references/PROFILE_REPAIR.md](references/PROFILE_REPAIR.md)). The repair's
additions are saved under `~/.cache/should-i-flag/profiles/` and applied on
top of the derived profile on later runs; any that no longer match the code
are left out.
