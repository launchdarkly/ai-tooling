"""The risk search: check an agent's claimed risk findings, and answer P30 from them."""
from __future__ import annotations

import re
import subprocess
from collections import Counter

KINDS = {"new-call", "retarget", "cache", "fail-closed", "new-action", "removed", "stored-data"}
NOT_SHIPPING = re.compile(r"(_test\.go$|\.test\.|\.spec\.|\.stories\.|/__tests__/|/testdata/|\.md$|(^|/)docs?/)")


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _respaced(line: str) -> str:
    """A line with the whitespace between its tokens collapsed and trailing
    whitespace dropped. Leading indentation is kept as is: re-indenting a
    line can change what it does (Python, YAML)."""
    lead = line[:len(line) - len(line.lstrip())]
    return lead + re.sub(r"\s+", " ", line[len(lead):]).rstrip()


_SLASH_COMMENTS = re.compile(r"\.(go|ts|tsx|js|jsx|mjs|cjs|java|kt|kts|swift|c|cc|cpp|h|hpp|rs|scala|cs|proto|php|dart)$")
_HASH_COMMENTS = re.compile(r"(\.(py|rb|sh|bash|zsh|ya?ml|toml|tf|r)$|(^|/)(Dockerfile|Makefile)[^/]*$)")
_DASH_COMMENTS = re.compile(r"\.(sql|lua)$")


def _only_close_left(rest: str) -> bool:
    """After a block comment's */: nothing, or only the } of a JSX {/* */}."""
    return rest.strip() in ("", "}")

def _comment_only(path: str, line: str) -> bool:
    """A line that holds only a comment in its file's language. Directives
    written as comments still count as code: //go: lines, // +build, ///
    references, #! lines."""
    s = line.strip()
    if _SLASH_COMMENTS.search(path):
        if s.startswith(("//go:", "// +build", "///")):
            return False
        for opener in ("{/*", "/*"):
            if s.startswith(opener):  # a block comment, unless code follows where it closes
                end = s.find("*/", len(opener))
                return end < 0 or _only_close_left(s[end + 2:])
        if s.startswith("*/"):
            return _only_close_left(s[2:])
        return s.startswith("//") or s == "*" or s.startswith("* ")
    if _HASH_COMMENTS.search(path):
        return s.startswith("#") and not s.startswith("#!")
    if _DASH_COMMENTS.search(path):
        return s.startswith("--")
    return False


def _comment_flags(path: str, texts: list[str]) -> list[bool]:
    """_comment_only for each of a hunk's added lines, in order, carrying a
    block comment that one added line opens (and doesn't close) over the
    added lines after it, so its middle and closing lines count too."""
    flags, open_block = [], False
    for t in texts:
        s = t.strip()
        if open_block:
            end = s.find("*/")
            flags.append(end < 0 or _only_close_left(s[end + 2:]))
            open_block = end < 0
            continue
        flags.append(_comment_only(path, t))
        if _SLASH_COMMENTS.search(path) and flags[-1]:
            opener = next((o for o in ("{/*", "/*") if s.startswith(o)), None)
            open_block = bool(opener) and s.find("*/", len(opener)) < 0
    return flags


def changed_lines(repo_path: str, base: str, head: str) -> dict[str, set[int]]:
    """Head-side lines the diff adds or modifies, per path. An added line that
    only re-spaces a line its hunk removes (the same text once whitespace
    between tokens is collapsed, as when gofmt re-aligns a struct after a
    field is deleted) is not a change, and neither is an added line that holds
    only a comment: a finding anchored only on one cites no line the change
    actually alters."""
    out: dict[str, set[int]] = {}
    cur, nxt, removed, added = None, 0, Counter(), []

    def close_hunk():
        comment = _comment_flags(cur, [text for _, text in added])
        for (ln, text), is_comment in zip(added, comment):
            if removed[_respaced(text)]:
                removed[_respaced(text)] -= 1
            elif not is_comment:
                out.setdefault(cur, set()).add(ln)
        removed.clear()
        added.clear()

    diff = subprocess.run(["git", "-C", str(repo_path), "diff", "-U0", f"{base}...{head}"],
                          capture_output=True, text=True, errors="replace").stdout
    in_header = False
    for line in diff.splitlines():
        if line.startswith("diff --git ") or line.startswith("@@"):
            if cur:
                close_hunk()
            removed.clear()
            added.clear()
            in_header = line.startswith("diff --git ")
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            if m:
                nxt = int(m.group(1))
        elif in_header:
            if line.startswith("+++ "):
                cur = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("-"):
            removed[_respaced(line[1:])] += 1
        elif line.startswith("+") and cur:
            added.append((nxt, line[1:]))
            nxt += 1
    if cur:
        close_hunk()
    return out


def verify(repo_path: str, head: str, finding: dict, files: dict, changed: dict[str, set[int]]) -> str | None:
    """None when `finding` checks out at `head`, else why not. `files` caches
    path -> lines (None when absent); `changed` is changed_lines()."""
    nf = finding.get("new_failure")
    if finding.get("preserves_behavior") is not False and not (
            isinstance(nf, dict) and all(str(nf.get(k) or "").strip() for k in ("case", "main", "head"))):
        return ("a behavior-preserving change with no new failure named (case, main, head)")
    if finding.get("kind") not in KINDS:
        return f"kind {finding.get('kind')!r} is not one of the risk search's kinds"
    chain = finding.get("chain") or []
    for c in chain:
        path, line = c.get("path") or "", c.get("line")
        if path not in files:
            p = subprocess.run(["git", "-C", str(repo_path), "show", f"{head}:{path}"],
                               capture_output=True, text=True, errors="replace")
            files[path] = p.stdout.splitlines() if p.returncode == 0 else None
        L = files[path]
        if L is None:
            return f"{path} does not exist at head"
        if not isinstance(line, int) or not 0 < line <= len(L):
            return f"{path}:{line} is not a line at head"
        got, want = _norm(L[line - 1]), _norm(c.get("text"))
        if not want or (want not in got and got not in want):
            return f"{path}:{line} reads {got[:80]!r}, not {want[:80]!r}"
    ch = [c for c in chain if c.get("role") == "changed"]
    if not ch:
        return "no changed line in the chain"
    if not any(c["line"] in changed.get(c["path"], set()) and not NOT_SHIPPING.search(c["path"]) for c in ch):
        return "no `changed` link is a line the diff adds or modifies in shipping code"
    en = [c for c in chain if c.get("role") == "entry"]
    if not en or all(NOT_SHIPPING.search(c["path"]) for c in en):
        return "no entry point outside tests, stories and docs"
    return None


def answer(verified: list[dict], dropped: list[dict]) -> dict:
    """P30 from the checked findings: YES when any verified, else NO."""
    if verified:
        f = verified[0]
        cites = [{"path": c["path"], "line": c["line"], "why": c.get("role", "")} for c in f.get("chain") or []]
        more = f" (and {len(verified) - 1} more)" if len(verified) > 1 else ""
        return {"value": True, "basis": "risk-search", "citations": cites,
                "evidence": f"{f.get('why') or f['kind']}{more} Customers reach it: "
                            f"{f.get('customer_facing_because') or 'see the entry point cited'}.",
                "findings": verified}
    return {"value": False, "basis": "risk-search", "citations": [],
            "evidence": "The risk search found no concrete risk on a path customers already use"
                        + (f" ({len(dropped)} claim(s) failed the line check)" if dropped else "") + "."}


def pending() -> dict:
    """P30 before the risk search ran: should-i-flag refuses to decide until it has."""
    return {"value": False, "basis": "risk-search", "citations": [], "pending": True,
            "evidence": "answered by the risk search (SKILL.md step 2), not yet recorded"}
