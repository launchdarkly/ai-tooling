#!/usr/bin/env python3
"""Which reader profile matches a repo checkout? Mechanical, not a guess.

    python3 -m reader.detect_profile <repo-path>      # prints the profile name

Reads the checkout's `origin` remote, normalises it to `org/repo`, and matches
it against the `repo:` field every `reader/profiles/*.yaml` already declares
(profiles are the one place repo identity is meant to live -- see
sources.py's `Profile`). Kept mechanical rather than left to prose so the
local skill and a future CI Action call the exact same deterministic lookup,
and so a wrong match is a fixable bug rather than a one-off misread.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

try:
    from . import specload
except ImportError:  # run as a script
    import specload


HERE = Path(__file__).parent
PROFILES = HERE / "profiles"


def normalize(remote_url: str) -> str:
    """`git@github.com:org/repo.git` / `https://github.com/org/repo(.git)` -> `org/repo`."""
    url = remote_url.strip()
    m = re.search(r"[:/]([^/:]+/[^/:]+?)(?:\.git)?/?$", url)
    if not m:
        raise ValueError(f"can't parse a org/repo out of remote {url!r}")
    return m.group(1)


def profiles() -> dict[str, str]:
    """profile name -> declared `repo:` (org/repo), skipping shared `_*.yaml` config."""
    from .sources import profile_dirs
    out = {}
    for p in [x for d in profile_dirs() for x in sorted(d.glob("*.json"))]:
        if p.stem.startswith("_"):
            continue
        doc = specload.load(p) or {}
        repo = doc.get("repo")
        if repo and p.stem not in out:
            out[p.stem] = repo
    return out


def detect(repo_path: str) -> str:
    r = subprocess.run(["git", "-C", repo_path, "remote", "get-url", "origin"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"no readable 'origin' remote at {repo_path}: "
                         f"{r.stderr.strip()}")
    org_repo = normalize(r.stdout)

    avail = profiles()
    hits = [name for name, repo in avail.items() if repo == org_repo]
    if not hits:
        raise SystemExit(
            f"no reader profile declares repo: {org_repo}\n"
            f"available profiles: "
            + ", ".join(f"{n} ({r})" for n, r in sorted(avail.items())) +
            f"\nadd <name>.json with `repo: {org_repo}` to a SHOULD_I_FLAG_PROFILES folder, or write one (references/PROFILE.md).")
    if len(hits) > 1:
        raise SystemExit(f"{org_repo} matches more than one profile: {hits} "
                         f"-- fix the duplicate `repo:` field")
    return hits[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo_path")
    args = ap.parse_args(argv)
    print(detect(args.repo_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
