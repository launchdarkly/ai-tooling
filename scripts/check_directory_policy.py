#!/usr/bin/env python3
"""Pre-submission checks for the Claude plugin directory that
`claude plugin validate . --profile directory --strict` does not cover.

Checklist: https://claude.com/docs/plugins/pre-submission-checklist.md

Output is one line per finding, `BLOCKS:` (exit 1) or `HELD:` (warning, exit 0),
then a one-line summary. Only committed files are read (`git ls-files`).
"""
import json
import os
import re
import shlex
import subprocess
import sys

CHECKLIST = "https://claude.com/docs/plugins/pre-submission-checklist.md"
MAX_NON_IMAGE_BYTES = 256 * 1024
MAX_FILES = 512
LOCKFILES = ("package-lock.json", "npm-shrinkwrap.json", "bun.lock", "bun.lockb")
IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
FONT_EXTS = {".woff", ".woff2", ".ttf", ".otf"}

# --- launchers -------------------------------------------------------------

NPM_PINNED = re.compile(r"^(?:@[^/@\s]+/)?[^@/\s]+@\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?$")
PY_PINNED = re.compile(r"^[A-Za-z0-9._\[\],-]+(?:==|@)\d+(?:\.\d+)*[0-9A-Za-z.+-]*$")
SEPARATORS = {"&&", "||", ";", "|", "&"}


def _is_local(spec):
    return spec.startswith((".", "/", "~", "${"))


def _package_args(tokens, value_flags):  # value_flags: flags whose value is a package
    """Return the packages a launcher invocation names (first positional plus
    any flag-supplied package)."""
    pkgs, positional_seen, i = [], False, 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in SEPARATORS:
            break
        if tok in value_flags and i + 1 < len(tokens):
            pkgs.append(tokens[i + 1])
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        if not positional_seen:
            positional_seen = True
            # `--from X tool`: X is the package, the positional is the tool.
            if not pkgs:
                pkgs.append(tok)
        break
    return pkgs


def launcher_findings(command_tokens):
    """Yield (launcher, spec, reason) for every unpinned launcher in a token list."""
    toks = command_tokens
    for i, tok in enumerate(toks):
        base = os.path.basename(tok)
        rest = toks[i + 1:]
        if base in ("npx", "bunx"):
            for spec in _package_args(rest, {"-p": 1, "--package": 1}):
                if not _is_local(spec) and not NPM_PINNED.match(spec):
                    yield base, spec, "needs an exact version such as pkg@1.2.3"
        elif base == "uvx":
            for spec in _package_args(rest, {"--from": 1, "--with": 1}):
                if not _is_local(spec) and not PY_PINNED.match(spec):
                    yield base, spec, "needs an exact version such as pkg==1.2.3"
        elif base in ("pnpm", "yarn") and rest[:1] == ["dlx"]:
            for spec in _package_args(rest[1:], {"-p": 1, "--package": 1}):
                if not _is_local(spec) and not NPM_PINNED.match(spec):
                    yield f"{base} dlx", spec, "needs an exact version such as pkg@1.2.3"
        elif base == "pipx" and rest[:1] == ["run"]:
            for spec in _package_args(rest[1:], {"--spec": 1}):
                if not _is_local(spec) and not PY_PINNED.match(spec):
                    yield "pipx run", spec, "needs an exact version such as pkg==1.2.3"
        elif base == "uv" and rest[:1] == ["run"]:
            end = next((j for j, t in enumerate(rest) if t in SEPARATORS), len(rest))
            if not ({"--locked", "--frozen"} & set(rest[:end])):
                yield "uv run", "uv run", "needs --locked or --frozen"


def _tokenize(command, args):
    parts = []
    try:
        parts.extend(shlex.split(command))
    except ValueError:
        parts.extend(command.split())
    parts.extend(str(a) for a in (args or []))
    return parts


def _walk_commands(node):
    if isinstance(node, dict):
        cmd = node.get("command")
        if isinstance(cmd, str):
            yield _tokenize(cmd, node.get("args") if isinstance(node.get("args"), list) else None)
        for v in node.values():
            yield from _walk_commands(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_commands(v)


def is_launcher_config(path):
    base = os.path.basename(path)
    if base in (".mcp.json", "hooks.json"):
        return True
    parts = path.split("/")
    return base == "plugin.json" and ".claude-plugin" in parts[:-1]


def check_launchers(root, files):
    out = []
    for path in files:
        if not is_launcher_config(path):
            continue
        try:
            with open(os.path.join(root, path), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue  # malformed JSON is the CLI validator's finding
        for tokens in _walk_commands(data):
            for launcher, spec, why in launcher_findings(tokens):
                out.append(("BLOCKS", f"{path}: `{launcher} {spec}` is unpinned; {why} "
                            "(checklist: Unpinned launcher)"))
    return out


# --- files -----------------------------------------------------------------


def _read_head(path, n=8192):
    with open(path, "rb") as fh:
        return fh.read(n)


def _is_allowed_binary(path, head):
    ext = os.path.splitext(path)[1].lower()
    if ext in FONT_EXTS:
        return True
    if ext in IMAGE_EXTS:
        return True
    if head.startswith(IMAGE_MAGIC) or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
        return True
    return False


def _is_image(path, head):
    ext = os.path.splitext(path)[1].lower()
    return ext in IMAGE_EXTS or ext in FONT_EXTS or head.startswith(IMAGE_MAGIC) or (
        head[:4] == b"RIFF" and head[8:12] == b"WEBP")


def _looks_binary(head):
    if b"\x00" in head:
        return True
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as exc:
        # a multibyte character cut at the 8 KiB boundary is not binary
        return exc.start < len(head) - 4
    return False


def check_files(root, files):
    out = []
    regular = [p for p in files if os.path.isfile(os.path.join(root, p))
               and not os.path.islink(os.path.join(root, p))]
    if len(regular) > MAX_FILES:
        out.append(("HELD", f"repository: {len(regular)} files, over the {MAX_FILES}-file limit "
                    "(checklist: Keep the plugin to 512 files or fewer)"))
    for path in regular:
        full = os.path.join(root, path)
        head = _read_head(full)
        size = os.path.getsize(full)
        if _looks_binary(head) and not _is_allowed_binary(path, head):
            out.append(("HELD", f"{path}: binary file that is not text, SVG, PNG, JPEG, GIF, WebP "
                        "or a font (checklist: Include only text files, images and fonts)"))
        elif size > MAX_NON_IMAGE_BYTES and not _is_image(path, head):
            out.append(("HELD", f"{path}: {size // 1024} KiB, over the 256 KiB limit for non-image "
                        "files (checklist: Keep every file that isn't an image or font under 256 KiB)"))
    present = set(files)
    if "package.json" in present:
        for lock in LOCKFILES:
            if lock in present:
                out.append(("HELD", f"{lock}: lockfile beside package.json in the plugin root "
                            "(checklist: Dependencies install from a lockfile)"))
    return out


# --- credential guidance in SKILL.md ---------------------------------------

# Narrow on purpose: the agent-facing instruction to *find* a credential on the
# user's machine. Not SDK snippets (code fences), references/, MCP tool names
# like `get-sdk-key`, or lines that forbid the behavior.
CONFIG_PATH = re.compile(r"\.claude/config\.json", re.I)
CLAUDE_JSON = re.compile(r"~/\.claude\.json", re.I)
SECRET = re.compile(r"\b(?:api[ _-]?keys?|api[ _-]?tokens?|access[ _-]?tokens?|auth(?:entication)?[ _-]?tokens?|"
                    r"tokens?|secrets?|credentials?)\b", re.I)
ENV_SOURCE = re.compile(r"\benvironment variables?\b|\benv vars?\b|\$\{?[A-Z][A-Z0-9_]{2,}\}?|`\.env`|"
                        r"\b[A-Z][A-Z0-9]*_(?:API_)?(?:TOKEN|KEY|SECRET)\b", re.I | re.A)
AGENT_VERB = re.compile(r"\b(?:read|reads|find|finds|look(?:s)? (?:up|for|in)|fetch|retrieve|pull|detect|"
                        r"search|grab|auto-?detect)\b", re.I)
NEGATION = re.compile(r"\b(?:do not|don't|dont|never|not|without|instead of|rather than|avoid|no need)\b|n't", re.I)
ASK_USER = re.compile(r"\b(?:ask the user|user provide[sd]?|user's own|your terminal|their terminal)\b", re.I)


def _prose_lines(text):
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield lineno, line


def credential_hits(text):
    hits = []
    for lineno, line in _prose_lines(text):
        for sentence in re.split(r"(?<=[.!?:;])\s+", line):
            if NEGATION.search(sentence) or ASK_USER.search(sentence):
                continue
            if CONFIG_PATH.search(sentence) or (CLAUDE_JSON.search(sentence) and SECRET.search(sentence)):
                hits.append((lineno, "points the agent at ~/.claude config for credentials"))
                break
            if SECRET.search(sentence) and ENV_SOURCE.search(sentence) and AGENT_VERB.search(sentence):
                hits.append((lineno, "tells the agent to take a credential from the environment"))
                break
    return hits


def check_credentials(root, files):
    out = []
    for path in files:
        parts = path.split("/")
        if parts[-1] != "SKILL.md" or "references" in parts[:-1]:
            continue
        try:
            with open(os.path.join(root, path), encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, why in credential_hits(text):
            out.append(("HELD", f"{path}:{lineno}: {why} "
                        "(checklist: Uses a credential from the user's machine; ask via userConfig or the user)"))
    return out


# --- driver ----------------------------------------------------------------


def list_files(root):
    if os.path.isdir(os.path.join(root, ".git")):
        res = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True)
        return sorted(p for p in res.stdout.decode("utf-8").split("\0") if p)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            found.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return sorted(found)


def run(root):
    files = list_files(root)
    findings = check_launchers(root, files) + check_files(root, files) + check_credentials(root, files)
    return findings


def main(argv):
    root = os.path.abspath(argv[1]) if len(argv) > 1 else os.path.abspath(
        os.path.join(os.path.dirname(__file__), ".."))
    findings = run(root)
    for level, msg in findings:
        print(f"{level}: {msg}")
    blocks = sum(1 for lvl, _ in findings if lvl == "BLOCKS")
    held = len(findings) - blocks
    print(f"{blocks} BLOCKS, {held} HELD ({CHECKLIST})")
    return 1 if blocks else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
