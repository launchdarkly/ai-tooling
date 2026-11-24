"""The feature flag search: check an agent's claimed release flag for the
feature a change belongs to, and make the ones that hold reuse candidates.

Reuse candidates come mechanically from flags evaluated within
PROXIMITY_LINES of a changed hunk (P9). The flag that releases the feature a
change belongs to is often evaluated somewhere else -- the route, page,
layout or registration the feature is reached through -- so the reuse
questions see no candidate, or the wrong one, and the team's rules for a
change inside a still-rolling-out feature (cover it, or reuse that flag) never
apply. The skill's feature flag search (SKILL.md, FEATURES.md) asks the agent
for that flag once the walk reaches the reuse questions with no candidate
covering the change, as quoted lines at head:

  - the flag's key;
  - a chain from the flag's evaluation, through the line its value decides,
    to the feature's own entry (a route, page, registration, handler, or the
    feature's own module);
  - a link from that entry to the changed code: the changed file is rendered,
    called or registered under the entry, or is part of the entry's own module.

`verify` checks every quote and the shape; only a claim that holds becomes a
candidate (`candidate`), and mechanical.feature_candidate_answers adds it to
P9/P11's answers, its LaunchDarkly state read like any candidate's. P10 and
P12 see its lines in their question (ask.feature_search_context) and may cite
them. Nothing unverified reaches a question.

Whether the entry is the feature's own -- not the door to a whole product
area, which the team's policy never reuses -- is the agent's to report
honestly (FEATURES.md) and P10's to judge; the verifier can only check that
the lines are real and connected.
"""
from __future__ import annotations

import os
import subprocess

from .gate_search import _check_ref, _norm, key_at, not_shipping_fn

ENTRY_KINDS = ("route", "page", "registration", "handler", "module")
CHAIN_ROLES = {"evaluates", "decides", "passes", "entry"}
LINK_ROLES = {"renders", "calls", "registers", "imports", "passes", "module", "changed"}
MODULE_INDEX = ("index", "main", "mod", "__init__", "module")  # a folder's own entry file
MAX_FEATURES = 3  # a change belongs to one feature; a few claims leave room for a dropped one


def verify(repo_path: str, head: str, base: str, claim: dict, files: dict,
           changed_paths: set[str], keys_added=(), not_shipping=None) -> str | None:
    """None when a feature claim checks out, else why not.

    The claim: {"key", "feature", "entry_kind", "chain": [{path, line, text,
    role}], "change_link": [{path, line, text, role}], "why"}. Checked: the
    key exists at head and at merge_base (a flag this change adds is not a
    reuse candidate); every quoted line matches head; the chain has a line
    that evaluates the flag, one where its value decides, and ends at the
    feature's entry, outside tests; the change link starts at the entry's
    file (or, for a module entry, stays in the entry's own directory: beside
    it, or below it when the entry is the folder's index) and ends in a file
    the diff changes, in shipping code."""
    not_shipping = not_shipping or not_shipping_fn()
    if not isinstance(claim, dict):
        return "not an object"
    key = _norm(claim.get("key"))
    if not key or not key_at(repo_path, head, key):
        return f"key {key!r} not found at head"
    if key in set(keys_added or ()) or not key_at(repo_path, base, key):
        return f"key {key!r} does not exist at merge_base: a flag this change adds is not a reuse candidate"
    if not _norm(claim.get("feature")):
        return "no feature named"
    kind = claim.get("entry_kind")
    if kind not in ENTRY_KINDS:
        return f"entry_kind is {kind!r}, not one of {', '.join(ENTRY_KINDS)}"
    chain = claim.get("chain")
    if not isinstance(chain, list) or not chain:
        return "no chain from the flag's evaluation to the feature's entry"
    roles = [str((c or {}).get("role")) if isinstance(c, dict) else "" for c in chain]
    bad = sorted({r for r in roles if r not in CHAIN_ROLES})
    if bad:
        return f"chain roles {bad} are not ones the feature search uses ({', '.join(sorted(CHAIN_ROLES))})"
    if "evaluates" not in roles or "decides" not in roles:
        return f"the chain needs a line that evaluates the flag and one where its value decides (has {sorted(set(roles))})"
    if roles[-1] != "entry":
        return "the chain must end at the feature's entry (its last link, role `entry`)"
    for c in chain:
        why = _check_ref(repo_path, head, c, files)
        if why:
            return f"chain: {why}"
    entry = chain[-1]
    if not_shipping(entry["path"]):
        return f"the entry {entry['path']}:{entry['line']} is in a test, story or doc file"
    link = claim.get("change_link")
    if not isinstance(link, list) or not link:
        return "no link from the feature's entry to the changed code"
    for c in link:
        if not isinstance(c, dict):
            return "a change_link line is not an object"
        if str(c.get("role")) not in LINK_ROLES:
            return (f"change_link role {c.get('role')!r} is not one the feature search uses "
                    f"({', '.join(sorted(LINK_ROLES))})")
        why = _check_ref(repo_path, head, c, files)
        if why:
            return f"change_link: {why}"
    last = link[-1]
    if last["path"] not in changed_paths:
        return f"the change link ends at {last['path']}, which the diff doesn't change"
    if not_shipping(last["path"]):
        return f"the change link ends in {last['path']}, a test, story or doc file"
    first = link[0]
    if first["path"] != entry["path"]:
        if kind != "module":
            return (f"the change link starts at {first['path']}, not at the entry's file "
                    f"{entry['path']}: it must show the entry reaching the changed code")
        # The module is the entry's own folder: a changed file beside the
        # entry, or below it when the entry is that folder's index. Never the
        # repository's root folder, and never a parent folder reached from an
        # ordinary file in it: that is a product area, not one feature.
        home = os.path.dirname(entry["path"])
        index = os.path.splitext(os.path.basename(entry["path"]))[0] in MODULE_INDEX
        inside = (lambda p: os.path.dirname(p) == home
                  or (index and p.startswith(home + "/")))  # noqa: E731
        if not home or not all(inside(c["path"]) for c in link):
            return (f"a module entry's change link must stay inside its directory "
                    f"({home or 'the repository root'}/): a changed file beside the entry, or below it "
                    f"when the entry is the folder's index")
    return None


def candidate(claim: dict, owners: dict | None = None) -> dict:
    """A verified claim as the packet keeps it (Packet.feature_candidates)."""
    pick = ("path", "line", "text", "role")
    chain = [{k: c[k] for k in pick if k in c} for c in claim["chain"]]
    return {"key": _norm(claim["key"]), "feature": _norm(claim.get("feature")),
            "entry_kind": claim["entry_kind"], "entry": chain[-1], "chain": chain,
            "change_link": [{k: c[k] for k in pick if k in c} for c in claim["change_link"]],
            "why": _norm(claim.get("why")), "owners": owners or {}}


def evaluated_at(c: dict) -> list[str]:
    """Where a candidate's flag is evaluated: its chain's `evaluates` lines."""
    return [f"{x['path']}:{x['line']}" for x in c["chain"] if x.get("role") == "evaluates"]


def owners(repo_path: str, base: str, codeowners_path: str, paths: list[str]) -> dict:
    """CODEOWNERS teams for `paths` at merge_base (P13(b) compares them with
    the changed paths'), as build_packet records each candidate's."""
    from .mechanical import _owners_for
    p = subprocess.run(["git", "-C", str(repo_path), "show", f"{base}:{codeowners_path}"],
                       capture_output=True, text=True, errors="replace")
    if p.returncode != 0:
        return {}
    rules: dict[str, list[str]] = {}
    for line in p.stdout.splitlines():
        bits = line.split("#")[0].split()
        if len(bits) >= 2:
            rules[bits[0]] = bits[1:]
    return _owners_for(rules, sorted(set(paths)))


# The reuse questions: the walk passes P9 and leaves the layer at one of these
# answered NO when no candidate covers the change.
REUSE_LAYER = ("P9", "P11", "P10", "P12")


def needed(tree: dict, answers: dict) -> bool:
    """Whether the walk on the answers so far reaches the reuse questions and
    leaves them with no candidate covering the change: some path passes P9
    and has P9, P11, P10 or P12 answered NO. A P10 or P12 still to be asked
    waits for its answer (the candidates near the change come first)."""
    import classify
    given = {p: a for p, a in answers.items() if a.get("evidence") != "not answered"}
    vals = {p: (classify.UNRESOLVED if str(a.get("value")).upper() == "UNRESOLVED" else bool(a.get("value")))
            for p, a in given.items()}
    missing = {n["predicate"] for n in tree["nodes"]} - set(given)
    for leaf in classify.explore_tree(tree, vals, missing):
        steps = leaf["steps"]
        if any(s["predicate"] == "P9" for s in steps) and any(
                s["predicate"] in REUSE_LAYER and s["answer"] == "N" for s in steps):
            return True
    return False
