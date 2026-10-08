# Gate search

Check this change for a LaunchDarkly flag that already gates it: a flag that
must be ON for the changed code to run or be seen. `ld-factory.pyz start` built the
evidence; it finds a flag when the flag is evaluated near the changed code or
in a caller a few levels up. Your job is the gates it can miss.

THE CHANGE
- Repository: {CHECKOUT}. Read files at the change's commit only:
  `git -C {CHECKOUT} show {HEAD}:<path>`; search with
  `git -C {CHECKOUT} grep -n <pattern> {HEAD} -- <paths>`. The working tree
  may hold other work: don't read it.
- The change's commit: {HEAD}. The version it is compared with: {BASE}.
  See the change with `git -C {CHECKOUT} diff {BASE}...{HEAD}`.
- The evidence, including the PR text and the flags already found:
  {RUN}/evidence.txt. Read its FLAG EVALUATION SITES and REFERENCED FILES
  sections, and the gates listed in `ld-factory.pyz next`'s P6 question if you have
  seen it, so you don't report what is already there.

HOW A FLAG CAN GATE A CHANGE WITHOUT BEING EVALUATED IN IT
Flags are declared in a flags file and evaluated through generated functions
or SDK calls; the evidence's flag sites show this repository's forms. Look
above the diff:
- a route, page, layout, navigation entry or access check that only renders
  or reaches the changed code when the flag is on;
- a helper or hook that returns a flag's value (`isXEnabled()`,
  `useXAccess()`) and the code that tests it before rendering or calling the
  changed code;
- a component or function further up the render or call chain, including a
  lazy-loaded one (`lazy(() => import(...))`);
- a server handler, resolver or service method that returns early, or never
  calls the changed code, unless the flag is on;
- a CSS class, data attribute or theme value the changed styles apply under,
  set only when the flag is on;
- a configuration value or registration (a job, a route table entry, a
  dependency binding) made only when the flag is on.

WHAT TO REPORT
Only a gate you can show end to end, at {HEAD}: the line where the flag is
evaluated, the line where its value decides (a condition, a ternary, a guard
that returns, a class toggle, a registration), and the line where the changed
code is rendered, called, styled or registered under that decision, with every
step between them that isn't obvious (an import, a hook call, a prop pass).
Every link is a real line at {HEAD}, quoted exactly; `ld-factory.pyz gates` checks
each one, and a link that doesn't match drops the whole gate.

Don't report a flag evaluated near the code but not deciding whether it runs,
a flag that gates a different branch from the one the change is in, a flag
the evidence already shows enclosing the change, or anything with no code
chain (a flag named only in the PR text). A flag that lives in another
repository goes under `outside_repo`, with the reference that points to it.
An empty list is a correct answer when nothing gates the change: don't guess.

Read-only: don't modify the repository, create or change flags, or use the
network.

Write ONLY this JSON to {RUN}/gates.json, then run
`python3 {SKILL_DIR}/scripts/ld-factory.pyz gates {RUN}`:

{"gates": [{"key": "the-flag-key", "how": "route | layout | helper | hook | caller | handler | css | config | other",
            "covers": "all | part", "covers_note": "which changed hunks it gates, if part",
            "chain": [{"path": "path/at/head", "line": 123, "text": "the exact line", "role": "evaluates | decides | passes | renders | calls | styles | registers | changed"}],
            "why": "one sentence, in plain words about the developer's code: how this flag being off keeps the changed code from running or being seen"}],
 "outside_repo": [{"key_or_name": "...", "reference": "path:line and what it says"}],
 "searched": "one or two sentences: the routes, callers, helpers or styles you followed"}
