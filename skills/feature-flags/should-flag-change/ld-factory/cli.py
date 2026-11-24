"""should-i-flag: should this committed change ship behind a LaunchDarkly flag?

`start` reads the committed change against its base and writes a run folder
(evidence.txt, questions.txt, the searches' task files). `decide` checks the
answers against the evidence, walks the decision tree and prints the result,
ending in a `recommend-flag` JSON block. Python 3.10+ standard library and git.

LaunchDarkly state: the agent fetches each flag the evidence needs with its
own LaunchDarkly tools and writes it to RUN/launchdarkly/
(references/LAUNCHDARKLY.md); `start` and `decide` exit 7 listing what's still
needed. --no-launchdarkly skips it.

Everything it writes goes under SHOULD_I_FLAG_RUNS when set, else
~/.cache/should-i-flag/: run folders, and repo profiles in profiles/.
Repo profiles: folders in SHOULD_I_FLAG_PROFILES (like PATH), then one a
developer wrote for the repo, else one derived from the repo with its saved
repair on top, checked against the change: lines it can't account for are
leads for the gate search (RUN/profile_leads.json), and a repair is optional
(RUN/profile_repair.txt, references/PROFILE_REPAIR.md).

Exit codes: 0 ready / decided, 2 setup problem, 4 nothing committed to check, 5 a
question must be answered again (RUN/recheck.txt), 6 can't tell which changes
are this branch's, 7 LaunchDarkly flags needed (RUN/launchdarkly-needed.txt),
8 a search must be recorded first (gates, risks, or readers, features or facts
when asked)."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import pickle
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "engine"
REPORT = ENGINE / "report"
os.environ["ODD_HOME"] = str(ENGINE)
sys.path[:0] = [str(ENGINE), str(REPORT)]

NEEDS_RECHECK, NO_UNIT, NEEDS_LD, NEEDS_GATES = 5, 6, 7, 8
CLOUD = "https://app.launchdarkly.com"


def say(label: str, text: str) -> None:
    print(f"{label}: {text}")


def fail(code: int, text: str):
    print(text, file=sys.stderr)
    raise SystemExit(code)


# The type of flag the author wants, if one is suggested: `--flag-type`, else
# "multivariate" in the PR's own text. "string/JSON flag" isn't read: in a PR
# it is as often a CLI flag.
FLAG_TYPES = ("multivariate", "string", "number", "json")
MULTIVARIATE = re.compile(r"\bmulti-?varia(?:te|nt)\b", re.I)


def stated_flag_type(flag_type: str | None, pr: dict) -> dict | None:
    if flag_type:
        return {"type": "multivariate", "value_type": None if flag_type == "multivariate" else flag_type,
                "source": "developer"}
    if pr.get("_source"):  # a commit message standing in for the PR text
        return None
    if MULTIVARIATE.search(f"{pr.get('title') or ''}\n{pr.get('body') or ''}"):
        return {"type": "multivariate", "value_type": None, "source": "pr"}
    return None


JSON_TYPE = {list: "list", str: "string", int: "number", float: "number", bool: "true/false", type(None): "null"}


def read_reply(f: Path, key: str, task: Path) -> dict:
    """A search's reply file (gates.json, risks.json, ...), the JSON object its
    task shows. A bare empty list is that object with nothing found: SKILL.md
    says "an empty list is a correct result", and an agent with nothing to
    report may write just that (EMSR-2652). Anything else that isn't an
    object fails SETUP, naming the object."""
    try:
        reply = json.loads(f.read_text())
    except ValueError as e:
        fail(2, f"SETUP: {f} is not JSON: {e}")
    if reply == []:
        return {key: []}
    if not isinstance(reply, dict):
        fail(2, f'SETUP: {f} holds a JSON {JSON_TYPE.get(type(reply), "value")}, not the object {task} shows: '
                f'{{"{key}": [...], "searched": "..."}}, with "{key}": [] when nothing was found.')
    return reply


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"git {' '.join(args)} failed")
    return r.stdout.strip()


def cache_root() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "should-i-flag"


def runs_root() -> Path:
    """Where run folders go: SHOULD_FLAG_CHANGE_RUNS (an evaluation's results
    directory, kept), else the cache."""
    return Path(os.environ.get("SHOULD_I_FLAG_RUNS") or os.environ.get("SHOULD_FLAG_CHANGE_RUNS") or cache_root())


def skill_build() -> dict:
    """This bundle's BUILD.json (name, version, graph hash), stamped on every
    run so a result names the SKILL.md and docs that produced it."""
    return {"name": "should-i-flag", "version": "0.5.3", "graph_hash": "07355490e985"}


# ---------------------------------------------------------------------------
# LaunchDarkly the agent supplies
# ---------------------------------------------------------------------------

def supplied_client(ld: dict, folder: Path):
    """An LDClient that serves flags from files the agent fetched instead of
    calling the API (the agent may have LaunchDarkly tools but no key). Each
    file is the REST shape of GET /api/v2/flags/{project}/{key}: see
    LAUNCHDARKLY.md. A flag with no file is recorded as needed."""
    from reader.sources import LDClient, from_tool_shape

    class SuppliedLD(LDClient):
        def __init__(self):
            super().__init__(ld, api_key="supplied-by-agent")
            self.folder, self.needed = folder, []

        def _get(self, path: str, **params) -> dict:
            m = re.fullmatch(r"/api/v2/flags/([^/]+)/([^/]+)", path)
            if not m:  # the audit log: never needed for today's state
                return {"_status": "not-supplied"}
            project, key = m.groups()
            f = self.folder / f"{project}__{key}.json"
            if not f.is_file():
                if (project, key) not in self.needed:
                    self.needed.append((project, key))
                return {"_status": "not-yet-fetched"}
            flag = from_tool_shape(json.loads(f.read_text()))
            if flag.get("not_found"):
                return {"_status": 404}
            # Fetched now, so each environment's state is today's: stamping
            # lastModified now makes snapshot() read it as such rather than
            # asking the audit log what it was.
            now = int(time.time() * 1000)
            for env in (flag.get("environments") or {}).values():
                env.setdefault("lastModified", now)
            return flag

    return SuppliedLD()


def ld_mode(run: Path, args_no_ld: bool, key: str) -> str:
    if args_no_ld:
        return "off"
    if key:
        return "api"
    return "supplied"


def read_key(path: str | None) -> str:
    """The API key in --key-file (evaluations only). Never read from the
    environment."""
    if not path:
        return ""
    f = Path(path)
    if not f.is_file():
        fail(2, f"SETUP: no key file {f}.")
    return f.read_text().strip()


def ld_key(man: dict) -> str:
    """The API key for a run started with --key-file: the manifest records the
    file's path, never the key."""
    f = man.get("launchdarkly_key_file")
    return Path(f).read_text().strip() if f and Path(f).is_file() else ""


def make_ld(prof, run: Path, mode: str, key: str = ""):
    from reader.sources import LDClient
    if mode == "api":
        return LDClient(prof.ld, api_key=key)
    if mode == "off":
        return LDClient(prof.ld, api_key="")
    return supplied_client(prof.ld, run / "launchdarkly")


def project_environments(prof, run: Path, mode: str, key: str = "") -> dict:
    """Which environments serve real users, for a profile that doesn't say
    (a derived one): the project's environments LaunchDarkly marks critical,
    and of those only the ones named like production (`prod` in the key) when
    there are any: a critical environment that isn't (a dogfood instance,
    say) is still read, but doesn't count as real users.
    From RUN/launchdarkly/environments.json when the agent wrote it, else read
    with the API key (and written there); without either, `deferred` (the agent
    is asked for them with the first flag it must fetch) or, with LaunchDarkly
    off, the defaults."""
    if (prof.data.get("launchdarkly") or {}).get("user_facing_production"):
        return {"source": "profile"}
    f = run / "launchdarkly" / "environments.json"
    envs = None
    if f.is_file():
        envs, source = json.loads(f.read_text()), "supplied"
    elif mode == "api":
        from reader.sources import LDClient
        c, envs, offset = LDClient(prof.ld, api_key=key), [], 0
        while True:
            r = c._get(f"/api/v2/projects/{c.project}/environments", limit=50, offset=offset)
            items = r.get("items") if isinstance(r, dict) else None
            if items is None:
                envs = None
                break
            envs += [{"key": e.get("key"), "critical": bool(e.get("critical"))} for e in items]
            offset += len(items)
            if not items or offset >= int(r.get("totalCount") or 0):
                break
        source = "api"
        if envs is not None:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(envs, indent=1) + "\n")
    if envs is None:
        return {"source": "deferred" if mode == "supplied" else "default"}
    if isinstance(envs, dict):
        envs = envs.get("environments") or envs.get("items") or []
    crit = [e["key"] for e in envs if isinstance(e, dict) and e.get("key") and e.get("critical")]
    if not crit:
        return {"source": source, "critical": [], "note": "no environment is marked critical"}
    users = [k for k in crit if "prod" in k.lower()] or crit
    main = "production" if "production" in users else users[0]
    prof.ld.update(user_facing_production=users, decision_environments=crit, main_production=main)
    return {"source": source, "critical": crit, "user_facing": users, "main": main}


def say_environments(env: dict, prof, mode: str) -> None:
    # With LaunchDarkly off, `LAUNCHDARKLY: not read` says it all: no flag is
    # read in any environment (EMSR-2642).
    if env["source"] == "profile" or mode == "off":
        return
    if env.get("critical"):
        other = [k for k in env["critical"] if k not in env["user_facing"]]
        say("LAUNCHDARKLY ENVIRONMENTS", f"real users: {', '.join(env['user_facing'])} (main: {env['main']})"
            + (f"; also read, not counted as real users: {', '.join(other)}" if other else ""))
    elif env["source"] != "deferred":
        say("LAUNCHDARKLY ENVIRONMENTS", f"only {', '.join(prof.ld['user_facing_production'])}: "
            + (env.get("note") or "the project's environments couldn't be read"))


def write_needed(run: Path, ld, env: dict | None = None) -> bool:
    """RUN/launchdarkly-needed.txt for the flags (and the project's
    environments) the agent must still fetch, printed as well: the agent acts
    on it without a call to read it."""
    needed = getattr(ld, "needed", [])
    # The environments only decide where a flag is read, so they're asked for
    # with the first flag to fetch, never alone: most changes read no flag.
    want_envs = bool(needed) and bool(env) and env.get("source") == "deferred"
    f = run / "launchdarkly-needed.txt"
    if not needed:
        f.unlink(missing_ok=True)
        return False
    head = ""
    if want_envs:
        envs = "every environment environments.json marks critical"
        head = ("First list the LaunchDarkly project's environments with your LaunchDarkly tools and\n"
                f"write them to {run / 'launchdarkly'}/environments.json as\n"
                '[{"key": "production", "critical": true}, {"key": "staging", "critical": false}, ...],\n'
                f"every environment of project {ld.project} with its key and whether it's critical.\n"
                "Only the ones marked critical are read, so the others may be left out.\n\n")
    else:
        envs = ", ".join(ld.decision_envs)
    body = ""
    if needed:
        body = (f"{'Then, for' if want_envs else 'For'} each flag below, read its targeting in {envs}:\n"
                "one call per flag and environment (a LaunchDarkly MCP server's get-flag-targeting\n"
                "tool, for one), all made together. Write each flag to\n"
                f"{run / 'launchdarkly'}/<project>__<key>.json as\n"
                '  {"key": "<key>", "environments": {"<environment>": <that call\'s result>, ...}}\n'
                "keeping the tool's own field names: no reshaping into another format. Only these are\n"
                "read: on, off_variation, fallthrough, rules (clauses, serves and disabled: a dropped\n"
                "disabled reads as a live rule), targets, context_targets, prerequisites, and one\n"
                "result's variations, as returned with each one's index (the tool may list them out\n"
                "of index order). Leave out the rest, and write a variation as just\n"
                "its index (\"off_variation\": 1) if you like.\n"
                "A flag from the REST API (GET /api/v2/flags/{project}/{key}) goes in as is too.\n"
                "An environment the flag doesn't have: leave it out.\n"
                "A flag that doesn't exist: {\"key\": \"<key>\", \"not_found\": true}.\n")
    text = (head + body + f"LaunchDarkly instance: {ld.base}\n"
            "Then run the same command again.\n\n" + "".join(f"{p}  {k}\n" for p, k in needed))
    f.write_text(text)
    say("LAUNCHDARKLY NEEDED", ("the project's environments and " if want_envs else "")
        + f"{len(needed)} flag(s), as below (also in {f})")
    print("\n" + text)
    return True


def run_environments(prof, run: Path, man: dict) -> dict | None:
    """The environments start chose, as RUN/launchdarkly/environments.json
    has them now (`deferred` until the agent writes it, with the first flag
    it fetches; the manifest then records what it wrote). None when start
    took them from the profile."""
    env = man.get("launchdarkly_environments")
    if not env:
        return None
    got = project_environments(prof, run, "off")
    if env.get("source") == "deferred" and got["source"] == "default":
        if not any(f.name != "environments.json" for f in (run / "launchdarkly").glob("*.json")):
            return env
        # flags fetched without the environments asked for with them: read
        # in the defaults, and the report says so
    if got != env:
        man["launchdarkly_environments"] = got
        (run / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    return got


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

def default_base(repo: Path) -> str:
    try:
        return git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    except RuntimeError:
        for b in ("origin/main", "origin/master"):
            try:
                git(repo, "rev-parse", "--verify", "-q", b)
                return b
            except RuntimeError:
                pass
    fail(2, "SETUP: can't tell the base branch; pass --base (e.g. origin/main).")


def load_profile_file(path):
    """A profile the agent wrote for a repo no bundled profile covers. Its
    flags live in the customer's account, not LaunchDarkly's own instance,
    unless the file says otherwise."""
    from reader.sources import Profile
    prof = Profile.from_file(path)
    if not (prof.data.get("launchdarkly") or {}).get("base_url"):
        prof.ld["base_url"] = CLOUD
    return prof


def written_profile(repo: Path) -> Path | None:
    """Where PROFILE.md says to save a profile for this repo: one per
    `origin`, outside the repo, so the developer's checkout is never touched.
    Under runs_root(), like everything else the skill writes: a sandboxed
    agent that can write only there must not fail writing ~/.cache."""
    from reader import detect_profile
    try:
        slug = detect_profile.normalize(git(repo, "remote", "get-url", "origin"))
    except (RuntimeError, ValueError):
        return None
    return runs_root() / "profiles" / (slug.replace("/", "__") + ".json")


def repair_file(repo: Path) -> Path | None:
    """The agent's saved repairs for this repo: additions to a derived profile."""
    w = written_profile(repo)
    return w.with_name(w.stem + ".repair.json") if w else None


REPO_ADDITIONS = ".launchdarkly/should-i-flag.json"


def repo_additions(repo: Path, base_sha: str | None) -> tuple[dict, str]:
    """The additions the repo itself commits in REPO_ADDITIONS, in a saved
    repair's shape ({"additions": {...}}; PROFILE_REPAIR.md), read at the
    base the change is checked against -- never at its head, so a pull
    request can't change how its own change is read. (additions, note)."""
    if not base_sha:
        return {}, ""
    try:
        text = git(repo, "show", f"{base_sha}:{REPO_ADDITIONS}")
    except RuntimeError:
        return {}, ""
    try:
        data = json.loads(text)
        adds = data.get("additions") if isinstance(data, dict) else None
        if not isinstance(adds, dict):
            raise ValueError('no "additions" object')
    except ValueError as e:
        return {}, f"; {REPO_ADDITIONS} ignored ({e})"
    return adds, ""


def resolve_profile(repo: Path, args, head_sha: str, base_sha: str | None = None):
    """(profile, its file, where it came from): --profile-file, --profile, a
    profile for this repo shipped or supplied (SHOULD_I_FLAG_PROFILES), one a
    developer wrote for it (runs_root()/profiles), else one derived from the repo at this
    commit (reader.derive_profile), with the repo's own REPO_ADDITIONS (read at
    the base) and then the saved repair's additions, those that still match
    the code, applied on top."""
    from reader import detect_profile
    from reader.sources import Profile
    if args.profile_file:
        return load_profile_file(args.profile_file), str(Path(args.profile_file).resolve()), "file"
    if args.profile:
        return Profile.load(args.profile), None, "named"
    try:
        return Profile.load(detect_profile.detect(str(repo))), None, "known"
    except SystemExit:
        pass
    saved = written_profile(repo)
    if saved and saved.is_file():
        if not json.loads(saved.read_text()).get("repaired"):
            return load_profile_file(saved), str(saved), "written"
        # An older skill saved whole repaired profiles here; they'd stop the
        # repo ever being derived again. Ignored: the check asks again.
        say("PROFILE", f"ignoring {saved}, a repaired profile from an older version; deriving instead")
    from reader import derive_profile, profile_check
    data = derive_profile.derive(repo, head_sha)
    stem = saved.stem if saved else repo.name
    folder = runs_root() / "profiles"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stem}.derived.json").write_text(json.dumps(data, indent=1) + "\n")
    rf, source, note = repair_file(repo), "derived", ""
    adds, bad = repo_additions(repo, base_sha)
    if adds:
        kept, dropped = profile_check.still_relevant(repo, head_sha, adds)
        if kept:
            data = profile_check.merged(data, kept)
            source = "derived+repo"
        note += (f", with {sum(len(v) for v in kept.values() if isinstance(v, list))} addition(s) from "
                 f"{REPO_ADDITIONS}" + (f" ({len(dropped)} left out: malformed, or no longer matching the code)" if dropped else ""))
    note += bad
    if rf and rf.is_file():
        kept, dropped = profile_check.still_relevant(repo, head_sha, json.loads(rf.read_text()).get("additions") or {})
        if kept:
            data = profile_check.merged(data, kept)
            source += "+repair"
        note += (f", with {sum(len(v) for v in kept.values() if isinstance(v, list))} saved repair addition(s)"
                + (f" ({len(dropped)} left out: malformed, or no longer matching the code)" if dropped else ""))
    path = folder / f"{stem}.profile.json"
    path.write_text(json.dumps(data, indent=1) + "\n")
    say("PROFILE", f"derived from the repo at {head_sha[:12]}{note} ({path})")
    return load_profile_file(path), str(path), source


def promisor_remote(repo: Path) -> str | None:
    """The remote a partial clone fetches its missing objects from; None for a full clone."""
    out = subprocess.run(["git", "-C", str(repo), "config", "--get-regexp",
                          r"^(extensions\.partialclone|remote\..*\.promisor)$"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        key, _, value = line.partition(" ")
        if key == "extensions.partialclone" and value:
            return value
        m = re.fullmatch(r"remote\.(.+)\.promisor", key)
        if m and value.strip().lower() == "true":
            return m.group(1)
    return None


def missing_objects(repo: Path, *revs: str) -> list[str]:
    """The objects (trees and files) of these commits' trees a partial clone
    (`git clone --filter=blob:none` or `--filter=tree:0`, usually with a
    sparse checkout) doesn't hold; none for a full clone. The evidence greps
    and reads the whole tree at head and at the merge base; in a partial
    clone those reads of files outside the checkout fail (or fetch one file
    at a time), and the evidence came out as if no caller, route or flag
    declaration existed: measured on an earlier PR, the ux-insights route
    gate above the changed page vanished from the evidence with no note, and
    the run still exited 0."""
    if not promisor_remote(repo):
        return []
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
    out = subprocess.run(["git", "-C", str(repo), "rev-list", "--objects", "--no-walk", "--missing=print", *revs],
                         capture_output=True, text=True, env=env)
    return [l[1:].strip() for l in out.stdout.splitlines() if l.startswith("?")]


def missing_files(repo: Path, *revs: str) -> int:
    return len(missing_objects(repo, *revs))


def evidence_commits(repo: Path, head_sha: str, base_sha: str) -> list[str]:
    """The commits whose trees the evidence reads: the head and the merge base, and --base's
    tip. Once the base branch has moved the merge base is none of the others, and a fresh
    partial clone holds the tip it checked out and the head, not the merge base."""
    try:
        return list(dict.fromkeys([head_sha, base_sha, git(repo, "merge-base", base_sha, head_sha)]))
    except RuntimeError:
        return [head_sha, base_sha]


FILL_ROUNDS = 8      # a missing tree only shows what's under it once it's fetched: one round per level
FILL_TIMEOUT = 300   # seconds a round's fetch may take


def fill_partial_clone(repo: Path, *revs: str) -> tuple[int, int, str]:
    """."""
    remote = promisor_remote(repo)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    fetched = 0
    for _ in range(FILL_ROUNDS):
        oids = missing_objects(repo, *revs)
        if not oids:
            return fetched, 0, ""
        try:
            r = subprocess.run(["git", "-C", str(repo), "-c", "fetch.negotiationAlgorithm=noop", "fetch", "-q",
                                remote, "--no-tags", "--no-write-fetch-head", "--recurse-submodules=no",
                                "--filter=blob:none", "--stdin"],
                               input="\n".join(oids) + "\n", capture_output=True, text=True, env=env,
                               timeout=FILL_TIMEOUT)
        except subprocess.TimeoutExpired:
            return fetched, len(oids), f"fetching from {remote} took over {FILL_TIMEOUT}s"
        if r.returncode != 0:
            err = (r.stderr.strip().splitlines() or ["no message"])[-1]
            return fetched, len(oids), f"fetching from {remote} failed: {err}"
        left = missing_objects(repo, *revs)
        if set(left) & set(oids):
            return fetched, len(left), f"{remote} didn't send {len(set(left) & set(oids))} of them"
        fetched += len(oids)
    left = missing_objects(repo, *revs)
    return fetched, len(left), (f"still missing after {FILL_ROUNDS} rounds" if left else "")


def start(args) -> int:
    from reader.mechanical import build_packet
    from reader.read import build_manifest
    from reader.sources import Profile, Repo
    import classify

    repo = Path(args.repo).resolve()
    try:
        git(repo, "rev-parse", "--git-dir")
    except RuntimeError:
        fail(3, f"NOT A REPO: {repo} is not a git checkout.")
    base = args.base or default_base(repo)
    head = args.head or "HEAD"
    try:
        head_sha, base_sha = git(repo, "rev-parse", head), git(repo, "rev-parse", base)
    except RuntimeError as e:
        fail(2, f"SETUP: {e}")
    if git(repo, "rev-list", "--count", f"{base_sha}..{head_sha}") == "0":
        fail(4, f"NOTHING TO CHECK: {head} has no commits that aren't on {base}. "
                "Commit the change (a WIP commit is fine) and run again.")
    read_at = evidence_commits(repo, head_sha, base_sha)
    if missing_files(repo, *read_at):
        fetched, missing, short = fill_partial_clone(repo, *read_at)
        if missing:
            fail(2, f"SETUP: {repo} is a partial clone: {missing} file(s) at the change's commit or the version it "
                    f"is compared with aren't in it ({short}), and the evidence reads files the change doesn't "
                    "touch (callers, routes, flag declarations), so it would miss flags that already gate the "
                    "change. Clone the repository again without --filter, keeping its full history (no --depth: the "
                    "diff needs the merge base), check out the same commit, and run start again.")
        say("PARTIAL CLONE", f"fetched the {fetched} object(s) it lacked at the change's commit and its base")
    prof, profile_file, profile_source = resolve_profile(repo, args, head_sha, base_sha)
    say("CHECKING", f"{head} ({head_sha[:12]}) against {base}, profile {prof.name}")
    dirty = git(repo, "status", "--porcelain", "--untracked-files=no")
    if dirty and head == "HEAD":
        say("UNCOMMITTED", f"{len(dirty.splitlines())} changed file(s) aren't committed "
                           "and aren't part of this check (untracked files never are)")
    commits = git(repo, "rev-list", "--count", f"{base_sha}..{head_sha}")
    files = git(repo, "diff", "--name-only", f"{base_sha}...{head_sha}").splitlines()
    say("CHANGE", f"{commits} commit(s), {len(files)} file(s) not on {base}: all of it is checked "
                  "as one change, the way a pull request shows it")

    _, _, _, graph = classify.load()
    run = runs_root() / f"{repo.name}-{head_sha[:12]}-{base_sha[:12]}-{graph}"
    run.mkdir(parents=True, exist_ok=True)
    (run / "launchdarkly").mkdir(exist_ok=True)

    pr = {}
    if args.pr_title:
        pr["title"] = args.pr_title
    if args.pr_body_file:
        # Bytes as written: read_text() would turn GitHub's \r\n into \n, and
        # the evidence would no longer match ODD's for the same PR.
        pr["body"] = Path(args.pr_body_file).read_bytes().decode("utf-8", "replace")[:8000]
    if not pr:
        pr = {"title": git(repo, "log", "-1", "--format=%s", head_sha),
              "body": git(repo, "log", "-1", "--format=%b", head_sha)[:8000],
              "_source": "commit message (no PR text supplied)"}
        say("PR TEXT", "none given, so the last commit's message stands in for it")
    flag_type = stated_flag_type(args.flag_type, pr)
    if flag_type:
        say("FLAG TYPE", f"{flag_type['value_type'] or 'multivariate'}"
                         f"{' (multivariate)' if flag_type['value_type'] else ''}, as "
                         f"{'you asked' if flag_type['source'] == 'developer' else 'the PR text asks'}, "
                         "if a new flag is suggested")

    key = read_key(args.key_file)
    mode = ld_mode(run, args.no_launchdarkly, key)
    env = project_environments(prof, run, mode, key)
    say_environments(env, prof, mode)
    ld = make_ld(prof, run, mode, key)
    merged = args.as_of or datetime.now(timezone.utc).date().isoformat()
    if args.as_of and mode == "supplied":
        fail(2, "SETUP: --as-of needs --key-file (past flag state comes from the audit log).")
    with contextlib.redirect_stdout(io.StringIO()):
        pkt, answers = build_packet(Repo(repo), prof, head_sha, base, pr, ld, merged)
    from reader import risk_search
    answers["P30"] = risk_search.pending()
    for stale in ("profile_check.json", "profile_leads.json", "profile_repair.txt"):
        (run / stale).unlink(missing_ok=True)
    if profile_source.startswith("derived") or profile_source == "written":
        check_profile_reading(run, repo, prof, profile_file, profile_source, pkt, ld)
    if write_needed(run, ld, env):
        say("RUN", str(run))
        return NEEDS_LD

    man = build_manifest(pkt, answers, prof.name, args.pr_url)
    man.update({"profile_file": profile_file, "pr_text": pr, "flag_type": flag_type, "merged": merged,
                "repo_path": str(repo), "launchdarkly": mode, "skill": skill_build()})
    if mode == "api":
        man["launchdarkly_key_file"] = str(Path(args.key_file).resolve())
    if env["source"] != "profile":
        man["launchdarkly_environments"] = env
    (run / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    (run / "repo_path").write_text(str(repo) + "\n")
    # The packet itself, so merging after each answer needn't rebuild it from
    # the checkout (merge_inline.PACKET_LOADER checks its hash first).
    (run / "packet.pickle").write_bytes(pickle.dumps(pkt))
    # Client repositories the consumer search may read (step 4), pinned to
    # their default branch as of the base commit.
    from reader import consumer_search
    from reader.sources import PROFILES
    from reader.sources import profile_dirs
    bundled = [Profile.load(p.stem).data for d in profile_dirs() for p in sorted(d.glob("*.json"))
               if not p.stem.startswith("_")]
    man["clients"] = consumer_search.clients(repo, git(repo, "merge-base", base_sha, head_sha),
                                             args.client_repo or [], bundled)
    (run / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    man["searches"] = (["features"] if os.environ.get("ODD_FEATURE_SEARCH") == "1" else []) + ["facts"]
    (run / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    for stale in ("replies.json", "answers.json", "asked.json", "recheck.txt", "gates.json", "gates-verified.json",
                  "risks.json", "risks-verified.json", "consumers.json", "consumers-verified.json",
                  "consumer_search.txt", "features.json", "features-verified.json", "feature_search.txt",
                  "facts.json", "facts-verified.json", "fact_search.txt", "fact_search.json",
                  "profile_fix.json", "profile_attempts",
                  "profile_repaired", "profile_repair_failed"):
        (run / stale).unlink(missing_ok=True)  # a fresh start answers afresh
    # The gate search (SKILL.md step 2): the agent looks for flags gating the
    # change from where the reader can't trace (routes, helpers, handlers,
    # styles); `gates` checks what it reports.
    (run / "gate_search.txt").write_text(with_leads(
        (HERE.parent / "references" / "GATES.md").read_text().replace("{CLIENTS}", clients_block(man["clients"]))
        .replace("{CHECKOUT}", str(repo)).replace("{HEAD}", head_sha)
        .replace("{BASE}", git(repo, "merge-base", base_sha, head_sha)).replace("{RUN}", str(run))
        .replace("{SKILL_DIR}", str(HERE.parent)), run))
    (run / "risk_search.txt").write_text(
        (HERE.parent / "references" / "RISK.md").read_text().replace("{CHECKOUT}", str(repo)).replace("{HEAD}", head_sha)
        .replace("{BASE}", git(repo, "merge-base", base_sha, head_sha)).replace("{RUN}", str(run))
        .replace("{SKILL_DIR}", str(HERE.parent)))
    say("RUN", str(run))
    say("LAUNCHDARKLY", {"api": "read with the key in --key-file",
                         "supplied": f"read from {len(list((run / 'launchdarkly').glob('*.json')))} "
                                     "flag(s) you fetched",
                         "off": "not read (--no-launchdarkly): questions about flag "
                                "state come back unclear"}[mode])
    u1 = answers.get("U1", {}).get("value")
    if u1 is not True:
        fail(NO_UNIT, "CAN'T TELL WHICH CHANGES ARE THIS BRANCH'S: "
                      + str(answers.get("U1", {}).get("evidence", "")))

    import explain
    with contextlib.redirect_stdout(io.StringIO()) as out:
        explain.render(run)
    try:  # best effort: only adds NEARBY FLAGS to the report
        with contextlib.redirect_stdout(io.StringIO()):
            explain.neighbors(run)
    except Exception as e:  # noqa: BLE001
        (run / "neighbors.log").write_text(f"{type(e).__name__}: {e}\n")
    # The first question, as `next` would print it: no call to ask for it.
    return next_question(run)


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------

def check_profile_reading(run: Path, repo: Path, prof, profile_file: str, source: str, pkt, ld) -> None:
    """For a profile this skill made (derived, with any saved repair) or a
    developer wrote: does it find this change's flag checks? It never stops
    the run. What it can't account for -- a flag key written in a changed file
    with no flag check the profile recognizes (a gap), a line it reads as a
    check for a key LaunchDarkly has no flag for (a suspect) -- is written to
    RUN/profile_leads.json, noted in the evidence (PACKET NOTES), and the gaps
    are handed to the gate search as leads (GATES.md, `with_leads`). For a
    derived profile, RUN/profile_repair.txt offers a repair (PROFILE_REPAIR.md):
    optional, for when the leads are many or the same helper keeps coming up."""
    from reader import profile_check
    from reader.sources import Repo, build_symbol_table
    st = build_symbol_table(Repo(repo), prof, pkt.unit["head"])
    ld_keys = profile_check.project_keys(ld)
    rep = profile_check.check(Repo(repo), pkt, st, ld_keys, prof)
    rep.update({"profile_file": profile_file, "source": source, "head": pkt.unit["head"],
                "paths": [f["path"] for f in pkt.files], "repo_path": str(repo)})
    (run / "profile_check.json").write_text(json.dumps(rep, indent=1) + "\n")
    ld_note = ("LaunchDarkly not read, so only the profile's own keys were checked"
               if rep["ld_keys"] is None else f"{rep['ld_keys']} flags in the LaunchDarkly project")
    if not rep["n_gaps"] + rep["n_suspects"]:
        say("PROFILE CHECK", f"the profile finds this change's flag checks ({ld_note})")
        return
    (run / "profile_leads.json").write_text(json.dumps(
        {k: rep[k] for k in ("gaps", "suspects", "n_gaps", "n_suspects", "ld_keys")}, indent=1) + "\n")
    # In the evidence, so every question knows the flag sites may be
    # incomplete. No run path: the evidence is the same wherever it runs.
    found = [f"finds no flag check near {rep['n_gaps']} flag key(s) written in the changed files (each a "
             "check through a helper it doesn't recognize, or no check at all: a log field, a config name, "
             "a test value; the gate search follows them as leads)" if rep["n_gaps"] else "",
             f"reads {rep['n_suspects']} line(s) as checks for keys LaunchDarkly has no flag for (perhaps "
             "not flag checks)" if rep["n_suspects"] else ""]
    found = [x for x in found if x]
    pkt.notes.append("the flag evaluation sites may be incomplete: the repository profile " + "; and it ".join(found))
    repair = ""
    if source != "written":
        lines = ([f"- GAP {g['path']}:{g['line']} `{g['key']}`: {g['text']}" for g in rep["gaps"]] +
                 [f"- SUSPECT {s['path']}:{s['line']} `{s['key']}`: {s['text']}" for s in rep["suspects"]])
        doc = (HERE.parent / "references" / "PROFILE_REPAIR.md")
        (run / "profile_repair.txt").write_text(
            doc.read_text().replace("](PROFILE.md)", f"]({doc.with_name('PROFILE.md')})").replace("{CHECKOUT}", str(repo))
            .replace("{HEAD}", pkt.unit["head"]).replace("{RUN}", str(run)).replace("{PROFILE}", profile_file)
            .replace("{FINDINGS}", "\n".join(lines) or "- (none listed)").replace("{LD}", ld_note))
        repair = f". A profile repair is optional ({run / 'profile_repair.txt'})"
    say("PROFILE CHECK", f"{rep['n_gaps']} flag key(s) in the changed files with no flag check the profile "
                         f"recognizes, {rep['n_suspects']} check(s) for keys LaunchDarkly has no flag for "
                         f"({ld_note}); continuing: they're in {run / 'profile_leads.json'}"
                         + (", and the gaps are leads for the gate search" if rep["n_gaps"] else "") + repair)


def with_leads(text: str, run: Path) -> str:
    """The gate search's task with the profile check's gaps as LEADS
    (GATES.md): its LEADS section filled in, or left out when there are none.
    The section is one paragraph block, ended by a blank line."""
    f = run / "profile_leads.json"
    gaps = json.loads(f.read_text())["gaps"] if f.is_file() else []
    if not gaps:
        return re.sub(r"\nLEADS FROM THE PROFILE CHECK\n.*?\n\n", "\n", text, count=1, flags=re.S)
    n = json.loads(f.read_text())["n_gaps"]
    lines = [f"- {g['path']}:{g['line']} `{g['key']}`: {g['text']}" for g in gaps]
    if n > len(gaps):
        lines.append(f"- ... and {n - len(gaps)} more, not listed")
    return text.replace("{LEADS}", "\n".join(lines))


def profile_cmd(args) -> int:
    """Check the agent's optional profile repair (RUN/profile_fix.json) and add
    its additions to this repo's saved repair, which `start` applies on top of
    the derived profile from then on. A fix that doesn't hold is dropped with
    the reason; after two, or whenever the agent stops trying, the run goes on
    as `start` left it: it was ready, with the leads, either way."""
    from reader import profile_check
    from reader.mechanical import flag_sites
    from reader.sources import Profile, Repo, build_symbol_table
    run = Path(args.run).resolve()
    rep = json.loads((run / "profile_check.json").read_text())
    f = run / "profile_fix.json"
    if not f.is_file():
        fail(2, f"SETUP: write the repair's JSON to {f} first ({run / 'profile_repair.txt'}).")
    try:
        fix = json.loads(f.read_text())
    except ValueError as e:
        fail(2, f"SETUP: {f} is not JSON: {e}")
    repo, head = Repo(Path(rep["repo_path"])), rep["head"]
    prof = load_profile_file(rep["profile_file"])

    def sites_at(p):
        st = build_symbol_table(repo, p, head)
        return flag_sites(repo, p, st, head, rep["paths"], imported_helpers=True, method_helpers=True)

    attempts = run / "profile_attempts"
    n = int(attempts.read_text()) + 1 if attempts.is_file() else 1
    attempts.write_text(str(n))
    res = profile_check.verify_fix(repo, head, Profile, prof, fix, rep, sites_at)
    dest = repair_file(Path(rep["repo_path"])) or Path(rep["profile_file"]).with_name("repair.json")
    if res["ok"]:
        old = json.loads(dest.read_text()) if dest.is_file() else {}
        data = {"additions": profile_check.merge_additions(old.get("additions") or {}, fix.get("additions") or {}),
                "updated_at": head}
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, indent=1) + "\n")
        (run / "profile_repaired").write_text(head + "\n")
        say("PROFILE", f"repair verified; its additions are saved in {dest} and applied to this repo's "
                       "derived profile from now on")
    elif n >= 2:
        (run / "profile_repair_failed").write_text("\n".join(res["problems"][:5]) + "\n")
        say("PROFILE", "the repair didn't hold twice; this run goes on with the profile it had ("
            + "; ".join(res["problems"][:3]) + ")")
        say("NEXT", f"ld-factory next {run}")
        return 0
    else:
        say("PROFILE REPAIR DROPPED", "; ".join(res["problems"][:5])
            + f". Fix profile_fix.json and run ld-factory profile {run} once more, or leave the repair: "
              f"the run is ready as it is (ld-factory next {run})")
        return 0
    say("NEXT", "run the same start command again, to read the change with the repaired profile")
    return 0


def merge(run: Path, man: dict) -> int:
    """The answers so far, checked: citations, rechecks, the gate re-read
    (merge_inline). Writes answers.json; 0, NEEDS_RECHECK or NEEDS_LD."""
    from reader import merge_inline
    from reader.sources import Profile
    prof = (load_profile_file(man["profile_file"]) if man.get("profile_file")
            else Profile.load(man["profile"]))
    env = run_environments(prof, run, man)  # the environments start chose (RUN/launchdarkly/)
    clients = []

    def factory(_prof):
        c = make_ld(prof, run, man.get("launchdarkly") or "off", ld_key(man))
        clients.append(c)
        return c

    merge_inline.LD_FACTORY = factory

    def kept_packet(m):
        f = run / "packet.pickle"
        return pickle.loads(f.read_bytes()) if f.is_file() else None

    merge_inline.PACKET_LOADER = kept_packet
    if "P30" not in man["mechanical"]:
        # A run started before the risk search existed: nothing was searched,
        # which is NO -- the verdict the rest of the tree reaches stands.
        from reader import risk_search
        man["mechanical"]["P30"] = {**risk_search.answer([], []),
                                    "evidence": "not searched: the run predates the risk search"}
        (run / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    if not (run / "replies.json").is_file():
        (run / "replies.json").write_text(json.dumps({"answers": {}}, indent=2) + "\n")
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        code = merge_inline.main([str(run / "manifest.json"), str(run / "replies.json"),
                                  "-o", str(run / "answers.json"),
                                  "--repo", man["repo_path"], "--merged", man["merged"]])
    (run / "merge.log").write_text(log.getvalue())
    if code == NEEDS_RECHECK:
        pid = re.search(r'"rechecks": \{"(\w+)"', (run / "recheck.txt").read_text())
        say("RECHECK", f"one question is asked again, below. Answer it with: "
                       f"ld-factory answer {run} {pid.group(1) if pid else '<id>'} --recheck")
        print((run / "recheck.txt").read_text())
        return NEEDS_RECHECK
    if code:
        fail(2, f"SETUP: merging the answers failed:\n{log.getvalue()}")
    for c in clients:
        if write_needed(run, c, env):
            return NEEDS_LD
    reuse_questions(run, man)
    # The searches the walk asks for once it needs them, in this order: the
    # feature flag search decides which reuse questions are asked at all, the
    # consumer search settles P19, and a fact search any other question whose
    # unresolved answer decides the result.
    for step in (settle_features, settle_contract, settle_facts):
        code = step(run, man)
        if code:
            return code
    return 0


def reuse_questions(run: Path, man: dict) -> None:
    """P10/P12/P13 name the candidates they may use (P11's still-withheld
    keys). When a P6 YES made its enclosing gate a candidate
    (mechanical.enclosing_gate_candidates), the questions are rendered again
    with it, so the next one asked names the gate. P13 also names the gate
    when P33, re-read from it, finds it still holding the change back in
    main production."""
    from reader.read import build_manifest
    ans = json.loads((run / "answers.json").read_text())["answers"]
    p11, p33 = ans.get("P11") or {}, ans.get("P33") or {}
    if (p11.get("from_enclosure") != "P6" and p33.get("from_enclosure") != "P6") \
            or not (run / "packet.pickle").is_file():
        return
    mech = {**man["mechanical"], **{k: ans[k] for k in ("P9", "P11", "P33")
                                    if (ans.get(k) or {}).get("from_enclosure") == "P6"}}
    for k in ("P10", "P12"):  # P12/P13's scope follows the answers given so far
        if ans.get(k, {}).get("evidence") not in (None, "not answered"):
            mech[k] = ans[k]
    pkt = pickle.loads((run / "packet.pickle").read_bytes())
    new = build_manifest(pkt, mech, man["profile"], man.get("pr"))
    changed = [q for q in ("P10", "P12", "P13")
               if q in new["questions"] and new["questions"][q] != man["questions"].get(q)]
    if changed:
        man["questions"].update({q: new["questions"][q] for q in changed})
        (run / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")


def settle_contract(run: Path, man: dict) -> int:
    """P19 left unresolved by an answer, once it decides the result: the
    consumer search settles it (CONSUMERS.md). Asks for the search (exit 8)
    until RUN/consumers-verified.json is recorded, then rewrites P19 in
    answers.json from it: YES when a reader verified, else NO."""
    from reader import consumer_search, specload
    from reader.read import lazy_needed
    import classify
    f = run / "answers.json"
    doc = json.loads(f.read_text())
    a = doc["answers"].get("P19") or {}
    if str(a.get("value")).upper() != "UNRESOLVED" or a.get("evidence") == "not answered":
        return 0
    if "clients" not in man:
        return 0  # a run started before the consumer search existed: P19 stays unresolved
    tree = specload.load(Path(os.environ["ODD_HOME"]) / "tree.yaml")
    given = {p: x for p, x in doc["answers"].items() if x.get("evidence") != "not answered"}
    if lazy_needed(tree, given) is not None:
        return 0  # other questions come first; P19 may not matter yet
    vals = {p: (classify.UNRESOLVED if str(x["value"]).upper() == "UNRESOLVED" else bool(x["value"]))
            for p, x in given.items()}
    missing = {n["predicate"] for n in tree["nodes"]} - set(given)
    now = classify.settle(classify.explore_tree(tree, vals, missing))
    if now is not None and now["verdict"] != "escalate":
        return 0  # every answer to P19 gives the same result
    yes, no = (classify.settle(classify.explore_tree(tree, {**vals, "P19": v}, missing)) for v in (True, False))
    if yes is not None and no is not None and (yes["verdict"], yes["terminal"]) == (no["verdict"], no["terminal"]):
        return 0
    v = run / "consumers-verified.json"
    if not v.is_file():
        write_consumer_task(run, man)
        say("CONSUMER SEARCH NEEDED", f"one question can't be settled from the evidence: follow "
                                      f"{run / 'consumer_search.txt'}, write its JSON to {run / 'consumers.json'}, "
                                      f"then run ld-factory readers {run}")
        return NEEDS_GATES
    rec = json.loads(v.read_text())
    doc["answers"]["P19"] = consumer_search.settle(a, rec["contract_changes"], [c["name"] for c in rec["clients"]])
    f.write_text(json.dumps(doc, indent=2) + "\n")
    return 0


def settle_features(run: Path, man: dict) -> int:
    """The feature flag search (FEATURES.md), once the walk reaches the reuse
    questions and leaves them with no candidate covering the change
    (feature_search.needed): asks for it (exit 8) until
    RUN/features-verified.json is recorded. `features` adds what verifies to
    the reuse candidates."""
    from reader import feature_search, specload
    if "features" not in (man.get("searches") or []) or (run / "features-verified.json").is_file():
        return 0
    answers = json.loads((run / "answers.json").read_text())["answers"]
    if not feature_search.needed(specload.load(Path(os.environ["ODD_HOME"]) / "tree.yaml"), answers):
        return 0
    write_feature_task(run, man, answers)
    say("FEATURE SEARCH NEEDED", f"no flag near the change covers it: find the flag that releases the feature it "
                                 f"belongs to. Follow {run / 'feature_search.txt'}, write its JSON to "
                                 f"{run / 'features.json'}, then run ld-factory features {run}")
    return NEEDS_GATES


def write_feature_task(run: Path, man: dict, answers: dict) -> None:
    repo, head, base = man["repo_path"], man["unit"]["head"], man["unit"]["merge_base"]
    shown = [f"- {p}: {' '.join(str(answers[p].get('evidence') or '').split())[:400]}"
             for p in ("P9", "P11", "P10", "P12") if p in answers and answers[p].get("evidence") != "not answered"]
    (run / "feature_search.txt").write_text(
        (HERE.parent / "references" / "FEATURES.md").read_text().replace("{CHECKOUT}", repo).replace("{HEAD}", head)
        .replace("{BASE}", base).replace("{RUN}", str(run)).replace("{SKILL_DIR}", str(HERE.parent))
        .replace("{CANDIDATES}", "\n".join(shown) or "- (none)"))


def settle_facts(run: Path, man: dict) -> int:
    """A fact search (FACTS.md) for the first question the answerer left
    unresolved that decides the result (fact_search.pick): asks for it
    (exit 8); `facts` checks what it finds and, when a finding verifies,
    puts the question to the answerer once more with it. Once per question
    per run. An answer given again after a search carries the search's
    record (`fact_search`), so a NO or YES resting on it says so."""
    from reader import fact_search, specload
    if "facts" not in (man.get("searches") or []):
        return 0
    f = run / "answers.json"
    doc = json.loads(f.read_text())
    replies = json.loads((run / "replies.json").read_text())
    vf = run / "facts-verified.json"
    done = json.loads(vf.read_text()) if vf.is_file() else {}
    marked = False
    for pid, rec in done.items():
        a = doc["answers"].get(pid)
        if a and a.get("evidence") != "not answered" and pid in (replies.get("before_fact_search") or {}):
            a["fact_search"] = fact_search.record(rec)
            marked = True
    if marked:
        f.write_text(json.dumps(doc, indent=2) + "\n")
    preds = {p["id"]: p for p in specload.load(Path(os.environ["ODD_HOME"]) / "predicates.yaml")["predicates"]}
    tree = specload.load(Path(os.environ["ODD_HOME"]) / "tree.yaml")
    pid = fact_search.pick(tree, preds, doc["answers"], replies, set(man["mechanical"]), set(done))
    if pid is None:
        return 0
    write_fact_task(run, man, pid, preds[pid], doc["answers"][pid])
    say("FACT SEARCH NEEDED", f"one question was answered unresolved and the result depends on it ({pid}): search "
                              f"the code for what was missing. Follow {run / 'fact_search.txt'}, write its JSON to "
                              f"{run / 'facts.json'}, then run ld-factory facts {run}")
    return NEEDS_GATES


def write_fact_task(run: Path, man: dict, pid: str, pred: dict, ans: dict) -> None:
    from reader import fact_search
    subs = {"CHECKOUT": man["repo_path"], "HEAD": man["unit"]["head"], "BASE": man["unit"]["merge_base"],
            "RUN": str(run), "SKILL_DIR": str(HERE.parent)}
    (run / "fact_search.txt").write_text(fact_search.task(
        (HERE.parent / "references" / "FACTS.md").read_text(), pid, pred, man["questions"].get(pid, ""), ans, subs))
    (run / "fact_search.json").write_text(json.dumps(
        {"question": pid, "answer": {k: ans.get(k) for k in ("value", "evidence", "citations")}}, indent=1) + "\n")


def clients_block(cl: list[dict]) -> str:
    """The client checkouts a search may read, each at its pinned commit, with
    the exact commands to read them (the consumer and gate searches)."""
    return ("\n".join(f"- {c['name']}: checkout {c['path']}, commit {c['rev']}. Read only as "
                       f"`git -C {c['path']} show {c['rev']}:<path>` and "
                       f"`git -C {c['path']} grep -n <pattern> {c['rev']} -- <paths>`." for c in cl)
            or "- None is available here: search this repository only.")


def write_consumer_task(run: Path, man: dict) -> None:
    repo, head, base = man["repo_path"], man["unit"]["head"], man["unit"]["merge_base"]
    block = clients_block(man.get("clients") or [])
    (run / "consumer_search.txt").write_text(
        (HERE.parent / "references" / "CONSUMERS.md").read_text().replace("{CLIENTS}", block).replace("{CHECKOUT}", repo)
        .replace("{HEAD}", head).replace("{BASE}", base).replace("{RUN}", str(run)))


# The first questions (does the unit resolve, does anything ship, does it change
# what the product does, is it only a flag cleanup or a data-prep step) read
# nothing the gate and risk searches add. A change the walk settles there never
# needs the searches; one that gets past them does, before the next question.
EARLY = frozenset({"U1", "P1", "P2", "P3", "P4"})


def early_state(run: Path, man: dict):
    """(next question or None, settled early): the walk on the answers so far,
    and whether its result rests on the first questions alone."""
    from reader import specload
    from reader.read import lazy_needed
    import classify
    code = merge(run, man)
    if code:
        return code, False
    tree = specload.load(Path(os.environ["ODD_HOME"]) / "tree.yaml")
    answers = json.loads((run / "answers.json").read_text())["answers"]
    given = {p: a for p, a in answers.items() if a.get("evidence") != "not answered"}
    pid = lazy_needed(tree, given)
    if pid is not None:
        return pid, False
    vals = {p: (classify.UNRESOLVED if str(a["value"]).upper() == "UNRESOLVED" else bool(a["value"]))
            for p, a in given.items()}
    steps, term = classify.resolve_tree(tree, vals)[:2]
    return None, all(st["predicate"] in EARLY for st in steps) and not str(term).startswith("E-UNRESOLVED")


def searches_needed(run: Path) -> bool:
    if gates_recorded(run):
        return False
    pid, early = early_state(run, json.loads((run / "manifest.json").read_text()))
    if isinstance(pid, int):
        return False  # merge asked for something else first (a recheck, LaunchDarkly)
    return not (early or pid in EARLY)


INLINE_MAX = 40_000


def say_searches(run: Path) -> None:
    say("SEARCHES NEEDED", f"the questions now get past whether the change ships and changes behavior: record "
                           f"both searches first: {run / 'gate_search.txt'} then ld-factory gates {run}; "
                           f"{run / 'risk_search.txt'} then ld-factory risks {run}")
    tasks = [(t.name, t.read_text()) for t in (run / "gate_search.txt", run / "risk_search.txt") if t.is_file()]
    if tasks and sum(len(body) for _, body in tasks) <= INLINE_MAX:
        for name, body in tasks:
            print(f"\n===== {name} =====\n{body}")


def next_question(run: Path) -> int:
    if searches_needed(run):
        say_searches(run)
        return NEEDS_GATES
    return _next_question(run)


def _next_question(run: Path) -> int:
    """The next question the walk needs, or DECIDED once every answer that
    could change the result is in. Questions past that point are never asked
    (reader.read's lazy walk: past an unresolved answer both branches are
    followed, and only while they could still agree)."""
    man = json.loads((run / "manifest.json").read_text())
    code = merge(run, man)
    if code:
        return code
    from reader import specload
    from reader.read import lazy_needed
    import explain
    answers = json.loads((run / "answers.json").read_text())["answers"]
    given = {p: a for p, a in answers.items() if a.get("evidence") != "not answered"}
    pid = lazy_needed(specload.load(Path(os.environ["ODD_HOME"]) / "tree.yaml"), given)
    replies = json.loads((run / "replies.json").read_text())
    last = False
    if pid is None:
        pid = next((q["id"] for q in explain.report_questions()
                    if q["id"] not in replies.get("answers", {})), None)
        if pid is None:
            say("DECIDED", f"every answer the result depends on is in. Run: ld-factory decide {run}")
            return 0
        q = next(q for q in explain.report_questions() if q["id"] == pid)
        text = explain.report_question_text(q)
        say("REPORT-ONLY QUESTION", f"{pid}: it goes in the report and never changes the result")
        last = all(r["id"] in replies.get("answers", {}) or r["id"] == pid for r in explain.report_questions())
    else:
        text = man["questions"][pid]
        if pid in (replies.get("before_fact_search") or {}):
            say("ASKED AGAIN", f"{pid} is asked once more, with what the fact search found (FACT SEARCH FINDINGS "
                               "below): answer it again by its procedure")
        elif pid in (replies.get("before_feature_search") or {}):
            say("ASKED AGAIN", f"{pid} is asked once more: the feature flag search added a reuse candidate "
                               "(FEATURE FLAG SEARCH below): answer it again by its procedure")
    asked = json.loads((run / "asked.json").read_text()) if (run / "asked.json").is_file() else []
    if pid not in asked:
        (run / "asked.json").write_text(json.dumps(asked + [pid]) + "\n")
    if last:
        # Nothing is asked after it: decide in the same call. A command of
        # its own, after the heredoc, so the record stays in a `decide`
        # command's output, where the online judge and tune look for it.
        say("QUESTION", f"{pid}, the last one. Answer it and decide in one command, the answer as JSON on stdin:\n"
                        f"  ld-factory answer {run} {pid} <<'JSON'\n  {{...}}\n  JSON\n  ld-factory decide {run}")
    else:
        say("QUESTION", f"{pid} (answer with: ld-factory answer {run} {pid}, the answer as JSON on stdin)")
    print("\n" + text)
    return 0


def gates(args) -> int:
    """Check the gate search's reply (RUN/gates.json) and add what holds to the
    evidence: each verified gate becomes a `searched` caller-gate entry, so
    P6 and P12 see it and may cite its lines, and its key's LaunchDarkly state
    is read like any other gate's. Every link is checked at head; a gate with
    one link that doesn't match is dropped, and said so. A caller coverage
    (`covered_units`) is checked the same way and for completeness
    (gate_search.verify_coverage), and shown to P6 and P12 when it holds; its
    callers in a client repository (man["clients"]) are checked in that
    checkout at its pinned revision, which is searched for other callers
    too, and their flags carry that client's LaunchDarkly project. A data
    gate (`data_gates`: changed code that only acts on records whose every
    writer is behind a flag) is checked the same way, the data's name
    searched for every other use (gate_search.verify_data_gate), and shown
    to P5, P6 and P12 when it holds."""
    from reader import gate_search
    from reader.read import build_manifest
    run = Path(args.run).resolve()
    man = json.loads((run / "manifest.json").read_text())
    f = run / "gates.json"
    if not f.is_file():
        fail(2, f"SETUP: write the gate search's JSON to {f} first ({run / 'gate_search.txt'}).")
    reply = read_reply(f, "gates", run / "gate_search.txt")
    repo, head, base = man["repo_path"], man["unit"]["head"], man["unit"]["merge_base"]
    pkt = pickle.loads((run / "packet.pickle").read_bytes())
    pkt.caller_gates = [g for g in pkt.caller_gates  # a rerun replaces
                        if g.get("kind") not in ("searched", "coverage", "covered", "data", "data-line")]
    changed = {x["path"] for x in pkt.files}
    # flag key -> changed path -> the lines where the evidence shows its check
    sited: dict[str, dict[str, set[int]]] = {}
    for site in pkt.flag_sites_head or []:
        if site.get("key") and site["path"] in changed:
            sited.setdefault(site["key"], {}).setdefault(site["path"], set()).add(site["line"])
    files: dict = {}
    kept, dropped = [], []
    for g in reply.get("gates") or []:
        why = gate_search.verify(repo, head, g, files)
        if why:
            dropped.append({**g, "dropped": why})
            continue
        kept.append(g)
        pkt.caller_gates += gate_search.entries(g, changed, gate_search.key_at(repo, base, g["key"]),
                                                sited.get(g["key"], {}))
    # Caller coverage (GATES.md): every caller of a changed unit, each behind
    # a flag or leaving the new behavior off, checked complete against head.
    from reader.sources import Profile
    prof = (load_profile_file(man["profile_file"]) if man.get("profile_file")
            else Profile.load(man["profile"]))
    not_shipping = gate_search.not_shipping_fn(prof)
    # Callers in a client repository (man["clients"], pinned at start) are
    # checked in that checkout at its pinned revision, which is searched for
    # every other use too; their flags are read from its LaunchDarkly project.
    clients = gate_search.client_repos(man.get("clients"))
    cov_kept, cov_dropped = [], []
    for c in reply.get("covered_units") or []:
        why = (gate_search.verify_coverage(repo, head, c, files, changed, not_shipping, clients,
                                           gate_search.generated_fn(prof))
               if isinstance(c, dict) else "not an object")
        if why:
            cov_dropped.append({**(c if isinstance(c, dict) else {"claim": c}), "dropped": why})
            continue
        cov_kept.append(c)
        pkt.caller_gates += gate_search.coverage_entries(c, changed, lambda k: gate_search.key_at(repo, base, k),
                                                         clients)
    data_kept, data_dropped = [], []
    for c in reply.get("data_gates") or []:
        why = (gate_search.verify_data_gate(repo, head, c, files, changed, not_shipping)
               if isinstance(c, dict) else "not an object")
        if why:
            data_dropped.append({**(c if isinstance(c, dict) else {"claim": c}), "dropped": why})
            continue
        data_kept.append(c)
        pkt.caller_gates += gate_search.data_entries(c, changed, lambda k: gate_search.key_at(repo, base, k))
    new = build_manifest(pkt, man["mechanical"], man["profile"], man.get("pr"))
    if new["packet_hash"] != man["packet_hash"]:
        fail(2, "SETUP: adding gates changed the evidence itself; only P6/P12's questions should change.")
    man.update({"questions": new["questions"], "citation_context": new["citation_context"]})
    (run / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    (run / "packet.pickle").write_bytes(pickle.dumps(pkt))
    (run / "gates-verified.json").write_text(json.dumps(
        {"verified": kept, "dropped": dropped, "covered_verified": cov_kept, "covered_dropped": cov_dropped,
         "data_verified": data_kept, "data_dropped": data_dropped,
         "clients": man.get("clients") or [],
         "outside_repo": reply.get("outside_repo") or [], "searched": reply.get("searched")}, indent=1) + "\n")
    import explain
    with contextlib.redirect_stdout(io.StringIO()):
        explain.render(run)
    if dropped or cov_dropped or data_dropped:
        say("REPAIR", "a dropped gate, caller coverage or data gate may be fixed once (SKILL.md step 2): correct it in "
                      "gates.json and run gates again")
    unit = lambda c: (c.get("unit") or {}).get("name") if isinstance(c.get("unit"), dict) else None  # noqa: E731
    dname = lambda c: (c.get("data") or {}).get("name") if isinstance(c.get("data"), dict) else None  # noqa: E731
    say("GATES", f"{len(kept)} verified, {len(dropped)} dropped"
        + "".join(f"\n  dropped {g.get('key')}: {g['dropped']}" for g in dropped)
        + "".join(f"\n  verified {g['key']} ({g.get('how')})" for g in kept)
        + (f"\nCALLER COVERAGE: {len(cov_kept)} verified, {len(cov_dropped)} dropped"
           + "".join(f"\n  dropped {unit(c)}: {c['dropped']}" for c in cov_dropped)
           + "".join(f"\n  verified {unit(c)} ({len(c.get('callers') or [])} caller(s))" for c in cov_kept)
           if cov_kept or cov_dropped else "")
        + (f"\nDATA GATES: {len(data_kept)} verified, {len(data_dropped)} dropped"
           + "".join(f"\n  dropped {dname(c)}: {c['dropped']}" for c in data_dropped)
           + "".join(f"\n  verified {dname(c)} ({len(c.get('writers') or [])} writer(s))" for c in data_kept)
           if data_kept or data_dropped else ""))
    return after_search(run, bool(dropped or cov_dropped or data_dropped))


def gates_recorded(run: Path) -> bool:
    """Both searches are recorded, or the run predates them (no task file:
    started by a build without the step)."""
    gates = (run / "gates-verified.json").is_file() or not (run / "gate_search.txt").is_file()
    risks = (run / "risks-verified.json").is_file() or not (run / "risk_search.txt").is_file()
    return gates and risks


def after_search(run: Path, repair: bool) -> int:
    """What follows `gates` or `risks`: the other search while it isn't
    recorded, else the next question, as `next` would print it. With a
    dropped claim to repair, `next` is left to the agent, after the repair."""
    if repair:
        say("NEXT", f"ld-factory next {run}")
        return 0
    if not (run / "gates-verified.json").is_file() and (run / "gate_search.txt").is_file():
        say("NEXT", f"the gate search: {run / 'gate_search.txt'}, then ld-factory gates {run}")
        return 0
    if not (run / "risks-verified.json").is_file() and (run / "risk_search.txt").is_file():
        say("NEXT", f"the risk search: {run / 'risk_search.txt'}, then ld-factory risks {run}")
        return 0
    return next_question(run)


def risks(args) -> int:
    """Check the risk search's reply (RUN/risks.json) and answer P30 from it:
    YES when at least one finding's every link matches the commit (a changed
    line the diff adds or modifies, an entry point outside tests), else NO."""
    from reader import risk_search
    run = Path(args.run).resolve()
    man = json.loads((run / "manifest.json").read_text())
    f = run / "risks.json"
    if not f.is_file():
        fail(2, f"SETUP: write the risk search's JSON to {f} first ({run / 'risk_search.txt'}).")
    reply = read_reply(f, "findings", run / "risk_search.txt")
    repo, head, base = man["repo_path"], man["unit"]["head"], man["unit"]["merge_base"]
    changed = risk_search.changed_lines(repo, base, head)
    files: dict = {}
    kept, dropped = [], []
    for fd in reply.get("findings") or []:
        why = risk_search.verify(repo, head, fd, files, changed)
        (dropped if why else kept).append({**fd, **({"dropped": why} if why else {})})
    man["mechanical"]["P30"] = risk_search.answer(kept, dropped)
    (run / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    (run / "risks-verified.json").write_text(json.dumps(
        {"verified": kept, "dropped": dropped, "searched": reply.get("searched")}, indent=1) + "\n")
    import explain
    with contextlib.redirect_stdout(io.StringIO()):
        explain.render(run)
    if dropped:
        say("REPAIR", "a dropped finding may be fixed once (SKILL.md step 2): correct its links in risks.json and run risks again")
    say("RISKS", f"{len(kept)} verified, {len(dropped)} dropped; P30 = {'yes' if kept else 'no'}"
        + "".join(f"\n  dropped {d.get('kind')}: {d['dropped']}" for d in dropped)
        + "".join(f"\n  verified {k['kind']}" for k in kept))
    return after_search(run, bool(dropped))


def readers(args) -> int:
    """Check the consumer search's reply (RUN/consumers.json): each contract
    change's reader must check out line by line, in this repository or a
    client checkout. `next` / `decide` then settle P19 from it."""
    from reader import consumer_search
    run = Path(args.run).resolve()
    man = json.loads((run / "manifest.json").read_text())
    f = run / "consumers.json"
    if not f.is_file():
        fail(2, f"SETUP: write the consumer search's JSON to {f} first ({run / 'consumer_search.txt'}).")
    reply = read_reply(f, "contract_changes", run / "consumer_search.txt")
    cl = man.get("clients") or []
    changes = consumer_search.check(man["repo_path"], man["unit"]["merge_base"], man["unit"]["head"], cl, reply)
    (run / "consumers-verified.json").write_text(json.dumps({"clients": cl, "contract_changes": changes}, indent=1) + "\n")
    ok = [c for c in changes if c["reader_verified"]]
    if any(c.get("chain") and not c["reader_verified"] and c.get("token") for c in changes):
        say("REPAIR", "a dropped reader may be fixed once (SKILL.md step 2): correct its links in consumers.json and run readers again")
    say("READERS", f"{len(changes)} contract change(s), {len(ok)} with a verified reader; "
                   f"P19 = {'yes' if ok else 'no'}"
        + "".join(f"\n  no reader for {c.get('interface', '?')[:60]}: {c['dropped']}" for c in changes
                  if not c["reader_verified"])
        + "".join(f"\n  verified reader of `{c['token']}` ({c.get('interface', '?')[:60]})" for c in ok))
    say("NEXT", f"ld-factory next {run} (or ld-factory decide {run})")
    return 0


def set_aside(run: Path, pids, why: str) -> list[str]:
    """Move the answers to `pids` out of replies.json (kept under
    `before_<why>`), so `next` asks them again; a question already set aside
    for this reason keeps its new answer. Returns the ids moved."""
    f = run / "replies.json"
    replies = json.loads(f.read_text()) if f.is_file() else {"answers": {}}
    kept = replies.setdefault(f"before_{why}", {})
    moved = []
    for pid in pids:
        if pid in kept:
            continue
        first = (replies.get("answers") or {}).pop(pid, None)
        again = (replies.get("rechecks") or {}).pop(pid, None)
        if first is not None or again is not None:
            kept[pid] = {"answer": first, **({"recheck": again} if again is not None else {})}
            moved.append(pid)
    f.write_text(json.dumps(replies, indent=2) + "\n")
    return moved


def features(args) -> int:
    """Check the feature flag search's reply (RUN/features.json): each claimed
    release flag must exist at merge_base, its chain from evaluation to the
    feature's entry and its link from the entry to a changed file must match
    head line by line (feature_search.verify). What holds joins the reuse
    candidates: P9/P11 are answered again with it, its LaunchDarkly state
    read like any candidate's, and P10/P12/P13 see its lines. When it adds a
    candidate, the reuse questions already answered are asked again."""
    from reader import feature_search, gate_search
    from reader.mechanical import feature_candidate_answers, setup_ld_client
    from reader.read import build_manifest
    from reader.sources import LDUnavailable, Profile
    run = Path(args.run).resolve()
    man = json.loads((run / "manifest.json").read_text())
    f = run / "features.json"
    if not f.is_file():
        fail(2, f"SETUP: write the feature search's JSON to {f} first ({run / 'feature_search.txt'}).")
    reply = read_reply(f, "features", run / "feature_search.txt")
    repo, head, base = man["repo_path"], man["unit"]["head"], man["unit"]["merge_base"]
    pkt = pickle.loads((run / "packet.pickle").read_bytes())
    prof = (load_profile_file(man["profile_file"]) if man.get("profile_file")
            else Profile.load(man["profile"]))
    changed = {x["path"] for x in pkt.files}
    not_shipping = gate_search.not_shipping_fn(prof)
    files: dict = {}
    kept, dropped = [], []
    for c in reply.get("features") or []:
        why = (feature_search.verify(repo, head, base, c, files, changed, pkt.keys_added_by_diff, not_shipping)
               if len(kept) < feature_search.MAX_FEATURES else
               f"more than {feature_search.MAX_FEATURES} claims: a change belongs to one feature")
        if why:
            dropped.append({**(c if isinstance(c, dict) else {"claim": c}), "dropped": why})
        elif c["key"].strip() not in {k["key"].strip() for k in kept}:
            kept.append(c)
    near = {c["key"] for c in pkt.candidates}
    added = [c["key"].strip() for c in kept if c["key"].strip() not in near]
    # LaunchDarkly state, read like any candidate's (exit 7 asks for a flag
    # the agent hasn't fetched yet).
    mode = man.get("launchdarkly") or "off"
    env = run_environments(prof, run, man)
    ld = make_ld(prof, run, mode, ld_key(man))
    if getattr(pkt, "ld_setup", None):
        setup_ld_client(ld, pkt.ld_setup)
    snaps, note = {}, None
    if added and ld.available:
        for k in added:
            try:
                snaps[k] = ld.snapshot(k, man["merged"])
            except LDUnavailable as e:
                snaps, note = {}, f"LaunchDarkly unavailable: {e}"
                break
        if write_needed(run, ld, env):
            return NEEDS_LD
    cfile = prof.data.get("codeowners", "CODEOWNERS")
    pkt.feature_candidates = [feature_search.candidate(
        c, feature_search.owners(repo, base, cfile, [x["path"] for x in c["chain"] if x.get("role") == "evaluates"]))
        for c in kept]
    pkt.feature_snapshots = snaps
    man.setdefault("before_feature_search", {k: man["mechanical"].get(k) for k in ("P9", "P11")})
    for k in ("P9", "P11"):  # a rerun starts again from the answers before the search
        if man["before_feature_search"].get(k) is None:
            man["mechanical"].pop(k, None)
        else:
            man["mechanical"][k] = man["before_feature_search"][k]
    man["mechanical"].update(feature_candidate_answers(pkt, man["mechanical"],
                                                       ld.main_production if snaps else None))
    new = build_manifest(pkt, man["mechanical"], man["profile"], man.get("pr"))
    if new["packet_hash"] != man["packet_hash"]:
        fail(2, "SETUP: adding the feature search changed the evidence itself; only the reuse questions should change.")
    man.update({"questions": new["questions"], "citation_context": new["citation_context"],
                "reuse_candidates": new["reuse_candidates"]})
    (run / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    (run / "packet.pickle").write_bytes(pickle.dumps(pkt))
    again = set_aside(run, ("P10", "P12", "P13"), "feature_search") if added else []
    (run / "features-verified.json").write_text(json.dumps(
        {"verified": kept, "dropped": dropped, "added": added, "asked_again": again,
         "launchdarkly": note or ("read" if snaps else "not read"), "searched": reply.get("searched")},
        indent=1) + "\n")
    import explain
    with contextlib.redirect_stdout(io.StringIO()):
        explain.render(run)
    if dropped:
        say("REPAIR", "a dropped feature flag may be fixed once (SKILL.md step 3): correct its links in "
                      "features.json and run features again")
    say("FEATURES", f"{len(kept)} verified, {len(dropped)} dropped"
        + "".join(f"\n  dropped {d.get('key')}: {d['dropped']}" for d in dropped)
        + "".join(f"\n  verified {c['key']} ({c.get('entry_kind')})" for c in kept)
        + (f"\n  new reuse candidate(s): {', '.join(added)}" if added else "")
        + (f"\n  asked again: {', '.join(again)}" if again else ""))
    say("NEXT", f"ld-factory next {run} (or ld-factory decide {run})")
    return 0


def facts(args) -> int:
    """Check the fact search's reply (RUN/facts.json): every finding's quoted
    line must match head (fact_search.verify). Verified findings go into the
    question's context, citable by it, and the question is asked once more;
    with none, its unresolved answer stands."""
    from reader import fact_search
    from reader.read import build_manifest
    run = Path(args.run).resolve()
    man = json.loads((run / "manifest.json").read_text())
    tf, f = run / "fact_search.json", run / "facts.json"
    if not tf.is_file():
        fail(2, f"SETUP: no fact search was asked for in {run}.")
    if not f.is_file():
        fail(2, f"SETUP: write the fact search's JSON to {f} first ({run / 'fact_search.txt'}).")
    reply = read_reply(f, "findings", run / "fact_search.txt")
    task = json.loads(tf.read_text())
    pid = task["question"]
    if reply.get("question") and reply["question"] != pid:
        fail(2, f"SETUP: facts.json answers {reply['question']}, but the search asked for is about {pid}.")
    kept, dropped = fact_search.check(man["repo_path"], man["unit"]["head"], reply)
    pkt = pickle.loads((run / "packet.pickle").read_bytes())
    found = dict(getattr(pkt, "fact_findings", None) or {})
    found.pop(pid, None)
    if kept:
        found[pid] = {"findings": kept, "searched": reply.get("searched")}
    pkt.fact_findings = found
    new = build_manifest(pkt, man["mechanical"], man["profile"], man.get("pr"))
    if new["packet_hash"] != man["packet_hash"]:
        fail(2, "SETUP: adding the fact search changed the evidence itself; only its question should change.")
    man.update({"questions": {**man["questions"], pid: new["questions"].get(pid, man["questions"].get(pid))},
                "citation_context": new["citation_context"]})
    (run / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    (run / "packet.pickle").write_bytes(pickle.dumps(pkt))
    again = set_aside(run, [pid], "fact_search") if kept else []
    vf = run / "facts-verified.json"
    done = json.loads(vf.read_text()) if vf.is_file() else {}
    done[pid] = {"verified": kept, "dropped": dropped, "searched": reply.get("searched"),
                 "not_found": bool(reply.get("not_found")) or not reply.get("findings"),
                 "first_answer": task.get("answer"), "asked_again": bool(kept)}
    vf.write_text(json.dumps(done, indent=1) + "\n")
    import explain
    with contextlib.redirect_stdout(io.StringIO()):
        explain.render(run)
    if dropped:
        say("REPAIR", "a dropped finding may be fixed once (SKILL.md step 3): correct its line in facts.json "
                      "and run facts again")
    say("FACTS", f"{pid}: {len(kept)} verified, {len(dropped)} dropped"
        + "".join(f"\n  dropped {d.get('path')}:{d.get('line')}: {d['dropped']}" for d in dropped)
        + (f"\n  {pid} is asked again with them" if kept
           else f"\n  nothing verified: {pid}'s unresolved answer stands"))
    say("NEXT", f"ld-factory next {run}")
    return 0


def next_cmd(args) -> int:
    return next_question(Path(args.run).resolve())


def answer(args) -> int:
    """Record one answer (JSON on stdin) in replies.json, then say what's next."""
    run = Path(args.run).resolve()
    raw = sys.stdin.read()
    try:
        a = json.loads(raw)
    except ValueError as e:
        fail(2, f"SETUP: the answer is not JSON: {e}")
    a = a.get(args.pid, a) if isinstance(a, dict) and set(a) == {args.pid} else a
    if not isinstance(a, dict) or str(a.get("value")).lower() not in ("yes", "no", "unresolved"):
        fail(2, 'SETUP: an answer is {"value": "yes|no|unresolved", "evidence": "...", "citations": [...]}')
    if a.get("gates") or a.get("gate_paths"):
        # P6's YES on more than one flag says how they combine (predicates.yaml P6).
        from reader.mechanical import GATE_COMBINATION_PREDICATES, gate_declaration
        if args.pid not in GATE_COMBINATION_PREDICATES:
            fail(2, f'SETUP: only {"/".join(GATE_COMBINATION_PREDICATES)} gives "gates" / "gate_paths"; '
                    f'leave them out of {args.pid}.')
        if gate_declaration(a) is None:
            fail(2, 'SETUP: "gates" is "all" or "any"; "gate_paths" is a list of paths, each a list of '
                    'flag keys that must all be on, e.g. [["outer-flag", "page-a"], ["outer-flag", "page-b"]].')
    if a.get("gate_values"):
        # P6's YES on a flag that serves a string, number or JSON value says
        # which value(s) the changed code runs under (predicates.yaml P6).
        from reader.mechanical import GATE_COMBINATION_PREDICATES, gate_values_declaration
        if args.pid not in GATE_COMBINATION_PREDICATES:
            fail(2, f'SETUP: only {"/".join(GATE_COMBINATION_PREDICATES)} gives "gate_values"; '
                    f'leave it out of {args.pid}.')
        if gate_values_declaration(a) is None:
            fail(2, 'SETUP: "gate_values" maps each flag key to the list of values the changed code runs '
                    'under, e.g. {"model-provider": ["coralbricks"]}: strings or numbers, at least one each.')
    f = run / "replies.json"
    replies = json.loads(f.read_text()) if f.is_file() else {"answers": {}}
    replies.setdefault("rechecks" if args.recheck else "answers", {})[args.pid] = a
    f.write_text(json.dumps(replies, indent=2) + "\n")
    return next_question(run)


def decide(args) -> int:
    run = Path(args.run).resolve()
    os.environ["FDG_HOME"] = str(run)  # classify writes its record here, nowhere else (set before it's imported)
    if searches_needed(run):
        say_searches(run)
        return NEEDS_GATES
    man = json.loads((run / "manifest.json").read_text())
    if args.key_file:  # a run started with a key, decided again later (evaluations)
        read_key(args.key_file)
        man["launchdarkly_key_file"] = str(Path(args.key_file).resolve())
        (run / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    os.environ["FDG_HOME"] = str(run)  # classify writes its record here, nowhere else
    code = merge(run, man)
    if code:
        return code
    from reader import specload
    from reader.read import lazy_needed
    answers = json.loads((run / "answers.json").read_text())["answers"]
    pending = lazy_needed(specload.load(Path(os.environ["ODD_HOME"]) / "tree.yaml"),
                          {p: a for p, a in answers.items() if a.get("evidence") != "not answered"})
    if pending:
        fail(2, f"NOT DECIDED YET: question {pending} is still needed. Run: ld-factory next {run}")

    import classify
    import explain
    with contextlib.redirect_stdout(io.StringIO()) as rec:
        classify.decide(str(run / "answers.json"))
    (run / "decide.log").write_text(rec.getvalue())
    explain.explain(run)
    return 0


def check_profile(args) -> int:
    """The reader's own profile check (verify_profile.py) on a written profile:
    a pattern that matches nothing makes every flag check invisible."""
    from reader import verify_profile
    repo = Path(args.repo).resolve()
    path = args.profile_file or written_profile(repo)
    if not path or not Path(path).is_file():
        fail(2, f"SETUP: no profile at {path}; write one as PROFILE.md describes.")
    return verify_profile.main(["verify_profile", str(Path(path).resolve()), str(repo)])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ld-factory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("repo", nargs="?", default=".")
    s.add_argument("--base")
    s.add_argument("--head")
    s.add_argument("--pr-url")
    s.add_argument("--pr-title")
    s.add_argument("--pr-body-file")
    s.add_argument("--flag-type", choices=FLAG_TYPES,
                   help="the type of flag the developer wants if one is suggested "
                        "(string, number and json are multivariate)")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--profile")
    g.add_argument("--profile-file")
    s.add_argument("--no-launchdarkly", action="store_true")
    s.add_argument("--client-repo", action="append", metavar="NAME=PATH[@REV]",
                   help="a checkout of a repository whose code calls this one's interfaces")
    s.add_argument("--as-of", help=argparse.SUPPRESS)  # timestamp or YYYY-MM-DD; evaluations only
    s.add_argument("--key-file", help=argparse.SUPPRESS)  # a read-only API key; evaluations only
    gt = sub.add_parser("gates")
    gt.add_argument("run")
    rk = sub.add_parser("risks")
    rk.add_argument("run")
    rd = sub.add_parser("readers")
    rd.add_argument("run")
    fe = sub.add_parser("features")
    fe.add_argument("run")
    fa = sub.add_parser("facts")
    fa.add_argument("run")
    d = sub.add_parser("decide")
    d.add_argument("run")
    d.add_argument("--key-file", help=argparse.SUPPRESS)
    n = sub.add_parser("next")
    n.add_argument("run")
    a = sub.add_parser("answer")
    a.add_argument("run")
    a.add_argument("pid")
    a.add_argument("--recheck", action="store_true")
    pr_ = sub.add_parser("profile")
    pr_.add_argument("run")
    c = sub.add_parser("check-profile")
    c.add_argument("repo", nargs="?", default=".")
    c.add_argument("--profile-file")
    args = ap.parse_args(argv)
    return {"start": start, "gates": gates, "risks": risks, "readers": readers, "features": features,
            "facts": facts, "next": next_cmd, "answer": answer, "decide": decide,
            "check-profile": check_profile, "profile": profile_cmd}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
