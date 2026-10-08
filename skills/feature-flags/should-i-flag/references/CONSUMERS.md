# Consumer search

One question about this change couldn't be settled from the evidence: whether
it changes what an EXISTING interface returns in a way a SEPARATE client
reads. The interface isn't shown to be published, and the evidence shows no
client reading what changed; that client is often in another repository. Find
it, or show there is none. Not a judgment that a client "probably" depends on
it: a reader you can show, line by line, in the code.

THE CHANGE
- Repository: {CHECKOUT}. Read files at the change's commit only:
  `git -C {CHECKOUT} show {HEAD}:<path>`; search with
  `git -C {CHECKOUT} grep -n <pattern> {HEAD} -- <paths>`. The working tree
  may hold other work: don't read it.
- The change's commit: {HEAD}. The version on main it is compared with:
  {BASE}. See the change with `git -C {CHECKOUT} diff {BASE}...{HEAD}`.
- The evidence, including the PR text: {RUN}/evidence.txt (its CHANGED FILES
  section gives each file's role; a PUBLISHED API LOOKUP section, when present,
  says which changed operations are in the published API).

CLIENT REPOSITORIES
Checkouts of other repositories whose code calls this one, each as it was on
its main branch when the change was compared (a client written after the
change can't show what relied on the old contract):
{CLIENTS}

WHAT IS A CONTRACT CHANGE
A behavior-carrying hunk that changes a status code, error shape or error
code, field presence or type, pagination, ordering, or a limit, in what an
interface that exists at {BASE} returns (an HTTP or GraphQL response, a tool
or RPC result, a webhook payload, stored data another program reads).
- A request the change makes differently (what it sends) is not one.
- An interface the diff adds has no contract yet.
- A response that failed at {BASE} and now succeeds is a repair, not one. A
  request that still fails but with a different status or error body IS one.

WHAT IS A SEPARATE READER
Code in a separate client -- a frontend, SDK, CLI, another service, or a
client repository -- that reads the specific thing that changed: the field it
accesses, the status code or error code it branches on, the order or page it
relies on. Code in the same program as the server (its own handlers, its own
tests) is not a separate reader. Code that only calls the interface without
reading what changed is not a reader of the change.

WHAT TO REPORT
Report each contract change. If you find a separate reader of it, give a
chain of real lines, quoted exactly:
- at least one CHANGED line: a line the diff adds or modifies, in shipping
  code (role "changed", repo "self");
- the READER line: the client line that reads the changed field, status or
  code (role "reader", repo "self" or the client repository's name above);
- "token": the exact identifier, field name, status code or error code the
  reader reads. It must appear in the reader line and in the diff.
Every link is checked mechanically: the changed line must be in the diff, the
reader line must exist at its commit outside tests, stories and docs, be in a
client repository or in a different language from the changed line, and
contain the token, and the token must appear in the diff. A link that doesn't
match drops the reader. Report a contract change with an empty chain when you
searched and found no reader: that is a normal, useful answer, and it settles
the question as no. If the change alters no contract at all, return an empty
list.

Read-only: never modify any checkout, use the network, or read other folders.
Never print a token or key.

Write ONLY this JSON to {RUN}/consumers.json:

{"contract_changes": [{"interface": "the existing interface (route, query, tool, payload)",
                       "what_changed": "one sentence: the status, field, error, order or limit that changed",
                       "token": "the identifier a reader reads, or empty when no reader was found",
                       "chain": [{"repo": "self | <client name>", "path": "path/at/that/commit", "line": 123,
                                  "text": "the exact line", "role": "changed | reader | calls"}],
                       "searched": "where you looked for readers"}]}
