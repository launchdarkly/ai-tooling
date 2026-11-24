#!/usr/bin/env python3
"""Path rules: the predicates decided from changed paths alone, no model.

    python3 risk/eval/paths.py POPULATION.jsonl [--out ANSWERS.jsonl]

Answers A1, B1, B3 and C1 outright, and B2 for migration directories. For B2
model files and B4 it gives only a hint (`hint_B2_model`, `hint_B4`) that a
reader confirms. A PR with more than 100 changed files is marked
`files_truncated` by collect.py, and its path answers are left unresolved
(None) rather than guessed from a partial list.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

A1 = re.compile(r"(^|/)(APPROVAL_POLICY\.md|CODEOWNERS)$|(^|/)\.cursor/BUGBOT\.md$"
                r"|(^|/)\.cursor/(automations|approval-policies|rules)/"
                r"|(^|/)(rulesets?|branch[-_]protection)[^/]*\.(json|ya?ml|tf)$")
B1 = re.compile(r"^\.github/(workflows|actions)/|^\.circleci/|^\.buildkite/")
B2_MIGRATION = re.compile(r"(^|/)migrations?/.*\.(sql|go|py)$|(^|/)clickhouse/migrations/|(^|/)_max$")
B2_MODEL = re.compile(r"^backend/model/[^/]+\.go$")
B3 = re.compile(r"(^|/)Dockerfile[^/]*$|(^|/)(helm|charts?/[^/]+/templates|k8s|kubernetes|terraform|cdk|cloudformation)/"
                r"|\.tf$|(^|/)deploy/.*\.(ya?ml|json|tf|toml|env)$|(^|/)ecs[^/]*\.json$|(^|/)serverless\.ya?ml$"
                r"|(^|/)docker-compose[^/]*\.ya?ml$|^dev-stack/.*\.(ya?ml|json|toml|env)$"
                r"|(^|/)dinghy(gen)?/|(^|/)dinghyfile$")
# editor and personal environment config; compose and dev-stack are B3 since v0.3
LOCAL_ONLY = re.compile(r"(^|/)\.devcontainer/|^\.cursor/environments/")
B4_HINT = re.compile(r"(^|/)(middleware|auth|authn|authz|authorization|authentication|rbac|permissions?|crypto|oauth|saml|sso|tokens?)(/|[._-])", re.I)
NO_SHIP = re.compile(
    r"(_test\.go|\.test\.[jt]sx?|\.spec\.[jt]sx?|\.stories\.[jt]sx?|_test\.py)$|(^|/)(__tests__|__mocks__|testdata|fixtures|mocks|e2e|test|tests)/"
    r"|\.md$|(^|/)docs?/"
    r"|^\.(vscode|idea)/|^\.github/(?!workflows|actions)|(^|/)\.(eslintrc|prettierrc|dependency-cruiser)[^/]*$"
    r"|\.(?i:figma)\.[jt]sx?$")
# prose the running system reads ships even though it is markdown
RUNTIME_PROSE = re.compile(r"(^|/)(prompts?|skills?)/|SKILL\.md$|(^|/)vega-plugin/")
# the repository's own coding-agent config is developer tooling, never deployed; a skill a
# deployed agent loads lives elsewhere (termag's deploy/claude-skills/). A1 still sees .cursor/rules.
AGENT_CONFIG = re.compile(r"^\.(claude|cursor|agents|codex|gemini)/")
# a lockfile ships: it pins what the build installs, so a lockfile-only bump changes the artifact
BUMP_ONLY = re.compile(r"(^|/)(package\.json|go\.mod|requirements[^/]*\.txt|pyproject\.toml"
                       r"|yarn\.lock|package-lock\.json|pnpm-lock\.yaml|go\.sum)$")


def any_match(rx, paths):
    return [p for p in paths if rx.search(p)]


def answer(row):
    paths = row["files"]
    t = row.get("files_truncated")
    a1 = any_match(A1, paths)
    b1 = any_match(B1, paths)
    b2 = [p for p in any_match(B2_MIGRATION, paths) if not NO_SHIP.search(p)]
    b2m = any_match(B2_MODEL, paths)
    b3 = [p for p in any_match(B3, paths) if not LOCAL_ONLY.search(p) and not NO_SHIP.search(p)]
    ships = [p for p in paths if (not NO_SHIP.search(p) or RUNTIME_PROSE.search(p)) and not AGENT_CONFIG.search(p)]
    b4 = [p for p in ships if B4_HINT.search(p)]

    def fact(hits):
        # a hit is conclusive even on a partial list; absence is not
        return True if hits else (None if t else False)

    return {
        "id": row["id"],
        "A1": fact(a1), "A1_paths": a1,
        "B1": fact(b1), "B1_paths": b1,
        "B2": True if b2 else None if (t or b2m) else False, "B2_paths": b2,
        "hint_B2_model": b2m,
        "B3": fact(b3), "B3_paths": b3,
        "hint_B4": b4,
        "C1": True if ships else (None if t else False),
        "deps_only": bool(ships) and all(BUMP_ONLY.search(p) for p in ships),
        "shipping_paths": len(ships),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("population")
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.population)]
    out = open(a.out, "w") if a.out else sys.stdout
    for r in rows:
        out.write(json.dumps(answer(r)) + "\n")


if __name__ == "__main__":
    main()
