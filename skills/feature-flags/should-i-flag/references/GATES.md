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

CLIENT REPOSITORIES
Checkouts of other repositories whose code calls this one (a frontend that
calls this backend's GraphQL fields or routes, or the backend a frontend
endpoint serves), each as it was on its main branch when the change was
compared. Read them only with these commands, at the commit given:
{CLIENTS}

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
repository goes under `outside_repo`, with the reference that points to it,
unless it gates every caller of a changed unit in a client repository above:
then report it as caller coverage (below).
An empty list is a correct answer when nothing gates the change: don't guess.

CALLER COVERAGE: WHEN NO ONE GATE COVERS A CHANGED UNIT
A flag can hide a feature's screen or entry point while some changed code
sits outside every chain you can show: an endpoint or resolver the flagged
screen calls, a hook, serializer or service method that several callers use.
That code is still covered when EVERY way to reach it is behind a flag, or
leaves the new behavior off. For a changed unit (function, method, component,
hook, endpoint or route handler, resolver) defined in a file the diff changes,
that no gate you report already reaches, you may list its callers instead,
under `covered_units`:
- List EVERY caller at {HEAD}. Find them with
  `git -C {CHECKOUT} grep -n -w <name> {HEAD}` (and the route path, for an
  endpoint), then follow imports, re-exports, registrations and aliases.
  An import line is not a caller: list the lines that call, render or mount
  it. Callers in tests and stories may be left out, or listed as `test`.
- Each caller says how it is reached: `gated` (give that flag's gate: a chain
  in the gate format above, ending with the caller line itself, role `calls`
  or `renders`), `off` (it passes a value that leaves the new behavior off;
  quote the line that does it as `off_line`), `test` (a test, story or
  fixture), or `none` (nothing reaches that caller at head; say why in
  `note`).
- Lines that declare or register the unit without calling it (an interface
  method, a route table entry, an `export default`) go in `declared_at`.
- `ld-factory.pyz gates` checks every quoted line, checks each gated caller's chain
  like a gate, and searches {HEAD} for the name (and route) itself: a
  reference in shipping code you didn't list drops the whole claim. A name
  another symbol also uses will drop it too; that is expected.
- Don't list a unit a reported gate already reaches.

CALLERS IN A CLIENT REPOSITORY
A changed endpoint, GraphQL resolver or field, route handler or RPC method is
often called only from a client repository listed above: a backend resolver
whose only callers are frontend screens, each behind the frontend's own flag.
Search that checkout for its callers, read-only, at its commit, with exactly
the commands listed for it, and list every caller there with `"repo": "<the
client's name>"`. Its `path`, `line` and `text`, its gate's chain and its
`off_line` are then in that client at that commit. The unit itself stays in
this repository.
- Give the unit's `external` name: the name a client uses to call it (the
  GraphQL field or operation, the RPC method), when it differs from `name`;
  for a route, the route path a client requests as `route`.
- For a GraphQL field, find every operation (query, mutation, fragment) in
  the client that requests it, then every line that calls each operation
  through its generated hook or document (`use<Operation>Query`,
  `use<Operation>LazyQuery`, `use<Operation>Mutation`, `<Operation>Document`,
  a fragment's spreads): those lines are the callers. The operation document
  and generated code need no listing, and neither do lines that only read
  the response (`data?.field`).
- The client is searched at its commit for the external name, the route and
  each operation's hooks and documents: a use in its shipping code you didn't
  list drops the whole claim, as in this repository. Generated code counts
  only when a listed caller uses it.
- This repository's generated code that serves the external name (a GraphQL
  executor, a generated router) is how those clients reach the unit, and
  needs no listing; any other reference in this repository still does.
- Put under `outside_repo` only a lead you can't check in a listed client
  checkout: a repository that isn't listed, or a caller you can't show.

Read-only: don't modify the repository or a client checkout, create or change
flags, or use the network.

Write ONLY this JSON to {RUN}/gates.json, then run
`python3 {SKILL_DIR}/scripts/ld-factory.pyz gates {RUN}`:

{"gates": [{"key": "the-flag-key", "how": "route | layout | helper | hook | caller | handler | css | config | other",
            "covers": "all | part", "covers_note": "which changed hunks it gates, if part",
            "chain": [{"path": "path/at/head", "line": 123, "text": "the exact line", "role": "evaluates | decides | passes | renders | calls | styles | registers | changed"}],
            "why": "one sentence, in plain words about the developer's code: how this flag being off keeps the changed code from running or being seen"}],
 "covered_units": [{"unit": {"path": "path/at/head", "line": 12, "text": "the exact definition line", "name": "the identifier callers use", "route": "/the/route/path, for an endpoint (else leave out)", "external": "the name a client calls it by, when it differs (a GraphQL field), else leave out"},
                    "declared_at": [{"repo": "a client's name, for a line there (else leave out)", "path": "...", "line": 0, "text": "..."}],
                    "callers": [{"repo": "a client's name, for a caller there (else leave out)", "path": "...", "line": 34, "text": "the exact calling or mounting line", "reached_by": "gated | off | test | none",
                                 "gate": {"key": "the-flag-key", "chain": ["...links as in gates, the last one this caller line..."]},
                                 "off_because": "for off: how this path leaves the new behavior off", "off_line": {"path": "...", "line": 0, "text": "..."},
                                 "note": "for none: why nothing reaches this caller"}],
                    "why": "one sentence: every way a customer reaches this unit is behind a flag or leaves the new behavior off"}],
 "outside_repo": [{"key_or_name": "...", "reference": "path:line and what it says"}],
 "searched": "one or two sentences: the routes, callers, helpers or styles you followed"}
