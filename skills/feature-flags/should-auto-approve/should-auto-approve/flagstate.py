#!/usr/bin/env python3
"""The fast flag-state input for C4: no should-i-flag run, a few API calls.

    python3 risk/eval/flagstate.py REPO_DIR BASE HEAD CUTOFF OUT.json [--keys KEYS.json]
    python3 risk/eval/flagstate.py --lookup FLAG_KEY CUTOFF

Finds the project's flag keys (as written, and camelCased as the JS SDK
exposes them) in the diff's changed hunks and their context, skipping
generated files, and writes each found flag's state in every critical
environment AS OF CUTOFF: a flag created after it reads as not found, and a
flag changed after it reads as it was just before the first such change (that
audit-log entry's previousVersion). --lookup prints one flag the same way, for
a gate the reader finds outside the hunks. KEYS.json caches the key list.
"""
import datetime as dt
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOST = os.environ.get("LAUNCHDARKLY_BASE_URI", "https://app.launchdarkly.com").rstrip("/")
PROJECT = os.environ.get("LAUNCHDARKLY_PROJECT", "default")
_KEY = []


def use_key(k: str):
    """The key to read with, from the caller: the skill's CLI passes its
    --key-file's, or none, and never reads one from the environment."""
    _KEY[:] = [k]


def key():
    """use_key's key, or none."""
    return _KEY[0] if _KEY else ""
CONTEXT = 10  # lines of context around each hunk: a flag check that already encloses the change
GENERATED = ["apidocs/*", "*/generated/*", "*/__generated__/*", "*.gen.*", "*.pb.go", "*_gen.go",
             "*.lock", "yarn.lock", "package-lock.json", "go.sum", "*.snap", "*.min.js"]


def api(p):
    try:
        req = urllib.request.Request(HOST + p, headers={"Authorization": key()})
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        return {"_http": e.code}


def project_keys(cache):
    if cache and Path(cache).exists():
        return json.loads(Path(cache).read_text())
    keys, off = [], 0
    while True:
        page = api(f"/api/v2/flags/{PROJECT}?summary=true&limit=100&offset={off}").get("items", [])
        keys += [f["key"] for f in page]
        if len(page) < 100:
            break
        off += 100
    if cache:
        Path(cache).write_text(json.dumps(keys))
    return keys


def generated(path, attrs):
    if any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch("/" + path, "*/" + g) for g in GENERATED):
        return True
    return any(fnmatch.fnmatch(path, l.split()[0]) for l in attrs.splitlines() if "linguist-generated" in l)


def changed_text(repo, base, head):
    files = subprocess.check_output(["git", "-C", repo, "diff", "--name-only", f"{base}...{head}"], text=True).split()
    attrs = subprocess.run(["git", "-C", repo, "show", f"{head}:.gitattributes"], capture_output=True, text=True).stdout
    kept = [f for f in files if not generated(f, attrs)]
    if not kept:
        return "", files
    diff = subprocess.check_output(["git", "-C", repo, "diff", f"-U{CONTEXT}", f"{base}...{head}", "--", *kept], text=True)
    return diff, [f for f in files if f not in kept]


def camel(k):
    parts = re.split(r"[-_.]", k)
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def as_of(key, cut):
    """The flag as it was at cut: the previousVersion of the first change after it, else today's."""
    now = api(f"/api/v2/flags/{PROJECT}/{key}")
    if now.get("_http") == 404 or (now.get("creationDate") or 0) > cut:
        return None, "not found at cutoff"
    log = api(f"/api/v2/auditlog?spec=proj/{PROJECT}:env/*:flag/{key}&after={cut}&limit=20").get("items", [])
    for e in sorted(log, key=lambda e: e["date"]):
        prev = api(f"/api/v2/auditlog/{e['_id']}").get("previousVersion")
        if prev and prev.get("environments"):
            return prev, f"as of cutoff, from the change at {e['date']}"
    return now, "unchanged since cutoff"


def summarize(flag, envs):
    out = {"key": flag["key"], "kind": flag.get("kind"), "created": flag.get("creationDate"),
           "variations": [v.get("value") for v in flag.get("variations", [])], "environments": {}}
    for e in envs:
        c = flag.get("environments", {}).get(e)
        if not c:
            continue
        ft = c.get("fallthrough", {})
        out["environments"][e] = {
            "on": c.get("on"), "off_variation": c.get("offVariation"),
            "fallthrough": ft.get("variation", "rollout" if ft.get("rollout") else None),
            "rules": len(c.get("rules", [])), "targets": sum(len(t.get("values", [])) for t in c.get("targets", [])),
            "prerequisites": [p.get("key") for p in c.get("prerequisites", [])]}
    return out


def critical_envs():
    return [e["key"] for e in api(f"/api/v2/projects/{PROJECT}/environments?limit=100").get("items", [])
            if e.get("critical")]


def state(key, cut, envs):
    f, source = as_of(key, cut)
    if f is None:
        return {"key": key, "not_found": True}
    return {**summarize(f, envs), "state_source": source}


def cut_ms(cutoff):
    return int(dt.datetime.fromisoformat(cutoff.replace("Z", "+00:00")).timestamp() * 1000)


def main():
    if sys.argv[1] == "--lookup":
        print(json.dumps(state(sys.argv[2], cut_ms(sys.argv[3]), critical_envs()), indent=1))
        return
    repo, base, head, cutoff, out = sys.argv[1:6]
    cache = sys.argv[sys.argv.index("--keys") + 1] if "--keys" in sys.argv else None
    t0 = time.time()
    cut = cut_ms(cutoff)
    text, skipped = changed_text(repo, base, head)
    keys = project_keys(cache)
    # one pass: a key is a whole [\w-] token (dotted keys, the rare case, by regex)
    tokens = set(re.findall(r"[\w-]+", text))
    found = sorted({k for k in keys if k in tokens or camel(k) in tokens
                    or ("." in k and re.search(rf"(?<![\w-]){re.escape(k)}(?![\w-])", text))})
    envs = critical_envs()
    flags = [state(k, cut, envs) for k in found]
    Path(out).write_text(json.dumps({"critical_environments": envs, "generated_files_skipped": skipped,
                                     "flags": flags, "seconds": round(time.time() - t0, 1)}, indent=1))
    print(f"{len(flags)} flag(s), {len(skipped)} generated file(s) skipped, {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
