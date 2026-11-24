#!/usr/bin/env python3
"""Tier 1 — predicates answered WITHOUT a model, plus the evidence packet.

Every answer produced here is a function of git, the repo profile, and the
LaunchDarkly API. Same inputs, same bits, every run. That is the reader's
determinism budget and it should be spent as widely as possible: each predicate
moved from Tier 2 to Tier 1 is one fewer place the reader can wobble.

ANSWERED HERE (7 of 29)
  U1   diff unit                 git merge-base / parent topology
  P1   ships_to_runtime          profile path roles
  P7   gate_state_resolved       LD readability at the merge date
  P8   gate_withholds            LD per-environment `on`
  P33  gate_holds_back_in_main   LD main-production targeting (after P8 NO)
  P9   candidate_exists_at_base  symbol table AT merge_base
  P11  candidate_not_released    LD per-environment `on`

EVERYTHING ELSE gets an evidence slice and goes to ask.py. Notably P5/P6
(enclosure) are NOT mechanical here -- real control-flow dominance across
TypeScript and Go is not implemented. They receive the full list of flag
evaluation sites in the changed files with line numbers, plus the changed line
ranges, and the model is asked to judge dominance from that. That is the
weakest joint in the reader and it is where a wrong answer is most expensive
(a false `already-flagged` hides real exposure), which is why ask.py requires
unanimity rather than a majority.

P6 additionally gets `referenced_context`: a bounded, ONE-HOP lookup for a
caller/renderer of the changed file that itself sits behind a flag check, so
P6 has somewhere legitimate to cite when the ancestor gate (almost by
definition) lives outside the diff. Still not real control-flow analysis,
and still only one hop -- a wrapper chain two or three components deep still
correctly falls through to escalation, same as before this existed.
"""

from __future__ import annotations

import bisect
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from . import specload

from .sources import (GitError, LDClient, LDUnavailable, Profile, Repo,
                      SymbolTable, build_symbol_table, resolve_unit)

UNRESOLVED = "UNRESOLVED"


def answer(value, evidence: str, basis: str | None = None) -> dict:
    a = {"value": value, "evidence": evidence}
    if basis:
        a["basis"] = basis
    return a


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class Hunk:
    path: str
    new_start: int
    new_count: int
    old_start: int
    old_count: int
    role: str
    text: str

    @property
    def new_range(self) -> tuple[int, int]:
        return (self.new_start, self.new_start + max(self.new_count, 1) - 1)


PROXIMITY_LINES = 40
"""How near a flag evaluation must be to a changed hunk to count as being in
"the code this change is part of" (P10).

40 lines is an approximation of "the same function or block". A real
implementation would use the enclosing function from an AST; this is a
deliberate stand-in, and sites outside the window are still shown to the model
under `elsewhere in file` so nothing is hidden -- they just are not offered as
candidates."""

MAX_CONTEXT_KEYS = 8  # far-from-hunk keys whose LD state is read for context


@dataclass
class Packet:
    """Everything a predicate may read. Built once, cached as a prompt prefix."""
    repo_name: str
    unit: dict
    pr: dict
    files: list[dict] = field(default_factory=list)
    hunks: list[Hunk] = field(default_factory=list)
    flag_sites_head: list[dict] = field(default_factory=list)
    flag_sites_base: list[dict] = field(default_factory=list)
    flag_sites_far: list[dict] = field(default_factory=list)
    referenced_context: list[dict] = field(default_factory=list)
    keys_added_by_diff: list[str] = field(default_factory=list)
    # How build_packet set up the LD client -- {"defaults": {key: [value,
    # added_by_diff]}, "key_projects": {key: [project, env_map]}} -- so a
    # later reader of this packet (merge_inline's gate re-read) sets up its
    # own client the same way. Not rendered: it doesn't change the hash.
    ld_setup: dict | None = None
    candidates: list[dict] = field(default_factory=list)
    ld: dict = field(default_factory=dict)
    codeowners: dict = field(default_factory=dict)
    public_api: dict | None = None
    external: list[dict] | None = None
    notes: list[str] = field(default_factory=list)
    # Not rendered into the packet (so the packet hash, and every cached
    # answer keyed on it, is unchanged): passed to P6/P12 in their question.
    caller_gates: list[dict] = field(default_factory=list)
    # Keys this diff deletes evaluations of (removed_flag_evaluations), with
    # their merge_base / head counts; rendered, with each key's LD state,
    # only when there is one. None on a packet kept before this existed.
    removed_flags: list[dict] | None = None
    # Added after the start by the skill's searches, never rendered into the
    # packet (its hash, and every answer keyed on it, is unchanged): the
    # feature flag search's verified release flags (feature_search.candidate)
    # with their LaunchDarkly state, which join P9/P11 as reuse candidates
    # (feature_candidate_answers) and are shown to P10/P12/P13; and the fact
    # search's verified findings, {question id: {"findings": [...]}}, shown
    # to that question when it is asked again. A packet kept before these
    # existed has no such attributes: read them with getattr.
    feature_candidates: list[dict] = field(default_factory=list)
    feature_snapshots: dict = field(default_factory=dict)
    fact_findings: dict = field(default_factory=dict)


def parse_hunks(repo: Repo, profile: Profile, unit_spec: str) -> list[Hunk]:
    out: list[Hunk] = []
    cur_path = None
    for raw in repo.diff(unit_spec, context=3).splitlines():
        if raw.startswith("+++ b/"):
            cur_path = raw[6:]
            continue
        if raw.startswith("+++ /dev/null"):
            continue
        m = HUNK_RE.match(raw)
        if m and cur_path:
            out.append(Hunk(
                path=cur_path,
                old_start=int(m.group(1)), old_count=int(m.group(2) or 1),
                new_start=int(m.group(3)), new_count=int(m.group(4) or 1),
                role=profile.role_of(cur_path), text=""))
        elif out and cur_path and out[-1].path == cur_path:
            out[-1].text += raw + "\n"
    return out


_TS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
# Lines parse_hunks appends from the NEXT file's header before its `+++ b/`.
_DIFF_HEADER = re.compile(r"^(diff --git |index |--- (a/|/dev/null)|new file mode|"
                          r"deleted file mode|similarity index|rename (from|to) |"
                          r"old mode|new mode)")


def import_only_hunk(h: Hunk) -> bool:
    """Is every line this hunk adds or removes part of an import statement?

    TS/JS, Go and Python; any other language is never import-only (the safe
    side: the hunk keeps counting). Context lines are read too, so a line
    inside a multi-line import that began above the change is recognised.
    """
    lang = ("ts" if h.path.endswith(_TS_EXT) else "go" if h.path.endswith(".go")
            else "py" if h.path.endswith(".py") else None)
    if lang is None:
        return False
    open_block = False
    changed: list[bool] = []
    for raw in h.text.splitlines():
        if _DIFF_HEADER.match(raw):
            continue
        tag, s = raw[:1], raw[1:].strip()
        if tag not in "+- " or raw.startswith("\\"):
            continue
        is_imp = False
        if open_block:
            is_imp = True
            if lang == "ts" and (re.search(r"\}\s*from\s+['\"]", s) or s.endswith(("';", '";'))):
                open_block = False
            elif lang in ("go", "py") and s.startswith(")"):
                open_block = False
        elif lang == "ts":
            if re.match(r"^import\s+(type\s+)?\{[^}]*$", s):
                is_imp = open_block = True
            elif re.match(r"^(import\s|export\s+(\*|\{[^}]*\})\s+from\s)", s):
                is_imp = True
        elif lang == "go":
            if re.match(r"^import\s*\($", s):
                is_imp = open_block = True
            elif re.match(r'^import\s+(\S+\s+)?"[^"]+"$', s):
                is_imp = True
        elif lang == "py":
            if re.match(r"^from\s+\S+\s+import\s*\($", s):
                is_imp = open_block = True
            elif re.match(r"^(import\s+\S|from\s+\S+\s+import\s)", s):
                is_imp = True
        if tag in "+-":
            changed.append(is_imp or s == "")
    return bool(changed) and all(changed) and any(
        _DIFF_HEADER.match(r) is None and r[:1] in "+-" and r[1:].strip()
        for r in h.text.splitlines())


def proximity_hunks(hunks: list[Hunk]) -> list[Hunk]:
    """The hunks that count as "the change" when finding nearby flags."""
    return [h for h in hunks if not import_only_hunk(h)]


def _in_scope(path: str, ev: dict) -> bool:
    import fnmatch
    if path in set(ev.get("exclude_files", [])):
        return False
    for pat in ev.get("search_exclude", []):
        bare = pat.replace("**/", "")
        if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path, bare) or \
           path.startswith(pat.replace("**", "").rstrip("/") + "/"):
            return False
    return True


def flag_aliases(repo: Repo, profile: Profile, rev: str
                 ) -> dict[str, tuple[str, str, int, str | None]]:
    """alias -> (key, declaring file, line, scope glob) at `rev`, from the
    profile's `evaluation.alias_declarations`.

    Some code reads flags through a map of named values rather than calling
    anything per use: `enableX: client.variation('enable-x', false)` in one
    file, then `settings.enableX` everywhere else. Neither the key nor a
    flag function appears at the read, so no call pattern can see it.
    Measured on an earlier PR: every gate in the diff was a read of
    `settings.enableAuditLogEntryLinks` or a prop drilled from it, and the
    reader concluded no flag was evaluated anywhere near the change.
    """
    out: dict[str, tuple[str, str, int, str | None]] = {}
    for ad in (profile.data.get("evaluation") or {}).get("alias_declarations") or []:
        text = repo.file_at(rev, ad["file"])
        if not text:
            continue
        rx = re.compile(ad["pattern"])
        for i, t in enumerate(text.splitlines(), 1):
            m = rx.search(t)
            if m:
                out[m.group(ad.get("alias_group", 1))] = (
                    m.group(ad.get("key_group", 2)), ad["file"], i,
                    ad.get("scope"))
    return out


def _alias_read_re(alias: str) -> re.Pattern:
    """A READ of an alias: a property access (`settings.enableX`, not an
    assignment to it), or the bare name used as a condition (`enableX &&`,
    `!enableX`, `if (enableX`). Not a type field (`enableX?: boolean`), a
    destructuring, or a prop handed down (`enableX={...}`) -- those carry
    the value without deciding anything."""
    a = re.escape(alias)
    return re.compile(
        rf"\.{a}\b(?!\s*=(?!=))"
        rf"|(?:&&|\|\||!|\?|\bif\s*\(|\bBoolean\()\s*{a}\b(?!\s*[:=(])"
        rf"|(?<![.\w]){a}\s*(?:&&|\|\|)")


_PRED_CACHE: dict[tuple[str, str, str], list[str] | None] = {}


def predicate_var_keys(repo: Repo, profile: Profile, st: SymbolTable,
                       rev: str, name: str, _seen: frozenset = frozenset()
                       ) -> list[str] | None:
    """The keys a hand-written flag predicate's body reads, or None when no
    definition of `name` is found."""
    ev = profile.data.get("evaluation", {})
    spec = ev.get("predicate_definitions")
    if not spec or name in _seen:
        return None
    ck = (str(repo.path), rev, name)
    if ck in _PRED_CACHE:
        return _PRED_CACHE[ck]
    pat = spec.replace("NAME", re.escape(name))
    body: list[str] = []
    for path, line, _ in repo.grep_at(rev, pat, ev.get("predicate_definition_files")):
        L = (repo.file_at(rev, path) or "").splitlines()
        depth = 0
        for t in L[line - 1:line - 1 + 200]:
            body.append(t)
            depth += t.count("{") - t.count("}")
            if depth <= 0 and len(body) > 1:
                break
        break
    if not body:
        _PRED_CACHE[ck] = None
        return None
    pats = [re.compile(p_) for p_ in (ev.get("resolved_patterns") or [])
            + (ev.get("extra_patterns") or [])]
    out: list[str] = []
    for t in body[1:]:
        for rx in pats:
            for mm in rx.finditer(t):
                sym = mm.group(1) if mm.groups() else None
                k = (st.key_for(sym) or (sym if sym in st.keys else None)) if sym else None
                if k and k not in out:
                    out.append(k)
        for nested in re.findall(r"\b\w+\.(\w+Pred)\b|\b(\w+Pred)\(", t):
            nm = nested[0] or nested[1]
            for k in predicate_var_keys(repo, profile, st, rev, nm, _seen | {name}) or []:
                if k not in out:
                    out.append(k)
    _PRED_CACHE[ck] = out
    return out


def flag_sites(repo: Repo, profile: Profile, st: SymbolTable, rev: str,
               paths: list[str], _siblings: bool = True,
               imported_helpers: bool = False,
               method_helpers: bool = False) -> list[dict]:
    """Flag EVALUATION sites in the given files, resolved to keys.

    Resolution through the symbol table is what makes this work at all: the
    key string is absent from the call site in both repos.

    `imported_helpers` adds calls to flag-evaluating functions from relative
    JS/TS imports (see _imported_helper_sites). build_packet asks for them
    on the changed files only. `method_helpers` adds Go method calls that
    decide an early exit on a flag returned in another package (see
    _method_helper_sites): the changed files and the outside-caller walk.
    """
    ev = profile.data.get("evaluation", {})
    sites: list[dict] = []
    if not paths:
        return sites
    excl_sym = set(ev.get("exclude_symbols", []))

    # `resolved_patterns` are broad shapes (`<anything>Flags.X()`, a
    # predicate's `f.X()`) whose matches only count when the captured name
    # resolves to a declared flag -- otherwise `f.HideWithFlag(` would be a
    # "flag site", and find_referenced_context treats any site as a gate.
    for pat, require_key in ([(p_, False) for p_ in ev.get("extra_patterns") or []]
                             + [(p_, True) for p_ in ev.get("resolved_patterns") or []]):
        for path, line, text in repo.grep_at(rev, pat, paths):
            if not _in_scope(path, ev):
                continue
            for m in re.finditer(pat, text):
                sym = m.group(1) if m.groups() else None
                if sym in excl_sym:
                    continue
                key = st.key_for(sym) if sym else None
                key = key or (sym if sym in st.keys else None)
                if require_key and not key:
                    continue
                sites.append({"path": path, "line": line, "symbol": sym,
                              "key": key, "source": "pattern",
                              "text": text.strip()[:200]})

    if ev.get("symbol_call"):
        specs = []
        for d in profile.data.get("flag_declarations", []):
            specs += d.get("import_specifiers", [])
        for path in paths:
            text = repo.file_at(rev, path)
            if text is None or not _in_scope(path, ev):
                continue
            imported: set[str] = set()
            for spec in specs:
                for im in re.finditer(
                        r"import\s*\{([^}]*)\}\s*from\s*['\"]"
                        + re.escape(spec) + r"['\"]", text):
                    for piece in im.group(1).split(","):
                        name = piece.split(" as ")[-1].strip()
                        if name:
                            imported.add(name)
            for sym in sorted(imported - excl_sym):
                key = st.key_for(sym)
                if not key:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if re.search(r"\b" + re.escape(sym) + r"\s*\(", line):
                        sites.append({"path": path, "line": i, "symbol": sym,
                                      "key": key, "source": "symbol-call",
                                      "text": line.strip()[:200]})
    import fnmatch
    aliases = flag_aliases(repo, profile, rev)
    for path in paths if aliases else []:
        if not _in_scope(path, ev):
            continue
        text = repo.file_at(rev, path)
        if text is None:
            continue
        for alias, (key, decl_file, decl_line, scope) in aliases.items():
            if scope and not fnmatch.fnmatch(path, scope):
                continue
            if path == decl_file:
                continue
            if alias not in text:
                continue
            rx = _alias_read_re(alias)
            for i, line in enumerate(text.splitlines(), 1):
                if alias in line and rx.search(line) and not \
                        line.lstrip().startswith(_COMMENT_PREFIXES):
                    sites.append({"path": path, "line": i, "symbol": alias,
                                  "key": key, "source": "alias-read",
                                  "text": line.strip()[:200]})

    # A qualified reference to a hand-written flag predicate (see
    # predicate_var_keys) is a site of each key its body reads. One the
    # definitions cannot resolve is kept WITHOUT a key, so keys_at_citations
    # knows the cited line holds a gate and does not borrow a neighbour's.
    if ev.get("predicate_definitions"):
        ref = re.compile(r"\b\w+\.(\w+Pred)\b")
        gen = re.compile(r"\b(?:d|dogfood)\.\w+Pred\b")
        for path in paths:
            if not _in_scope(path, ev):
                continue
            text = repo.file_at(rev, path)
            if text is None:
                continue
            for i, t in enumerate(text.splitlines(), 1):
                for m in ref.finditer(t):
                    if gen.match(m.group(0)):
                        continue      # generated: resolved by the profile patterns
                    keys = predicate_var_keys(repo, profile, st, rev, m.group(1))
                    for k in keys or [None]:
                        sites.append({"path": path, "line": i, "symbol": m.group(1),
                                      "key": k, "source": "predicate-var" if k else
                                      "unresolved-predicate", "text": t.strip()[:200]})

    # A call that names the flag KEY as an argument (see _keyed_call_sites).
    sites += _keyed_call_sites(repo, st, rev, paths, ev)
    # A call to a helper that TAKES a flag as a parameter (see
    # _flag_param_sites).
    sites += _flag_param_sites(repo, st, rev, paths, ev)
    if imported_helpers:
        sites += _imported_helper_sites(repo, profile, st, rev, paths, ev)
    if method_helpers:
        sites += _method_helper_sites(repo, profile, st, rev, paths, ev)

    extra = _sibling_sites(repo, profile, st, rev, paths) if _siblings else []
    sites += _helper_gate_sites(repo, rev, paths, sites, extra)

    # Two patterns can match the same call (`ctx.Flags.X()` fits both the
    # accessor pattern and the broad `<anything>Flags.X()` one).
    seen: set[tuple] = set()
    unique = []
    for site in sites:
        k = (site["path"], site["line"], site["key"] or site["symbol"])
        if k not in seen:
            seen.add(k)
            unique.append(site)
    return unique


def _dead_flag_removal(repo: Repo, profile: Profile, st_base: SymbolTable,
                       st_head: SymbolTable, base_rev: str, pkt: "Packet"
                       ) -> list[str]:
    """The keys, if the diff does nothing but remove the declarations of
    flags no code evaluates at merge_base; else []. Every changed line outside
    the profile's declaration/generated files (and tests) must name a removed
    key, and each removed key's names -- the key, every symbol declaring it,
    its generated `<Field>FlagKey` / `<Field>Pred` -- must have no match at
    merge_base outside those files and the diff's own files."""
    removed = sorted(st_base.keys - st_head.keys)
    if not removed:
        return []
    ev = profile.data.get("evaluation", {})
    decl = set(ev.get("exclude_files", []))
    names_of = {k: {k} | {sym for sym, kk in st_base.by_symbol.items() if kk == k}
                for k in removed}
    for k in removed:
        for sym in list(names_of[k]):
            if sym != k:
                names_of[k] |= {sym + "FlagKey", sym + "Pred"}
    every = set().union(*names_of.values())
    changed = {f["path"] for f in pkt.files}

    def exempt(path: str) -> bool:
        return (path in decl or profile.role_of(path) in ("test", "generated")
                or not _in_scope(path, ev))
    for h in pkt.hunks:
        if exempt(h.path):
            continue
        for line in h.text.splitlines():
            if line[:1] in "+-" and not line.startswith(("+++", "---")):
                body = line[1:].strip()
                if body and not any(n in body for n in every):
                    return []
    for k in removed:
        for n in sorted(names_of[k]):
            out = repo.git("grep", "-l", "-w", "-F", n, base_rev, check=False)
            for hit in out.splitlines():
                path = hit.split(":", 1)[1] if ":" in hit else hit
                if path not in changed and not exempt(path):
                    return []
    return removed


def _block_end(lines: list[str], line_1idx: int) -> int:
    """The line closing the brace block the given line opens, or the line
    itself when it opens none. Braces in strings are not special-cased: this
    only bounds where a block's own gate may sit."""
    t = lines[line_1idx - 1] if 0 < line_1idx <= len(lines) else ""
    if not t.rstrip().endswith("{"):
        return line_1idx
    depth = 0
    for i in range(line_1idx - 1, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth <= 0:
            return i + 1
    return len(lines)


def _call_args(text: str, start: int) -> list[str] | None:
    """The top-level, comma-separated arguments of a call whose opening
    parenthesis ends just before `start`, or None if it never closes. Strings
    and nested brackets are skipped, so `f(ctx, "a,b", g(x, y))` is three
    arguments."""
    args, depth, cur, i, n = [], 0, [], start, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'`":
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" and ch != "`" else 1
            cur.append(text[i:j + 1]); i = j + 1; continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                args.append("".join(cur).strip())
                return args
            depth -= 1
        elif ch == "," and depth == 0:
            args.append("".join(cur).strip()); cur = []; i += 1; continue
        cur.append(ch); i += 1
    return None


def _resolve_key_arg(raw: str, text: str, st: SymbolTable) -> str | None:
    """A flag-key argument as written at a call site, resolved to the key:
    a string literal; a generated `<Field>FlagKey` constant (the go-raw-flags
    field name resolves through the symbol table); or an identifier bound to
    a string literal in the same file (`name = "key"`, `name := "key"`)."""
    m = re.fullmatch(r"[\"`]([A-Za-z0-9][A-Za-z0-9._-]*)[\"`]", raw)
    if m:
        return m.group(1)
    m = re.fullmatch(r"(?:\w+\.)?([A-Z]\w*)FlagKey", raw)
    if m and st.key_for(m.group(1)):
        return st.key_for(m.group(1))
    m = re.fullmatch(r"[A-Za-z_]\w*", raw)
    if m:
        b = re.search(r"\b" + re.escape(raw) + r"\s*(?::=|=)\s*[\"`]([A-Za-z0-9][A-Za-z0-9._-]*)[\"`]",
                      text)
        if b:
            return b.group(1)
    return None


_FLAG_PARAM_CACHE: dict[tuple, list[str]] = {}


def _flag_param_sites(repo: Repo, st: SymbolTable, rev: str,
                      paths: list[str], ev: dict) -> list[dict]:
    """."""
    spec = ev.get("flag_param_helpers")
    if not spec or not paths:
        return []
    ck = (str(getattr(repo, "path", "")), rev)
    if ck not in _FLAG_PARAM_CACHE:
        out = repo.git("grep", "-h", "-P", spec["signature"], rev, "--",
                       *spec.get("files", []), check=False)
        names = set()
        for line in out.splitlines():
            m = re.search(spec["signature"], line)
            if m:
                names.add(m.group(1))
        _FLAG_PARAM_CACHE[ck] = sorted(names)
    names = _FLAG_PARAM_CACHE[ck]
    arg = re.compile(spec["arg"])
    sites: list[dict] = []
    for path in paths if names else []:
        if not _in_scope(path, ev):
            continue
        text = repo.file_at(rev, path)
        if not text:
            continue
        for name in names:
            for m in re.finditer(r"\b" + re.escape(name) + r"\s*\(", text):
                line = _line_of(text, m.start())
                if text.splitlines()[line - 1].lstrip().startswith("func "):
                    continue          # the helper's own declaration
                args = _call_args(text, m.end()) or []
                for a in args:
                    am = arg.fullmatch(a.strip())
                    key = st.key_for(am.group(1)) if am else None
                    if key:
                        sites.append({"path": path, "line": line, "symbol": name,
                                      "key": key, "source": "flag-param-helper",
                                      "text": text.splitlines()[line - 1].strip()[:200]})
    return sites


_REL_IMPORT_RE = re.compile(
    r"^\s*import\s+(type\s+)?(?:([A-Za-z_$][\w$]*)\s*,?\s*)?(?:\{([^}]*)\})?"
    r"\s*from\s*['\"](\.\.?/[^'\"]*)['\"]", re.M)
_DEFAULT_EXPORT_RE = re.compile(
    r"^export\s+default\s+(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)"
    r"|^export\s+default\s+([A-Za-z_$][\w$]*)\s*;?\s*$", re.M)
_HELPER_MODULE_EXTS = (".ts", ".tsx", ".js", ".jsx")


def _relative_imports(text: str) -> list[tuple[str, str, str]]:
    """(local name, imported name or "default", specifier) for each value
    import from a relative module. Type-only and namespace imports are
    skipped: neither is called."""
    out = []
    for m in _REL_IMPORT_RE.finditer(text):
        if m.group(1):
            continue
        if m.group(2):
            out.append((m.group(2), "default", m.group(4)))
        for piece in (m.group(3) or "").split(","):
            piece = piece.strip()
            if not piece or piece.startswith("type "):
                continue
            bits = [b.strip() for b in piece.split(" as ")]
            if bits[-1]:
                out.append((bits[-1], bits[0], m.group(4)))
    return out


def _imported_helper_sites(repo: Repo, profile: Profile, st: SymbolTable,
                           rev: str, paths: list[str], ev: dict) -> list[dict]:
    """Calls to a function imported from a relative JS/TS module whose body
    evaluates a flag, as sites of the key(s) it evaluates."""
    listings: dict[str, set[str]] = {}
    modules: dict[str, dict[str, list[str]] | None] = {}

    def listing(d: str) -> set[str]:
        if d not in listings:
            listings[d] = set(repo.git("ls-tree", "--name-only", rev, "--",
                                       d.rstrip("/") + "/", check=False).splitlines())
        return listings[d]

    def resolve(caller: str, spec: str) -> str | None:
        base = os.path.normpath(os.path.join(str(Path(caller).parent), spec))
        d = str(Path(base).parent)
        if base.startswith("..") or d in ("", "."):
            return None
        if Path(base).suffix in _HELPER_MODULE_EXTS and base in listing(d):
            return base
        for ext in _HELPER_MODULE_EXTS:
            if base + ext in listing(d):
                return base + ext
        for ext in _HELPER_MODULE_EXTS:
            if f"{base}/index{ext}" in listing(base):
                return f"{base}/index{ext}"
        return None

    def helpers_in(mod: str) -> dict[str, list[str]] | None:
        """function name -> keys its body evaluates; "default" names the
        default export's."""
        if mod not in modules:
            text = repo.file_at(rev, mod) if _in_scope(mod, ev) else None
            if not text:
                modules[mod] = None
                return None
            L = text.splitlines()
            out: dict[str, list[str]] = {}
            for s in flag_sites(repo, profile, st, rev, [mod], _siblings=False):
                fn = _function_at(L, s["line"], Path(mod).suffix) if s["key"] else None
                if fn and fn[1] not in _GENERIC_SYMBOLS:
                    ks = out.setdefault(fn[1], [])
                    if s["key"] not in ks:
                        ks.append(s["key"])
            dm = _DEFAULT_EXPORT_RE.search(text)
            if dm and (dm.group(1) or dm.group(2)) in out:
                out["default"] = out[dm.group(1) or dm.group(2)]
            modules[mod] = out
        return modules[mod]

    sites: list[dict] = []
    for path in paths:
        if not path.endswith(_HELPER_MODULE_EXTS) or not _in_scope(path, ev):
            continue
        text = repo.file_at(rev, path)
        if not text:
            continue
        L = text.splitlines()
        for local, name, spec in _relative_imports(text):
            mod = resolve(path, spec)
            keys = (helpers_in(mod) or {}).get(name) if mod and mod != path else None
            if not keys:
                continue
            call = re.compile(r"\b" + re.escape(local) + r"\s*\(")
            decl = re.compile(r"\bfunction\s+" + re.escape(local) + r"\b")
            for i, t in enumerate(L, 1):
                if not call.search(t) or t.lstrip().startswith(_COMMENT_PREFIXES) \
                        or _IMPORT_RE.match(t) or decl.search(t):
                    continue
                for k in keys:
                    sites.append({"path": path, "line": i, "symbol": local,
                                  "key": k, "source": "imported-helper",
                                  "text": t.strip()[:200]
                                  + f"  [{local} evaluates it in {mod}]"})
    return sites


MAX_METHOD_DEFS = 3
"""A method name defined more often than this (outside tests and mocks) is
ambiguous at a call through an interface, so it is not followed."""

_METHOD_CALL_RE = re.compile(r"\.([A-Z]\w*)\(")
_METHOD_DEF_CACHE: dict[tuple, list[tuple[str, int]]] = {}


def _method_helper_sites(repo: Repo, profile: Profile, st: SymbolTable,
                         rev: str, paths: list[str], ev: dict) -> list[dict]:
    """Go: a method call that decides an early exit, where the method is
    defined in another package and RETURNS a flag, is a site of that flag.

    an earlier PR: the batch loop skips an account with `if
    !c.deps.Flags.AllowsAutoConversion(ctx, acct) { ... continue }` before
    calling the changed ConvertAccount. AllowsAutoConversion lives in an
    adapter package and returns allow-plan-trial-auto-conversion, but gate
    helpers were only looked for in the changed files and their package, so
    the caller walk reached the loop and saw no gate. The definition is found
    by name (`func (<recv>) Name(`), test and mock files aside; a name with
    more than MAX_METHOD_DEFS definitions is skipped as ambiguous.
    """
    out: list[dict] = []
    for path in paths:
        if not path.endswith(".go") or not _in_scope(path, ev):
            continue
        L = (repo.file_at(rev, path) or "").splitlines()
        for i, t in enumerate(L, 1):
            if not _COND_RE.match(t) or t.lstrip().startswith(_COMMENT_PREFIXES) \
                    or not _block_exits(L, i, len(L) + 1):
                continue
            for name in dict.fromkeys(_METHOD_CALL_RE.findall(t)):
                if name in _GENERIC_SYMBOLS:
                    continue
                for k, where in _method_flag_keys(repo, profile, st, rev, name, ev):
                    out.append({"path": path, "line": i, "symbol": name, "key": k,
                                "source": "method-helper",
                                "text": t.strip()[:200]
                                + f"  [{name} returns it in {where}]"})
    return out


def _method_flag_keys(repo: Repo, profile: Profile, st: SymbolTable, rev: str,
                      name: str, ev: dict) -> list[tuple[str, str]]:
    """(key, defining file) for each flag a method `name` returns."""
    ck = (str(getattr(repo, "path", "")), rev, name)
    if ck not in _METHOD_DEF_CACHE:
        defs = [(p, n) for p, n, _ in repo.grep_at(
                    rev, r"^func\s+\([^)]*\)\s*" + re.escape(name) + r"\s*\(", ["*.go"])
                if not p.endswith("_test.go") and "/mocks/" not in p
                and not Path(p).name.startswith("mock_") and _in_scope(p, ev)]
        _METHOD_DEF_CACHE[ck] = defs if len(defs) <= MAX_METHOD_DEFS else []
    found: list[tuple[str, str]] = []
    for p, start in _METHOD_DEF_CACHE[ck]:
        L = (repo.file_at(rev, p) or "").splitlines()
        end = _block_end(L, start)
        for s in flag_sites(repo, profile, st, rev, [p], _siblings=False):
            if not s["key"] or not (start < s["line"] <= end):
                continue
            t = L[s["line"] - 1]
            am = _MULTI_ASSIGN_RE.match(t)
            first = am.group(1).split(",")[0].strip() if am else None
            if _RETURN_RE.match(t) or (first and first not in ("_", "err") and any(
                    re.match(r"^\s*return\s+" + re.escape(first) + r"\b", L[n - 1])
                    for n in range(s["line"] + 1, end + 1))):
                if (s["key"], p) not in found:
                    found.append((s["key"], p))
    return found


def _keyed_call_sites(repo: Repo, st: SymbolTable, rev: str,
                      paths: list[str], ev: dict) -> list[dict]:
    """."""
    specs = ev.get("keyed_calls") or []
    out: list[dict] = []
    for path in paths if specs else []:
        if not _in_scope(path, ev):
            continue
        text = repo.file_at(rev, path)
        if not text:
            continue
        for spec in specs:
            for m in re.finditer(spec["pattern"], text):
                args = _call_args(text, m.end())
                idx = spec.get("key_arg", 1)
                if not args or len(args) <= idx:
                    continue
                key = _resolve_key_arg(args[idx], text, st)
                if not key and re.fullmatch(r"[A-Za-z_]\w*", args[idx]) and re.search(
                        r"\bfunc\b[^{]*[(,]\s*" + re.escape(args[idx]) + r"\s+string\b",
                        text[:m.start()]):
                    continue
                line = _line_of(text, m.start())
                out.append({"path": path, "line": line, "symbol": args[idx][:80],
                            "key": key,
                            "source": "keyed-call" if key else "unresolved-keyed-call",
                            "text": text.splitlines()[line - 1].strip()[:200]})
    return out


_EXPORT_RE = [
    re.compile(r"export\s+default\s+function\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"export\s+(?:const|function|class)\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z][A-Za-z0-9_]*)\s*\(", re.M),
]

_GENERIC_SYMBOLS = frozenset({
    "New", "String", "Error", "Close", "Get", "Set", "Handle", "Validate",
    "Equals", "Copy", "Clone", "UnmarshalJSON", "MarshalJSON", "UnmarshalText",
    "MarshalText", "Scan", "Value", "Len", "Less", "Swap", "Unwrap",
})


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


_AFTER_HUNK_PENALTY = 10_000
"""A symbol declared AFTER a hunk cannot be the top-level function enclosing
it -- Go/TS functions are declared sequentially, not nested, so only a
declaration at or before the hunk's start is even a candidate for enclosing
it. Scoring "before" and "after" symmetrically (plain absolute distance)
picks the wrong function whenever a short, unrelated sibling is declared
right after a long one that actually contains the hunk: measured on
an earlier PR, where the hunk sits inside makePrequelS3DestinationRep
(declared 42 lines before it) but 4 short, irrelevant functions declared
just after the hunk scored as "closer" under plain distance and won the
top-5 cap. A large fixed penalty on "after" keeps it as a last-resort
fallback (still better than nothing) without ever letting it outrank a
"before" candidate."""


def _hunk_distance(line: int, hunk_lines: list[tuple[int, int]]) -> int:
    """0 if `line` falls inside any (lo, hi) range; the gap if it's before
    one (a plausible enclosing declaration); a heavily penalized gap if it's
    only after one (see `_AFTER_HUNK_PENALTY`)."""
    return min((0 if lo <= line <= hi else
               (lo - line if line < lo else _AFTER_HUNK_PENALTY + (line - hi)))
               for lo, hi in hunk_lines)


def _exported_symbols(path: str, text: str,
                      hunk_lines: list[tuple[int, int]] | None = None
                      ) -> list[str]:
    """A deliberately simple 'what might call into this file' guess.

    A component file's own basename (PascalCase) is usually its default
    export -- `PayloadsSettingsSection.tsx` exports `PayloadsSettingsSection`
    -- treated as distance 0 (highest priority) since it is the cheapest,
    most reliable signal. Explicit `export`/`func` declarations are added
    after, INCLUDING lowercase Go funcs (package-private, not repo-private --
    see find_referenced_context's same-package scoping). `_GENERIC_SYMBOLS`
    is filtered out of all of the above: a name common enough to be a
    coincidence is worse than no name at all.

    `hunk_lines`, when given, is the `[(start, end), ...]` line ranges the
    diff actually changed in THIS file (1-indexed, new-file numbering).
    Candidates are ranked by distance to the nearest range before the cap to
    5 is applied -- without this, a file with several functions declared
    before the changed one silently crowds the relevant symbol out of the
    candidate list by file order alone, not relevance. Measured on
    an earlier PR: the hunk sits inside `ReplaceMemberTeams` at line 547,
    but 5 unrelated helper functions declared earlier (lines 59-247) filled
    the cap before line 547 was ever reached, and `find_referenced_context`
    never even tried searching for callers of the right name. When
    `hunk_lines` is omitted, candidates keep file-declaration order (the
    original behavior) -- every current caller passes it, but this keeps the
    function usable standalone.

    This is NOT real symbol resolution (`flag_sites`'s `symbol_call` path
    does that carefully, for flag declarations specifically); a missed or
    wrong guess here just means `find_referenced_context` finds nothing for
    that file, and P6 falls back to escalating -- the same place it was
    before this existed.

    A Storybook stories file (`*.stories.tsx` etc.) is excluded before any
    of the above runs, not filtered after: it exports one const per UI
    STATE, and those names are drawn from an open-ended, unpredictable
    vocabulary (`Empty`, `Loading`, `Default`, `Disabled`, `WithError`, ...)
    that `_GENERIC_SYMBOLS`' fixed blocklist can never keep up with one
    word at a time. Measured on an earlier PR: `ContextKindSelector.
    stories.tsx`'s `export const Empty: Story = {...}` matched three
    entirely unrelated files elsewhere in the repo that happen to export
    their OWN thing called `Empty`, none of which have anything to do with
    `ContextKindSelector.tsx`. A story is also never actually CALLED by
    application code the way a component or function is -- only Storybook's
    own tooling consumes it -- so searching for its "callers" is
    categorically the wrong question, not just a name collision to dodge.
    """
    if re.search(r"\.stories\.[jt]sx?$", path):
        return []
    candidates: dict[str, int] = {}  # symbol -> line of first occurrence
    stem = Path(path).stem
    if stem and stem[0].isupper():
        candidates[stem] = 0
    for rx in _EXPORT_RE:
        for m in rx.finditer(text):
            s = m.group(1)
            if s not in candidates:
                candidates[s] = _line_of(text, m.start())
    kept = [s for s in candidates if s not in _GENERIC_SYMBOLS]
    if hunk_lines:
        kept.sort(key=lambda s: _hunk_distance(candidates[s], hunk_lines)
                  if candidates[s] else 0)
    return kept[:5]


# "* " (with the space) is a doc-comment continuation; a bare "*" would also
# swallow Go pointer dereferences like `*cfg = Foo(...)`.
_COMMENT_PREFIXES = ("//", "/*", "* ", "*/", "{/*")
_IMPORT_RE = re.compile(
    r"^\s*(?:import\b|export\s*\{[^}]*\}\s*from\b|from\s+\S+\s+import\b)")
_IMPORT_OPEN_RE = re.compile(
    r"^\s*(?:(?:import|export)\s+(?:type\s+)?(?:[\w$]+\s*,\s*)?\{[^}]*"
    r"|from\s+\S+\s+import\s*\()\s*$")


_LINE_COMMENT_RE = re.compile(r"/\*.*?\*/|//.*$|(?:^|\s)#.*$")


def _in_import(lines: list[str], ln: int) -> bool:
    """Is 1-based line `ln` part of an import statement: one matching
    `_IMPORT_RE`, or a member line of a multi-line `import {` (or a
    re-export's `export {`, or Python's `from m import (`)."""
    if not 1 <= ln <= len(lines):
        return False
    if _IMPORT_RE.match(lines[ln - 1]):
        return True
    for i in range(ln - 1, max(0, ln - 80), -1):
        # A comment's punctuation (`// (legacy)`) neither opens nor closes it.
        t = _LINE_COMMENT_RE.sub("", lines[i - 1])
        if _IMPORT_OPEN_RE.match(t):
            return True
        if any(c in t for c in "{}();"):
            return False
    return False


def _window_over_use(anchor: int, gate_line: int | None, uses: list[int],
                     n: int, window: int) -> tuple[int, int]:
    """The shown window, `anchor` +/- window//2, moved to cover a use of the
    symbol when the anchor is only its import.

    The import line is a reference but not what enclosure is judged on: the
    render or call is. When no use is already in the window, it is moved to
    span the credited gate line and the nearest use that fits with it in the
    same number of lines. Measured on an earlier PR: NewHiresContainer.tsx
    was shown at 1-48 (its import of NewHiresTable at 18, flag reads at
    23-33) while the render was at 65, so a P6 answer citing the render was
    rejected and the run escalated. A use too far from the gate to share the
    window leaves it where it was."""
    lo, hi = max(1, anchor - window // 2), min(n, anchor + window // 2)
    if not uses or any(lo <= u <= hi for u in uses):
        return lo, hi
    keep = gate_line if gate_line is not None else anchor
    for u in sorted(uses, key=lambda u: abs(u - keep)):
        a, b = min(keep, u), max(keep, u)
        if b - a > window:
            break
        lo = max(1, (a + b) // 2 - window // 2)
        hi = lo + window
        if hi > n:
            hi, lo = n, max(1, n - window)
        return lo, hi
    return lo, hi

_ASSIGN_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=")
CONDITIONAL_USE_RE_TEMPLATE = r"\b{var}\b\s*&&|if\s*\([^)]*\b{var}\b|\b{var}\b\s*\?"


def _flag_derived_vars(sites: list[dict]) -> dict[str, str]:
    """."""
    out: dict[str, str] = {}
    for s in sites:
        if not s.get("key"):
            continue
        m = _ASSIGN_RE.match(s.get("text") or "")
        if m:
            out[m.group(1)] = s["key"]
    return out


def _conditional_use_line(lines: list[str], near_line_1idx: int,
                          derived: dict[str, str], radius: int
                          ) -> tuple[int, str] | None:
    """Does a flag-derived variable gate something within `radius` lines of
    `near_line_1idx` (1-indexed)? Returns (line, key) for the first hit."""
    if not derived:
        return None
    lo = max(1, near_line_1idx - radius)
    hi = min(len(lines), near_line_1idx + radius)
    for var, key in derived.items():
        pat = re.compile(CONDITIONAL_USE_RE_TEMPLATE.format(var=re.escape(var)))
        for i in range(lo, hi + 1):
            if pat.search(lines[i - 1]):
                return i, key
    return None


_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_GO_IMPORT_RE = re.compile(r'^\s*(?:import\s+)?(?:[A-Za-z_.]\w*\s+)?"([^"]+)"\s*$', re.M)


def _module_stem(path: str) -> str:
    """A module's path without extension, and without a trailing /index."""
    stem = str(Path(path).with_suffix(""))
    return stem[:-len("/index")] if stem.endswith("/index") else stem


_SOURCE_ROOTS = {"src", "lib"}


def _path_tail(path: str) -> str:
    """."""
    parts = [x.lstrip("#") for x in Path(path).parts if x not in _SOURCE_ROOTS]
    return "/".join(parts[-2:])


def _imports_symbol_from(text: str, caller_path: str, sym: str,
                         changed_path: str) -> bool:
    """Does the file at `caller_path` get `sym` from `changed_path`, rather
    than from some other module that exports the same name?

    JS/TS: an import (or re-export) of `sym` whose specifier resolves to the
    changed module -- relative specifiers exactly, package or alias
    specifiers by their trailing path. Go: the same directory (package), or
    an import path ending in the changed file's directory. Other languages
    are not checked.
    """
    if caller_path.endswith(_JS_EXTS):
        target = _module_stem(changed_path)
        accepted = {target, str(Path(target).parent)}
        tails = {_path_tail(t) for t in accepted}
        rx = re.compile(r"(?:import|export)\s+(?:type\s+)?(?:\{[^}]*\b"
                        + re.escape(sym) + r"\b[^}]*\}|" + re.escape(sym)
                        + r")[^'\"]*?from\s*['\"]([^'\"]+)['\"]", re.S)
        for m in rx.finditer(text):
            spec = m.group(1)
            if spec.startswith("."):
                resolved = _module_stem(os.path.normpath(os.path.join(
                    str(Path(caller_path).parent), spec)))
                if resolved in accepted:
                    return True
            elif _path_tail(_module_stem(spec)) in tails:
                return True
        return False
    if caller_path.endswith(".go"):
        pkg = str(Path(changed_path).parent)
        if str(Path(caller_path).parent) == pkg:
            return True
        return any(imp == pkg or imp.endswith("/" + pkg)
                   for imp in _GO_IMPORT_RE.findall(text))
    return True


def _declaration_files(profile: Profile) -> set[str]:
    """The profile's flag declaration files (flag_declarations' `file`, and
    exclude_files, which lists them and their generated accessors)."""
    return ({d["file"] for d in profile.data.get("flag_declarations", []) if d.get("file")}
            | set(profile.data.get("evaluation", {}).get("exclude_files", [])))


def find_referenced_context(repo: Repo, profile: Profile, st: SymbolTable,
                            rev: str, ship_paths: list[str],
                            exclude_paths: set[str],
                            hunk_ranges: dict[str, list[tuple[int, int]]]
                            | None = None,
                            max_files: int = 3, window: int = 60
                            ) -> list[dict]:
    """One-hop lookup: does some OTHER file call/render a changed file's own
    symbol, itself behind a flag check nearby (directly, or via a
    flag-derived variable used conditionally elsewhere in the same file --
    see `_conditional_use_line`)? P6's ancestor gate almost by
    definition lives outside the diff, so this is where P6 gets legitimate
    evidence to cite instead of nothing.

    Bounded and ONE HOP ONLY: this looks at direct callers/renderers of a
    changed file, not callers of callers. A gate two or three components up a
    wrapper chain is not found here and P6 correctly escalates, same as
    before -- this closes the one-hop subset of the gap, not the general
    case. Reuses `flag_sites()` (the same patterns already trusted for
    in-diff flag detection) rather than inventing a second detection path.

    `hunk_ranges`, when given, is `{path: [(start, end), ...]}` for the
    diff's own changed lines -- forwarded to `_exported_symbols` so a file
    with many declarations picks the one actually near the changed hunk
    instead of just the first few in file order (see that function's
    docstring; measured on an earlier PR).
    """
    found: list[dict] = []
    seen: set[str] = set()
    declares = _declaration_files(profile)
    for path in sorted(ship_paths):
        if len(found) >= max_files:
            break
        if path in declares:
            continue
        # exclude_paths excludes CANDIDATE CALLERS (below) from matching a
        # changed file against itself or another changed file -- it must not
        # also skip the changed files themselves here, or this loop never runs.
        text = repo.file_at(rev, path)
        if not text:
            continue
        for sym in _exported_symbols(path, text,
                                     (hunk_ranges or {}).get(path)):
            # A lowercase Go func is PACKAGE-private, not repo-private: only
            # a caller in the same directory (this codebase's packages are
            # one-per-directory) can legitimately reference it at all. Search
            # repo-wide only for a symbol that could actually be called from
            # anywhere -- an uppercase Go func, or any TS/JS export.
            same_pkg_only = path.endswith(".go") and sym[:1].islower()
            pkg_dir = str(Path(path).parent) if same_pkg_only else None
            hits = repo.grep_at(rev, r"\b" + re.escape(sym) + r"\b")
            by_path: dict[str, list[int]] = {}
            for hp, hline, htext in hits:
                if hp in exclude_paths or hp in seen:
                    continue
                if same_pkg_only and str(Path(hp).parent) != pkg_dir:
                    continue
                if htext.lstrip().startswith(_COMMENT_PREFIXES):
                    continue
                by_path.setdefault(hp, []).append(hline)
            for hp, ref_lines in sorted(by_path.items()):
                body = repo.file_at(rev, hp) or ""
                if not _imports_symbol_from(body, hp, sym, path):
                    continue
                sites = flag_sites(repo, profile, st, rev, [hp])
                if not sites:
                    continue
                lines = body.splitlines()
                derived = _flag_derived_vars(sites)

                ref_line, matched_keys, pick = None, set(), None
                for rl in ref_lines:
                    cond = _conditional_use_line(lines, rl, derived, radius=8)
                    if cond:
                        ref_line, key = cond
                        matched_keys = {key}
                        break
                if ref_line is None:
                    for rl in sorted(ref_lines, key=lambda l: bool(
                            _IMPORT_RE.match(lines[l - 1] if l <= len(lines)
                                             else ""))):
                        near = [s for s in sites if abs(s["line"] - rl) <= window // 2]
                        if near:
                            ref_line = rl
                            # Credit only the nearest check at or above the
                            # reference -- the conditional that wraps a usage
                            # precedes it -- falling back to the nearest
                            # overall.
                            above = [s for s in near if s["line"] <= rl]
                            inside = [s for s in near
                                      if rl < s["line"] <= _block_end(lines, rl)]
                            pick = (min(s["line"] for s in inside) if inside else
                                    max(s["line"] for s in above) if above
                                    else min(near, key=lambda s:
                                             abs(s["line"] - rl))["line"])
                            matched_keys = {s["key"] for s in near
                                            if s["key"] and s["line"] == pick}
                            break
                if ref_line is None:
                    continue

                if _in_import(lines, ref_line):
                    lo, hi = _window_over_use(
                        ref_line, pick,
                        [rl for rl in ref_lines if not _in_import(lines, rl)],
                        len(lines), window)
                else:
                    lo = max(1, ref_line - window // 2)
                    hi = min(len(lines), ref_line + window // 2)
                found.append({"path": hp, "lo": lo, "hi": hi,
                             "text": "\n".join(lines[lo - 1:hi]),
                             "matched_symbol": sym,
                             "gate_keys": sorted(matched_keys),
                             # Lines of the flag evaluations themselves, so a
                             # citation of the flag call counts as gate-shaped
                             # (see sources.verify_citation).
                             "gate_lines": sorted(s["line"] for s in sites
                                                  if lo <= s["line"] <= hi)})
                seen.add(hp)
                if len(found) >= max_files:
                    break
            if len(found) >= max_files:
                break
    return sorted(found, key=lambda r: r["path"])


MAX_CALLER_GATES = 10     # entries in the caller-gate evidence, per diff
MAX_GATES_PER_ENTRY = 2   # nearest evaluations above one call or hunk
GATE_EXCERPT_AFTER = 6    # lines shown after an evaluation (its early return)

# Function declarations, by extension: (decl pattern, function-end pattern).
# Group 1 (or 2) is the name. The end pattern marks a top-level function's
# closing line; None means enclosure is decided by indentation (Python).
_FUNC_DECLS: dict[str, tuple[re.Pattern, re.Pattern | None]] = {
    ".go": (re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*[\[(]"),
            re.compile(r"^\}")),
    ".py": (re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\("), None),
}
_TS_DECL = (re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*"
    r"([A-Za-z_$][\w$]*)\s*[<(]"
    r"|^\s*(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*"
    r"(?::[^=]+)?=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*"
    r"(?::[^=]+)?=>"),
    re.compile(r"^\}(?!.*\{\s*$)"))
for _ext in (".ts", ".tsx", ".js", ".jsx"):
    _FUNC_DECLS[_ext] = _TS_DECL


_MARKS: dict[tuple[int, str], tuple[list[str], list[int]]] = {}


def _marked_lines(lines: list[str], ext: str) -> list[int]:
    """Indexes of the lines `_function_at` acts on (a declaration or a block
    end), ascending, computed once per file. Every other line it skips, so
    visiting only these gives the same answer: rescanning a whole file per
    changed line was quadratic (an earlier PR's 51k-line catalog: 2.6 billion
    regex matches, 15 minutes)."""
    hit = _MARKS.get((id(lines), ext))
    if hit and hit[0] is lines:
        return hit[1]
    decl_re, end_re = _FUNC_DECLS[ext]
    marks = [i for i, t in enumerate(lines) if (end_re and end_re.match(t)) or decl_re.match(t)]
    _MARKS[(id(lines), ext)] = (lines, marks)  # holding `lines` keeps its id from being reused
    return marks


def _function_at(lines: list[str], line_1idx: int, ext: str
                 ) -> tuple[int, str] | None:
    """(start line, name) of the function enclosing `line_1idx`, or None."""
    decl = _FUNC_DECLS.get(ext)
    if not decl:
        return None
    decl_re, end_re = decl
    want_indent = None
    if end_re is None and 0 < line_1idx <= len(lines):
        t = lines[line_1idx - 1]
        want_indent = len(t) - len(t.lstrip())
    marks = _marked_lines(lines, ext)
    top = min(line_1idx, len(lines)) - 1
    for i in reversed(marks[:bisect.bisect_right(marks, top)]):
        if end_re and i < line_1idx - 1 and end_re.match(lines[i]):
            return None
        m = decl_re.match(lines[i])
        if not m:
            continue
        indent = len(lines[i]) - len(lines[i].lstrip())
        if want_indent is not None and i < line_1idx - 1 \
                and indent >= want_indent:
            continue
        if end_re is not None and indent > 0 and i < line_1idx - 1 \
                and lines[i].rstrip().endswith("{") \
                and _block_end(lines, i + 1) < line_1idx:
            continue
        if end_re is not None and indent > 0 and i < line_1idx - 1 \
                and not lines[i].rstrip().endswith("{") \
                and _nested_decl_ends_before(lines, i, indent, line_1idx):
            continue
        return i + 1, next(g for g in m.groups() if g)
    return None


def _nested_decl_ends_before(lines: list[str], i: int, indent: int, line_1idx: int) -> bool:
    """Does the declaration at index `i` (indented `indent`, its line opening
    no block) end before `line_1idx`? It ends at the first later line at its
    own indent or less, unless that line opens the body (`) => {`), in which
    case it ends where that block closes."""
    # Clamped: a deletion at the end of a file is placed past its last line.
    for j in range(i + 1, min(line_1idx, len(lines))):
        t = lines[j]
        if not t.strip() or _indent(t) > indent:
            continue
        if t.lstrip().startswith((")", "}")) and t.rstrip().endswith("=>"):
            continue  # `) =>` closing a multi-line parameter list
        if j == line_1idx - 1:
            # The line itself, at the declaration's indent: a sibling
            # statement (`const helper = () => x;` then the line), unless it
            # closes the declaration's own brackets.
            return not t.lstrip().startswith((")", "}", "]"))
        if t.rstrip().endswith("{"):
            return _block_end(lines, j + 1) < line_1idx
        return True
    return False


def find_caller_gates(repo: Repo, rev: str, hunks: list[Hunk],
                      head_sites: list[dict], base_sites: list[dict]
                      ) -> list[dict]:
    """Flag evaluations that run BEFORE changed code, inside the changed
    files: earlier in the changed function itself, or in a function (in a
    changed file) that calls it.

    Evidence, not a verdict: each entry shows the evaluation, the lines after
    it, and the call. Whether it dominates is the predicate's judgment.
    One hop, changed files only, same as referenced context's bound.
    """
    texts: dict[str, list[str]] = {}

    def lines_of(path):
        if path not in texts:
            texts[path] = (repo.file_at(rev, path) or "").splitlines()
        return texts[path]

    sites_by_path: dict[str, list[dict]] = {}
    for s in head_sites:
        if s.get("key"):
            sites_by_path.setdefault(s["path"], []).append(s)
    base_keys = {s["key"] for s in base_sites if s.get("key")}
    paths = sorted({h.path for h in hunks if Path(h.path).suffix in _FUNC_DECLS})

    changed_fns: dict[tuple[str, str], tuple[int, int]] = {}
    for h in hunks:
        ext = Path(h.path).suffix
        if ext not in _FUNC_DECLS:
            continue
        L = lines_of(h.path)
        for n in _changed_new_lines(h):
            fn = _function_at(L, n, ext)
            if fn:
                key = (h.path, fn[1])
                start, first = changed_fns.get(key, (fn[0], n))
                changed_fns[key] = (start, min(first, n))

    def gates_before(path, lo, hi):
        L = lines_of(path)
        g = [s for s in sites_by_path.get(path, []) if lo <= s["line"] < hi
             and _dominance_shaped(L, s["line"], hi)]
        return sorted(g, key=lambda s: s["line"])[-MAX_GATES_PER_ENTRY:]

    def excerpt(path, gates, until, extra=()):
        L = lines_of(path)
        keep: set[int] = set()
        for s in gates:
            keep |= set(range(s["line"], min(s["line"] + GATE_EXCERPT_AFTER,
                                             until) + 1))
        keep |= {x for x in extra if 1 <= x <= len(L)}
        return [(n, L[n - 1]) for n in sorted(keep) if 1 <= n <= len(L)]

    out: list[dict] = []
    for (path, name), (start, first) in sorted(changed_fns.items()):
        g = gates_before(path, start, first)
        if g:
            out.append({"kind": "same-function", "path": path,
                        "function": name, "changed_at": first,
                        "keys": sorted({s["key"] for s in g}),
                        "keys_at_merge_base": sorted({s["key"] for s in g}
                                                     & base_keys),
                        "lines": excerpt(path, g, first, (first,))})
        # Callers of the changed function in the changed files. A lowercase
        # Go func is package-private: callers must share its directory.
        call_re = re.compile(r"\b" + re.escape(name) + r"\s*\(")
        pkg_only = path.endswith(".go") and name[:1].islower()
        for q in paths:
            if pkg_only and Path(q).parent != Path(path).parent:
                continue
            Q = lines_of(q)
            # One entry per calling function: its FIRST call, which the
            # fewest evaluations precede, is the one a gate must dominate.
            calls: dict[tuple[int, str], list[int]] = {}
            for i, t in enumerate(Q, start=1):
                if not call_re.search(t) or t.lstrip().startswith(
                        _COMMENT_PREFIXES + ("#",)):
                    continue
                caller = _function_at(Q, i, Path(q).suffix)
                if not caller or caller[1] == name:
                    continue            # the declaration itself, or recursion
                calls.setdefault(caller, []).append(i)
            for (cstart, cname), at in sorted(calls.items()):
                g = gates_before(q, cstart, at[0])
                if not g:
                    continue
                out.append({"kind": "caller", "path": q,
                            "function": cname, "call_line": at[0],
                            "other_calls": at[1:],
                            "callee": name, "callee_path": path,
                            "keys": sorted({s["key"] for s in g}),
                            "keys_at_merge_base": sorted(
                                {s["key"] for s in g} & base_keys),
                            "lines": excerpt(q, g, at[0], (at[0],))})
                if len(out) >= MAX_CALLER_GATES:
                    return out
    return out[:MAX_CALLER_GATES]


MAX_OUTSIDE_NAMES = 8     # changed functions whose outside callers are searched
MAX_OUTSIDE_HITS = 10     # call sites followed per searched name
MAX_OUTSIDE_ENTRIES = 6   # entries from further up the call chain, per diff
MAX_ALSO_CHAINS = 12      # other changed functions named on one such entry
MAX_CALLER_DEPTH = 3      # levels of callers walked from a changed function


def _changed_functions(repo: Repo, rev: str, hunks: list[Hunk]
                       ) -> dict[tuple[str, str], tuple[int, int]]:
    """(path, function) -> (its start line, first changed line in it)."""
    out: dict[tuple[str, str], tuple[int, int]] = {}
    texts: dict[str, list[str]] = {}
    for h in hunks:
        ext = Path(h.path).suffix
        if ext not in _FUNC_DECLS:
            continue
        L = texts.setdefault(h.path, (repo.file_at(rev, h.path) or "").splitlines())
        for n in _changed_new_lines(h):
            fn = _function_at(L, n, ext)
            if fn:
                start, first = out.get((h.path, fn[1]), (fn[0], n))
                out[(h.path, fn[1])] = (start, min(first, n))
    return out


_EXIT_RE = re.compile(r"^\s*(?:return\b|continue\b|break\b|throw\b|raise\b|panic\()")
_COND_RE = re.compile(r"^\s*(?:\}\s*else\s+)?if\b|^\s*\{?\s*!?\s*[\w.]+(?:\(\))?\s*&&"
                      # a ternary whose arms follow: `return on ? (` / `on ? <A` --
                      # not `?.` (optional chaining) or `?:` (an optional type)
                      r"|^\s*(?:return\s+)?\(?\s*!?\s*[\w.]+(?:\(\))?\s*\?\s*(?:\(|<|$)")
_TERNARY_RE = re.compile(r"\?\s*(?:\(|<|$)")
_ELSE_ARM_RE = re.compile(r"^\s*\)?\s*:\s*(?:\(|<|$|null|undefined)")
_ASSIGNED_RE = re.compile(r"^\s*(?:const|let|var)?\s*([A-Za-z_]\w*)(?:\s*,\s*\w+)?\s*:?=")
_MULTI_ASSIGN_RE = re.compile(
    r"^\s*(?:const|let|var)?\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*:?=(?!=)")
_RETURN_RE = re.compile(r"^\s*return\b")
_CASE_RE = re.compile(r"^\s*case\s+(.+?)\s*:\s*(?://.*)?$")


def _indent(t: str) -> int:
    return len(t) - len(t.lstrip())


DECIDING_WINDOW = 12  # lines after an assigned evaluation searched for its test


def _deciding_conditionals(L: list[str], ev_line: int, limit: int) -> list[int]:
    """."""
    if _COND_RE.match(L[ev_line - 1]):
        return [ev_line]
    m = _ASSIGNED_RE.match(L[ev_line - 1])
    if not m:
        return []
    var = re.compile(r"\b" + re.escape(m.group(1)) + r"\b")
    return [n for n in range(ev_line + 1, min(ev_line + DECIDING_WINDOW + 1, limit))
            if _COND_RE.match(L[n - 1]) and var.search(L[n - 1])]


def _deciding_conditional(L: list[str], ev_line: int, limit: int) -> int | None:
    """The first of _deciding_conditionals, or None."""
    c = _deciding_conditionals(L, ev_line, limit)
    return c[0] if c else None


MAX_BLOCK_SCAN = 40  # lines of a conditional's block read for an early exit


def _block_exits(L: list[str], cond: int, limit: int) -> bool:
    """."""
    ind = _indent(L[cond - 1])
    for i in range(cond, min(cond + MAX_BLOCK_SCAN, limit - 1)):
        t = L[i]
        if t.strip() and _indent(t) <= ind:
            return False              # the conditional's block ended
        if _EXIT_RE.match(t):
            return True
    return False


MAX_SIBLING_FILES = 60
"""A package directory larger than this is not scanned for sibling helpers:
the cost grows with it and a helper that far away is rarely a gate."""


def _sibling_sites(repo: Repo, profile: Profile, st: SymbolTable, rev: str,
                   paths: list[str]) -> list[dict]:
    """Flag sites in the other non-test Go files of each changed Go file's
    package directory, for finding gate helpers defined there."""
    dirs = sorted({str(Path(p).parent) for p in paths if p.endswith(".go")})
    sibs: list[str] = []
    for d in dirs:
        try:
            names = repo.git("ls-tree", "--name-only", rev, "--", d.rstrip("/") + "/",
                             check=False).splitlines()
        except Exception:
            continue
        files = [n for n in names if n.endswith(".go") and not n.endswith("_test.go")
                 and n not in paths]
        if len(files) <= MAX_SIBLING_FILES:
            sibs += files
    return flag_sites(repo, profile, st, rev, sibs, _siblings=False) if sibs else []


def _helper_gate_sites(repo: Repo, rev: str, paths: list[str],
                       sites: list[dict], extra_sites: list[dict] | None = None
                       ) -> list[dict]:
    """Calls to a GATE HELPER, as flag sites of the key(s) it evaluates."""
    texts: dict[str, list[str]] = {}

    def lines_of(path):
        if path not in texts:
            texts[path] = (repo.file_at(rev, path) or "").splitlines()
        return texts[path]

    helpers: dict[str, dict] = {}     # name -> {"keys": [...], "cases": {key: label}}

    def add(name, key, case=None):
        h = helpers.setdefault(name, {"keys": [], "cases": {}})
        if key not in h["keys"]:
            h["keys"].append(key)
        if case:
            h["cases"].setdefault(key, case)

    sibling = {id(x) for x in extra_sites or []}
    for x in list(sites) + list(extra_sites or []):
        ext = Path(x["path"]).suffix
        if not x.get("key") or ext not in _FUNC_DECLS:
            continue
        L = lines_of(x["path"])
        fn = _function_at(L, x["line"], ext)
        if not fn or fn[1] in _GENERIC_SYMBOLS:
            continue
        cond = _deciding_conditional(L, x["line"], len(L) + 1)
        am = _MULTI_ASSIGN_RE.match(L[x["line"] - 1])
        first = am.group(1).split(",")[0].strip() if am else None
        # In a sibling file, only a helper that RETURNS the flag's value is
        # one: a flag there that decides an early return usually picks the
        # helper's own implementation (a store method's query path, a quota
        # check), which does not gate whoever calls it.
        if cond and _block_exits(L, cond, len(L) + 1) and id(x) not in sibling:
            add(fn[1], x["key"])
        elif first and first not in ("_", "err") and any(
                re.match(r"^\s*return\s+" + re.escape(first) + r"\b", L[n - 1])
                for n in range(x["line"] + 1, _block_end(L, fn[0]) + 1)):
            add(fn[1], x["key"])
        elif _RETURN_RE.match(L[x["line"] - 1]):
            case = next((m.group(1) for n in range(x["line"] - 1,
                                                   max(fn[0], x["line"] - 4), -1)
                         for m in [_CASE_RE.match(L[n - 1])] if m), None)
            add(fn[1], x["key"], case)
    # Second order: a function that returns a call to a helper is one too.
    helper_paths = list(dict.fromkeys(list(paths) + [x["path"] for x in extra_sites or []]))
    for _ in range(2):
        for path in helper_paths:
            ext = Path(path).suffix
            if ext not in _FUNC_DECLS:
                continue
            L = lines_of(path)
            for i, t in enumerate(L, 1):
                if not _RETURN_RE.match(t):
                    continue
                for name in list(helpers):
                    if re.search(r"\b" + re.escape(name) + r"\s*\(", t):
                        fn = _function_at(L, i, ext)
                        if fn and fn[1] != name and fn[1] not in _GENERIC_SYMBOLS:
                            for k in helpers[name]["keys"]:
                                add(fn[1], k)
    out = []
    for path in paths:
        if Path(path).suffix not in _FUNC_DECLS:
            continue
        L = lines_of(path)
        for name, h in helpers.items():
            call = re.compile(r"\b" + re.escape(name) + r"\s*\(")
            for i, t in enumerate(L, 1):
                if not call.search(t) or t.lstrip().startswith(_COMMENT_PREFIXES):
                    continue
                at = None
                if _COND_RE.match(t) and _block_exits(L, i, len(L) + 1):
                    at = i
                else:
                    m = _MULTI_ASSIGN_RE.match(t)
                    names = [n.strip() for n in (m.group(1).split(",") if m else [])
                             if n.strip() not in ("_", "err")]
                    for n in range(i + 1, min(i + GATE_EXCERPT_AFTER + 1, len(L) + 1)):
                        u = L[n - 1]
                        if names and _COND_RE.match(u) and any(
                                re.search(r"\b" + re.escape(v) + r"\b", u) for v in names) \
                                and _block_exits(L, n, len(L) + 1):
                            at = n
                            break
                        if names and re.match(r"^\s*switch\s+(" + "|".join(
                                re.escape(v) for v in names) + r")\b", u):
                            at = n
                            break
                if at is None:
                    continue
                cases = "; ".join(f"{h['cases'][k]} -> {k}" for k in h["keys"]
                                  if k in h["cases"])
                for k in h["keys"]:
                    out.append({"path": path, "line": at, "symbol": name,
                                "key": k, "source": "gate-helper",
                                "cases": dict(h["cases"]) if len(h["keys"]) > 1 else {},
                                "text": (t.strip() if at == i else
                                         f"{t.strip()} ... {L[at - 1].strip()}")[:200]
                                + (f"  [{name} returns by case: {cases}]" if cases else "")})
    return out


def _enclosing_case(L: list[str], line: int, fn_start: int,
                    labels: list[str]) -> str | None:
    """The case label whose branch encloses `line`: the nearest enclosing
    opener (a line less indented than the code it opens) that tests one of
    `labels` with `==` or `case`, or the `else` of a test of the other label
    when there are exactly two. None when no enclosing branch names one."""
    def names(t, lab):
        tail = re.escape(lab.split(".")[-1])
        return re.search(r"(?:==\s*(?:\w+\.)?" + tail + r"\b|\b" + tail
                         + r"\s*==|^\s*case\s+.*\b" + tail + r"\b)", t)
    cur = _indent(L[line - 1])
    for i in range(line - 1, fn_start - 1, -1):
        t = L[i - 1]
        if not t.strip() or _indent(t) >= cur:
            continue
        cur = _indent(t)
        hit = [lab for lab in labels if names(t, lab)]
        if len(hit) == 1 and "!=" not in t:
            return hit[0]
        if t.lstrip().startswith("} else") and len(labels) == 2:
            for j in range(i - 1, fn_start - 1, -1):     # its `if`
                u = L[j - 1]
                if u.strip() and _indent(u) == cur and _COND_RE.match(u):
                    other = [lab for lab in labels if names(u, lab)]
                    if len(other) == 1:
                        return next(x for x in labels if x != other[0])
                    break
    return None


def _narrow_case_sites(repo: Repo, rev: str, sites: list[dict],
                       hunks: list[Hunk]) -> list[dict]:
    """Keep, of a gate helper's per-case keys at one call site, only the key
    whose case every changed line after it in that function runs under.

    an earlier PR's handlers return 404 unless isTwoStepSetupEnabled(ctx,
    key), which returns the snowflake flag or the redshift one by case; the
    changed validation sits in the redshift branch. Offering both put the
    snowflake flag -- served to every user -- in front of P7/P8 as part of
    the gate, and P8 read the gate as exposing. Unresolved cases keep every
    key: which one applies is then the reading predicate's call."""
    groups: dict[tuple[str, int], list[dict]] = {}
    for x in sites:
        if x.get("cases"):
            groups.setdefault((x["path"], x["line"]), []).append(x)
    drop: set[int] = set()
    for (path, line), grp in groups.items():
        L = (repo.file_at(rev, path) or "").splitlines()
        fn = _function_at(L, line, Path(path).suffix)
        if not fn:
            continue
        cases = grp[0]["cases"]
        labels = sorted(set(cases.values()))
        changed = [n for h in hunks if h.path == path for n in _changed_new_lines(h)
                   if n > line and (_function_at(L, n, Path(path).suffix) or (0, ""))[0] == fn[0]]
        found = {_enclosing_case(L, n, fn[0], labels) for n in changed if L[n - 1].strip()}
        if len(found) == 1 and None not in found:
            keep = {k for k, lab in cases.items() if lab in found}
            drop |= {id(x) for x in grp if x["key"] not in keep}
    return [x for x in sites if id(x) not in drop]


def _same_line_gate(text: str, symbol: str, name: str) -> bool:
    """Does the evaluation of `symbol` on this line gate the call or render of
    `name` on the same line: `flag() ? <Name ...` or `flag() && <Name ...` (or
    `Name(`), with `name` in the arm that runs only when the flag is on?

    _dominance_shaped needs the evaluation on an earlier line, so a one-line
    JSX conditional was never a gate. Measured on an earlier PR: the
    settings route renders the changed EnvironmentReleasePlansCollection only
    in `{enableEnvironmentReleasePlans() ? <EnvironmentReleasePlansCollection
    /> : <ReleasePoliciesCollection />}`. Structure only, and only the true
    arm of a condition that is the bare evaluation: a negated `!flag() ? ...`
    or a compound condition is not read as a gate."""
    if not symbol or not name:
        return False
    m = re.search(
        r"(?<![!\w.$])(?:[\w$]+\.)*" + re.escape(symbol) + r"\s*\(\s*\)\s*"
        r"(?:\?\s*|&&\s*)\(?\s*(?:<" + re.escape(name) + r"(?=[\s/>]|$)|"
        + re.escape(name) + r"\s*\()", text)
    if not m:
        return False
    # `a || flag() ? <Name/>` renders Name without the flag: the condition,
    # back to where its expression starts, must not have an alternative.
    cond = re.split(r"[{(=]|\breturn\b", text[:m.start()])[-1]
    return "||" not in cond and "??" not in cond


def _dominance_shaped(L: list[str], ev_line: int, call_line: int) -> bool:
    """Is an evaluation at `ev_line` SHAPED like a gate over `call_line`?"""
    if not (0 < ev_line < call_line <= len(L)):
        return False
    return any(_dominates(L, cond, call_line)
               for cond in _deciding_conditionals(L, ev_line, call_line))


def _dominates(L: list[str], cond: int, call_line: int) -> bool:
    """Does the conditional at `cond` gate `call_line` (see _dominance_shaped)?"""
    ind = _indent(L[cond - 1])
    between = [L[i] for i in range(cond, call_line - 1) if L[i].strip()]
    if any(_indent(t) < ind for t in between):
        return False
    if _block_exits(L, cond, call_line):
        return True
    ternary = bool(_TERNARY_RE.search(L[cond - 1])) and not \
        L[cond - 1].lstrip().startswith(("if", "} else"))
    if ternary and any(_ELSE_ARM_RE.match(t) for t in between):
        return False                  # the target is in the ternary's else arm
    return (bool(between) or ternary or L[cond - 1].rstrip().endswith(("(", "{", "&&"))) \
        and all(_indent(t) > ind for t in between) \
        and _indent(L[call_line - 1]) > ind


def reported_calls(caller_gates: list[dict]) -> set[tuple[str, int]]:
    """Every (path, line) find_caller_gates reported a gated call at: each
    `caller` entry's first call and its `other_calls`, for the outside
    walk's skip set (find_outside_caller_gates' `reported`)."""
    return {(g["path"], n) for g in caller_gates if g.get("kind") == "caller"
            for n in [g["call_line"], *(g.get("other_calls") or [])]}


def find_outside_caller_gates(repo: Repo, profile: Profile, st: SymbolTable,
                              rev: str, hunks: list[Hunk],
                              changed_paths: set[str],
                              keys_at_base: set[str],
                              visited: set[str] | None = None,
                              reported: set[tuple[str, int]] | None = None) -> list[dict]:
    """Gates further up the call chain into changed code: walk callers of each
    changed function, breadth-first, up to MAX_CALLER_DEPTH levels, and
    report the first flag evaluation that precedes the call at each branch.

    Direct callers inside the changed files are find_caller_gates' job; this
    reports everything else. Bounded: a capped number of names per level and
    hits per name, same-package only for a package-private Go name, generic
    names skipped, a branch stops at its first gate. Evidence for the
    gate-dependent predicates, not a verdict.
    """
    ev = profile.data.get("evaluation", {})
    texts: dict[str, list[str]] = {}
    site_cache: dict[str, list[dict]] = {}

    def lines_of(path):
        if path not in texts:
            texts[path] = (repo.file_at(rev, path) or "").splitlines()
        return texts[path]

    def sites_of(path):
        if path not in site_cache:
            site_cache[path] = [x for x in flag_sites(repo, profile, st, rev, [path],
                                                      method_helpers=True)
                                if x.get("key")]
        return site_cache[path]

    def callers(name, home):
        pkg_only = home.endswith(".go") and name[:1].islower()
        out = []
        pat = r"\b" + re.escape(name) + r"\s*\("
        if Path(home).suffix in _JS_EXTS and name[:1].isupper():
            pat = r"(?:" + pat + r"|<" + re.escape(name) + r"(?=[\s/>]|$))"
        for hp, hl, ht in repo.grep_at(rev, pat):
            if not _in_scope(hp, ev) or Path(hp).suffix not in _FUNC_DECLS \
                    or hp.endswith("_test.go") or ".test." in hp or ".spec." in hp \
                    or ".stories." in hp:
                continue
            if pkg_only and Path(hp).parent != Path(home).parent:
                continue
            if hp != home and ht.find("<" + name) >= 0 and not ht.find(name + "(") >= 0 \
                    and not _imports_symbol_from("\n".join(lines_of(hp)), hp, name, home):
                continue
            if ht.lstrip().startswith(_COMMENT_PREFIXES + ("#",)):
                continue
            fn = _function_at(lines_of(hp), hl, Path(hp).suffix)
            if fn and fn[1] != name:
                out.append((hp, hl, fn))
            if len(out) >= MAX_OUTSIDE_HITS:
                break
        return out

    def gates_before(path, lo, hi, name):
        L = lines_of(path)
        g = [x for x in sites_of(path) if (lo <= x["line"] < hi
             and _dominance_shaped(L, x["line"], hi))
             or (x["line"] == hi and _same_line_gate(L[hi - 1], x.get("symbol") or "", name))]
        return sorted(g, key=lambda x: x["line"])[-MAX_GATES_PER_ENTRY:]

    def entry(path, fn, call_line, chain, gates):
        L = lines_of(path)
        keep: set[int] = {call_line}
        for g in gates:
            keep |= set(range(g["line"], min(g["line"] + GATE_EXCERPT_AFTER,
                                             call_line) + 1))
        keys = sorted({g["key"] for g in gates})
        return {"kind": "outside-caller", "path": path, "function": fn[1],
                "call_line": call_line, "callee": chain[0], "chain": chain,
                "keys": keys, "keys_at_merge_base": sorted(set(keys) & keys_at_base),
                "gate_lines": [g["line"] for g in gates],
                "lines": [(n, L[n - 1]) for n in sorted(keep) if 1 <= n <= len(L)]}

    out: list[dict] = []
    frontier = [(n, p, [n]) for (p, n) in sorted(_changed_functions(repo, rev, hunks))
                if n not in _GENERIC_SYMBOLS][:MAX_OUTSIDE_NAMES]
    seen = {(p, n) for n, p, _ in frontier}
    emitted: dict[tuple[str, int], dict] = {}
    for depth in range(1, MAX_CALLER_DEPTH + 1):
        nxt = []
        for name, home, chain in frontier:
            for hp, hl, fn in callers(name, home):
                if visited is not None:
                    visited.add(hp)   # find_registered_guards reads these files
                g = gates_before(hp, fn[0], hl, name)
                if g:
                    # A gated direct caller in a changed file is already
                    # find_caller_gates' entry.
                    if (hp, hl) in emitted:
                        e = emitted[(hp, hl)]
                        if chain[0] != e["callee"] and all(c[0] != chain[0] for c in e["also"]) \
                                and len(e["also"]) < MAX_ALSO_CHAINS:
                            e["also"].append(chain + [fn[1]])
                    # A direct caller in a changed file is skipped only when
                    # find_caller_gates reported that call (`reported`): it
                    # matches `name(` with the evaluation on an earlier line,
                    # so a render or a one-line `flag() ? <Name/>` in a
                    # changed parent is this walk's to report.
                    elif depth > 1 or hp not in changed_paths or (hp, hl) not in (reported or set()):
                        e = entry(hp, fn, hl, chain + [fn[1]], g)
                        e["also"] = []
                        emitted[(hp, hl)] = e
                        out.append(e)
                        if len(out) >= MAX_OUTSIDE_ENTRIES:
                            return out
                elif (hp, fn[1]) not in seen and fn[1] not in _GENERIC_SYMBOLS:
                    seen.add((hp, fn[1]))
                    nxt.append((fn[1], hp, chain + [fn[1]]))
        frontier = nxt[:MAX_OUTSIDE_NAMES]
    return out


MAX_GUARD_FILES = 40      # sibling files read for guards, per changed directory
MAX_GUARD_REFS = 6        # lines attaching one guard, shown per guard
MAX_GUARD_ENTRIES = 6     # registered-guard entries, per diff
MAX_ATTACH_CALLS = 3      # call sites shown of the function that attaches a guard
_VALUE_REF_TAIL = re.compile(r"^\s*(?:[,;)}\]]|$)")
_MODULE_ALIAS_RE = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*(?::[^=]+)?=\s*([A-Za-z_$][\w$]*)\s*;?\s*$"
    r"|^export\s*\{\s*([A-Za-z_$][\w$]*)\s+as\s+[A-Za-z_$][\w$]*\s*\}")
_DEFINITION_RE = r"(?:\bfunction\s*\*?\s*{n}\s*[<(]|\b(?:const|let|var)\s+{n}\s*[:=]|^func\s+(?:\([^)]*\)\s*)?{n}\s*[\[(])"


def find_registered_guards(repo: Repo, profile: Profile, st: SymbolTable,
                           rev: str, ship_paths: list[str],
                           walk_paths: set[str],
                           keys_at_base: set[str]) -> list[dict]:
    """    Two ways a guard is tied to the change, both structural:
      - attached at module level in a changed file, or in a file the caller
        walk reached (`walk_paths`): a route module's registration applies
        to the module it is in;
      - in Go, a wrapper (middleware: it takes the next handler and calls it
        only when its check allows) defined in the same package as changed
        shipping code: then every line that attaches it is shown, with the
        attaching function's call sites.
    Evidence for P6, not a verdict: whether the attached guard runs before
    the changed code is P6's judgment, as for every caller-gate entry.
    """
    ev = profile.data.get("evaluation", {})
    texts: dict[str, list[str]] = {}

    def lines_of(path):
        if path not in texts:
            texts[path] = (repo.file_at(rev, path) or "").splitlines()
        return texts[path]

    ships = set(profile.data.get("roles_that_ship") or ["ships"])

    def shipping(path):
        return _in_scope(path, ev) and Path(path).suffix in _FUNC_DECLS \
            and profile.role_of(path) in ships and "/__tests__/" not in path \
            and not path.endswith("_test.go") and ".test." not in path \
            and ".spec." not in path and ".stories." not in path

    def wraps(L, start, end):
        """Does the function at `start` take a function-typed parameter and
        call it -- `func Require(next Handler) Handler { ... next(w, r) }`?
        That is a wrapper (middleware), which runs the code it is attached
        to only on the path its check allows. A handler that merely returns
        early on a flag is not: it gates its own body, not what it is
        registered beside (an earlier PR's segment handlers)."""
        sig = " ".join(t.strip() for t in L[start - 1:min(start + 2, end)])
        m = re.search(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)", sig)
        names = [x.split()[0] for x in (m.group(1).split(",") if m else [])
                 if len(x.split()) >= 2 and re.search(r"\b(?:func|Handler|HandlerFunc|Middleware)\b", x)]
        body = "\n".join(L[start:end])
        return any(re.search(r"\b" + re.escape(n) + r"(?:\.ServeHTTP)?\s*\(", body) for n in names)

    def guards_in(path, only=None, wrapper=False):
        """{name: (fn_start, site, cond, exit_line)} for guard-shaped
        functions in `path` (with `wrapper`, only wrappers)."""
        L, ext = lines_of(path), Path(path).suffix
        out = {}
        for x in flag_sites(repo, profile, st, rev, [path], method_helpers=True):
            if not x.get("key"):
                continue
            fn = _function_at(L, x["line"], ext)
            if not fn or fn[1] in out or (only and fn[1] != only):
                continue
            end = _block_end(L, fn[0]) if _FUNC_DECLS[ext][1] is not None else len(L)
            if end <= fn[0]:
                end = min(len(L), fn[0] + 80)
            if wrapper and not wraps(L, fn[0], end):
                continue
            for c in _deciding_conditionals(L, x["line"], end + 1):
                if _block_exits(L, c, end + 1):
                    ex = next((i for i in range(c + 1, min(c + MAX_BLOCK_SCAN, end) + 1)
                               if _EXIT_RE.match(L[i - 1])), c)
                    out[fn[1]] = (fn[0], x, c, ex)
                    break
        return out

    def value_refs(name, home):
        """Shipping lines naming `name` as a value, not calling, importing
        or defining it."""
        out = []
        defn = re.compile(_DEFINITION_RE.format(n=re.escape(name)))
        for hp, hl, ht in repo.grep_at(rev, r"\b" + re.escape(name) + r"\b"):
            if not shipping(hp) or ht.lstrip().startswith(_COMMENT_PREFIXES + ("#",)):
                continue
            if defn.search(ht) or re.match(r"^\s*(import\b|from\s+\S+\s+import\b|\})", ht):
                continue
            m = re.search(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])", ht)
            if m and _VALUE_REF_TAIL.match(ht[m.end():]):
                out.append((hp, hl, ht))
        return out

    def definition_of(name, spec, caller):
        """The file defining `name`, imported by `caller` from `spec`."""
        if spec.startswith("."):
            base = os.path.normpath(os.path.join(str(Path(caller).parent), spec))
            cands = [base] if Path(base).suffix else \
                [base + e for e in _HELPER_MODULE_EXTS] + [f"{base}/index{e}" for e in _HELPER_MODULE_EXTS]
            return next((c for c in cands if lines_of(c)), None)
        tail = _path_tail(_module_stem(spec))
        defs = {hp for hp, _, ht in repo.grep_at(rev, _DEFINITION_RE.format(n=re.escape(name)))
                if shipping(hp)}
        hits = [d for d in sorted(defs) if _path_tail(_module_stem(d)) == tail
                or _path_tail(str(Path(d).parent)) == tail]
        return hits[0] if len(hits) == 1 else None

    def guard_entry(path, name, g, refs):
        start, site, cond, ex = g
        L = lines_of(path)
        keep = {start, site["line"], cond, ex} | set(range(cond, min(ex, cond + GATE_EXCERPT_AFTER) + 1))
        # The other arm too: `if on { return next(...) }` refuses after its
        # block closes (flag_gate.go's forbidden error), so show that exit.
        close = _block_end(L, cond)
        after = next((i for i in range(close + 1, min(close + GATE_EXCERPT_AFTER, len(L)) + 1)
                      if _EXIT_RE.match(L[i - 1])), None)
        if after:
            keep |= set(range(close, after + 1))
        return {"kind": "registered-guard", "path": path, "function": name,
                "callee": name, "chain": [], "call_line": cond,
                "keys": [site["key"]],
                "keys_at_merge_base": [site["key"]] if site["key"] in keys_at_base else [],
                "gate_lines": sorted({site["line"], cond}),
                "attached_at": [(rp, rl, rt.strip()) for rp, rl, rt in refs[:MAX_GUARD_REFS]],
                "lines": [(n, L[n - 1]) for n in sorted(keep) if 1 <= n <= len(L)]}

    def attach_entry(rp, rl, name, key, home):
        L = lines_of(rp)
        keep = {rl}
        fn = _function_at(L, rl, Path(rp).suffix)
        calls = []
        if fn and fn[1] not in _GENERIC_SYMBOLS:
            keep.add(fn[0])
            for cp, cl, ct in repo.grep_at(rev, r"\b" + re.escape(fn[1]) + r"\s*\("):
                if cp == rp and cl == fn[0] or not shipping(cp):
                    continue
                calls.append((cp, cl))
                if cp == rp:
                    keep.add(cl)
                if len(calls) >= MAX_ATTACH_CALLS:
                    break
        return {"kind": "guard-attached", "path": rp, "function": fn[1] if fn else "",
                "callee": name, "chain": [], "call_line": rl, "guard_path": home,
                "keys": [key], "keys_at_merge_base": [key] if key in keys_at_base else [],
                "gate_lines": [rl], "attach_calls": calls,
                "lines": [(n, L[n - 1]) for n in sorted(keep) if 1 <= n <= len(L)]}

    found: dict[tuple[str, str], tuple[tuple, list]] = {}   # (home, name) -> (guard, refs)

    def emit(home, name, g, refs):
        _, have = found.setdefault((home, name), (g, []))
        have += [r for r in refs if r[:2] not in {x[:2] for x in have}]

    # A guard attached at module level in a changed file or a walked caller.
    for f in sorted(set(ship_paths) | set(walk_paths)):
        if not shipping(f) or not f.endswith(_HELPER_MODULE_EXTS):
            continue
        L = lines_of(f)
        imports = {local: spec for local, _, spec in _relative_imports("\n".join(L))}
        for m in re.finditer(r"""import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]""", "\n".join(L)):
            for part in m.group(1).split(","):
                bits = part.strip().split(" as ")
                if bits[0].strip():
                    imports.setdefault(bits[-1].strip(), m.group(2))
        for i, t in enumerate(L, 1):
            mm = _MODULE_ALIAS_RE.match(t)
            name = mm and (mm.group(1) or mm.group(2))
            if not name or name in _GENERIC_SYMBOLS or name not in imports:
                continue
            home = definition_of(name, imports[name], f)
            g = guards_in(home, name).get(name) if home else None
            if g:
                emit(home, name, g, [(f, i, t)])

    dirs = sorted({str(Path(p).parent) for p in ship_paths
                   if shipping(p) and p.endswith(".go")})
    for d in dirs:
        files = [x for x in repo.git("ls-tree", "--name-only", rev, "--", d.rstrip("/") + "/",
                                     check=False).splitlines() if shipping(x)]
        for f in files[:MAX_GUARD_FILES]:
            for name, g in guards_in(f, wrapper=True).items():
                if name in _GENERIC_SYMBOLS:
                    continue
                refs = [r for r in value_refs(name, f) if r[0] != f]
                if refs:
                    emit(f, name, g, refs)
    out: list[dict] = []
    for (home, name), (g, refs) in list(found.items())[:MAX_GUARD_ENTRIES]:
        out.append(guard_entry(home, name, g, refs))
        for rp, rl, _ in refs[:MAX_GUARD_REFS]:
            if rp != home:
                out.append(attach_entry(rp, rl, name, g[1]["key"], home))
    return out


MAX_API_NAMES = 12    # functions enclosing a changed line, per diff
MAX_API_CALLERS = 10  # caller hits followed per such function (one hop)


def _changed_new_lines(h: Hunk) -> list[int]:
    """New-file line numbers of the lines a hunk actually changes (a
    deletion is placed at the line that now follows it)."""
    out, n = [], h.new_start
    for raw in h.text.splitlines():
        tag = raw[:1]
        if tag == "+":
            out.append(n)
            n += 1
        elif tag == "-":
            out.append(n)
        elif tag == " ":
            n += 1
    return out


def _enclosing_decl(lines: list[str], line_1idx: int, decl_re: re.Pattern,
                    end_re: re.Pattern | None = None
                    ) -> tuple[int, str] | None:
    """Nearest declaration at or above `line_1idx`. With `end_re`, a
    function-closing line between the two means the line is NOT inside it
    (a top-level var after the last func, e.g. an embedded spec blob in
    generated code -- measured on an earlier PR)."""
    for i in range(min(line_1idx, len(lines)) - 1, -1, -1):
        if end_re and i < line_1idx - 1 and end_re.match(lines[i]):
            return None
        m = decl_re.match(lines[i])
        if m:
            return i + 1, m.group(1)
    return None


def _annotated_ops(lines: list[str], decl_1idx: int,
                   ann_re: re.Pattern | None) -> list[str]:
    """Operation ids named in the comment block directly above a
    declaration."""
    out = []
    i = decl_1idx - 2
    while ann_re and i >= 0 and lines[i].lstrip().startswith(_COMMENT_PREFIXES
                                                             + ("#",)):
        m = ann_re.search(lines[i])
        if m:
            out.append(m.group(1))
        i -= 1
    return out


DOC_DESCRIPTION_CAP = 160  # characters of each response's description


def _spec_ref(doc: dict, node):
    """A local `$ref` (`#/components/responses/X`) resolved one level, or the
    node itself."""
    ref = node.get("$ref") if isinstance(node, dict) else None
    if not (isinstance(ref, str) and ref.startswith("#/")):
        return node
    cur = doc
    for part in ref[2:].split("/"):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur if isinstance(cur, dict) else node


def _schema_name(schema) -> str | None:
    """A response schema's name: its `$ref`'s last segment, `array of X` for
    an array of one, else its plain type."""
    if not isinstance(schema, dict):
        return None
    if isinstance(schema.get("$ref"), str):
        return schema["$ref"].rsplit("/", 1)[-1]
    if schema.get("type") == "array":
        inner = _schema_name(schema.get("items"))
        return f"array of {inner}" if inner else "array"
    return schema.get("type") if isinstance(schema.get("type"), str) else None


def _doc_responses(doc: dict, op: dict) -> list[dict]:
    """An operation's documented responses, in spec order: status, its
    description (one line, capped) and the response schema's name. What
    P19's decision-7 exceptions are judged against: a response that
    contradicted these was a wrong answer."""
    out = []
    for status, r in (op.get("responses") or {}).items():
        r = _spec_ref(doc, r)
        if not isinstance(r, dict):
            continue
        schema = None
        for media in (r.get("content") or {}).values():
            schema = _schema_name((media or {}).get("schema"))
            if schema:
                break
        schema = schema or _schema_name(r.get("schema"))  # Swagger 2
        out.append({"status": str(status),
                    "description": " ".join(str(r.get("description") or "").split())[:DOC_DESCRIPTION_CAP],
                    "schema": schema})
    return out


def _spec_operations(repo: Repo, rev: str, paths: list[str]) -> dict[str, dict]:
    """operationId (lowercased) -> {operation_id, method, path, responses},
    from OpenAPI files (JSON or YAML) at `rev`."""
    ops: dict[str, dict] = {}
    for p in paths:
        text = repo.file_at(rev, p)
        if text is None:
            continue
        try:
            doc = json.loads(text) if p.endswith(".json") else specload.loads(text)
        except ValueError:  # YAML spec, no PyYAML (the skill bundle)
            continue
        for route, item in ((doc or {}).get("paths") or {}).items():
            for method, op in (item or {}).items():
                if isinstance(op, dict) and op.get("operationId"):
                    ops.setdefault(op["operationId"].lower(), {
                        "operation_id": op["operationId"],
                        "method": method.upper(), "path": route,
                        "responses": _doc_responses(doc, op)})
    return ops


def _route_binding(repo: Repo, rev: str, cfg: dict, decls: dict,
                   operation_id: str) -> dict:
    """How an operation's route is bound, from the profile's
    `route_binding` pattern, classified by its `user_credential_auth` /
    `internal_only_auth` lists. Empty when the profile declares no pattern
    or the binding isn't found (e.g. a hand-registered route)."""
    pat = cfg.get("route_binding")
    if not pat:
        return {}
    op_pascal = operation_id[:1].upper() + operation_id[1:]
    rx = pat.replace("{Op}", re.escape(op_pascal))
    hits = repo.grep_at(rev, rx, [f"*{ext}" for ext in decls] or None)
    if not hits:
        return {"binding": None}
    hp, hline, htext = hits[0]
    m = re.search(rx, htext)
    wrapper = m.group(1) if m else None
    auth = ("user-credential" if wrapper in (cfg.get("user_credential_auth")
                                             or []) else
            "internal-only" if wrapper in (cfg.get("internal_only_auth")
                                           or []) else "unclassified")
    return {"binding": f"{hp}:{hline}", "auth_wrapper": wrapper,
            "auth": auth}


def published_operations(repo: Repo, profile: Profile, head_rev: str,
                         base_rev: str, hunks: list[Hunk]) -> dict | None:
    """P19 publication evidence: which published API operations do the
    changed lines sit in, or one call below?

    Repo-agnostic: the spec files, the operation-annotation pattern and the
    per-extension declaration patterns all come from the profile's
    `api_spec` block; a profile without one returns None and P19 is asked
    exactly as before. What IS fixed here is the matching rule -- a name
    matches an operation when it equals its operationId case-insensitively,
    the common OpenAPI-codegen handler/service convention -- and the bound:
    the function enclosing each changed line, plus ONE hop of its callers
    (a store method changed under a service method named for the operation,
    measured on an earlier PR).

    Membership in the public spec at merge_base is positive evidence of
    publication; an operation found only in the hidden spec is positive
    evidence it is NOT published (an earlier PR). A hunk matching no
    operation is reported as such, not guessed.
    """
    cfg = profile.data.get("api_spec")
    if not cfg:
        return None
    public = _spec_operations(repo, base_rev, cfg.get("public") or [])
    hidden = _spec_operations(repo, base_rev, cfg.get("hidden") or [])
    decls = {ext: re.compile(rx)
             for ext, rx in (cfg.get("function_decl") or {}).items()}
    ends = {ext: re.compile(rx)
            for ext, rx in (cfg.get("function_end") or {}).items()}
    ann_re = (re.compile(cfg["operation_annotation"])
              if cfg.get("operation_annotation") else None)
    shipping = set(profile.data.get("roles_that_ship") or ["ships"])
    texts: dict[str, list[str]] = {}

    def lines_of(path: str) -> list[str]:
        if path not in texts:
            texts[path] = (repo.file_at(head_rev, path) or "").splitlines()
        return texts[path]

    def decl_re_for(path: str) -> re.Pattern | None:
        return next((rx for ext, rx in decls.items() if path.endswith(ext)),
                    None)

    def end_re_for(path: str) -> re.Pattern | None:
        return next((rx for ext, rx in ends.items() if path.endswith(ext)),
                    None)

    # name -> how it was reached; insertion order = discovery order
    names: dict[str, str] = {}
    for h in hunks:
        rx = decl_re_for(h.path)
        if rx is None or h.role not in shipping:
            continue
        lines = lines_of(h.path)
        for ln in _changed_new_lines(h):
            d = _enclosing_decl(lines, ln, rx, end_re_for(h.path))
            if not d:
                continue
            decl_line, name = d
            names.setdefault(name, f"{h.path}:{decl_line} encloses a change")
            for op in _annotated_ops(lines, decl_line, ann_re):
                names.setdefault(op, f"@annotation above {h.path}:{decl_line}")

    pathspec = [f"*{ext}" for ext in decls] + \
        [f":(exclude,glob){g}" for g in cfg.get("caller_exclude") or []]
    for name in list(names)[:MAX_API_NAMES]:
        if name.lower() in public or name.lower() in hidden:
            continue
        hits = repo.grep_at(head_rev, r"\b" + re.escape(name) + r"\(",
                            pathspec)
        if len(hits) > MAX_API_CALLERS:
            continue
        for hp, hline, htext in hits:
            rx = decl_re_for(hp)
            if rx is None or rx.match(htext) or \
                    htext.lstrip().startswith(_COMMENT_PREFIXES):
                continue
            d = _enclosing_decl(lines_of(hp), hline, rx, end_re_for(hp))
            if d and d[1] != name:
                names.setdefault(d[1], f"{hp}:{hline} ({d[1]}) calls {name}")

    matches = []
    for name, via in names.items():
        key = name.lower()
        op = public.get(key) or hidden.get(key)
        if op and not any(m["operation_id"] == op["operation_id"]
                          for m in matches):
            matches.append({**op, "published": key in public,
                            "hidden_spec_only": key in hidden
                            and key not in public, "via": via,
                            **_route_binding(repo, head_rev, cfg, decls,
                                             op["operation_id"])})
    return {"public_spec": cfg.get("public") or [],
            "hidden_spec": cfg.get("hidden") or [],
            "as_of": base_rev, "matches": matches,
            "searched": list(names)[:MAX_API_NAMES * 2]}


EXTERNAL_WINDOW_DAYS = 30  # how far before the merge external PRs are listed
MAX_EXTERNAL_PRS = 40


def _gh_api(args: list[str]) -> tuple[object | None, str | None]:
    """`gh api <args>` -> (parsed JSON, None) or (None, reason)."""
    try:
        r = subprocess.run(["gh", "api", *args], capture_output=True,
                           text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"gh unavailable: {e}"
    if r.returncode != 0:
        return None, f"gh api failed: {(r.stderr or '').strip()[:200]}"
    try:
        return json.loads(r.stdout), None
    except json.JSONDecodeError as e:
        return None, f"gh api returned non-JSON: {e}"


def external_repo_activity(profile: Profile, hunks: list[Hunk],
                           merged_date: str | None, gh=_gh_api
                           ) -> list[dict] | None:
    """Evidence from repos outside this tree that the diff itself names.

    Repo-agnostic: which external repos exist, and what counts as the diff
    mentioning one, come from the profile's `external_repos` block; a profile
    without one, or a run without a merge date, returns None. For each repo
    mentioned in a hunk, this lists the PRs merged in the
    `EXTERNAL_WINDOW_DAYS` before the merge date, each with the first
    non-draft release published at or after it -- whether a change had
    SHIPPED by the merge date is what a "does any writer emit this?" question
    turns on (P4; measured on an earlier PR / ldcli#767).

    "First release published after the PR merged" assumes releases are cut
    from the branch the PR merged into, which holds for release-please style
    repos; the packet says so rather than presenting it as exact.
    """
    repos = profile.data.get("external_repos") or {}
    if not repos or not merged_date:
        return None
    text = "\n".join(h.text for h in hunks)
    end = date.fromisoformat(merged_date[:10])
    start = end - timedelta(days=EXTERNAL_WINDOW_DAYS)
    out = []
    for name, cfg in repos.items():
        pats = cfg.get("mentions") or [r"\b" + re.escape(name) + r"\b"]
        if not any(re.search(p, text) for p in pats):
            continue
        entry = {"name": name, "github": cfg["github"],
                 "window": [start.isoformat(), end.isoformat()]}
        prs, err = gh(["-X", "GET", "search/issues", "-f",
                       f"q=repo:{cfg['github']} is:pr is:merged "
                       f"merged:{start.isoformat()}..{end.isoformat()}",
                       "-f", "per_page=100"])
        rels, err2 = (None, None) if err else gh(
            [f"repos/{cfg['github']}/releases?per_page=100"])
        if err or err2:
            out.append({**entry, "error": err or err2})
            continue
        releases = sorted((r for r in rels or []
                           if not r.get("draft") and r.get("published_at")),
                          key=lambda r: r["published_at"])
        items = []
        for it in (prs or {}).get("items") or []:
            merged_at = ((it.get("pull_request") or {}).get("merged_at")
                         or it.get("closed_at") or "")
            rel = next((r for r in releases if r["published_at"] >= merged_at),
                       None)
            items.append({
                "number": it.get("number"), "title": it.get("title"),
                "merged_at": merged_at[:10],
                "first_release": rel["tag_name"] if rel else None,
                "released_at": rel["published_at"][:10] if rel else None,
                "released_by_merge": bool(rel and rel["published_at"][:10]
                                          <= end.isoformat())})
        items.sort(key=lambda i: (i["merged_at"], i["number"] or 0))
        out.append({**entry, "prs": items[-MAX_EXTERNAL_PRS:]})
    return out


def stack_added_keys(repo: Repo, profile: Profile, head: str, base_rev: str,
                     keys_at_base: set[str]) -> set[str]:
    """."""
    for ref in ("origin/HEAD", "origin/main", "origin/master"):
        try:
            trunk = repo.merge_base(ref, head)
            break
        except GitError:
            continue
    else:
        return set()
    # Stacked only when the base is past where the branch left the default
    # branch. A base already in the default branch's history is not stacked:
    # a PR based on main (base == trunk), or a pinned commit that is itself
    # on main, read against its first parent (trunk == head).
    if not trunk or repo.is_ancestor(base_rev, trunk):
        return set()
    st_trunk = build_symbol_table(repo, profile, trunk)
    alias_keys_trunk = {v[0] for v in flag_aliases(repo, profile, trunk).values()}
    return keys_at_base - (st_trunk.keys | alias_keys_trunk)


def build_packet(repo: Repo, profile: Profile, head: str,
                 base_branch: str = "origin/main",
                 pr: dict | None = None,
                 ld_client: LDClient | None = None,
                 merged_date: str | None = None) -> tuple[Packet, dict]:
    """Build the evidence packet and the Tier-1 answers together.

    Returns (packet, answers). The packet is what ask.py caches as a prompt
    prefix; the answers are already-decided predicates.
    """
    answers: dict[str, dict] = {}
    unit = resolve_unit(repo, head, base_branch)

    answers["U1"] = answer(
        unit.resolved, f"{unit.mode}: {unit.basis}",
        basis="git") if unit.resolved else answer(
        False, f"unit unresolved: {unit.basis}", basis="git")

    pkt = Packet(repo_name=profile.name, pr=pr or {},
                 unit={"mode": unit.mode, "merge_base": unit.merge_base,
                       "head": unit.head, "spec": unit.spec,
                       "basis": unit.basis, "resolved": unit.resolved})
    if not unit.resolved:
        pkt.notes.append("diff unit unresolved; no other predicate was read")
        return pkt, answers

    base_rev = unit.merge_base or f"{unit.head}^"

    # ---- P1: does anything ship -------------------------------------------
    changed = repo.changed_files(unit.spec)
    stats = repo.numstat(unit.spec)
    for p in changed:
        add, dele = stats.get(p, (0, 0))
        pkt.files.append({"path": p, "role": profile.role_of(p),
                          "added": add, "deleted": dele})
    shipping_roles = set(profile.data.get("roles_that_ship") or ["ships"])
    ships = [f for f in pkt.files if f["role"] in shipping_roles]
    answers["P1"] = answer(
        bool(ships),
        (f"{len(ships)} of {len(pkt.files)} changed files ship: "
         + ", ".join(f["path"] for f in ships[:6])
         + ("…" if len(ships) > 6 else ""))
        if ships else
        (f"no changed file ships; roles: "
         + ", ".join(sorted({f['role'] for f in pkt.files}))),
        basis="profile-path-roles")

    # ---- P2, mechanically, when only comments or layout changed ----------
    # (reader/cosmetic.py); otherwise P2 is asked as usual.
    if ships:
        from reader.cosmetic import cosmetic
        verdicts = [(f["path"], cosmetic(repo.file_at(base_rev, f["path"]), repo.file_at(unit.head, f["path"]),
                                          f["path"])) for f in ships]
        if all(ok for _, (ok, _) in verdicts):
            answers["P2"] = answer(
                False,
                "every changed file that ships differs from merge_base only in comments, blank lines, "
                "indentation or spacing within a line: " + ", ".join(p for p, _ in verdicts[:6])
                + ("…" if len(verdicts) > 6 else ""),
                basis="cosmetic-only")

    pkt.hunks = parse_hunks(repo, profile, unit.spec)

    # ---- symbol tables at BOTH revisions ----------------------------------
    st_base = build_symbol_table(repo, profile, base_rev)
    st_head = build_symbol_table(repo, profile, unit.head)
    for p in st_base.problems + st_head.problems:
        pkt.notes.append("symbol-table: " + p)
    # Keys declared through an alias map (flag_aliases) exist at a revision
    # too, though no declaration file the symbol table reads names them.
    aliases_base = flag_aliases(repo, profile, base_rev)
    aliases_head = flag_aliases(repo, profile, unit.head)
    alias_keys_base = {v[0] for v in aliases_base.values()}
    alias_keys_head = {v[0] for v in aliases_head.values()}
    # An alias map's flags may live in another LD project (the declaration
    # says which): read them there, not from the profile's project.
    by_file = {ad["file"]: ad for ad in
               (profile.data.get("evaluation") or {}).get("alias_declarations") or []}
    key_projects = {}
    for key, decl_file, _, _ in list(aliases_base.values()) + list(aliases_head.values()):
        ad = by_file.get(decl_file) or {}
        if ad.get("ld_project"):
            key_projects[key] = [ad["ld_project"], dict(ad.get("ld_environments") or {})]
    keys_at_base = st_base.keys | alias_keys_base
    pkt.keys_added_by_diff = sorted((st_head.keys | alias_keys_head) - keys_at_base)
    # A key LD has no flag for serves the code's declared default: tell the
    # LD client which defaults are known (see LDClient.set_code_default).
    # A key the branch's stack adds below this PR counts as added too.
    added = set(pkt.keys_added_by_diff) | stack_added_keys(
        repo, profile, unit.head, base_rev, keys_at_base)
    pkt.ld_setup = {"key_projects": key_projects,
                    "defaults": {k: [v, k in added] for k, v in st_head.defaults.items()}}
    if ld_client is not None:
        setup_ld_client(ld_client, pkt.ld_setup)

    # Scan EVERY changed file, not just the shipping ones. The P5 shortcut
    # below concludes "no gate exists in the diff" from an empty result, and
    # that is only sound if the scan covered everything the diff touched.
    all_paths = [f["path"] for f in pkt.files]
    ship_paths = [f["path"] for f in pkt.files if f["role"] == "ships"]
    raw_head_sites = flag_sites(repo, profile, st_head, unit.head, all_paths,
                                imported_helpers=True, method_helpers=True)
    pkt.flag_sites_head = _narrow_case_sites(repo, unit.head, raw_head_sites,
                                             pkt.hunks)
    pkt.flag_sites_base = flag_sites(repo, profile, st_base, base_rev,
                                     all_paths, imported_helpers=True,
                                     method_helpers=True)
    # Compared before case narrowing, which only the head side has: a
    # narrowed per-case key is not a deleted evaluation.
    pkt.removed_flags = removed_flag_evaluations(pkt.flag_sites_base,
                                                 raw_head_sites)

    # ---- restrict candidacy to sites NEAR a changed hunk -------------------
    # Import-only hunks do not count as the change (see proximity_hunks).
    prox = proximity_hunks(pkt.hunks)

    def ranges_of(hunks):
        out: dict[str, list[tuple[int, int]]] = {}
        for h in hunks:
            out.setdefault(h.path, []).append(h.new_range)
        return out

    ranges = ranges_of(prox)

    def near(site, rng=ranges) -> bool:
        for lo, hi in rng.get(site["path"], []):
            if lo - PROXIMITY_LINES <= site["line"] <= hi + PROXIMITY_LINES:
                return True
        return False

    near_head = [s for s in pkt.flag_sites_head if near(s)]
    pkt.flag_sites_far = [s for s in pkt.flag_sites_head if not near(s)]
    import_near = [s for s in pkt.flag_sites_head
                   if not near(s) and near(s, ranges_of(pkt.hunks))]
    if import_near:
        pkt.notes.append(
            f"{len(import_near)} flag evaluation(s) are near only an import "
            f"change, which changes no behavior, so they are not treated as "
            f"near the change: "
            + ", ".join(f"{s['key'] or '?'}@{s['path']}:{s['line']}"
                        for s in import_near[:4]))
    if pkt.flag_sites_far:
        pkt.notes.append(
            f"{len(pkt.flag_sites_far)} flag evaluation(s) are in a changed "
            f"file but more than {PROXIMITY_LINES} lines from any changed "
            f"hunk; shown as 'elsewhere in file', NOT offered as reuse "
            f"candidates")

    # ---- P5: mechanical when the diff wires no gate at all ----------------
    # P5 asks whether every behaviour-carrying hunk sits inside a flag
    # evaluation THE DIFF ITSELF WIRES. If the changed files contain no flag
    # evaluation at head, there is nothing for a hunk to sit inside, so the
    # answer is False by construction -- no judgment required.
    #
    # This is worth doing for cost as much as determinism: P5 is one of the
    # two predicates the tier file spends Opus at high effort on, and most PRs
    # touch no flag code at all, so most PRs were paying for a frontier model
    # to read an empty list.
    #
    # P6 IS NOT SHORTCUT THE SAME WAY, and the asymmetry is the point: an
    # ANCESTOR gate can live in an unchanged caller, route guard, or wrapping
    # component, none of which appear in the diff. An empty in-diff scan says
    # nothing about it. Shortcutting P6 here would manufacture `not covered`
    # on exactly the changes that are covered.
    if not near_head:
        answers["P5"] = answer(
            False,
            f"no flag evaluation lies within {PROXIMITY_LINES} lines of any "
            f"changed hunk across the {len(all_paths)} changed files at head "
            f"{unit.head[:12]}"
            + (f" ({len(pkt.flag_sites_far)} exist elsewhere in those files)"
               if pkt.flag_sites_far else "")
            + (" (import-only changes aside)" if import_near else "")
            + ", so no hunk is enclosed by a gate this diff wires",
            basis="flag-site-scan")

    dead = _dead_flag_removal(repo, profile, st_base, st_head, base_rev, pkt)
    if dead:
        answers["P3"] = answer(
            True,
            f"the diff only removes the declaration of {', '.join(dead)}; no "
            f"code outside the declaration and generated files evaluates "
            f"{'it' if len(dead) == 1 else 'them'} at merge_base "
            f"{base_rev[:12]}, so there is no variation to keep",
            basis="flag-site-scan")
    elif not pkt.removed_flags and (sum(1 for x in pkt.flag_sites_base if not x.get("key"))
                                    <= sum(1 for x in raw_head_sites if not x.get("key"))):
        # ... and NO when the diff deletes no flag evaluation at all, keyed
        # or not: P3's YES needs one removed. Every P3 answered over 148
        # saved runs with none removed was NO (142 of 142).
        answers["P3"] = answer(
            False,
            f"the diff deletes no flag evaluation in the {len(all_paths)} "
            f"changed files (merge_base {base_rev[:12]} to head "
            f"{unit.head[:12]}), so no change here is a flag removal",
            basis="flag-site-scan")

    # ---- P6: one-hop referenced context, for when the ancestor gate is
    # outside the diff (see find_referenced_context's docstring) ------------
    hunk_ranges: dict[str, list[tuple[int, int]]] = {}
    for h in pkt.hunks:
        hunk_ranges.setdefault(h.path, []).append(h.new_range)
    pkt.referenced_context = find_referenced_context(
        repo, profile, st_head, unit.head, ship_paths, set(all_paths),
        hunk_ranges)
    # ... and the same for callers INSIDE the changed files, which the hunks'
    # few lines of context never show (see find_caller_gates).
    pkt.caller_gates = find_caller_gates(
        repo, unit.head, [h for h in pkt.hunks if h.path in ship_paths],
        pkt.flag_sites_head, pkt.flag_sites_base)
    walked: set[str] = set()
    pkt.caller_gates += find_outside_caller_gates(
        repo, profile, st_head, unit.head,
        [h for h in pkt.hunks if h.path in ship_paths], set(all_paths),
        keys_at_base, visited=walked,
        reported=reported_calls(pkt.caller_gates))
    # ... and guards attached by registration (middleware, a route module's
    # loader), which no call reaches (see find_registered_guards).
    pkt.caller_gates += find_registered_guards(
        repo, profile, st_head, unit.head, ship_paths, walked, keys_at_base)
    # ---- P19: publication evidence from the repo's published API spec ---
    pkt.public_api = published_operations(repo, profile, unit.head, base_rev,
                                          pkt.hunks)

    # ---- P4: evidence from external repos the diff names ----------------
    pkt.external = external_repo_activity(profile, pkt.hunks, merged_date)

    if pkt.referenced_context:
        pkt.notes.append(
            f"{len(pkt.referenced_context)} referenced file(s) outside the "
            f"diff shown for P6 enclosure judgment only: "
            + ", ".join(rc["path"] for rc in pkt.referenced_context))

    # ---- P9: a reuse candidate that EXISTS AT merge_base -------------------
    # A key the diff itself introduces is not a candidate: there is nothing to
    # reuse. This is why the base symbol table is built at all.
    cand_keys = sorted({s["key"] for s in near_head if s["key"]}
                       & keys_at_base)
    for k in cand_keys:
        where = [f"{s['path']}:{s['line']}" for s in near_head
                 if s["key"] == k][:4]
        pkt.candidates.append({"key": k, "evaluated_at": where,
                               "existed_at_base": True})
    if pkt.keys_added_by_diff:
        pkt.notes.append(
            "keys ADDED by this diff (never reuse candidates): "
            + ", ".join(pkt.keys_added_by_diff[:8]))
    answers["P9"] = answer(
        bool(cand_keys),
        (f"candidate keys present at merge_base {base_rev[:12]} and evaluated "
         f"within {PROXIMITY_LINES} lines of a changed hunk: "
         f"{', '.join(cand_keys[:6])}") if cand_keys else
        (f"no key evaluated in the changed files exists at merge_base "
         f"{base_rev[:12]}"
         + (f"; the diff ADDS {', '.join(pkt.keys_added_by_diff[:4])}"
            if pkt.keys_added_by_diff else "")),
        basis="symbol-table@merge_base")

    # ---- CODEOWNERS fact for P13(b) ---------------------------------------
    co = repo.file_at(base_rev, profile.data.get("codeowners", "CODEOWNERS"))
    if co:
        owners: dict[str, list[str]] = {}
        for line in co.splitlines():
            line = line.split("#")[0].strip()
            if not line:
                continue
            bits = line.split()
            if len(bits) >= 2:
                owners[bits[0]] = bits[1:]
        pkt.codeowners = {"rules": len(owners),
                          "matched": _owners_for(owners, ship_paths),
                          # P13(b) compares the changed paths' owners with the
                          # owners of the REUSE KEY's evaluation sites, so each
                          # candidate's are recorded here (by key).
                          "candidate_sites": {
                              c["key"]: _owners_for(owners, sorted({
                                  w.rsplit(":", 1)[0] for w in c["evaluated_at"]}))
                              for c in pkt.candidates}}

    # ---- P7 / P8 / P11: LaunchDarkly state --------------------------------
    near_base = [s for s in pkt.flag_sites_base
                 if any(lo - PROXIMITY_LINES <= s["line"] <= hi + PROXIMITY_LINES
                        for lo, hi in
                        [(h.old_start, h.old_start + max(h.old_count, 1) - 1)
                         for h in prox if h.path == s["path"]])]
    # A P6 ancestor gate found via referenced_context lives outside the diff
    # entirely, so it never shows up in near_base -- without this, P6=YES
    # would have no way to reach P7/P8's readable state and would always
    # escalate at P7, even though the gate (and its key) is now known.
    ref_gate_keys = {k for rc in pkt.referenced_context
                     for k in rc.get("gate_keys", [])}
    cited = sorted({s["key"] for s in near_base if s["key"]} | ref_gate_keys)
    # Every P9 candidate gets its state read, not only the ones that also sit
    # near a merge_base hunk: P11 is about EACH candidate, and a key the
    # change starts evaluating next to its own hunks would otherwise be left
    # out of P11 silently. P7/P8 still read exactly the `cited` keys.
    to_read = sorted(set(cited) | {c["key"] for c in pkt.candidates})
    if not merged_date:
        pkt.notes.append("no merge date supplied; LD state not read")
    if ld_client and ld_client.available and merged_date and to_read:
        snaps = {}
        for k in to_read:
            try:
                snaps[k] = ld_client.snapshot(k, merged_date)
            except LDUnavailable as e:
                pkt.notes.append(f"LD unavailable: {e}")
                break
        pkt.ld = {"as_of": merged_date, "snapshots": snaps,
                  "user_facing": ld_client.user_facing}
        if cited:
            answers.update(_gate_state({k: snaps[k] for k in cited if k in snaps},
                                       ld_client.user_facing, merged_date,
                                       "cited keys", main=_main_env(ld_client)))
        else:
            # Only candidates were read: P7/P8 have no key, exactly as when LD
            # is not read at all (see the else branch below).
            why = "no flag key is evaluated in the changed files at merge_base"
            pkt.notes.append(f"LD state not read for P7/P8: {why}")
            answers["P7"] = answer(UNRESOLVED, f"not read: {why}", basis="ld-api")
        if pkt.candidates:
            archived = sorted(c["key"] for c in pkt.candidates
                              if (snaps.get(c["key"]) or {}).get("archived"))
            csnaps = {c["key"]: snaps[c["key"]] for c in pkt.candidates
                      if c["key"] in snaps and c["key"] not in archived}
            if archived and not csnaps:
                answers["P11"] = {**answer(False, "P11: every candidate is archived "
                                           f"({', '.join(archived)}), so none is a "
                                           "release lever", basis="ld-api"),
                                  "withholding_keys": []}
            if csnaps:
                # Over the main production environment only (ruling R5).
                answers["P11"] = p11_answer(csnaps, [ld_client.main_production])
                if archived:
                    answers["P11"]["archived_candidates"] = archived
    else:
        why = ("no flag key is evaluated in the changed files at merge_base"
               if not cited else
               "no LaunchDarkly API key" if not (
                   ld_client and ld_client.available) else
               "no merge date")
        pkt.notes.append(f"LD state not read: {why}")
        # P7 is only RELEVANT when an ancestor gate encloses (P6). Leaving it
        # UNRESOLVED rather than answering False is deliberate: the relevance
        # test in classify.py will drop it when P6 is false, and escalate via
        # E-STATE when it is not. Answering False here would assert "state is
        # unreadable" on every PR with no gate at all.
        answers["P7"] = answer(UNRESOLVED, f"not read: {why}", basis="ld-api")

    far_ranges: dict[str, list[tuple[int, int]]] = {}
    for h in pkt.hunks:
        far_ranges.setdefault(h.path, []).append(h.new_range)

    def _gap(site: dict) -> int:
        return min((lo - site["line"] if site["line"] < lo else
                    max(0, site["line"] - hi))
                   for lo, hi in far_ranges.get(site["path"], [(0, 0)]))

    context_keys: list[str] = []
    for site in sorted(pkt.flag_sites_head, key=lambda x: (_gap(x), x["line"])):
        k = site["key"]
        if k and k not in cited and k not in context_keys:
            context_keys.append(k)
    def _gate_keys(obj) -> list[str]:
        if isinstance(obj, dict):
            ks = [k for k in obj.get("keys") or [] if isinstance(k, str)]
            return ks + [k for v in obj.values() for k in _gate_keys(v)]
        if isinstance(obj, list):
            return [k for v in obj for k in _gate_keys(v)]
        return []
    caller_keys = [k for k in dict.fromkeys(_gate_keys(pkt.caller_gates))
                   if k not in cited]
    context_keys = (caller_keys + [k for k in context_keys if k not in caller_keys]
                    )[:MAX_CONTEXT_KEYS]
    if ld_client and ld_client.available and merged_date and context_keys:
        ctx_snaps = {}
        for k in context_keys:
            try:
                ctx_snaps[k] = ld_client.snapshot(k, merged_date)
            except LDUnavailable as e:
                pkt.notes.append(f"LD unavailable (context keys): {e}")
                break
        if ctx_snaps:
            pkt.ld = pkt.ld or {"as_of": merged_date, "snapshots": {},
                                "user_facing": ld_client.user_facing}
            pkt.ld["context_snapshots"] = ctx_snaps

    removed_keys = [r["key"] for r in pkt.removed_flags or []]
    if ld_client and ld_client.available and merged_date and removed_keys:
        known = {**((pkt.ld or {}).get("context_snapshots") or {}),
                 **((pkt.ld or {}).get("snapshots") or {})}
        rm_snaps = {}
        for k in removed_keys:
            if k in known:
                rm_snaps[k] = known[k]
                continue
            try:
                rm_snaps[k] = ld_client.snapshot(k, merged_date)
            except LDUnavailable as e:
                pkt.notes.append(f"LD unavailable (removed flags): {e}")
                break
        if rm_snaps:
            pkt.ld = pkt.ld or {"as_of": merged_date, "snapshots": {},
                                "user_facing": ld_client.user_facing}
            pkt.ld["removed_snapshots"] = rm_snaps

    return pkt, answers


def removed_flag_evaluations(base_sites: list[dict],
                             head_sites: list[dict]) -> list[dict]:
    """Keys the diff deletes evaluations of: evaluated in the changed files
    more times at merge_base than at head (a removed flag's sites are at
    merge_base and not at head). Counted per key over every site in the
    changed files, near a hunk or not, so a removal in a deleted file
    counts. Sorted by key."""
    def counts(sites):
        out: dict[str, int] = {}
        for s in sites:
            if s.get("key"):
                out[s["key"]] = out.get(s["key"], 0) + 1
        return out
    base, head = counts(base_sites), counts(head_sites)
    return [{"key": k, "at_merge_base": n, "at_head": head.get(k, 0)}
            for k, n in sorted(base.items()) if n > head.get(k, 0)]


def removed_flag_key(removed: list[str], answer_: dict | None) -> str | None:
    """The removed flag a P32 YES keeps (T-RE-2's reuse key): the one key of
    `removed` its evidence names as a whole key, else the only removed key.
    None when that can't be told."""
    if not isinstance(answer_, dict) or answer_.get("value") is not True:
        return None
    said = " ".join(str(x) for x in [answer_.get("evidence")]
                    + [s.get("evidence") for s in answer_.get("samples") or []
                       if isinstance(s, dict)] if x)
    named = [k for k in removed if names_key(said, k)]
    if len(named) == 1:
        return named[0]
    return removed[0] if len(removed) == 1 and not named else None


def record_removed_key(answers: dict, removed: list[str]) -> None:
    """Set P32's `flag_key` from the packet's removed flags, in place, so
    the ledger and the report name the flag T-RE-2 keeps
    (classify.reuse_flag_key reads it). Shared by read.py and
    merge_inline.py."""
    a = answers.get("P32")
    key = removed_flag_key(removed, a)
    if key:
        a["flag_key"] = key


def _gate_state(snaps: dict, user_facing: list[str], merged_date: str,
                what: str, paths: list[list[str]] | None = None,
                main: str | None = None) -> dict:
    """P7 (every gate key readable?) and P8 (does the gate withhold?) from
    LD snapshots of the keys taken to be the gate, and P33 (does it still
    hold the change back in the main production environment `main`?) beside
    P8 whenever it is read.

    `paths` is how P6's YES says its flags combine (gate_paths_of): with a
    path of more than one flag, P8 is read per path (_path_withholding).
    Without it, or with every path a single flag, the keys are alternative
    ways in and P8 is read flat, as before. P7 is unchanged either way:
    every key must be readable. P33 reads the same paths (_main_holding)."""
    out = {}
    readable = [k for k, s in snaps.items() if s.get("user_facing_resolved")]
    out["P7"] = answer(
        bool(readable) and len(readable) == len(snaps),
        f"read {len(readable)}/{len(snaps)} {what} across {user_facing} as of "
        f"{merged_date}"
        + (f"; unreadable: "
           + ", ".join(f"{k}({s.get('unreadable_environments') or s.get('basis')})"
                       for k, s in snaps.items()
                       if not s.get('user_facing_resolved'))
           if len(readable) != len(snaps) else ""),
        basis="ld-api")
    if readable:
        if paths and any(len(p) > 1 for p in paths):
            out["P8"] = _path_withholding(snaps, user_facing, paths, "P8")
            out["P8"]["gate_paths"] = paths
        else:
            out["P8"] = _withholding(snaps, user_facing, "P8")
        if main:
            out["P33"] = _main_holding(snaps, main, paths)
    return out


# P6 is the one predicate whose YES says how its enclosing flags combine
# (predicates.yaml P6: `gates` / `gate_paths`). Not a citation: it is checked
# against the keys the citations resolve to (gate_paths_of).
GATE_COMBINATION_PREDICATES = ("P6",)
GATE_COMBINATIONS = ("all", "any")


def gate_declaration(a: dict) -> tuple[str, list[list[str]]] | None:
    """One answer's (or sample's) `gates` / `gate_paths`, checked for shape:
    ("all" | "any", []) or ("paths", [[key, ...], ...]); None when it
    declares nothing or the shape is wrong (read as not stated)."""
    if not isinstance(a, dict):
        return None
    gp = a.get("gate_paths")
    if gp:
        if not (isinstance(gp, list) and all(
                isinstance(p, list) and p and all(isinstance(k, str) and k for k in p)
                for p in gp)):
            return None
        return "paths", [list(dict.fromkeys(p)) for p in gp]
    g = a.get("gates")
    return (g, []) if g in GATE_COMBINATIONS else None


def agreed_gate_declaration(samples: list[dict]) -> dict:
    """The `gates` / `gate_paths` every YES sample gives, as fields for the
    answer; empty when they don't all give the same one, which leaves the
    flags read as alternative ways in (the reading that errs toward
    exposure)."""
    decl = [gate_declaration(s) for s in samples or []
            if isinstance(s, dict) and s.get("value") in ("yes", True)]
    if not decl or any(d is None for d in decl):
        return {}
    norm = {(d[0], frozenset(frozenset(p) for p in d[1])) for d in decl}
    if len(norm) != 1:
        return {}
    kind, paths = decl[0]
    return {"gate_paths": paths} if kind == "paths" else {"gates": kind}


def gate_values_declaration(a: dict) -> dict[str, list] | None:
    """One answer's (or sample's) `gate_values` -- for a cited flag that is
    not boolean, the value(s) it must serve for the changed code to run,
    `{"key": ["value", ...]}` -- checked for shape; None when it declares
    nothing or the shape is wrong (read as not stated: `on` then stands for
    exposing, the reading that errs away from a false already-flagged)."""
    if not isinstance(a, dict):
        return None
    gv = a.get("gate_values")
    if not gv:
        return None
    ok = isinstance(gv, dict) and all(
        isinstance(k, str) and k and isinstance(v, list) and v
        and all(isinstance(x, (str, int, float)) and not isinstance(x, bool) for x in v)
        for k, v in gv.items())
    return {k: list(dict.fromkeys(v)) for k, v in gv.items()} if ok else None


def gate_values_of(enclosure: dict, keys: list[str]) -> dict[str, list]:
    """P6's `gate_values` for the enclosing `keys`: from the answer, else
    from its YES samples when they all give the same; keys the citations
    don't resolve to are dropped. Empty when none is declared."""
    decl = gate_values_declaration(enclosure)
    if decl is None:
        got = [gate_values_declaration(x) for x in enclosure.get("samples") or []
               if isinstance(x, dict) and x.get("value") in ("yes", True)]
        if got and all(g is not None for g in got) and \
                len({tuple(sorted((k, tuple(map(str, v))) for k, v in g.items())) for g in got}) == 1:
            decl = got[0]
    return {k: v for k, v in (decl or {}).items() if k in keys}


def gate_paths_of(enclosure: dict, keys: list[str]) -> list[list[str]] | None:
    """How P6's YES says the enclosing `keys` combine, as paths to the change:
    each path the flags that must all be on for it, the change exposed when
    any path is. None when nothing is declared -- the keys are then
    alternative ways in, each a path of one, which is the flat reading P8 had
    before (`_withholding`).

    "all" is one path of every key; "any" a path per key. With `gate_paths`,
    a key not among `keys` (the ones the citations resolve to) is dropped
    from its path -- fewer flags on a path can only expose more -- and a
    resolved key on no path is a path of its own; a path left with no
    resolved key makes the declaration unusable (None), since that way in
    could be open. Read from the answer's own fields, else from its YES
    samples when they all agree (agreed_gate_declaration)."""
    if not keys:
        return None
    decl = gate_declaration(enclosure)
    if decl is None:
        agreed = agreed_gate_declaration(enclosure.get("samples") or [])
        decl = gate_declaration(agreed) if agreed else None
    if decl is None:
        return None
    kind, paths = decl
    if kind == "all":
        return [list(keys)]
    if kind == "any":
        return [[k] for k in keys]
    out = []
    for p in paths:
        kept = [k for k in p if k in keys]
        if not kept:
            return None
        if kept not in out:
            out.append(kept)
    on_paths = {k for p in out for k in p}
    out += [[k] for k in keys if k not in on_paths]
    return out


def _env_reading(e: dict) -> tuple[str, str]:
    """One key's state in one environment, as P8 reads it in `_withholding`:
    ("exposing" | "withheld" | "unknown", tag)."""
    reach = e.get("serves")
    if reach:
        return (("exposing" if reach in ("all", "partial", "cohort") else "withheld"),
                f"[{reach}: {e.get('serves_basis')}]")
    if e.get("on") is None:
        return "unknown", f"({e.get('basis')})"
    return ("exposing" if e["on"] else "withheld"), ""


def _path_withholding(snaps: dict, user_facing: list[str],
                      paths: list[list[str]], which: str = "P8") -> dict:
    """P8 over gates that combine (gate_paths_of): in each user-facing
    production env, a path is exposing only if EVERY flag on it exposes
    there; the env exposes the change if ANY path does. YES only if no env
    has an exposing path. Each key's state is read as `_withholding` reads
    it, and with its precedence: a known state that settles it decides --
    one withheld flag closes a path, one exposing path exposes the env --
    and unknown matters only when nothing known does. A key with no entry
    for an env is left out of that env, as `_withholding` leaves it out."""
    exposing, withheld, unknown = [], [], []
    no_targeting = False
    for name in user_facing:
        env_state, env_unknown, env_withheld = None, [], []
        for path in paths:
            states = []
            for k in path:
                e = ((snaps.get(k) or {}).get("environments") or {}).get(name)
                if e:
                    st, tag = _env_reading(e)
                    states.append((st, f"{k}@{name}{tag}"))
            if not states:
                continue
            closed = [t for st, t in states if st == "withheld"]
            if closed:
                env_withheld.append(closed[0])
            elif any(st == "unknown" for st, _ in states):
                env_unknown += [t for st, t in states if st == "unknown"]
            else:
                env_state = "exposing"
                no_targeting |= any("[" not in t for _, t in states)
                exposing.append(" + ".join(t for _, t in states))
                break
        if env_state == "exposing":
            continue
        if env_unknown:
            unknown += env_unknown
        else:
            withheld += env_withheld
    shape = " or ".join("(" + " and ".join(p) + ")" for p in paths)
    how = f"the change runs only when {shape} {'is' if len(paths) == 1 else 'are'} on"
    note = (" (targeting not read for some, so `on` is read as exposing)"
            if no_targeting else "")
    if exposing:
        return answer(False, f"{which}: {how}, and every flag on one of those "
                             f"is served to real users in user-facing production: "
                             f"{'; '.join(exposing[:5])}{note}",
                      basis="ld-api")
    if unknown:
        return answer(UNRESOLVED, f"{which}: {how}; state unknown for "
                                  f"{', '.join(unknown[:5])}",
                      basis="ld-api")
    return answer(True, f"{which}: {', '.join(dict.fromkeys(withheld[:6]))} "
                        f"withhold(s) it from real users in every user-facing "
                        f"production environment: {how}, and in each "
                        f"environment one flag on every way in is withheld",
                  basis="ld-api")


def _main_env(ld_client) -> str | None:
    """The main production environment (LDClient.main_production: the
    profile's `main_production`, else the first user-facing one), for a
    client that may predate the attribute."""
    uf = list(getattr(ld_client, "user_facing", None) or [])
    return getattr(ld_client, "main_production", None) or (uf[0] if uf else None)


def _main_reading(e: dict | None) -> tuple[str, str]:
    """One key's state in the main production environment, as P33 reads it:
    ("all" | "held" | "unknown", tag). Targeting as P8 reads it (`serves`):
    only `all` serves every real user; `partial`, `cohort`, `internal` and
    `none` hold the change back from some. Without targeting, `on` counts
    as serving everyone -- the reading that errs away from a false
    already-flagged, as P8's does -- and off holds it back. No entry for the
    environment, or no `on`, is unknown."""
    if not e:
        return "unknown", "(not read)"
    reach = e.get("serves")
    if reach:
        return ("all" if reach == "all" else "held"), f"[{reach}: {e.get('serves_basis')}]"
    if e.get("on") is None:
        return "unknown", f"({e.get('basis')})"
    return ("all" if e["on"] else "held"), ("[on, targeting not read]" if e["on"] else "[off]")


def _main_holding(snaps: dict, main: str,
                  paths: list[list[str]] | None = None) -> dict:
    """    `paths` as P8 reads them (gate_paths_of): each path the flags that must
    all be on for that way in; None reads the keys as alternative ways in,
    a path of one each. The change reaches every real user only through a
    path whose every flag serves everyone (`all`): then NO. YES when every
    path has a flag that holds it back. With _withholding's precedence: a
    known state that settles it decides, and unknown matters only when
    nothing known does. Records `holding_keys`, the keys closing a path,
    in path order; the first is the key an already-flagged verdict names.

    Measured on an evaluation set: a gate serving a cohort, or 5%, in production
    read as P8 NO and walked the reuse layer, which reached already-flagged
    (T-AF-3) only when P10 and P12 both held."""
    paths = paths or [[k] for k in snaps]
    serving, holding, unknown = [], [], []
    for path in paths:
        states = [(k, *_main_reading(((snaps.get(k) or {}).get("environments") or {}).get(main)))
                  for k in path]
        held = [(k, tag) for k, st, tag in states if st == "held"]
        if held:
            holding += [x for x in held if x not in holding]
        elif any(st == "unknown" for _, st, _ in states):
            unknown += [f"{k}@{main}{tag}" for k, st, tag in states if st == "unknown"]
        else:
            serving.append(" + ".join(f"{k}@{main}{tag}" for k, _, tag in states))
    shape = (" or ".join("(" + " and ".join(p) + ")" for p in paths)
             if any(len(p) > 1 for p in paths) else None)
    how = f"; the change runs only when {shape} {'is' if len(paths) == 1 else 'are'} on" if shape else ""
    if serving:
        a = answer(False, f"P33: {'; '.join(serving[:5])} serve(s) the change to every real "
                          f"user in the main production environment ({main}){how}",
                   basis="ld-api")
        a["holding_keys"] = []
        return a
    if unknown:
        a = answer(UNRESOLVED, f"P33: main production ({main}) state unknown for "
                               f"{', '.join(dict.fromkeys(unknown[:5]))}{how}",
                   basis="ld-api")
        a["holding_keys"] = list(dict.fromkeys(k for k, _ in holding))
        return a
    tags = list(dict.fromkeys(f"{k}@{main}{tag}" for k, tag in holding))
    a = answer(True, f"P33: {', '.join(tags[:5])} still hold(s) the change back from "
                     f"some real users in the main production environment ({main}){how}",
               basis="ld-api")
    a["holding_keys"] = list(dict.fromkeys(k for k, _ in holding))
    return a


def names_key(text: str, key: str) -> bool:
    """Whether `text` names flag key `key` as a whole key: `banner` is not
    named inside `banner-v2`. A dot continues a key only when a key character
    follows it, so a key that ends a sentence still counts."""
    return bool(key) and re.search(
        rf"(?<![A-Za-z0-9._-]){re.escape(key)}(?![A-Za-z0-9_-]|\.[A-Za-z0-9])",
        text) is not None


FLAG_READ_SOURCES = {"symbol-call", "pattern", "alias-read", "predicate-var"}


def names_symbol(text: str, symbol: str) -> bool:
    """Whether `text` names code symbol `symbol` as a whole identifier:
    `enableFoo` is not named inside `enableFooV2`."""
    return bool(symbol) and re.search(
        rf"(?<![A-Za-z0-9_$]){re.escape(symbol)}(?![A-Za-z0-9_$])",
        text) is not None


def keys_at_citations(pkt: Packet, citations: list[dict],
                      window: int = 2, evidence: str = "") -> list[str]:
    """Flag keys evaluated at (or within `window` lines of) the cited lines:
    diff files via their head/merge_base flag sites, referenced files via the
    gate lines recorded for them.

    Where one cited line carries several keys -- a gate helper whose switch
    returns a different flag per case -- and the citing answer's `evidence`
    names some of them, only those are kept: the answer has said which case
    the change runs under (an earlier PR's isTwoStepSetupEnabled returns
    the snowflake key or the redshift one)."""
    by_path: dict[str, list[dict]] = {}
    unresolved_at: set[tuple[str, int]] = set()
    for site in (pkt.flag_sites_head or []) + (pkt.flag_sites_base or []):
        if site.get("key"):
            by_path.setdefault(site["path"], []).append(site)
        elif site.get("source") == "unresolved-predicate":
            unresolved_at.add((site["path"], site["line"]))
    keys: list[str] = []
    symbol_keys: dict[str, set[str]] = {}
    for c in citations:
        path, line = c.get("path"), c.get("line")
        if not isinstance(line, int):
            continue
        here = [s for s in by_path.get(path, []) if s["line"] == line]
        if not here and (path, line) in unresolved_at:
            continue
        near = here or [s for s in by_path.get(path, [])
                        if abs(s["line"] - line) <= window]
        named = [s for s in near if names_key(evidence, s["key"])]
        if here and len({s["key"] for s in here}) > 1 and named:
            near = named
        for site in near:
            if site["key"] not in keys:
                keys.append(site["key"])
            if site.get("symbol") and site.get("source") in FLAG_READ_SOURCES:
                symbol_keys.setdefault(site["symbol"], set()).add(site["key"])
        for rc in pkt.referenced_context or []:
            if rc["path"] == path and any(abs(gl - line) <= window
                                          for gl in rc.get("gate_lines") or []):
                for k in rc.get("gate_keys") or []:
                    if k not in keys:
                        keys.append(k)
        for g in getattr(pkt, "caller_gates", None) or []:
            if g["path"] == path and any(abs(gl - line) <= window
                                         for gl in g.get("gate_lines") or []):
                for k in g.get("keys") or []:
                    if k not in keys:
                        keys.append(k)
    by_symbol = {k: [sym for sym, ks in symbol_keys.items() if ks == {k}]
                 for k in keys}
    named = [k for k in keys if names_key(evidence, k)
             or any(names_symbol(evidence, sym) for sym in by_symbol[k])]
    return named or keys


def _enclosure_cites(enclosure: dict) -> list[dict]:
    """Citations of a P5/P6 answer: pooled from the keyed reader's samples,
    or the single inline answer's own (merge_inline / the preflight skill)."""
    return [c for smp in enclosure.get("samples") or []
            for c in smp.get("citations") or []] or enclosure.get("citations") or []


def _enclosure_said(enclosure: dict) -> str:
    return " ".join(str(smp.get("evidence") or "")
                    for smp in enclosure.get("samples") or []) or str(enclosure.get("evidence") or "")


def diff_wired_guard(pkt: Packet, enclosure: dict) -> dict | None:
    """A NO for P5, when its YES cites only gates that already existed.

    P5 asks for a gate THIS DIFF wires. A YES whose every enclosing key was
    declared before the diff and is evaluated only on lines the diff does not
    touch is an ancestor gate -- P6's question, where the gate's merge-date
    state decides. Measured on an earlier PR: P5 credited an evaluation that
    sat unchanged at merge_base, and because a diff-wired gate is already
    flagged whatever its state, a flag on for every user was taken as
    protection. A key the diff adds, or evaluates on a line it adds or
    changes (a swapped-in gate included), keeps the YES. Returns None when
    the YES stands or its keys cannot be resolved.
    """
    if enclosure.get("value") is not True:
        return None
    cites, said = _enclosure_cites(enclosure), _enclosure_said(enclosure)
    keys = keys_at_citations(pkt, cites, evidence=said)
    if not keys:
        return None
    added = {(h.path, n) for h in pkt.hunks for n in _changed_new_lines(h)}
    new_keys = set(pkt.keys_added_by_diff or [])
    for k in keys:
        if k in new_keys:
            return None
        if any(s.get("key") == k and (s["path"], s["line"]) in added
               for s in pkt.flag_sites_head):
            return None
    return answer(False,
                  f"every gate P5's YES cites ({', '.join(keys)}) was declared before "
                  f"this diff and is evaluated only on lines the diff leaves unchanged, "
                  f"so it is not a gate this diff wires -- whether that existing gate "
                  f"encloses and withholds the change is P6's question (was: "
                  f"{str(enclosure.get('evidence') or '')[:200]})",
                  basis="diff-wired-guard")


def gate_state_from_enclosure(pkt: Packet, ld_client: LDClient | None,
                              merged_date: str | None, pid: str,
                              enclosure: dict) -> dict | None:
    """P7/P8 re-read from the keys a YES on P5/P6 actually cites as the
    enclosing gate, or None to keep the proximity-based answers.

    P5 and P6 each record "the enclosing key(s)", and P7/P8 are about that
    gate -- not about every flag evaluated within PROXIMITY_LINES of a hunk.
    Measured on an earlier PR: the change's real gates were two flags off in
    every user-facing environment, but proximity handed P7/P8 four unrelated
    flags passed as arguments next to the change, one of them on in
    production, so P8 could never have read the actual gate.
    """
    if enclosure.get("value") is not True:
        return None
    cites, said = _enclosure_cites(enclosure), _enclosure_said(enclosure)
    keys = keys_at_citations(pkt, cites, evidence=said)
    if not keys:
        return None
    if not (ld_client and ld_client.available and merged_date):
        return {"P7": answer(UNRESOLVED, f"{pid}'s enclosing keys "
                             f"{', '.join(keys)}: LD state not read",
                             basis="ld-api")}
    # A multivariate gate is read by the value(s) P6's YES says the changed
    # code runs under (gate_values_of); without them `on` stands for exposing.
    values = (gate_values_of(enclosure, keys) if pid in GATE_COMBINATION_PREDICATES
              else {})
    snaps = {}
    for k in keys:
        try:
            snaps[k] = (ld_client.snapshot(k, merged_date, exposing_values=values[k])
                        if values.get(k) else ld_client.snapshot(k, merged_date))
        except LDUnavailable as e:
            return {"P7": answer(UNRESOLVED, f"LD unavailable: {e}",
                                 basis="ld-api")}
    # How the keys combine, when P6's YES says (nested gates: one flag still
    # withholding keeps the change withheld). P5's YES ends the walk before
    # P8 is used, and records none.
    paths = (gate_paths_of(enclosure, keys) if pid in GATE_COMBINATION_PREDICATES
             else None)
    return _gate_state(snaps, ld_client.user_facing, merged_date,
                       f"of {pid}'s enclosing keys ({', '.join(keys)})", paths,
                       main=_main_env(ld_client))


def candidate_from_enclosure(pkt: Packet, pid: str,
                             enclosure: dict) -> dict | None:
    """P12 answered by a YES on P5/P6, or None to ask it.

    One key only. With several (a gate swap, or different hunks under
    different flags) no single candidate is shown to cover the whole change,
    which is what P12 asks."""
    if enclosure.get("value") is not True:
        return None
    cites = _enclosure_cites(enclosure)
    keys = keys_at_citations(pkt, cites, window=0)
    cands = {c["key"] for c in pkt.candidates}
    if len(keys) != 1 or keys[0] not in cands \
            or set(keys_at_citations(pkt, cites)) != set(keys):
        return None
    a = answer(True, f"reuse candidate `{keys[0]}` is the one key {pid} "
                     f"found enclosing every behavior-carrying hunk, with "
                     f"the same off-arm test P12 asks",
               basis=f"from-{pid}-enclosure")
    a["reuse_keys"] = [keys[0]]
    return a


# ---- the reuse layer is about ONE key (predicates.yaml, P11..P13) ----------
# P11 records the candidates still withholding their feature; P10 and P12
# record, in `reuse_keys`, the keys their YES rests on. Each may only use keys
# the one before it kept, so the reuse key is the intersection.
REUSE_KEY_PREDICATES = ("P10", "P12")


def reuse_allowed_keys(answers: dict, pid: str) -> list[str] | None:
    """The keys `pid` (P10 or P12) may rest a YES on, or None when the layer
    above it recorded no key set (an answer file from before key scoping, or
    P11 unread). P10 ranges over P11's still-withheld keys -- plus, when P11
    is UNRESOLVED, the keys whose state it couldn't read (p11_answer); P12
    over those P10 also qualified."""
    allowed = (answers.get("P11") or {}).get("withholding_keys")
    if allowed is None:
        return None
    if pid == "P12":
        p10 = answers.get("P10") or {}
        if "reuse_keys" not in p10:
            return None
        allowed = [k for k in allowed if k in set(p10["reuse_keys"])]
    return sorted(allowed)


def reuse_scope(answers: dict) -> list[str] | None:
    """The reuse key(s): still withheld (P11), this change's feature (P10),
    covering the change (P12). None when any of the three recorded no keys."""
    allowed = reuse_allowed_keys(answers, "P12")
    p12 = answers.get("P12") or {}
    if allowed is None or "reuse_keys" not in p12:
        return None
    return sorted(set(allowed) & set(p12["reuse_keys"]))


def derived_from(a: dict) -> str | None:
    """The predicate an answer was taken from (P5/P6 for a P12 set by
    candidate_from_enclosure), or None for an answer of its own."""
    b = str(a.get("basis") or "")
    if b.startswith("from-") and b.endswith("-enclosure"):
        return b[len("from-"):-len("-enclosure")]
    return None


def reuse_key_violation(answers: dict, pid: str) -> dict | None:
    """A YES on P10 or P12 resting on no key it may use, or None.

    The independent "at least one candidate" readings of P10, P11 and P12 let
    reuse hold for three different keys -- measured on the revert board and
    the 50-PR pilot, 12 of 24 reuse verdicts had no one key satisfying all
    three, and 7 named a key P11 never showed still withholding (a flag on
    for everyone, which withholds the change from no one). Returns the keys
    the predicate may use and a question context naming them, so the caller
    asks it again; a second violation is answered NO (see reuse_scope_no).
    """
    a = answers.get(pid) or {}
    if pid not in REUSE_KEY_PREDICATES or a.get("value") is not True:
        return None
    allowed = reuse_allowed_keys(answers, pid)
    if allowed is None:
        return None
    named = sorted(set(a.get("reuse_keys") or []))
    if set(named) & set(allowed):
        return None
    src = derived_from(a)
    if src:
        reason = (f"{pid} YES (taken from {src}'s enclosing key) names "
                  f"{', '.join(named) or 'no key'}, none of which it may use "
                  f"({', '.join(allowed) or 'none'})")
        ctx = (f"{pid} WAS ASKED AGAIN: it was first answered YES automatically, "
               f"from {', '.join(named) or 'no named key'}, the one key {src}'s "
               f"answer found enclosing the change, and only "
               f"{', '.join(allowed) or 'no key'} may be used here. "
               "Answer for those keys only; NO if none of them qualifies.")
    else:
        reason = (f"{pid} YES names {', '.join(named) or 'no key'}, none of which "
                  f"it may use ({', '.join(allowed) or 'none'})")
        ctx = (f"{pid} WAS ASKED AGAIN: its first YES rested on "
               f"{', '.join(named) or 'no named key'}, and only "
               f"{', '.join(allowed) or 'no key'} may be used here. "
               "Answer for those keys only; NO if none of them qualifies.")
    return {"pid": pid, "reason": reason, "allowed": allowed, "named": named,
            "context": ctx}


def reuse_scope_no(answers: dict, pid: str, violation: dict) -> dict:
    """The NO a second key-scope violation settles on: the predicate's YES
    rests on no key the layer above it kept."""
    return answer(False, f"{pid}: no usable key -- {violation['reason']}",
                  basis="key-scope")


def diff_wired_keys(pkt: Packet) -> list[str]:
    """Flag keys this diff wires: declared by it, or evaluated on a line it
    adds or changes. The same test diff_wired_guard applies to P5's keys."""
    added = {(h.path, n) for h in pkt.hunks for n in _changed_new_lines(h)}
    keys = set(pkt.keys_added_by_diff or [])
    keys |= {s["key"] for s in pkt.flag_sites_head
             if s.get("key") and (s["path"], s["line"]) in added}
    return sorted(keys)


def reuse_contradiction(answers: dict, candidate_keys: list[str],
                        wired_keys: list[str]) -> dict | None:
    """A P12 YES that contradicts P5's NO about the same gate, or None.

    The keys are the candidates P12's evidence names (its procedure requires
    naming one; it records no structured citations). Not fired when P12 was
    itself derived from P5/P6, or when P5's NO came from diff_wired_guard
    (that NO is about a pre-existing gate, not a reading of this one). The
    caller asks P12 again with `context`, rather than forcing an answer: a
    diff that wires a key around only some hunks can be a correct reuse.
    """
    p12, p5 = answers.get("P12") or {}, answers.get("P5") or {}
    if (p12.get("value") is not True or p12.get("from_enclosure")
            or p5.get("value") is not False or p5.get("basis") == "diff-wired-guard"):
        return None
    said = _enclosure_said(p12)
    named = [k for k in candidate_keys
             if re.search(rf"(?<![\w-]){re.escape(k)}(?![\w-])", said)]
    if not named or any(k not in wired_keys for k in named):
        return None
    p5_said = next((str(s.get("evidence")) for s in p5.get("samples") or []
                    if s.get("evidence")), None) or str(p5.get("evidence") or "")
    cites = []
    for c in _enclosure_cites(p5):
        ref = f"{c.get('path')}:{c.get('line')}"
        if ref not in cites:
            cites.append(ref)
    ctx = ("P5 ANSWERED NO -- its recorded finding about the flag checks this "
           "diff adds or changes, given for this predicate:\n  "
           + " ".join(p5_said.split())
           + (f"\n  P5 cited: {', '.join(cites[:8])}" if cites else "")
           + f"\nThe candidate{'s' if len(named) > 1 else ''} "
           f"{', '.join(named)} {'are' if len(named) > 1 else 'is'} evaluated on "
           "lines this diff adds or changes, so for "
           f"{'them' if len(named) > 1 else 'it'} the off arm over the changed "
           "hunks is the diff's own code as written, not a placement to imagine.")
    return {"keys": named,
            "reason": f"P12 YES on diff-wired {', '.join(named)} beside a P5 NO",
            "context": ctx}


def setup_ld_client(ld_client: LDClient, setup: dict) -> None:
    """Give an LD client what build_packet knows about the keys (Packet.ld_setup):
    which project a key lives in, and the default the code serves when LD
    has no such flag. Without the defaults, a flag created in LD after the
    PR's dispatch reads as unreadable instead of serving its declared
    default."""
    for key, (project, env_map) in (setup.get("key_projects") or {}).items():
        ld_client.set_key_project(key, project, env_map)
    for key, (value, added) in (setup.get("defaults") or {}).items():
        ld_client.set_code_default(key, value, added)


def caller_gate_projects(pkt: Packet, ld_client: LDClient | None) -> None:
    """."""
    if ld_client is None:
        return
    for g in getattr(pkt, "caller_gates", None) or []:
        for key, (project, env_map) in (g.get("key_projects") or {}).items():
            ld_client.set_key_project(key, project, env_map)


def apply_enclosure(pkt: Packet, ld_client: LDClient | None,
                    merged_date: str | None, answers: dict, pid: str,
                    log=None) -> None:
    """."""
    say = log or (lambda msg: None)
    if pid not in ("P5", "P6") or pid not in answers:
        return
    caller_gate_projects(pkt, ld_client)
    # A P5 YES that cites only pre-existing, untouched gates is P6's
    # question, not P5's (see diff_wired_guard).
    if pid == "P5":
        g = diff_wired_guard(pkt, answers["P5"])
        if g:
            answers["P5"] = {**g, "overrides": answers["P5"].get("basis")}
            say(f"  P5   {'False':10s} (diff-wired guard: the cited gate already existed)")
            return
    new = gate_state_from_enclosure(pkt, ld_client, merged_date, pid, answers[pid])
    if (new is None and answers[pid].get("value") is True
            and (answers.get("P8") or {}).get("value") is True
            and not (answers.get("P8") or {}).get("from_enclosure")):
        # The YES names a gate whose key could not be resolved, so P7/P8 still
        # read the flags NEAR the change -- which need not be that gate. That
        # fallback is kept where it can only route on (an exposing P8), but a
        # withholding P8 from proximity would decide `already-flagged` -- the
        # verdict whose error hides real exposure -- on a flag nobody showed
        # is the gate. Unknown is not guessed: P7 escalates instead.
        answers["P7"] = {**answer(
            UNRESOLVED, f"{pid} found an enclosing gate, but its key could not "
                        f"be resolved from its citations; the flags near the "
                        f"change are not shown to be that gate",
            basis="ld-api"), "from_enclosure": pid}
        say(f"  P7   {'UNRESOLVED':10s} ({pid}'s gate key unresolved; proximity P8 not trusted)")
    if (new is None and answers[pid].get("value") is True
            and (answers.get("P33") or {}).get("value") is True
            and not (answers.get("P33") or {}).get("from_enclosure")):
        # The same rule for P33: a proximity flag still holding back users
        # in main production would decide already-flagged (T-AF-4) on a
        # flag nobody showed is the gate. Its NO can only route on.
        answers["P33"] = {**answer(
            UNRESOLVED, f"{pid} found an enclosing gate, but its key could not "
                        f"be resolved from its citations; the flags near the "
                        f"change are not shown to be that gate",
            basis="ld-api"), "from_enclosure": pid}
        say(f"  P33  {'UNRESOLVED':10s} ({pid}'s gate key unresolved; proximity P33 not trusted)")
    if new:
        for k in ("P8", "P33"):
            if k not in new and not _answered(answers.get(k)):
                answers.pop(k, None)
        for k, v in new.items():
            answers[k] = {**v, "from_enclosure": pid}
            say(f"  {k:4s} {str(v['value']):10s} (from {pid}'s enclosing keys)")
    gate = enclosing_gate_candidates(pkt, ld_client, merged_date, answers, pid)
    if gate:
        answers.update(gate)
        say(f"  P9/P11 (with {pid}'s enclosing gate as a candidate: "
            f"{', '.join(gate['P9']['enclosing_candidates'])})")
    p12 = candidate_from_enclosure(pkt, pid, answers[pid])
    if p12:
        answers["P12"] = {**p12, "from_enclosure": pid}
        say(f"  P12  {'True':10s} (from {pid}'s enclosing key)")


def _answered(a: dict | None) -> bool:
    """An answer the answerer gave (merge_inline's inline reply, or the keyed
    reader's samples), not one read here."""
    return str((a or {}).get("basis") or "").startswith(("inline:", "model:"))


def enclosing_gate_candidates(pkt: Packet, ld_client: LDClient | None,
                              merged_date: str | None, answers: dict,
                              pid: str) -> dict | None:
    """P9/P11 with the gate a P6 YES names counted as a reuse candidate, or
    None to keep them."""
    if pid != "P6" or (answers.get(pid) or {}).get("value") is not True:
        return None
    if (answers.get("P8") or {}).get("value") is not False:
        return None
    enc = answers[pid]
    keys = keys_at_citations(pkt, _enclosure_cites(enc), evidence=_enclosure_said(enc))
    keys = [k for k in keys if k not in {c["key"] for c in pkt.candidates}]
    if not keys or not (ld_client and ld_client.available and merged_date):
        return None
    snaps = dict((pkt.ld or {}).get("snapshots") or {}) if isinstance(pkt.ld, dict) else {}
    snaps = {c["key"]: snaps[c["key"]] for c in pkt.candidates if c["key"] in snaps}
    # The feature flag search's candidates stay candidates beside the gate
    # (feature_candidate_answers), with the state read when they were added.
    fsnaps = getattr(pkt, "feature_snapshots", None) or {}
    fkeys = [k for k in feature_keys(pkt) if k not in keys and k in fsnaps]
    snaps.update({k: fsnaps[k] for k in fkeys})
    for k in keys:
        try:
            snaps[k] = ld_client.snapshot(k, merged_date)
        except LDUnavailable:
            return None
    live = {k: s for k, s in snaps.items() if not (s or {}).get("archived")}
    keys = [k for k in keys if k in live]
    if not keys:
        return None
    near = [c["key"] for c in pkt.candidates]
    p9 = answer(True, f"the enclosing gate {pid} found ({', '.join(keys)}) existed at "
                      f"merge_base and is a reuse candidate"
                      + (f", with the keys evaluated near the change: {', '.join(near[:6])}"
                         if near else "")
                      + (f", and the feature flag search's: {', '.join(fkeys)}" if fkeys else ""),
                basis="symbol-table@merge_base")
    p9["enclosing_candidates"] = keys
    if fkeys:
        p9["feature_candidates"] = fkeys
    p11 = p11_answer(live, [ld_client.main_production])  # ruling R5, as P11 above
    return {"P9": {**p9, "from_enclosure": pid}, "P11": {**p11, "from_enclosure": pid}}


def feature_keys(pkt: Packet) -> list[str]:
    """The feature flag search's verified keys that aren't already reuse
    candidates from near the change (reader/feature_search.py)."""
    near = {c["key"] for c in pkt.candidates}
    return [c["key"] for c in getattr(pkt, "feature_candidates", None) or [] if c["key"] not in near]


def feature_candidate_answers(pkt: Packet, answers: dict, main_env: str | None) -> dict:
    """P9 and P11 with the feature flag search's verified flags counted as
    reuse candidates, or {} when it found none that isn't one already."""
    keys = feature_keys(pkt)
    if not keys:
        return {}
    near = [c["key"] for c in pkt.candidates]
    p9 = answer(True, f"the feature flag search found {', '.join(keys)}, the flag"
                      f"{'s' if len(keys) > 1 else ''} releasing the feature this change "
                      f"belongs to, present at merge_base"
                      + (f"; evaluated near the change: {', '.join(near[:6])}" if near else ""),
                basis="feature-search")
    p9["feature_candidates"] = keys
    out = {"P9": p9}
    fsnaps = getattr(pkt, "feature_snapshots", None) or {}
    if not main_env or any(k not in fsnaps for k in keys):
        return out
    known = ((pkt.ld or {}).get("snapshots") or {}) if isinstance(pkt.ld, dict) else {}
    snaps = {c["key"]: known[c["key"]] for c in pkt.candidates if c["key"] in known}
    snaps.update({k: fsnaps[k] for k in keys})
    archived = sorted(k for k, s in snaps.items() if (s or {}).get("archived"))
    live = {k: s for k, s in snaps.items() if k not in archived}
    if not live:
        out["P11"] = {**answer(False, "P11: every candidate is archived "
                               f"({', '.join(archived)}), so none is a release lever",
                               basis="ld-api"), "withholding_keys": []}
        return out
    out["P11"] = p11_answer(live, [main_env])
    if archived:
        out["P11"]["archived_candidates"] = archived
    return out


def _owners_for(rules: dict[str, list[str]], paths: list[str]) -> dict:
    import fnmatch
    hit: dict[str, list[str]] = {}
    for p in paths:
        for pat, own in rules.items():
            probe = pat.lstrip("/")
            if fnmatch.fnmatch(p, probe) or fnmatch.fnmatch(p, probe + "*") \
               or p.startswith(probe.rstrip("*")):
                hit[p] = own
    teams = sorted({t for v in hit.values() for t in v})
    return {"paths": len(hit), "teams": teams}


def p11_answer(snaps: dict, user_facing: list[str]) -> dict:
    """P11 over the non-archived candidates, with the keys the rest of the
    reuse layer may use (P10, P12 and P13 range over `withholding_keys`,
    predicates.yaml).

    When P11 is UNRESOLVED -- no key is known to withhold and some key's state
    can't be read -- those unreadable keys stay usable. Leaving them out made
    the allowed set empty, so a P10 YES was key-scoped to NO and both P11
    branches reached the battery: the walk never escalated, and unreadable
    flag state became a confident verdict. With them in, the walk explores
    both P11 branches and escalates when the answer decides it."""
    ans = _withholding(snaps, user_facing, "P11", any_env=True)
    keys = withholding_keys(snaps, user_facing)
    if ans["value"] == UNRESOLVED:
        unread = unreadable_keys(snaps, user_facing)
        ans["unreadable_keys"] = unread
        keys = sorted(set(keys) | set(unread))
    ans["withholding_keys"] = keys
    return ans


def unreadable_keys(snaps: dict, user_facing: list[str]) -> list[str]:
    """The candidate keys whose state is unknown in some user-facing
    production environment (no targeting read and no `on`): P11 can't rule
    them out."""
    keys = []
    for k, s in snaps.items():
        envs = s.get("environments") or {}
        for name in user_facing:
            e = envs.get(name)
            if e and not e.get("serves") and e.get("on") is None:
                keys.append(k)
                break
    return sorted(keys)


def withholding_keys(snaps: dict, user_facing: list[str]) -> list[str]:
    """The candidate keys still withheld from some real users in at least one
    user-facing production environment -- P11's reading (`_withholding` with
    `any_env=True`), per key instead of over the set. A key whose state is
    unknown everywhere it is read is not included: nothing shows it still
    withholds."""
    keys = []
    for k, s in snaps.items():
        envs = s.get("environments") or {}
        for name in user_facing:
            e = envs.get(name)
            if not e:
                continue
            reach = e.get("serves")
            if (reach and reach != "all") or (not reach and e.get("on") is False):
                keys.append(k)
                break
    return sorted(keys)


def _withholding(snaps: dict, user_facing: list[str], which: str,
                 any_env: bool = False) -> dict:
    """Does each user-facing production env serve the exposing variation to
    real users?

    Two readings, matching the two predicates that use this:
      P8  (`any_env=False`) YES only if EVERY user-facing env withholds, so
          one exposing env settles NO.
      P11 (`any_env=True`)  YES if AT LEAST ONE user-facing env withholds
          (predicates.yaml), so one withholding env settles YES. P11 used
          P8's all-envs reading until an earlier PR.
    """
    exposing, withheld, unknown = [], [], []
    read_targeting = False
    for k, s in snaps.items():
        envs = s.get("environments") or {}
        for name in user_facing:
            e = envs.get(name)
            if not e:
                continue
            reach = e.get("serves")
            if reach:
                read_targeting = True
                tag = f"{k}@{name}[{reach}: {e.get('serves_basis')}]"
                reaches_all = reach == "all"
                reaches_some = reach in ("all", "partial", "cohort")
                if (reaches_all if any_env else reaches_some):
                    exposing.append(tag)
                else:
                    withheld.append(tag)
            elif e.get("on") is None:
                unknown.append(f"{k}@{name}({e.get('basis')})")
            elif e["on"]:
                exposing.append(f"{k}@{name}")
            else:
                withheld.append(f"{k}@{name}")
    note = ("" if read_targeting and all("[" in x for x in exposing)
            else " (targeting not read for some, so `on` is read as exposing)")
    if any_env:
        if withheld:
            return answer(True, f"{which}: withheld from some real users in "
                                f"user-facing production: "
                                f"{', '.join(withheld[:5])}",
                          basis="ld-api")
    elif exposing:
        return answer(False,
                      f"{which}: served to real users in user-facing "
                      f"production: {', '.join(exposing[:5])}{note}",
                      basis="ld-api")
    if unknown:
        return answer(UNRESOLVED,
                      f"{which}: state unknown for {', '.join(unknown[:5])}",
                      basis="ld-api")
    if exposing:
        return answer(False, f"{which}: served to every real user in every "
                             f"user-facing production environment: "
                             f"{', '.join(exposing[:5])}{note}",
                      basis="ld-api")
    return answer(True, f"{which}: withheld from real users in every "
                        f"user-facing production environment: "
                        f"{', '.join(withheld[:5])}",
                  basis="ld-api")
