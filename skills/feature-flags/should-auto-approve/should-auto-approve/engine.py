"""The risk graph's walk: copied from classify.py by tools/build_auto_approve.py."""
from __future__ import annotations



UNRESOLVED = "UNRESOLVED"


EVALUATOR = "unresolved-relevance"


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
