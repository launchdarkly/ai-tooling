#!/usr/bin/env python3
"""Check the repo against findings the Claude plugin directory has held us on.

The directory scans the whole repository (the marketplace entry's source is
"."), so rules that match text run over every tracked file, not only the
skills the plugin ships. Each rule names the directory finding it guards.

    python3 scripts/check_directory_policy.py

Exits 1 and prints one line per violation when any rule fails.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

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
UNINSPECTABLE_ALLOWED: dict[str, str] = {}

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


def main() -> int:
    violations = check()
    for v in violations:
        print(v)
    if violations:
        print(f"\n{len(violations)} directory policy violation(s).", file=sys.stderr)
        return 1
    print("No directory policy violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
