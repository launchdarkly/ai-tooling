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

WHAT COUNTS (the team's flag policy: flag changes to paths already in use, new
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

DO NOT REPORT
- tests, stories, fixtures, docs, build or CI configuration;
- internal tools, admin consoles and developer utilities that only employees
  use (an internal launcher, a support console, a private developer CLI);
- logging, metrics, traces or analytics events only;
- a migration or schema change no shipping code reads or writes yet, or code
  that nothing shipping calls yet (a later pull request will);
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
`python3 {SKILL_DIR}/scripts/ld-factory.pyz risks {RUN}`:

{"findings": [{"kind": "new-call | retarget | cache | fail-closed | new-action | removed | stored-data",
               "chain": [{"path": "path/at/head", "line": 123, "text": "the exact line", "role": "changed | entry | calls | renders | registers"}],
               "customer_facing_because": "who reaches the entry, and how (a session-bound route, a customer page, a job per customer account)",
               "why": "one sentence, in plain words about the developer's code: what could go wrong for customers that a flag would let the team switch off"}],
 "searched": "one or two sentences: what you checked"}
