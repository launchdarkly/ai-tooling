#!/usr/bin/env python3
"""Build the Claude plugin directory bundle into a clean folder.

The Claude plugin directory scans every file in the submitted plugin folder.
At the repository root that includes evals, tests, lockfiles, and scripts that
the plugin never ships, and each of them can hold a version for review. This
script copies only what the plugin loads:

- .claude-plugin/plugin.json and .claude-plugin/marketplace.json
- .mcp.json
- the skill folders listed in .claude-plugin/plugin.json
- README.md, LICENSE, and the icon named in plugin.json
- any skill folder (or file) that a shipped Markdown file links to, so
  relative links keep resolving

The release workflow publishes the result to the `claude-plugin` branch, which
the directory submission tracks.

Usage: python3 scripts/build_claude_plugin.py <output-dir>
"""

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
ROOT_FILES = (
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".mcp.json",
    "README.md",
    "LICENSE",
)
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
IGNORED = shutil.ignore_patterns(".DS_Store", "Thumbs.db", "desktop.ini", "__pycache__", "*.pyc")


def shipped_paths(manifest: dict) -> list[str]:
    paths = list(ROOT_FILES)
    if manifest.get("icon"):
        paths.append(manifest["icon"])
    for skill in manifest.get("skills", []):
        paths.append(skill.removeprefix("./"))
    return paths


def copy(rel: str, out: Path) -> None:
    src = ROOT / rel
    dst = out / rel
    if src.is_dir():
        shutil.copytree(src, dst, ignore=IGNORED, dirs_exist_ok=True)
    elif src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    else:
        raise FileNotFoundError(f"{rel} is listed for the plugin but does not exist")


def linked_paths(out: Path) -> set[str]:
    """Repo paths that shipped Markdown links to but the bundle lacks."""
    missing = set()
    for md in out.rglob("*.md"):
        for target in LINK.findall(md.read_text(encoding="utf-8")):
            if re.match(r"[a-z][a-z0-9+.-]*:", target) or target.startswith("/"):
                continue
            rel_md = md.relative_to(out)
            resolved = (ROOT / rel_md.parent / target).resolve()
            if ROOT not in resolved.parents or not resolved.exists():
                continue  # external, or already broken in the repo
            rel = resolved.relative_to(ROOT)
            if (out / rel).exists():
                continue
            # Ship the whole skill the link lands in, when there is one.
            for parent in [rel, *rel.parents]:
                if (ROOT / parent / "SKILL.md").is_file():
                    rel = parent
                    break
            missing.add(rel.as_posix())
    return missing


def build(out: Path) -> list[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    paths = shipped_paths(manifest)
    for rel in paths:
        copy(rel, out)
    while missing := linked_paths(out):
        for rel in sorted(missing):
            copy(rel, out)
            paths.append(rel)
    return paths


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    out = Path(sys.argv[1]).resolve()
    # The output folder is deleted first, so never accept the repo, an
    # ancestor of it, or a folder inside it other than dist/.
    inside_repo = out == ROOT or ROOT in out.parents
    if out in ROOT.parents or (inside_repo and ROOT / "dist" not in [out, *out.parents]):
        print(f"refusing to build into {out}: use a folder outside the repo or under dist/", file=sys.stderr)
        return 2
    for rel in build(out):
        print(rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
