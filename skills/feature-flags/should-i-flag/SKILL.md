---
name: should-i-flag
description: "Decide whether a given code change should be placed behind a LaunchDarkly feature flag. Use when a developer asks whether a change should be behind a flag, when reviewing a diff or pull request, or when running in CI on a PR. Runs a fixed decision tree over the committed change and the code around it, then emits a structured advisory recommendation. Read-only: it never creates or modifies flags."
license: Apache-2.0
compatibility: "Advisory and read-only. Needs a git checkout with the change committed, a shell, git and Python 3.10+ (no packages). Reads LaunchDarkly flag state through your LaunchDarkly tools or LAUNCHDARKLY_API_KEY when available, and works without it. When it can't run, it hands off to the should-flag-change skill. Returns a structured verdict as a `recommend-flag` block."
metadata:
  author: launchdarkly
  version: "0.1.0"
  graph: "e0a0549d0ce9"
---

# Should This Change Be Behind a Flag?

This skill answers one question about a committed change: should it ship
behind a LaunchDarkly feature flag? It does not decide by judgment. A fixed
decision tree asks a series of narrow questions about the change, some
answered mechanically from git and LaunchDarkly, the rest by you, each by a
written procedure, from evidence the skill gathers. The same answers always
give the same result.

Every command below is this skill's command line, `ld-factory.pyz`: one file, beside
this one. Where it isn't on your `PATH`, run it as `SKILL_DIR/ld-factory.pyz`
(`SKILL_DIR` is the directory this file is in), or `python3 SKILL_DIR/ld-factory.pyz`.
It needs `python3` and `git`, nothing else.

**Finish in one run.** Don't stop partway to ask anyone something and wait.
Everything below, including fetching flags and answering a question a second
time, happens in the same turn.

## Scope

- **Advisory and read-only.** Never create, toggle, or modify a flag, and
  never edit the repo being checked. Everything the skill writes goes to its
  run folder under `~/.cache/should-i-flag/` (or `SHOULD_I_FLAG_RUNS`).
- **Committed changes only**: the branch's commits against its base, the same
  change a pull request shows. Uncommitted edits and untracked files are not
  part of it. A long-lived branch is checked as one change, all its commits
  together (`start` prints the count as `CHANGE`).

## When it can't run: use should-flag-change

Hand off to the `should-flag-change` skill, and say in your summary that you did and
why, when this skill can't run:

- there's no shell, no `python3` or no `git`, or no checkout of the change
  (for example, only a pasted diff);
- `ld-factory.pyz` crashes, or reports a setup problem (exit 2) you can't fix by
  correcting what you passed it.

Follow `should-flag-change` from the start, and never mix the two. If it isn't
available either, say so and stop.

## Steps

### 1. Prepare

```bash
ld-factory.pyz start <REPO_PATH> [--base <REF>] [--head <REF>] \
    [--pr-title "<title>"] [--pr-body-file <file>] [--client-repo <NAME>=<PATH>]
```

- `REPO_PATH` defaults to the current directory, `--head` to `HEAD`, `--base`
  to the remote's default branch (`origin/HEAD`, else `origin/main`).
- **On a pull request** (CI, a PR review), pass the PR's base and head:
  `--base origin/<base_ref> --head <head_sha>`, and its title and body
  (write the body to a file first). Without them the commit message stands in
  for the PR text.
- `--client-repo` (repeatable) names a checkout of another repository whose
  code calls this one's interfaces, e.g. the frontend for a backend. Without
  it, checkouts beside `REPO_PATH` of the other repositories the skill knows
  are used when present. Only the consumer search below reads them.

It prints `RUN: <folder>` and status lines (`CHECKING`, `CHANGE`,
`UNCOMMITTED`, `PR TEXT`, `LAUNCHDARKLY`). By exit code:

| Exit | Meaning | What you do |
|---|---|---|
| 0 | Ready | Go to step 2: the two searches. |
| 7 | LaunchDarkly flags are needed | Fetch the flags listed in `RUN/launchdarkly-needed.txt` as [LAUNCHDARKLY.md](references/LAUNCHDARKLY.md) says, then run the same `start` command again. If you have no way to read LaunchDarkly, run it again with `--no-launchdarkly`. |
| 3 | No profile for this repo | Write one as [PROFILE.md](references/PROFILE.md) says, check it, and run `start` again. |
| 4 | Nothing committed to check | Stop; tell the developer to commit (a WIP commit is fine) and ask again. |
| 6 | Can't tell which changes are this branch's | Stop and report it: a person needs to decide. |
| 2 | Setup problem | If you passed something wrong (a ref, a file), fix it and run `start` again; otherwise hand off to `should-flag-change` (above) and say why. |

### 2. Two searches the evidence can't do

The evidence finds a flag when it is evaluated near the changed code or in a
caller a few levels up. A flag can gate a change from further away: a route
or layout that only renders the changed code when the flag is on, a helper or
hook that wraps the flag, a server handler that returns early, a style that
applies only under a flag's class. Look for those now, before answering
anything: P6 and P12 ask about gates, and they see what you find here.

Follow `RUN/gate_search.txt` (written by `start`; the method is
[GATES.md](references/GATES.md)). Write its JSON to `RUN/gates.json`, then:

```bash
ld-factory.pyz gates RUN
```

It checks every line of every gate you report against the change's commit
and keeps only the gates whose every link matches, then adds them to the
evidence (`GATES: N verified, M dropped`). An empty list is a correct result
when nothing gates the change: don't guess.

**Then the risk search.** Some changes rework a path customers already use in
a way that can fail them -- a new call or write to another service, an
existing call pointed somewhere else, a cache, a check that blocks the path
when a call fails, a new action on a customer screen, a removed capability, a
change to stored data -- without tripping any of the questions. Follow
`RUN/risk_search.txt` ([RISK.md](references/RISK.md)), write its JSON to
`RUN/risks.json`, then:

```bash
ld-factory.pyz risks RUN
```

It checks each finding's every line (the changed line must be one the diff
adds or modifies, the entry point outside tests) and answers one question
from what holds (`RISKS: N verified ... P30 = yes|no`). You never answer that
question yourself. Most changes have no finding: an empty list is correct.

**A dropped claim gets one repair.** When `gates`, `risks` or `readers`
prints a claim as dropped, read why: usually a quoted line doesn't match its
number, or a link has a role the search doesn't use. Re-read the lines it
cites at the commit, fix that claim's links (path, line, the line's exact
text, role) in the same JSON file, and run the same command again -- once.
Don't add a claim in the repair or change what one says; if it doesn't hold
up when you re-read it, remove it.

`next` and `decide` refuse to run (exit 8) until both searches are recorded.

### 3. Answer the questions the result needs, one at a time

Read `RUN/evidence.txt` and `RUN/answering.txt` once. `evidence.txt` is the
evidence and the rules for answering, and lists the questions already
answered automatically (don't answer those; later questions may refer to
them). `answering.txt` is the answer's shape and the rules for cases that
need one: P2's list of changed lines that alter behavior, the reuse keys,
citing a deleted line, a follow-up question whose earlier question was no,
and a question about a list that isn't there.

Then ask for questions one at a time. Each answer can settle the result, and
questions after that point are never asked:

```bash
ld-factory.pyz next RUN
```

prints `QUESTION: <id>` and the question. Answer it by its procedure, as
JSON on stdin:

```bash
ld-factory.pyz answer RUN <id> <<'JSON'
{"value": "no", "evidence": "...", "citations": [{"path": "...", "line": 12, "why": "..."}]}
JSON
```

`answer` records it and prints the next question, so keep answering what it
prints. After the tree's questions come any REPORT-ONLY questions (ids like
`R1`): answer them the same way; they add to the report but never change the
result. When it prints `DECIDED`, go to step 4. If it prints `RECHECK` (exit
5), one question is asked again because two answers disagree: answer the
question it shows with `ld-factory.pyz answer RUN <id> --recheck`. If it exits 7,
fetch the LaunchDarkly flags as in step 1, then run `next` again.

**The consumer search, when asked for.** If you answered the question about
an interface's contract a separate client reads as unresolved because no
client is shown, and the result depends on it, `next` (or `decide`) prints
`CONSUMER SEARCH NEEDED` and exits 8. Follow `RUN/consumer_search.txt`
([CONSUMERS.md](references/CONSUMERS.md)): look for the client code that reads what
changed, in this repository and the client checkouts it lists. Write its JSON
to `RUN/consumers.json`, then:

```bash
ld-factory.pyz readers RUN
```

It checks every reader line by line (`READERS: N contract change(s), M with
a verified reader`), and the question is settled from it: yes when a reader
holds, no when the search found none. Leave your own answer as it was; then
run `next` again (or `decide`, if that is where it stopped).
(`questions.txt` lists every question, for reference; don't answer from it.)

The rules in `evidence.txt` decide everything here. In short:

- Answer the ONE question asked by following its PROCEDURE exactly. You are
  not deciding whether the change needs a flag; the tree does that.
- Answer each question on its own. Don't let one answer lean on another.
- Answer from the evidence, and cite only a `path` and `line` it shows.
  A very large change doesn't all fit: the evidence marks every part it
  leaves out (`[cut to fit: ...]`, and PACKET NOTES lists them), and what
  isn't shown isn't evidence. If the PR description and the diff disagree,
  the diff wins.
- Your `evidence` text and each citation's `why` are shown to the developer
  word for word (WHY, REASONS, WHERE TO CHECK IT, the `recommend-flag`
  block). Write them in plain words about their code, without the check's own
  terms (see "Talking to the developer").
- Answer `"unresolved"` when the question's UNRESOLVED-WHEN holds or the
  evidence lacks what the procedure needs. Guessing is worse than
  abstaining: `"unresolved"` sends the decision to a person, which is the
  intended outcome. (Some procedures say what absence of evidence means;
  then follow them.)

### 4. Decide

```bash
ld-factory.pyz decide RUN
```

It checks every citation against the evidence (an answer whose citations
don't check out counts as unresolved), walks the tree, and prints the result.

| Exit | Meaning | What you do |
|---|---|---|
| 0 | Decided | Go to step 5. |
| 7 | More LaunchDarkly flags are needed | Fetch them as in step 1 and run `decide` again. |
| 8 | A search isn't recorded yet | Do what it says: step 2's two searches, or the consumer search (step 3), then run `decide` again. |
| 2 | Setup problem, or a question is still needed | Pass a setup message on; for `NOT DECIDED YET`, go back to `ld-factory.pyz next`. |

### 5. Emit the verdict

`decide` prints the result in plain English (`RESULT`, `WHY`, `DECIDING
QUESTION`, and when a flag is suggested `REASONS FOR A FLAG`, `FLAG TO ADD`,
`WHERE TO CHECK IT`, `WHAT A ROLLOUT CAN MEASURE`, `NEARBY FLAGS`, `NEXT
STEPS`), then `ALSO CHECKED`, `CAVEAT`, and a fenced block:

````
```json recommend-flag
{ "recommend": true, "verdict": "suggested", "confidence": "medium", "reasons": [...], ... }
```
````

That block is the deliverable. **Copy it verbatim** as the last thing in your
output: CI and other tools parse it. Never edit its fields.

- `verdict` is `suggested`, `reuse-existing` (with `reuse_flag_key`),
  `already-flagged`, or `not-suited`.
- When a person has to decide, the verdict is `suggested` with
  `confidence: "low"`, `needs_human: true`, and `question_for_human`.
- If a `recommend-flag` tool is available, call it once with the block's
  `recommend`, `verdict`, `reuse_flag_key` (if any), `confidence` and
  `reasons`, as well as printing the block. If your instructions say to
  translate the verdict into another tool instead, do that rather than
  calling `recommend-flag`.

Then summarize for the developer in short paragraphs, using only what
`decide` printed:

1. The `RESULT` and `WHY`, close to verbatim, and a sentence or two on what
   in their change led there, in terms of their code. If `REASONS FOR A
   FLAG` lists more than the deciding one, a sentence for each.
2. When a flag is suggested: what kind (`FLAG TO ADD`), where to check it
   (`WHERE TO CHECK IT`, by file and component), what a rollout can measure,
   and the `NEXT STEPS`. If there's a `NEARBY FLAGS` line, say a similar
   neighbor already uses a flag.
3. `UNCLEAR, BUT IT DIDN'T MATTER`, if present: a question the check couldn't
   settle, which every answer would decide the same way.
4. `WORTH A LOOK`, if present.
5. Anything from step 1 to act on: uncommitted changes left out, or
   LaunchDarkly state not read.
6. The `CAVEAT`, in a sentence.

Don't add facts the output doesn't give you. List the `ALSO CHECKED`
questions only if asked how it got there.

## Talking to the developer

The people reading this don't know how the check works inside. In everything
you say, including progress updates, don't use its internal words: predicate,
P-numbers, node, walk, tree, terminal, outcome codes (T-SG-6, E-UNRESOLVED),
manifest, packet, hunk, mechanical, merge_base. Say "the check", "your
change", "the code you changed", "a person needs to decide", "the version on
main". Refer to questions by what they ask, in the wording `decide` prints.

## What not to do

- Don't create, toggle, or modify any flag, and don't edit the checked repo.
- Don't answer from your own view of the change's risk. Follow each procedure.
- Don't cite code the evidence doesn't show, and don't change the
  `recommend-flag` block.
- Don't hand off to `should-flag-change` because the result surprised you. It's only
  for when this skill can't run.
