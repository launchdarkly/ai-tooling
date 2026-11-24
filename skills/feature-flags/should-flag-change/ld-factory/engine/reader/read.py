#!/usr/bin/env python3
"""Which question comes next, and the manifest a run's questions are asked
from (the evidence, the automatic answers, one rendered question per open
predicate).
"""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reader import ask as askmod                                  # noqa: E402
from reader import specload                                        # noqa: E402
from reader.mechanical import UNRESOLVED, diff_wired_keys, REUSE_KEY_PREDICATES, GATE_COMBINATION_PREDICATES
from classify import explore_tree, settle                           # noqa: E402

GRAPH = Path(__file__).resolve().parent.parent


def tree_order() -> list[str]:
    t = specload.load(GRAPH / "tree.yaml")
    return [n["predicate"] for n in t["nodes"]]


def lazy_needed(tree: dict, answers: dict) -> str | None:
    """Next predicate the tree actually needs, or None if it can decide.

    Past an UNRESOLVED answer the walk takes both branches (classify's
    explore_tree), so a predicate on either branch is asked -- but only while
    the branches could still agree: once two finished branches differ, the PR
    escalates whatever else is asked. With nothing unresolved there is one
    path, and this is the old one-path walk. So it costs extra reads only on
    PRs that would otherwise escalate."""
    vals = {p: (UNRESOLVED if a["value"] == UNRESOLVED else bool(a["value"]))
            for p, a in answers.items()}
    missing = {n["predicate"] for n in tree["nodes"]} - set(answers)
    leaves = explore_tree(tree, vals, missing=missing)
    pending = [l["pending"] for l in leaves if l["pending"]]
    if not pending:
        return None
    done = [l for l in leaves if not l["pending"]]
    if done and settle(done) is None:
        return None
    return pending[0]


def build_manifest(pkt, answers: dict, profile: str, pr_url=None) -> dict:
    """The evidence packet plus one question per predicate the mechanical
    answers left open, for an answerer outside this process (the skills)."""
    preds = askmod.load_predicates()
    ph = askmod.packet_hash(pkt)
    todo = [p for p in tree_order() if p not in answers]
    return {
        "pr": pr_url or f"{profile}@{pkt.unit['head'][:12]}",
        "unit": pkt.unit,
        "packet_hash": ph,
        "profile": profile,
        "mechanical": answers,
        "packet": askmod.render_packet(pkt),
        "changed_files": [f["path"] for f in pkt.files],
        "instructions": askmod.SYSTEM,
        "questions": {pid: askmod.render_question(preds[pid])
                      + "".join(f"\n\n{c}" for c in (
                          askmod.caller_gate_context(pkt, preds[pid]),
                          # The feature flag search's verified candidates
                          # (P10/P12/P13) and the fact search's findings for
                          # a question asked again; None when there are none.
                          askmod.feature_search_context(pkt, preds[pid]),
                          # P11 is mechanical, so its still-withheld keys
                          # are known here; P10/P12/P13 get the rule.
                          askmod.reuse_scope_context(answers, preds[pid]),
                          askmod.fact_search_context(pkt, preds[pid]),
                          askmod.citable_note(pkt, pid)) if c)
                      + (("\n\nName the key(s) your YES rests on in "
                          "`reuse_keys`.") if pid in REUSE_KEY_PREDICATES
                         else "")
                      + (("\n\nOn a YES resting on more than one enclosing "
                          "flag, say how they combine: `gates` (\"all\" or "
                          "\"any\") or, for a mix, `gate_paths`, as the "
                          "procedure says.") if pid in GATE_COMBINATION_PREDICATES
                         else "")
                      for pid in todo},
        # predicates.yaml's closed_world_no flag (currently just P13):
        # a NO here may rest on ABSENCE of evidence rather than positive
        # evidence, so merge_inline.py needs to know which ids these are
        # to tag the answer `"basis": "closed-world"` per GOVERNANCE.md.
        "closed_world_no": [pid for pid in todo
                            if preds[pid].get("closed_world_no")],
        # P6's one-hop referenced-context files (see mechanical.py's
        # find_referenced_context) -- the local/inline answerer needs
        # these too so merge_inline.py can verify a citation into them.
        "referenced_context": pkt.referenced_context,
        # What ask.verify_citations checks a sampled answer against, so
        # merge_inline checks an inline one the same way (caller-gate
        # windows, deleted ranges, diff gate lines).
        "citation_context": askmod.citation_context(pkt),
        # What mechanical.reuse_contradiction checks P12 against, so
        # merge_inline asks P12 again on the same contradiction.
        "reuse_candidates": [c["key"] for c in pkt.candidates]
        + [c["key"] for c in getattr(pkt, "feature_candidates", None) or []
           if c["key"] not in {x["key"] for x in pkt.candidates}],
        "diff_wired_keys": diff_wired_keys(pkt),
        # The keys this diff deletes evaluations of: T-RE-2's reuse key is
        # the one a P32 YES keeps (mechanical.record_removed_key).
        "removed_flag_keys": [r["key"] for r in getattr(pkt, "removed_flags", None) or []],
        # The same flags with their evaluation counts and who each user-facing
        # production environment serves: the report's removed-flag caveat
        # (explain.removed_flag_warnings) reads them without the packet.
        "removed_flags": removed_flag_states(pkt),
    }


def removed_flag_states(pkt) -> list[dict]:
    """Each flag the diff deletes evaluations of: its counts at merge_base and
    head, and per user-facing production environment who is served its
    exposing variation (sources.serving's class; a boolean flag's true). An
    environment whose state wasn't read is `unknown`, so "not read" stays
    told apart from "doesn't apply"; a flag never read at all has none."""
    ld = getattr(pkt, "ld", None) or {}
    snaps = ld.get("removed_snapshots") or {}
    uf = list(ld.get("user_facing") or [])
    out = []
    for r in getattr(pkt, "removed_flags", None) or []:
        envs = (snaps.get(r["key"]) or {}).get("environments") or {}
        serves = {e: (envs.get(e) or {}).get("serves") or "unknown" for e in uf} if envs else {}
        out.append({"key": r["key"], "at_merge_base": r["at_merge_base"], "at_head": r["at_head"],
                    "serves": serves})
    return out


