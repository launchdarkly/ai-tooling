#!/usr/bin/env python3
"""Check a repo profile's claims against a real checkout. Run before trusting it.

A profile is a claim about a repo at a point in time. Every claim here is
checkable, so it gets checked: a drifted regex silently returns zero flag
declarations, which would make every gate in the repo invisible and drive
`already-flagged` and `reuse-existing` to zero without any error."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reader.sources import Profile, Repo, build_symbol_table  # noqa: E402


def in_scope(path: str, ev: dict) -> bool:
    """Apply exclude_files + search_exclude, so a count means something."""
    import fnmatch
    if path in set(ev.get("exclude_files", [])):
        return False
    for pat in ev.get("search_exclude", []):
        bare = pat.replace("**/", "")
        if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path, bare) \
           or path.startswith(pat.replace("**", "").rstrip("/") + "/"):
            return False
    return True


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    name, path = argv[1], Path(argv[2])
    rev = "HEAD"
    if "--rev" in argv:
        rev = argv[argv.index("--rev") + 1]

    # A path to a .json profile is one written outside profiles/ (the
    # should-flag-change skill writes them for repos no profile covers).
    prof = Profile.from_file(name) if name.endswith(".json") else Profile.load(name)
    repo = Repo(path)
    sha = repo.rev_parse(rev)
    print(f"profile {name}  repo {path}  rev {rev} ({sha[:12]})\n")

    st = build_symbol_table(repo, prof, sha)
    print(f"declaration sources: {st.sources}")
    print(f"keys: {len(st.keys)}   symbol->key: {len(st.by_symbol)}")
    ok = True
    if st.problems:
        ok = False
        print("\nPROBLEMS")
        for p in st.problems:
            print("  -", p)
    if not st.keys:
        ok = False
        print("\nFAIL: zero flag keys extracted -- the pattern is broken")

    if st.by_symbol:
        print("\nsample symbol -> key")
        for s, k in list(st.by_symbol.items())[:5]:
            print(f"  {s:44s} -> {k}")

    # An evaluation pattern that matches nothing in the whole tree is dead.
    print("\nevaluation patterns")
    ev = prof.data.get("evaluation", {})
    pats = ev.get("extra_patterns") or []
    if not pats:
        print(f"  (none declared; go_evaluation="
              f"{ev.get('go_evaluation', 'n/a')})")
    for pat in pats:
        hits = repo.grep_at(sha, pat)
        live = [h for h in hits if in_scope(h[0], ev)]
        status = "ok" if live else "NO LIVE HITS"
        if not live:
            ok = False
        print(f"  [{status}] {len(hits)} raw, {len(live)} in scope")
        for h in live[:3]:
            print(f"      {h[0]}:{h[1]}")

    # resolved_patterns only count where the captured name is a declared
    # flag, so "live" means: at least one hit resolves through the symbol
    # table (a pattern that matches only non-flags is dead).
    import re as _re
    for pat in ev.get("resolved_patterns") or []:
        hits = [h for h in repo.grep_at(sha, pat) if in_scope(h[0], ev)]
        resolved = [h for h in hits
                    for m in [_re.search(pat, h[2])]
                    if m and (st.key_for(m.group(1)) or m.group(1) in st.keys)]
        status = "ok" if resolved else "NO RESOLVED HITS"
        if not resolved:
            ok = False
        print(f"  [{status}] resolved_pattern: {len(hits)} in scope, "
              f"{len(resolved)} resolve to a flag")

    # alias_declarations: the declaring file must still yield at least the
    # expected number of aliases, and at least one must be read somewhere in
    # scope -- a map nobody reads (or a pattern that stopped matching) is dead.
    if ev.get("alias_declarations"):
        from reader.mechanical import _alias_read_re, flag_aliases
        import fnmatch
        al = flag_aliases(repo, prof, sha)
        for ad in ev["alias_declarations"]:
            mine = {a: v for a, v in al.items() if v[1] == ad["file"]}
            want = ad.get("expect_at_least", 1)
            reads = 0
            for a in list(mine)[:10]:
                for hp, _, ht in repo.grep_at(sha, r"\b" + _re.escape(a) + r"\b"):
                    if hp != ad["file"] and in_scope(hp, ev) and (
                            not ad.get("scope") or fnmatch.fnmatch(hp, ad["scope"])) \
                            and _alias_read_re(a).search(ht):
                        reads += 1
            good = len(mine) >= want and reads > 0
            ok = ok and good
            print(f"  [{'ok' if good else 'FAIL'}] alias_declarations "
                  f"{ad['file']}: {len(mine)} aliases (want >= {want}), "
                  f"{reads} reads of the first 10 in scope")

    if ev.get("symbol_call"):
        specs = []
        for d in prof.data.get("flag_declarations", []):
            specs += d.get("import_specifiers", [])
        print("\n  symbol_call imports")
        for spec in specs:
            hits = repo.grep_at(sha, spec.replace("/", "/"))
            print(f"    [{'ok' if hits else 'NO HITS'}] {spec}: {len(hits)}")
            if not hits:
                ok = False

    # api_spec (P19): every spec file must parse to operations, public must
    # be a subset of hidden (the profile's stated relationship), and the
    # declaration/annotation patterns must match something in the tree.
    api = prof.data.get("api_spec")
    if api:
        from reader.mechanical import _spec_operations
        print("\napi_spec")
        pub = _spec_operations(repo, sha, api.get("public") or [])
        hid = _spec_operations(repo, sha, api.get("hidden") or [])
        for label, files, ops in (("public", api.get("public") or [], pub),
                                  ("hidden", api.get("hidden") or [], hid)):
            status = "ok" if ops or not files else "NO OPERATIONS"
            ok = ok and status == "ok"
            print(f"  [{status}] {label}: {len(ops)} operations from {files}")
        if hid and set(pub) - set(hid):
            ok = False
            print(f"  [FAIL] {len(set(pub) - set(hid))} public operations "
                  f"missing from hidden -- 'hidden-only means unpublished' "
                  f"no longer holds")
        for ext, rx in (api.get("function_decl") or {}).items():
            hits = repo.grep_at(sha, rx, [f"*{ext}"])
            ok = ok and bool(hits)
            print(f"  [{'ok' if hits else 'NO HITS'}] function_decl {ext}: "
                  f"{len(hits)}")
        if api.get("route_binding"):
            rx = api["route_binding"].replace("{Op}", r"[A-Za-z_]\w*")
            hits = repo.grep_at(sha, rx)
            ok = ok and bool(hits)
            wrappers = sorted({m.group(1) for _, _, t in hits
                               for m in [__import__("re").search(rx, t)] if m})
            known = set(api.get("user_credential_auth") or []) | \
                set(api.get("internal_only_auth") or [])
            print(f"  [{'ok' if hits else 'NO HITS'}] route_binding: "
                  f"{len(hits)} bindings; wrappers {wrappers}"
                  + (f" -- UNCLASSIFIED: {sorted(set(wrappers) - known)}"
                     if set(wrappers) - known else ""))
        if api.get("operation_annotation"):
            hits = repo.grep_at(sha, api["operation_annotation"])
            ok = ok and bool(hits)
            print(f"  [{'ok' if hits else 'NO HITS'}] operation_annotation: "
                  f"{len(hits)}")

    print("\nexclusions still present in the tree (each is a real false positive)")
    for sym in ev.get("exclude_symbols", []):
        hits = repo.grep_at(sha, sym)
        print(f"  {'found' if hits else 'GONE ':5s} {sym} ({len(hits)})")

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
