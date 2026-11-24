"""The fact search: when a question answered "unresolved" decides the result,
search the repository for the one fact the answer was missing, and ask the
question once more with what verifies.

A question answers UNRESOLVED when the evidence lacks something its procedure
needs, and the walk then escalates to a person. Often one fact is missing --
a caller, a guard, a writer, a setting -- that is in the repository at the
change's commit but not in the bounded evidence. The consumer search already
settles P19 this way (consumer_search.py). This generalizes it to every
question a model answers: once the answers are in and one UNRESOLVED answer
decides the result (`pick`, the same test that asks for the consumer search),
the skill asks the agent (FACTS.md) to search the repository at head for
exactly that fact and report what it finds as quoted lines, each with a
one-line claim. `verify` checks every quote against head; only verified
findings reach the question (ask.fact_search_context), which is then asked
once more. A search that verifies nothing changes nothing: the answer stays
UNRESOLVED and the walk escalates as before. One search per question per run.

Not for mechanical answers (they are computed), not for P19 (the consumer
search), and not for a question about LaunchDarkly state (a repository search
can't supply it).
"""
from __future__ import annotations

from .gate_search import _check_ref, _norm

MAX_FINDINGS = 12
SKIP = frozenset({"P19"})  # settled by the consumer search instead


def verify(repo_path: str, head: str, finding: dict, files: dict) -> str | None:
    """None when a finding ({path, line, text, claim}) is that line at head
    and says what it shows, else why not."""
    if not isinstance(finding, dict):
        return "not an object"
    if not _norm(finding.get("claim")):
        return "no claim: say in one line what this line shows"
    return _check_ref(repo_path, head, finding, files)


def check(repo_path: str, head: str, reply: dict) -> tuple[list[dict], list[dict]]:
    """(verified, dropped) findings of a reply; at most MAX_FINDINGS are read."""
    files: dict = {}
    kept, dropped = [], []
    for f in (reply.get("findings") or [])[:MAX_FINDINGS]:
        why = verify(repo_path, head, f, files)
        if why:
            dropped.append({**(f if isinstance(f, dict) else {"finding": f}), "dropped": why})
        else:
            kept.append({"path": f["path"], "line": f["line"], "text": _norm(f["text"]),
                         "claim": _norm(f["claim"])})
    return kept, dropped


# The questions answered from LaunchDarkly state (predicates.yaml: their
# inputs are flag state, read against the code at most): a repository search
# can't supply what they lack. Named here, not read from `inputs`, because the
# shipped spec leaves `inputs` out.
LAUNCHDARKLY_STATE = frozenset({"P7", "P8", "P11", "P33"})


def searchable(pid: str) -> bool:
    """A question a repository search can inform: not the consumer search's,
    and not one about LaunchDarkly state."""
    return pid not in SKIP and pid not in LAUNCHDARKLY_STATE


def _vals(answers: dict) -> dict:
    import classify
    return {p: (classify.UNRESOLVED if str(a.get("value")).upper() == "UNRESOLVED" else bool(a.get("value")))
            for p, a in answers.items()}


def decides(tree: dict, vals: dict, missing: set, pid: str) -> bool:
    """Whether answering `pid` YES or NO gives different results (either
    still undecided counts as different): the consumer search's test."""
    import classify
    yes, no = (classify.settle(classify.explore_tree(tree, {**vals, pid: v}, missing)) for v in (True, False))
    return not (yes is not None and no is not None
                and (yes["verdict"], yes["terminal"]) == (no["verdict"], no["terminal"]))


def model_reply(replies: dict, pid: str) -> dict | None:
    """The answerer's own reply to `pid` (a recheck's, when given)."""
    return ((replies.get("rechecks") or {}).get(pid) or (replies.get("answers") or {}).get(pid))


def pick(tree: dict, preds: dict, answers: dict, replies: dict, mechanical: set,
         done: set) -> str | None:
    """The question to search for, or None: the first in the tree's order
    whose answer the answerer gave as unresolved, that a repository search
    can inform, that hasn't been searched for in this run, and that decides
    the result once every question the result needs is answered."""
    import classify
    from .read import lazy_needed
    given = {p: a for p, a in answers.items() if a.get("evidence") != "not answered"}
    if lazy_needed(tree, given) is not None:
        return None  # other questions come first; this one may not matter yet
    vals = _vals(given)
    missing = {n["predicate"] for n in tree["nodes"]} - set(given)
    now = classify.settle(classify.explore_tree(tree, vals, missing))
    if now is not None and now["verdict"] != "escalate":
        return None  # decided whatever the unresolved answers would be
    seen = []
    for n in tree["nodes"]:
        pid = n["predicate"]
        if pid in seen:
            continue
        seen.append(pid)
        a = given.get(pid) or {}
        r = model_reply(replies, pid) or {}
        if (not searchable(pid) or pid in mechanical or pid in done or pid not in preds
                or vals.get(pid) != classify.UNRESOLVED or a.get("from_enclosure")
                or str(r.get("value")).lower() != "unresolved"):
            continue
        if decides(tree, vals, missing, pid):
            return pid
    return None


def task(template: str, pid: str, pred: dict, question: str, answer: dict, subs: dict) -> str:
    """FACTS.md filled in for one question."""
    text = template
    for k, v in {**subs, "QUESTION_ID": pid,
                 "QUESTION": " ".join(str(pred.get("question") or "").split()),
                 "UNRESOLVED_WHEN": "\n".join("  " + ln for ln in str(pred.get("unresolved_when") or "")
                                              .rstrip().splitlines()),
                 "ANSWER_EVIDENCE": " ".join(str(answer.get("evidence") or "(none given)").split()),
                 "FULL_QUESTION": question}.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def record(rec: dict) -> dict:
    """What an answer re-given after the search carries, so a NO or YES that
    rests on the search says so in the ledger."""
    return {"findings": len(rec.get("verified") or []), "dropped": len(rec.get("dropped") or []),
            "searched": rec.get("searched"), "first_answer": rec.get("first_answer")}
