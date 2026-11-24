"""The gate search: check an agent's claimed flag gates, and turn the ones that
hold into caller-gate entries.

Caller coverage is the second kind of claim. One gate is one flag and one
chain, so it can't say "this changed function has three callers: two behind
one flag, one behind another, and the only other reference is a test". A
`covered_units` claim says exactly that about one changed unit (a function,
method, component, hook, endpoint or resolver), and `verify_coverage` checks
it: every quoted line at head, each gated caller's chain like a gate, and --
the part that makes it a claim about ALL callers -- a search of head for the
unit's name (and route) whose every hit in shipping code must be a listed
caller. A name another symbol also uses makes the claim fail that search: the
safe direction, since a dropped claim only leaves the unit uncovered.

A caller may be in a CLIENT repository (`"repo": "<client name>"`, one of
the run's `clients`: a backend resolver or route whose only callers are
frontend screens, or the reverse). Its lines and its gate's chain are checked
in that checkout at its pinned revision (main as of the change's base, as the
consumer search reads it), its gate key must exist there, and that client is
searched for every other use of the unit's external name (`client_search`),
with the generated-code and GraphQL-operation rules described there. Its
flag is read from the client's LaunchDarkly project (`client_key_project`)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

EVALUATES = {"evaluates"}
REACHES = {"renders", "calls", "styles", "registers", "changed", "writes"}
REACHED_BY = ("gated", "off", "test", "none")
MAX_REFERENCES = 200  # hits of a unit's name past which no claim can list them all

# Paths that are not customer-reachable code, when the repository profile
# doesn't say otherwise: tests, stories, fixtures, mocks, docs.
TEST_LIKE = re.compile(
    r"(_test\.go$|_mock\.go$|(^|/)mock_[^/]*\.go$|[.-]test\.[^/]+$|\.spec\.[^/]+$|\.stories\.[^/]+$"
    r"|\.story\.[^/]+$|\.snap$|(^|/)test_[^/]*\.py$|_test\.py$"
    r"|(^|/)(__tests__|__mocks__|__fixtures__|tests?|testdata|testutils?|fixtures?|mocks?|e2e|cypress"
    r"|playwright|\.storybook|stories)/)")
# Docs, and ownership metadata: CODEOWNERS, and the folders coding agents read
# their instructions and ownership maps from (`.agents/ux-surface-owners.yml`
# names components). Nothing ships from them; a unit's name there is a path or
# a label, never a call.
DOC_LIKE = re.compile(r"(\.(md|mdx|rst|adoc)$|(^|/)docs?/|(^|/)\.(agents|claude|cursor|codex|windsurf)/"
                      r"|(^|/)CODEOWNERS$)")
# Stylesheets: a unit's name there is a class name, never a call.
STYLESHEET = re.compile(r"\.(css|scss|sass|less|styl|pcss)$")
IDENT = re.compile(r"^[A-Za-z_$][\w$]*$")
COMMENT = re.compile(r"^\s*(//|#|\*|/\*|<!--|\{/\*)")
IMPORT_LINE = re.compile(r"^\s*(import\b|from\s+\S+\s+import\b|(export\s+)?(const|let|var)\s+.*=\s*require\()")
REEXPORT_LINE = re.compile(r"^\s*export\s+(type\s+)?(\*|\{)")
IMPORT_OPEN = re.compile(r"^\s*(import\s+(type\s+)?([\w$]+\s*,\s*)?\{|from\s+\S+\s+import\s*\()\s*$")
REEXPORT_OPEN = re.compile(r"^\s*export\s+(type\s+)?\{\s*$")
LIST_ITEM = re.compile(r"^\s*(type\s+)?[\w$]+(\s+as\s+[\w$]+)?\s*,?\s*$")
# Generated code, when the repository profile doesn't say: codegen output
# directories and the usual generated-file suffixes.
GENERATED_LIKE = re.compile(r"((^|/)(generated|__generated__)/|\.generated\.[^/]+$|\.gen\.[^/]+$|_gen\.go$"
                            r"|\.pb\.go$|_pb2(_grpc)?\.py$)")
# A GraphQL operation or fragment: its header line in a document file, or in
# a gql`...` template (generated hooks, inline documents).
GQL_DOC = re.compile(r"\.(gql|graphql|graphqls)$")
OP_HEADER = re.compile(r"^\s*(query|mutation|subscription|fragment)\s+([A-Za-z_]\w*)")
# What graphql-codegen (Apollo) generates for an operation: the hooks and
# document a client's code calls it through. A fragment is used by spreading
# it (`...Name`) or interpolating its document.
OP_HOOKS = ("Query", "LazyQuery", "SuspenseQuery", "Mutation", "Subscription")
DEFINES = r"\b(function|const|let|var|class|type|interface|enum|def|func)\s+{}\b"
RELATIVE_IMPORT = re.compile(r"""(?:from\s*|import\s*\(\s*|require\s*\(\s*|import\s+)['"](\.{1,2}/[^'"]+)['"]""")


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _lines(repo_path: str, head: str, path: str, files: dict) -> list[str] | None:
    if path not in files:
        p = subprocess.run(["git", "-C", str(repo_path), "show", f"{head}:{path}"],
                           capture_output=True, text=True, errors="replace")
        files[path] = p.stdout.splitlines() if p.returncode == 0 else None
    return files[path]


def _check_line(repo_path: str, head: str, link: dict, files: dict) -> str | None:
    """None when `link` ({path, line, text}) is that line at head, else why not."""
    path, line = (link or {}).get("path") or "", (link or {}).get("line")
    L = _lines(repo_path, head, path, files)
    if L is None:
        return f"{path} does not exist at head"
    if not isinstance(line, int) or not 0 < line <= len(L):
        return f"{path}:{line} is not a line at head"
    got, want = _norm(L[line - 1]), _norm(link.get("text"))
    if not want or (want not in got and got not in want):
        return f"{path}:{line} reads {got[:80]!r}, not {want[:80]!r}"
    return None


def _check_ref(repo_path: str, head: str, link, files: dict) -> str | None:
    """_check_line for a caller-coverage line, which must name a file."""
    if not isinstance(link, dict) or not link.get("path"):
        return "a quoted line has no path"
    return _check_line(repo_path, head, link, files)


def verify(repo_path: str, head: str, gate: dict, files: dict) -> str | None:
    """None when every link of `gate` checks out at `head`, else why not.
    `files` caches path -> lines (None when absent) across gates."""
    key = gate.get("key") or ""
    if not key or subprocess.run(["git", "-C", str(repo_path), "grep", "-q", "-F", key, head],
                                 capture_output=True).returncode != 0:
        return f"key {key!r} not found at head"
    chain = gate.get("chain") or []
    roles = {str(c.get("role")) for c in chain}
    if not roles & EVALUATES or not roles & REACHES:
        return f"the chain needs a line that evaluates the flag and one that reaches the changed code (has {sorted(roles)})"
    for c in chain:
        why = _check_line(repo_path, head, c, files)
        if why:
            return why
    return None


SITE_NEAR = 2  # a gate line this close to a check the evidence shows is that check (profile_check.NEAR)


def entries(gate: dict, changed_paths: set[str], key_at_base: bool,
            sited: dict[str, set[int]] | None = None) -> list[dict]:
    """One `searched` caller-gate entry per file of the chain that isn't
    changed (a changed file's lines are citable already, and the evidence
    shows its flag checks), and per changed file where the gate evaluates or
    decides at a line the evidence shows no check of this flag near: one
    through a helper the profile doesn't recognize (GATES.md's LEADS), so the
    gate's lines reach the questions marked as such. Line by line, like the
    profile check's gaps: a recognized check of the same key elsewhere in the
    file doesn't hide it. `sited`: changed path -> the lines where the
    evidence shows this flag's check; None, every changed file is skipped."""
    by_path: dict[str, list[dict]] = {}
    for link in gate.get("chain") or []:
        by_path.setdefault(link["path"], []).append(link)
    out = []
    for path, links in by_path.items():
        if path in changed_paths:
            seen = (sited or {}).get(path, set())
            unseen = [l for l in links if l.get("role") in ("evaluates", "decides") and isinstance(l.get("line"), int)
                      and not any(abs(l["line"] - s) <= SITE_NEAR for s in seen)]
            if sited is None or not unseen:
                continue
        out.append({"kind": "searched", "path": path, "how": gate.get("how") or "other",
                    "why": gate.get("why") or "", "function": "", "callee": "", "chain": [],
                    "call_line": links[-1]["line"], "keys": [gate["key"]],
                    "keys_at_merge_base": [gate["key"]] if key_at_base else [],
                    "gate_lines": [l["line"] for l in links if l.get("role") in ("evaluates", "decides")],
                    "lines": sorted({(l["line"], l["text"]) for l in links}),
                    **({"in_diff": True} if path in changed_paths else {})})
    return out


def key_at(repo_path: str, rev: str, key: str) -> bool:
    return subprocess.run(["git", "-C", str(repo_path), "grep", "-q", "-F", key, rev],
                          capture_output=True).returncode == 0


# ---------------------------------------------------------------------------
# Caller coverage
# ---------------------------------------------------------------------------

def not_shipping_fn(profile=None):
    """path -> True when it is a test, story, fixture, mock or doc file: the
    profile's own test/docs/build_ci roles (its ships_anyway wins), then the
    generic patterns above."""
    from .sources import _match
    roles = (getattr(profile, "data", None) or {}).get("path_roles", {}) if profile is not None else {}

    def f(path: str) -> bool:
        if profile is not None:
            if any(_match(path, p) for p in roles.get("ships_anyway", [])):
                return False
            if profile.role_of(path) in ("test", "docs", "build_ci"):
                return True
        return bool(TEST_LIKE.search(path) or DOC_LIKE.search(path))
    return f


def _names(text: str, name: str) -> bool:
    if IDENT.match(name):
        return re.search(rf"(?<![\w$]){re.escape(name)}(?![\w$])", text or "") is not None
    return name in (text or "")


def _import_kind(lines: list[str], i: int, name: str) -> str | None:
    """Is line i (0-based) part of an import or re-export statement?
    "import" (an import of the name, perhaps aliased), "reexport" (the same
    name exported on), "aliased-reexport", or None for any other line."""
    s = lines[i]
    aliased = re.search(rf"(?<![\w$]){re.escape(name)}\s+as\s+[\w$]+", s) is not None
    if IMPORT_LINE.match(s):
        return "import"
    if REEXPORT_LINE.match(s):
        return "aliased-reexport" if aliased else "reexport"
    if not LIST_ITEM.match(s):
        return None
    for j in range(i - 1, max(-1, i - 200), -1):
        t = lines[j]
        if IMPORT_OPEN.match(t):
            return "import"
        if REEXPORT_OPEN.match(t):
            return "aliased-reexport" if aliased else "reexport"
        if not LIST_ITEM.match(t):
            return None
    return None


def _grep(repo_path: str, head: str, pattern: str, word: bool) -> list[tuple[str, int, str]]:
    args = ["git", "-C", str(repo_path), "grep", "-n", "-I", "-F"] + (["-w"] if word else []) \
        + ["-e", pattern, head, "--"]
    p = subprocess.run(args, capture_output=True, text=True, errors="replace")
    if p.returncode not in (0, 1):  # 1 is "no match"; anything else, the search itself failed
        raise RuntimeError(f"git grep failed: {p.stderr.strip()[:200]}")
    out = p.stdout
    hits = []
    for ln in out.splitlines():
        rest = ln[len(head) + 1:] if ln.startswith(head + ":") else ln
        m = re.match(r"^(.*?):(\d+):(.*)$", rest)
        if m:
            hits.append((m.group(1), int(m.group(2)), m.group(3)))
    return hits


def _importers(repo_path: str, head: str, unit_path: str) -> list[tuple[str, int, str]]:
    """Lines that import the unit's module (for a default export, which an
    importer may name anything)."""
    base = unit_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if base == "index" and "/" in unit_path:
        base = unit_path.rsplit("/", 2)[-2]
    rx = re.compile(r"""(from\s*|import\s*\(\s*|require\s*\(\s*|import\s+)['"]([^'"]*/)?"""
                    + re.escape(base) + r"""(\.[\w]+)?['"]""")
    return [h for h in _grep(repo_path, head, base, False) if rx.search(h[2]) and h[0] != unit_path]


def generated_fn(profile=None):
    """path -> True when it is generated code: the profile's `generated`
    role, else the generic codegen patterns (GENERATED_LIKE)."""
    if profile is not None:
        return lambda path: profile.role_of(path) == "generated"
    return lambda path: bool(GENERATED_LIKE.search(path))


# ---------------------------------------------------------------------------
# Client repositories
# ---------------------------------------------------------------------------

def client_profile(client: dict):
    """The repository profile for a client checkout, or None: the one the
    client names, the one its origin matches (detect_profile), or a profile
    named like the client."""
    from . import detect_profile
    from .sources import Profile
    names = [client.get("profile")]
    try:
        names.append(detect_profile.detect(str(client["path"])))
    except (SystemExit, Exception):  # noqa: BLE001 -- no origin, or no profile declares it
        pass
    names.append(client.get("name"))
    for n in dict.fromkeys(x for x in names if x):
        try:
            return Profile.load(n)
        except (SystemExit, Exception):  # noqa: BLE001
            continue
    return None


def client_repos(clients: list[dict] | None) -> dict:
    """{name: client} for the run's client checkouts (man["clients"]: name,
    path, rev pinned at start), each with its profile and the functions
    caller coverage classifies its paths by."""
    out = {}
    for c in clients or []:
        if not (isinstance(c, dict) and c.get("name") and c.get("path") and c.get("rev")):
            continue
        prof = client_profile(c)
        out[c["name"]] = {"name": c["name"], "path": str(c["path"]), "rev": c["rev"], "profile": prof,
                          "not_shipping": not_shipping_fn(prof), "generated": generated_fn(prof)}
    return out


def client_key_project(client: dict, key: str) -> list:
    """."""
    prof = client.get("profile")
    if prof is None:
        return [None, {}]
    decls = {ad["file"]: ad for ad in (prof.data.get("evaluation") or {}).get("alias_declarations") or []
             if ad.get("ld_project")}
    if decls:
        from .mechanical import flag_aliases
        from .sources import Repo
        for k, f, _, _ in flag_aliases(Repo(Path(client["path"])), prof, client["rev"]).values():
            if k == key and f in decls:
                return [decls[f]["ld_project"], dict(decls[f].get("ld_environments") or {})]
    return [prof.ld.get("project"), {}]


def _caller_repo(c: dict) -> str | None:
    r = c.get("repo") if isinstance(c, dict) else None
    return None if r in (None, "", "self") else str(r)


def _enclosing_operation(lines: list[str], i: int, path: str) -> tuple[str, str] | None:
    """(kind, name) of the GraphQL operation or fragment line i (0-based) is
    in, or None: the nearest header above it in a .gql/.graphql file, or in a
    gql`...` template (the header's line or the one above holds the opening
    backtick, and no backtick closes a template between them)."""
    doc = bool(GQL_DOC.search(path))
    for j in range(i, max(-1, i - 3000), -1):
        m = OP_HEADER.match(lines[j])
        if m and (doc or "`" in lines[j] or (j > 0 and "`" in lines[j - 1])):
            return m.group(1), m.group(2)
        if j < i and "`" in lines[j] and not doc:
            return None
    return None


def _check_client_gate(cl: dict, c: dict, files: dict) -> str | None:
    """A client caller's gate, checked like a gate in the client at its
    pinned revision; its chain's links are all in that client."""
    g = c.get("gate") or {}
    for link in g.get("chain") or []:
        if _caller_repo(link) not in (None, c["repo"]):
            return f"its gate chain has a link in {link.get('repo')!r}, not {c['repo']}"
    why = verify(cl["path"], cl["rev"], g, files)
    if why:
        return f"gate {g.get('key')!r}: {why.replace('at head', 'at its pinned revision')}"
    if not any(l.get("path") == c["path"] and l.get("line") == c["line"]
               and l.get("role") in REACHES for l in g.get("chain") or []):
        return "its gate chain does not end at the caller line"
    return None


def _check_own_gate(repo_path: str, head: str, c: dict, files: dict) -> str | None:
    """A caller's (or writer's) gate in this repository: verified like a gate,
    and its chain ends at that caller's line."""
    g = c.get("gate") or {}
    why = verify(repo_path, head, g, files)
    if why:
        return f"gate {g.get('key')!r}: {why}"
    if not any(l.get("path") == c["path"] and l.get("line") == c["line"]
               and l.get("role") in REACHES for l in g.get("chain") or []):
        return "its gate chain does not end at the caller line"
    return None


def _check_caller(repo_path: str, rev: str, c: dict, files: dict, not_shipping, where: str,
                  gate_check) -> str | None:
    """One listed caller's quoted line and how it says it is reached."""
    why = _check_ref(repo_path, rev, c, files)
    if why:
        return f"caller {where}: {why}"
    rb = c.get("reached_by")
    if rb not in REACHED_BY:
        return f"caller {where}: reached_by is {rb!r}, not one of {', '.join(REACHED_BY)}"
    if rb == "gated":
        why = gate_check()
        if why:
            return f"caller {where}: {why}"
    elif rb == "off":
        if not _norm(c.get("off_because")):
            return f"caller {where}: off, but no off_because"
        why = _check_ref(repo_path, rev, c.get("off_line") or {}, files)
        if why:
            return f"caller {where}: off_line: {why}"
    elif rb == "test":
        if not not_shipping(c["path"]):
            return f"caller {where}: marked test, but {c['path']} is shipping code"
    elif not _norm(c.get("note")):
        return f"caller {where}: reached_by none, but no note saying why nothing reaches it"
    return None


def verify_coverage(repo_path: str, head: str, claim: dict, files: dict,
                    changed_paths: set[str] | None = None, not_shipping=None,
                    clients: dict | None = None, generated=None) -> str | None:
    """None when a caller-coverage claim checks out at `head`, else why not.

    The claim: {"unit": {path, line, text, name, route?, external?},
    "declared_at": [{repo?, path, line, text}], "callers": [{repo?, path,
    line, text, reached_by, gate?, off_because?, off_line?, note?}], "why"}.
    Checked: every quoted line matches head; the unit is in shipping code, in
    a changed file, and its line names it; each `gated` caller's gate
    verifies like a gate and its chain includes the caller line; each `off`
    caller's off_line exists; each `test` caller is in a test file; and every
    reference to the unit's name (and route) in shipping code at head is the
    unit's own line, a `declared_at` line, an import or same-name re-export of
    it (its file then holds a listed caller), a comment, or a listed caller.

    A caller or declaration with `repo` set is in that client repository
    (`clients`, client_repos()): checked there at its pinned revision, and
    that client is searched for every other use (client_search). With a
    client caller listed, this repository's generated code that serves the
    unit's external name (a GraphQL executor, a generated router: a generated
    file that also names `external` or the route) is how those callers reach
    it, and needs no listing; `generated` classifies this repository's
    paths (generated_fn)."""
    not_shipping = not_shipping or not_shipping_fn()
    generated = generated or generated_fn()
    clients = clients or {}
    unit = claim.get("unit") or {}
    name, route = _norm(unit.get("name")), _norm(unit.get("route"))
    if not name:
        return "the unit has no name"
    if _caller_repo(unit):
        return "the unit must be in this repository; only callers may be in a client repository"
    why = _check_ref(repo_path, head, unit, files)
    if why:
        return f"unit: {why}"
    upath, uline = unit["path"], unit["line"]
    if not_shipping(upath):
        return f"unit {upath}:{uline} is not in shipping code"
    if changed_paths is not None and upath not in changed_paths:
        return f"unit {upath}:{uline} is not in a file the diff changes"
    if IDENT.match(name) and not _names(_lines(repo_path, head, upath, files)[uline - 1], name):
        return f"unit {upath}:{uline} does not name {name!r}"
    all_declared = claim.get("declared_at") or []
    if not isinstance(all_declared, list) or not all(isinstance(d, dict) for d in all_declared):
        return "declared_at is not a list of lines"
    for d in all_declared:
        r = _caller_repo(d)
        if r and r not in clients:
            return f"declared_at: repo {r!r} is not a client checkout of this run"
    declared = [d for d in all_declared if not _caller_repo(d)]
    for d in declared:
        why = _check_ref(repo_path, head, d, files)
        if why:
            return f"declared_at: {why}"
        text = _lines(repo_path, head, d["path"], files)[d["line"] - 1]
        ext = str((claim.get("unit") or {}).get("external") or "").strip()
        squash = lambda x: re.sub(r"[_\-]", "", x).lower()  # gqlgen: field_name <-> FieldName
        if not (_names(text, name) or (ext and _names(text, ext)) or (route and route in text)
                or any(n and squash(n) in squash(text) for n in (name, ext))):
            return f"declared_at {d['path']}:{d['line']} names neither {name!r}, its external name, nor the route"
    all_callers = claim.get("callers")
    if not isinstance(all_callers, list) or not all(isinstance(c, dict) for c in all_callers):
        return "no callers list"
    callers = [c for c in all_callers if not _caller_repo(c)]
    by_client: dict[str, list[dict]] = {}
    for c in all_callers:
        r = _caller_repo(c)
        if r:
            if r not in clients:
                return (f"caller {r}:{c.get('path')}:{c.get('line')}: repo {r!r} is not a client "
                        f"checkout of this run")
            by_client.setdefault(r, []).append(c)
    for d in all_declared:
        r = _caller_repo(d)
        if r and r not in by_client:
            return f"declared_at {r}:{d.get('path')}:{d.get('line')}: no caller is listed in {r}"
    for c in callers:
        where = f"{c.get('path')}:{c.get('line')}"
        why = _check_caller(repo_path, head, c, files, not_shipping, where,
                            lambda c=c: _check_own_gate(repo_path, head, c, files))
        if why:
            return why
    for r, cs in by_client.items():
        cl = clients[r]
        cfiles = files.setdefault(("client", r), {})
        for c in cs:
            why = _check_caller(cl["path"], cl["rev"], c, cfiles, cl["not_shipping"], f"{r}:{c.get('path')}:{c.get('line')}",
                                lambda c=c: _check_client_gate(cl, c, cfiles))
            if why:
                return why.replace("at head", "at its pinned revision")

    # Completeness: every reference at head is accounted for.
    listed = {(c["path"], c["line"]) for c in callers}
    known = listed | {(upath, uline)} | {(d["path"], d["line"]) for d in declared}
    caller_files = {c["path"] for c in callers}
    try:
        hits = _grep(repo_path, head, name, bool(IDENT.match(name)))
        if route:
            hits += _grep(repo_path, head, route, False)
        importers = _importers(repo_path, head, upath)
    except RuntimeError as e:
        return f"the search for other callers failed: {e}"
    shipping = sorted({h for h in hits if not not_shipping(h[0])})
    if len(shipping) > MAX_REFERENCES:
        return f"{len(shipping)} references to {name!r} at head; too many to list"
    default_export = bool(re.search(r"\bexport\s+default\b", unit.get("text") or ""))
    external = _norm(unit.get("external")) or name
    serving: dict[str, bool] = {}

    def serves_external(path: str) -> bool:
        # This repository's generated code that names the external name or
        # route: the layer through which the listed client callers reach it.
        if path not in serving:
            L = _lines(repo_path, head, path, files) or []
            serving[path] = any(_names(t, external) or (route and route in t) for t in L)
        return serving[path]
    for path, line, text in shipping:
        if (path, line) in known or COMMENT.match(text) or STYLESHEET.search(path):
            continue
        if by_client and generated(path) and serves_external(path):
            continue
        if re.match(rf"^\s*export\s+default\s+{re.escape(name)}\b", text):
            default_export = True
        L = _lines(repo_path, head, path, files) or []
        kind = _import_kind(L, line - 1, name) if 0 < line <= len(L) and IDENT.match(name) else None
        if kind == "reexport":
            continue
        if kind == "import":
            if not _names(re.sub(r"""(['"`]).*?\1""", "", text), name):
                continue  # only the module path says it (`./Name.module.css`): another module's import
            if path not in caller_files:
                return f"unlisted caller {path}:{line} (imports {name} with no caller listed in that file)"
            continue
        return f"unlisted caller {path}:{line}"
    if default_export:
        for path, line, _ in importers:
            if not not_shipping(path) and path not in caller_files:
                return f"unlisted caller {path}:{line} (imports the default export with no caller listed in that file)"
    for r, cs in by_client.items():
        why = client_search(clients[r], unit, cs, [d for d in all_declared if _caller_repo(d) == r],
                            files.setdefault(("client", r), {}))
        if why:
            return why
    return None


def client_search(cl: dict, unit: dict, callers: list[dict], declared: list[dict], files: dict) -> str | None:
    """None when every use of the unit in client `cl` at its pinned revision
    is accounted for, else why not. The unit's external name (`external`,
    else `name`: a GraphQL field or operation, an RPC method; word-bounded)
    and its `route` (a plain string) are searched in the client, and every
    hit in its shipping code (by the client profile's roles) must be:

      - a listed caller or a `declared_at` line in that client, or a comment;
      - an import (its file holds a listed caller) or a same-name re-export;
      - inside a GraphQL operation or fragment (a .gql/.graphql document, or a
        gql`...` template, generated or not). The operation is then followed
        to what code calls it through: graphql-codegen's `use<Op>Query`,
        `use<Op>LazyQuery`, `use<Op>SuspenseQuery`, `use<Op>Mutation`,
        `use<Op>Subscription` and `<Op>Document` (a fragment: its
        `<Op>FragmentDoc` and every `...<Op>` spread, whose operations are
        followed in turn). Each of their uses outside generated code must be
        a listed caller, an import in a file holding one, or a comment. An
        operation none of those names exists for is dropped as unfollowable;
        one whose names exist only in generated code is called by nothing;
      - in generated code (the client profile's `generated` role, else
        GENERATED_LIKE), outside an operation: a type or a hook definition.
        It counts only when a listed caller uses that generated file: the
        file defines a hook or document of an operation a listed caller
        calls, or a function or component a listed caller's line calls (a
        generated REST or RPC client; that name's uses are then searched
        like an operation's), or it is imported (by a relative path) by a
        generated file that is used;
      - for a GraphQL field (the name occurs in an operation), a mention in a
        file holding a listed caller: that file reading the response.

    Any other hit is an unlisted client caller, and drops the claim. So does a
    client with no use of the name at all (its listed callers can't reach the
    unit by it), and a listed non-test caller whose line is none of the uses
    found."""
    R, path0, rev = cl["name"], cl["path"], cl["rev"]
    ns, gen = cl["not_shipping"], cl["generated"]
    external = _norm(unit.get("external")) or _norm(unit.get("name"))
    route = _norm(unit.get("route"))
    listed = {(c["path"], c["line"]) for c in callers}
    callers_at = {c["path"] for c in callers if c.get("reached_by") != "test"}
    decl = {(d["path"], d["line"]) for d in declared}
    found: set[tuple[str, int]] = set()

    def lines_of(p):
        return _lines(path0, rev, p, files) or []

    def grep(term, word):
        hs = sorted({h for h in _grep(path0, rev, term, word) if not ns(h[0])})
        if len(hs) > MAX_REFERENCES:
            raise RuntimeError(f"{len(hs)} references to {term!r} in {R}; too many to list")
        return hs

    for d in declared:
        why = _check_ref(path0, rev, d, files)
        if why:
            return f"declared_at {R}:{d['path']}:{d['line']}: {why.replace('at head', 'at its pinned revision')}"
    try:
        hits = (grep(external, bool(IDENT.match(external))) if external else []) + (grep(route, False) if route else [])
    except RuntimeError as e:
        return f"the search of {R} for other callers failed: {e}"
    if not hits:
        return (f"{R} has no use of {external or route!r} at {rev[:12]}: its listed callers can't reach "
                f"the unit by that name")
    ops: dict[str, str] = {}
    gen_hits: dict[str, int] = {}
    loose: list[tuple[str, int]] = []
    for path, line, text in hits:
        found.add((path, line))
        if (path, line) in listed or (path, line) in decl or COMMENT.match(text):
            continue
        L = lines_of(path)
        op = _enclosing_operation(L, line - 1, path) if 0 < line <= len(L) else None
        if op:
            ops.setdefault(op[1], op[0])
            continue
        if gen(path):
            gen_hits.setdefault(path, line)
            continue
        kind = _import_kind(L, line - 1, external) if 0 < line <= len(L) and IDENT.match(external) else None
        if kind == "reexport":
            continue
        if kind == "import":
            if path not in callers_at:
                return f"unlisted client caller {R}:{path}:{line} (imports {external} with no caller listed in that file)"
            continue
        loose.append((path, line))
    # A GraphQL field is only ever requested through an operation, and every
    # operation is followed below: a mention elsewhere that reads it (as a
    # property, `x?.name`, `T['name']`, `name: ...`) reads a response.
    for path, line in loose:
        if not (ops and _reads_field(lines_of(path)[line - 1], external)):
            return f"unlisted client caller {R}:{path}:{line}"

    # Follow each operation, and each identifier a listed caller names that a
    # generated file with a hit defines, to the code that uses it.
    gen_of: dict[str, set[str]] = {}   # entry -> generated files defining or holding it
    called: set[str] = set()           # entries a listed caller uses
    try:
        queue, seen = list(ops), set(ops)
        while queue:
            op = queue.pop(0)
            kind = ops[op]
            names = ([f"{op}FragmentDoc", op] if kind == "fragment"
                     else [f"use{op}{s}" for s in OP_HOOKS] + [f"{op}Document"])
            any_hit = False
            for nm in names:
                for path, line, text in grep(nm, True):
                    any_hit = True
                    found.add((path, line))
                    L = lines_of(path)
                    inner = _enclosing_operation(L, line - 1, path) if 0 < line <= len(L) else None
                    if inner:
                        if inner[1] != op and inner[1] not in seen:
                            ops[inner[1]] = inner[0]
                            seen.add(inner[1])
                            queue.append(inner[1])
                        continue
                    if gen(path):
                        gen_of.setdefault(op, set()).add(path)
                        continue
                    why = _entry_use(R, path, line, text, nm, L, listed, decl, callers_at, f"uses operation {op}")
                    if why:
                        return why
                    if (path, line) in listed:
                        called.add(op)
            if not any_hit:
                return (f"can't tell how code in {R} reaches GraphQL {kind} {op}: nothing names "
                        f"{', '.join(names[:2])} or the other generated names")
        used = set().union(*(gen_of.get(op, set()) for op in called)) if called else set()
        _imported_closure(used, gen_hits, lines_of)
        # A generated file defining a function or component a listed caller
        # calls (a generated REST or RPC client): used, and that name's uses
        # are searched too.
        calls = {t for c in callers if c.get("reached_by") != "test"
                 for t in re.findall(r"([A-Za-z_$][\w$]{2,})\s*(?=\(|<[\w\s,.]*>\s*\()", c.get("text") or "")}
        calls |= {t for c in callers if c.get("reached_by") != "test"
                  for t in re.findall(r"<([A-Z][\w$]{2,})\b", c.get("text") or "")}
        for gpath in [p for p in gen_hits if p not in used]:
            G = "\n".join(lines_of(gpath))
            for tok in sorted(calls):
                if not re.search(DEFINES.format(re.escape(tok)), G):
                    continue
                used.add(gpath)
                for path, line, text in grep(tok, True):
                    found.add((path, line))
                    if gen(path):
                        continue
                    why = _entry_use(R, path, line, text, tok, lines_of(path), listed, decl, callers_at,
                                     f"uses {tok}, which {gpath} generates")
                    if why:
                        return why
        _imported_closure(used, gen_hits, lines_of)
    except RuntimeError as e:
        return f"the search of {R} for other callers failed: {e}"
    for path, line in gen_hits.items():
        if path not in used:
            return f"unlisted client caller {R}:{path}:{line} (generated code no listed caller uses)"
    for c in callers:
        if c.get("reached_by") != "test" and (c["path"], c["line"]) not in found:
            return (f"client caller {R}:{c['path']}:{c['line']} is none of the uses of {external or route!r} "
                    f"found in {R} (the name, the route, or an operation's generated hook or document)")
    for d in declared:
        if (d["path"], d["line"]) not in found:
            return f"declared_at {R}:{d['path']}:{d['line']} names neither {external!r} nor the route"
    return None


def _reads_field(text: str, name: str) -> bool:
    """Every mention of `name` in `text` reads a property: `.name`,
    `?.name`, `['name']`, or `name:` / `name?:` (an object key or a type
    member), not a request (`name(...) {` / `name {` in a document)."""
    if not IDENT.match(name):
        return False
    n = re.escape(name)
    occ = list(re.finditer(rf"(?<![\w$]){n}(?![\w$])", text))
    return bool(occ) and all(
        re.search(r"(\?\.|\.)\s*$|\[\s*['\"`]$", text[:m.start()])
        or re.match(r"['\"`]?\s*\??\s*:(?!:)", text[m.end():])
        for m in occ)


def _entry_use(R, path, line, text, nm, L, listed, decl, callers_at, what) -> str | None:
    """A use, outside generated code, of an operation's hook or document (or
    a generated client's function): None when it is accounted for."""
    if (path, line) in listed or (path, line) in decl or COMMENT.match(text):
        return None
    kind = _import_kind(L, line - 1, nm) if 0 < line <= len(L) else None
    if kind == "reexport":
        return None
    if kind == "import":
        if path in callers_at:
            return None
        return f"unlisted client caller {R}:{path}:{line} (imports {nm} with no caller listed in that file)"
    return f"unlisted client caller {R}:{path}:{line} ({what})"


def _imported_closure(used: set[str], gen_hits: dict, lines_of) -> None:
    """Add to `used` the generated files with a hit that a used generated
    file imports by a relative path (hooks -> operation types -> schema
    types), until nothing more is added."""
    stems = {re.sub(r"\.[^./]+$", "", p): p for p in gen_hits}
    grew = True
    while grew:
        grew = False
        for u in list(used):
            base = u.rsplit("/", 1)[0] if "/" in u else ""
            for m in RELATIVE_IMPORT.finditer("\n".join(lines_of(u))):
                tgt = _join(base, m.group(1))
                for cand in (tgt, re.sub(r"\.[^./]+$", "", tgt), tgt + "/index"):
                    q = stems.get(cand)
                    if q and q not in used:
                        used.add(q)
                        grew = True


def _join(base: str, rel: str) -> str:
    parts = [p for p in base.split("/") if p]
    for seg in rel.split("/"):
        if seg == "..":
            parts = parts[:-1]
        elif seg not in (".", ""):
            parts.append(seg)
    return "/".join(parts)


def coverage_entries(claim: dict, changed_paths: set[str], key_at_base, clients: dict | None = None) -> list[dict]:
    """A verified caller coverage as caller-gate entries: one `coverage`
    entry holding the claim (rendered in P6's and P12's questions), plus
    `covered` entries for its lines outside the diff -- one per gated
    caller's chain file, carrying that flag's key and its evaluate/decide
    lines (so a citation of them names the key, as for a gate), and one per
    other file for the caller, off and declaration lines (so they're
    citable). `key_at_base(key)` says whether a key existed at merge_base.

    A client caller's lines are entries at `<client>:<path>` (citable by that
    name, never mistaken for this repository's file), its key "existed at
    merge_base" when it is in the client at its pinned revision, and every
    entry naming a client key carries `key_projects` {key: [project,
    env_map]}: the LaunchDarkly project it is read from (client_key_project),
    which apply_enclosure gives the LaunchDarkly client."""
    clients = clients or {}
    unit = claim["unit"]
    ref = f"{unit['path']}:{unit['line']}"

    def at(x):
        r = _caller_repo(x)
        return (f"{r}:{x['path']}" if r else x["path"]), r

    gated = [c for c in claim["callers"] if c["reached_by"] == "gated"]
    keys = list(dict.fromkeys(c["gate"]["key"] for c in gated))
    client_keys = {c["gate"]["key"]: _caller_repo(c) for c in gated if _caller_repo(c)}
    own_keys = {c["gate"]["key"] for c in gated if not _caller_repo(c)}
    at_base = [k for k in keys if (k in own_keys and key_at_base(k))
               or (k in client_keys and k not in own_keys and client_keys[k] in clients
                   and key_at(clients[client_keys[k]]["path"], clients[client_keys[k]]["rev"], k))]
    projects = {k: (client_key_project(clients[r], k) if r in clients else [None, {}])
                for k, r in client_keys.items() if k not in own_keys}
    out = [{"kind": "coverage", "path": unit["path"], "how": "coverage", "why": claim.get("why") or "",
            "function": _norm(unit.get("name")), "callee": "", "chain": [], "call_line": unit["line"],
            "keys": keys, "keys_at_merge_base": at_base, "gate_lines": [], "lines": [],
            "unit": {k: unit.get(k) for k in ("path", "line", "text", "name", "route", "external") if unit.get(k)},
            "declared_at": [{k: d[k] for k in ("repo", "path", "line", "text") if d.get(k)}
                            for d in claim.get("declared_at") or []],
            "callers": [{k: c[k] for k in ("repo", "path", "line", "text", "reached_by", "off_because", "off_line", "note")
                         if c.get(k)} | ({"key": c["gate"]["key"]} if c["reached_by"] == "gated" else {})
                        for c in claim["callers"]],
            "clients": {r: clients[r]["rev"] for r in dict.fromkeys(filter(None, map(_caller_repo, claim["callers"])))
                        if r in clients},
            "coverage_of": ref}]
    if projects:
        out[0]["key_projects"] = projects
    shown: set[tuple[str, int]] = set()
    for c in gated:
        g = c["gate"]
        r = _caller_repo(c)
        for e in entries({**g, "how": "caller", "why": ""}, set() if r else changed_paths, g["key"] in at_base):
            e.update({"kind": "covered", "coverage_of": ref})
            if r:
                e["path"] = f"{r}:{e['path']}"
                if g["key"] in projects:
                    e["key_projects"] = {g["key"]: projects[g["key"]]}
            shown |= {(e["path"], n) for n, _ in e["lines"]}
            out.append(e)
    rest: dict[str, set[tuple[int, str]]] = {}
    for x in [unit, *(claim.get("declared_at") or []), *claim["callers"]]:
        for y in [x] + ([{**x["off_line"], "repo": x.get("repo")}] if x.get("off_line") else []):
            p, r = at(y)
            if (r or p not in changed_paths) and (p, y["line"]) not in shown:
                rest.setdefault(p, set()).add((y["line"], y["text"]))
    for path, lines in rest.items():
        out.append({"kind": "covered", "path": path, "how": "caller", "why": "", "function": "", "callee": "",
                    "chain": [], "call_line": max(n for n, _ in lines), "keys": [], "keys_at_merge_base": [],
                    "gate_lines": [], "lines": sorted(lines), "coverage_of": ref})
    return out


# ---------------------------------------------------------------------------
# Data gates
# ---------------------------------------------------------------------------

def _quoted(xs, what: str) -> tuple[list[dict] | None, str | None]:
    if xs is None:
        return [], None
    if not isinstance(xs, list) or not all(isinstance(x, dict) for x in xs):
        return None, f"{what} is not a list of lines"
    return xs, None


def verify_data_gate(repo_path: str, head: str, claim: dict, files: dict,
                     changed_paths: set[str] | None = None, not_shipping=None) -> str | None:
    """None when a data-gate claim checks out at `head`, else why not.

    The claim: {"data": {"name", "also"?, "what"}, "readers": [{path, line, text}],
    "writers": [{path, line, text, reached_by, gate?, off_because?, off_line?,
    note?}], "other_uses": [{path, line, text}], "why"}. Checked: every quoted
    line matches head; each reader is shipping code in a changed file; each
    writer is reached as a caller is (`gated`: its gate verifies like a gate
    and its chain ends at the write; `off`: it writes the records only empty,
    at a real off_line; `test`; `none`, with a note), and at least one is
    gated; and every reference to the data's name, and to each of `also`
    (the field or setter a write can set it through from a variable, when the
    name is a value such as a kind), in shipping code at head is a listed
    reader, writer or other use, a comment, or an import or same-name
    re-export. Whether a line listed as an other use really doesn't write, and
    whether ungated code wrote such records before the change, is P5/P6's to
    judge: the lines are shown to them."""
    not_shipping = not_shipping or not_shipping_fn()
    data = claim.get("data") if isinstance(claim.get("data"), dict) else {}
    name = _norm(data.get("name"))
    if not name:
        return "the data has no name"
    also = data.get("also") or []
    if not isinstance(also, list) or not all(isinstance(a, str) and _norm(a) for a in also):
        return "also is not a list of names"
    groups = {}
    for k in ("readers", "writers", "other_uses"):
        xs, why = _quoted(claim.get(k), k)
        if why:
            return why
        groups[k] = xs
    readers, writers, others = groups["readers"], groups["writers"], groups["other_uses"]
    if not readers:
        return "no reader: name the changed lines that act only on the data"
    if not writers:
        return "no writer: a data gate needs the writes behind a flag"
    for r in readers + others:
        why = _check_ref(repo_path, head, r, files)
        if why:
            return f"{'reader' if r in readers else 'other use'}: {why}"
    for r in readers:
        if not_shipping(r["path"]):
            return f"reader {r['path']}:{r['line']} is not in shipping code"
        if changed_paths is not None and r["path"] not in changed_paths:
            return f"reader {r['path']}:{r['line']} is not in a file the diff changes"
    for w in writers:
        why = _check_caller(repo_path, head, w, files, not_shipping, f"{w.get('path')}:{w.get('line')}",
                            lambda w=w: _check_own_gate(repo_path, head, w, files))
        if why:
            return why.replace("caller ", "writer ", 1).replace("the caller line", "the write")
    if not any(w["reached_by"] == "gated" for w in writers):
        return "no writer is behind a flag"

    listed = {(x["path"], x["line"]) for x in readers + writers + others}
    listed_files = {p for p, _ in listed}
    for nm in dict.fromkeys([name, *map(_norm, also)]):
        try:
            hits = _grep(repo_path, head, nm, bool(IDENT.match(nm)))
        except RuntimeError as e:
            return f"the search for other uses failed: {e}"
        shipping = sorted({h for h in hits if not not_shipping(h[0])})
        if len(shipping) > MAX_REFERENCES:
            return f"{len(shipping)} references to {nm!r} at head; too many to list"
        for path, line, text in shipping:
            if (path, line) in listed or COMMENT.match(text):
                continue
            L = _lines(repo_path, head, path, files) or []
            kind = _import_kind(L, line - 1, nm) if 0 < line <= len(L) and IDENT.match(nm) else None
            if kind == "reexport" or (kind == "import" and path in listed_files):
                continue
            return f"unlisted use {path}:{line} of {nm!r}"
    return None


def data_entries(claim: dict, changed_paths: set[str], key_at_base) -> list[dict]:
    """A verified data gate as caller-gate entries: one `data` entry holding
    the claim (rendered in P5's, P6's and P12's questions), plus `data-line`
    entries for its lines outside the diff -- one per gated writer's chain
    file, carrying that flag's key and its evaluate/decide lines (so a
    citation of them names the key, as for a gate), and one per other file
    for its reader, writer, off and other-use lines (so they're citable).
    `key_at_base(key)` says whether a key existed at merge_base."""
    data = claim["data"]
    ref = f"data:{_norm(data['name'])}"
    gated = [w for w in claim["writers"] if w["reached_by"] == "gated"]
    keys = list(dict.fromkeys(w["gate"]["key"] for w in gated))
    at_base = [k for k in keys if key_at_base(k)]
    pick = lambda x, ks: {k: x[k] for k in ks if x.get(k)}  # noqa: E731
    first = claim["readers"][0]
    out = [{"kind": "data", "path": first["path"], "how": "data", "why": claim.get("why") or "",
            "function": "", "callee": "", "chain": [], "call_line": first["line"],
            "keys": keys, "keys_at_merge_base": at_base, "gate_lines": [], "lines": [],
            "data": pick(data, ("name", "also", "what")),
            "readers": [pick(r, ("path", "line", "text")) for r in claim["readers"]],
            "writers": [pick(w, ("path", "line", "text", "reached_by", "off_because", "off_line", "note"))
                        | ({"key": w["gate"]["key"]} if w["reached_by"] == "gated" else {})
                        for w in claim["writers"]],
            "other_uses": [pick(o, ("path", "line", "text")) for o in claim.get("other_uses") or []],
            "data_of": ref}]
    shown: set[tuple[str, int]] = set()
    for w in gated:
        g = w["gate"]
        for e in entries({**g, "how": "data", "why": ""}, changed_paths, g["key"] in at_base):
            e.update({"kind": "data-line", "data_of": ref})
            # The gated write is what the flag decides here: a citation of it alone is
            # gate-shaped and names the key, though it sits apart from the check.
            if e["path"] == w["path"] and w["line"] not in e["gate_lines"]:
                e["gate_lines"] = sorted(e["gate_lines"] + [w["line"]])
            shown |= {(e["path"], n) for n, _ in e["lines"]}
            out.append(e)
    rest: dict[str, set[tuple[int, str]]] = {}
    for x in [*claim["readers"], *claim["writers"], *(claim.get("other_uses") or [])]:
        for y in [x] + ([x["off_line"]] if x.get("off_line") else []):
            if y["path"] not in changed_paths and (y["path"], y["line"]) not in shown:
                rest.setdefault(y["path"], set()).add((y["line"], y["text"]))
    for path, lines in rest.items():
        out.append({"kind": "data-line", "path": path, "how": "data", "why": "", "function": "", "callee": "",
                    "chain": [], "call_line": max(n for n, _ in lines), "keys": [], "keys_at_merge_base": [],
                    "gate_lines": [], "lines": sorted(lines), "data_of": ref})
    return out
