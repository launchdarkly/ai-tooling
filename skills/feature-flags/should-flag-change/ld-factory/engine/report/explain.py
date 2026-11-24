"""The report: the result in plain English, the reasons, where to check a flag,
what a rollout can measure, next steps, and the machine-readable
`recommend-flag` block.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SELF = Path(__file__).resolve().parent
# The should-flag-change skill bundle ships this file beside its own copy of
# the tree and says where that is.
ODD_HOME = Path(os.environ.get("ODD_HOME") or SELF.parent).resolve()
sys.path.insert(0, str(ODD_HOME))

from classify import UNRESOLVED, resolve_tree, reuse_flag_key  # noqa: E402
from reader import specload  # noqa: E402

QUESTION = {
    "U1": "Could the change be compared against the right starting point?",
    "P1": "Does any changed file ship to production?",
    "P2": "Does the change alter what the product actually does?",
    "P3": "Is it only cleaning up an old flag?",
    "P32": "Does that flag still give some real customers the behavior this change deletes?",
    "P4": "Does it only prepare code to accept data nothing sends yet?",
    "P5": "Is all of it behind a flag this change adds?",
    "P6": "Is all of it already behind an existing flag?",
    "P7": "Could that flag's current state be read from LaunchDarkly?",
    "P8": "Is that flag still off for every real user?",
    "P33": "Is that flag still off, or only partly rolled out, for customers in the main production environment?",
    "P9": "Is an existing flag checked right next to the changed code?",
    "P10": "Is that flag used in the same feature?",
    "P11": "Is that flag still off for some users?",
    "P12": "Would turning that flag off hide all of this change?",
    "P13": "Does this change have its own separate release plan?",
    "P15": "Does it add something new customers can reach, like a page, endpoint, or flow?",
    "P18": "Does it show users an announcement, banner, or message they didn't ask for?",
    "P19": "Does it change an API that other apps or services rely on?",
    "P20": "Does it change a default, or how an existing screen works?",
    "P27": "Does it add work to a path all customer traffic goes through?",
    "P28": "Is that new work safely contained?",
    "P30": "Does it change a path customers already use in a way that could fail them (shown line by line)?",
    "P26": "Is it a fix, cleanup, or restyle a flag wouldn't really help with?",
    "P21": "Would a real user notice the difference?",
    "P22": "Is it only a visual or wording change?",
    "P23": "Does it only change what happens for things that were already failing?",
    "P25": "Is it a noticeable change a flag still wouldn't really help with?",
    "P31": "Would a mistake be small and quickly undone?",
}

HEADLINE = {
    "suggested": "Suggested: ship this change behind a new feature flag.",
    "reuse-existing": "Reuse an existing flag rather than adding a new one.",
    "already-flagged": "Already flagged: no new flag needed.",
    "not-suited": "Not suited: a flag wouldn't meaningfully reduce the risk here.",
    "escalate": "A person needs to decide.",
}

WHY = {
    "T-NS-1": "Nothing that changed ships to production.",
    "T-NS-2": "The shipped code is reorganized (renamed, moved, reformatted) without changing what the product does.",
    "T-NS-3": "It only removes an old flag and keeps one of its behaviors. Cleanup doesn't need a new flag.",
    "T-NS-4": "It only prepares code to accept data in a format nothing sends yet. A flag would break things once that data arrives.",
    "T-NS-5": "Behavior changes, but no real user would notice, and it touches nothing high-risk.",
    "T-NS-6": "Users will see it, but only how things look or read changes: styling, layout, or wording.",
    "T-NS-7": "It only changes what happens for things that were already failing. Turning a flag off would just bring the failure back.",
    "T-NS-8": "Something about it looked flag-worthy, but it's a fix, cleanup, or restyle that users won't notice.",
    "T-NS-9": "Users will notice it, but it's a fix or cleanup a flag wouldn't really help with. Worth a reviewer's quick look.",
    "T-NS-10": "Users will notice it, but nothing about it calls for a flag. Worth a reviewer's quick look.",
    "T-NS-11": "Something about it looked flag-worthy, but a mistake would reach few users, be easy to spot, and be undone by rolling back, so a flag adds little. Worth a reviewer's quick look.",
    "T-AF-1": "The change is already behind a flag this PR adds.",
    "T-AF-2": "The change is already behind an existing flag that's still off for every real user.",
    "T-AF-3": "The change is already behind an existing flag. It's on for some real users, but it can still switch this change off.",
    "T-AF-4": "The change is already behind an existing flag that still holds it back from some customers in the main production environment (it's off there, or on only for some), so turning that flag off still protects them.",
    "T-RE-1": "An existing flag already covers this unreleased feature, and turning it off hides this whole change.",
    "T-RE-2": "It deletes a flag that some real customers still don't get: they still get the behavior this change removes. Keep the flag and finish the rollout before removing it.",
    "T-SG-1": "An existing flag could cover it, but this change is released on its own schedule, so it should get its own flag.",
    "T-SG-3": "It adds something new that customers can reach, like a page, endpoint, or flow.",
    "T-SG-6": "It shows users an announcement, banner, or message they didn't ask for. Who sees it, and when, is a release decision.",
    "T-SG-7": "It changes an API that other apps or services rely on.",
    "T-SG-8": "It changes a default, or how an existing screen works, for users who didn't opt in.",
    "T-SG-9": "Something about it looked flag-worthy but reads like a fix or cleanup. Users will notice it, so consider whether an off switch is worth having.",
    "T-SG-10": "It adds new work to a path all customer traffic goes through. A flag lets you switch it off if it misbehaves.",
    "T-SG-12": "It changes how a path customers already use behaves -- a new call or write, a different target, a cache, a check that can block it, a new or removed action, or a change to stored data -- in a way that could fail them. A flag lets you switch it off if it does.",
    "E-UNIT": "The change couldn't be compared against the right starting point, so it couldn't be checked.",
    "E-STATE": "The change sits behind an existing flag, but that flag's current state couldn't be read from LaunchDarkly.",
}

# The one question each outcome turns on, so the report can point at it.
DECIDING = {
    "T-NS-1": "P1", "T-NS-2": "P2", "T-NS-3": "P3", "T-NS-4": "P4", "T-NS-5": "P21",
    "T-NS-6": "P22", "T-NS-7": "P23", "T-NS-8": "P26", "T-NS-9": "P25", "T-NS-10": "P21",
    "T-NS-11": "P31",
    "T-AF-1": "P5", "T-AF-2": "P8", "T-AF-3": "P6", "T-AF-4": "P33", "T-RE-1": "P12", "T-RE-2": "P32",
    "T-SG-1": "P13", "T-SG-3": "P15",
    "T-SG-6": "P18", "T-SG-7": "P19", "T-SG-8": "P20", "T-SG-10": "P27", "T-SG-12": "P30",
}
SIGNALS = ("P15", "P18", "P19", "P20", "P27", "P30")

# Each reason-for-a-flag question, as a reason. The walk stops at the first
# one that fires; the skill answers them all, so the report can list every
# reason the change gives, not only the one that decided it.
REASON = {
    "P15": "It adds something new customers can reach, like a page, endpoint, or flow.",
    "P18": "It shows users an announcement, banner, or message they didn't ask for.",
    "P19": "It changes an API that other apps or services rely on.",
    "P20": "It changes a default, or how an existing screen works, for users who didn't opt in.",
    "P27": "It adds work to a path all customer traffic goes through.",
    "P30": "It changes a path customers already use in a way that could fail them.",
}

# What kind of flag each "suggested" outcome calls for.
FLAG_KIND = {
    "T-SG-1": "Its own boolean release flag, off by default, rather than reusing the existing one, since this ships on its own schedule.",
    "T-SG-3": "A boolean release flag, off by default, so the new page, endpoint, or flow can't be reached until you turn it on.",
    "T-SG-6": "A boolean release flag, off by default, so the announcement doesn't show until you turn it on.",
    "T-SG-7": "A boolean release flag, checked on the server and off by default, so clients keep getting today's response until you turn it on.",
    "T-SG-8": "A boolean release flag, off by default, so users keep today's behavior until you turn it on.",
    "T-SG-9": "Optional: a boolean release flag, off by default, if an off switch is worth having for this change.",
    "T-SG-10": "A kill switch: a boolean operational flag you can turn off instantly if the new work slows down or breaks that path.",
    "T-SG-12": "A kill switch: a boolean operational flag, off by default or ready to turn off, that restores today's behavior on that path.",
}

# What comparing flag-on with flag-off can show, by the kind of change.
MEASURE = {
    "T-SG-3": "With the flag off, users can't reach the new thing at all, so a rollout can compare usage and errors of the surrounding flow; the new thing itself needs its own usage events.",
    "T-SG-6": "With the flag off, users see nothing extra, so a rollout can only compare overall use of the page unless the announcement records its own events.",
    "T-SG-7": "Compare error rates and client failures on the changed API between traffic with the flag on and off.",
    "T-SG-8": "Compare how users behave with the old and new behavior: how often they switch back, and whether they still finish the affected flow.",
    "T-SG-10": "Watch latency and error rates on that path as you ramp up. A guarded rollout can roll back on its own if they get worse.",
    "T-SG-12": "Compare error rates, latency and failed requests on that path between flag on and off. A guarded rollout can roll back on its own if they get worse.",
}
ADDITIVE = {"T-SG-3", "T-SG-6"}
TRACK_CALL = re.compile(r"\b(track[A-Z]\w*)\s*\(")

SOFT_OUTCOMES = {"T-NS-9", "T-NS-10", "T-NS-11", "T-SG-9"}  # the "worth a reviewer's look" endings
LD_KEY = re.compile(r"\b([a-z0-9][a-z0-9._-]*)@")


DEFAULT_FLAG_KIND = ("A boolean release flag, off by default, so users keep today's behavior "
                     "until you turn it on.")


def flag_kind(outcome, stated=None):
    """The flag to add: the outcome's boolean one, or the multivariate flag
    the author asked for (`stated`, the manifest's `flag_type`), whose off
    variation is today's behavior as the boolean's off is."""
    base = FLAG_KIND.get(outcome, DEFAULT_FLAG_KIND)
    if not stated:
        return base
    vt = stated.get("value_type")
    kind = (f"a multivariate ({vt}) flag" if vt else "a multivariate flag") + \
        (", as you asked" if stated.get("source") == "developer" else ", as the PR asks")
    if base.startswith("Optional:"):
        return f"Optional: {kind}, with today's behavior as its off variation, if an off switch is worth having for this change."
    text = (f"{kind[0].upper()}{kind[1:]}, with today's behavior as its off variation and its fallback value, "
            "so users keep today's behavior until you serve another variation.")
    return text + (" Turning it off is still your kill switch." if base.startswith("A kill switch") else "")


def load_tree():
    tree = specload.load(ODD_HOME / "tree.yaml")
    apply_spec_wording(tree)
    return tree


def apply_spec_wording(tree):
    """A tree other than ODD's (`wording: spec`) brings its own words: the
    tables above are ODD's, keyed by ODD's ids, and another tree's ids can
    collide with them. Questions from its predicates, reasons from its
    terminals, the deciding question from the node that reaches each
    terminal, and every reason-to-flag question from the nodes whose YES is
    a `suggested` terminal."""
    global SIGNALS, ADDITIVE, SOFT_OUTCOMES
    if tree.get("wording") != "spec" or tree.get("_wording_applied"):
        return
    preds = {p["id"]: p for p in specload.load(ODD_HOME / "predicates.yaml")["predicates"]}
    term = {x["id"]: x for x in tree["terminals"]}
    QUESTION.clear()
    QUESTION.update({k: " ".join(v["question"].split()) for k, v in preds.items()})
    QUESTION["U1"] = "Could the change be compared against the right starting point?"
    WHY.clear()
    WHY.update({k: " ".join(x["reason"].split()) for k, x in term.items()})
    WHY.update({e["id"]: " ".join(e.get("question_for_human", "").split()) for e in tree["escalations"]})
    DECIDING.clear()
    REASON.clear()
    signals = []
    for n in tree["nodes"]:
        for br in ("if_yes", "if_no"):
            if n[br] in term:
                DECIDING[n[br]] = n["predicate"]
        if n["if_yes"] in term and term[n["if_yes"]]["verdict"] == "suggested":
            signals.append(n["predicate"])
            REASON[n["predicate"]] = WHY[n["if_yes"]]
    SIGNALS = tuple(signals)
    FLAG_KIND.clear()
    MEASURE.clear()
    ADDITIVE = set()
    SOFT_OUTCOMES = {k for k, x in term.items() if x.get("ambiguous")}
    tree["_wording_applied"] = True


def check_coverage(tree):
    if tree.get("wording") == "spec":
        return  # its words come from the spec itself (apply_spec_wording)
    missing = sorted({n["predicate"] for n in tree["nodes"]} - set(QUESTION)
                     | {t["id"] for t in tree["terminals"]} - set(WHY)
                     | {e["id"] for e in tree["escalations"]} - set(WHY))
    if missing:
        raise SystemExit(f"explain.py has no plain wording for {missing}; update it before running the skill.")


def render(run):
    m = json.loads((run / "manifest.json").read_text())
    tree = load_tree()
    own = {n["predicate"] for n in tree["nodes"]}
    m["mechanical"] = {k: v for k, v in m["mechanical"].items() if k in own}
    packet = m["packet"] if isinstance(m["packet"], str) else json.dumps(m["packet"], indent=1)
    auto = "".join(
        f"{k} {QUESTION.get(k, '')} -> {answer_word(_value(v.get('value')))}"
        + (f" ({v['evidence']})" if v.get("evidence") else "")
        + (PROVISIONAL if k in ("P7", "P8", "P33") else "") + "\n"
        for k, v in m["mechanical"].items())
    (run / "evidence.txt").write_text(
        "=== RULES FOR ANSWERING\n" + str(m["instructions"])
        + "\n\n=== ALREADY ANSWERED AUTOMATICALLY (do not answer these; questions below may refer to them)\n"
        + auto + "\n=== EVIDENCE\n" + packet + "\n")
    qs, extra = m["questions"], report_questions()
    (run / "answering.txt").write_text(answer_rules())
    (run / "questions.txt").write_text(
        f"{len(qs)} questions" + (f", then {len(extra)} report-only" if extra else "")
        + ". Answer every one, each on its own, following its procedure.\n\n"
        "Write replies.json as {\"answers\": {\"<id>\": <answer>, ...}}.\n" + answer_rules()
        + "".join(f"\n\n######## {k}\n{v if isinstance(v, str) else json.dumps(v, indent=1)}" for k, v in qs.items()))
    if extra:
        with (run / "questions.txt").open("a") as f:
            f.write("\n\n" + "=" * 72 + "\nREPORT-ONLY QUESTIONS -- answer these too, the same way and in the same\n"
                    "replies.json. They go in the report and never change the result.\n")
            for q in extra:
                f.write(f"\n\n######## {q['id']}\n" + report_question_text(q))
    print(f"QUESTIONS: {len(qs) + len(extra)} to answer ({len(extra)} for the report only).")


# P7/P8/P33 are read before any question is answered, from flags checked near the
# change or by its callers; a YES to P5/P6 re-reads them from the flag that
# answer cites (merge_inline._reread_gates). Said, so the answerer doesn't
# take an unrelated flag for the change's gate.
PROVISIONAL = (" [read from flags found near the change before any answer; if your answers "
               "show the change behind a particular flag, this is re-read from that flag]")


def _value(v):
    return UNRESOLVED if v in (UNRESOLVED, "unresolved", None) else bool(v)


def askmod_behavior_set():
    from reader import ask as askmod
    return askmod.BEHAVIOR_SET_DESCRIPTION


def answer_rules():
    """How to write an answer: the rules every question shares."""
    return (
        "An answer is {\"value\": \"yes|no|unresolved\", \"evidence\": \"...\", "
        "\"citations\": [{\"path\": \"...\", \"line\": 1, \"why\": \"...\"}]}\n"
        "- Write `evidence` and each citation's `why` in plain words about the developer's code: "
        "the report quotes them word for word (WHY, REASONS, WHERE TO CHECK IT, and the "
        "recommend-flag block's reasons). Don't use the check's own terms there -- not "
        "\"merge_base\" (say \"the version on main\"), \"hunk\" (\"the changed code\"), "
        "\"behavior-carrying\", \"packet\", \"off arm\", or question ids like P5.\n"
        "- citations: a path and line the evidence shows. A deleted line is cited by its `old` "
        "number; a citation has no old/new field.\n"
        + (("- Name a flag key in backticks (`the-key`) whenever a procedure asks for the key: "
            "the report and the reuse key are read from it.\n")
           if load_tree().get("wording") == "spec" else
           ("- P2 also gives \"behavior_carrying\": [{\"path\": \"...\", \"line\": 1, \"why\": \"...\"}] -- "
            f"{askmod_behavior_set()}.\n"
            "- P10 and P12 also give \"reuse_keys\": [\"<key>\", ...] -- the key(s) a YES rests on, "
            "chosen only from the keys that question lists. Name only the key the YES actually rests on; "
            "name more than one only if each one alone would make it YES.\n"
            "- P6, on a YES that rests on more than one existing flag, also says how they combine: "
            "\"gates\": \"all\" when the change runs only when every one of them is on (one check "
            "inside another), \"gates\": \"any\" when any one of them alone reaches it (separate ways "
            "in), or, for a mix, \"gate_paths\": [[\"<key>\", ...], ...] -- one list per way in, holding "
            "the keys that must all be on for it. Leave them out for one flag, or when you can't tell.\n"
            "- P6, on a YES that rests on a flag that is not on/off (it serves a string, number or JSON "
            "value), also says which value(s) the changed code runs under: \"gate_values\": "
            "{\"<key>\": [\"<value>\", ...]}, each value as the code compares it, citing the line that "
            "compares it. Leave it out when every value reaches the change, or when you can't tell: the "
            "flag is then read as exposing whenever it is on.\n")) +
        "- A question that follows up on an earlier one (it says \"given\", or applies only when the "
        "earlier question is YES): if your answer to the earlier one is NO, answer NO and say "
        "\"not applicable: <earlier question> is no\". If it's unresolved, answer as if it were YES. "
        "It only counts when the earlier question is YES.\n"
        "- A question that works over a list it says is shown (reuse candidates, keys) when no such "
        "list is shown: answer NO, \"no candidates\".\n"
        "- A very large change doesn't all fit: the evidence marks every part it leaves out "
        "(\"[cut to fit: ...]\", listed in PACKET NOTES). What isn't shown isn't evidence: if a "
        "procedure needs it, answer by that procedure's rule for missing evidence.\n"
        "- If the PR description and the diff disagree, answer from the diff.\n")


def report_question_text(q):
    """A report-only question, rendered like a tree question."""
    return (f"QUESTION\n  {' '.join(q['question'].split())}\n\n"
            f"PROCEDURE\n{indent(q['procedure'])}\nUNRESOLVED-WHEN\n{indent(q['unresolved_when'])}\n"
            f"Answer only {q['id']}. Cite path and line from the packet.\n")


def indent(text):
    return "".join(f"  {l}\n" for l in text.rstrip().splitlines())


def report_questions():
    if load_tree().get("report_questions") == "none":
        return []
    try:
        return specload.load(SELF / "report_questions.yaml")
    except (OSError, ValueError):
        return []


SPLIT = {"partial", "cohort"}   # real users split between the flag's values in one environment
NOBODY = {"none", "internal"}   # no real user gets the true variation there
SERVED = {"all": "to every real user", "partial": "to part of its users",
          "cohort": "only to the users some rules or targets pick",
          "internal": "to no real user", "none": "to no real user"}
UNREAD = "unread"


def removed_flags_of(run, man: dict) -> list[dict]:
    """The manifest's removed flags with their state; a run started before
    `start` recorded them reads its saved packet instead."""
    if "removed_flags" in man:
        return man["removed_flags"] or []
    try:
        import pickle
        from reader.read import removed_flag_states
        return removed_flag_states(pickle.loads((run / "packet.pickle").read_bytes()))
    except Exception:  # noqa: BLE001 -- no packet, or one this build can't read: no caveat
        return []


def removed_flag_warnings(removed: list[dict], walked: set[str]) -> list[dict]:
    """The report-only caveat for a change that deletes every evaluation of a
    flag (in the changed files) that still serves different values to real
    users. It never moves the result.

    Shown only when the walk did not reach P32: a change that is only a flag
    removal (P3 YES) has P32 weigh exactly this, and a P32 YES keeps the flag.
    A larger change that also deletes a flag is judged on the rest (policy,
    2026-10-23); the caveat says who would lose what the flag served them.
    Read from the state of a boolean flag's true variation in each user-facing
    production environment: split when one environment serves it to some real
    users and not others, or when environments disagree (all in one, nobody in
    another). A flag that serves one value to every real user everywhere, an
    unread or non-boolean flag, and a flag still evaluated at head get none."""
    if "P32" in walked:
        return []
    out = []
    for r in removed:
        serves = r.get("serves") or {}
        if r.get("at_head") or not serves:
            continue
        # `unknown` (a prerequisite not followed or unreadable), or any class
        # this doesn't know, says nothing about a split: it doesn't count
        # toward one, and the note names it as unread.
        classes = set(serves.values()) & (SPLIT | NOBODY | {"all"})
        if not (classes & SPLIT or ("all" in classes and classes & NOBODY)):
            continue
        groups = {}
        for env, c in serves.items():
            groups.setdefault(SERVED.get(c, UNREAD), []).append(env)
        said = "; ".join((f"{' and '.join(envs)} couldn't be read" if who == UNREAD else
                          f"{' and '.join(envs)} {'serves' if len(envs) == 1 else 'serve'} its `true` value {who}")
                         for who, envs in groups.items())
        out.append({"flag": r["key"], "serves": serves,
                    "note": (f"This change deletes `{r['key']}` from the code, but the flag still serves different "
                             f"values to real users: {said}. Whichever behavior the change keeps, the users on the "
                             "other side get a different one once it ships. Keep the flag until it serves one value "
                             "everywhere, or confirm those users should change. This doesn't change the result.")})
    return out


def report_findings(run):
    """YES answers to the report-only questions whose citations check out
    (against the same citation context as every other answer)."""
    from reader import ask as askmod
    reps = json.loads((run / "replies.json").read_text()).get("answers", {}) \
        if (run / "replies.json").exists() else {}
    m = json.loads((run / "manifest.json").read_text())
    ctx = m.get("citation_context")
    out = []
    for q in report_questions():
        r = reps.get(q["id"]) or {}
        if str(r.get("value")).lower() not in ("yes", "true"):
            continue
        if ctx:
            ok, _ = askmod.check_citations(r.get("citations") or [], ctx,
                                           predicate_id=q["id"], value="yes")
            if not ok:
                continue
        out.append((q, str(r.get("evidence") or "")))
    return out


def answer_word(v):
    return "couldn't tell" if v is UNRESOLVED else ("yes" if v else "no")


EXPERIMENT_NOTE = ("No flag is needed, but if you want to A/B test this change (for example, the new "
                   "wording), you can add a flag on purpose to run an experiment.")
NON_ESSENTIAL = re.compile(r"\bnon-?essential\b", re.I)


def experiment_note_applies(outcome, vals, ev):
    """A not-suited result that rests on presentation or wording only (P22),
    or a change P20 found to only remove a non-essential extra."""
    return (outcome == "T-NS-6" or vals.get("P22") is True
            or (vals.get("P20") is False and bool(NON_ESSENTIAL.search(ev.get("P20") or ""))))


def removed_keys(run):
    """The flags this change deletes evaluations of (the manifest's
    removed_flag_keys, from the evidence's removed-flags section)."""
    return json.loads((run / "manifest.json").read_text()).get("removed_flag_keys") or []


def reuse_keys(run):
    m = json.loads((run / "manifest.json").read_text())
    packet = m["packet"] if isinstance(m["packet"], str) else ""
    block = packet.split("REUSE CANDIDATES", 1)[1].split("\n\n", 1)[0] if "REUSE CANDIDATES" in packet else ""
    return re.findall(r"^\s{2}([a-z0-9][a-z0-9._-]+)\s", block, re.M)


def packet_text(run):
    m = json.loads((run / "manifest.json").read_text())
    return m["packet"] if isinstance(m["packet"], str) else ""


def added_files(run):
    """Files this change creates (as opposed to edits): not present at the
    commit the change branched from."""
    m = json.loads((run / "manifest.json").read_text())
    repo_file, base = run / "repo_path", (m.get("unit") or {}).get("merge_base")
    if not repo_file.exists() or not base:
        return set()
    repo = repo_file.read_text().strip()
    return {p for p in m.get("changed_files", [])
            if subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{base}:{p}"],
                              capture_output=True).returncode != 0}


def added_tracking(run, paths):
    """Event-tracking calls on lines the change adds to the given files."""
    found, current = [], None
    for line in packet_text(run).splitlines():
        if line.startswith("--- "):
            current = line[4:].split(" [", 1)[0]
        elif current in paths and re.match(r"new\s+\d+ \| \+", line):
            found += [n for n in TRACK_CALL.findall(line) if n not in found]
    return found


def cited_paths(cites):
    return {c["path"] for c in cites or [] if c.get("path")}


def where_to_check(cites, new_files):
    """The code locations the deciding answer points at: where existing code
    places the new behavior first, then the new code itself."""
    seen, ranked = set(), []
    for i, c in enumerate(cites or []):
        path, line = c.get("path"), c.get("line")
        if not path or (path, line) in seen or "/__tests__/" in path or ".test." in path:
            continue
        seen.add((path, line))
        ranked.append((path in new_files, i, {"path": path, "line": line, **({"reason": c["why"]} if c.get("why") else {})}))
    return [r[2] for r in sorted(ranked, key=lambda r: r[:2])[:2]]


def spot_text(s):
    return f"{s['path'].rsplit('/', 1)[-1]}:{s['line']}" + (f" ({s['reason']})" if s.get("reason") else "")


def cite_text(cites):
    refs = [f"{c['path']}:{c['line']}" for c in cites or [] if c.get("path") and c.get("line")]
    return f" ({', '.join(refs[:3])})" if refs else ""


def decision_record(run):
    """The entry `classify.py decide` wrote for this run (FDG_HOME is the run folder)."""
    files = sorted((run / "ledger").glob("*.json"), key=lambda f: f.stat().st_mtime)
    return json.loads(files[-1].read_text()) if files else {}


def gate_key(doc, run, outcome):
    """The flag an already-flagged change sits behind. T-AF-1 is decided by
    P5 alone, so it's the flag this change wires itself (the one P5's
    evidence names, when it wires several); the tree reads no LaunchDarkly
    state there. T-AF-2's is the ancestor gate whose state P8 read; T-AF-4's
    the one P33 found still holding the change back in main production (the
    first of its `holding_keys`, else the first key its evidence names)."""
    tree = load_tree()
    if tree.get("gate_key_from"):
        from classify import answer_key
        pid = tree["gate_key_from"].get(outcome)
        return answer_key(doc.get(pid)) if pid else None
    if outcome == "T-AF-1":
        wired = json.loads((run / "manifest.json").read_text()).get("diff_wired_keys") or []
        said = (doc.get("P5") or {}).get("evidence") or ""
        from reader.mechanical import names_key  # whole keys only: not `banner` inside `banner-v2`
        named = [k for k in wired if names_key(said, k)]
        return named[0] if len(named) == 1 else wired[0] if len(wired) == 1 else None
    if outcome == "T-AF-4":
        held = (doc.get("P33") or {}).get("holding_keys") or []
        keys = held or LD_KEY.findall((doc.get("P33") or {}).get("evidence") or "")
        return keys[0] if keys else None
    keys = LD_KEY.findall((doc.get("P8") or {}).get("evidence") or "")
    return keys[0] if keys else None


REVIEW_SCHEMA = "should-i-flag-record/1"
SEARCH_FILES = ("gates", "risks", "consumers", "features", "facts")


def review_record(run, record, doc):
    """A compact, replayable record of this decision: the graph it ran on, the
    commits it read, every answer with where it came from, and the walk. It is
    the decision-record entry without the evidence text, so it fits in a tool
    result and a transcript keeps it even when the run folder is gone; a
    replay re-walks `answers` against any graph."""
    tree = record.get("tree") or {}
    word = {True: "yes", False: "no"}
    answers = {}
    for pid, v in (record.get("predicates") or {}).items():
        a = doc.get(pid) or {}
        answers[pid] = {"value": word.get(v, "unresolved"), "basis": a.get("basis") or "answered"}
    searches = {}
    for name in SEARCH_FILES:
        f = run / f"{name}-verified.json"
        if f.is_file():
            data = json.loads(f.read_text())
            count = lambda d: {k: len(v) for k, v in d.items() if isinstance(v, list)}  # noqa: E731
            # facts-verified.json is keyed by question, one search each
            searches[name] = ({pid: count(d) for pid, d in data.items() if isinstance(d, dict)}
                              if name == "facts" else count(data))
    out = {"schema": REVIEW_SCHEMA, "graph_hash": record.get("graph_hash"),
           "graph_version": record.get("graph_version"), "recorded_at": record.get("recorded_at"),
           "pr": record.get("pr"), "profile": record.get("profile"), "unit": record.get("unit"),
           "answers": answers,
           "walk": [[s.get("node"), s.get("predicate"), s.get("answer")] for s in tree.get("walk") or []],
           "terminal": tree.get("terminal"), "verdict": tree.get("verdict"),
           "over_determined": tree.get("over_determined"),
           "decided_by_closed_world": bool(record.get("decided_by_closed_world")),
           "searches": searches}
    (run / "review-record.json").write_text(json.dumps(out, indent=1) + "\n")
    print("REVIEW RECORD (for later review; don't pass it on to the developer):")
    print("```json should-i-flag-record")
    print(json.dumps(out, separators=(",", ":")))
    print("```")


def emit_recommendation(run, rec):
    (run / "recommend-flag.json").write_text(json.dumps(rec, indent=2) + "\n")
    print("RECOMMEND-FLAG:")
    print("```json recommend-flag")
    print(json.dumps(rec, indent=2))
    print("```")


def next_steps(run):
    profile = json.loads((run / "manifest.json").read_text()).get("profile", "")
    steps = specload.load(SELF / "next_steps.yaml")
    return steps.get(profile) or steps["default"]


CODE_EXT = (".ts", ".tsx", ".js", ".jsx", ".go", ".py")
MAX_NEIGHBORS_PER_DIR = 60


def name_words(path):
    """Words in a file name, for ranking similar neighbors: `DatabaseQueriesBanner.tsx` -> {database, queries, banner}."""
    stem = Path(path).name.split(".", 1)[0]
    return {w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", stem) if len(w) > 2}


def is_test(path):
    return any(t in path for t in ("/__tests__/", ".test.", "-test.", "_test.go", "/tests/", "/testdata/"))


def neighbors(run):
    """Flags already checked in the other files of each changed file's
    folder, as of the commit the change branched from. Mechanical: the same
    flag-site finder the check uses, over files the check didn't read."""
    from reader.mechanical import flag_sites
    from reader.sources import Profile, Repo, build_symbol_table

    m = json.loads((run / "manifest.json").read_text())
    base = (m.get("unit") or {}).get("merge_base")
    repo_path = (run / "repo_path").read_text().strip()
    changed = [p for p in m.get("changed_files", []) if not is_test(p)]
    out = {}
    if base and changed:
        repo = Repo(Path(repo_path))
        profile = (Profile.from_file(m["profile_file"]) if m.get("profile_file")
                   else Profile.load(m["profile"]))
        files = []
        for d in sorted({str(Path(p).parent) for p in changed}):
            names = repo.git("ls-tree", "--name-only", base, "--", d.rstrip("/") + "/", check=False).splitlines()
            names = [n for n in names if n.endswith(CODE_EXT) and not is_test(n) and n not in changed]
            if len(names) <= MAX_NEIGHBORS_PER_DIR:
                files += names
        if files:
            st = build_symbol_table(repo, profile, base)
            for s in flag_sites(repo, profile, st, base, files, _siblings=False):
                if s.get("key"):
                    keys = out.setdefault(s["path"], [])
                    if s["key"] not in keys:
                        keys.append(s["key"])
    (run / "neighbors.json").write_text(json.dumps(out, indent=1))
    print(f"NEARBY: {len(out)} neighboring file(s) already use flags.")


def feature_flags(run):
    """Flags already used right around the changed code: the ones the check
    found evaluated next to the changed lines (its reuse candidates). These
    are this feature's flags, unlike a same-folder file that only shares a
    name (an earlier PR: `schema.resolvers.go` checking an unrelated
    batch-size flag outranked the session-fields flags beside the change).
    Gates further up the call chain are left out: a file that renders the
    changed code can gate something else entirely (the banner test branch:
    DashboardContent.tsx's gate is for the service-map dashboard)."""
    m = json.loads((run / "manifest.json").read_text())
    packet = m["packet"] if isinstance(m["packet"], str) else ""
    out = {}
    block = packet.split("REUSE CANDIDATES", 1)[1].split("\n\n", 1)[0] if "REUSE CANDIDATES" in packet else ""
    for key, path in re.findall(r"^\s{2}([a-z0-9][a-z0-9._-]+)\s+evaluated at (\S+?):\d+", block, re.M):
        out.setdefault(path, []).append(key)
    return out


def _boolean_flag(flag):
    """True / False when a flag file says whether the flag is boolean (every
    variation true or false, or its kind); None when it can't tell (a 404,
    or a file with neither)."""
    vals = [v.get("value") for v in flag.get("variations") or [] if isinstance(v, dict)]
    if vals:
        return all(isinstance(v, bool) for v in vals)
    return flag["kind"] == "boolean" if flag.get("kind") else None


def _declared_boolean(pkt, key):
    """The change declares `key` with a true/false default: the symbol table
    read one, or a line the diff adds gives the key then a boolean
    (`createFlagFunction('k', false)`, `ld:"k,false"`, `k: false`)."""
    if key in ((getattr(pkt, "ld_setup", None) or {}).get("defaults") or {}):
        return True
    rx = re.compile(rf"""(?<![\w.-]){re.escape(key)}(?![\w.-])["'`]?\s*[,:=]\s*(?:true|false)\b""")
    return any(rx.search(raw[1:]) for h in getattr(pkt, "hunks", None) or []
               for raw in h.text.splitlines() if raw.startswith("+"))


def own_flags(run):
    """The flags this change adds and checks in its changed code that can
    switch a part off, each with whether LaunchDarkly has it yet ({key:
    True | False | None}, None when not read). A suggestion that names no key
    gets a key made up beside the PR's own (an earlier PR: `...-errors-
    table-page` proposed next to the PR's `...-errors-table-view`).

    All from the run: the diff adds the key; a changed file evaluates it at
    head (a declaration alone gates nothing); and it is boolean, by its flag
    file's variations when LaunchDarkly has it, else by the default the
    change declares. A settings flag that picks a value is no off switch, so
    a part outside it gets a flag of its own (an earlier PR later added
    one)."""
    import pickle
    from reader.sources import from_tool_shape
    try:
        pkt = pickle.loads((run / "packet.pickle").read_bytes())
    except Exception:  # noqa: BLE001 -- no packet, no claim about the PR's flags
        return {}
    evaluated = {s.get("key") for s in getattr(pkt, "flag_sites_head", None) or []}
    files ={f.name.split("__", 1)[-1][:-5]: f for f in (run / "launchdarkly").glob("*__*.json")} \
        if (run / "launchdarkly").is_dir() else {}
    out = {}
    for k in getattr(pkt, "keys_added_by_diff", None) or []:
        if k not in evaluated:
            continue
        try:
            # As the agent wrote it, maybe in the MCP tool's shape (values
            # on each environment, often bare booleans, no `kind`)
            flag = from_tool_shape(json.loads(files[k].read_text())) if k in files else {}
        except (OSError, ValueError):
            flag = {}
        boolean = None if flag.get("not_found") else _boolean_flag(flag)
        if boolean is False or (boolean is None and not _declared_boolean(pkt, k)):
            continue
        out[k] = False if flag.get("not_found") else True if flag.get("key") else None
    return out


def stated_flag_type(run):
    """The type of flag the author asked for (should-i-flag start's FLAG TYPE), or
    None. "multivariate" in the PR text alone doesn't count when the change
    adds and checks a flag of its own that isn't a boolean switch: the word
    then most likely describes that flag, not the one to add."""
    try:
        stated = json.loads((run / "manifest.json").read_text()).get("flag_type")
    except (OSError, ValueError):
        return None
    if not stated or stated.get("source") == "developer":
        return stated or None
    import pickle
    try:
        pkt = pickle.loads((run / "packet.pickle").read_bytes())
    except Exception:  # noqa: BLE001 -- no packet, no claim about the PR's flags
        return stated
    evaluated = {s.get("key") for s in getattr(pkt, "flag_sites_head", None) or []}
    added = {k for k in getattr(pkt, "keys_added_by_diff", None) or [] if k in evaluated}
    return None if added - set(own_flags(run)) else stated


def nearby_flags_line(run):
    """The report's consistency note: this feature's own flags when it has
    any, otherwise flags in same-folder files, most similarly named first."""
    def fmt(items):
        return "; ".join(f"{p.rsplit('/', 1)[-1]} checks {', '.join(f'`{k}`' for k in ks[:2])}"
                         + (f" (and {len(ks) - 2} more)" if len(ks) > 2 else "") for p, ks in items[:3])
    feat = feature_flags(run)
    if feat:
        return (f"the code around this change already uses flags: {fmt(sorted(feat.items()))}. "
                "Adding one here would be consistent with it.")
    near = json.loads((run / "neighbors.json").read_text()) if (run / "neighbors.json").exists() else {}
    if not near:
        return None
    changed = json.loads((run / "manifest.json").read_text()).get("changed_files", [])
    mine = {w for p in changed for w in name_words(p)}
    # Names of files the change creates count double: a new component is
    # most like its siblings (DatabaseQueriesBanner -> AgentControlProductBanner),
    # not like whatever shares the folder's generic word ("Dashboard").
    created = {w for p in added_files(run) if not is_test(p) for w in name_words(p)}
    by_key = {}  # one entry per flag, with the files that check it, most similar first
    for path, keys in near.items():
        for k in keys:
            by_key.setdefault(k, []).append(path)
    sim = lambda path: len(mine & name_words(path)) + len(created & name_words(path))
    ranked = sorted(by_key.items(), key=lambda kv: (-max(sim(p) for p in kv[1]), -len(kv[1]), kv[0]))
    def one(k, paths):
        paths = sorted(paths, key=lambda p: (-sim(p), p))
        names = ", ".join(p.rsplit("/", 1)[-1] for p in paths[:2]) + (f" and {len(paths) - 2} more" if len(paths) > 2 else "")
        return f"`{k}` ({names})"
    more = f", and {len(ranked) - 3} other flag(s)" if len(ranked) > 3 else ""
    return (f"other code in the same folder already uses flags: {'; '.join(one(k, ps) for k, ps in ranked[:3])}{more}. "
            "Adding one here would be consistent with it.")


def explain(run):
    tree = load_tree()
    check_coverage(tree)
    doc = json.loads((run / "answers.json").read_text())["answers"]
    vals, ev, basis = {}, {}, {}
    for pid, a in doc.items():
        v = a.get("value") if isinstance(a, dict) else a
        vals[pid] = UNRESOLVED if v in (UNRESOLVED, "UNRESOLVED", "unresolved", None) else bool(v)
        ev[pid] = (a.get("evidence") or "") if isinstance(a, dict) else ""
        basis[pid] = a.get("basis", "") if isinstance(a, dict) else ""
    steps, outcome, verdict, od = resolve_tree(tree, vals)

    key = None
    if outcome.startswith("E-UNRESOLVED@"):
        key = steps[-1]["predicate"]
        why = f"The check couldn't answer this with confidence: \"{QUESTION[key]}\""
    else:
        why = WHY.get(outcome, "")
        key = DECIDING.get(outcome)
        if outcome == "T-SG-9" and tree.get("wording") != "spec":
            key = next((s["predicate"] for s in steps if s["predicate"] in SIGNALS and s["answer"] == "Y"), None)

    headline = HEADLINE["escalate" if verdict == "escalate" else verdict]
    key_, ordered, spots, measure, findings = None, [], [], None, report_findings(run)
    # One flag the change adds and checks itself: name it rather than ask for a new one.
    own = own_flags(run) if verdict == "suggested" else {}
    own_key = next(iter(own)) if len(own) == 1 else None
    stated = stated_flag_type(run) if verdict == "suggested" and not own_key else None
    if own_key:
        headline = f"Suggested: put the rest of this change behind `{own_key}`, the flag it already adds."
    if verdict == "reuse-existing":
        # The reuse layer settles on ONE key (P11's still-withheld keys that
        # P10 and P12 also hold for), recorded as reuse_flag_key; the packet's
        # REUSE CANDIDATES list is only the fallback for answers from before
        # key scoping, and names a flag only when there is a single candidate.
        key_, _note = reuse_flag_key(doc, tree, outcome)
        if key_ is None:
            keys = removed_keys(run) if outcome == "T-RE-2" else reuse_keys(run)
            key_ = keys[0] if len(keys) == 1 else None
        if key_ and outcome == "T-RE-2":
            headline = f"Keep the flag `{key_}` for now: some real customers still get the behavior this change deletes."
        elif key_:
            headline = f"Reuse the existing flag `{key_}` rather than adding a new one."

    print(f"RESULT: {headline}")
    print(f"WHY: {why}")
    if key:
        auto = basis.get(key) in ("git", "ld-api", "profile-path-roles", "symbol-table@merge_base", "flag-site-scan")
        detail = "" if auto or not ev.get(key) else f" {ev[key]}"
        print(f"DECIDING QUESTION: {QUESTION[key]} -> {answer_word(vals.get(key, UNRESOLVED))}.{detail}")
    unclear = (od or {}).get("unresolved") or []
    if unclear:
        print("UNCLEAR, BUT IT DIDN'T MATTER: " + "; ".join(f'"{QUESTION[p]}"' for p in unclear)
              + (" -- the check couldn't answer this, but " if len(unclear) == 1 else
                 " -- the check couldn't answer these, but ")
              + "every possible answer leads to the same result.")

    if verdict == "suggested":
        reasons = [p for p in SIGNALS if vals.get(p) is True
                   and not (p == "P27" and vals.get("P28") is True)]  # contained load is no reason
        ordered = ([key] if key in reasons else []) + [p for p in reasons if p != key]
        extra = findings
        if ordered or extra:
            print("REASONS FOR A FLAG:")
            for p in ordered:
                note = (f" {ev[p]}" if p != key and ev.get(p)
                        and basis.get(p, "").startswith("inline") else "")  # the deciding one's is above
                print(f"  - {REASON[p]}{' (the deciding one)' if p == key else ''}{note}")
            for q, e in extra:
                print(f"  - {q['reason']} {e}".rstrip())
        if own_key:
            print(f"FLAG TO ADD: none new. This change already adds and checks `{own_key}`: put the parts it "
                  f"doesn't cover behind `{own_key}` too, unless the PR says they ship on their own schedule.")
        else:
            print(f"FLAG TO ADD: {flag_kind(outcome, stated)}")
        cites = doc.get(key, {}).get("citations") if key else None
        spots = where_to_check(cites, added_files(run))
        if spots:
            print("WHERE TO CHECK IT: at or around " + "; ".join(spot_text(s) for s in spots))
        measure = MEASURE.get(outcome, "Compare users with the flag on and off on whatever the change affects.")
        if outcome in ADDITIVE:
            tracked = added_tracking(run, cited_paths(cites))
            measure += (f" The change already records: {', '.join(tracked)}." if tracked else
                        " The change records no events of its own, so add view, click, and dismiss tracking if you want the rollout to measure it.")
        print(f"WHAT A ROLLOUT CAN MEASURE: {measure}")
        line = nearby_flags_line(run)
        if line:
            print(f"NEARBY FLAGS: {line}")
        print("NEXT STEPS:")
        # The repo's steps say to plan and create a flag; with the change's
        # own flag there is none to create, only checks to add.
        todo = ([f"Create `{own_key}` in LaunchDarkly, off in every environment, before this ships: "
                  "the code already checks it."] if own_key and own[own_key] is False else []) + (
            [f"Put the parts `{own_key}` doesn't cover yet behind it, where the check names above, "
             f"then roll `{own_key}` out when you're ready."] if own_key else next_steps(run))
        for s in todo:
            print(f"  - {s}")
    elif verdict == "reuse-existing" and outcome == "T-RE-2":
        print("NEXT STEPS:")
        print("  - Keep the flag" + (f" `{key_}`" if key_ else "") + " and its checks in the code for now. Finish its "
              "rollout in LaunchDarkly until every real customer gets the behavior you're keeping, then remove it.")
    elif verdict == "reuse-existing":
        print("NEXT STEPS:")
        print("  - Put the change behind the existing flag named above instead of adding a new one.")
    elif verdict == "already-flagged" and outcome == "T-AF-4":
        gk = gate_key(doc, run, outcome)
        print("NEXT STEPS:")
        print("  - Nothing to add. This change rolls out with the flag" + (f" `{gk}`" if gk else "")
              + ": widen its rollout when you're ready, or turn it off if this part misbehaves.")
    elif verdict == "already-flagged":
        print("NEXT STEPS:")
        print("  - Nothing to add. Keep the flag off for real users until you're ready to release.")
    elif verdict == "not-suited" and experiment_note_applies(outcome, vals, ev):
        print("NEXT STEPS:")
        print(f"  - {EXPERIMENT_NOTE}")
    elif verdict == "escalate":
        print("NEXT STEPS:")
        print("  - Ask a reviewer to answer the question above, or add detail to the PR that settles it, and run the check again.")
    if verdict != "suggested":
        for q, e in findings:
            print(f"WORTH A LOOK: {q['reason']} {e} This doesn't change the result, "
                  "but a flag could still help you roll it out carefully.")
    print("ALSO CHECKED:")
    for s in steps:
        if s["predicate"] == key or s["predicate"] in unclear:
            continue
        print(f"  - {QUESTION[s['predicate']]} {answer_word(vals.get(s['predicate'], UNRESOLVED))}")
    man_ = json.loads((run / "manifest.json").read_text())
    env = man_.get("launchdarkly_environments") or {}
    on_pr = str(man_.get("pr") or "").startswith("http")
    # --no-launchdarkly: no flag's state was read anywhere, so no note about
    # which environments it was read in (EMSR-2642).
    ld_off = man_.get("launchdarkly") == "off"
    # deferred: no flag needed reading, so no flag's state went into the answers
    no_flag_read = ld_off or env.get("source") == "deferred"
    env_note = ""
    if ld_off:
        env_note = " LaunchDarkly wasn't read (--no-launchdarkly), so no flag's state was checked."
    elif env and not env.get("critical") and not no_flag_read:
        env_note = (" Flag state was read in `production` only: the LaunchDarkly project's environments "
                    "couldn't be listed, or none is marked critical, so other production environments "
                    "weren't checked.")
    removals = removed_flag_warnings(removed_flags_of(run, man_), {s["predicate"] for s in steps})
    for w in removals:
        print(f"FLAG REMOVAL: {w['note']}")
    if on_pr:
        # A review of the PR itself: there's no later check to defer to.
        print("CAVEAT: each question was answered once, from the code at this commit"
              + ("" if no_flag_read else " and the flags' state in LaunchDarkly today")
              + "; a reviewer who reads the change differently can overrule the result." + env_note)
    else:
        print("CAVEAT: a quick heads-up, not the final word. Each question was answered once, in this session; "
              "the check that runs on an opened PR answers them again on its own and can come out differently."
              + env_note)

    # The same result for tools, every reason with the evidence behind it.
    reasons = []

    def add(text, pid=None):
        e = re.sub(r"^P\d+:\s*", "", ev.get(pid, "") if pid else "").strip()
        cites = (doc.get(pid) or {}).get("citations") if pid else None
        reasons.append(" ".join(x for x in (text, e) if x) + cite_text(cites))

    add(why, key or ("P7" if outcome == "E-STATE" else None))
    if tree.get("gate_key_from"):
        if outcome in tree["gate_key_from"] and tree["gate_key_from"][outcome] != key:
            add("Where the existing flag covers it:", tree["gate_key_from"][outcome])
    elif outcome in ("T-AF-2", "T-AF-3", "T-AF-4"):  # T-AF-1 is P5 alone; the tree reads no flag state there
        add("Where the existing flag covers it:", "P6")
    for p in ordered:
        if p != key:
            add(REASON[p], p)
    for q, e in findings:
        reasons.append(" ".join(x for x in (q["reason"] if verdict == "suggested" else f"Worth a look: {q['reason']}", e) if x))
    for p in unclear:
        reasons.append(f"Couldn't settle \"{QUESTION[p]}\", but every possible answer leads to the same result.")

    record = decision_record(run)
    shown = "suggested" if verdict == "escalate" else verdict
    rec = {"recommend": tree["verdicts"][shown]["recommend"], "verdict": shown}
    if verdict == "reuse-existing" and key_:
        rec["reuse_flag_key"] = key_
    rec["confidence"] = ("low" if verdict == "escalate" else
                         "medium" if unclear or record.get("decided_by_closed_world") or outcome in SOFT_OUTCOMES
                         else "high")
    rec["reasons"] = reasons
    rec["needs_human"] = verdict == "escalate"
    if verdict == "escalate":
        rec["question_for_human"] = QUESTION[key] if key else why
    existing = key_ if verdict == "reuse-existing" else gate_key(doc, run, outcome) if verdict == "already-flagged" else None
    if existing:
        rec["existing_flag_key"] = existing
    if verdict == "suggested":
        rec["flag_to_add"] = {"kind": flag_kind(outcome, stated),
                              "type": stated["type"] if stated else "boolean"}
        if stated:
            rec["flag_to_add"]["type_source"] = stated.get("source")
            if stated.get("value_type"):
                rec["flag_to_add"]["value_type"] = stated["value_type"]
        if own_key:
            rec["flag_to_add"] = {"key": own_key, "extend_existing": True,
                                  "kind": f"The flag this change already adds, `{own_key}`: put the parts it "
                                          "doesn't cover behind it too, unless the PR says they ship on their own schedule."}
        if spots:
            rec["where_to_check"] = spots
        rec["rollout_measure"] = measure
    if removals:
        rec["flag_removal_warnings"] = [{"flag": w["flag"], "serves": w["serves"], "note": w["note"]}
                                        for w in removals]
    rec["decided_by_closed_world"] = bool(record.get("decided_by_closed_world"))
    if record.get("graph_hash"):
        rec["graph_hash"] = record["graph_hash"]
    if record:
        review_record(run, record, doc)
    emit_recommendation(run, rec)


if __name__ == "__main__":
    cmd, run = sys.argv[1], Path(sys.argv[2])
    {"render": render, "neighbors": neighbors, "explain": explain}[cmd](run)
