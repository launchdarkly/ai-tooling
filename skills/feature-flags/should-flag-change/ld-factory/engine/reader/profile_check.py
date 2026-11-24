"""Does a derived profile read this change's flag checks? And the agent's repair.

The skill derives a profile for a repo it has none for (derive_profile). That
is mechanical, so it can miss a repo's own flag helper or match code that
isn't a flag check. `check` finds both, on the files the change touches only:

- a gap: a known flag key written in a changed shipping code file where the
  profile found no flag check near it. Known keys are the profile's declared
  ones (by key, or by the name the code declares it under when that name is
  called or read as a member, `Name(` or `x.Name`, a suffix allowed:
  `x.NamePred`; a bare identifier of the same name is a local name) plus,
  when LaunchDarkly can be read, every flag in the project (and a React
  `useFlags()` property spelled as a flag's camel-cased key);
- a suspect: with LaunchDarkly read, a flag check whose key the project has no
  flag for and the change doesn't add.

When either turns up, the agent repairs the profile (references/PROFILE_REPAIR.md):
patterns to add or narrow, each with the quoted lines it should cover. Only
those additions are saved for the repo; later runs derive afresh and apply
the ones that still match the code (`still_relevant`), then check again.
`verify_fix` checks every quoted line against the commit and keeps a change
only when re-reading the changed files with it covers the gap (or clears the
suspect) it was made for.
"""
from __future__ import annotations

import copy
import json
import re

NEAR = 2  # a key literal this many lines from a flag check is that check's
LISTS = ("keyed_calls", "extra_patterns", "resolved_patterns", "exclude_symbols", "exclude_files")


def camel(key: str) -> str:
    parts = re.split(r"[-_.]", key)
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def project_keys(ld_client) -> set[str] | None:
    """Every flag key in the LaunchDarkly project, or None when it can't be read."""
    if not (ld_client and getattr(ld_client, "available", False)):
        return None
    keys, offset = set(), 0
    while True:
        r = ld_client._get(f"/api/v2/flags/{ld_client.project}", summary="true", limit=100, offset=offset)
        if not isinstance(r, dict) or "items" not in r:
            return keys or None
        items = r.get("items") or []
        keys.update(i.get("key") for i in items if i.get("key"))
        offset += len(items)
        if not items or offset >= int(r.get("totalCount") or 0):
            return keys


# Flags are checked in code, not in data or docs (a generated defaults table,
# an API spec, a README naming a flag).
CODE = (".go", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".rb", ".java", ".kt", ".kts", ".scala",
        ".cs", ".fs", ".vb", ".php", ".swift", ".m", ".mm", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".ex",
        ".exs", ".erl", ".dart", ".lua", ".vue", ".svelte", ".groovy", ".clj", ".cljs", ".hs", ".pl", ".r")
DEFINITION = re.compile(r"\s*(func|def|fn|function|export\s+(default\s+)?(async\s+)?function|(export\s+)?(const|let|var)\s+[\w$]+\s*=\s*(async\s*)?\()\b")
COMMENT = re.compile(r"\s*(//|#|/\*|\*|<!--|--\s)")  # a comment line mentions, it doesn't check
STRING = re.compile(r"""(['"`])(?:\\.|(?!\1).)*\1""")
IMPORT = re.compile(r"^\s*(import\b|export\s+\{[^}]*\}\s+from\b|from\s+\S+\s+import\b)|\brequire\(")


def check(repo, pkt, st, ld_keys: set[str] | None, profile) -> dict:
    """Gaps and suspects in the changed shipping files at head. `st` is the
    profile's symbol table at head (keys, and the names they're declared as)."""
    st_head_keys = st.keys
    names = {n: k for n, k in (st.by_symbol or {}).items()
             if len(n) >= 6 and re.fullmatch(r"[A-Za-z_$][\w$]*", n) and n != k}
    alt = "|".join(map(re.escape, sorted(names, key=len, reverse=True)))
    member_re = re.compile(r"\.\s*(" + alt + r")[\w$]*") if names else None
    call_re = re.compile(r"(?<![\w$.])(" + alt + r")[\w$]*\s*\(") if names else None
    head = pkt.unit["head"]
    ev = profile.data.get("evaluation") or {}
    skip = set(ev.get("exclude_files") or []) | {d.get("file") for d in profile.data.get("flag_declarations", [])}
    known = set(st_head_keys) | set(ld_keys or ())
    known = {k for k in known if len(k) >= 4}
    camels = {camel(k): k for k in (ld_keys or ()) if camel(k) != k}
    site_lines: dict[str, set[int]] = {}
    for s in pkt.flag_sites_head or []:
        site_lines.setdefault(s["path"], set()).add(s["line"])
    gaps = []
    for f in pkt.files:
        if f["role"] != "ships" or f["path"] in skip or not f["path"].lower().endswith(CODE):
            continue
        text = repo.file_at(head, f["path"])
        if not text:
            continue
        react = bool(re.search(r"\buseFlags\b|\bwithLDConsumer\b|\bldFlags\b", text))
        near = site_lines.get(f["path"], set())
        in_import = False
        for n, line in enumerate(text.splitlines(), 1):
            if re.match(r"\s*(import|export)\b[^'\"]*\{[^}]*$", line) or re.match(r"\s*import\s*\($", line):
                in_import = True
            elif in_import and re.search(r"[})]", line):
                in_import = False
                continue
            if in_import or COMMENT.match(line):
                continue
            hits = [m.group(1) for m in re.finditer(r"['\"`]([A-Za-z0-9][A-Za-z0-9._-]{3,})['\"`]", line)
                    if m.group(1) in known]
            if names and not IMPORT.search(line):
                code = STRING.sub('""', line)  # a name inside a string is text, not a reference
                hits += [names[m.group(1)] for m in member_re.finditer(code)]
                if not DEFINITION.match(code):
                    hits += [names[m.group(1)] for m in call_re.finditer(code)]
            if react and camels:
                hits += [camels[m.group(1)] for m in re.finditer(r"\.\s*([a-z][A-Za-z0-9]{3,})\b", line)
                         if m.group(1) in camels]
            for key in dict.fromkeys(hits):
                if not any(abs(n - s) <= NEAR for s in near):
                    gaps.append({"path": f["path"], "line": n, "key": key, "text": line.strip()[:200]})
    suspects = []
    if ld_keys is not None:
        added = set(pkt.keys_added_by_diff or [])
        for s in pkt.flag_sites_head or []:
            k = s.get("key")
            if k and k not in ld_keys and k not in added:
                suspects.append({"path": s["path"], "line": s["line"], "key": k, "text": s.get("text", "")})
    return {"gaps": gaps[:40], "suspects": suspects[:40], "n_gaps": len(gaps), "n_suspects": len(suspects),
            "ld_keys": None if ld_keys is None else len(ld_keys)}


def merged(profile_data: dict, additions: dict) -> dict:
    """The profile with the repair's additions (new patterns, declarations,
    exclusions) appended where they belong."""
    out = copy.deepcopy(profile_data)
    ev = out.setdefault("evaluation", {})
    for k in LISTS:
        for item in additions.get(k) or []:
            if item not in (ev.get(k) or []):
                ev.setdefault(k, []).append(item)
    for k in ("flag_declarations", "flag_defaults"):
        for d in additions.get(k) or []:
            if d not in (out.get(k) or []):
                out.setdefault(k, []).append(d)
    if additions.get("symbol_call") is True:
        ev["symbol_call"] = True
    return out


def merge_additions(saved: dict, new: dict) -> dict:
    """Saved repair additions plus a new repair's, without duplicates."""
    out = copy.deepcopy(saved or {})
    for k in LISTS + ("flag_declarations", "flag_defaults"):
        for item in (new or {}).get(k) or []:
            if item not in (out.get(k) or []):
                out.setdefault(k, []).append(item)
    if (new or {}).get("symbol_call") is True:
        out["symbol_call"] = True
    return out


def _compiles(pat) -> bool:
    if not isinstance(pat, str) or not pat:
        return False
    try:
        re.compile(pat)
        return True
    except re.error:
        return False


def _is_index(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def well_formed(additions) -> tuple[dict, list[str]]:
    """The additions entries the reader can use, and why the rest were
    dropped. Additions come from files the check doesn't control (a repo's
    .launchdarkly/should-i-flag.json, a repair saved by an older version):
    an entry in the wrong shape (a keyed call written as {"name", "arg"}) is
    dropped with its reason instead of crashing the read."""
    if not isinstance(additions, dict):
        return {}, ["additions is not an object"]
    out, bad = {}, []

    def keep(k, item, ok, need):
        if ok:
            out.setdefault(k, []).append(item)
        else:
            bad.append(f"{k}: {json.dumps(item)[:80]} needs {need}")

    for item in additions.get("keyed_calls") or []:
        keep("keyed_calls", item, isinstance(item, dict) and _compiles(item.get("pattern"))
             and _is_index(item.get("key_arg", 0)),
             'a "pattern" regex and a 0-based "key_arg"')
    for k in ("extra_patterns", "resolved_patterns"):
        for item in additions.get(k) or []:
            keep(k, item, _compiles(item), "to be a regex string")
    for k in ("exclude_symbols", "exclude_files"):
        for item in additions.get(k) or []:
            keep(k, item, isinstance(item, str) and bool(item), "to be a string")
    for item in additions.get("flag_declarations") or []:
        # The reader reads keys only through "key_group", and falls back to
        # "file" when "files" is empty: both must be there to be read at all.
        files = item.get("files") if isinstance(item, dict) else None
        src = isinstance(item, dict) and (
            (isinstance(files, list) and files and all(isinstance(f, str) and f for f in files))
            or (not files and isinstance(item.get("file"), str) and bool(item["file"])))
        keep("flag_declarations", item, bool(src) and isinstance(item.get("id"), str)
             and _compiles(item.get("pattern")) and _is_index(item.get("key_group")),
             'an "id", a "pattern" regex, a "file" or a non-empty "files", and a "key_group"')
    for item in additions.get("flag_defaults") or []:
        keep("flag_defaults", item, isinstance(item, dict) and isinstance(item.get("file"), str)
             and _compiles(item.get("pattern")) and _is_index(item.get("default_group"))
             and (_is_index(item.get("symbol_group")) or _is_index(item.get("key_group"))),
             'a "file", a "pattern" regex, a "default_group", and a "symbol_group" or "key_group"')
    if additions.get("symbol_call") is True:
        out["symbol_call"] = True
    return out, bad


def still_relevant(repo_path, rev: str, additions: dict) -> tuple[dict, list[str]]:
    """The saved additions that still match something in the repo at `rev`
    (a pattern with a hit, a symbol or file that exists), and what was
    dropped. Applied on top of a fresh derivation, so a helper the repo has
    since removed stops shaping how its code is read."""
    import subprocess

    def git(*a) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(repo_path), *a], capture_output=True, text=True)

    def has(pattern: str, fixed: bool = False) -> bool:
        flags = ["-w", "-F"] if fixed else ["-P"]
        return bool(git("grep", "-l", "-I", *flags, "-e", pattern, rev).stdout.strip())

    additions, dropped = well_formed(additions)
    kept = {}
    for k in LISTS + ("flag_declarations", "flag_defaults"):
        for item in additions.get(k) or []:
            if k == "flag_defaults" and isinstance(item, dict):
                # Its pattern spans lines (a map entry's braces), which a
                # line-by-line grep can't match: kept while its file exists.
                pat, name, path = None, None, item.get("file")
            elif isinstance(item, dict):
                pat, name, path = item.get("pattern"), item.get("name"), item.get("file")
            else:
                pat, name, path = (item, None, None) if k in ("extra_patterns", "resolved_patterns") else \
                    (None, item if k == "exclude_symbols" else None, item if k == "exclude_files" else None)
            try:
                if pat:
                    ok = has(pat)
                elif name:
                    ok = has(name, fixed=True)
                elif path:
                    ok = any(c in path for c in "*?[") or git("cat-file", "-e", f"{rev}:{path}").returncode == 0
                else:
                    ok = True
            except re.error:
                ok = False
            if ok:
                kept.setdefault(k, []).append(item)
            else:
                dropped.append(f"{k}: {str(item)[:80]}")
    if additions.get("symbol_call") is True:
        kept["symbol_call"] = True
    return kept, dropped


def verify_fix(repo, head: str, profile_cls, profile, fix: dict, report: dict, sites_at) -> dict:
    """Check the repair. Every quoted example must be a real line at head; the
    repaired profile must then find a flag check at each gap example and none
    at each suspect example. `sites_at(profile)` re-reads the changed files'
    flag checks with a profile. Returns the kept additions and why anything
    was dropped."""
    problems = []
    examples = fix.get("examples") or []
    for e in examples:
        text = repo.file_at(head, e.get("path") or "")
        lines = text.splitlines() if text else []
        n = e.get("line")
        if not isinstance(n, int) or not 0 < n <= len(lines):
            problems.append(f"{e.get('path')}:{n} is not a line at head")
            continue
        want = re.sub(r"\s+", " ", e.get("text") or "").strip()
        got = re.sub(r"\s+", " ", lines[n - 1]).strip()
        if not want or (want not in got and got not in want):
            problems.append(f"{e.get('path')}:{n} reads {got[:80]!r}, not {want[:80]!r}")
    for item in (fix.get("additions") or {}).get("keyed_calls") or []:
        arg = item.get("key_arg", 0) if isinstance(item, dict) else None
        if not (isinstance(item, dict) and isinstance(item.get("pattern"), str) and item["pattern"]
                and isinstance(arg, int) and not isinstance(arg, bool) and arg >= 0):
            problems.append(f"keyed_calls entry {json.dumps(item)[:80]} needs a \"pattern\" (a regex "
                            f"ending at the call's opening paren) and a \"key_arg\" (the key's "
                            f"0-based argument position)")
    for k in LISTS + ("flag_declarations",):
        for item in (fix.get("additions") or {}).get(k) or []:
            pat = item.get("pattern") if isinstance(item, dict) else (item if k in ("extra_patterns", "resolved_patterns") else None)
            if pat:
                try:
                    re.compile(pat)
                except re.error as err:
                    problems.append(f"{k} pattern doesn't compile: {err}")
    if problems:
        return {"ok": False, "problems": problems}
    data = merged(profile.data, fix.get("additions") or {})
    repaired = profile_cls(profile.name, data, profile.ld)
    sites = sites_at(repaired)
    lines = {(s["path"], s["line"]) for s in sites}
    for e in examples:
        hit = any(e["path"] == p and abs(e["line"] - l) <= NEAR for p, l in lines)
        if e.get("covers") == "suspect" and hit:
            problems.append(f"{e['path']}:{e['line']} still reads as a flag check")
        if e.get("covers", "gap") == "gap" and not hit:
            problems.append(f"{e['path']}:{e['line']} still has no flag check")
    return {"ok": not problems, "problems": problems, "profile": data}
