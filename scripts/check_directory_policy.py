#!/usr/bin/env python3
"""Claude plugin directory checks that `claude plugin validate . --profile
directory --strict` does not cover. Two rule sets share this file:

1. Findings the directory has already held our versions on (symlinks, icon and
   privacy URL, unknown keys, uninspectable archives, RUNTIME_FETCH_EXEC). These
   always fail. They run over every tracked file, since the directory scans
   the repository root.
2. The rest of the pre-submission checklist, each line labelled with the result
   the checklist gives: BLOCKS fails CI; HELD and WARN are reported only.

Checklist: https://claude.com/docs/plugins/pre-submission-checklist.md

    python3 scripts/check_directory_policy.py [ROOT]

Inside a git work tree only tracked files are read (`git ls-files`), so the
result matches what the portal fetches. The plugin folder is assumed to be the
repository root.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

CHECKLIST = "https://claude.com/docs/plugins/pre-submission-checklist.md"
MAX_NON_IMAGE_BYTES = 256 * 1024
MAX_FILES = 512
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ENTRIES = 10_000
MAX_UNPACKED_BYTES = 256 * 1024 * 1024
LOCKFILES = ("package-lock.json", "npm-shrinkwrap.json", "bun.lock", "bun.lockb")
FONT_MAGIC = {".woff": (b"wOFF",), ".woff2": (b"wOF2",), ".ttf": (b"\x00\x01\x00\x00", b"true"),
              ".otf": (b"OTTO",)}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
LFS_POINTER = b"version https://git-lfs.github.com/spec/"
# Paths Claude Code loads from a plugin at the root by default.
LOADED_DEFAULTS = ("skills/", "commands/", "agents/", "hooks/", "output-styles/", ".mcp.json", ".lsp.json")
COMPONENT_KEYS = ("skills", "commands", "agents", "hooks", "mcpServers", "outputStyles", "lspServers")

# --- rules from findings the directory has held us on ----------------------

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MANIFEST = ROOT / ".claude-plugin" / "plugin.json"

# Keys Claude Code reads from plugin.json, plus the listing-only fields the
# directory reads (icon, privacyPolicyUrl). Anything else is UNKNOWN_KEY.
CLAUDE_CODE_KEYS = {
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "commands",
    "agents",
    "skills",
    "hooks",
    "mcpServers",
    "outputStyles",
    "lspServers",
}
LISTING_ONLY_KEYS = {"icon", "privacyPolicyUrl"}

# Files the directory's validator can't read inside. Each one that ships needs
# a reason here; a new one should be source the validator can read instead.
UNINSPECTABLE_SUFFIXES = {
    ".pyz", ".zip", ".whl", ".egg", ".jar", ".war", ".tar", ".gz", ".tgz",
    ".bz2", ".xz", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".bin",
    ".wasm", ".pyc", ".class",
}
UNINSPECTABLE_ALLOWED = {
    "skills/feature-flags/should-flag-change/ld-factory.pyz":
        "the skill's command line; waived for 1.0.12 as a file the validator couldn't inspect",
    "skills/feature-flags/should-auto-approve/should-auto-approve.pyz":
        "the skill's command line; waived for 1.0.12 as a file the validator couldn't inspect",
}

# RUNTIME_FETCH_EXEC: a command that downloads code and runs it straight away.
# Point the user to the tool's own install instructions instead.
FETCH_EXEC_PATTERNS = [
    # A launcher followed by a package, not prose such as "npx not available".
    (re.compile(r"\b(npx|bunx|uvx)\s+(-\S+\s+)*(?!(?:not|is|isn't|must|on|available|installed)\b)[@\w]"),
     "runs a package it downloads"),
    # An MCP server or settings entry whose command is a package launcher.
    (re.compile(r'"command"\s*:\s*"(npx|bunx|uvx|pipx)"'), "configures a command that downloads and runs a package"),
    (re.compile(r"\b(pnpm|yarn)\s+dlx\s"), "runs a package it downloads"),
    (re.compile(r"\bpipx\s+run\s"), "runs a package it downloads"),
    (re.compile(r"\bgo\s+run\s+\S+@\S+"), "runs a module it downloads"),
    (re.compile(r"\b(curl|wget)\b[^\n]*\|\s*(sudo\s+)?(ba|z)?sh\b"), "pipes a download into a shell"),
    (re.compile(r"\b(irm|iwr|Invoke-WebRequest|Invoke-RestMethod)\b[^\n]*\|\s*iex\b"), "pipes a download into PowerShell"),
    # Likely what matched two eval tests in 1.0.12: curl and a computed URL
    # on one physical line. Build such commands one line per array entry.
    (re.compile(r"\bcurl\b[^\n]*\$\{[^}]*\}"), "puts curl and a computed URL on one line"),
]
# Lockfiles list package names and URLs, not commands.
FETCH_EXEC_SKIP = re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|uv\.lock|poetry\.lock)$")


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{where}: [{self.rule}] {self.message}"


def tracked_files(root: Path) -> list[tuple[str, str]]:
    """(mode, path) for every tracked file, from git's index."""
    out = subprocess.run(
        ["git", "ls-files", "-s"], cwd=root, check=True, capture_output=True, text=True
    ).stdout
    files = []
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        files.append((meta.split()[0], path))
    return files


def shipped_dirs(manifest: dict) -> list[str]:
    return [s.removeprefix("./").rstrip("/") for s in manifest.get("skills", [])]


def check_symlinks(files: list[tuple[str, str]]) -> list[Violation]:
    """BINARIES_NOT_INSPECTED / INVENTORY_GAPS (1.0.0): the validator doesn't follow symlinks."""
    return [
        Violation("no-symlinks", path, 0, "symlink; the directory's validator doesn't follow it")
        for mode, path in files
        if mode == "120000"
    ]


def check_uninspectable(files: list[tuple[str, str]], manifest: dict) -> list[Violation]:
    """Files or downloads the validator couldn't inspect (waived for 1.0.12)."""
    dirs = shipped_dirs(manifest)
    found = []
    for _, path in files:
        if not any(path == d or path.startswith(d + "/") for d in dirs):
            continue
        if Path(path).suffix.lower() in UNINSPECTABLE_SUFFIXES and path not in UNINSPECTABLE_ALLOWED:
            found.append(Violation(
                "inspectable-files", path, 0,
                "shipped archive or binary the validator can't read; ship source, "
                "or add it to UNINSPECTABLE_ALLOWED with a reason",
            ))
    return found


def check_manifest(manifest: dict, root: Path) -> list[Violation]:
    """ICON_MISSING, PRIVACY_URL_MISSING (1.0.0) and UNKNOWN_KEY_CROSS_TOOL / UNKNOWN_KEY."""
    rel = str(CLAUDE_MANIFEST.relative_to(ROOT))
    found = []
    icon = manifest.get("icon")
    if not icon:
        found.append(Violation("listing-fields", rel, 0, "no 'icon'; the directory listing reads it (not 'logo')"))
    elif not (root / ".claude-plugin" / ".." / icon).resolve().is_file():
        found.append(Violation("listing-fields", rel, 0, f"'icon' points at {icon}, which doesn't exist"))
    url = manifest.get("privacyPolicyUrl", "")
    if not url.startswith("https://"):
        found.append(Violation("listing-fields", rel, 0, "'privacyPolicyUrl' must be an https URL"))
    for key in sorted(set(manifest) - CLAUDE_CODE_KEYS - LISTING_ONLY_KEYS):
        found.append(Violation("known-keys", rel, 0, f"'{key}' is neither a Claude Code key nor a listing field"))
    return found


def check_fetch_exec(files: list[tuple[str, str]], root: Path) -> list[Violation]:
    """RUNTIME_FETCH_EXEC (1.0.12), over every file the directory scans."""
    found = []
    for mode, path in files:
        if mode == "120000" or FETCH_EXEC_SKIP.search(path):
            continue
        if Path(path).suffix.lower() in UNINSPECTABLE_SUFFIXES:
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for pattern, why in FETCH_EXEC_PATTERNS:
                if pattern.search(line):
                    found.append(Violation(
                        "no-fetch-exec", path, n,
                        f"{why}; point to the tool's own install instructions instead",
                    ))
                    break
    return found


def check(root: Path = ROOT) -> list[Violation]:
    files = tracked_files(root)
    manifest = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return (
        check_symlinks(files)
        + check_uninspectable(files, manifest)
        + check_manifest(manifest, root)
        + check_fetch_exec(files, root)
    )


# --- helpers ---------------------------------------------------------------


def _read(root, path, n=None):
    with open(os.path.join(root, path), "rb") as fh:
        return fh.read() if n is None else fh.read(n)


def _load_json(root, path):
    try:
        return json.loads(_read(root, path).decode("utf-8"))
    except (OSError, ValueError):
        return None  # malformed JSON is the CLI validator's finding


def _manifest(root, files):
    path = ".claude-plugin/plugin.json"
    return _load_json(root, path) if path in files else None


def _norm(rel):
    rel = rel.strip()
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _manifest_paths(manifest, key):
    """Plugin-relative file or folder paths a manifest key names."""
    val = (manifest or {}).get(key)
    vals = val if isinstance(val, list) else [val]
    return [_norm(v) for v in vals if isinstance(v, str)]


# --- launchers and commands ------------------------------------------------

NPM_PINNED = re.compile(r"^(?:@[^/@\s]+/)?[^@/\s]+@\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?$")
PY_PINNED = re.compile(r"^[A-Za-z0-9._\[\],-]+(?:==|@)\d+(?:\.\d+)*[0-9A-Za-z.+-]*$")
SEPARATORS = {"&&", "||", ";", "|", "&"}
SHELLS = {"sh", "bash", "zsh", "dash", "fish", "ksh", "cmd", "cmd.exe", "powershell", "pwsh"}
INLINE_FLAGS = {
    "python": {"-c"}, "python3": {"-c"}, "node": {"-e", "--eval", "-p", "--print"},
    "deno": {"eval"}, "bun": {"-e", "--eval"}, "ruby": {"-e"}, "perl": {"-e", "-E"},
    "sh": {"-c"}, "bash": {"-c"}, "zsh": {"-c"}, "dash": {"-c"},
    "pwsh": {"-c", "-command"}, "powershell": {"-c", "-command"},
}
VAR_REF = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_.]*)")
ALLOWED_VAR = re.compile(r"^(?:CLAUDE_PLUGIN_ROOT|user_config\.[A-Za-z0-9_]+)$")
PLUGIN_ROOT_PATH = re.compile(r"^\$\{CLAUDE_PLUGIN_ROOT\}/?(.*)$")


def _is_local(spec):
    return spec.startswith((".", "/", "~", "${"))


def _package_args(tokens, replaces, adds=()):
    """Return the packages a launcher invocation names. A flag in `replaces`
    (-p/--package, --from, --spec) names the package instead of the first
    positional; a flag in `adds` (--with) names an extra one."""
    pkgs, replaced, i = [], False, 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in SEPARATORS:
            break
        flag, eq, val = tok.partition("=")
        if flag in replaces or flag in adds:
            if not eq and i + 1 < len(tokens):
                val, i = tokens[i + 1], i + 1
            if val:
                pkgs.append(val)
                replaced = replaced or flag in replaces
            i += 1
            continue
        if tok.startswith("-"):
            i += 1
            continue
        if not replaced:
            pkgs.append(tok)
        break
    return pkgs


def launcher_findings(command_tokens):
    """Yield (launcher, spec, pinned, reason) for every package launcher in a token list."""
    toks = command_tokens
    for i, tok in enumerate(toks):
        base = os.path.basename(tok)
        rest = toks[i + 1:]
        if base in ("npx", "bunx"):
            for spec in _package_args(rest, {"-p", "--package"}):
                if not _is_local(spec):
                    yield base, spec, bool(NPM_PINNED.match(spec)), "needs an exact version such as pkg@1.2.3"
        elif base == "uvx" or (base == "uv" and rest[:2] == ["tool", "run"]):
            args = rest if base == "uvx" else rest[2:]
            for spec in _package_args(args, {"--from"}, {"--with"}):
                if not _is_local(spec):
                    yield "uvx", spec, bool(PY_PINNED.match(spec)), "needs an exact version such as pkg==1.2.3"
        elif base in ("pnpm", "yarn") and rest[:1] == ["dlx"]:
            for spec in _package_args(rest[1:], {"-p", "--package"}):
                if not _is_local(spec):
                    yield f"{base} dlx", spec, bool(NPM_PINNED.match(spec)), \
                        "needs an exact version such as pkg@1.2.3"
        elif base == "pipx" and rest[:1] == ["run"]:
            for spec in _package_args(rest[1:], {"--spec"}):
                if not _is_local(spec):
                    yield "pipx run", spec, bool(PY_PINNED.match(spec)), "needs an exact version such as pkg==1.2.3"
        elif base == "uv" and rest[:1] == ["run"]:
            end = next((j for j, t in enumerate(rest) if t in SEPARATORS), len(rest))
            locked = bool({"--locked", "--frozen"} & set(rest[:end]))
            yield "uv", "run", locked, "needs --locked or --frozen"


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


def launcher_configs(files, manifest):
    """Files whose `command` entries Claude Code runs: .mcp.json and hooks.json
    anywhere, the manifest, and files the manifest's mcpServers/hooks name."""
    named = set(_manifest_paths(manifest, "mcpServers") + _manifest_paths(manifest, "hooks"))
    out = []
    for path in files:
        base = os.path.basename(path)
        if base in (".mcp.json", "hooks.json") or path in named or path == ".claude-plugin/plugin.json":
            out.append(path)
    return out


def _mcp_servers(data, top_level_ok):
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if servers is None and isinstance(data, dict) and top_level_ok:
        servers = data  # .mcp.json may list servers at the top level
    return {k: v for k, v in servers.items() if isinstance(v, dict)} if isinstance(servers, dict) else {}


def _hook_entries(data):
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return
    for event, groups in hooks.items():
        for group in groups if isinstance(groups, list) else []:
            for hook in (group.get("hooks") if isinstance(group, dict) else None) or []:
                if isinstance(hook, dict):
                    yield event, hook


def _env_refs(value):
    if isinstance(value, dict):
        return [r for v in value.values() for r in _env_refs(v)]
    if isinstance(value, str):
        return [m for m in VAR_REF.findall(value) if not ALLOWED_VAR.match(m)]
    return []


def command_findings(where, tokens, kind):
    """Findings for one hook or MCP server command. kind is 'hook' or 'mcp'."""
    out = []
    if not tokens:
        return out
    for tok in tokens:
        if ".." in re.split(r"[/\\]", tok):
            out.append(("BLOCKS", f"{where}: `{tok}` climbs out of the plugin folder with `..` "
                        "(checklist: Command reaches above the plugin folder)"))
        bad = [m for m in VAR_REF.findall(tok) if not ALLOWED_VAR.match(m)]
        if bad:
            out.append(("BLOCKS", f"{where}: `{tok}` uses ${bad[0]}; write paths from ${{CLAUDE_PLUGIN_ROOT}} only "
                        "(checklist: Command path can't be followed)"))
        if "$(" in tok or "`" in tok:
            out.append(("BLOCKS", f"{where}: `{tok}` uses command substitution "
                        "(checklist: Command path can't be followed)"))
        if "://" not in tok and any(c in tok for c in "*?"):
            out.append(("BLOCKS", f"{where}: `{tok}` uses a wildcard (checklist: Command path can't be followed)"))
    for i, tok in enumerate(tokens[:-1]):
        flags = INLINE_FLAGS.get(os.path.basename(tok).lower())
        if flags and tokens[i + 1].lower() in flags:
            out.append(("BLOCKS", f"{where}: `{tok} {tokens[i + 1]}` runs an inline program "
                        "(checklist: Command path can't be followed)"))
    base = os.path.basename(tokens[0]).lower()
    if kind == "mcp" and (base in SHELLS or (base in ("npm", "pnpm", "yarn", "bun")
                                              and tokens[1:2] in (["run"], ["start"], ["exec"]))):
        out.append(("HELD", f"{where}: starts through `{' '.join(tokens[:2])}`; run a plugin file directly "
                    "(checklist: MCP server command wasn't read)"))
    for tok in tokens:
        m = PLUGIN_ROOT_PATH.match(tok)
        if m and not re.search(r"\.(?:sh|bash)$", m.group(1)):
            out.append(("HELD", f"{where}: runs `{tok}`, which the validator does not read through "
                        "(checklist: Scripts the validator couldn't follow)"))
        if tok.lower().endswith((".mcpb", ".dxt")):
            out.append(("HELD", f"{where}: runs bundle `{tok}`; declare command and args instead "
                        "(checklist: Bundled MCP server not inspected)"))
    return out


def check_commands(root, files, manifest):
    out, launchers = [], []
    for path in launcher_configs(files, manifest):
        data = _load_json(root, path)
        if data is None:
            continue
        for tokens in _walk_commands(data):
            for launcher, spec, pinned, why in launcher_findings(tokens):
                launchers.append(path)
                if pinned:
                    out.append(("HELD", f"{path}: `{launcher} {spec}` resolves its dependencies at install time "
                                "(checklist: Runs a pinned launcher package)"))
                else:
                    out.append(("BLOCKS", f"{path}: `{launcher} {spec}` is unpinned; {why} "
                                "(checklist: Unpinned launcher)"))
        is_manifest = path == ".claude-plugin/plugin.json"
        top_level_ok = os.path.basename(path) == ".mcp.json" or path in _manifest_paths(manifest, "mcpServers")
        for name, cfg in _mcp_servers(data, top_level_ok).items():
            where = f"{path}: MCP server {name}"
            url = cfg.get("url")
            if isinstance(url, str) and url.lower().split("?")[0].endswith((".mcpb", ".dxt")):
                out.append(("BLOCKS", f"{where}: fetches bundle {url} (checklist: Bundled MCP server not inspected)"))
            refs = _env_refs(cfg.get("headers")) + _env_refs(cfg.get("env"))
            if refs:
                out.append(("HELD", f"{where}: sends ${refs[0]} from the user's environment; ask via userConfig "
                            "(checklist: Uses a credential from the user's machine)"))
            if isinstance(cfg.get("command"), str):
                args = cfg.get("args") if isinstance(cfg.get("args"), list) else None
                out += command_findings(where, _tokenize(cfg["command"], args), "mcp")
        hooks_data = data if not is_manifest else ({"hooks": data["hooks"]} if isinstance(data.get("hooks"), dict)
                                                    else None)
        for event, hook in _hook_entries(hooks_data):
            where = f"{path}: {event} hook"
            if hook.get("type") == "http":
                url = hook.get("url")
                if not (isinstance(url, str) and url.startswith("https://")):
                    out.append(("BLOCKS", f"{where}: HTTP hook URL {url!r} is not https:// "
                                "(checklist: hooks.json is invalid)"))
                if _env_refs(hook.get("headers")):
                    out.append(("BLOCKS", f"{where}: HTTP hook sends a credential from the user's environment "
                                "(checklist: Uses a credential from the user's machine)"))
            if isinstance(hook.get("command"), str):
                out += command_findings(where, _tokenize(hook["command"], None), "hook")
    return out, launchers


SOURCE_CONFIGS = {".npmrc", ".yarnrc", ".yarnrc.yml", "bunfig.toml", "uv.toml", "pip.conf", "pip.ini"}
SOURCE_SETTING = re.compile(r"registry|index|proxy|mirror|find-links|source", re.I)


def check_package_sources(root, files, launchers):
    out = []
    install = "package.json" in files
    if not launchers and not install:
        return out
    for path in files:
        if os.path.basename(path) not in SOURCE_CONFIGS:
            continue
        try:
            text = _read(root, path).decode("utf-8", "replace")
        except OSError:
            continue
        if not SOURCE_SETTING.search(text):
            continue
        level, ctx = ("BLOCKS", "a package launcher") if launchers else ("HELD", "a package install")
        out.append((level, f"{path}: sets a package source in a plugin with {ctx} "
                    "(checklist: Install may use a custom registry or package source)"))
    return out


# --- repository layout -----------------------------------------------------

WINDOWS_DEVICES = {"con", "prn", "aux", "nul"} | {f"{p}{n}" for p in ("com", "lpt") for n in range(1, 10)}
WINDOWS_BAD = re.compile(r'[<>:"|?*\\\x00-\x1f]')


def check_names(files):
    out, seen = [], {}
    entries = set(files)
    for path in files:
        parts = path.split("/")
        entries.update("/".join(parts[:i]) for i in range(1, len(parts)))
    for entry in sorted(entries):
        name = entry.rsplit("/", 1)[-1]
        if WINDOWS_BAD.search(name) or name.endswith((".", " ")) or name.split(".")[0].lower() in WINDOWS_DEVICES:
            out.append(("BLOCKS", f"{entry!r}: name is not valid on Windows "
                        "(checklist: Couldn't validate that repository)"))
        other = seen.setdefault(entry.lower(), entry)
        if other != entry:
            out.append(("BLOCKS", f"{entry!r} and {other!r} differ only by capitalization "
                        "(checklist: Couldn't validate that repository)"))
    for path in files:
        parts = path.split("/")
        for i, part in enumerate(parts):
            for want in ("SKILL.md", "skills", "hooks", "commands", "agents"):
                if part != want and part.lower() == want.lower() and (want == "SKILL.md" or i == 0):
                    out.append(("BLOCKS", f"{path}: `{part}` must be spelled `{want}` "
                                "(checklist: Name component folders and files exactly)"))
    return out


GITATTR_BAD = re.compile(r"(?:^|\s)(export-ignore|export-subst|filter=\S+|filter\b(?!=)|ident\b|"
                         r"working-tree-encoding=\S+)")


def check_gitattributes(root, files):
    out = []
    for path in files:
        if os.path.basename(path) != ".gitattributes":
            continue
        try:
            lines = _read(root, path).decode("utf-8", "replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            line = line.split("#", 1)[0] if line.lstrip().startswith("#") else line
            m = GITATTR_BAD.search(line)
            if m:
                out.append(("BLOCKS", f"{path}:{lineno}: `{m.group(1)}` changes what git archives "
                            "(checklist: Couldn't validate that repository)"))
    return out


def _loaded(path, manifest):
    prefixes = list(LOADED_DEFAULTS)
    for key in COMPONENT_KEYS:
        prefixes += _manifest_paths(manifest, key)
    return any(p and (path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/")) for p in prefixes)


def check_special_entries(root, files, modes, manifest):
    """Submodules, symlinks and Git LFS pointer files."""
    out = []
    for path in files:
        mode = modes.get(path, "")
        kind = None
        if mode == "160000":
            kind = "Git submodule"
        elif not modes and os.path.islink(os.path.join(root, path)):  # git: see check_symlinks
            kind = "symbolic link"
        elif os.path.isfile(os.path.join(root, path)):
            try:
                if _read(root, path, len(LFS_POINTER)) == LFS_POINTER:
                    kind = "Git LFS pointer file"
            except OSError:
                pass
        if kind:
            level = "BLOCKS" if _loaded(path, manifest) else "WARN"
            out.append((level, f"{path}: {kind}; commit the regular file "
                        "(checklist: Commit regular files, not symbolic links, submodules, or LFS pointers)"))
    return out


# --- files -----------------------------------------------------------------


def _complete_image(ext, data):
    if ext == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n") and data.endswith(b"IEND\xaeB`\x82")
    if ext in (".jpg", ".jpeg"):
        return data.startswith(b"\xff\xd8\xff") and data.rstrip(b"\x00").endswith(b"\xff\xd9")
    if ext == ".gif":
        return data[:6] in (b"GIF87a", b"GIF89a") and data.endswith(b";")
    if ext == ".webp":
        return (data[:4] == b"RIFF" and data[8:12] == b"WEBP"
                and int.from_bytes(data[4:8], "little") + 8 == len(data))
    return False


def allowed_media(path, root):
    """True for a complete PNG/JPEG/GIF/WebP or a font whose bytes match its extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in FONT_MAGIC:
        return _read(root, path, 4) in FONT_MAGIC[ext]
    if ext in IMAGE_EXTS:
        return _complete_image(ext, _read(root, path))
    return False


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
    dirs = {"/".join(p.split("/")[:i]) for p in files for i in range(1, p.count("/") + 1)}
    if len(files) + len(dirs) >= MAX_ENTRIES:
        out.append(("BLOCKS", f"repository: {len(files) + len(dirs)} files and folders, at or over {MAX_ENTRIES} "
                    "(checklist: Repository too large to validate)"))
    total = sum(os.path.getsize(os.path.join(root, p)) for p in regular)
    if total > MAX_UNPACKED_BYTES:
        out.append(("BLOCKS", f"repository: {total // (1024 * 1024)} MiB unpacked, over 256 MiB "
                    "(checklist: Repository too large to validate)"))
    if len(regular) > MAX_FILES:
        out.append(("HELD", f"repository: {len(regular)} files, over the {MAX_FILES}-file limit "
                    "(checklist: Keep the plugin to 512 files or fewer)"))
    for path in regular:
        size = os.path.getsize(os.path.join(root, path))
        head = _read(root, path, 8192)
        if head.startswith(LFS_POINTER):
            continue  # reported by check_special_entries
        media = allowed_media(path, root)
        if size > MAX_FILE_BYTES:
            out.append(("BLOCKS", f"{path}: {size // (1024 * 1024)} MiB, over the 5 MiB limit for any file "
                        "(checklist: Repository too large to validate)"))
        elif not media and (_looks_binary(head) or os.path.splitext(path)[1].lower() in IMAGE_EXTS | set(FONT_MAGIC)):
            out.append(("HELD", f"{path}: binary file that is not text, SVG, a complete PNG, JPEG, GIF or WebP, "
                        "or a font (checklist: Include only text files, images and fonts)"))
        elif size > MAX_NON_IMAGE_BYTES and not media:
            out.append(("HELD", f"{path}: {size // 1024} KiB, over the 256 KiB limit for non-image "
                        "files (checklist: Keep every file that isn't an image or font under 256 KiB)"))
    present = set(files)
    if "package.json" in present:
        for lock in LOCKFILES:
            if lock in present:
                out.append(("HELD", f"{lock}: lockfile beside package.json in the plugin root "
                            "(checklist: Dependencies install from a lockfile)"))
    return out


# --- literal secrets -------------------------------------------------------

SECRET_PATTERNS = [
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{60,}")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[0-9A-Za-z-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Stripe live key", re.compile(r"\b[sr]k_live_[0-9A-Za-z]{16,}")),
    ("private key", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("LaunchDarkly key", re.compile(r"\b(?:api|sdk|mob)-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")),
]


def _placeholder(token):
    body = re.sub(r"^[a-z]+[-_]", "", token)
    return "EXAMPLE" in token.upper() or len(set(body.replace("-", "").lower())) < 6


def check_secrets(root, files):
    out = []
    for path in files:
        full = os.path.join(root, path)
        if not os.path.isfile(full) or os.path.islink(full) or os.path.getsize(full) > MAX_FILE_BYTES:
            continue
        data = _read(root, path)
        if _looks_binary(data[:8192]):
            continue
        for lineno, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            for label, pattern in SECRET_PATTERNS:
                m = pattern.search(line)
                if m and not _placeholder(m.group(0)):
                    out.append(("BLOCKS", f"{path}:{lineno}: looks like a real {label} ({m.group(0)[:8]}…) "
                                "(checklist: Keep real credentials out of every file)"))
                    break
    return out


# --- manifest identity -----------------------------------------------------


def _script(ch):
    try:
        return unicodedata.name(ch).split()[0]
    except ValueError:
        return "UNKNOWN"


def check_identity(manifest):
    out = []
    if not isinstance(manifest, dict):
        return out
    author = manifest.get("author")
    fields = [("displayName", manifest.get("displayName")),
              ("author.name", author.get("name") if isinstance(author, dict) else None)]
    for field, value in fields:
        if not isinstance(value, str):
            continue
        invisible = [c for c in value if unicodedata.category(c) in ("Cf", "Co", "Cn", "Cc")]
        scripts = {_script(c) for c in value if c.isalpha()}
        if invisible:
            out.append(("BLOCKS", f".claude-plugin/plugin.json: {field} contains invisible character "
                        f"U+{ord(invisible[0]):04X} (checklist: one writing system, no invisible characters)"))
        if len(scripts) > 1:
            out.append(("BLOCKS", f".claude-plugin/plugin.json: {field} {value!r} mixes writing systems "
                        f"{sorted(scripts)} (checklist: one writing system, no look-alike letters)"))
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
    """Return (paths, modes). Inside a git work tree (including a linked
    worktree, where .git is a file) list the index; otherwise walk the disk."""
    try:
        res = subprocess.run(["git", "ls-files", "-z", "--stage"], cwd=root, check=True, capture_output=True)
        inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root,
                                capture_output=True, text=True).stdout.strip() == "true"
    except (OSError, subprocess.CalledProcessError):
        inside = False
    if inside:
        modes = {}
        for rec in res.stdout.decode("utf-8", "surrogateescape").split("\0"):
            if rec:
                meta, path = rec.split("\t", 1)
                modes[path] = meta.split()[0]
        return sorted(modes), modes
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            found.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return sorted(found), {}


def run(root):
    files, modes = list_files(root)
    manifest = _manifest(root, files)
    held_on = []
    if modes and isinstance(manifest, dict):  # these rules read git's index and the manifest
        held_on = [("BLOCKS", str(v)) for v in check(Path(root))]
    commands, launchers = check_commands(root, files, manifest)
    return (held_on + commands + check_package_sources(root, files, launchers) + check_names(files)
            + check_gitattributes(root, files) + check_special_entries(root, files, modes, manifest)
            + check_files(root, files) + check_secrets(root, files) + check_identity(manifest)
            + check_credentials(root, files))


def main(argv):
    root = os.path.abspath(argv[1]) if len(argv) > 1 else os.path.abspath(
        os.path.join(os.path.dirname(__file__), ".."))
    findings = run(root)
    for level, msg in findings:
        print(f"{level}: {msg}")
    blocks = sum(1 for lvl, _ in findings if lvl == "BLOCKS")
    held = sum(1 for lvl, _ in findings if lvl == "HELD")
    warn = len(findings) - blocks - held
    print(f"{blocks} BLOCKS, {held} HELD, {warn} WARN ({CHECKLIST})")
    return 1 if blocks else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
