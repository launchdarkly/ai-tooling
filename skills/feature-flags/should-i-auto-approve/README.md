# should-i-auto-approve

Rates a committed code change's review risk as **low** (can merge on an
automated approval), **medium** or **high** (needs a person). A fixed decision
graph asks narrow yes/no questions about the change: the changed paths answer
some, the agent answers the rest by written procedures from the code, and the
graph turns the answers into the rating. The same answers always give the same
rating.

- **Advisory and read-only.** It never approves, comments on or changes a pull
  request, never changes a flag, and never edits the repository it checks.
- **Needs** a git checkout with the change committed and its merge base,
  `python3` (3.10+, standard library only) and `git`.
- **Output:** a short report ending in a `should-i-auto-approve` JSON block (`rating`,
  `terminal`, `steps`, `values`, `graph`).
- **Shadow mode:** told to run in shadow mode, the agent prints the report and
  does nothing else with it.

## Command line

`should-i-auto-approve.pyz` is the whole program in one file (a Python zip application: the walk,
the graph and its questions). `start`, `flag`, `answer`, `decide`;
`python3 should-i-auto-approve.pyz --help` lists them. SKILL.md gives the order, and
[references/QUESTIONS.md](references/QUESTIONS.md) every question.

## Settings

| Variable | Default | What it sets |
|---|---|---|
| `LAUNCHDARKLY_API_KEY` | unset | Read flag state directly; without it the agent reads flags with its own LaunchDarkly tools. |
| `LAUNCHDARKLY_BASE_URI` | `https://app.launchdarkly.com` | The LaunchDarkly instance. |
| `LAUNCHDARKLY_PROJECT` | `default` | The project whose flags the change may name. |
| `SHOULD_I_AUTO_APPROVE_RUNS` | `~/.cache/should-i-auto-approve/` | Where run folders go. |

Built from the risk graph at version 0.6 (graph `e0f1846b4950`).
