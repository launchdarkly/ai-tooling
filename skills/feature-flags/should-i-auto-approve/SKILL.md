---
name: should-i-auto-approve
description: "Rates a committed code change's review risk as low, medium or high by a fixed decision graph (low can be approved without a human; medium and high need one), from checked answers to narrow questions about the change. Use only when your instructions or the user name should-i-auto-approve. Advisory and read-only: it never approves, comments on, or changes a pull request."
license: Apache-2.0
compatibility: "Advisory and read-only. Needs a git checkout with the change committed and its merge base present, a shell, git and Python 3.10+ (no packages). Reads LaunchDarkly flag state with LAUNCHDARKLY_API_KEY, or through your LaunchDarkly tools. Ends with a `should-i-auto-approve` JSON block."
metadata:
  author: launchdarkly
  version: "0.1.0"
  graph: "e0f1846b4950"
---

# Can This Change Be Approved Without a Human?

This skill rates one committed change **low**, **medium** or **high** risk.
Low is a change that can merge on an automated approval; medium and high need
a person's review. It does not rate by judgment. A fixed decision graph asks
narrow yes/no questions about the change. The changed paths answer some
mechanically, and you answer the rest, each by its written procedure, from the
code. The same answers always give the same rating.

Every command below is this skill's command line, `should-i-auto-approve.pyz`:
one file, beside this one. Run it as `python3 SKILL_DIR/should-i-auto-approve.pyz`
(`SKILL_DIR` is the directory this file is in). It needs `python3` and `git`.

**Finish in one run.** Don't stop partway to ask anyone something and wait.

## Scope

- **Advisory and read-only.** Never approve, comment on, label or change a
  pull request, never create or change a flag, and never edit, check out,
  commit or push in the repository being checked. Everything the skill writes
  goes to its run folder under `~/.cache/should-i-auto-approve/` (or
  `SHOULD_I_AUTO_APPROVE_RUNS`).
- **Committed changes only**: the branch's commits against its merge base,
  the same change a pull request shows.
- **Judge the code, not the conversation.** Don't read PR comments, reviews,
  labels, or any bot's output about the PR (another reviewer's or approval
  agent's risk rating included), and don't use `gh` for them. Read the code
  and the PR's own title and description only.

## Shadow mode

When your instructions say to run this skill in **shadow mode**, its rating
is for observation only. Run it after your own work is finished and
submitted, print its report, and do nothing else with it. Don't let it change,
delay or justify anything you did or submitted, don't submit or post anything
again because of it, and don't mention it anywhere outside your own reply.

## When it can't run

If there's no shell, `python3`, `git` or checkout of the change, or the CLI
crashes or reports a setup problem (exit 2) you can't fix by correcting what
you passed it, say so in one line and stop. Don't rate the change yourself
instead.

## Steps

### 1. Prepare

```bash
python3 SKILL_DIR/should-i-auto-approve.pyz start <REPO_PATH> [--base <REF>] [--head <REF>] \
    [--pr-title "<title>"] [--pr-body-file <file>]
```

- `REPO_PATH` defaults to the current directory, `--head` to `HEAD`, `--base`
  to the remote's default branch (`origin/HEAD`, else `origin/main`).
- **On a pull request**, pass its base and head (`--base origin/<base_ref>
  --head <head_sha>`) and its title and description (write the description to
  a file first).
- A shallow clone works when it still has the merge base. If `start` says
  there's no merge base, fetch more history (`git fetch --deepen` or
  `--unshallow`) and run it again.

It prints `RUN: <folder>` and status lines (`CHANGE`, `PR TEXT`,
`LAUNCHDARKLY`, `QUESTIONS`).

| Exit | Meaning | What you do |
|---|---|---|
| 0 | Ready | Go to step 2. |
| 4 | Nothing committed to check | Stop and say so. |
| 2 | Setup problem | Fix what you passed (a ref, a file) and run `start` again, else stop and say why. |

### 2. Answer every question

`RUN/questions.md` holds the questions left after the path answers, each with
its procedure and when it may be left unresolved. Read the change and the
code around it:

```bash
git -C <REPO_PATH> diff <merge_base>...<head>
git -C <REPO_PATH> show <head>:<path>
git -C <REPO_PATH> grep -n <pattern> <head>
```

(`RUN/case.json` has `merge_base` and `head`.)

- **Answer every question**, even when an earlier answer already decides the
  rating: the answers are kept, and re-walked when the graph changes.
- Follow each question's procedure, not your own view of the change's risk.
- Give `true`, `false`, or `"unresolved"` (only when that question's
  "Unresolved when" actually holds; say which part), with evidence: the files
  and lines or symbols that decide it, in one or two sentences.
- **Flag state.** `RUN/flags.json` lists every LaunchDarkly flag whose key
  (or its camelCased SDK name) appears in the change or the ten lines around
  each hunk, with its state now in each critical environment: `on`, the off
  and fallthrough variations, and counts of rules and targets. An environment
  whose key has `prod` serves real users. It is a key match, not a gate
  analysis. Check in the code that a listed flag really withholds the changed
  behavior, and look for a flag check the file missed (a wrapper, a constant, a
  flag passed in from a caller, a route gated elsewhere). Read such a flag's
  state with `python3 SKILL_DIR/should-i-auto-approve.pyz flag RUN <flag-key>`.
  When `start` printed `LAUNCHDARKLY: not read`, or `flag` exits 9, read the
  flags with your LaunchDarkly tools instead. If you can't read flag state at
  all, a question that depends on it is unresolved.

Then record the answers, all in one JSON object on stdin:

```bash
python3 SKILL_DIR/should-i-auto-approve.pyz answer RUN <<'JSON'
{
  "answers": {
    "<question id>": {"value": true, "evidence": "..."}
  },
  "behavior_hunks": ["path:symbol", "..."],
  "flag_keys": ["feature flag keys that gate any changed code"]
}
JSON
```

| Exit | Meaning | What you do |
|---|---|---|
| 0 | Recorded | Go to step 3. |
| 7 | Missing or invalid answers (listed) | Fix them and send the whole object again. |

### 3. Decide

```bash
python3 SKILL_DIR/should-i-auto-approve.pyz decide RUN
```

Run it as is, with its whole output: don't pipe it through `grep`, `sed`,
`head` or `tail`. It prints `RESULT` (low, medium, high, or "a person needs to
decide"), `WHY`, the `DECIDING QUESTION` with the evidence that settled it,
`UNCLEAR, BUT IT DIDN'T MATTER` when present, and a fenced block:

````
```json should-i-auto-approve
{"rating": "low", "escalated": false, "terminal": "...", "graph": "...", ...}
```
````

| Exit | Meaning | What you do |
|---|---|---|
| 0 | Decided | Go to step 4. |
| 2 | No answers recorded yet | Go back to step 2. |

### 4. Report

Print, in a few short lines, using only what `decide` printed:

1. The rating and `WHY`, close to verbatim, and a sentence on what in the
   change led there, in terms of its code.
2. `UNCLEAR, BUT IT DIDN'T MATTER`, if present.
3. Anything from step 1 to act on: LaunchDarkly state that couldn't be read.

Then copy the `should-i-auto-approve` block **verbatim** as the last thing in
your output. Never edit its fields.

## Talking to people

Readers don't know how the check works inside. Don't use its internal words:
predicate, node, walk, graph, terminal, outcome codes (T-LO-2, E-UNIT), hunk,
merge_base. Say "the check", "the change", "the code it changes", "a person
needs to decide". Refer to questions by what they ask.

## What not to do

- Don't approve, comment on, or change the pull request, or any flag.
- Don't answer from your own view of the change's risk. Follow each procedure.
- Don't read reviews, comments or other bots' ratings of the PR.
- Don't change the `should-i-auto-approve` block.
