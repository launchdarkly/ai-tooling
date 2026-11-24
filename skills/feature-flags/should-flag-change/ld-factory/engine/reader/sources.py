#!/usr/bin/env python3
"""Evidence sources: git, repo profiles, flag symbol tables, LaunchDarkly state.

Everything here is MECHANICAL. No model is consulted. That boundary is the
reader's main defence: whatever a model is later asked (ask.py), it is asked on
top of facts computed here, and a fact computed here is identical on every run.

THE SYMBOL TABLE IS THE LOAD-BEARING PIECE
------------------------------------------
In both repos a flag key does not appear at its call site:

So a diff grep for the key finds nothing, and every gate in the repo becomes
invisible. Resolving symbol -> key AT merge_base is a precondition for P3, P5,
P6, P9 and P10. It must be read at merge_base, not at HEAD: a key the diff
itself introduces is not a reuse candidate (P9), and reading HEAD would make it
look like one."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import specload

HERE = Path(__file__).parent
PROFILES = HERE / "profiles"


def profile_dirs() -> list[Path]:
    """Where repo profiles are found: SHOULD_I_FLAG_PROFILES (folders, separated
    like PATH), then the ones shipped with the skill."""
    extra = [Path(p) for p in os.environ.get("SHOULD_I_FLAG_PROFILES", "").split(os.pathsep) if p]
    return [d for d in extra if d.is_dir()] + [PROFILES]


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------

class GitError(RuntimeError):
    pass


@dataclass
class Repo:
    path: Path
    _file_cache: dict = field(default_factory=dict, repr=False, compare=False)
    _grep_cache: dict = field(default_factory=dict, repr=False, compare=False)

    def git(self, *args: str, check: bool = True) -> str:
        r = subprocess.run(["git", "-C", str(self.path), *args],
                           capture_output=True, text=True, errors="replace")
        if check and r.returncode != 0:
            raise GitError(f"git {' '.join(args)}: {r.stderr.strip()}")
        return r.stdout

    def rev_parse(self, ref: str) -> str:
        return self.git("rev-parse", ref).strip()

    def merge_base(self, base: str, head: str) -> str:
        return self.git("merge-base", base, head).strip()

    def is_ancestor(self, a: str, b: str) -> bool:
        r = subprocess.run(
            ["git", "-C", str(self.path), "merge-base", "--is-ancestor", a, b],
            capture_output=True, text=True, errors="replace")
        return r.returncode == 0

    def parents(self, ref: str) -> list[str]:
        out = self.git("rev-list", "--parents", "-n", "1", ref).split()
        return out[1:]

    def file_at(self, rev: str, path: str) -> str | None:
        key = (rev, path)
        if key not in self._file_cache:
            self._file_cache[key] = self._file_at(rev, path)
        return self._file_cache[key]

    def _file_at(self, rev: str, path: str) -> str | None:
        r = subprocess.run(
            ["git", "-C", str(self.path), "show", f"{rev}:{path}"],
            capture_output=True, text=True, errors="replace")
        return r.stdout if r.returncode == 0 else None

    def changed_files(self, unit: str) -> list[str]:
        out = self.git("diff", "--name-only", unit)
        return [l for l in out.splitlines() if l.strip()]

    def numstat(self, unit: str) -> dict[str, tuple[int, int]]:
        res = {}
        for line in self.git("diff", "--numstat", unit).splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            a, d, p = parts
            res[p] = (0 if a == "-" else int(a), 0 if d == "-" else int(d))
        return res

    def diff(self, unit: str, path: str | None = None, context: int = 3) -> str:
        args = ["diff", f"-U{context}", unit]
        if path:
            args += ["--", path]
        return self.git(*args)

    def grep_at(self, rev: str, pattern: str,
                pathspec: list[str] | None = None) -> list[tuple[str, int, str]]:
        key = (rev, pattern, tuple(pathspec or ()))
        if key not in self._grep_cache:
            self._grep_cache[key] = self._grep_at(rev, pattern, pathspec)
        return list(self._grep_cache[key])  # a copy: callers may extend or sort it

    def _grep_at(self, rev: str, pattern: str,
                 pathspec: list[str] | None = None) -> list[tuple[str, int, str]]:
        """`git grep -nP` at a revision. Returns (path, lineno, line).

        PCRE (-P), not ERE (-E). The profiles use `(?:...)` non-capturing
        groups, which POSIX ERE does not support -- and `git grep -E` does not
        error on them, it just matches NOTHING. That silently reported every
        evaluation pattern as dead, i.e. "this repo has no flag gates".
        Falls back to -E only if the git build lacks PCRE, and says so.
        """
        args = ["grep", "-nP", pattern, rev]
        if pathspec:
            args += ["--", *pathspec]
        r = subprocess.run(["git", "-C", str(self.path), *args],
                           capture_output=True, text=True, errors="replace")
        if r.returncode > 1 and "PCRE" in (r.stderr or ""):
            self._pcre_missing = True
            args[1] = "-nE"
            r = subprocess.run(["git", "-C", str(self.path), *args],
                               capture_output=True, text=True, errors="replace")
        hits = []
        for line in r.stdout.splitlines():
            # format: <rev>:<path>:<lineno>:<text>
            rest = line[len(rev) + 1:] if line.startswith(rev + ":") else line
            m = re.match(r"^(.*?):(\d+):(.*)$", rest)
            if m:
                hits.append((m.group(1), int(m.group(2)), m.group(3)))
        return hits


# ---------------------------------------------------------------------------
# diff unit  (U1)
# ---------------------------------------------------------------------------

@dataclass
class Unit:
    mode: str                 # "merge_base...head" | "squashed-commit"
    merge_base: str | None
    head: str
    spec: str                 # what to hand `git diff`
    basis: str
    resolved: bool = True
    note: str | None = None


def resolve_unit(repo: Repo, head: str, base_branch: str = "origin/main",
                 squashed: bool | None = None) -> Unit:
    """Establish the true diff unit, or say it is unresolved.

    Two real shapes:
      * the pin is the squashed PR commit already on the base branch -> the
        commit IS the pr, so the unit is pin^..pin;
      * the pin is a branch tip -> merge_base...pin.

    Rating the wrong one shows an arbitrary slice of the PR, so this is a
    precondition rather than a decision -- see U1.

    The one merge left unresolved is a head already on the base branch with
    more than one parent: a PR merged with a merge commit, whose own change
    can't be read off merge_base...head (that is empty).
    """
    try:
        head_sha = repo.rev_parse(head)
    except GitError as e:
        return Unit("unknown", None, head, "", f"head-unresolvable: {e}",
                    resolved=False)
    try:
        base_sha = repo.rev_parse(base_branch)
    except GitError as e:
        return Unit("unknown", None, head_sha, "",
                    f"base-branch-unresolvable: {e}", resolved=False)

    on_base = repo.is_ancestor(head_sha, base_sha)
    parents = repo.parents(head_sha)

    if squashed is True or (squashed is None and on_base and len(parents) == 1):
        return Unit("squashed-commit", parents[0] if parents else None,
                    head_sha, f"{head_sha}^..{head_sha}",
                    "pin is on the base branch with one parent: the commit is "
                    "the PR")

    note = None
    if len(parents) > 1:
        if on_base:
            return Unit("unknown", None, head_sha, "",
                        "head is a merge commit already on the base branch; "
                        "the PR's own change can't be read from merge_base...head",
                        resolved=False)
        note = (f"head {head_sha[:12]} is a merge commit; compared as GitHub "
                f"does, merge_base...head, so what the merge brought in that "
                f"isn't on the base counts as part of the change")

    mb = repo.merge_base(base_sha, head_sha)
    return Unit("merge_base...head", mb, head_sha, f"{mb}...{head_sha}",
                f"merge-base({base_branch}, head)", note=note)


# ---------------------------------------------------------------------------
# profiles + symbol table
# ---------------------------------------------------------------------------

@dataclass
class Profile:
    name: str
    data: dict
    ld: dict

    @classmethod
    def load(cls, name: str) -> "Profile":
        p = next((d / f"{name}.json" for d in profile_dirs() if (d / f"{name}.json").is_file()), None)
        if p is None:
            avail = sorted(x.stem for d in profile_dirs() for x in d.glob("*.json")
                           if not x.stem.startswith("_"))
            raise SystemExit(f"no profile {name!r}; have {avail}")
        data = specload.load(p)
        # A profile's own `launchdarkly` section overrides the defaults:
        # its instance, project and environments.
        ld = {**specload.load(PROFILES / "_launchdarkly.yaml"), **(data.get("launchdarkly") or {})}
        return cls(name, data, ld)

    @classmethod
    def from_file(cls, path: Path | str) -> "Profile":
        """A profile outside profiles/: a repo the bundled profiles don't
        cover, written as JSON by the should-flag-change skill. Its optional
        `launchdarkly` section overrides _launchdarkly.yaml's project and
        environments, which are LaunchDarkly's own."""
        path = Path(path)
        data = json.loads(path.read_text())
        ld = {**specload.load(PROFILES / "_launchdarkly.yaml"),
              **(data.get("launchdarkly") or {})}
        return cls(data.get("name") or path.stem, data, ld)

    def role_of(self, path: str) -> str:
        roles = self.data.get("path_roles", {})
        for pat in roles.get("ships_anyway", []):
            if _match(path, pat):
                return "ships"
        for role in ("test", "docs", "build_ci", "generated"):
            for pat in roles.get(role, []):
                if _match(path, pat):
                    return role
        return "ships"


def _match(path: str, pattern: str) -> bool:
    if fnmatch.fnmatch(path, pattern):
        return True
    # fnmatch does not treat ** as spanning separators; approximate it
    if "**/" in pattern:
        return fnmatch.fnmatch(path, pattern.replace("**/", "", 1)) or \
            fnmatch.fnmatch(path, pattern.replace("**/", "*/", 1)) or \
            any(fnmatch.fnmatch(path, pattern.replace("**", "*" * n))
                for n in (1, 2))
    return False


_ACCESSOR_SUFFIX = re.compile(r"^([A-Za-z_$][\w$]*?[a-z0-9])(?:Pred|Predicate|Noisy|FlagKey|Key|Flag)$")


@dataclass
class SymbolTable:
    """symbol -> key and key -> symbol, read at one revision."""
    rev: str
    by_symbol: dict[str, str] = field(default_factory=dict)
    by_key: dict[str, str] = field(default_factory=dict)
    keys: set[str] = field(default_factory=set)
    # key -> the boolean the code serves when LD has no such flag, where the
    # declaration states one (flag_declarations' default_group, flag_defaults).
    defaults: dict[str, bool] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def key_for(self, symbol: str) -> str | None:
        key = self.by_symbol.get(symbol)
        if key is None and symbol:
            m = _ACCESSOR_SUFFIX.match(symbol)
            if m:
                key = self.by_symbol.get(m.group(1))
        return key


def build_symbol_table(repo: Repo, profile: Profile, rev: str) -> SymbolTable:
    st = SymbolTable(rev=rev)
    for decl in profile.data.get("flag_declarations", []):
        if decl.get("files"):
            # No declarations file: keys are whatever the code evaluates by
            # literal key (a repo calling the SDK directly, as most customer
            # code does). The pattern is matched line by line over every hit
            # of `git grep` in these pathspecs, so a key "exists" at a
            # revision when some code there evaluates it.
            text = "\n".join(t for _, _, t in repo.grep_at(rev, decl["pattern"],
                                                           decl["files"]))
            decl = {**decl, "file": ",".join(decl["files"]), "multiline": True}
        else:
            text = repo.file_at(rev, decl["file"])
        if text is None:
            st.problems.append(
                f"{decl['id']}: {decl['file']} absent at {rev[:12]}")
            continue
        flags = re.M if decl.get("multiline") else 0
        try:
            rx = re.compile(decl["pattern"], flags)
        except re.error as err:
            st.problems.append(f"{decl['id']}: the pattern doesn't compile ({err}), "
                               f"so its declarations weren't read")
            continue
        n = 0
        for m in rx.finditer(text):
            kg, sg = decl.get("key_group"), decl.get("symbol_group")
            key = m.group(kg) if kg else None
            if not key:
                continue
            st.keys.add(key)
            n += 1
            if sg:
                sym = m.group(sg)
                st.by_symbol[sym] = key
                st.by_key.setdefault(key, sym)
            dg = decl.get("default_group")
            if dg and m.group(dg) in ("true", "false"):
                st.defaults[key] = m.group(dg) == "true"
        st.sources.append(f"{decl['file']}@{rev[:12]}:{n}")
        low = decl.get("expect_at_least")
        if low and n < low:
            st.problems.append(
                f"{decl['id']}: matched {n} declarations, profile expects "
                f">= {low}. The pattern has probably drifted -- do NOT treat "
                f"the shortfall as flags having been deleted.")
    # Defaults declared apart from the key (Go's ValidFlags map), matched by
    # the symbol the declarations above resolved.
    for fd in profile.data.get("flag_defaults", []):
        text = repo.file_at(rev, fd["file"])
        if text is None:
            continue
        rx = re.compile(fd["pattern"], re.M | re.S if fd.get("multiline") else 0)
        for m in rx.finditer(text):
            sg, kg, dg = fd.get("symbol_group"), fd.get("key_group"), fd["default_group"]
            key = m.group(kg) if kg else st.by_symbol.get(m.group(sg))
            if key and m.group(dg) in ("true", "false"):
                st.defaults[key] = m.group(dg) == "true"
    return st


# ---------------------------------------------------------------------------
# LaunchDarkly state  (P7 / P8 / P11)
# ---------------------------------------------------------------------------

class LDUnavailable(RuntimeError):
    pass


_NON_STATE_VERBS = ("requested approval", "commented", "reviewed", "declined",
                    "deleted the approval request", "a link to")
"""Audit-entry verbs that never change a flag's per-environment state, so
they can sit between the entry read and the merge date without invalidating
it."""
_FORWARD_SAFE_VERBS = _NON_STATE_VERBS + ("applied approved changes",)


_MAX_AUDIT_PAGES = 5  # pages of 20 read within one post-merge time window
# Windows after the merge, widened until one holds an entry. The first
# post-merge entry is found by looking FORWARD from the merge, not by paging
# back from the newest entry: paged back from now, a flag that keeps being
# edited eventually has more history after the merge than the page cap can
# reach, and a state that read cleanly last week turns indeterminate -- the
# same PR's answers drifting, and its cached answers going stale, only
# because the flag kept changing after the merge.
_POST_MERGE_WINDOWS_DAYS = (1, 7, 30, 180, 3650)


def _is_non_state_verb(verb: str, forward: bool = False) -> bool:
    return any(t in verb for t in
               (_FORWARD_SAFE_VERBS if forward else _NON_STATE_VERBS))


FULL_ROLLOUT = 100_000  # LD rollout weights are thousandths of a percent


def _served(spec: dict, targets: set[int]) -> int:
    """Weight (of FULL_ROLLOUT) that a fallthrough/rule `spec` gives `targets`."""
    if "variation" in spec and spec["variation"] is not None:
        return FULL_ROLLOUT if spec["variation"] in targets else 0
    return sum(w.get("weight") or 0
               for w in ((spec.get("rollout") or {}).get("variations") or [])
               if w.get("variation") in targets)


def _non_user_rule(rule: dict, non_user: tuple[str, ...]) -> bool:
    """Does a rule match only contexts that are not real users? True when one
    of its clauses -- they are ANDed -- is a non-negated segment match whose
    segments are all named for a non-user audience (a word of the segment key
    such as `internal` or `dogfood`). Anything else, individual targets
    included, is taken to be real users: the population is unknown, and
    reading it as real users errs toward `suggested`."""
    for c in rule.get("clauses") or []:
        if c.get("negate") or c.get("op") != "segmentMatch" or not c.get("values"):
            continue
        if all(set(re.split(r"[-_.:\s]+", str(v).lower())) & set(non_user)
               for v in c["values"]):
            return True
    return False


def serving(cfg: dict, targets: set[int], non_user: tuple[str, ...] = ()
            ) -> tuple[str, str]:
    """Who, in one environment, is served one of the `targets` variations.

    `cfg` is LaunchDarkly's per-environment flag configuration (on,
    offVariation, fallthrough, rules, targets, contextTargets). Returns one of:
      all       every real user not matched by an earlier rule (the
                fallthrough serves it in full)
      partial   the fallthrough rolls it out to a percentage of real users,
                above 0% and below 100%: some real users get it, some do not
      cohort    only the users some rules or individual targets match
      internal  only contexts in a non-user audience (non_user_audiences)
      none      nobody
    and a one-clause reason. Prerequisites are the caller's job: this reads
    one flag's own configuration."""
    if not cfg.get("on"):
        off = cfg.get("offVariation")
        return (("all", "off, and its off variation is the exposing one")
                if off in targets else ("none", "off"))
    ft = _served(cfg.get("fallthrough") or {}, targets)
    if ft >= FULL_ROLLOUT:
        return "all", "on; the fallthrough serves it"
    if ft > 0:
        # Not `all`: a 10% rollout withholds the change from 90% of real
        # users. P8 (withheld from EVERY real user?) reads it as exposing,
        # exactly as before; P11 (withheld from SOME?) as still withholding --
        # an in-progress rollout is the textbook reuse candidate, and reading
        # it as `all` dropped it from the reuse layer.
        return "partial", f"on; the fallthrough rolls it out to {ft / 1000:g}%"
    rules = [r for r in cfg.get("rules") or []
             if not r.get("disabled") and _served(r, targets) > 0]
    named = [t for t in (cfg.get("targets") or []) + (cfg.get("contextTargets") or [])
             if t.get("variation") in targets and t.get("values")]
    if not rules and not named:
        return "none", "on, but the fallthrough and every rule serve another variation"
    real = [r for r in rules if not _non_user_rule(r, non_user)]
    if not real and not named:
        return "internal", (f"on; only {len(rules)} rule(s) for non-user "
                            f"audiences serve it, the fallthrough does not")
    return "cohort", (f"on; the fallthrough does not serve it, but {len(real)} "
                      f"rule(s) and {sum(len(t['values']) for t in named)} "
                      f"individual target(s) do")


def exposing_variations(flag: dict, values: list | None = None) -> set[int] | None:
    """Indices of the variations that EXPOSE the gated behavior, or None when
    that cannot be told mechanically. A boolean flag's `true` -- the reading
    `on` already stood for. A multivariate flag has no such default: which
    value turns the change on depends on the code, so its state stays read
    by `on` alone -- unless the enclosure answer says which value(s) the
    changed code runs under (P6's `gate_values`): then those variations, and
    an empty set when the flag has none of them, which serves nobody."""
    vals = [v.get("value") for v in flag.get("variations") or []]
    if vals and all(isinstance(v, bool) for v in vals):
        return {i for i, v in enumerate(vals) if v is True}
    if not vals or not values:
        return None
    return {i for i, v in enumerate(vals) if any(same_flag_value(v, x) for x in values)}


def same_flag_value(variation, value) -> bool:
    """Is `value` (as an answer names it) this variation's value? Equal, or
    equal as text for scalars (`3` and `"3"`): the code compares a string
    flag to a literal, and an answer quotes it."""
    if variation == value:
        return True
    scalar = (str, int, float)
    return (isinstance(variation, scalar) and isinstance(value, scalar)
            and not isinstance(variation, bool) and str(variation) == str(value))


def _index(v):
    """A variation as the MCP tool gives it ({"index": 1, "value": ...}) or
    as REST does (1): its index."""
    return v.get("index") if isinstance(v, dict) else v


def _served_spec(s: dict | None) -> dict:
    """The MCP tool's {"type": "variation"|"rollout", ...} as REST's
    {"variation": i} or {"rollout": {"variations": [{"variation", "weight"}]}}."""
    if not isinstance(s, dict):
        return {}
    if s.get("type") == "variation" or ("variation" in s and "rollout" not in s):
        return {"variation": _index(s.get("variation"))}
    ro = s.get("rollout") or {}
    return {"rollout": {"variations": [
        {"variation": _index(w.get("variation")),
         "weight": w["weight"] if "weight" in w else round(float(w.get("weight_percent") or 0) * 1000)}
        for w in ro.get("variations") or []]}}


def _indexed(variations) -> bool:
    return bool(variations) and all(isinstance(v, dict) and "index" in v for v in variations)


def from_tool_shape(flag: dict) -> dict:
    """A flag file as the agent wrote it, in REST shape. An environment may be
    the LaunchDarkly MCP tool's targeting result as returned (`off_variation`,
    `fallthrough` with a `type`, rules that `serves`, `context_targets`,
    `prerequisites` as `flag_key`/`variation_index`): it's converted here, so
    the agent never rewrites variation values as indexes by hand. A result the
    tool marked as an error leaves its environment out. REST-shaped
    environments pass through unchanged."""
    if not isinstance(flag, dict) or flag.get("not_found"):
        return flag
    envs = flag.get("environments") or {}
    out, variations = {}, flag.get("variations")
    for name, e in envs.items():
        if not isinstance(e, dict):
            continue
        tool = ("off_variation" in e or "context_targets" in e or "status" in e
                or (isinstance(e.get("fallthrough"), dict) and "type" in e["fallthrough"]))
        if not tool:
            out[name] = e
            continue
        if e.get("status") not in (None, "success"):
            continue  # the tool couldn't read this environment
        ev = e.get("variations")
        if ev and (not variations or _indexed(ev) and not _indexed(variations)):
            variations = ev  # the tool's indexed list beats values in an unknown order
        out[name] = {
            "on": bool(e.get("on")),
            "offVariation": _index(e.get("off_variation")),
            "fallthrough": _served_spec(e.get("fallthrough")),
            "rules": [{**_served_spec(r.get("serves")), "disabled": bool(r.get("disabled")),
                       "clauses": [{"attribute": c.get("attribute"), "op": c.get("op"),
                                    "values": c.get("values") or [], "negate": bool(c.get("negate")),
                                    "contextKind": c.get("context_kind") or c.get("contextKind")}
                                   for c in r.get("clauses") or []]}
                      for r in e.get("rules") or []],
            "targets": [{"variation": _index(t.get("variation")), "values": t.get("values") or []}
                        for t in e.get("targets") or []],
            "contextTargets": [{"variation": _index(t.get("variation")), "values": t.get("values") or [],
                                "contextKind": t.get("context_kind") or t.get("contextKind")}
                               for t in e.get("context_targets") or e.get("contextTargets") or []],
            "prerequisites": [{"key": p.get("flag_key") or p.get("key"),
                               "variation": p.get("variation_index", p.get("variation"))}
                              for p in e.get("prerequisites") or []],
        }
    flag = {**flag, "environments": out}
    if variations:
        vs = [v if isinstance(v, dict) else {"value": v} for v in variations]
        if _indexed(vs):  # the tool may list them out of index order
            vs = sorted(vs, key=lambda v: v["index"])
        flag["variations"] = [{"value": v.get("value")} for v in vs]
    return flag


class LDClient:
    """Read-only LD reader with as-of-merge-date reconstruction.

    The as-of rules, which are what make P7 answerable at all:
      * creationDate after the merge date       -> the flag did not exist yet
      * env lastModified <= the merge date      -> today's value IS the merge
                                                   value, nothing has touched it
      * env lastModified >  the merge date      -> reconstruct from the audit
                                                   log: the LAST pre-merge
                                                   entry's currentVersion, else
                                                   the EARLIEST post-merge
                                                   entry's previousVersion (see
                                                   state_at)
    Anything else stays None with an `indeterminate:*` basis, so P7 answers NO
    and the walk escalates rather than guessing.
    """

    def __init__(self, ld: dict, api_key: str | None = None, timeout: int = 45):
        self.base = ld["base_url"].rstrip("/")
        self.project = ld["project"]
        # key -> (project, {profile env name: that project's env name}), for
        # flags that live outside the profile's project (set_key_project).
        self.key_projects: dict[str, tuple[str, dict[str, str]]] = {}
        # key -> the code's default, for keys whose absence from LD means
        # "serves the default" (set_code_default).
        self.code_defaults: dict[str, tuple[bool, bool]] = {}
        self.decision_envs = list(ld["decision_environments"])
        self.user_facing = list(ld["user_facing_production"])
        # P11's environment (ruling R5): a profile may name it; else the first
        # user-facing one.
        self.main_production = ld.get("main_production") or self.user_facing[0]
        self.non_user = tuple(str(a).lower() for a in ld.get("non_user_audiences") or [])
        # (audit spec) -> that environment's full configuration as of the
        # merge, stashed by the audit readers so snapshot() can read targeting
        # without changing state_at's (on, basis) contract.
        self._cfg_at: dict[str, dict] = {}
        # (key, merged) -> {env: configuration as of the merge}, for
        # prerequisite lookups.
        self._cfgs: dict[tuple[str, str], dict[str, dict]] = {}
        self.timeout = timeout
        # The caller passes the key; this never reads one from the environment.
        self.key = api_key or ""

    @property
    def available(self) -> bool:
        return bool(self.key)

    def _get(self, path: str, **params) -> dict:
        if not self.key:
            raise LDUnavailable("no LaunchDarkly API key")
        url = self.base + path
        if params:
            # safe=":/" matters: an audit `spec` is proj/X:env/Y:flag/Z and the
            # percent-encoded form returns zero entries SILENTLY, which reads
            # as "this flag never changed".
            url += "?" + urllib.parse.urlencode(params, safe=":/")
        req = urllib.request.Request(url, headers={"Authorization": self.key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return {"_status": e.code}
        except urllib.error.URLError as e:
            return {"_status": f"network:{e.reason}"}

    @staticmethod
    def _date(ms) -> str | None:
        if not ms:
            return None
        return datetime.fromtimestamp(ms / 1000, timezone.utc).date().isoformat()

    @staticmethod
    def _cutoff_ms(as_of: str) -> int:
        """`as_of` in ms: an ISO timestamp as given (UTC when it names no
        zone), a bare date as the end of that UTC day. A day's end lets in
        whatever was created or changed after the PR opened that same day
        (an earlier PR, an earlier PR), so pass the timestamp when it
        is known."""
        if "T" not in as_of:
            as_of += "T23:59:59+00:00"
        t = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return int(t.timestamp() * 1000)

    def set_key_project(self, key: str, project: str | None,
                        env_map: dict[str, str] | None = None) -> None:
        """."""
        self.key_projects[key] = (project, dict(env_map or {}))

    def set_code_default(self, key: str, value: bool,
                         added_by_diff: bool) -> None:
        """What the code serves for `key` when LD has no such flag."""
        self.code_defaults[key] = (value, added_by_diff)

    def _default_snapshot(self, key: str, why: str) -> dict | None:
        if key not in self.code_defaults:
            return None
        value, _ = self.code_defaults[key]
        basis = f"{why}: serves the code default ({str(value).lower()})"
        return {"key": key, "exists": False, "readable": True,
                "environments": {n: {"on": value, "basis": basis}
                                 for n in self.decision_envs},
                "user_facing_resolved": True, "unreadable_environments": [],
                "absent_environments": [], "basis": basis}

    def _where(self, key: str, env: str | None = None) -> tuple[str, str | None]:
        project, env_map = self.key_projects.get(key, (self.project, {}))
        return project, (env_map.get(env, env) if env else None)

    def state_at(self, key: str, env: str, merged: str) -> tuple[bool | None, str]:
        """`on` in `env` as of the end of `merged`, reconstructed from the
        audit log.

        Primary: the `currentVersion` of the LAST pre-merge entry that
        carries this env's state -- the state after the last change before
        the merge is the state at the merge. Fallback: the `previousVersion`
        of the FIRST post-merge entry that carries it.

        Both are read. Changes made through LD's approval workflow leave
        post-merge entries whose `previousVersion` is the approval request,
        and "updated the flag" entries with no `previousVersion` at all
        (an earlier PR), so often only the pre-merge side has a value."""
        project, env = self._where(key, env)
        spec = f"proj/{project}:env/{env}:flag/{key}"
        merged_ms = self._cutoff_ms(merged)
        pre, pre_basis = self._state_from_last_pre_merge(spec, env, merged_ms)
        if pre_basis.startswith("indeterminate:audit-http"):
            return None, pre_basis
        post, post_basis = self._state_from_first_post_merge(spec, env,
                                                             merged_ms)
        if pre is not None and post is not None:
            if pre == post:
                self._cfg_at[spec] = self._cfg_at.get("pre:" + spec) or {}
                return pre, "audit-reconstructed"
            return None, (f"indeterminate:audit-history-inconsistent "
                          f"(last pre-merge entry says on={pre}, first "
                          f"post-merge entry says on={post})")
        if pre is not None:
            self._cfg_at[spec] = self._cfg_at.get("pre:" + spec) or {}
            return pre, pre_basis
        if post is not None:
            self._cfg_at[spec] = self._cfg_at.get("post:" + spec) or {}
            return post, post_basis
        if pre_basis.startswith("indeterminate:"):
            return None, pre_basis
        if post_basis.startswith("indeterminate:"):
            return None, post_basis
        return None, f"indeterminate:{pre_basis}/{post_basis}"

    def _state_from_last_pre_merge(self, spec: str, env: str,
                                   merged_ms: int) -> tuple[bool | None, str]:
        res = self._get("/api/v2/auditlog", spec=spec, limit=20,
                        before=merged_ms)
        if res.get("_status"):
            return None, f"indeterminate:audit-http-{res['_status']}"
        newer: list[str] = []
        for entry in sorted(res.get("items") or [], key=lambda i: i["date"],
                            reverse=True):
            det = self._get(f"/api/v2/auditlog/{entry['_id']}")
            e = ((det.get("currentVersion") or {}).get("environments")
                 or {}).get(env)
            if isinstance(e, dict) and "on" in e:
                if all(_is_non_state_verb(v) for v in newer):
                    self._cfg_at["pre:" + spec] = e
                    return bool(e["on"]), "audit-reconstructed-pre-merge"
                return None, ("indeterminate:pre-merge-state-changing-"
                              "entries-without-state")
            newer.append(str(entry.get("titleVerb") or "?"))
        return None, "no-pre-merge-entry-carries-state"

    def _state_from_first_post_merge(self, spec: str, env: str,
                                     merged_ms: int
                                     ) -> tuple[bool | None, str]:
        # The log returns the NEWEST entries first. Bound it to a window just
        # after the merge and read the whole window (paging back inside it),
        # widening the window until one holds an entry: the earliest entry in
        # the first non-empty window is the first post-merge entry, however
        # much history has piled up since. Past the page cap INSIDE a window
        # the first entry is unknown: report that rather than read a later
        # entry's previousVersion as the merge state.
        items: list[dict] = []
        for days in _POST_MERGE_WINDOWS_DAYS:
            hi = merged_ms + days * 86_400_000
            items, before, complete = [], hi, False
            for _ in range(_MAX_AUDIT_PAGES):
                params = {"spec": spec, "limit": 20, "after": merged_ms,
                          "before": before}
                res = self._get("/api/v2/auditlog", **params)
                if res.get("_status"):
                    return None, f"indeterminate:audit-http-{res['_status']}"
                page = [i for i in (res.get("items") or [])
                        if merged_ms < i.get("date", 0) < hi]
                items += page
                if len(res.get("items") or []) < 20:
                    complete = True
                    break
                before = min(i["date"] for i in page) if page else merged_ms
            if not complete:
                return None, "post-merge-history-exceeds-page-cap"
            if items:
                break
        items.sort(key=lambda i: i["date"])
        if not items:
            return None, "no-post-merge-audit-entries"
        skipped: list[str] = []
        for entry in items:
            det = self._get(f"/api/v2/auditlog/{entry['_id']}")
            e = ((det.get("previousVersion") or {}).get("environments")
                 or {}).get(env)
            if isinstance(e, dict) and "on" in e:
                if all(_is_non_state_verb(v, forward=True) for v in skipped):
                    self._cfg_at["post:" + spec] = e
                    return bool(e["on"]), "audit-reconstructed"
                return None, "indeterminate:skipped-state-changing-entries"
            skipped.append(str(entry.get("titleVerb") or "?"))
        return None, "no-audit-entry-carries-state"

    def snapshot(self, key: str, merged: str, _depth: int = 0,
                 exposing_values: list | None = None) -> dict:
        """Per-environment `on` as of `merged`, with a basis per field, and
        who that environment serves the exposing variation to (`serves`, see
        serving()) when its targeting could be read. `exposing_values` names
        a multivariate flag's exposing value(s) (exposing_variations)."""
        project, _ = self._where(key)
        if project is None:
            # A client repository's flag whose LaunchDarkly project isn't
            # known (gate_search.client_key_project): unknown, never off.
            return {"key": key, "readable": False,
                    "basis": "indeterminate:ld-project-unknown"}
        flag = self._get(f"/api/v2/flags/{project}/{key}")
        if flag.get("_status") == 404 and (self.code_defaults.get(key) or
                                           (None, False))[1]:
            return self._default_snapshot(key, "added by this diff and never "
                                               "created in LaunchDarkly")
        if flag.get("_status"):
            return {"key": key, "readable": False,
                    "basis": f"indeterminate:flag-http-{flag['_status']}"}
        if not flag.get("key"):
            return {"key": key, "exists": False, "readable": True,
                    "basis": "absent-from-launchdarkly"}
        cutoff = self._cutoff_ms(merged) if merged else None
        created = self._date(flag.get("creationDate"))
        if created and cutoff is not None and flag["creationDate"] > cutoff:
            d = self._default_snapshot(key, f"created in LaunchDarkly on "
                                            f"{created}, after the merge")
            if d:
                return {**d, "created": created, "as_of": merged}
            return {"key": key, "exists": False, "readable": True,
                    "created": created, "as_of": merged,
                    "basis": "created-after-merge"}
        envs, bad, cfgs = {}, [], {}
        for name in self.decision_envs:
            env = self._where(key, name)[1]
            e = (flag.get("environments") or {}).get(env)
            if not e:
                continue
            lm = self._date(e.get("lastModified"))
            if lm and cutoff is not None and e["lastModified"] <= cutoff:
                envs[name] = {"on": bool(e.get("on")), "last_modified": lm,
                              "basis": "unchanged-since-merge"}
                cfgs[name] = e
            else:
                on, basis = self.state_at(key, name, merged)
                envs[name] = {"on": on, "last_modified": lm, "basis": basis}
                if on is None:
                    bad.append(name)
                else:
                    cfgs[name] = self._cfg_at.get(
                        f"proj/{project}:env/{env}:flag/{key}") or {}
        self._cfgs[(key, merged)] = cfgs
        targets = exposing_variations(flag, exposing_values)
        absent = targets == set() and bool(exposing_values)
        if targets is not None:
            for name, cfg in cfgs.items():
                if "fallthrough" not in cfg and "rules" not in cfg:
                    continue  # the audit entry carried `on` but no targeting
                if bool(cfg.get("on")) != bool(envs[name]["on"]):
                    continue
                reach, why = serving(cfg, targets, self.non_user)
                if absent:
                    why = (f"no variation of the flag is "
                           f"{' or '.join(repr(v) for v in exposing_values)}")
                reach, why = self._through_prerequisites(cfg, name, merged,
                                                          reach, why, _depth)
                envs[name].update(serves=reach, serves_basis=why)
        missing = [n for n in self.user_facing if n not in envs]
        return {
            "key": key, "exists": True, "readable": True, "as_of": merged,
            "environments": envs,
            "archived": bool(flag.get("archived")),
            **({"exposing_values": list(exposing_values)}
               if exposing_values and targets is not None else {}),
            "user_facing_resolved": (not [n for n in bad
                                          if n in self.user_facing]
                                     and not missing),
            "unreadable_environments": bad,
            "absent_environments": missing,
            "basis": "per-environment",
        }

    def _through_prerequisites(self, cfg: dict, name: str, merged: str,
                               reach: str, why: str, depth: int
                               ) -> tuple[str, str]:
        """Narrow `reach` by the flag's prerequisites: a context that fails
        one is served the off variation, so the flag reaches at most whom
        every prerequisite serves its required variation. A prerequisite
        that is off fails for everyone, whatever its off variation (LD's
        evaluation rule). A prerequisite that cannot be read leaves only
        `none` settled."""
        if not cfg.get("on") or reach in ("none", "internal"):
            return reach, why
        order = {"none": 0, "internal": 1, "cohort": 2, "partial": 3, "all": 4}
        for p in cfg.get("prerequisites") or []:
            pk, pv = p.get("key"), p.get("variation")
            if depth >= 2 or not pk:
                return "unknown", f"{why}; prerequisite {pk} not followed"
            if (pk, merged) not in self._cfgs:
                self.snapshot(pk, merged, _depth=depth + 1)
            pcfg = self._cfgs.get((pk, merged), {}).get(name)
            if not pcfg or ("fallthrough" not in pcfg and "rules" not in pcfg):
                return "unknown", f"{why}; prerequisite {pk} unreadable"
            preach, pwhy = (serving(pcfg, {pv}, self.non_user)
                            if pcfg.get("on") else ("none", "off"))
            if order[preach] < order[reach]:
                reach, why = preach, f"{why}; but prerequisite {pk} is {pwhy}"
        return reach, why


# ---------------------------------------------------------------------------
# citation verification -- shared by ask.py (keyed) and merge_inline.py (inline)
# ---------------------------------------------------------------------------

GATE_SHAPE_WINDOW = 2
"""Lines of slack on either side of a referenced_context citation when
looking for a conditional/symbol -- see verify_citation's use of this for
why an exact-line-only check was too strict."""

CONDITIONAL_TOKENS = ("&&", "if ", "if(", "?")
"""A cheap, mechanical sanity check for a referenced_context citation: the
cited line's own text must contain either the matched symbol or something
that looks like a conditional, so a citation can't point at a real line
inside the shown window that has nothing to do with a gate. Not semantic
verification -- just enough to catch a real-but-irrelevant citation."""


_SIBLING_EXTENSIONS = [{".ts", ".tsx"}, {".js", ".jsx"}]


def _extension_tolerant_match(cited_path: str, candidates) -> str | None:
    """A citation to `Foo.ts` when the real file the model was shown is
    `Foo.tsx` is a one-character transcription slip, not a fabrication: the
    packet renders the real path with the right extension right there in
    the "REFERENCED FILES"/diff header, and the model's own evidence text
    reasons about the correct file -- it just retyped the extension when
    filling in the separate structured `path` field, dropping the trailing
    `x` (`.tsx` -> `.ts` reads as the more common TS extension, an easy
    autocomplete-shaped slip). Measured on an earlier PR: a P6 sample
    correctly answered "yes" with correct reasoning, cited
    `ViewSettings.ts`, and had the whole answer discarded as UNRESOLVED over
    that one character -- contributing a false split.

    Deliberately narrow: only a swap within one of `_SIBLING_EXTENSIONS`,
    with everything else in the path byte-identical. This must never widen
    to a fuzzy/basename-only match -- that would legitimize a citation to a
    genuinely different file that merely shares a name, which is exactly
    the fabrication this whole check exists to catch.
    """
    base, ext = os.path.splitext(cited_path)
    for pair in _SIBLING_EXTENSIONS:
        if ext not in pair:
            continue
        for other_ext in pair - {ext}:
            candidate = base + other_ext
            if candidate in candidates:
                return candidate
    return None


# P10 asks whether the change belongs to a candidate's feature, and the
# enclosing gate P6 found is a candidate (mechanical.enclosing_gate_candidates),
# so it may cite the gate's lines as well; not listed in the evidence text.
CITES_GATE_FILES_EXTRA = frozenset({"P10"})
GATE_DEPENDENT_PREDICATES = frozenset({"P6", "P7", "P8", "P11", "P12", "P21"}) | specload.gate_evidence_ids(
    Path(__file__).resolve().parent.parent)
"""Predicates whose own procedure text reasons about the SAME ancestor gate
P6 establishes (P7/P8/P11: does it exist, does it withhold, is it fully
released; P21: is a hunk reachable given its state) -- as opposed to a predicate like P15 that
has no reason to look outside the diff at all. Citing referenced_context is
legitimate evidence for any of these, not just P6 itself.

P12 (would a candidate's off arm withhold every hunk?) is enclosure by the
candidate's gate, so the callers that gate is evaluated in are its evidence.
Measured on an earlier PR: the changed query options are shared by the diff's
TokensPagination.tsx and by TokensPage.tsx, a referenced file gated by the
same candidate -- one P12 sample, barred from using that file, escalated for
want of exactly the evidence the packet already showed."""


SHOWN_NOT_GATE_PREDICATES = frozenset({"P21"})
"""Gate-dependent predicates whose referenced-context citations need only be
grounded in the window shown, not gate-shaped. P21 asks what a user of the
referenced screen or caller perceives, so the line it cites is what renders
the change (a page title, a heading), not a conditional. Measured on
an earlier PR: every P21 sample cited the screen's `<title>` and lost its
answer to the gate-shape check, which exists to keep P6's ancestor-gate
claims honest."""


def verify_citations(citations: list[dict], known_diff_paths: set[str],
                     referenced_context: list[dict] | None = None,
                     file_lines: dict[str, list[str]] | None = None,
                     predicate_id: str | None = None,
                     deleted_ranges: dict[str, list[tuple[int, int]]]
                     | None = None,
                     diff_gate_lines: dict[str, set[int]] | None = None,
                     claims_enclosure: bool = True
                     ) -> tuple[bool, str]:
    """Check an answer's citations as a set, the way ask.py and
    merge_inline.py both need it.

    Every citation must be grounded (see `verify_citation`), including being
    inside the referenced window actually shown. But among citations into
    referenced files, only ONE has to look like a gate: an answer that points
    at the gate and also at the lines it guards is doing exactly what it
    should. Measured on an earlier PR: a P6 sample citing the real gate plus
    supporting lines in the same shown window lost its whole answer to the
    per-citation gate-shape check, splitting an otherwise unanimous YES.
    """
    ref_cited = ref_shaped = False
    shape_why = ""
    for c in citations:
        ok, why = verify_citation(c, known_diff_paths, referenced_context,
                                  file_lines, predicate_id,
                                  require_gate_shape=False,
                                  deleted_ranges=deleted_ranges)
        if not ok:
            return False, why
        path = c.get("path")
        if path in known_diff_paths or _extension_tolerant_match(
                path, known_diff_paths):
            continue
        ref_cited = True
        ok, why = verify_citation(c, known_diff_paths, referenced_context,
                                  file_lines, predicate_id)
        if ok:
            ref_shaped = True
        elif not shape_why:
            shape_why = why
    if ref_cited and not ref_shaped and (predicate_id in SHOWN_NOT_GATE_PREDICATES
                                         or not claims_enclosure):
        return True, ""
    if ref_cited and not ref_shaped:
        if diff_gate_lines and any(
                c.get("path") in diff_gate_lines and isinstance(c.get("line"), int)
                and any(abs(c["line"] - g) <= GATE_SHAPE_WINDOW
                        for g in diff_gate_lines[c["path"]])
                for c in citations):
            return True, ""
        return False, shape_why
    return True, ""


def verify_citation(citation: dict, known_diff_paths: set[str],
                    referenced_context: list[dict] | None = None,
                    file_lines: dict[str, list[str]] | None = None,
                    predicate_id: str | None = None,
                    require_gate_shape: bool = True,
                    deleted_ranges: dict[str, list[tuple[int, int]]]
                    | None = None,
                    ) -> tuple[bool, str]:
    """Is this citation grounded in something the answerer was actually shown?

    Two legitimate sources, and nothing else:
      1. `known_diff_paths` -- the diff's own changed files. Unchanged rule.
      2. `referenced_context` -- files OUTSIDE the diff that were fetched and
         rendered for P6 enclosure judgment (see mechanical.py). A citation
         into one of these is only accepted if `predicate_id` is one of
         `GATE_DEPENDENT_PREDICATES` (or omitted, for callers that don't pass
         it), AND the line falls inside the SPECIFIC range that was actually
         shown (not just anywhere in that file), AND the cited line's own
         text is structurally consistent with a gate (contains the matched
         symbol or a conditional token) -- "a real path/line exists
         somewhere" is never sufficient on its own.

    The restriction on source 2 closes a real gap: the SYSTEM prompt already
    tells the model referenced_context is "P6 only", but the check itself
    accepted a referenced_context citation from ANY predicate until this was
    added. Measured on an earlier PR, twice, in opposite directions:
      * P14 ("does this hunk touch a named high-blast-radius class?") has no
        reason to look outside the diff at all -- a sample cited the P6
        evidence anyway, got rejected, and lost an otherwise-correct "no" to
        the split. Restricting to P6 fixed this.
      * P17 ("does a hunk call something still withheld?") is directly ABOUT
        the same gate P6 found -- restricting to literally just "P6" then
        made all 3 samples unanimously fail for wanting the same evidence
        P6 legitimately uses. GATE_DEPENDENT_PREDICATES is the fix: P14 has
        no business here either way; P7/P8/P11/P17/P21 do, because their own
        procedures are about that gate's existence/state, not just P6's.

    `file_lines`, when given, is `{path: [line, ...]}` for in-diff files, used
    to keep the existing line-bounds check for path 1. Callers that don't have
    this handy (merge_inline.py, which never reads the repo) can omit it.

    `deleted_ranges`, when given, is `{path: [(old_lo, old_hi), ...]}` -- the
    old-side range of each hunk. A line past the end of the file at head is
    still grounded if it falls in one: a hunk that deletes code is naturally
    cited by the deleted line's old number. Measured on an earlier PR: a P2
    sample cited useReleaseGuardian.ts:33 (inside a deleted 49-line block;
    the file has 29 lines at head) and turned a 3-0 "no" into a split.
    """
    path, line = citation.get("path"), citation.get("line")
    if path not in known_diff_paths:
        resolved = _extension_tolerant_match(path, known_diff_paths)
        if resolved:
            path = resolved
    if path in known_diff_paths:
        lines = (file_lines or {}).get(path)
        if lines is not None and isinstance(line, int) and line > len(lines) \
                and not any(lo <= line <= hi for lo, hi in
                            (deleted_ranges or {}).get(path, [])):
            return False, (f"cites {path}:{line} but that file has "
                           f"{len(lines)} lines at head and the line is not "
                           f"in any hunk's deleted (old-side) range")
        return True, ""

    if predicate_id is not None and predicate_id not in GATE_DEPENDENT_PREDICATES | CITES_GATE_FILES_EXTRA:
        return False, (f"cites {path}, a referenced-context file -- only "
                       f"legitimate for a gate-dependent predicate "
                       f"({sorted(GATE_DEPENDENT_PREDICATES)}), not "
                       f"{predicate_id}")

    rc_paths = {rc["path"] for rc in referenced_context or []}
    resolved = _extension_tolerant_match(citation.get("path"), rc_paths)
    if resolved:
        path = resolved
    for rc in referenced_context or []:
        if rc["path"] != path:
            continue
        if not (isinstance(line, int) and rc["lo"] <= line <= rc["hi"]):
            continue
        if not require_gate_shape:
            return True, ""
        lines = rc["text"].splitlines()
        idx = line - rc["lo"]
        cited_text = lines[idx] if 0 <= idx < len(lines) else ""
        symbol = rc.get("matched_symbol") or ""
        near = lines[max(0, idx - GATE_SHAPE_WINDOW):
                     min(len(lines), idx + GATE_SHAPE_WINDOW + 1)]
        if any((symbol and symbol in t) or
               any(tok in t for tok in CONDITIONAL_TOKENS) for t in near):
            return True, ""
        if any(abs(line - gl) <= GATE_SHAPE_WINDOW
               for gl in rc.get("gate_lines") or []):
            return True, ""
        return False, (f"cites {path}:{line}, which is in the shown "
                       f"referenced-context window but doesn't look like "
                       f"part of a gate ({cited_text.strip()[:80]!r})")

    shown = [f"{rc['lo']}-{rc['hi']}" for rc in referenced_context or []
             if rc["path"] == path]
    if shown:
        return False, (f"cites {path}:{line}, outside the lines shown "
                       f"({', '.join(shown)}); cite a line inside them")
    return False, (f"cites {path}, which is neither a changed file in the "
                   f"packet nor one of the referenced-context files shown "
                   f"for enclosure judgment")
