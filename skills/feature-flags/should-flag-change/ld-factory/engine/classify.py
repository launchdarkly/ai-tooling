#!/usr/bin/env python3
"""Walk a PR through both graphs, record the walk, and manage disputes.

    classify.py decide   <answers.json>       -> verdict + walk, appended to ledger
    classify.py replay                        -> re-walk every ledger entry against
                                                 the CURRENT graph; report flips
    classify.py cohort   <NODE> [Y|N]         -> every ledger entry that answered
                                                 NODE that way (the comparison set
                                                 for a disputed node)
    classify.py dispute  <pr> <claimed>       -> open a dispute: shows the walk, the
                                                 deciding node, and the cohort
    classify.py gaps                          -> open escalations awaiting a human
    classify.py baseline                      -> REGRESSION GATE: frozen vectors
                                                 must keep their verdicts. Run
                                                 on every graph edit.

WHAT A LEDGER ENTRY IS FOR
--------------------------
Three jobs, and the schema is shaped by all three:

1. Reproduction. The entry pins the graph version by CONTENT HASH. A verdict
   recorded under one graph is not evidence about another, and without the hash
   you cannot tell which graph produced a stored answer.

2. Dispute localisation. The walk names the node that decided. "The bot was
   wrong about this PR" becomes "node N15 answered YES on this PR and should
   have answered NO", which is a claim about a predicate's procedure and can be
   checked without re-litigating the verdict.

3. Node splitting. Every entry stores the FULL predicate vector, not just the
   prefix the tree walked. When a node is disputed you need the other 21 bits
   for the contested PR and for every PR that walked the same way -- that is
   how you find the observable that separates them. Storing only the walked
   prefix makes splitting guesswork, which is why `decide` evaluates the logic
   graph too even though the tree alone would answer.

An answers file is a mapping of predicate id -> one of true | false |
"UNRESOLVED", each with the evidence that settled it:

    {"pr": "https://github.com/o/r/pull/1",
     "unit": {"mode": "merge_base...head", "merge_base": "abc", "head": "def"},
     "answers": {"U1": {"value": true, "evidence": "merge-base = abc123"},
                 "P1": {"value": true, "evidence": "backend/foo.go ships"}}}
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from reader import specload

HERE = Path(__file__).parent
# The spec walked: this folder by default; FDG_SPEC names another tree
# (trees/<name>/) with the same four files.
SPEC = Path(os.environ["FDG_SPEC"]) if os.environ.get("FDG_SPEC") else HERE
# Overridable so the self-test does not write into the repo's real ledger.
_ROOT = Path(os.environ.get("FDG_HOME", HERE))
LEDGER = _ROOT / "ledger"
ESCDIR = _ROOT / "escalations"
UNRESOLVED = "UNRESOLVED"


# Part of the graph hash: how the graphs are EVALUATED, not only what they
# say. Bump it when the walk's semantics change, so a ledger entry records
# which evaluator produced it. "unresolved-relevance": an unresolved answer
# escalates only when the verdict depends on it (resolve_tree).
EVALUATOR = "unresolved-relevance"


def load():
    if not (SPEC / "predicates.yaml").is_file():
        # This skill ships the spec as JSON, with the hash of its YAML source.
        tree = specload.load(SPEC / "tree.yaml")
        return (specload.load(SPEC / "predicates.yaml")["predicates"], tree,
                specload.load(SPEC / "workflow.yaml"), tree["graph_hash"])
    ptxt = (SPEC / "predicates.yaml").read_text()
    ttxt = (SPEC / "tree.yaml").read_text()
    wtxt = (SPEC / "workflow.yaml").read_text()
    h = hashlib.sha256((ptxt + ttxt + wtxt + EVALUATOR).encode()).hexdigest()[:12]
    # The hash is over the YAML text; specload parses it, or its .json twin
    # in the skill bundle, which has no PyYAML.
    preds = specload.load(SPEC / "predicates.yaml")["predicates"]
    return (preds, specload.load(SPEC / "tree.yaml"),
            specload.load(SPEC / "workflow.yaml"), h)


def ev(expr, vals, terms):
    """Three-valued evaluation. Returns True, False or UNRESOLVED."""
    if isinstance(expr, str):
        if expr in terms:
            return ev(terms[expr]["expr"], vals, terms)
        return vals.get(expr, UNRESOLVED)
    if isinstance(expr, list):
        if len(expr) == 1:
            return ev(expr[0], vals, terms)
        op, *rest = expr
        if op == "not":
            v = ev(rest[0], vals, terms)
            return UNRESOLVED if v is UNRESOLVED else (not v)
        parts = [ev(r, vals, terms) for r in rest]
        if op == "and":
            if any(p is False for p in parts):
                return False           # a false conjunct decides, gaps or not
            return UNRESOLVED if any(p is UNRESOLVED for p in parts) else True
        if op == "or":
            if any(p is True for p in parts):
                return True            # a true disjunct decides, gaps or not
            return UNRESOLVED if any(p is UNRESOLVED for p in parts) else False
        raise ValueError(f"bad operator {op!r}")
    raise TypeError(expr)


def walk_tree(tree, vals):
    nodes = {n["id"]: n for n in tree["nodes"]}
    terms = {t["id"]: t for t in tree["terminals"]}
    escs = {e["id"]: e for e in tree["escalations"]}
    steps, cur = [], tree["entry"]
    while cur in nodes:
        n = nodes[cur]
        v = vals.get(n["predicate"], UNRESOLVED)
        if v is UNRESOLVED:
            steps.append({"node": cur, "predicate": n["predicate"],
                          "answer": UNRESOLVED})
            return steps, f"E-UNRESOLVED@{cur}", "escalate"
        steps.append({"node": cur, "predicate": n["predicate"],
                      "answer": "Y" if v else "N"})
        cur = n["if_yes"] if v else n["if_no"]
    if cur in terms:
        return steps, cur, terms[cur]["verdict"]
    return steps, cur, "escalate"


def explore_tree(tree, vals, missing=frozenset()):
    """Every path a partial assignment allows, as leaves.

    An UNRESOLVED answer takes both branches; a predicate in `missing` (not
    asked yet -- the lazy reader's case) ends its path as a pending leaf.
    Exact without carrying assumptions along a path because the tree is an
    ordered decision diagram: verify.py's check 1 proves no predicate is
    tested twice on one path, so the two branches of an unresolved answer
    can never meet that predicate again. Each leaf therefore stands for a
    non-empty set of completions, and together they cover all of them.

    Leaf: {"steps", "terminal", "verdict", "pending"}; an unresolved step
    has answer UNRESOLVED and `branch` Y/N for the side that leaf took.
    """
    nodes = {n["id"]: n for n in tree["nodes"]}
    terms = {t["id"]: t for t in tree["terminals"]}
    leaves = []

    def go(cur, steps):
        while cur in nodes:
            n = nodes[cur]
            pid = n["predicate"]
            if pid in missing:
                leaves.append({"steps": steps, "terminal": None,
                               "verdict": None, "pending": pid})
                return
            v = vals.get(pid, UNRESOLVED)
            if v == UNRESOLVED:
                for b, nxt in (("Y", n["if_yes"]), ("N", n["if_no"])):
                    go(nxt, steps + [{"node": cur, "predicate": pid,
                                      "answer": UNRESOLVED, "branch": b}])
                return
            steps = steps + [{"node": cur, "predicate": pid,
                              "answer": "Y" if v else "N"}]
            cur = n["if_yes"] if v else n["if_no"]
        leaves.append({"steps": steps, "terminal": cur, "pending": None,
                       "verdict": terms[cur]["verdict"] if cur in terms else "escalate"})

    go(tree["entry"], [])
    return leaves


def settle(leaves):
    """The leaf standing for the outcome every leaf reaches, or None.

    Every leaf the same verdict (by any terminal), or every leaf the same
    decided escalation. A pending leaf settles nothing."""
    if not leaves or any(l["pending"] for l in leaves):
        return None
    if len({l["verdict"] for l in leaves}) == 1 and leaves[0]["verdict"] != "escalate":
        return leaves[0]
    if len({l["terminal"] for l in leaves}) == 1:
        return leaves[0]
    return None


def resolve_tree(tree, vals):
    """walk_tree, except an unresolved answer escalates only when the verdict
    depends on it.

    Returns (steps, terminal, verdict, over_determined). When every way of
    answering the unresolved predicates on the reachable paths gives the
    same verdict, that verdict stands: steps and terminal are the first such
    path's (YES branch first), and over_determined names the predicates that
    did not matter and every terminal reached. Otherwise this is exactly
    walk_tree, escalating at the first unresolved node. Measured on the
    boards: an earlier PR escalated at N27C though both answers give
    suggested; an earlier PR at N21 though both give not-suited.
    """
    leaves = explore_tree(tree, vals)
    if len(leaves) == 1:
        l = leaves[0]
        return l["steps"], l["terminal"], l["verdict"], None
    s = settle(leaves)
    if s is None:
        return (*walk_tree(tree, vals), None)
    order = {n["id"]: i for i, n in enumerate(tree["nodes"])}
    unres = {}
    for l in leaves:
        for st in l["steps"]:
            if st["answer"] == UNRESOLVED:
                unres.setdefault(st["predicate"], order.get(st["node"], 0))
    return s["steps"], s["terminal"], s["verdict"], {
        "unresolved": sorted(unres, key=unres.get),
        "terminals": sorted({l["terminal"] for l in leaves}),
        "paths": len(leaves)}


def walk_signature(steps):
    """N3N/N27C?Y -- `?` marks an unresolved answer and the branch shown."""
    return "/".join(f"{s['node']}?{s['branch']}" if s.get("branch")
                    else f"{s['node']}{s['answer']}" for s in steps)


def walk_workflow(wf, vals):
    """Walk the n-ary workflow. Edges are ordered; first match wins.

    ONE QUESTION PER STEP, same discipline as the tree -- a node with eight
    edges is a single multiple-choice dispatch, not a multi-predicate match.
    Asking only what the walk needs keeps it from manufacturing answers to
    questions the decision never asks. The static exactly-one / no-gap check
    lives in verify.py.

    An edge whose condition is UNRESOLVED, with no earlier edge matched, means
    the node cannot dispatch -> escalate. If an earlier edge already matched,
    later unresolved conditions are irrelevant by construction.
    """
    nodes = {n["id"]: n for n in wf["nodes"]}
    steps, cur = [], wf["entry"]
    while cur in nodes:
        n = nodes[cur]
        chosen = None
        for e in n["edges"]:
            if e["when"] == "default":
                chosen = e
                break
            r = ev(e["when"], vals, {})
            if r is True:
                chosen = e
                break
            if r is UNRESOLVED:
                steps.append({"node": cur, "question": n["question"],
                              "answer": UNRESOLVED,
                              "blocked_on": e.get("answer")})
                return steps, f"E-UNRESOLVED@{cur}", "escalate"
        steps.append({"node": cur, "question": n["question"],
                      "answer": chosen["answer"], "to": chosen["to"]})
        cur = chosen["to"]
    return steps, cur, None


def _vars(expr):
    if isinstance(expr, str):
        return [expr]
    if isinstance(expr, list):
        return [v for x in expr if x not in ("and", "or", "not") for v in _vars(x)]
    return []


def resolve_workflow(wf, tverd, vals):
    """walk_workflow with resolve_tree's rule: a node blocked on an
    unresolved condition is dispatched both ways on one of its unresolved
    predicates, and escalates only if the outcomes differ.

    Branches by assigning the predicate, so it is exact for any edge
    expression. Returns (steps, terminal, label, over_determined), the label
    being the tree verdict a terminal maps to, or the escalation id.
    """
    nodes = {n["id"]: n for n in wf["nodes"]}
    leaves, assumed = [], []

    def go(v):
        steps, term, _ = walk_workflow(wf, v)
        if term.startswith("E-UNRESOLVED@"):
            node = nodes[term.split("@", 1)[1]]
            for e in node["edges"]:
                if e["when"] == "default":
                    break
                r = ev(e["when"], v, {})
                if r is True:
                    break
                if r is UNRESOLVED:
                    p = next(x for x in _vars(e["when"]) if v.get(x, UNRESOLVED) == UNRESOLVED)
                    if p not in assumed:
                        assumed.append(p)
                    go({**v, p: True})
                    go({**v, p: False})
                    return
        leaves.append({"steps": steps, "terminal": term, "pending": None,
                       "verdict": tverd.get(term, "escalate")})

    go(dict(vals))
    if len(leaves) == 1 and not assumed:
        l = leaves[0]
        return l["steps"], l["terminal"], tverd.get(l["terminal"], l["terminal"]), None
    s = settle(leaves)
    if s is None:
        steps, term, _ = walk_workflow(wf, vals)
        return steps, term, term, None
    return s["steps"], s["terminal"], tverd.get(s["terminal"], s["terminal"]), {
        "unresolved": assumed, "terminals": sorted({l["terminal"] for l in leaves}),
        "paths": len(leaves)}


ALIAS ={"ESCALATE-AMBIGUOUS": "E-AMBIG", "ESCALATE-UNIT": "E-UNIT",
         "ESCALATE-STATE": "E-STATE"}

# Two kinds of non-verdict outcome, and the difference matters when comparing
# the graphs. A DECIDED escalation is the graph deliberately routing a fully
# resolved PR to a human (E-STATE, E-AMBIG, E-UNIT); both graphs must name the
# same one. A DATA GAP is the graph declining to answer because an input is
# missing; the tree names the node where the walk stopped, the logic names the
# expression that would not resolve. Those are different descriptions of one
# situation, not a disagreement -- so they are compared by KIND, and both
# labels are recorded.
DECIDED_ESCALATIONS = {"E-STATE", "E-AMBIG", "E-UNIT"}


def outcome_kind(label):
    if label in DECIDED_ESCALATIONS:
        return "decided-escalation"
    if label.startswith("E-"):
        return "data-gap"
    return "verdict"


def compare(tree_label, logic_label):
    """Return (agree: bool, note: str)."""
    kt, kl = outcome_kind(tree_label), outcome_kind(logic_label)
    if kt != kl:
        return False, f"tree gave a {kt}, logic gave a {kl}"
    if kt == "data-gap":
        return True, ("both declined for missing inputs "
                      f"(tree: {tree_label}, logic: {logic_label})")
    if tree_label != logic_label:
        return False, f"both {kt}s but different: {tree_label} vs {logic_label}"
    return True, ""


BACKTICK_KEY = re.compile(r"`([a-z0-9][a-z0-9._-]*)`")


def answer_key(a) -> str | None:
    """The flag key an answer names: its `flag_key` field, else the first key
    in backticks in its evidence (the classic tree asks for keys that way)."""
    if not isinstance(a, dict):
        return None
    if a.get("flag_key"):
        return str(a["flag_key"])
    m = BACKTICK_KEY.search(str(a.get("evidence") or ""))
    return m.group(1) if m else None


def reuse_flag_key(raw: dict, tree: dict | None = None,
                   terminal: str | None = None) -> tuple[str | None, str | None]:
    """(the reuse key, a note when it cannot be recorded cleanly) from an
    answers.json's answers: P11's still-withheld keys, intersected with the
    keys P10's and P12's YES rest on. Answer files from before the reuse
    layer recorded keys carry none of these fields; their key is not
    recorded rather than guessed from free text. A tree that names
    `reuse_key_from` takes the key that question's answer names, and so
    does a terminal that names one (T-RE-2: the removed flag P32 keeps,
    which the reader records as P32's `flag_key`)."""
    tree = tree if tree is not None else load()[1]
    term = next((t for t in tree.get("terminals") or [] if t.get("id") == terminal), {})
    if term.get("reuse_key_from"):
        pid = term["reuse_key_from"]
        key = answer_key(raw.get(pid))
        return key, (None if key else f"{pid}'s answer names no removed flag key")
    if tree.get("reuse_key_from"):
        key = answer_key(raw.get(tree["reuse_key_from"]))
        return key, (None if key else f"{tree['reuse_key_from']}'s answer names no key in backticks")
    p10, p11, p12 = (raw.get(p) if isinstance(raw.get(p), dict) else {}
                     for p in ("P10", "P11", "P12"))
    if ("withholding_keys" not in p11 or "reuse_keys" not in p10
            or "reuse_keys" not in p12):
        return None, "not recorded: these answers predate key-scoped reuse"
    scope = (set(p11["withholding_keys"]) & set(p10["reuse_keys"])
             & set(p12["reuse_keys"]))
    if not scope:
        return None, ("NO key satisfies P10, P11 and P12 together -- the "
                      "reader's key-scope check should have answered P12 NO")
    keys = sorted(scope)
    return keys[0], (None if len(keys) == 1 else
                     f"several keys qualify ({', '.join(keys)}); recorded the first")


def decide(path):
    preds, tree, wf, gh = load()
    ids = [p["id"] for p in preds]
    doc = json.loads(Path(path).read_text())
    raw = doc.get("answers", {})

    unknown = sorted(set(raw) - set(ids))
    if unknown and not tree.get("reuse_key_from"):
        raise SystemExit(f"unknown predicate ids in answers: {unknown}")
    # A tree other than ODD's (trees/<name>/) runs on the same reader, whose
    # automatic answers are ODD's questions: they are set aside, not walked.
    set_aside = {k: raw[k] for k in unknown}
    raw = {k: v for k, v in raw.items() if k not in set_aside}

    vals, evidence, basis = {}, {}, {}
    for pid in ids:
        a = raw.get(pid)
        if a is None:
            vals[pid] = UNRESOLVED
            evidence[pid] = None
            continue
        v = a["value"] if isinstance(a, dict) else a
        vals[pid] = UNRESOLVED if v == UNRESOLVED else bool(v)
        evidence[pid] = a.get("evidence") if isinstance(a, dict) else None
        if isinstance(a, dict) and a.get("basis"):
            basis[pid] = a["basis"]

    steps, terminal, verdict, od = resolve_tree(tree, vals)

    # A closed-world answer is only worth recording if it DECIDED something.
    # Same relevance test the logic graph uses for unresolved inputs: flip the
    # predicate, re-walk, and see whether the verdict moves. Tagging every
    # closed-world answer regardless would mark most entries and the tag would
    # stop meaning anything.
    cw = [p for p in ids if basis.get(p) == "closed-world"]
    cw_decisive = []
    for p in cw:
        if vals[p] is UNRESOLVED:
            continue
        flipped = dict(vals)
        flipped[p] = not vals[p]
        _, t2, v2, _ = resolve_tree(tree, flipped)
        if (t2, v2) != (terminal, verdict):
            cw_decisive.append({"predicate": p, "would_become": v2,
                                "would_terminal": t2})

    tverd = {t["id"]: t["verdict"] for t in tree["terminals"]}
    wsteps, wterminal, wf_label, wod = resolve_workflow(wf, tverd, vals)

    tv = terminal if verdict == "escalate" else verdict
    agree, agree_note = compare(tv, wf_label)

    entry = {
        "pr": doc.get("pr"),
        "profile": doc.get("reader", {}).get("profile"),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graph_hash": gh,
        "graph_version": tree["version"],
        "unit": doc.get("unit"),
        "predicates": {p: (vals[p] if vals[p] is not UNRESOLVED else UNRESOLVED)
                       for p in ids},
        "evidence": {k: v for k, v in evidence.items() if v},
        "tree": {"walk": steps, "terminal": terminal, "verdict": verdict,
                 "walk_signature": walk_signature(steps),
                 "over_determined": od},
        "workflow": {"steps": wsteps, "terminal": wterminal,
                     "verdict": wf_label,
                     "walk_signature": "/".join(s["node"] for s in wsteps),
                     "over_determined": wod},
        "agreement": agree,
        "agreement_note": agree_note or None,
        "basis": basis or None,
        "closed_world": {"answers": cw, "decisive": cw_decisive} if cw else None,
        "decided_by_closed_world": bool(cw_decisive),
    }

    # T-RE-1 must_record: reuse_flag_key. The reuse layer is about ONE key
    # (predicates.yaml), recorded by the reader as P11's withholding_keys and
    # P10/P12's reuse_keys; the key is their intersection.
    if verdict == "reuse-existing":
        key, note = reuse_flag_key(raw, tree, terminal)
        entry["reuse_flag_key"] = key
        if note:
            entry["reuse_flag_key_note"] = note

    LEDGER.mkdir(parents=True, exist_ok=True)
    slug = (doc.get("pr") or "unknown").rstrip("/").replace("https://", "") \
        .replace("/", "-").replace(":", "")
    (LEDGER / f"{slug}.json").write_text(json.dumps(entry, indent=2) + "\n")

    print(f"pr        {entry['pr']}")
    print(f"profile   {entry['profile']}")
    print(f"graph     {entry['graph_version']} ({gh})")
    print(f"tree      {terminal} -> {verdict}")
    if "reuse_flag_key" in entry:
        print(f"reuse key {entry['reuse_flag_key']}"
              + (f"  ({entry['reuse_flag_key_note']})"
                 if entry.get("reuse_flag_key_note") else ""))
    print(f"workflow  {wf_label}  ({len(wsteps)} steps)")
    print(f"agreement {'YES' if agree else 'NO -- graphs disagree, escalate'}"
          + (f"  ({agree_note})" if agree_note else ""))
    print(f"walk      {entry['tree']['walk_signature']}")
    if od:
        print(f"OVER-DETERMINED  {', '.join(od['unresolved'])} unresolved, but every "
              f"answer gives {verdict} ({', '.join(od['terminals'])})")
    for d in cw_decisive:
        print(f"CLOSED-WORLD  {d['predicate']} answered from ABSENCE of evidence "
              f"and it decided this verdict")
        print(f"              positive evidence would give "
              f"{d['would_become']} ({d['would_terminal']})")
        print(f"              audit the population: classify.py cohort "
              f"{next((s['node'] for s in steps if s['predicate']==d['predicate']), '?')} "
              f"{'Y' if vals[d['predicate']] else 'N'}")
    if not agree or verdict == "escalate":
        ESCDIR.mkdir(parents=True, exist_ok=True)
        (ESCDIR / f"{slug}.json").write_text(json.dumps({
            "pr": entry["pr"], "profile": entry["profile"], "graph_hash": gh,
            "reason": ("graphs disagree" if not agree else
                       terminal if verdict == "escalate" else wterminal),
            "tree_verdict": tv, "workflow_verdict": wf_label,
            "walk_signature": entry["tree"]["walk_signature"],
            "deciding_node": steps[-1] if steps else None,
            "unresolved": [p for p in ids if vals[p] is UNRESOLVED],
            "question_for_human": None, "human_ruling": None,
            "justification_required": True,
        }, indent=2) + "\n")
        print(f"\nESCALATED -> escalations/{slug}.json")
        print("A human judge must rule, and the ruling must name an OBSERVABLE.")
    return 0


def entries():
    if not LEDGER.exists():
        return []
    out = []
    for f in sorted(LEDGER.glob("*.json")):
        try:
            out.append((f, json.loads(f.read_text())))
        except json.JSONDecodeError:
            print(f"  ! unreadable ledger entry: {f.name}", file=sys.stderr)
    return out


def replay():
    preds, tree, wf, gh = load()
    rows = entries()
    if not rows:
        print("ledger is empty — nothing to replay")
        return 0
    print(f"current graph {tree['version']} ({gh}) · {len(rows)} entries\n")
    flips, stale = [], 0
    for f, e in rows:
        vals = {k: (UNRESOLVED if v == UNRESOLVED else v)
                for k, v in e["predicates"].items()}
        steps, terminal, verdict, _ = resolve_tree(tree, vals)
        was = e["tree"]["verdict"]
        if e.get("graph_hash") != gh:
            stale += 1
        if verdict != was:
            flips.append((e["pr"], e.get("profile"), was, verdict,
                          e["tree"]["walk_signature"],
                          walk_signature(steps)))
    print(f"recorded under an older graph: {stale}")
    if not flips:
        print("no verdict changed under the current graph")
        return 0
    print(f"\n{len(flips)} verdict(s) CHANGED — review each before shipping the edit:\n")
    for pr, profile, was, now, w0, w1 in flips:
        print(f"  [{profile or '?'}] {pr}\n    {was} -> {now}\n    was: {w0}\n    now: {w1}\n")
    return 0


def cohort(node, answer=None):
    rows = entries()
    hits = []
    for f, e in rows:
        for s in e["tree"]["walk"]:
            if s["node"] == node and (answer is None or s["answer"] == answer):
                hits.append((e, s["answer"]))
                break
    if not hits:
        print(f"no ledger entries visited {node}"
              + (f" with answer {answer}" if answer else ""))
        return 0
    print(f"{len(hits)} entr{'y' if len(hits)==1 else 'ies'} visited {node}"
          + (f"={answer}" if answer else "") + "\n")
    for e, a in hits:
        cwm = " [closed-world]" if e.get("decided_by_closed_world") else ""
        print(f"  {a}  {e['tree']['verdict']:16s}  [{e.get('profile') or '?'}]  "
              f"{e['pr']}{cwm}")
    # the splitting search: which other predicates separate this cohort?
    print("\npredicates that VARY across this cohort (candidate splitters):")
    allp = sorted({k for e, _ in hits for k in e["predicates"]})
    for p in allp:
        vs = {json.dumps(e["predicates"].get(p)) for e, _ in hits}
        if len(vs) > 1:
            print(f"  {p:5s} takes {sorted(vs)}")
    print("\nA predicate that varies here can split the node. One that does not,")
    print("cannot — no procedure change to it will separate these PRs.")
    return 0


def dispute(pr, claimed):
    rows = [e for _, e in entries() if e.get("pr") == pr or pr in str(e.get("pr"))]
    if not rows:
        print(f"no ledger entry for {pr}; run `decide` first")
        return 1
    e = rows[0]
    print(f"pr        {e['pr']}")
    print(f"profile   {e.get('profile') or '?'}")
    print(f"recorded  {e['tree']['verdict']} under graph {e['graph_version']} "
          f"({e['graph_hash']})")
    print(f"claimed   {claimed}")
    print(f"walk      {e['tree']['walk_signature']}\n")
    last = e["tree"]["walk"][-1]
    print(f"The walk is deterministic, so the disagreement is localised to one")
    print(f"node. Deciding node: {last['node']} ({last['predicate']}) "
          f"answered {last['answer']}.\n")
    print("Two things a human judge must separate:")
    print("  (a) the predicate was answered WRONGLY on this PR")
    print("      -> fix the evidence; the graph is fine. No node change.")
    print("  (b) the predicate was answered CORRECTLY and the verdict is still")
    print("      wrong -> the node is wrong. Change or split it.\n")
    print(f"Cohort for (b) — run: classify.py cohort {last['node']} {last['answer']}")
    return 0


BASELINE = HERE / "baseline"


def baseline():
    """Regression gate: frozen vectors must keep their expected verdicts.

    WHY FROZEN VECTORS AND NOT RE-READ PRs
    The graph is a pure function of the predicate vector, so freezing vectors
    tests the GRAPH. Re-reading the PRs would mix in reader variance, and a
    failure would not tell you whether the graph regressed or the reader
    drifted -- plus it would need a key and cost money on every edit. Reader
    drift is a real thing to watch, but it is a different instrument on a
    different cadence.

    WHY `replay` IS NOT THIS
    `replay` reports what changed across the whole ledger; every flip needs a
    human look. This asserts what must NOT change. Different jobs: replay is
    the blast-radius report for a proposed edit, baseline is the gate.

    THREE SEVERITIES, AND THE REASON
      structural (fail) -- a constructed vector pinning a terminal's
          reachability. Complete by construction: every terminal has one, so
          an edit cannot silently orphan a branch.
      ruled (fail)      -- a human-confirmed verdict. A flip here means the
          graph now contradicts a ruling.
      observed (warn)   -- a machine verdict on a real PR, never reviewed.
          Reported, never fatal. Freezing unreviewed output as a hard gate
          would cement today's mistakes and then fail every correct amendment
          that fixes one.
    """
    preds, tree, wf, gh = load()
    if not BASELINE.exists() or not any(BASELINE.glob("*.json")):
        print("no baseline cases; seed with scripts/seed_baseline.py")
        return 1
    tverd = {x["id"]: x["verdict"] for x in tree["terminals"]}

    cases = []
    for f in sorted(BASELINE.glob("*.json")):
        try:
            cases.append((f, json.loads(f.read_text())))
        except json.JSONDecodeError as e:
            print(f"  ! unreadable baseline case {f.name}: {e}")
            return 1

    print(f"graph {tree['version']} ({gh})   {len(cases)} baseline cases\n")
    fails, warns, covered = [], [], set()
    for f, c in cases:
        vals = {k: (UNRESOLVED if v == UNRESOLVED else v)
                for k, v in c["vector"].items()}
        steps, terminal, verdict, od = resolve_tree(tree, vals)
        wsteps, wterm, wlabel, wod = resolve_workflow(wf, tverd, vals)
        got = {"terminal": terminal,
               "verdict": terminal if verdict == "escalate" else verdict}
        want = c["expect"]
        covered.add(want["terminal"])
        sev = c.get("severity", "fail")
        ok = got["terminal"] == want["terminal"]
        # Over-determined, each graph names the first terminal it reached;
        # they need only agree on the verdict.
        cross = (wterm == terminal) if not (od or wod) else (wlabel == got["verdict"])
        tag = "ok  " if ok and cross else ("FAIL" if sev == "fail" else "warn")
        if not ok or not cross:
            row = (c["id"], want["terminal"], got["terminal"],
                   c.get("kind"), "" if cross else " (tree/workflow disagree)")
            (fails if sev == "fail" else warns).append(row)
        print(f"  [{tag}] {c['id']:34s} {c.get('kind','?'):10s} "
              f"{want['terminal']} -> {got['terminal']}")

    all_terms = set(tverd) | {e["id"] for e in tree["escalations"]}
    missing = sorted(all_terms - covered)
    print()
    print(f"terminal coverage: {len(covered)}/{len(all_terms)}")
    if missing:
        fails.append(("<coverage>", ",".join(missing), "no fixture", "-", ""))
        print(f"  UNCOVERED (an edit could break these undetected): {missing}")

    if warns:
        print(f"\n{len(warns)} warning(s) -- observed verdicts moved, review "
              f"but not fatal:")
        for i, w, g, k, x in warns:
            print(f"  {i}: {w} -> {g}{x}")
    if fails:
        print(f"\nFAIL -- {len(fails)} regression(s):")
        for i, w, g, k, x in fails:
            print(f"  {i} [{k}]: expected {w}, got {g}{x}")
        print("\nIf an amendment INTENDED one of these, re-baseline it")
        print("explicitly: update the case's `expect`, and record the ruling")
        print("that authorises it in `why`. Do not edit expectations to make")
        print("the gate pass -- that is the one move that makes it worthless.")
        return 1
    print("\nPASS -- every frozen vector kept its verdict")
    return 0


def gaps():
    if not ESCDIR.exists() or not any(ESCDIR.glob("*.json")):
        print("no open escalations")
        return 0
    for f in sorted(ESCDIR.glob("*.json")):
        d = json.loads(f.read_text())
        state = "RULED" if d.get("human_ruling") else "OPEN"
        print(f"[{state}] {d['reason']:24s} [{d.get('profile') or '?'}] {d['pr']}")
        if state == "OPEN":
            print(f"         walk: {d['walk_signature']}")
            if d.get("unresolved"):
                print(f"         unresolved: {', '.join(d['unresolved'])}")
    return 0


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, *rest = argv[1:]
    if cmd == "decide":
        return decide(rest[0])
    if cmd == "replay":
        return replay()
    if cmd == "cohort":
        return cohort(rest[0], rest[1] if len(rest) > 1 else None)
    if cmd == "dispute":
        return dispute(rest[0], rest[1] if len(rest) > 1 else "(unstated)")
    if cmd == "gaps":
        return gaps()
    if cmd == "baseline":
        return baseline()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
