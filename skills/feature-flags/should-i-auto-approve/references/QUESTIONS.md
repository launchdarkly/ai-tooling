# The questions

What the check asks, in order. The changed paths answer some (marked);
the agent answers the rest from the code, each by its procedure.

## A1: Does the diff change the approval control itself: an approval policy file, the approval agent's configuration, review-bot rules, CODEOWNERS, or a branch protection or ruleset definition? (from the changed paths)

YES if any changed path is one of:
  APPROVAL_POLICY.md (any directory), CODEOWNERS (any location),
  .cursor/BUGBOT.md or any file under .cursor/rules/ or a
  .cursor/automations/ directory, a GitHub ruleset or branch-protection
  definition (terraform or JSON describing repository rules).
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

## C1: Does at least one changed file end up inside a deployed runtime artifact? (from the changed paths)

Tests, fixtures, stories, docs, lockfiles,
editor config do not ship. Prose the running system reads (agent
prompts, skill bodies, templated content) ships. CI workflows were
already taken by B1.

**Unresolved when:** A changed path's role cannot be determined from the tree.

## C2: Does at least one shipping changed hunk alter what the program does at runtime?

NO for rename, move, extract, inline,
reformat, comment, type-only annotation, and deterministically generated
output whose inputs did not change. A dependency bump is YES (a new
version is new runtime code) unless the bumped package is dev-only.
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

## C5: Does every behavior-carrying hunk only add logging, metrics, traces, or spans, without changing control flow, return values, or stored data?

YES if each behavior-carrying hunk adds a log line, a metric, a span or
span attribute, or an analytics event emission, and removing it would
leave every other output identical. A changed or removed existing
event, a new required property on an existing event, a new exporter or
sampling rule, or telemetry that adds a network call on the request
path is NO.

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
manifests.

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

**Unresolved when:** The callers are dispatched dynamically and cannot be counted from the
tree.

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

## Ratings

- **high**: Changes the approval control itself (policy file, agent or review-bot config, CODEOWNERS, branch rules).
- **high**: Deletes, rewrites or reshapes existing persisted data; redeploying the old build does not undo it.
- **high**: Changes infrastructure or deployment configuration applied to production.
- **medium**: Changes who is authenticated, what an identity may do, session or token handling, or cryptography.
- **medium**: Changes a CI workflow definition.
- **medium**: Adds or changes a database schema or migration, additively.
- **medium**: Changes non-production infrastructure or deployment configuration.
- **medium**: Touches middleware, authentication, authorization, session or crypto code without changing access.
- **medium**: Changes how existing logic that more than one feature relies on behaves (a validation, a query parser or builder, a request helper, a database write), with no flag.
- **medium**: Behavior change whose failure would be silent, spread beyond its surface, or not undone by a revert.
- **low**: Nothing ships: tests, docs, comments, stories, or other files outside the runtime.
- **low**: Ships, but changes no runtime behavior: formatting, rename, or regenerated output with unchanged inputs.
- **low**: Copy change only.
- **low**: Net-new behavior reachable only behind a flag serving its default (off) in every production environment.
- **low**: Additive telemetry only.
- **low**: A patch-level bump of an existing dependency, nothing else.
- **low**: A contained change: a failure would show where it happens, the changed behavior runs in one feature only, and a revert undoes it.
