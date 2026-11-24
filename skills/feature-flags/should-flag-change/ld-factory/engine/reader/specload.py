"""Read a spec or profile file: the YAML file when it exists and PyYAML is
installed, otherwise the `.json` file beside it. This skill ships JSON only,
so it runs on Python's standard library.
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    import yaml
except ImportError:  # the skill bundle
    yaml = None


def read_text(path: Path) -> str:
    """A file's text, also when the path runs through a zip archive (the
    program used to ship as one .pyz): the file is read from the archive."""
    try:
        return path.read_text()
    except (FileNotFoundError, NotADirectoryError):
        import zipfile
        for arc in path.parents:
            if arc.is_file() and zipfile.is_zipfile(arc):
                with zipfile.ZipFile(arc) as z:
                    try:
                        return z.read(path.relative_to(arc).as_posix()).decode()
                    except KeyError:
                        raise FileNotFoundError(path) from None
        raise


def load(path: Path | str):
    path = Path(path)
    if yaml is not None and path.is_file():
        return yaml.safe_load(path.read_text())
    return json.loads(read_text(path.with_suffix(".json")))


def loads(text: str):
    """Parse YAML text, or JSON text when PyYAML is missing (raises
    ValueError for YAML that isn't also JSON)."""
    if yaml is not None:
        return yaml.safe_load(text)
    return json.loads(text)


def spec_dir(default: Path) -> Path:
    """The tree in use: `default` (the folder holding predicates.yaml), or
    the one FDG_SPEC names (trees/<name>/)."""
    import os
    return Path(os.environ["FDG_SPEC"]) if os.environ.get("FDG_SPEC") else default


def gate_evidence_ids(default: Path) -> frozenset:
    """Questions of the tree in use that judge whether a flag check covers
    the change, marked `gate_evidence: true` in its predicates.yaml: they get
    the same gate evidence (callers' flag checks, referenced files) as the
    ODD tree's gate questions. Empty for the ODD tree, which names its own."""
    try:
        preds = load(spec_dir(default) / "predicates.yaml")["predicates"]
    except (OSError, ValueError, KeyError):
        return frozenset()
    return frozenset(p["id"] for p in preds if p.get("gate_evidence"))
