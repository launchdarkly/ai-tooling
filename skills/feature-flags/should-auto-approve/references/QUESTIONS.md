# The questions

What the check asks, in order. The changed paths answer some (marked);
the agent answers the rest from the code, each by its procedure.

## A1: Does the diff change the approval control itself: an approval policy file, the approval agent's configuration, review-bot rules, CODEOWNERS, or a branch protection or ruleset definition? (from the changed paths)

YES if any changed path is one of:
  APPROVAL_POLICY.md (any directory), CODEOWNERS (any location),
  a .cursor/BUGBOT.md (any directory) or any file under a
  .cursor/rules/, .cursor/automations/ or .cursor/approval-policies/
  directory, a GitHub ruleset or branch-protection definition
  (terraform or JSON describing repository rules).
CI workflow definitions are NOT this predicate (see B1): they are
never low, but a workflow edit does not let a change approve itself.

**Unresolved when:** Never: decided from paths alone.

## A3: Does the change delete, rewrite, or reshape data that already exists in a persistent store, in a way that redeploying the previous build does not undo?

YES for: a migration that drops or renames a table/column/index in use,
changes a column type with conversion, or rewrites rows (backfill,
UPDATE/DELETE over existing data); a ClickHouse migration that drops,
replaces, or re-materializes a table holding data; a code path that
bulk-deletes or overwrites existing customer records; a changed
serialization format for data written to a store that the previous
build cannot read back.

NO for additive schema (new table, new nullable column, new index
created concurrently) -- that is B2 -- and for writes of new records.

**Unresolved when:** The migration's effect depends on production data shape the tree does
not show (for example a conversion that fails only on some rows), and
the diff does not guard it.

## A4: Does the diff change infrastructure or deployment configuration that is applied to a production environment?

YES if a changed file is applied by a production deploy or provisioning
path: terraform/CDK/CloudFormation for prod accounts, Helm values or
Kubernetes manifests for prod clusters, ECS task definitions, the
production Dockerfile's base image, entrypoint, or installed system
packages, autoscaling and resource limits, production environment
variables, DNS, load balancer, or network policy.

NO for config applied only to dev, staging, CI, or local development
(docker-compose files, dev-stack, test clusters) -- that is B3.

NO for the deploy pipeline itself, even for production: which
pipelines a merge triggers, their order, serialization, promotion and
approval steps, notifications (Spinnaker/dinghy pipeline definitions,
deploy workflows, rollout orchestration). That is B1 or B3, medium. A4 is what production runs on, not how a build
gets there.

**Unresolved when:** The file's deploy target cannot be determined from the tree (no
pipeline or environment reference reaches it).

## B1: Does the diff change a CI workflow definition? (from the changed paths)

YES if any changed path is under .github/workflows/ or .github/actions/,
or is another CI system's pipeline definition (.circleci/, buildkite,
a Makefile target CI invokes is NOT included).

**Unresolved when:** Never: decided from paths alone.

## B2: Does the diff add or change a database schema or a migration? (from the changed paths)

YES if any changed path is a migration (SQL or Go migration directories,
ClickHouse migration directories, the migration _max marker), or a
persisted model definition whose change alters the schema an ORM
auto-migrates (GORM model structs, for example).
paths.py gives the path list; a reader confirms a model-file hunk
changes a persisted field (a method-only change to a model file is NO).
An API schema (a GraphQL schema.graphqls, an OpenAPI spec or api.yaml)
is NO: it is a contract, not a database schema; the code behind it is
asked at the C questions.

**Unresolved when:** A model file changed and paths.py cannot tell whether a persisted field
changed; the reader then answers.

## B3: Does the diff change infrastructure, build-image, or deployment configuration (any environment)? (from the changed paths)

YES if any changed path is a Dockerfile, a docker-compose file, a
shared dev-environment stack (dev-stack/), a deploy pipeline definition
(Spinnaker/dinghy, its generator), Helm chart, Kubernetes
manifest, terraform/CDK file, ECS/Lambda deploy descriptor, or
environment config read at deploy, in any environment: infrastructure and deployment configuration
need a review "regardless of size".
Editor and personal environment config (devcontainer, .cursor/
environments, editor settings) is NO.

**Unresolved when:** Never: decided from paths alone.

## A2: Does a behavior-carrying hunk change who is authenticated, what an identity is authorized to do, how a session or token is issued, validated, or expired, or how data is encrypted, signed, or hashed?

YES if, for some request, the set of identities allowed to perform an
action, or the identity resolved for that request, differs between
merge_base and head; or a token/session lifetime, scope, audience,
signature check, or cipher/hash parameter differs.

Includes: role and permission checks, policy evaluation, API key and
access-token scopes, SSO/SAML/OIDC handling, cookie flags, CSRF and CORS
allowlists, secret handling.

NO when the hunk is in that code but only renames, logs, adds a metric,
or reformats (that is B4), or when it only changes which UI controls are
shown and the server still enforces the same check.

**Unresolved when:** The enforcement point for the changed check is outside the tree (an
external authorizer, a vendored policy engine) and the diff alone does
not show whether enforcement changed.

## B4: Does a shipping hunk change middleware, authentication, authorization, session, or cryptography code, even without changing access (A2)?

YES if a shipping hunk is inside request middleware (code every request
passes through before its handler), or inside an authentication,
authorization, session, or crypto module, whatever the hunk does.
paths.py flags candidate paths by name (middleware, auth, session,
rbac, permission, crypto, token); the reader confirms the code's role.

**Unresolved when:** The changed code's role cannot be determined from the tree.

## B6: Does an approval policy file in force at merge_base that covers a changed path forbid automatic approval of a kind of change this change makes?

`start` lists the APPROVAL_POLICY.md files at merge_base that cover a
changed path (the file in that path's directory or the nearest one above
it; a root file covers every path). If it lists none, answer NO.

Read each listed file at merge_base. Count only a rule that names a kind
of change -- by what it changes, where, or how -- as not low risk or not
to be approved automatically. Answer YES if a shipping hunk of this
change is of that kind, naming the file, the rule and the hunk. Answer
NO otherwise.

These are not such rules; skip them:
  - rules about the pull request description, its author, or the review
    process itself (the approval gates check those);
  - a rule that permits automatic approval of a narrow kind of change
    under conditions, including one that says to route the pull request
    elsewhere when a condition fails or files outside its directory
    change (gate G3 checks those conditions);
  - examples or rationale in a policy, apart from the rule they
    illustrate.

Apply the rule as written to what the diff does. A rule's own words
outrank a narrower reading: if it says a kind of change is not low risk
even when behavior is unchanged, an unchanged-behavior change of that
kind is YES. The description's claims about risk are not evidence.

**Unresolved when:** The rule depends on something outside the repository at merge_base and
the change, or whether a hunk is of the rule's kind cannot be told from
the diff and the tree.

## B7: Does a shipping hunk change the name, value, derivation or emission of a telemetry attribute that a product view displays to customers?

Telemetry a product view displays is product data, not monitoring: a
span, span event, metric or log attribute that a page customers use
reads and shows (a trace or conversation view, an evaluation result,
a cost or usage rollup). The view usually lives in another repository,
so two things point to one:
  - `start` lists, as `hint_B7`, changed lines that name an attribute
    the product's views are known to read;
  - the PR's title or description says a product view, dashboard or
    another repository's page reads what the change emits. A claim that
    raises the risk can be taken as given; confirm only that the change
    really emits or alters the attributes it names.

YES if a shipping hunk adds, removes or renames such an attribute,
changes the value written into it or how that value is derived (a new
unit or scale, a label computed differently, a fallback), or changes
when the span, event or metric carrying it is emitted or which ones
carry it.

NO when the attribute is read only by our own monitoring (error
tracking, log search, operational dashboards: that is C5); when the
key appears only in text the program does not emit (a description, a
comment, documentation); and when every such hunk only moves or
reformats code that emits the same attributes with the same values.
Name the attribute, the hunk and what reads it in the evidence.

**Unresolved when:** Whether the attribute is emitted depends on an exporter or wrapper the
tree does not show.

## B8: Does a shipping hunk change what cloud resources get provisioned, or how: instance type or size, disk, machine image, network placement, pool membership, or scaling?

YES if a shipping hunk is in code that creates, sizes, places or
replaces cloud resources at runtime (a provisioner, a launch or create
path, a warm or standby pool, an autoscaler, a resource reconciler),
and it changes, for some request that code already handled, what is
launched or kept: the instance type or size, disk size or performance,
the machine image, the subnet, zone or security group, which pool a
resource is in or claimed from, how many are kept, or when one is
replaced or retired. Say which resource and what changes about it.

A default-off flag does not make it NO: a provisioning change is an
infrastructure change, which is never low.

NO when the hunk leaves what gets provisioned the same: a refactor,
rename or move; comments and types; removing a flag that already
serves its final value everywhere; logging, metrics or tracing.
NO for software installed or run on a resource after it exists (tool
updates, setup scripts), and for infrastructure config files, which
A4 and B3 ask about. NO when "provisioning" means something other than
cloud resources, such as account plans, seats or entitlements.

**Unresolved when:** Whether the changed code runs on a provisioning path, or what a flag
that would make the change a no-op serves in production, cannot be told
from the tree and the flag lookups.

## C1: Does at least one changed file end up inside a deployed runtime artifact? (from the changed paths)

Tests, fixtures, stories, docs and editor
config do not ship. Lockfiles ship: they pin what the build installs.
Prose the running system reads (agent prompts, skill bodies, templated
content) ships. CI workflows were already taken by B1.

**Unresolved when:** A changed path's role cannot be determined from the tree.

## C2: Does at least one shipping changed hunk alter what the program does at runtime?

NO for rename, move, extract, inline,
reformat, comment, type-only annotation, and deterministically generated
output whose inputs did not change. A dependency bump is YES (a new
version is new runtime code) unless the bumped package is dev-only.

A change to how shipped code is compiled, transpiled, linked or bundled
(compiler, transpiler or bundler settings, the options of a build rule
or macro that produces a shipped artifact, a compiler version) is YES
when it can change the code the artifact executes, even though no
source file changed: a compiler pass that rewrites or optimizes code,
a changed compile target, define, polyfill set or module resolution.
It is NO when it changes only what the artifact keeps for debugging
(symbol tables, debug info, source maps), which builds are allowed to
fail, or settings used only by a dev server, tests or an editor. A
YES records the build setting as the behavior-carrying hunk.

Record the set of behavior-carrying hunks; C3-C7 read only that set.

**Unresolved when:** A hunk's runtime effect depends on code not present in the tree.

## C3: Does every behavior-carrying hunk change only user-visible text, with no change to message ids, placeholders, markup structure, or logic?

YES if every behavior-carrying hunk replaces the content of a string
shown to people (UI copy, error message text, email copy) and the
string's id, interpolation placeholders, and surrounding markup are
unchanged. A string a program parses or matches on (an error code, an
event name, an enum value) is not copy.

**Unresolved when:** A changed string is both displayed and read by code, and the tree does
not show whether any reader depends on its content.

## C4: Is every behavior-carrying hunk reachable only when a feature flag serves a non-default variation, where the flag's code fallback and its served value in every production environment at merge are that default?

Find the flag check
that encloses each behavior-carrying hunk (added by the diff or an
ancestor gate), confirm the hunk runs only on the non-default side,
that the code's fallback is the default side, and that every
production environment serves the default side to every context at the
merge date. Code outside the flagged branch (the flag check itself, new
props, a new hook) counts only if it does nothing when the flag is off.

**Unresolved when:** The flag's production state could not be read, or the flag key is
computed at runtime.

## C5: Does every behavior-carrying hunk change only telemetry -- what the code adds or reports to logging, metrics, traces, spans or error tracking -- without changing control flow, return values, or stored data?

YES if each behavior-carrying hunk does one of these, and every other
output (what the code returns, raises, renders, sends to callers or
users, or writes) stays identical:
  - adds a log line, a metric, a span or span attribute, or (in a
    repository whose approval policy files do not forbid it, B6) an
    analytics event emission;
  - changes how our own monitoring sees something that already
    happens: whether an error is sent to error tracking (trackError,
    Sentry, RUM), its severity or log level, a log message's text or
    fields, or the tags or attributes on an existing metric or span. This holds in shared helpers too: a change
    to what a shared error or logging helper reports is telemetry,
    not shared logic.
NO for telemetry a product view displays to customers (that is B7),
for a changed or removed existing product analytics event
(exposure, usage or other events that customers' data, experiments or
billing are built from), a new required property on an existing
analytics event, a new exporter or sampling rule, telemetry that adds
a network call on the request path, or any hunk whose telemetry value
is also read by product logic (a rate limiter, a quota, a routing
decision).

**Unresolved when:** The telemetry call's cost or failure mode (does it throw, does it block)
is defined outside the tree.

## C9: Is every behavior-carrying hunk a patch-level version bump of a dependency the code already uses, with no change to how the code uses it?

YES if each behavior-carrying hunk only moves an existing dependency's
version (go.mod, package.json, requirements, pyproject, a lockfile, a
vendored submodule pin) from x.y.z to x.y.z' with the same major and
minor, and the diff changes no call site, configuration or option of
that dependency. NO for a minor or major bump, a new dependency, or a
bump that ships with code or config changes (an option newly enabled).
paths.py's deps_only hint marks diffs whose shipping files are all
manifests or lockfiles.

**Unresolved when:** The version is not semver, or the old version cannot be read from the
tree.

## C8: Does a behavior-carrying hunk change how existing logic that more than one feature relies on behaves: a validation check, a search or query parser or builder, a request or client helper, or a database write statement?

YES if the changed function or statement already exists at merge_base,
has callers in more than one feature area there (git grep its callers),
or sits on a path every request of a kind passes through, AND the hunk
changes what it accepts, rejects, returns, sends or writes for inputs it
already handled.

NO for a net-new path (a new endpoint, a function only the PR's feature
calls), for presentation-only changes to a shared UI component (layout,
styling, labels), and for logic only one feature calls (that is C7).
Count callers, not where the code lives: a function in a shared
package or component whose callers at merge_base all belong to one
feature is NO.
Count every caller at merge_base: don't set a caller aside because the
inputs it passes today never reach the changed branch. Whether the hunk
changes what the function accepts, rejects or returns is judged on the
function's inputs, not caller by caller.

**Unresolved when:** The callers are dispatched dynamically and cannot be counted from the
tree.

## C10: Does a behavior-carrying hunk change what a person can do with the product: what a page, tool or agent does, accepts, saves or returns, or how a flow works?

YES if a behavior-carrying hunk changes, for someone using the product, what
happens when they use it: an action added, removed, enabled or disabled;
what an input or form accepts or rejects; what is saved, sent, deleted or
returned; what a page, report or API shows as data (not how it is styled);
the steps, order or defaults of a flow; or what an agent does or answers.
An edit to a deployed agent's prompt or skill text changes what the agent
does, so it is YES. Any person counts, customers or staff (an admin tool,
an internal page). New behavior counts as much as a change to existing
behavior.

An opt-in setting, a preview link or a beta toggle with no feature flag is
not a flag: a change reached that way is YES.

NO when every behavior-carrying hunk is:
  - withheld by a flag that serves off in every production environment:
    the changed code only runs when that flag is on. Decide this from the
    flag's live state (the flag lookups), never from the default
    written in code: a flag that is on for any account, segment, rollout
    or rule is live, and the change reaches those people. That holds
    whether this PR adds the flag or the code already sat behind one (a
    page, route or component that renders only when the flag is on). Look
    up every gate before answering;
  - a flag removal that keeps the flag-on path, when that path already
    serves everywhere: nothing changes for anyone;
  - presentation only: markup, styling, layout, spacing, icon slots,
    labels, how a value is displayed, with the same data and the same
    actions;
  - wording only: different text in a message, reply or comment, with the
    same outcome (the same action still allowed or refused);
  - developer tooling: lint rules and baselines, dev-server, build, test
    and editor settings, CI helpers, and internal bots and scripts that
    only engineers run or read (a CI flake bot, a report script). A
    deployed agent's prompt or skill text is not developer tooling, even
    for an internal agent: it is YES;
  - code no person reaches yet: a new endpoint, function, job or response
    field that nothing calls or reads yet.
Copy-only changes, telemetry and PRs wholly behind a new default-off flag
are asked earlier (C3, C5, C4); this question still checks each hunk.

Name the person, the surface and what changes for them, and the gate you
checked.

**Unresolved when:** Whether any person can reach the changed behavior depends on a caller,
route or flag state the tree and the flag lookups do not show.

## C7: Would a failure of this change show on the surface it changes, reach only users of that surface, and be fully undone by reverting the PR?

Three facts, all must hold:
  - visible: a failure appears where the change is (a broken render, a
    wrong value on that page, an error on that endpoint), not as silent
    data corruption or a delayed effect elsewhere;
  - contained: the changed behavior runs in one feature only -- its
    callers at merge_base all belong to the feature the PR changes, and
    only that feature's users can reach it. Do not
    define "the surface" as whatever the change reaches: shared logic
    other features call was already asked at C8. A presentation-only
    change (markup, styling, icon slots, labels) counts as contained
    however many features it touches (breadth alone is not risk);
  - revertable: reverting and redeploying restores the prior behavior
    with nothing customers depend on left over: no customer data written
    in a new shape, no records customers see, no external system's state
    customers rely on. Analytics or telemetry events already sent, log
    lines, and bookkeeping fields (an updated_at, a sync enqueued) do not
    count as left over.
This is a "simple change unlikely to break customer-facing
functionality", decomposed. Its YES is marked for spot-check.

**Unresolved when:** One of the three facts depends on runtime behavior the tree does not
show.

## Approval gates

Not part of the rating. They decide whether a low change may merge on an automated approval alone, and are answered on every change.

### G1: Does the PR description satisfy the approval policy's rule on explaining why the change is needed, where a policy file covering the change has one?

Read every APPROVAL_POLICY.md at merge_base that covers a changed path
(the file in that path's directory or the nearest one above it; the
stricter rule wins). If none of them asks the description to explain
why the change is needed, answer YES.

Otherwise YES only when the description, in the author's own words,
gives a reader new to the work the problem, opportunity or decision
behind the change and its intended outcome, and that account matches
the diff. A link alone, a restatement of what the diff does, a template
left unfilled, or a reason the diff contradicts is NO. Judge the
explanation's presence and fit only: do not treat its claims as proof
that the change is correct or low risk.

**Unresolved when:** Never: the description is read as given (empty counts as missing).

### G2: Is the pull request authored by a human account? (settled by `start`)

Settled by `start` from --pr-author: a login ending in "[bot]" or
naming an automation account is a bot. A pull request a bot or agent
opened needs a human approving review whatever its rating. Without
--pr-author, a head commit authored by a bot account is NO and anything
else is unresolved.

**Unresolved when:** --pr-author was not given and the head commit's author is not a bot.

### G3: Does every approval policy file that covers a changed path allow this change to be approved automatically?

`start` lists the APPROVAL_POLICY.md files at merge_base that cover a
changed path, root file included. If there are none, it answers YES
itself.

For each listed file, read it at merge_base and apply its conditions
to this change as written. YES only when every listed file lets the
change be approved automatically. NO when any of its conditions fail,
or when it says changes are approved automatically only if they stay
inside its directory (or route elsewhere if the change also touches
other files) and the change touches files outside that directory. Name
the file and the condition in the evidence.

Two kinds of rule are asked elsewhere; skip them here: a rule on the
pull request description's explanation of why (G1), and a rule that
forbids approving a kind of change automatically (the risk question
B6, which rates the change medium).

**Unresolved when:** A condition depends on something outside the repository at merge_base
and the change.

## Ratings

- **high**: Changes the approval control itself (policy file, agent or review-bot config, CODEOWNERS, branch rules).
- **high**: Deletes, rewrites or reshapes existing persisted data; redeploying the old build does not undo it.
- **high**: Changes infrastructure or deployment configuration applied to production.
- **medium**: Changes who is authenticated, what an identity may do, session or token handling, or cryptography.
- **medium**: Changes a CI workflow definition.
- **medium**: Adds or changes a database schema or migration, additively.
- **medium**: Changes non-production infrastructure or deployment configuration.
- **medium**: Touches middleware, authentication, authorization, session or crypto code without changing access.
- **medium**: Makes a kind of change a repository approval policy file forbids approving automatically.
- **medium**: Changes telemetry a product view displays to customers (an attribute's name, value, derivation or emission).
- **medium**: Changes what cloud resources get provisioned, or how (instance type or size, disk, image, network placement, pool membership, scaling).
- **medium**: Changes how existing logic that more than one feature relies on behaves (a validation, a query parser or builder, a request helper, a database write), with no flag.
- **medium**: Changes what a person can do with the product: what a page, tool or agent does, accepts, saves or returns, or how a flow works.
- **medium**: Behavior change whose failure would be silent, spread beyond its surface, or not undone by a revert.
- **low**: Nothing ships: tests, docs, comments, stories, or other files outside the runtime.
- **low**: Ships, but changes no runtime behavior: formatting, rename, or regenerated output with unchanged inputs.
- **low**: Copy change only.
- **low**: Net-new behavior reachable only behind a flag serving its default (off) in every production environment.
- **low**: Telemetry only: what our own monitoring records or reports, nothing else.
- **low**: A patch-level bump of an existing dependency, nothing else.
- **low**: A contained change: a failure would show where it happens, the changed behavior runs in one feature only, and a revert undoes it.
