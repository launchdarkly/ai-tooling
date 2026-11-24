#!/usr/bin/env python3
"""The evidence and the questions: renders the evidence packet the answers
are given on, each question with its context, and checks every citation an
answer makes against what was shown.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import specload

from .sources import CITES_GATE_FILES_EXTRA, GATE_DEPENDENT_PREDICATES
from .sources import verify_citations as verify_citation_set

GRAPH = Path(__file__).parent.parent
UNRESOLVED = "UNRESOLVED"

MODEL = "claude-opus-5-5"        # fallback when no tier is configured
EFFORT = "medium"
SAMPLES = 3
DEFAULT_MAX_TOKENS = 2048        # per-predicate override: model_tiers.yaml

# USD per million tokens. Cache writes bill at ~1.25x input. Cache reads bill at
# ~0.1x input unless a model lists its own `cache_read` rate: Opus 5.5's is
# $0.20/MTok, 0.05x its input price (Anthropic model reference, 2026-09-25).
PRICES = {
    "claude-opus-5-5": {"in": 4.00, "out": 20.00, "cache_read": 0.20},
    "claude-opus-5":   {"in": 5.00, "out": 25.00},
    "claude-sonnet-5": {"in": 2.00, "out": 10.00},
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00},
}


UNPRICED: set[str] = set()
"""Models a request ran on that PRICES has no entry for: their cost counts as
0 in the totals, so read.py says so instead of reporting a false $0."""


# Models that take neither `output_config.effort` nor adaptive thinking.
# Sending either is a 400, so this is a correctness table, not a preference.
NO_EFFORT_MODELS = {"claude-haiku-4-5"}


# The predicate whose answer DEFINES "behavior-carrying hunk" for every later
# predicate (P2's procedure: "Record the set of hunks that answer YES").
BEHAVIOR_SET_PREDICATE = "P2"
BEHAVIOR_SET_DESCRIPTION = (
    "every changed hunk that alters runtime behavior, one entry per hunk, "
    "cited at one of its changed lines -- the set later predicates will "
    "treat as 'behavior-carrying'. Only hunks that themselves change "
    "behavior: not a call site, helper, or refactor you cite as context")

# The predicates whose YES must name the reuse key(s) it rests on
# (mechanical.REUSE_KEY_PREDICATES; predicates.yaml's reuse layer is about ONE
# key).
REUSE_KEY_PREDICATES = ("P10", "P12")
REUSE_KEYS_DESCRIPTION = (
    "ONLY for a question that asks you to name qualifying REUSE CANDIDATES: "
    "the candidate key(s) your YES rests on, chosen from the keys that "
    "question lists. Leave empty for every other question")

# The predicate whose YES says how its enclosing flags combine
# (mechanical.GATE_COMBINATION_PREDICATES; predicates.yaml P6). Read by P8's
# per-path reading (mechanical.gate_paths_of). Not a citation.
GATE_COMBINATION_PREDICATE = "P6"
GATES_DESCRIPTION = (
    "ONLY for the question that asks how its enclosing flags combine, on a "
    "YES that rests on more than one: \"all\" when the change runs only when "
    "every cited enclosing flag is on (nested gates), \"any\" when any one "
    "of them alone reaches it (alternative ways in). Leave empty otherwise, "
    "or when the ways in are a mix (use gate_paths)")
GATE_PATHS_DESCRIPTION = (
    "ONLY for that same question, when the ways in are a mix: one list per "
    "path to the change, each holding the flag keys that must ALL be on for "
    "that path, e.g. [[\"outer\", \"page-a\"], [\"outer\", \"page-b\"]]. "
    "Leave empty otherwise")

GATE_VALUES_DESCRIPTION = (
    "ONLY for that same question, on a YES resting on a flag that serves a "
    "string, number or JSON value rather than on/off: per such flag, the "
    "value(s) the changed code runs under, as the code compares them, e.g. "
    "[{\"key\": \"model-provider\", \"values\": [\"coralbricks\"]}]. Leave "
    "empty otherwise, or when every value reaches the changed code")


def gate_values_field(gv) -> dict[str, list] | None:
    """The schema's `gate_values` (a list of {key, values}) as the map P6's
    YES records, `{key: [value, ...]}`; None when it names nothing."""
    if isinstance(gv, list):
        gv = {x["key"]: list(x["values"]) for x in gv
              if isinstance(x, dict) and x.get("key") and x.get("values")}
    return gv or None if isinstance(gv, dict) else None


# Bumped when a predicate's answer SCHEMA changes, so answers cached under
# the old schema are not reused as if they had the new fields (read.py puts
# the tag in the cache filename, via schema_tag).
SCHEMA_TAGS = {BEHAVIOR_SET_PREDICATE: "set1", "P10": "keys1", "P12": "keys1"}
# Not bumped for P6's `gates` / `gate_paths` / `gate_values`: an answer without them keeps
# its meaning (the flags read as alternative ways in, mechanical.gate_paths_of),
# so a cached P6 stays valid; re-ask it to learn how its flags combine.
# Every predicate's request now carries ONE shared schema per packet (see
# shared_answer_model), so every cached answer predates it.
SHARED_SCHEMA_TAG = "shared1"


def citable_note(pkt, pid: str) -> str | None:
    """Which files `pid` may cite, when the shared schema offers more: the
    referenced files and caller windows are shown for the gate predicates
    only, and a citation of one from any other predicate is rejected."""
    changed = {f["path"] for f in pkt.files}
    barred = set()
    if pid not in GATE_DEPENDENT_PREDICATES | CITES_GATE_FILES_EXTRA:
        barred |= {rc["path"] for rc in (getattr(pkt, "referenced_context", None) or [])}
    if pid not in CALLER_GATE_PREDICATES:
        barred |= {w["path"] for w in caller_gate_windows(pkt)}
    if pid not in FEATURE_CITING_PREDICATES:
        barred |= {w["path"] for w in feature_windows(pkt)}
    barred -= changed
    if not barred:
        return None
    return ("CITABLE FILES FOR THIS QUESTION: these are shown for other "
            "questions and may not be cited here: " + ", ".join(sorted(barred))
            + ".")


SYSTEM = """\
You answer ONE yes/no question about a code change, by following a written \
procedure exactly.

Rules that override any instinct about the change:

1. Follow the PROCEDURE as written. Do not substitute your own judgment about \
whether the change is risky, important, or well-made. You are not deciding \
anything about feature flags; another system does that from your answer.
2. Answer "unresolved" when the procedure's UNRESOLVED-WHEN condition holds, \
or when the packet does not contain what the procedure requires. "unresolved" \
is a correct, expected answer -- it routes the change to a human. Guessing is \
worse than abstaining. Exception: when the PROCEDURE itself says what the \
absence of evidence means (e.g. "absence ... is NO"), follow the procedure.
3. Every claim must cite a path and line either from the diff itself, or \
from a file explicitly shown under REFERENCED FILES, or -- when the question \
shows them -- from the GATES ABOVE CHANGED CODE windows, the FEATURE FLAG SEARCH \
lines or the FACT SEARCH FINDINGS. Every shown line has its \
number printed at the left: cite that number (a deleted diff line is marked \
`old`; cite its old number). REFERENCED FILES are NOT \
part of the diff and may be cited ONLY when answering """ + \
    ", ".join(sorted(GATE_DEPENDENT_PREDICATES)) + """ -- for any other \
predicate, cite the diff only. Do not cite a file that is not one of those \
sources. Do not cite a line you have not been shown. A fact read from a packet \
section that is not a file -- PULL REQUEST, CODEOWNERS, LAUNCHDARKLY STATE, \
PUBLISHED API LOOKUP, EXTERNAL REPO ACTIVITY -- is cited by quoting it in your \
evidence, naming the section; it has no path or line. If you cannot cite \
it either way, answer "unresolved".
4. Do not reason about any predicate other than the one asked.
"""


def load_predicates() -> dict:
    d = specload.load(GRAPH / "predicates.yaml")
    return {p["id"]: p for p in d["predicates"]}


HUNK_BUDGET, REFERENCED_CAP, PR_FIELD_CAP = 400_000, 6000, 4000
# Documented responses shown per PUBLISHED API LOOKUP operation (P19's
# decision-7 exceptions are judged against them); the rest are counted.
MAX_DOC_RESPONSE_LINES = 15
CUT_ORDER = ("build_ci", "generated", "test", "docs", "ships")
MAX_CUT_NOTES = 10


def fit_lines(lines: list[str], cap: int) -> tuple[list[str], int]:
    """The longest run of whole lines from the start of `lines` that fits in
    `cap` characters joined by newlines, and how many lines it leaves out.
    A first line longer than `cap` is kept cut to `cap`, and counted."""
    kept, size = [], -1
    for ln in lines:
        size += len(ln) + 1
        if size > cap:
            break
        kept.append(ln)
    if not kept and lines:
        return [lines[0][:cap]], len(lines)
    return kept, len(lines) - len(kept)


def _joined_len(lines: list[str]) -> int:
    return sum(len(ln) for ln in lines) + max(len(lines) - 1, 0)


def budget_hunks(hunks, budget: int | None = None) -> list[tuple[list[str], int]]:
    """Each hunk's numbered lines to show, and how many are left out. Every
    hunk is whole when they fit in `budget` together. Otherwise hunks are cut
    one role at a time in CUT_ORDER, largest first within a role, each only
    as far as the remaining excess needs, until the rest fits."""
    budget = HUNK_BUDGET if budget is None else budget
    lines = [_numbered_hunk_lines(h) for h in hunks]
    kept = [list(ls) for ls in lines]
    more = [0] * len(hunks)
    total = sum(_joined_len(k) for k in kept)
    for role in CUT_ORDER:
        if total <= budget:
            break
        order = sorted((i for i, h in enumerate(hunks) if h.role == role),
                       key=lambda i: (-_joined_len(kept[i]), i))
        for i in order:
            excess = total - budget
            if excess <= 0:
                break
            size = _joined_len(kept[i])
            room = size - excess
            k, m = fit_lines(lines[i], room) if room > 0 else ([], len(lines[i]))
            total += _joined_len(k) - size
            kept[i], more[i] = k, m
    return list(zip(kept, more))


def _cut_marker(n: int, what: str) -> str:
    return (f"{'':>9} | [cut to fit: {n} more line(s) of this {what} not shown. "
            f"What isn't shown is not evidence.]")


def render_packet(pkt) -> str:
    """The cached prefix. Must be byte-stable for the same commit."""
    cuts: list[str] = []
    L = [f"REPOSITORY: {pkt.repo_name}",
         f"DIFF UNIT: {pkt.unit['mode']}  spec={pkt.unit['spec']}",
         f"  merge_base={pkt.unit['merge_base']}  head={pkt.unit['head']}"]
    if pkt.pr:
        L.append("\nPULL REQUEST")
        for k in ("title", "body"):
            if pkt.pr.get(k):
                v = str(pkt.pr[k])
                if len(v) > PR_FIELD_CAP:
                    more = len(v) - PR_FIELD_CAP
                    v = (v[:PR_FIELD_CAP] + f" [cut to fit: {more} more "
                         f"character(s) not shown]")
                    cuts.append(f"the pull request {k}: {more} character(s) not shown")
                L.append(f"  {k}: {v}")
    L.append("\nCHANGED FILES (role from the repo profile)")
    for f in pkt.files:
        L.append(f"  [{f['role']:9s}] +{f['added']:<5} -{f['deleted']:<5} "
                 f"{f['path']}")
    L.append("\nFLAG EVALUATION SITES IN CHANGED FILES, AT HEAD")
    L.append("  (resolved through the declaration file: in this repo the key "
             "string does NOT appear at the call site)")
    for s in pkt.flag_sites_head or []:
        L.append(f"  {s['path']}:{s['line']}  key={s['key']}  "
                 f"symbol={s['symbol']}  | {s['text']}")
    if not pkt.flag_sites_head:
        L.append("  (none)")
    far = getattr(pkt, "flag_sites_far", None) or []
    if far:
        L.append(f"\n  ELSEWHERE IN THOSE FILES (>40 lines from any changed "
                 f"hunk -- shown for context, NOT reuse candidates):")
        for s in far[:20]:
            L.append(f"    {s['path']}:{s['line']}  key={s['key']}")
    L.append("\nFLAG EVALUATION SITES IN THE SAME FILES, AT MERGE_BASE")
    for s in pkt.flag_sites_base or []:
        L.append(f"  {s['path']}:{s['line']}  key={s['key']}")
    if not pkt.flag_sites_base:
        L.append("  (none)")
    if pkt.keys_added_by_diff:
        L.append("\nFLAG KEYS THIS DIFF ADDS (never reuse candidates)")
        for k in pkt.keys_added_by_diff:
            L.append(f"  {k}")
    if pkt.candidates:
        L.append("\nREUSE CANDIDATES (exist at merge_base)")
        for c in pkt.candidates:
            L.append(f"  {c['key']}  evaluated at {', '.join(c['evaluated_at'])}")
    if pkt.ld:
        L.append(f"\nLAUNCHDARKLY STATE as of {pkt.ld.get('as_of')} "
                 f"(user-facing production: {pkt.ld.get('user_facing')})")
        uf = list(pkt.ld.get("user_facing") or [])
        L += _ld_lines(pkt.ld.get("snapshots") or {}, uf) or [
            "  (no key cited near a changed hunk)"]
        ctx = pkt.ld.get("context_snapshots")
        if ctx:
            L.append("\nLAUNCHDARKLY STATE, OTHER KEYS: gates in the changed "
                     "code's callers, then flags evaluated in the changed files "
                     "at head (including any this diff adds), nearest first -- "
                     "context only, not reuse candidates")
            L += _ld_lines(ctx, uf)
    removed = getattr(pkt, "removed_flags", None) or []
    if removed:
        rm_snaps = (pkt.ld or {}).get("removed_snapshots") or {}
        L.append("\nLAUNCHDARKLY STATE, FLAGS WHOSE EVALUATIONS THIS DIFF "
                 "DELETES (evaluations in the changed files, merge_base -> "
                 "head; state "
                 + (f"as of {pkt.ld.get('as_of')}; for a boolean flag, "
                    "`serves` says who gets its true variation"
                    if rm_snaps else "not read")
                 + ")")
        uf = list((pkt.ld or {}).get("user_facing") or [])
        for r in removed:
            snap = rm_snaps.get(r["key"])
            state = (_ld_lines({r["key"]: snap}, uf)[0].split(": ", 1)[1]
                     if snap is not None else "state not read")
            L.append(f"  {r['key']} ({r['at_merge_base']} -> {r['at_head']} "
                     f"evaluation(s)): {state}")
    if pkt.codeowners:
        L.append(f"\nCODEOWNERS: {json.dumps(pkt.codeowners)}")
    api = getattr(pkt, "public_api", None)
    if api is not None:
        L.append(f"\nPUBLISHED API LOOKUP (mechanical, at merge_base "
                 f"{str(api['as_of'])[:12]}; public spec: "
                 f"{', '.join(api['public_spec'])}; hidden/internal spec: "
                 f"{', '.join(api['hidden_spec']) or '(none)'})")
        L.append("  Operations whose operationId names a function enclosing a "
                 "changed line, or one call above it:")
        for m in api["matches"]:
            status = ("PUBLISHED (in the public spec)" if m["published"] else
                      "NOT PUBLISHED (hidden/internal spec only)")
            L.append(f"    {m['method']} {m['path']}  operationId="
                     f"{m['operation_id']}  {status}  -- via {m['via']}")
            if m.get("binding"):
                how = {"user-credential": "accepts a user session or user "
                                          "API token",
                       "internal-only": "internal / employee-only auth",
                       }.get(m.get("auth"), "auth not classified by the "
                                            "repo profile")
                L.append(f"      route binding {m['binding']}: "
                         f"{m['auth_wrapper']} ({how})")
            docs = m.get("responses") or []
            if docs:
                L.append("      documented responses (spec at merge_base):")
                for r in docs[:MAX_DOC_RESPONSE_LINES]:
                    L.append(f"        {r['status']}  {r['description'] or '(no description)'}"
                             + (f"  [{r['schema']}]" if r.get("schema") else ""))
                if len(docs) > MAX_DOC_RESPONSE_LINES:
                    L.append(f"        (+{len(docs) - MAX_DOC_RESPONSE_LINES} more "
                             f"documented response(s) not shown)")
        if not api["matches"]:
            L.append("    (none)")
        L.append("  Functions searched: "
                 + (", ".join(api["searched"]) or
                    "(none -- no changed line is inside a function in a "
                    "language this lookup covers)"))
    for ext in getattr(pkt, "external", None) or []:
        L.append(f"\nEXTERNAL REPO ACTIVITY: {ext['github']} (named "
                 f"'{ext['name']}' in this diff; outside this tree)")
        if ext.get("error"):
            L.append(f"  (not available: {ext['error']})")
            continue
        L.append(f"  PRs merged {ext['window'][0]} .. {ext['window'][1]} (this "
                 f"diff's merge date), each with the first release published "
                 f"after it merged (approximate: assumes releases are cut from "
                 f"the branch it merged into):")
        for pr in ext["prs"]:
            rel = (f"first release {pr['first_release']} on {pr['released_at']}"
                   + (" -- RELEASED by the merge date"
                      if pr["released_by_merge"] else
                      " -- NOT released by the merge date")
                   if pr["first_release"] else
                   "no release after it -- NOT released")
            L.append(f"    #{pr['number']} merged {pr['merged_at']}: "
                     f"{pr['title']}  [{rel}]")
        if not ext["prs"]:
            L.append("    (none)")
    L.append("\nDIFF HUNKS")
    for h, (kept, more) in zip(pkt.hunks, budget_hunks(pkt.hunks)):
        L.append(f"\n--- {h.path} [{h.role}] new lines "
                 f"{h.new_range[0]}-{h.new_range[1]} ---")
        L.append("\n".join(kept + ([_cut_marker(more, "hunk")] if more else [])))
        if more:
            cuts.append(f"{h.path} [{h.role}] new lines {h.new_range[0]}-{h.new_range[1]}: "
                        f"{more} line(s) of the hunk not shown")
    ref = getattr(pkt, "referenced_context", None) or []
    if ref:
        L.append("\nREFERENCED FILES (NOT part of this diff -- citable ONLY "
                 "when answering "
                 + ", ".join(sorted(GATE_DEPENDENT_PREDICATES)) + ")")
        for rc in ref:
            L.append(f"\n--- {rc['path']} lines {rc['lo']}-{rc['hi']} "
                     f"(matched symbol: {rc['matched_symbol']}) ---")
            kept, more = fit_lines([f"{n:>6} | {t}" for n, t in
                                    enumerate(rc["text"].splitlines(), rc["lo"])],
                                   REFERENCED_CAP)
            L.append("\n".join(kept + ([_cut_marker(more, "window")] if more else [])))
            if more:
                cuts.append(f"referenced file {rc['path']} lines {rc['lo']}-{rc['hi']}: "
                            f"{more} line(s) not shown")
    notes = list(pkt.notes)
    if cuts:
        shown = "; ".join(cuts[:MAX_CUT_NOTES]) + (
            f"; and {len(cuts) - MAX_CUT_NOTES} more" if len(cuts) > MAX_CUT_NOTES else "")
        notes.append(f"{len(cuts)} part(s) of this evidence were cut to fit (diff "
                     f"hunks share one size budget, cut by file role: build/CI, "
                     f"generated, test, docs, then shipping code last), so what "
                     f"they leave out is not evidence: {shown}")
    if notes:
        L.append("\nPACKET NOTES (limits of this evidence)")
        for n in notes:
            L.append(f"  - {n}")
    return "\n".join(L)


def _numbered_hunk(h) -> str:
    return "\n".join(_numbered_hunk_lines(h))


def _numbered_hunk_lines(h) -> list[str]:
    """A diff hunk with every line's number printed, so a citation is read
    off the page instead of counted from the header. Context and added lines
    carry their NEW-file number, deleted lines their OLD one. Measured on
    an earlier PR: three P21 samples all cited a referenced file four lines
    above the route they meant -- the packet showed only `lines lo-hi`."""
    out, new_n, old_n = [], h.new_start, h.old_start
    for raw in h.text.rstrip("\n").splitlines():
        tag, body = raw[:1], raw[1:]
        if tag == "-":
            out.append(f"old{old_n:>6} | -{body}")
            old_n += 1
        elif tag == "+":
            out.append(f"new{new_n:>6} | +{body}")
            new_n += 1
        elif tag == " ":
            out.append(f"new{new_n:>6} |  {body}")
            new_n += 1
            old_n += 1
        else:  # "\ No newline at end of file" and the like
            out.append(f"{'':>9} | {raw}")
    return out


def _ld_lines(snaps: dict, user_facing: list[str]) -> list[str]:
    """."""
    out = []
    for k, snap in snaps.items():
        envs = snap.get("environments")
        if not envs:
            out.append(f"  {k}: {snap.get('basis')}")
            continue
        def fmt(name):
            e = envs[name]
            on = e.get("on")
            state = "unknown" if on is None else ("on" if on else "off")
            if e.get("serves"):
                # who is served the exposing variation: all / cohort /
                # internal / none (sources.serving); `on` alone does not say
                state += f", serves {e['serves']}"
            return f"{name}={state}" + (f" ({e.get('basis')})" if on is None
                                        else "")
        uf = [fmt(n) for n in user_facing if n in envs]
        other = [fmt(n) for n in envs if n not in user_facing]
        line = f"  {k}: " + ", ".join(uf)
        if other:
            line += "  | not user-facing: " + ", ".join(other)
        if snap.get("archived"):
            line += "  [archived]"
        out.append(line)
    return out


def render_question(p: dict) -> str:
    L = [f"PREDICATE {p['id']}: {p['name']}", "",
         "QUESTION", "  " + " ".join(p["question"].split()), "",
         "PROCEDURE"]
    L += ["  " + ln for ln in p["procedure"].rstrip().splitlines()]
    L += ["", "UNRESOLVED-WHEN"]
    L += ["  " + ln for ln in p["unresolved_when"].rstrip().splitlines()]
    L += ["", f"Answer only {p['id']}. Cite path and line from the packet."]
    if p.get("id") == BEHAVIOR_SET_PREDICATE:
        L += ["List the set this procedure records in `behavior_carrying`: "
              "one entry per hunk that itself alters runtime behavior. "
              "`citations` is for your supporting evidence and may include "
              "context lines; `behavior_carrying` may not."]
    return "\n".join(L)


def citation_context(pkt) -> dict:
    """Everything the citation check needs from a packet, JSON-shaped, so the
    manifest can carry it and merge_inline checks an inline answer exactly as
    this file checks a sampled one. Measured on an earlier PR via the
    preflight skill: without the caller-gate windows, merge_inline rejected a
    P6 citation the question itself said to make ("Cite these line numbers")
    and the walk escalated at N6."""
    known = sorted({f["path"] for f in pkt.files})
    referenced = (getattr(pkt, "referenced_context", None) or []) \
        + caller_gate_windows(pkt) + feature_windows(pkt)
    deleted: dict[str, list[list[int]]] = {}
    for h in getattr(pkt, "hunks", None) or []:
        if h.old_count:
            deleted.setdefault(h.path, []).append(
                [h.old_start, h.old_start + h.old_count - 1])
    gates: dict[str, set[int]] = {}
    for site in (getattr(pkt, "flag_sites_head", None) or []) + \
            (getattr(pkt, "flag_sites_base", None) or []):
        if site.get("key") and site["path"] in known:
            gates.setdefault(site["path"], set()).add(site["line"])
    for g in getattr(pkt, "caller_gates", None) or []:
        if g["path"] in known:
            gates.setdefault(g["path"], set()).update(g.get("gate_lines") or [])
    out = {"known": known, "referenced": referenced, "deleted_ranges": deleted,
           "diff_gate_lines": {p: sorted(s) for p, s in gates.items()}}
    facts = fact_lines(pkt)
    if facts:
        out["facts"] = facts
    return out


def check_citations(citations: list[dict], ctx: dict, file_lines=None,
                    predicate_id: str | None = None,
                    value=None) -> tuple[bool, str]:
    """`sources.verify_citations` over a `citation_context` -- the one call
    both the keyed reader and merge_inline make. `value` is the answer the
    citations support: only a YES claims a gate covers the change, so only a
    YES must cite a gate-shaped referenced line."""
    # A line the fact search verified for THIS question (fact_lines) is
    # citable by it, wherever it is: it was checked against head and shown.
    shown = {tuple(x) for x in (ctx.get("facts") or {}).get(predicate_id) or []}
    if shown:
        citations = [c for c in citations or []
                     if (c.get("path"), c.get("line")) not in shown]
    return verify_citation_set(
        citations or [], set(ctx["known"]), ctx["referenced"], file_lines,
        predicate_id,
        {p: [tuple(r) for r in rs] for p, rs in ctx["deleted_ranges"].items()},
        diff_gate_lines={p: set(ls) for p, ls in ctx["diff_gate_lines"].items()},
        claims_enclosure=value in (True, "yes", None))


def cited_file_lines(repo, rev: str, citations: list[dict], known) -> dict:
    """Head text of each cited changed file, for the line-exists check."""
    out: dict[str, list[str]] = {}
    for c in citations or []:
        if c.get("path") in known and c["path"] not in out:
            text = repo.file_at(rev, c["path"])
            if text is not None:
                out[c["path"]] = text.splitlines()
    return out


def verify_citations(ans: dict, pkt, repo=None,
                     predicate_id: str | None = None) -> tuple[bool, str]:
    """Mechanical check: does the cited evidence exist? Delegates to
    `sources.verify_citations`, the one implementation this file and
    `merge_inline.py` both use."""
    ctx = citation_context(pkt)
    cites = ans.get("citations") or []
    file_lines = (cited_file_lines(repo, pkt.unit["head"], cites, set(ctx["known"]))
                  if repo is not None else None)
    return check_citations(cites, ctx, file_lines, predicate_id, value=ans.get("value"))


BEHAVIOR_TERM = "behavior-carrying"
MAX_CONTEXT_CITATIONS = 20


def behavior_set_context(answers: dict, p: dict) -> str | None:
    """P2's recorded behavior-carrying set, for a later predicate that uses
    the term, or None.

    P2's own procedure is the contract: "Record the set of hunks that answer
    YES. Downstream predicates say 'behavior-carrying hunk' and mean exactly
    this set." Without this, every later predicate re-decided the set for
    itself -- measured on an earlier PR, P6 split 2-1 on whether removing a
    struct tag's `hidden:"true"` carries behavior, a question P2 had already
    answered, unanimously, YES. Passed in the question (after the packet's
    cache breakpoint), so the cached packet prefix is unchanged.
    """
    p2 = answers.get("P2") or {}
    if p.get("id") == "P2" or p2.get("value") is not True:
        return None
    text = " ".join(str(p.get(k, "")) for k in
                    ("question", "procedure", "unresolved_when"))
    if BEHAVIOR_TERM not in text:
        return None
    samples = p2.get("samples") or []
    recorded = any("behavior_carrying" in smp for smp in samples)
    field_name = "behavior_carrying" if recorded else "citations"
    cites: list[str] = []
    for smp in samples:
        for c in smp.get(field_name) or []:
            ref = f"{c.get('path')}:{c.get('line')}"
            if ref not in cites:
                cites.append(ref)
    L = ["BEHAVIOR-CARRYING HUNKS -- P2's recorded answer. This defines the "
         "term for this predicate: treat it as given and do not re-decide "
         "which hunks carry behavior.",
         "  " + " ".join(str(p2.get("evidence") or "").split())]
    if cites:
        L.append(("  P2 recorded these hunks: " if recorded else "  P2 cited: ")
                 + ", ".join(cites[:MAX_CONTEXT_CITATIONS]))
    return "\n".join(L)


CALLER_GATE_PREDICATES = frozenset({"P6", "P10", "P12"}) | specload.gate_evidence_ids(GRAPH)


def caller_gate_windows(pkt) -> list[dict]:
    """The caller-gate lines shown from files OUTSIDE the diff, shaped like
    referenced_context entries (one per contiguous run), so a citation into
    them is checked the same way: inside a window actually shown, and
    gate-shaped. Lines in changed files need no window -- any line of a
    changed file is citable."""
    known = {f["path"] for f in getattr(pkt, "files", None) or []}
    out: list[dict] = []
    for g in getattr(pkt, "caller_gates", None) or []:
        if g["path"] in known:
            continue
        run: list[tuple[int, str]] = []
        for n, t in g["lines"] + [(None, None)]:
            if run and (n is None or n != run[-1][0] + 1):
                out.append({"path": g["path"], "lo": run[0][0], "hi": run[-1][0],
                            "text": "\n".join(x[1] for x in run),
                            "matched_symbol": g.get("callee") or "",
                            "gate_keys": g["keys"],
                            "gate_lines": [x for x in g.get("gate_lines") or []
                                           if run[0][0] <= x <= run[-1][0]]})
                run = []
            if n is not None:
                run.append((n, t))
    return out


def caller_gate_context(pkt, p: dict) -> str | None:
    """The flag evaluations that run before changed code inside the changed
    files (mechanical.find_caller_gates), for the predicates that judge
    whether a gate dominates it, or None.

    In the question, not the packet: the packet is the cached prefix every
    predicate shares, and only P6 (ancestor enclosure) and P12 (a candidate's
    off arm) reason about gates above the changed code. The text is hashed
    into their cache key, so the rest of the cache is untouched.
    """
    every = getattr(pkt, "caller_gates", None) or []
    if p.get("id") not in DATA_GATE_PREDICATES or not every:
        return None
    if p.get("id") not in CALLER_GATE_PREDICATES:
        return "\n".join(data_gate_lines(every, cites_outside=False)) or None
    gates = [g for g in every if g["kind"] not in COVERAGE_KINDS + DATA_KINDS]
    L = ["GATES ABOVE CHANGED CODE -- flag evaluations that run before the "
         "changed code: earlier in the changed function, in a caller before "
         "its call, or further up the call chain (marked NOT in the diff; "
         "the chain is shown). The numbered hunks do not show these lines. "
         "Each entry shows the evaluation, the lines after it, and the call; "
         "whether it dominates (e.g. returns early when off) is yours to "
         "judge from them. Cite these line numbers."] if gates else []
    for g in gates:
        at_base = ("existed at merge_base: " + ", ".join(g["keys_at_merge_base"])
                   if g["keys_at_merge_base"] else "none existed at merge_base")
        if g["kind"] == "searched":
            # Found by the skill's gate search (a route, layout, helper,
            # handler or style the walk can't trace), every quoted line
            # checked against head before it got here.
            # A changed file's (in_diff): the evidence showed no check of
            # this flag there, through a helper the profile doesn't know.
            where = "in a changed file" if g.get("in_diff") else "NOT in the diff"
            L.append(f"- {g['path']} ({where}; found by the gate search, {g['how']}): "
                     f"{g['why']} Keys {', '.join(g['keys'])} ({at_base})")
        elif g["kind"] == "outside-caller":
            via = " <- ".join(f"{x}()" for x in g["chain"])
            L.append(f"- {g['path']} (NOT in the diff): {g['function']}() "
                     f"reaches the changed {g['callee']}() via {via}, calling "
                     f"{g['chain'][-2]}() at line {g['call_line']}; keys "
                     f"{', '.join(g['keys'])} ({at_base})")
            for c in g.get("also") or []:
                L.append(f"    the same call also reaches the changed {c[0]}() via "
                         + " <- ".join(f"{x}()" for x in c))
        elif g["kind"] == "registered-guard":
            # mechanical.find_registered_guards: a guard attached by
            # registration (middleware, a route module's loader), not called.
            at = "; ".join(f"{p}:{n} `{t[:90]}`" for p, n, t in g.get("attached_at") or [])
            L.append(f"- {g['path']} (NOT in the diff): {g['function']}() returns or throws at "
                     f"line {g['call_line']} depending on keys {', '.join(g['keys'])} ({at_base}). "
                     f"It is attached, not called -- passed as a value at: {at}. Whether what it "
                     f"is attached to runs the changed code only after it is yours to judge.")
        elif g["kind"] == "guard-attached":
            calls = ", ".join(f"{p}:{n}" for p, n in g.get("attach_calls") or [])
            L.append(f"- {g['path']} (NOT in the diff): line {g['call_line']} attaches the guard "
                     f"{g['callee']}() (in {g['guard_path']}; keys {', '.join(g['keys'])})"
                     + (f", inside {g['function']}()" + (f", which is called at {calls}" if calls else "")
                        if g.get("function") else ""))
        elif g["kind"] == "caller":
            more = (f" (and again at {', '.join(map(str, g['other_calls']))})"
                    if g.get("other_calls") else "")
            L.append(f"- {g['path']}: {g['function']}() calls the changed "
                     f"{g['callee']}() at line {g['call_line']}{more}; keys "
                     f"{', '.join(g['keys'])} ({at_base})")
        else:
            L.append(f"- {g['path']}: {g['function']}() is changed at line "
                     f"{g['changed_at']}; evaluated earlier in it: keys "
                     f"{', '.join(g['keys'])} ({at_base})")
        prev = None
        for n, t in g["lines"]:
            if prev is not None and n != prev + 1:
                L.append("         ...")
            L.append(f"  {n:>6} | {t}")
            prev = n
    L += caller_coverage_lines(every)
    L += data_gate_lines(every)
    return "\n".join(L) or None


# Caller coverage (reader/gate_search.verify_coverage): a `coverage` entry
# holds one verified claim, `covered` entries its lines outside the diff.
COVERAGE_KINDS = ("coverage", "covered")


def caller_coverage_lines(gates: list[dict]) -> list[str]:
    """The verified caller coverages among the caller-gate entries, rendered
    plainly: the unit, each caller and the flag that gates it (or why it
    leaves the new behavior off), and the quoted lines outside the diff."""
    covs = [g for g in gates if g["kind"] == "coverage"]
    if not covs:
        return []
    L = ["CALLER COVERAGE -- changed units whose every caller at head the gate "
         "search listed. Checked against head: every quoted line matches, each "
         "gated caller's chain from its flag evaluation to the call checks out "
         "as a gate's does, and a search of head for the unit's name found no other "
         "reference in shipping code (tests, stories, fixtures and docs aside). "
         "Whether each flag withholds the caller, and whether an `off` caller "
         "really leaves the new behavior off, is yours to judge from the lines. "
         "Cite these line numbers."]
    if any(g.get("clients") for g in covs):
        L.append("A caller written `<repository>:<path>` is in that client repository (a separate "
                 "checkout, such as the frontend that calls this backend), read at its main branch "
                 "as of this change's base; that repository was searched too, for every other use "
                 "of the unit's name, route, and the GraphQL operations that request it. Its flag "
                 "is read from that repository's LaunchDarkly project. Cite its lines by that "
                 "`<repository>:<path>`.")
    for g in covs:
        u = g["unit"]
        at_base = ("existed at merge_base: " + ", ".join(g["keys_at_merge_base"])
                   if g["keys_at_merge_base"] else "none existed at merge_base")
        route = f" (route {u['route']})" if u.get("route") else ""
        if u.get("external") and u["external"] != u["name"]:
            route += f" (called by clients as {u['external']})"
        if g.get("clients"):
            route += " (clients searched: " + ", ".join(f"{r} at {v[:12]}" for r, v in g["clients"].items()) + ")"
        L.append(f"- {u['name']}{route}, defined at {u['path']}:{u['line']}: "
                 + (f"{len(g['callers'])} caller(s) at head" if g["callers"]
                    else "no caller at head")
                 + (f"; flags {', '.join(g['keys'])} ({at_base})" if g["keys"] else "; no flag"))
        projects = g.get("key_projects") or {}
        for d in g.get("declared_at") or []:
            at = f"{d['repo']}:{d['path']}" if d.get("repo") else d["path"]
            L.append(f"    declared at {at}:{d['line']}: {d['text'].strip()}")
        for c in g["callers"]:
            at = f"{c['repo']}:{c['path']}" if c.get("repo") else c["path"]
            where = f"    caller {at}:{c['line']}: {c['text'].strip()}"
            rb = c["reached_by"]
            if rb == "gated":
                pj = projects.get(c["key"]) if c.get("repo") else None
                L.append(f"{where} -- behind flag {c['key']}"
                         + ((f" (LaunchDarkly project {pj[0]})" if pj[0] else
                             " (its LaunchDarkly project is unknown, so its state can't be read)") if pj else ""))
            elif rb == "off":
                o = c.get("off_line") or {}
                op = f"{c['repo']}:{o.get('path')}" if c.get("repo") else o.get("path")
                L.append(f"{where} -- leaves the new behavior off: {c.get('off_because')} "
                         f"({op}:{o.get('line')}: {str(o.get('text') or '').strip()})")
            elif rb == "test":
                L.append(f"{where} -- a test or story, not a way customers reach it")
            else:
                L.append(f"{where} -- nothing reaches it at head: {c.get('note')}")
        if g.get("why"):
            L.append(f"    why: {g['why']}")
        by_path: dict[str, set] = {}
        for e in gates:
            if e["kind"] == "covered" and e.get("coverage_of") == g["coverage_of"]:
                by_path.setdefault(e["path"], set()).update(map(tuple, e["lines"]))
        for path, lines in by_path.items():
            L.append(f"    {path} (NOT in the diff):")
            prev = None
            for n, t in sorted(lines):
                if prev is not None and n != prev + 1:
                    L.append("         ...")
                L.append(f"  {n:>6} | {t}")
                prev = n
    return L


# Data gates (reader/gate_search.verify_data_gate): a `data` entry holds one
# verified claim, `data-line` entries its lines outside the diff. P5 sees them
# too (a data gate over a flag the diff wires), but cites only the diff.
DATA_KINDS = ("data", "data-line")
DATA_GATE_PREDICATES = CALLER_GATE_PREDICATES | {"P5"}


def data_gate_lines(gates: list[dict], cites_outside: bool = True) -> list[str]:
    """The verified data gates among the caller-gate entries, rendered
    plainly: the records, the changed lines that act on them, every line
    that writes them with the flag it is behind (or why it doesn't count),
    the other uses, and the quoted lines outside the diff."""
    dgs = [g for g in gates if g["kind"] == "data"]
    if not dgs:
        return []
    L = ["DATA GATES -- changed code that only acts on records whose every writer at head "
         "the gate search listed (code that only acts on records that only flag-gated "
         "code writes counts as behind that flag). Checked against "
         "head: every quoted line matches, each gated writer's chain from its flag "
         "evaluation to the write checks out as a gate's does, and a search of head for "
         "the data's name found no reference in shipping code (tests, stories, fixtures "
         "and docs aside) beyond the lines listed. Whether a line listed as another use "
         "really doesn't write, whether each flag withholds its writer, and whether "
         "ungated code wrote such records before this change, is yours to judge from "
         "the lines. "
         + ("Cite these line numbers." if cites_outside else
            "Cite the lines of the changed files only; name the writers outside them in "
            "your evidence.")]
    for g in dgs:
        d = g["data"]
        at_base = ("existed at merge_base: " + ", ".join(g["keys_at_merge_base"])
                   if g["keys_at_merge_base"] else "none existed at merge_base")
        named = d["name"] + "".join(f", {x}" for x in d.get("also") or [])
        L.append(f"- {d.get('what') or d['name']} (named {named}): "
                 f"{len(g['writers'])} writer(s) at head; flags {', '.join(g['keys'])} ({at_base})")
        for r in g["readers"]:
            L.append(f"    reader {r['path']}:{r['line']}: {r['text'].strip()}")
        for w in g["writers"]:
            where = f"    writer {w['path']}:{w['line']}: {w['text'].strip()}"
            rb = w["reached_by"]
            if rb == "gated":
                L.append(f"{where} -- behind flag {w['key']}")
            elif rb == "off":
                o = w.get("off_line") or {}
                L.append(f"{where} -- writes them only empty: {w.get('off_because')} "
                         f"({o.get('path')}:{o.get('line')}: {str(o.get('text') or '').strip()})")
            elif rb == "test":
                L.append(f"{where} -- a test or fixture, not a way customers' records are written")
            else:
                L.append(f"{where} -- nothing reaches it at head: {w.get('note')}")
        for o in g.get("other_uses") or []:
            L.append(f"    other use {o['path']}:{o['line']}: {o['text'].strip()}")
        if g.get("why"):
            L.append(f"    why: {g['why']}")
        by_path: dict[str, set] = {}
        for e in gates:
            if e["kind"] == "data-line" and e.get("data_of") == g["data_of"]:
                by_path.setdefault(e["path"], set()).update(map(tuple, e["lines"]))
        for path, lines in by_path.items():
            L.append(f"    {path} (NOT in the diff):")
            prev = None
            for n, t in sorted(lines):
                if prev is not None and n != prev + 1:
                    L.append("         ...")
                L.append(f"  {n:>6} | {t}")
                prev = n
    return L


# The feature flag search (reader/feature_search.py): its verified flags are
# reuse candidates, and the questions that judge a candidate's feature and
# off arm see their lines and may cite them; P13 sees where each is
# evaluated and who owns it.
FEATURE_CITING_PREDICATES = frozenset({"P10", "P12"})
FEATURE_CONTEXT_PREDICATES = FEATURE_CITING_PREDICATES | {"P13"}


def feature_windows(pkt) -> list[dict]:
    """The feature search's lines outside the diff, shaped like
    referenced_context entries (one per contiguous run per file), so a
    citation of them is checked the same way; the flag's evaluate/decide
    lines are its gate lines."""
    known = {f["path"] for f in getattr(pkt, "files", None) or []}
    out: list[dict] = []
    for c in getattr(pkt, "feature_candidates", None) or []:
        by_path: dict[str, dict[int, str]] = {}
        gate: dict[str, set[int]] = {}
        for x in c["chain"] + c["change_link"]:
            if x["path"] in known:
                continue
            by_path.setdefault(x["path"], {})[x["line"]] = x["text"]
            if x.get("role") in ("evaluates", "decides"):
                gate.setdefault(x["path"], set()).add(x["line"])
        for path, lines in by_path.items():
            run: list[tuple[int, str]] = []
            for n, t in sorted(lines.items()) + [(None, None)]:
                if run and (n is None or n != run[-1][0] + 1):
                    out.append({"path": path, "lo": run[0][0], "hi": run[-1][0],
                                "text": "\n".join(x[1] for x in run), "matched_symbol": "",
                                "gate_keys": [c["key"]],
                                "gate_lines": sorted(g for g in gate.get(path, ())
                                                     if run[0][0] <= g <= run[-1][0])})
                    run = []
                if n is not None:
                    run.append((n, t))
    return out


def feature_search_context(pkt, p: dict) -> str | None:
    """The feature flag search's verified release flags, for the reuse
    questions that range over candidates, or None (so a question with none
    is unchanged)."""
    cands = getattr(pkt, "feature_candidates", None) or []
    pid = p.get("id")
    if not cands or pid not in FEATURE_CONTEXT_PREDICATES:
        return None
    if pid == "P13":
        L = ["FEATURE FLAG SEARCH -- reuse candidates found releasing the feature this "
             "change belongs to; where each is evaluated, and the CODEOWNERS teams of "
             "those files (for (b)):"]
        for c in cands:
            ev = ", ".join(f"{x['path']}:{x['line']}" for x in c["chain"] if x.get("role") == "evaluates")
            teams = ", ".join((c.get("owners") or {}).get("teams") or []) or "none listed"
            L.append(f"- {c['key']} ({c['feature']}): evaluated at {ev}; owners {teams}")
        return "\n".join(L)
    known = {f["path"] for f in getattr(pkt, "files", None) or []}
    L = ["FEATURE FLAG SEARCH -- the flag that releases the feature this change "
         "belongs to, found by the skill's feature search where the evidence above "
         "doesn't reach (a route, page, registration or module away from the changed "
         "lines). Checked against head: the key existed at merge_base, every quoted "
         "line matches, the chain runs from the flag's evaluation through the line its "
         "value decides to the feature's entry, and the second part runs from that entry "
         "to a changed file. Each is a REUSE CANDIDATE like the others. Whether all of "
         "the change is that feature's -- its own route, page or module, not the product "
         "area around it -- and whether the flag's off arm covers the change are yours "
         "to judge from the lines. Cite these line numbers."]
    for c in cands:
        e = c["entry"]
        L.append(f"- {c['key']}: releases {c['feature']} (entry, a {c['entry_kind']}: "
                 f"{e['path']}:{e['line']}). {c['why']}")
        for part, links in (("flag to entry", c["chain"]), ("entry to the change", c["change_link"])):
            L.append(f"    {part}:")
            for x in links:
                where = "" if x["path"] in known else " (NOT in the diff)"
                L.append(f"      {x['path']}:{x['line']}{where} [{x.get('role')}] | {x['text'].strip()}")
    return "\n".join(L)


def fact_lines(pkt) -> dict:
    """{question id: [[path, line], ...]}: the fact search's verified lines
    each question may cite (check_citations)."""
    out = {}
    for pid, rec in (getattr(pkt, "fact_findings", None) or {}).items():
        lines = [[f["path"], f["line"]] for f in rec.get("findings") or []]
        if lines:
            out[pid] = lines
    return out


def fact_search_context(pkt, p: dict) -> str | None:
    """The fact search's verified findings for this question, or None."""
    rec = (getattr(pkt, "fact_findings", None) or {}).get(p.get("id")) or {}
    found = rec.get("findings") or []
    if not found:
        return None
    L = ["FACT SEARCH FINDINGS -- this question was first answered unresolved, and "
         "the result depends on it, so the repository at head was searched for what "
         "that answer said was missing. Each line below was checked against head; the "
         "claim beside it is the searcher's, yours to check against the line. These "
         "add to the evidence: answer by the PROCEDURE and UNRESOLVED-WHEN as written, "
         "and cite these lines by path and line like any other."]
    if rec.get("searched"):
        L.append("  searched: " + " ".join(str(rec["searched"]).split()))
    for f in found:
        L.append(f"  {f['path']}:{f['line']} | {f['text']}")
        L.append(f"      -- {f['claim']}")
    return "\n".join(L)


def given_answers_context(answers: dict, p: dict) -> str | None:
    """The recorded answers of the predicates `p` declares as `given:`, or
    None. A predicate asked about an earlier one's finding -- P28 weighs the
    hunks P27 found -- needs that finding, not a re-derivation of it."""
    L = []
    for pid in p.get("given") or []:
        a = answers.get(pid) or {}
        if a.get("value") is not True:
            continue
        cites: list[str] = []
        for smp in a.get("samples") or []:
            for c in smp.get("citations") or []:
                ref = f"{c.get('path')}:{c.get('line')}"
                if ref not in cites:
                    cites.append(ref)
        L.append(f"{pid} ANSWERED YES -- its recorded finding, given for this "
                 f"predicate:\n  " + " ".join(str(a.get("evidence") or "").split()))
        if cites:
            L.append(f"  {pid} cited: " + ", ".join(cites[:MAX_CONTEXT_CITATIONS]))
    return "\n".join(L) or None


def reuse_scope_context(answers: dict, p: dict) -> str | None:
    """The keys P10, P12 and P13 range over (predicates.yaml: the reuse layer
    is about ONE key), or None.

    P10 gets the candidates P11 found still withholding; P12, those P10 also
    named; P13, the reuse key P12 named. When the answer it depends on is not
    in yet -- the inline manifest is written before anything is answered --
    the same rule is stated against the earlier question instead, and
    mechanical.reuse_key_violation enforces it on the replies."""
    from reader.mechanical import reuse_allowed_keys, reuse_scope
    pid = p.get("id")
    withheld = (answers.get("P11") or {}).get("withholding_keys")
    # P33 YES: the enclosing gate still holds the change back in main
    # production, so P13 is asked whether or not P12 named a key, and with
    # none it is about that gate (predicates.yaml P13; tree N13C).
    p33 = answers.get("P33") or {}
    holding = (p33.get("holding_keys") or []) if p33.get("value") is True else []
    if pid == "P13" and withheld is None and holding:
        return ("THE REUSE KEY: " + ", ".join(holding) + " -- the enclosing gate: "
                "P6 found it enclosing this change, and P33 found it still holding "
                "the change back from some real users in the main production "
                "environment. Compare this change's release with that gate's feature.")
    if pid not in ("P10", "P12", "P13") or withheld is None:
        return None
    if pid == "P10":
        found = ("P11 found these still withheld from some real users, or "
                 "could not read their state: "
                 if (answers.get("P11") or {}).get("unreadable_keys")
                 else "P11 found these still withheld from some real users: ")
        return ("REUSE CANDIDATES FOR THIS QUESTION -- " + found
                + (", ".join(withheld) or "none")
                + ". Only these keys count. Name the qualifying key(s) in "
                "`reuse_keys`.")
    if pid == "P12":
        allowed = reuse_allowed_keys(answers, "P12")
        if allowed is None:
            return ("REUSE CANDIDATES FOR THIS QUESTION -- only the keys you "
                    "named for P10, which must come from those P11 found still "
                    "withheld: " + (", ".join(withheld) or "none")
                    + ". Name the key(s) whose off arm covers the change in "
                    "`reuse_keys`.")
        return ("REUSE CANDIDATES FOR THIS QUESTION -- P10 found this change "
                "belongs to the feature of: " + (", ".join(allowed) or "none")
                + ". Only these keys count. Name the key(s) whose off arm "
                "covers the change in `reuse_keys`.")
    scope = reuse_scope(answers)
    gate = (" If P12 named no key, THE REUSE KEY is the enclosing gate "
            + ", ".join(holding) + ": P6 found it enclosing this change, and "
            "P33 found it still holding the change back from some real users "
            "in the main production environment. Compare this change's release "
            "with that gate's feature." if holding else "")
    if scope is None:
        return ("THE REUSE KEY is the key you named for P12 (it must be one P10 "
                "named, still withheld per P11: " + (", ".join(withheld) or "none")
                + "). The packet's CODEOWNERS block lists the owners of each "
                "candidate's evaluation sites under `candidate_sites`." + gate)
    if not scope and holding:
        return ("THE REUSE KEY: " + ", ".join(holding) + " -- no reuse candidate "
                "covers the change, so this is the enclosing gate: P6 found it "
                "enclosing this change, and P33 found it still holding the change "
                "back from some real users in the main production environment. "
                "Compare this change's release with that gate's feature.")
    return ("THE REUSE KEY: " + (", ".join(scope) or "none")
            + " (still withheld per P11, this change's feature per P10, covering "
            "the change per P12). The packet's CODEOWNERS block lists the owners "
            "of its evaluation sites under `candidate_sites`.")


def join_contexts(*parts: str | None) -> str | None:
    kept = [x for x in parts if x]
    return "\n\n".join(kept) if kept else None


PROMPT_CACHE_FRESH_S = 270
"""How long after its last use a cached prefix is trusted to still be warm.
Anthropic's ephemeral cache lives 5 minutes from last use; 30s of margin."""


def packet_hash(pkt) -> str:
    return hashlib.sha256(render_packet(pkt).encode()).hexdigest()[:16]
