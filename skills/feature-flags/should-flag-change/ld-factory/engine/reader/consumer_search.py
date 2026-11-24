"""The consumer search: check an agent's claimed readers of a changed contract,
and settle an unresolved P19 from them."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

NOT_SHIPPING = re.compile(r"(_test\.go$|\.test\.|\.spec\.|\.stories\.|/__tests__/|/testdata/|/fixtures?/|/mocks?/"
                          r"|\.md$|(^|/)docs?/)")
FAMILY = {".go": "go", ".py": "py", ".ts": "js", ".tsx": "js", ".js": "js", ".jsx": "js", ".mjs": "js",
          ".graphql": "graphql", ".gql": "graphql", ".rb": "rb", ".java": "java", ".kt": "java", ".swift": "swift"}


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, errors="replace")


def family(path: str) -> str:
    ext = os.path.splitext(path)[1]
    return FAMILY.get(ext, ext)


def clients(repo: Path, base: str, explicit: list[str], profiles: list[dict]) -> list[dict]:
    """The client repositories the search may read: each `--client-repo
    NAME=PATH[@REV]`, else every checkout beside `repo` whose origin is
    another bundled profile's repo. A client is read as its default branch
    was when `base` was committed (a client written after the change can't
    show what relied on the old contract); one whose commit can't be resolved
    is left out."""
    out = []
    if explicit:
        for spec in explicit:
            name, _, rest = spec.partition("=")
            path, _, rev = rest.partition("@")
            out.append({"name": name, "path": str(Path(path).expanduser().resolve()), "rev": rev or None})
    else:
        own = _git(repo, "remote", "get-url", "origin").stdout.strip()
        for p in profiles:
            slug = p.get("repo") or ""
            if not slug or own.rstrip("/").removesuffix(".git").endswith(slug):
                continue
            cand = repo.parent / slug.split("/")[-1]
            url = _git(cand, "remote", "get-url", "origin").stdout.strip() if cand.is_dir() else ""
            if url.rstrip("/").removesuffix(".git").endswith(slug):
                out.append({"name": slug.split("/")[-1], "path": str(cand.resolve()), "rev": None})
    when = _git(repo, "log", "-1", "--format=%cI", base).stdout.strip()
    kept = []
    for c in out:
        rev = c["rev"]
        if not rev:
            for ref in ("origin/HEAD", "origin/main", "origin/master"):
                r = _git(c["path"], "rev-list", "-1", "--first-parent", f"--before={when}", ref)
                if r.returncode == 0 and r.stdout.strip():
                    rev = r.stdout.strip()
                    break
        r = _git(c["path"], "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}") if rev else None
        if r is not None and r.returncode == 0:
            kept.append({**c, "rev": r.stdout.strip()})
    return kept


def changed_lines(repo_path, base: str, head: str) -> dict[str, set[int]]:
    """Head-side lines the diff adds or modifies, per path."""
    out: dict[str, set[int]] = {}
    cur = None
    for line in _git(repo_path, "diff", "-U0", f"{base}...{head}").stdout.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
        elif line.startswith("+++ /dev/null"):
            cur = None
        elif line.startswith("@@") and cur:
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                start, n = int(m.group(1)), int(m.group(2) or 1)
                out.setdefault(cur, set()).update(range(start, start + n))
    return out


def verify(repos: dict, cc: dict, files: dict, changed: dict, diff_text: str) -> str | None:
    """None when `cc`'s reader checks out, else why not. `repos` maps "self"
    and each client name to (checkout, commit); `files` caches (repo, path) ->
    lines; `changed` is changed_lines(); `diff_text` the full diff."""
    chain = cc.get("chain") or []
    if not chain:
        return "no reader claimed"
    for c in chain:
        repo = c.get("repo") or "self"
        if repo not in repos:
            return f"repo {repo!r} is not this repository or a client checkout"
        path, line = c.get("path") or "", c.get("line")
        if (repo, path) not in files:
            checkout, rev = repos[repo]
            p = _git(checkout, "show", f"{rev}:{path}")
            files[(repo, path)] = p.stdout.splitlines() if p.returncode == 0 else None
        L = files[(repo, path)]
        if L is None:
            return f"{repo}:{path} does not exist at its commit"
        if not isinstance(line, int) or not 0 < line <= len(L):
            return f"{repo}:{path}:{line} is not a line at its commit"
        got, want = _norm(L[line - 1]), _norm(c.get("text"))
        if not want or (want not in got and got not in want):
            return f"{repo}:{path}:{line} reads {got[:80]!r}, not {want[:80]!r}"
    ch = [c for c in chain if c.get("role") == "changed" and (c.get("repo") or "self") == "self"
          and c["line"] in changed.get(c["path"], set()) and not NOT_SHIPPING.search(c["path"])]
    if not ch:
        return "no `changed` link is a line the diff adds or modifies in shipping code"
    tok = (cc.get("token") or "").strip()
    if len(tok) < 2:
        return "no token"
    if tok not in diff_text:
        return f"token {tok!r} does not appear in the diff"
    fams = {family(c["path"]) for c in ch}
    rd = [c for c in chain if c.get("role") == "reader"]
    if not rd:
        return "no reader link"
    for c in rd:
        repo = c.get("repo") or "self"
        if NOT_SHIPPING.search(c["path"]) or (repo == "self" and family(c["path"]) in fams):
            continue
        if tok in files[(repo, c["path"])][c["line"] - 1]:
            cc["verified_reader"] = c  # the link that passed, which `settle` quotes
            return None
    return "no reader link outside tests, in a client repository or another language, containing the token"


def check(repo: str, base: str, head: str, clients_: list[dict], reply: dict) -> list[dict]:
    """Every contract change in the reply, with `reader_verified` and, when
    not, `dropped` (why)."""
    repos = {"self": (repo, head), **{c["name"]: (c["path"], c["rev"]) for c in clients_}}
    changed = changed_lines(repo, base, head)
    diff_text = _git(repo, "diff", f"{base}...{head}").stdout
    files: dict = {}
    out = []
    for cc in reply.get("contract_changes") or []:
        why = verify(repos, cc, files, changed, diff_text)
        out.append({**cc, "reader_verified": why is None, **({"dropped": why} if why else {})})
    return out


def settle(model: dict, changes: list[dict], client_names: list[str]) -> dict:
    """P19 from the search, replacing the model's UNRESOLVED (kept as
    `model_answer`): YES when any reader verified, else NO."""
    ok = [c for c in changes if c["reader_verified"]]
    if ok:
        c = ok[0]
        cites = [{"path": x["path"], "line": x["line"], "why": "the changed contract"}
                 for x in c["chain"] if x.get("role") == "changed" and (x.get("repo") or "self") == "self"][:1]
        rd = c.get("verified_reader") or next(x for x in c["chain"] if x.get("role") == "reader")
        where = rd["path"] if (rd.get("repo") or "self") == "self" else f"{rd['repo']}'s {rd['path']}"
        more = f" (and {len(ok) - 1} more)" if len(ok) > 1 else ""
        return {"value": True, "basis": "consumer-search", "citations": cites, "model_answer": model,
                "evidence": f"{(c.get('what_changed') or 'The contract changes').rstrip('. ')}. A separate client reads it: "
                            f"{where} line {rd['line']} uses `{c['token']}`{more}."}
    return {"value": False, "basis": "consumer-search", "citations": [], "model_answer": model,
            "evidence": "The interface isn't shown to be published, and a search of this repository"
                        + (f" and {', '.join(client_names)}" if client_names else "")
                        + " found no separate client reading what changed."}
