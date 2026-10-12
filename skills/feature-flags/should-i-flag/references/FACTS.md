# Fact search

One question about this change was answered "unresolved", and the result
depends on it: answered yes or no, the check would decide differently. The
answer usually says what the evidence was missing -- a caller, a guard, a
writer or reader, a setting, a route. That fact is often in the repository at
the change's commit, outside the part of the code the evidence shows. Search
for exactly that fact, and report what you find as quoted lines. Don't answer
the question here, and don't look for anything else.

THE CHANGE
- Repository: {CHECKOUT}. Read files at the change's commit only:
  `git -C {CHECKOUT} show {HEAD}:<path>`; search with
  `git -C {CHECKOUT} grep -n <pattern> {HEAD} -- <paths>`. The working tree
  may hold other work: don't read it.
- The change's commit: {HEAD}. The version on main it is compared with:
  {BASE}. See the change with `git -C {CHECKOUT} diff {BASE}...{HEAD}`.
- The evidence: {RUN}/evidence.txt.

THE QUESTION ({QUESTION_ID})
  {QUESTION}

It is unresolved when:
{UNRESOLVED_WHEN}

The answer given, and why it was unresolved:
  {ANSWER_EVIDENCE}

WHAT TO REPORT
The lines at {HEAD} that show the missing fact, or show it isn't there: each
one quoted exactly, with its path and line number, and a one-line claim of
what it shows ("the only caller passes false", "this handler returns before
the changed call when the account is new"). Report the lines that settle it,
not everything you read: a few lines, at most 12. Each is checked
mechanically -- its path must exist at {HEAD}, and the quoted text must match
that line -- and a finding that doesn't match is dropped. Only verified lines
are shown when the question is asked again, and the answer must still follow
the question's procedure. If you can't find the fact, report no findings and
say where you looked: that is a correct answer, and the question stays
unresolved.

Read-only: don't modify the repository, create or change flags, or use the
network.

Write ONLY this JSON to {RUN}/facts.json, then run
`python3 {SKILL_DIR}/scripts/ld-factory.pyz facts {RUN}`:

{"question": "{QUESTION_ID}",
 "findings": [{"path": "path/at/head", "line": 12, "text": "the exact line", "claim": "one line: what this line shows"}],
 "not_found": false,
 "searched": "one or two sentences: what you looked for and where"}

THE QUESTION IN FULL, as it was asked:

{FULL_QUESTION}
