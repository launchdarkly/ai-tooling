#!/usr/bin/env python3
"""should-auto-approve: rate a committed change low, medium or high risk by a
fixed decision graph, from answers an agent gives to its questions.

    cli.py start [REPO] [--base REF] [--head REF] [--pr-title T] [--pr-body-file F] [--pr-author LOGIN]
    cli.py flag RUN FLAG_KEY
    cli.py answer RUN < ANSWERS.json
    cli.py decide RUN

`start` answers what the changed paths decide (paths.py), lists the
LaunchDarkly flags named in the change with their state now (flagstate.py),
and writes the questions left for the agent to RUN/questions.md. `answer`
checks the agent's reply covers every question; `decide` walks the graph
(classify.resolve_tree) and prints the rating, with the approval gates
(approval.yaml) that decide whether a low rating may merge on an automated
approval alone. Run as a folder: python3 should-auto-approve.

Exit codes: 0 ok, 2 setup problem or not decided yet, 4 nothing committed,
7 answers missing or invalid (listed), 9 LaunchDarkly not readable.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
try:  # the built skill: engine.py and spec_data.py sit beside this file
    import engine as E
    import spec_data
    PREDS, TREE, GRAPH = spec_data.PREDICATES, spec_data.TREE, spec_data.GRAPH
    GATES, GATES_VERSION = spec_data.GATES, spec_data.GATES_VERSION
    PRODUCT_ATTRS = spec_data.PRODUCT_ATTRS
except ImportError:  # run from the repo: walk the YAML spec with classify.py
    ROOT = HERE.parent.parent
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(HERE.parent / "eval"))
    import yaml
    import classify as E
    _t = {f: (HERE.parent / f"{f}.yaml").read_text() for f in ("predicates", "tree", "workflow", "approval")}
    PREDS = yaml.safe_load(_t["predicates"])["predicates"]
    TREE = yaml.safe_load(_t["tree"])
    GATES = yaml.safe_load(_t["approval"])["gates"]
    GATES_VERSION = hashlib.sha256(_t["approval"].encode()).hexdigest()[:12]
    PRODUCT_ATTRS = json.loads((HERE.parent / "product_attrs.json").read_text())["keys"]
    GRAPH = hashlib.sha256((_t["predicates"] + _t["tree"] + _t["workflow"] + E.EVALUATOR).encode()).hexdigest()[:12]
import flagstate as F  # noqa: E402
import paths as P  # noqa: E402

NAME = "should-auto-approve"
PATH_IDS = ("A1", "B1", "B3", "C1")
RUNS = Path(os.environ.get("SHOULD_AUTO_APPROVE_RUNS", Path.home() / ".cache" / NAME))
# the skill reads LaunchDarkly's own defaults, not the eval's instance
F.HOST = os.environ.get("LAUNCHDARKLY_BASE_URI", "https://app.launchdarkly.com").rstrip("/")


def git(repo, *args, check=True):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and p.returncode:
        raise SystemExit(f"setup: git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def default_base(repo):
    for ref in ("origin/HEAD", "origin/main", "origin/master", "main", "master"):
        if git(repo, "rev-parse", "--verify", "-q", ref, check=False):
            return ref
    raise SystemExit("setup: no base given and no origin/HEAD, origin/main or main; pass --base")


def questions(path_ans):
    """The reader-answered questions, in the graph's order (run_reader.questions)."""
    out = []
    for p in PREDS:
        if p["id"] == "U1" or (p["id"] in PATH_IDS and path_ans.get(p["id"]) is not None):
            continue
        if p["id"] == "B2" and path_ans.get("B2") is True:
            continue
        out.append(p)
    return out


POLICY = "APPROVAL_POLICY.md"
BOT = re.compile(r"\[bot\]$|^(dependabot|renovate|github-actions|devin-ai-integration|cursor)\b", re.I)


def policies(repo, base, files):
    """The APPROVAL_POLICY.md files at merge_base that cover a changed path:
    the one in the path's directory or the nearest one above it."""
    have = {str(Path(p).parent) if "/" in p else "" for p in
            git(repo, "ls-tree", "-r", "--name-only", base).splitlines() if Path(p).name == POLICY}
    cover = {}
    for f in files:
        d = str(Path(f).parent) if "/" in f else ""
        while True:
            if d in have:
                cover.setdefault(f"{d}/{POLICY}" if d else POLICY, []).append(f)
                break
            if not d:
                break
            d = str(Path(d).parent) if "/" in d else ""
    return cover


def gate_answers(repo, head, files, cover, author):
    """What `start` settles itself; None leaves a gate to the agent."""
    if author:
        g2 = {"value": not BOT.search(author), "evidence": f"pull request author {author}"}
    else:
        c = git(repo, "log", "-1", "--format=%an <%ae>", head)
        g2 = ({"value": False, "evidence": f"head commit author {c} is a bot account"} if BOT.search(c.split(" <")[0])
              else {"value": "unresolved", "evidence": f"no --pr-author; head commit author {c}"})
    return {
        "G1": None if cover else {"value": True, "evidence": "no approval policy file covers the change"},
        "G2": g2,
        "G3": None if cover else {"value": True, "evidence": "no approval policy file covers the change"},
    }


def product_attr_hints(repo, base, head):
    """B7's hint: changed shipping lines that name a telemetry attribute the
    product's views read (product_attrs.json)."""
    rx = re.compile(r"(?<![\w.])(" + "|".join(re.escape(k) for k in sorted(PRODUCT_ATTRS, key=len, reverse=True))
                    + r")(?![\w])")
    out, cur = [], None
    for line in git(repo, "diff", f"{base}...{head}").splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
        elif cur and line[:1] in "+-" and not line.startswith(("+++", "---")) and not P.NO_SHIP.search(cur):
            out += [f"{cur}: {m}" for m in sorted(set(rx.findall(line)))]
    return sorted(set(out))[:40]


def render(p):
    return (f"### {p['id']} -- {p['name']}\n\n{p['question'].strip()}\n\n"
            f"Procedure:\n{p['procedure'].strip()}\n\nUnresolved when:\n{p['unresolved_when'].strip()}\n")


def current(key, envs):
    f = F.api(f"/api/v2/flags/{F.PROJECT}/{key}")
    if f.get("_http") == 404:
        return {"key": key, "not_found": True}
    if f.get("_http"):
        return {"key": key, "error": f"LaunchDarkly returned HTTP {f['_http']}"}
    return F.summarize(f, envs)


def flag_state(repo, base, head):
    """Every project flag key named in the change's hunks (and ten lines
    around them), with its state now in every critical environment."""
    t0 = time.time()
    if not F.key():
        return {"read": False, "why": "no key"}
    text, skipped = F.changed_text(str(repo), base, head)
    probe = F.api(f"/api/v2/projects/{F.PROJECT}")
    if probe.get("_http"):
        return {"read": False, "why": f"LaunchDarkly returned HTTP {probe['_http']} for project {F.PROJECT}"}
    keys = F.project_keys(None)
    tokens = set(re.findall(r"[\w-]+", text))
    found = sorted({k for k in keys if k in tokens or F.camel(k) in tokens
                    or ("." in k and re.search(rf"(?<![\w-]){re.escape(k)}(?![\w-])", text))})
    envs = F.critical_envs()
    return {"read": True, "project": F.PROJECT, "critical_environments": envs,
            "generated_files_skipped": skipped, "flags": [current(k, envs) for k in found],
            "seconds": round(time.time() - t0, 1)}


def read_key(path):
    """The API key in --key-file (evaluations only); never from the environment."""
    if not path:
        return ""
    if not Path(path).is_file():
        raise SystemExit(f"setup: no key file {path}")
    return Path(path).read_text().strip()


def start(a):
    repo = Path(a.repo).resolve()
    F.use_key(read_key(a.key_file))
    if not git(repo, "rev-parse", "--is-inside-work-tree", check=False):
        raise SystemExit(f"setup: {repo} is not a git checkout")
    if a.pr_body_file and not Path(a.pr_body_file).is_file():
        raise SystemExit(f"setup: --pr-body-file {a.pr_body_file} is not a file")
    head = git(repo, "rev-parse", "--verify", f"{a.head}^{{commit}}")
    base_ref = a.base or default_base(repo)
    base = git(repo, "merge-base", base_ref, head, check=False)
    if not base:
        print(f"setup: no merge base between {base_ref} and {head[:12]} (a shallow clone needs the merge base)")
        return 2
    files = git(repo, "diff", "--name-only", f"{base}...{head}").split()
    if not files:
        print(f"NOTHING COMMITTED: {base_ref}...{head[:12]} changes no files")
        return 4
    title = a.pr_title or git(repo, "log", "-1", "--format=%s", head)
    body = Path(a.pr_body_file).read_text() if a.pr_body_file else git(repo, "log", "-1", "--format=%b", head)
    run = RUNS / f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{head[:12]}"
    run.mkdir(parents=True, exist_ok=True)
    pa = P.answer({"id": head[:12], "files": files, "files_truncated": False})
    pa["hint_B7"] = product_attr_hints(repo, base, head)
    fs = flag_state(repo, base, head)
    qs = questions(pa)
    cover = policies(repo, base, files)
    ga = gate_answers(repo, head, files, cover, a.pr_author)
    gq = [g for g in GATES if ga.get(g["id"]) is None]
    (run / "case.json").write_text(json.dumps({
        "repo": str(repo), "base_ref": base_ref, "merge_base": base, "head": head, "title": title,
        "files": files, "path_answers": pa, "questions": [q["id"] for q in qs + gq], "graph": GRAPH,
        "policies": cover, "gate_answers": {k: v for k, v in ga.items() if v is not None},
        "gates_version": GATES_VERSION,
        "key_file": str(Path(a.key_file).resolve()) if a.key_file else None}, indent=1))
    (run / "flags.json").write_text(json.dumps(fs, indent=1))
    (run / "pr_body.txt").write_text(body or "(no description)")
    shown = {k: v for k, v in pa.items() if k in ("A1", "A1_paths", "B1", "B1_paths", "B2", "B2_paths",
                                                   "hint_B2_model", "B3", "B3_paths", "hint_B4", "hint_B7", "C1")}
    (run / "questions.md").write_text(
        f"# Questions for {head[:12]} ({title})\n\nMerge base `{base}`, commit `{head}`.\n\n"
        f"## Already answered from paths (do not re-answer)\n\n```json\n{json.dumps(shown, indent=1)}\n```\n\n"
        + "## Approval policy files covering the change at merge base\n\nRead by B6, G1 and G3.\n\n"
        + ("".join(f"- `{k}`: {len(v)} changed file(s)\n" for k, v in cover.items()) or "- none\n") + "\n"
        + "\n".join(render(q) for q in qs)
        + "\n## Approval gates\n\nNot part of the rating: whether a low change may merge on an automated "
          "approval alone. Answer these too, in the same object, from the policy files listed above.\n"
        + "".join(f"\n### {g['id']} -- {g['name']} (settled by start: {ga[g['id']]['value']})\n"
                  for g in GATES if ga.get(g["id"]) is not None)
        + "\n" + "\n".join(render(g) for g in gq))
    print(f"RUN: {run}")
    print(f"CHANGE: {len(files)} file(s), {base[:12]}...{head[:12]} ({base_ref})")
    print(f"PR TEXT: {title}")
    if fs["read"]:
        print(f"LAUNCHDARKLY: {len(fs['flags'])} flag(s) named in the change, project {fs['project']}, "
              f"environments {', '.join(fs['critical_environments']) or '(none critical)'}; RUN/flags.json")
    else:
        print(f"LAUNCHDARKLY: not read ({fs['why']}); find the flags yourself and read their state with your "
              f"LaunchDarkly tools")
    print(f"QUESTIONS: {len(qs) + len(gq)} ({', '.join(q['id'] for q in qs + gq)}); RUN/questions.md")
    return 0


def load_run(run):
    run = Path(run)
    if not (run / "case.json").is_file():
        raise SystemExit(f"setup: {run} is not a run folder (run `start` first)")
    return run, json.loads((run / "case.json").read_text())


def flag(a):
    run, case = load_run(a.run)
    kf = case.get("key_file")  # the path start was given, never the key
    F.use_key(Path(kf).read_text().strip() if kf and Path(kf).is_file() else "")
    if not F.key():
        print("LAUNCHDARKLY: no key; read this flag with your LaunchDarkly tools")
        return 9
    fs = json.loads((run / "flags.json").read_text())
    envs = fs.get("critical_environments") or F.critical_envs()
    got = current(a.key, envs)
    if got.get("error"):
        print(f"LAUNCHDARKLY: {got['error']} reading {a.key}; read this flag with your LaunchDarkly tools")
        return 9
    print(json.dumps(got, indent=1))
    return 0


def check(obj, case):
    if not isinstance(obj, dict) or not isinstance(obj.get("answers"), dict):
        return ['the reply must be one JSON object with an "answers" object']
    bad = []
    for q in case["questions"]:
        x = obj["answers"].get(q)
        if not isinstance(x, dict):
            bad.append(f"{q}: missing")
        elif x.get("value") not in (True, False, "unresolved"):
            bad.append(f"{q}: value must be true, false or \"unresolved\", not {x.get('value')!r}")
        elif not str(x.get("evidence") or "").strip():
            bad.append(f"{q}: evidence is empty")
    return bad


def answer(a):
    run, case = load_run(a.run)
    text = sys.stdin.read()
    try:
        obj = json.loads(text)
    except ValueError as e:
        print(f"INVALID: not JSON ({e})")
        return 7
    bad = check(obj, case)
    if bad:
        print("INVALID: fix these and send the whole object again:\n  " + "\n  ".join(bad))
        return 7
    (run / "answers.json").write_text(json.dumps(obj, indent=1))
    print(f"ANSWERS: {len(case['questions'])} recorded; run `decide {run}`")
    return 0


def values(obj, pa):
    """run_reader.values: path answers first, then the reader's."""
    vals = {"U1": True}
    for k in PATH_IDS + ("B2",):
        if pa.get(k) is not None:
            vals[k] = pa[k]
    for k, x in obj["answers"].items():
        if k in vals or k.startswith("G"):  # approval gates are not graph answers
            continue
        v = x.get("value") if isinstance(x, dict) else x
        vals[k] = E.UNRESOLVED if v not in (True, False) else v
    for p in PREDS:
        vals.setdefault(p["id"], E.UNRESOLVED)
    return vals


def walk(obj, pa):
    vals = values(obj, pa)
    steps, term, verdict, over = E.resolve_tree(TREE, vals)
    return vals, steps, term, verdict, over


def decide(a):
    run, case = load_run(a.run)
    if not (run / "answers.json").is_file():
        print("NOT DECIDED YET: no answers recorded; answer RUN/questions.md with `answer`")
        return 2
    obj = json.loads((run / "answers.json").read_text())
    vals, steps, term, verdict, over = walk(obj, case["path_answers"])
    by_id = {p["id"]: p for p in PREDS}
    terms = {t["id"]: t for t in TREE["terminals"]}
    last = steps[-1]["predicate"] if steps else None
    escalated = verdict == "escalate"
    rating = None if escalated else verdict
    print(f"RESULT: {rating or 'a person needs to decide'}")
    if escalated:
        q = by_id.get(last, {})
        print(f"WHY: the check could not settle: {q.get('question', '').strip()}")
    else:
        print(f"WHY: {terms[term]['reason']}")
    if last and not escalated:
        ev = (obj["answers"].get(last) or {}).get("evidence") or "(answered from the changed paths)"
        print(f"DECIDING QUESTION: {by_id[last]['question'].strip()}\n  {ev}")
    if over:
        print(f"UNCLEAR, BUT IT DIDN'T MATTER: {', '.join(by_id[p]['question'].strip() for p in over['unresolved'])}")
    gates = {}
    for g in GATES:
        x = case.get("gate_answers", {}).get(g["id"]) or obj["answers"].get(g["id"])
        v = x.get("value") if isinstance(x, dict) else None
        gates[g["id"]] = v if v in (True, False) else "unresolved"
    auto = (False if rating != "low" or False in gates.values() else
            "unresolved" if "unresolved" in gates.values() else True)
    shut = [g for g in GATES if gates[g["id"]] is not True]
    print(f"APPROVAL: {'can merge on an automated approval' if auto is True else 'needs a person'}"
          + "".join(f"\n  {'not met' if gates[g['id']] is False else 'unclear'}: {g['question'].strip()}"
                    for g in shut))
    rec = {"rating": rating, "escalated": escalated, "terminal": term, "graph": GRAPH,
           "head": case["head"], "merge_base": case["merge_base"],
           "steps": [[s["node"], s["predicate"], s["answer"]] for s in steps],
           "values": {k: (v if v in (True, False) else "unresolved") for k, v in vals.items()},
           "gates": gates, "auto_approve": auto, "gates_version": case.get("gates_version", GATES_VERSION)}
    print(f"\n```json {NAME}\n{json.dumps(rec)}\n```")
    (run / "verdict.json").write_text(json.dumps(rec, indent=1))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog=NAME, description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="{start,flag,answer,decide}")
    s = sub.add_parser("start", help="prepare a run: path answers, flag state, the questions")
    s.add_argument("repo", nargs="?", default=".")
    s.add_argument("--base")
    s.add_argument("--head", default="HEAD")
    s.add_argument("--pr-title")
    s.add_argument("--pr-body-file")
    s.add_argument("--pr-author", help="the pull request author's login (bot authors need a person)")
    s.add_argument("--key-file", help=argparse.SUPPRESS)  # a read-only API key; evaluations only
    f = sub.add_parser("flag", help="read one flag's state now (a gate outside the hunks)")
    f.add_argument("run")
    f.add_argument("key")
    sub.add_parser("answer", help="record the answers (JSON on stdin)").add_argument("run")
    sub.add_parser("decide", help="walk the graph and print the rating").add_argument("run")
    sub.add_parser("_questions")  # equivalence.py: the question ids left after path answers (JSON on stdin)
    a = ap.parse_args(argv)
    if a.cmd == "_questions":
        print(json.dumps([q["id"] for q in questions(json.loads(sys.stdin.read()))]))
        return 0
    try:
        return {"start": start, "flag": flag, "answer": answer, "decide": decide}[a.cmd](a)
    except SystemExit as e:
        if not isinstance(e.code, str):
            raise
        print(e.code)  # a setup message: exit 2, as SKILL.md's tables say
        return 2


if __name__ == "__main__":
    sys.exit(main())
