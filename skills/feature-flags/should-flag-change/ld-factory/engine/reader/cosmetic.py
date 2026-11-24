"""Does a change only touch comments, blank lines, indentation or spacing?

P2 asks whether the change alters what the product does. For a file whose
code is unchanged once comments and layout are set aside, the answer is
mechanically no. `cosmetic(old, new, path)` says whether one file's change is
of that kind; it errs toward "not cosmetic" (the question is then asked as
usual):

- Only Go, JavaScript/TypeScript, CSS/SCSS and Python are read. Anything else,
  an added, deleted or renamed file, or text the tokenizer can't read with
  confidence (an unterminated string or comment, a JS template literal with
  nested code), is not cosmetic.
- Strings are kept exactly, whitespace and all.
- Line structure is kept: a line wrapped differently is a change (newlines can
  end statements in Go and JavaScript). What may differ is a line's leading
  and trailing whitespace, the spacing between tokens on a line, blank lines,
  and comments.
- Python keeps its indentation, which is code there.
- Comments that act as code count as code: Go build constraints and
  `//go:`/`//export`/`//line` directives, a cgo preamble (any file importing
  "C" is not read), webpack magic comments, JSX pragmas, `__PURE__`
  annotations, encoding lines and shebangs.
"""
from __future__ import annotations

import re

LANG = {".go": "go", ".ts": "js", ".tsx": "js", ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
        ".css": "css", ".scss": "scss", ".py": "py"}
DIRECTIVE = re.compile(r"^\s*(?://|#|/\*)?\s*(go:|\+build\b|export\b|line\b|webpack|@jsx|@vite|"
                       r"#__PURE__|__PURE__|@__PURE__|-\*-.*coding|coding[:=]|!)")
WORD = re.compile(r"[A-Za-z0-9_$]+")


class Unsure(Exception):
    pass


def lang_of(path: str) -> str | None:
    m = re.search(r"(\.[A-Za-z0-9]+)$", path)
    return LANG.get(m.group(1).lower()) if m else None


def _quote_end(text: str, i: int, q: str, multiline_ok: bool, raw: bool = False) -> int:
    """Index just past the closing quote of the string opened at text[i]."""
    j = i + 1
    while j < len(text):
        c = text[j]
        if c == "\\" and not raw:
            j += 2
            continue
        if q == "`" and c == "$" and text[j + 1:j + 2] == "{":
            raise Unsure("template literal with code inside")
        if c == q:
            return j + 1
        if c == "\n" and not multiline_ok:
            raise Unsure("unterminated string")
        j += 1
    raise Unsure("unterminated string")


def lines_of(text: str, lang: str) -> list[list[str]]:
    """The code as lines of tokens: comments dropped (unless they act as
    code), strings whole, spacing gone, blank lines gone; Python's
    indentation kept as a leading token."""
    if lang == "go" and re.search(r'^\s*import\s+(?:\(\s*)?"C"', text, re.M):
        raise Unsure("cgo")
    out: list[list[str]] = []
    cur: list[str] = []
    line_start = True
    i, n = 0, len(text)

    def end_line():
        nonlocal cur
        if cur:
            out.append(cur)
        cur = []

    while i < n:
        c = text[i]
        if c == "\n":
            end_line(); line_start = True; i += 1
            continue
        if c in " \t\r\f\v":
            if lang == "py" and line_start:
                j = i
                while j < n and text[j] in " \t":
                    j += 1
                if j < n and text[j] not in "\n#":
                    cur.append("<indent:%s>" % text[i:j].replace("\t", "        "))
                i = j
                continue
            i += 1
            continue
        line_start = False
        two = text[i:i + 2]
        # comments
        if (lang in ("go", "js", "scss") and two == "//") or (lang == "py" and c == "#"):
            j = text.find("\n", i)
            j = n if j < 0 else j
            if DIRECTIVE.match(text[i:j]):
                cur.append(text[i:j].strip())
            i = j
            continue
        if lang in ("go", "js", "css", "scss") and two == "/*":
            j = text.find("*/", i + 2)
            if j < 0:
                raise Unsure("unterminated comment")
            body = text[i:j + 2]
            if DIRECTIVE.match(body[2:].lstrip()) or "__PURE__" in body or "webpack" in body:
                cur.append(re.sub(r"\s+", " ", body))
            i = j + 2
            continue
        # strings
        if c in "\"'" or (c == "`" and lang in ("go", "js")):
            if lang == "py" and text[i:i + 3] in ('"""', "'''"):
                j = text.find(text[i:i + 3], i + 3)
                if j < 0:
                    raise Unsure("unterminated string")
                cur.append(text[i:j + 3]); i = j + 3
                continue
            j = _quote_end(text, i, c, multiline_ok=(c == "`"), raw=(c == "`" and lang == "go"))
            cur.append(text[i:j]); i = j
            continue
        if lang == "js" and c == "/" and two not in ("//", "/*"):
            # a regex literal and a division look alike; a slash after a value
            # is a division, anything else we can't read reliably
            if not cur or not (WORD.fullmatch(cur[-1]) or cur[-1] in (")", "]")):
                raise Unsure("possible regex literal")
        m = WORD.match(text, i)
        if m:
            cur.append(m.group(0)); i = m.end()
            continue
        j = i
        while j < n and not text[j].isspace() and not WORD.match(text, j) and text[j] not in "\"'`" \
                and text[j:j + 2] not in ("//", "/*") and not (lang == "py" and text[j] == "#"):
            j += 1
        cur.append(text[i:j] or text[i]); i = max(j, i + 1)
    end_line()
    return out


def cosmetic(old: str | None, new: str | None, path: str) -> tuple[bool, str]:
    """(only comments or layout changed, why not when it isn't)."""
    lang = lang_of(path)
    if not lang:
        return False, "not a language this check reads"
    if old is None or new is None:
        return False, "added or deleted"
    if old == new:
        return False, "unchanged content (a mode change or rename)"
    try:
        same = lines_of(old, lang) == lines_of(new, lang)
    except Unsure as e:
        return False, f"can't read it reliably ({e})"
    return same, "" if same else "code changed"
