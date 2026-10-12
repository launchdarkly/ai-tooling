# Feature flag search

The check looked for an existing flag this change could reuse and found none
that covers it. It looks only at flags evaluated close to the changed lines,
so it misses the flag that releases the feature the change belongs to when
that flag is checked somewhere else: the route, page, layout, navigation entry
or registration the feature is reached through. Find that flag, or show there
is none. Not a guess about which flag "probably" applies: a flag you can show,
line by line, in the code at the change's commit.

THE CHANGE
- Repository: {CHECKOUT}. Read files at the change's commit only:
  `git -C {CHECKOUT} show {HEAD}:<path>`; search with
  `git -C {CHECKOUT} grep -n <pattern> {HEAD} -- <paths>`. The working tree
  may hold other work: don't read it.
- The change's commit: {HEAD}. The version on main it is compared with:
  {BASE}. See the change with `git -C {CHECKOUT} diff {BASE}...{HEAD}`.
- The evidence, including the PR text and the flags already found:
  {RUN}/evidence.txt. Read its FLAG EVALUATION SITES and REUSE CANDIDATES
  sections. What the check has so far about reuse:
{CANDIDATES}

WHAT TO FIND
The feature the change belongs to: the screen, flow, endpoint or job whose
behavior the changed code produces. Then the flag that releases THAT
feature: the flag whose value decides whether customers reach the feature's
own entry -- its route or page, the registration that mounts it, the handler
that serves it, or the module that is the feature.

Not a flag over a whole product area. A flag that decides a top-level section
of the product -- many features behind one route prefix, layout or navigation
group -- releases the area, not this feature: the team doesn't reuse such a
flag, so don't report it. The entry must be the feature's own route, page,
registration, handler or module. Not a flag that only decides something
beside the change (a different branch of the same page, a different tab),
and not a flag the change itself adds: it must exist at {BASE}.

WHAT TO REPORT
For the flag, two chains of real lines at {HEAD}, quoted exactly:
- `chain`: from the flag to the feature's entry. The line that evaluates the
  flag (role "evaluates"), the line where its value decides (a condition, a
  ternary, a guard that returns, a filter on a route list; role "decides"),
  any step between them that isn't obvious (role "passes"), and LAST the
  feature's entry line itself (role "entry"): the route definition, the page
  component's mount, the registration, the handler.
- `change_link`: from that entry to the changed code. Start at a line in the
  entry's file (the route's element, a lazy import, a registered handler;
  role "renders", "calls", "registers", "imports" or "passes"), follow each
  step that isn't obvious, and end at a line in a file this change modifies
  (role "changed": the changed component, function or handler, or a line
  inside it). When the entry is the feature's own module (`entry_kind`
  "module"), the link may be a line in a changed file in the entry's own
  folder -- beside the entry, or below it when the entry is the folder's
  index file (role "module").
Every link is checked mechanically: the key must exist at {HEAD} and at
{BASE}, each quoted line must match its line at {HEAD}, the chain must
evaluate, decide and end at the entry outside tests, and the link must start
at the entry's file (a module: stay in its folder) and end in a changed
shipping file. A link that doesn't
match drops the claim. An empty list is the right answer when no flag
releases the feature, or the only flag gates a whole product area: don't
stretch.

Read-only: don't modify the repository, create or change flags, or use the
network.

Write ONLY this JSON to {RUN}/features.json, then run
`python3 {SKILL_DIR}/scripts/ld-factory.pyz features {RUN}`:

{"features": [{"key": "the-flag-key",
               "feature": "a short name for the feature, in the developer's words",
               "entry_kind": "route | page | registration | handler | module",
               "chain": [{"path": "path/at/head", "line": 12, "text": "the exact line", "role": "evaluates | decides | passes | entry"}],
               "change_link": [{"path": "path/at/head", "line": 34, "text": "the exact line", "role": "renders | calls | registers | imports | passes | module | changed"}],
               "why": "one sentence, in plain words about the developer's code: how this flag being off keeps customers from the feature the change belongs to"}],
 "searched": "one or two sentences: the routes, pages and registrations you followed"}
