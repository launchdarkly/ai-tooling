#!/usr/bin/env python3
"""Merge out-of-band predicate answers into an answers.json, honestly labelled.

    python3 -m reader.merge_inline manifest.json replies.json -o answers.json

WHY THIS EXISTS
When no API key is available, the predicates can be answered by whoever is
reading -- including the assistant in-session. That is a legitimate fallback
and it produces a usable vector, but it does NOT produce the reader the design
specifies, and the difference must be visible in the ledger rather than
discovered later.

WHAT IS LOST, AND WHY IT IS RECORDED
  * SAMPLE INDEPENDENCE. The keyed reader samples each predicate 3x in
    separate requests and requires unanimity; a split becomes UNRESOLVED. One
    in-session answerer cannot produce independent samples -- it sees its own
    prior answers -- so `3x-unanimous` would be a false claim. Basis is
    recorded as `inline:1-sample:no-independence`.
  * PER-PREDICATE ISOLATION. The keyed reader gives each predicate its own
    request containing only its own question. An inline answerer holds every
    predicate in one context, so answers can bleed across predicates. That is
    the monolithic-skill failure mode the graph exists to remove.

WHAT SURVIVES
  * The MECHANICAL tier, unchanged -- git, profiles, LD state are computed, not
    judged, and carry their own basis strings.
  * The CITATION CHECK, unchanged and re-run here via `sources.verify_citations`
    -- the same function ask.py's keyed path uses. A citation must be either a
    changed file in the packet, or one of P6's referenced_context files (see
    mechanical.py); an answer whose evidence does not resolve is forced to
    UNRESOLVED. Being mechanical, it constrains an inline answerer exactly as
    much as a keyed one.
  * The GRAPH, which is indifferent to where the bits came from.

So the entry is marked `reproducible: false`. Do not compare it against a keyed
run as though the two were the same instrument.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reader.sources import verify_citations  # noqa: E402

GATE_READERS = ("P5", "P6")  # a YES on these names the gate P7/P8/P12 are about
REUSE_KEY_PREDICATES = ("P10", "P12")  # mechanical.REUSE_KEY_PREDICATES
GATE_COMBINATION_PREDICATES = ("P6",)  # mechanical.GATE_COMBINATION_PREDICATES

UNRESOLVED = "UNRESOLVED"
BASIS = "inline:1-sample:no-independence"
RECHECK_EXIT = 5  # a question must be answered again; see recheck.txt


def _ld_client(prof):
    from reader.sources import LDClient
    return LDClient(prof.ld)


# How _reread_gates reads LaunchDarkly. The should-flag-change skill replaces
# it with a reader over flag state the agent fetched (it may have no API key).
LD_FACTORY = _ld_client

# How _reread_gates gets the packet back: rebuilt from the checkout, unless the
# caller kept the one the manifest was built from (the skill does, since it
# merges after every answer). Takes the manifest; returns a packet or None.
PACKET_LOADER = None


def _profile(man: dict):
    """The manifest's profile: a bundled one by name, or the file the
    should-flag-change skill wrote for a repo no bundled profile covers."""
    from reader.sources import Profile
    if man.get("profile_file"):
        return Profile.from_file(man["profile_file"])
    return Profile.load(man["profile"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("replies")
    ap.add_argument("-o", "--out", default="answers.json")
    ap.add_argument("--repo", help="checkout the manifest was built from; with "
                    "--merged, re-reads the gate a P5/P6 YES cites, as read.py does")
    ap.add_argument("--merged", help="the --merged date or timestamp the manifest was built with")
    a = ap.parse_args(argv)

    man = json.loads(Path(a.manifest).read_text())
    rep = json.loads(Path(a.replies).read_text())
    rechecks = (rep.get("rechecks") or {}) if "answers" in rep else {}
    if "answers" in rep:
        rep = rep["answers"]

    known = set(man["changed_files"])
    referenced = man.get("referenced_context") or []
    ctx = man.get("citation_context")
    repo = None
    if ctx and a.repo:
        from reader.sources import Repo
        repo = Repo(Path(a.repo).resolve())
    closed_world_no = set(man.get("closed_world_no") or [])
    answers = dict(man["mechanical"])
    forced, missing, kept = [], [], 0

    def take(pid, r):
        """One inline answer, citation-checked the way ask.py checks a sample."""
        val = r.get("value")
        cites = r.get("citations") or []
        if ctx:
            # The keyed reader's own check (ask.check_citations), with the
            # line-exists test when the checkout is at hand.
            from reader import ask as askmod
            lines = (askmod.cited_file_lines(repo, man["unit"]["head"], cites, known)
                     if repo is not None else None)
            ok, why = askmod.check_citations(cites, ctx, lines, predicate_id=pid,
                                             value=val)
        else:  # a manifest from before citation_context existed
            ok, why = verify_citations(cites, known, referenced, predicate_id=pid)
        if not ok:
            return {"value": UNRESOLVED, "evidence": f"citation rejected: {why}",
                    "basis": BASIS, "citations": cites}, False
        value = (UNRESOLVED if val in (UNRESOLVED, "unresolved")
                 else bool(val is True or val == "yes"))
        # A NO on a closed_world_no predicate is a claim about the absence of
        # evidence, not positive evidence -- GOVERNANCE.md's contract for that
        # is the literal basis string "closed-world", which is what
        # classify.py's decide() checks for. That replaces, rather than joins,
        # the inline/no-independence provenance below: the documented contract
        # is one basis string per answer, and closed-world is the one classify.py
        # actually looks for.
        basis = ("closed-world" if pid in closed_world_no and value is False
                 else BASIS)
        out = {"value": value, "evidence": r.get("evidence", ""),
               "basis": basis, "citations": cites}
        if pid in REUSE_KEY_PREDICATES:
            # The key(s) the YES rests on (the reuse layer is about ONE key;
            # mechanical.reuse_key_violation checks them below).
            out["reuse_keys"] = sorted(set(r.get("reuse_keys") or []))
        if pid in GATE_COMBINATION_PREDICATES and value is True:
            # How the enclosing flags combine (P6's `gates` / `gate_paths`),
            # for P8's per-path reading (mechanical.gate_paths_of). Not a
            # citation; a malformed one is dropped, which reads the flags as
            # alternative ways in, the reading that errs toward exposure.
            from reader.mechanical import gate_declaration
            d = gate_declaration(r)
            if d:
                out.update({"gate_paths": d[1]} if d[0] == "paths" else {"gates": d[0]})
            elif r.get("gates") or r.get("gate_paths"):
                out["gates_ignored"] = {k: r.get(k) for k in ("gates", "gate_paths") if r.get(k)}
            # The value(s) a multivariate gate must serve for the change to
            # run (mechanical.gate_values_of); a malformed one is dropped, so
            # `on` stands for exposing.
            from reader.mechanical import gate_values_declaration
            gv = gate_values_declaration(r)
            if gv:
                out["gate_values"] = gv
            elif r.get("gate_values"):
                out["gates_ignored"] = {**out.get("gates_ignored", {}), "gate_values": r.get("gate_values")}
        return out, True

    for pid, q in man["questions"].items():
        r = rep.get(pid)
        if r is None:
            answers[pid] = {"value": UNRESOLVED,
                            "evidence": "not answered", "basis": BASIS}
            missing.append(pid)
            continue
        answers[pid], ok = take(pid, r)
        if ok:
            kept += 1
        else:
            forced.append(pid)

    # The answerer's own P10/P12, before _reread_gates can replace P12 with
    # the key P5/P6's YES cites (mechanical.candidate_from_enclosure).
    own = {pid: answers[pid] for pid in REUSE_KEY_PREDICATES if pid in rep}
    reread = _reread_gates(man, answers, a.repo, a.merged) if a.repo and a.merged else None

    # A P12 YES that contradicts P5's NO about a gate this diff wires is asked
    # again with P5's finding, as read.py does (mechanical.reuse_contradiction).
    # Inline there is no model to call: the question goes to recheck.txt, the
    # answerer adds it under "rechecks" in replies.json, and this runs again.
    recheck = None
    if "reuse_candidates" in man:
        from reader.mechanical import reuse_contradiction
        f = reuse_contradiction(answers, man["reuse_candidates"],
                                man.get("diff_wired_keys") or [])
        if f and "P12" not in rechecks:
            qf = Path(a.out).resolve().parent / "recheck.txt"
            qf.write_text(
                "One question is asked again, because its first answer and an "
                "earlier answer cannot both be right.\n"
                "Answer it in replies.json under \"rechecks\": {\"P12\": {...}}, "
                "in the same shape as the other answers, then run decide again.\n\n"
                "=== P12 ===\n" + man["questions"]["P12"] + "\n\n" + f["context"] + "\n")
            print(f"RECHECK P12: {f['reason']}; question written to {qf}")
            return RECHECK_EXIT
        if f:
            first = answers["P12"]
            answers["P12"], ok = take("P12", rechecks["P12"])
            answers["P12"]["consistency_recheck"] = {
                "reason": f["reason"], "keys": f["keys"],
                "first_read": {k: first.get(k) for k in ("value", "evidence", "basis")}}
            recheck = f"P12 asked again ({f['reason']}): {answers['P12']['value']}"
            if not ok:
                forced.append("P12 (recheck)")

    # The reuse layer is about ONE key, as read.py enforces: a P10/P12 YES
    # resting on no key the layer above kept is asked again (recheck.txt), and
    # a second such YES is a NO (mechanical.reuse_key_violation).
    from reader.mechanical import derived_from, reuse_key_violation, reuse_scope_no
    scope_note = []
    for pid in REUSE_KEY_PREDICATES:
        v = reuse_key_violation(answers, pid)
        if not v:
            continue
        if derived_from(answers[pid]) and pid in own and pid not in rechecks:
            derived, answers[pid] = answers[pid], own[pid]
            answers[pid]["key_scope_recheck"] = {
                "reason": v["reason"], "allowed": v["allowed"],
                "first_read": {k: derived.get(k) for k in ("value", "evidence", "basis", "reuse_keys")},
                "answered_by": "the answerer's own answer, given before the automatic one"}
            v = reuse_key_violation(answers, pid)
            if not v:
                scope_note.append(f"{pid}'s automatic YES was out of scope; the answerer's "
                                  f"own answer kept: {answers[pid]['value']}")
                continue
        if pid not in rechecks:
            qf = Path(a.out).resolve().parent / "recheck.txt"
            qf.write_text(
                "One question is asked again, because its YES rests on no key "
                "it may use.\n"
                f"Answer it in replies.json under \"rechecks\": {{\"{pid}\": {{...}}}}, "
                "in the same shape as the other answers, then run decide again.\n\n"
                f"=== {pid} ===\n" + man["questions"][pid] + "\n\n" + v["context"] + "\n")
            print(f"RECHECK {pid}: {v['reason']}; question written to {qf}")
            return RECHECK_EXIT
        first = answers[pid]
        answers[pid], ok = take(pid, rechecks[pid])
        if not ok:
            forced.append(f"{pid} (recheck)")
        v2 = reuse_key_violation(answers, pid)
        if v2:
            answers[pid] = reuse_scope_no(answers, pid, v2)
        answers[pid]["key_scope_recheck"] = {
            "reason": v["reason"], "allowed": v["allowed"],
            "first_read": {k: first.get(k) for k in ("value", "evidence", "basis", "reuse_keys")}}
        scope_note.append(f"{pid} asked again ({v['reason']}): {answers[pid]['value']}")

    # P32's YES keeps a removed flag: name it for T-RE-2's reuse key, as
    # read.py does (mechanical.record_removed_key).
    from reader.mechanical import record_removed_key
    record_removed_key(answers, man.get("removed_flag_keys") or [])

    doc = {
        "pr": man["pr"],
        "unit": man["unit"],
        "reader": {
            "profile": man["profile"],
            "packet_hash": man["packet_hash"],
            "mode": "inline-no-key",
            "model": "claude-in-session (Claude Code)",
            "samples": 1,
            "reproducible": False,
            "caveats": [
                "no sample independence: one answerer, one context, so the "
                "unanimity check the keyed reader relies on was not performed",
                "no per-predicate isolation: all predicates answered in one "
                "context, so answers may bleed across predicates",
                "no token accounting",
            ],
            "citation_check": "re-run; unresolvable citations forced to "
                              "UNRESOLVED",
            "gate_reread": reread if reread is not None else "not run (needs --repo and --merged)",
            "consistency_recheck": recheck or "none needed",
            "key_scope_recheck": "; ".join(scope_note) or "none needed",
        },
        "answers": answers,
    }
    Path(a.out).write_text(json.dumps(doc, indent=2) + "\n")
    print(f"merged {kept} inline answers + {len(man['mechanical'])} mechanical")
    if forced:
        print(f"  citation-rejected -> UNRESOLVED: {', '.join(forced)}")
    if missing:
        print(f"  unanswered -> UNRESOLVED: {', '.join(missing)}")
    print(f"  reproducible: false  (see reader.caveats in {a.out})")
    print(f"wrote {a.out}")
    return 0


def _reread_gates(man: dict, answers: dict, repo_path: str, merged: str) -> str:
    """P7/P8/P12 from the gate an inline P5/P6 YES cites.

    The manifest's P7/P8 were read before any predicate was answered, from
    flags near the change; the keyed reader re-reads them from the gate a P5
    or P6 YES names (mechanical.apply_enclosure). Without this, an inline P6
    YES leaves P7 at "no flag key is evaluated in the changed files" and the
    walk escalates at N7. The packet is rebuilt to get the flag-site tables,
    and only used if it hashes to the manifest's packet, so the gate is read
    from the same evidence the answers were given on."""
    from reader import ask as askmod
    from reader.mechanical import apply_enclosure, build_packet, setup_ld_client
    from reader.sources import Repo

    if not any(isinstance(answers.get(p), dict) and answers[p].get("value") is True
               for p in GATE_READERS):
        return "no P5/P6 YES to read a gate from"
    repo, prof = Repo(Path(repo_path).resolve()), _profile(man)
    ld = LD_FACTORY(prof)
    head = man["unit"]["head"]
    # The PR text the manifest was built with, when it records one; otherwise
    # the commit message, as read.py falls back to.
    pr = man.get("pr_text") or {
        "title": repo.git("log", "-1", "--format=%s", head).strip(),
        "body": repo.git("log", "-1", "--format=%b", head).strip()[:8000],
        "_source": "commit message (no PR text supplied)"}
    pkt = PACKET_LOADER(man) if PACKET_LOADER else None
    if pkt is None:
        pkt, _ = build_packet(repo, prof, head, man["unit"]["merge_base"], pr, ld, merged)
    elif getattr(pkt, "ld_setup", None) is None:
        # Kept before Packet.ld_setup existed: build once only so the client
        # learns the code's defaults and key projects, and read the gate from
        # the kept packet -- the evidence the answers were given on, with any
        # gates added to it after the start (the gate search).
        build_packet(repo, prof, head, man["unit"]["merge_base"], pr, ld, merged)
    else:
        setup_ld_client(ld, pkt.ld_setup)
    if askmod.packet_hash(pkt) != man["packet_hash"]:
        return "skipped: the rebuilt evidence differs from the manifest's"
    for pid in GATE_READERS:
        if isinstance(answers.get(pid), dict) and answers[pid].get("value") is True:
            apply_enclosure(pkt, ld, merged, answers, pid, log=print)
    return "re-read from the P5/P6 YES"


if __name__ == "__main__":
    sys.exit(main())
