# Risk search

You are checking one pull request for concrete risk that a feature flag would
let the team turn off: a change to behavior customers already depend on, on a
path they reach. Not a judgment that the change "seems risky": a finding you can
show, line by line, in the code at the pull request's commit.

THE CHANGE
- Repository: {CHECKOUT}. Read files at the change's commit only:
  `git -C {CHECKOUT} show {HEAD}:<path>`; search with
  `git -C {CHECKOUT} grep -n <pattern> {HEAD} -- <paths>`. The working tree
  may hold other work: don't read it.
- The pull request's commit: {HEAD}. The version on main it is compared with:
  {BASE}. See the change with `git -C {CHECKOUT} diff {BASE}...{HEAD}`.
- The evidence, including the PR text: {RUN}/evidence.txt (its CHANGED FILES
  section gives each file's role: shipping code, test, build, docs).

WHAT COUNTS (flag changes to paths already in use, new
calls and writes, backend performance changes, fixes that touch stored data or
an external integration, a new control that adds a new action)
Report a finding only if it is one of these kinds, in SHIPPING code:
- new-call: a new call or write to another service, external integration,
  queue or durable store, on a path customers' requests or jobs already run;
- retarget: an existing call, read or write now sent to a different target
  (another project, account, deployment, client, endpoint, table or column);
- cache: a cache placed in front of an existing read on such a path;
- fail-closed: a new condition that stops, blocks or skips that path when such
  a call fails or comes back empty;
- new-action: a new control or entry on an existing customer screen that
  triggers a new request, write or action (not only local UI state: opening a
  panel, sorting, collapsing, styling is not an action);
- removed: a control, option, endpoint or behavior customers use, removed with
  no replacement where they used it;
- stored-data: a change to how existing customer data is written, migrated or
  backfilled.


A NEW FAILURE, NOT JUST A PATH
Say for each finding whether the change is meant to keep behavior the same (a
refactor, a swapped data source, a reworked query, a moved component):
"preserves_behavior": true or false. When it is true, the finding must also name
the new failure: the case -- an input, a state, a dependency that errors or
comes back empty, a page or a project shape -- in which customers end up worse
off at {HEAD} than they did at {BASE}: what the version on main did in that
case, and what the change does instead. Such a change is a finding only when the
code shows such a case. A change that means to alter behavior (a new call or
write, a stored-data change, a new action, a removal) is judged by the kinds
above as before. A failure the old
code already had in the same case (the same error, empty state or fallback when
a read fails) is not new. A bug that merely could exist is not concrete: name
the case and the line that produces the worse outcome, or don't report it.

DO NOT REPORT
- tests, stories, fixtures, docs, build or CI configuration;
- internal tools, admin consoles and developer utilities that only employees
  use (an internal launcher, a support console, a private developer CLI);
- logging, metrics, traces or usage-analytics events only. NOT this
  exclusion: data that decides how a signup or account is treated
  downstream -- a classification verdict (for example junk), lead
  routing, or targeting data sent to sales or marketing systems (Segment
  traits, Marketo leads) or stored on the account. Report that as
  stored-data or new-call;
- a migration or schema change no shipping code reads or writes yet, or code
  that nothing shipping calls yet (a later pull request will);
- a change that takes effect when it is deployed or applied, not when code
  runs: a schema or DDL migration, a table swap or rename, a backfill, build
  or infrastructure configuration. A runtime flag can't switch it off, so it
  isn't a finding even when shipping code reads the result. NOT this
  exclusion: application code in the same change that starts reading or
  writing somewhere new -- report that part;
- a change that only affects inputs that already failed on main (a repair of
  an error path);
- copy, styling, layout or ordering changes on their own;
- a change already behind a LaunchDarkly flag the evidence shows enclosing it.
If you are unsure whether a path is customer-facing, it isn't a finding.

WHAT TO REPORT
For each finding, a chain of real lines at {HEAD}, quoted exactly:
- at least one CHANGED line: a line the diff adds or modifies, in shipping code
  (role "changed");
- the ENTRY a customer reaches it through: a route or page, a request handler
  bound to a user session or API token, a webhook or job that runs for
  customers (role "entry"), with any step between them that isn't obvious (a
  call, a render, a registration; role "calls" / "renders" / "registers").
Every link is checked mechanically: the changed line must be in the diff, the
entry must exist at {HEAD} outside tests, and a link that doesn't match drops
the finding. An empty list is the right answer when nothing qualifies: most
changes have none. Don't stretch a kind to fit.

Read-only: don't modify the repository, create or change flags, or use the
network.

Write ONLY this JSON to {RUN}/risks.json, then run
`python3 {SKILL_DIR}/ld-factory.pyz risks {RUN}`:

{"findings": [{"kind": "new-call | retarget | cache | fail-closed | new-action | removed | stored-data",
               "chain": [{"path": "path/at/head", "line": 123, "text": "the exact line", "role": "changed | entry | calls | renders | registers"}],
               "preserves_behavior": true,
               "new_failure": {"case": "the input, state or failure in which it differs", "main": "what customers got at the version on main", "head": "what they get with the change"},
               "customer_facing_because": "who reaches the entry, and how (a session-bound route, a customer page, a job per customer account)",
               "why": "one sentence, in plain words about the developer's code: what could go wrong for customers that a flag would let the team switch off"}],
 "searched": "one or two sentences: what you checked"}
