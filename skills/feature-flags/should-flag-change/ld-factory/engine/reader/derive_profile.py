"""Derive a repo profile from the repo itself, so the skill needs no
hand-written profile for it.

    python3 -m reader.derive_profile REPO [--rev REV] [-o profile.json]

A profile tells the reader what a flag check looks like in a repo (see
skill/PROFILE.md for the shape). Everything here is read from the repo at one
commit, with git only:

- the LaunchDarkly SDKs it uses (package manifests), and their own evaluation
  calls with a literal key (`keyed_calls`);
- `.launchdarkly/coderefs.yaml`, LaunchDarkly Code References' config: its
  `filepattern` aliases say where flag keys are declared and which name the
  code uses for each, and its `projKey` / `baseUri` the project and instance;
- declaration files: many named constants bound to flag-key strings in a file
  whose path names flags (a Go `const FlagX Flag = "x"` block, a TypeScript
  `export const newCheckout = 'new-checkout'` list), and the calls that
  reference those names (`resolved_patterns`);
- wrapper files: SDK evaluation calls whose key is a variable, i.e. the
  repo's own flag helper, excluded so its internal call isn't read as the
  gate for every flag;
- path roles by convention, `.gitattributes` linguist markers and migration
  folders, and the CODEOWNERS file.

Anything it can't see (a published-API spec, product code that mentions
flags without gating on them, a second LaunchDarkly project) belongs in a
profile file committed in the repo, which is merged over this one.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

KEY = r"[A-Za-z0-9][A-Za-z0-9._-]*"

# SDK packages per family, as they appear in manifests.
SDKS = {
    "go": [r"github\.com/launchdarkly/go-server-sdk", r"github\.com/launchdarkly/go-sdk-common"],
    "node": [r"launchdarkly-node-server-sdk", r"@launchdarkly/node-server-sdk"],
    "js": [r"launchdarkly-js-client-sdk", r"@launchdarkly/js-client-sdk", r"launchdarkly-react-client-sdk",
           r"@launchdarkly/react-client-sdk", r"@launchdarkly/react-native-client-sdk"],
    "python": [r"\blaunchdarkly-server-sdk\b", r"\bldclient\b"],
    "ruby": [r"launchdarkly-server-sdk"],
    "java": [r"com\.launchdarkly"],
    "dotnet": [r"LaunchDarkly\.(?:ServerSdk|ClientSdk)"],
}
MANIFESTS = ["go.mod", "package.json", "requirements*.txt", "pyproject.toml", "Pipfile", "Gemfile",
             "pom.xml", "build.gradle*", "*.csproj"]

# Each SDK family's own evaluation calls that take the key first.
KEYED = {
    "go": r"\b\w+\.(?:Bool|Int|Float64|String|JSON)Variation(?:Detail)?(?:Ctx)?\(",
    "node": r"\b\w+\.(?:variation|boolVariation|stringVariation|numberVariation|jsonVariation|variationDetail)\(",
    "js": r"\b\w+\.(?:variation|boolVariation|stringVariation|numberVariation|jsonVariation|variationDetail)\(",
    "python": r"\b\w+\.variation(?:_detail)?\(",
    "ruby": r"\b\w+\.variation(?:_detail)?\(",
    "java": r"\b\w+\.(?:bool|int|double|string|json)Variation(?:Detail)?\(",
    "dotnet": r"\b\w+\.(?:Bool|Int|Float|Double|String|Json)Variation(?:Detail)?\(",
}
REACT_HOOKS = r"\buse(?:Bool|String|Number|Json)Variation\("
EXT = {"go": ["*.go"], "node": ["*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs"],
       "js": ["*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs"], "python": ["*.py"], "ruby": ["*.rb"],
       "java": ["*.java", "*.kt"], "dotnet": ["*.cs"]}
NOT_CODE = [":!**/node_modules/**", ":!**/vendor/**", ":!**/*_test.go", ":!**/*.test.*", ":!**/*.spec.*",
            ":!**/__tests__/**", ":!**/__mocks__/**", ":!**/testdata/**", ":!**/fixtures/**", ":!docs/**",
            ":!**/*.md"]

PATH_ROLES = {
    "test": ["**/__tests__/**", "**/__mocks__/**", "**/__fixtures__/**", "**/*-test.ts", "**/*-test.tsx",
             "**/*-test.js", "**/*-test.jsx", "**/*.test.*", "**/*.spec.*", "**/*_test.go", "**/*_test.py",
             "**/test_*.py", "**/testdata/**", "**/fixtures/**", "**/tests/**", "**/e2e/**"],
    "docs": ["**/*.md", "docs/**"],
    "build_ci": [".github/workflows/**", "**/Makefile", "**/*.lock", "**/go.sum", "**/package-lock.json",
                 "**/yarn.lock", "**/pnpm-lock.yaml", "**/BUILD.bazel", "**/tsconfig*.json", "**/.eslintrc*"],
    "generated": ["**/generated/**", "**/*.pb.go", "**/*_generated.*", "**/*.generated.*"],
    "ships_anyway": ["**/Dockerfile*", "**/*.sql", "**/migrations/**", "**/skills/**/*.md", "**/prompts/**"],
}


def git(repo, *args) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, errors="replace")
    return p.stdout if p.returncode in (0, 1) else ""


def files_at(repo, rev) -> list[str]:
    return git(repo, "ls-tree", "-r", "--name-only", rev).splitlines()


def show(repo, rev, path) -> str | None:
    p = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{path}"], capture_output=True, text=True,
                       errors="replace")
    return p.stdout if p.returncode == 0 else None


def grep(repo, rev, pattern, paths) -> list[tuple[str, int, str]]:
    out = []
    for line in git(repo, "grep", "-n", "-P", "-I", pattern, rev, "--", *paths).splitlines():
        try:
            _, path, ln, text = line.split(":", 3)
        except ValueError:
            continue
        out.append((path, int(ln), text))
    return out


def origin_slug(repo) -> str | None:
    url = git(repo, "remote", "get-url", "origin").strip()
    m = re.search(r"[:/]([^/:]+/[^/:]+?)(?:\.git)?/?$", url)
    return m.group(1) if m else None


def sdk_families(repo, rev, all_files) -> list[str]:
    import fnmatch
    manifests = [f for f in all_files if any(fnmatch.fnmatch(Path(f).name, m) for m in MANIFESTS)
                 and "node_modules/" not in f and "vendor/" not in f]
    found = set()
    for f in manifests:
        text = show(repo, rev, f) or ""
        for fam, pats in SDKS.items():
            if any(re.search(p, text) for p in pats):
                if fam in ("node", "js", "ruby") and not f.endswith(("package.json", "Gemfile")):
                    continue
                if fam == "ruby" and not f.endswith("Gemfile"):
                    continue
                found.add(fam)
    return sorted(found)


def coderefs(repo, rev) -> dict:
    """`.launchdarkly/coderefs.yaml`, parsed with a tiny YAML subset reader
    (the skill runs without PyYAML): projKey, baseUri, and filepattern aliases."""
    text = show(repo, rev, ".launchdarkly/coderefs.yaml") or show(repo, rev, ".launchdarkly/coderefs.yml")
    if not text:
        return {}
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        pass
    out: dict = {"aliases": []}
    cur = None
    section = None
    for raw in text.splitlines():
        line = raw.split(" #")[0].rstrip()
        if not line.strip():
            continue
        m = re.match(r"^(projKey|baseUri):\s*(.+)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip("'\"")
            continue
        if re.match(r"^\s*-\s*type:\s*", line):
            cur = {"type": line.split(":", 1)[1].strip().strip("'\""), "paths": [], "patterns": []}
            out["aliases"].append(cur)
            section = None
        elif cur is not None and re.match(r"^\s*(paths|patterns):\s*$", line):
            section = line.strip().rstrip(":")
        elif cur is not None and section and re.match(r"^\s*-\s+", line):
            cur[section].append(line.split("-", 1)[1].strip().strip("'\""))
        elif cur is not None and re.match(r"^\s*name:\s*", line):
            cur["name"] = line.split(":", 1)[1].strip()
    return out


def alias_declarations(cr: dict) -> list[dict]:
    """filepattern aliases -> flag_declarations. A pattern names the code's
    identifier in one group and has FLAG_KEY where the key goes."""
    decls = []
    for i, a in enumerate(cr.get("aliases") or []):
        if str(a.get("type", "")).lower() != "filepattern":
            continue
        for j, pat in enumerate(a.get("patterns") or []):
            if "FLAG_KEY" not in pat:
                continue
            before = pat.split("FLAG_KEY")[0]
            groups_before = len(re.findall(r"(?<!\\)\((?!\?)", before))
            regex = pat.replace("FLAG_KEY", f"({KEY})")
            try:
                re.compile(regex)
            except re.error:
                continue
            n_groups = re.compile(regex).groups
            key_group = groups_before + 1
            symbol_group = 1 if key_group != 1 and n_groups >= 2 else None
            # An alias that only captures the key itself (`(FLAG_KEY):` over
            # *.yaml) says where keys are MENTIONED, not how the code names
            # them: not a declaration.
            if symbol_group is None or re.fullmatch(r"\(*\(" + re.escape(f"({KEY})") + r"\)*.*", regex):
                continue
            if before.strip().startswith("(") and before.count("(") == groups_before and not re.search(r"\(\\w|\(\[", before):
                continue
            paths = a.get("paths") or []
            d = {"id": f"coderefs-{i}-{j}", "pattern": regex, "key_group": key_group, "expect_at_least": 1}
            if symbol_group:
                d["symbol_group"] = symbol_group
            if re.fullmatch(r"""['"`]?,?""", pat.split("FLAG_KEY", 1)[1]):
                d["pattern"] = regex = regex + r"(?:\s*,?\s*(true|false)\b)?"
                d["default_group"] = n_groups + 1
            if len(paths) == 1 and not any(c in paths[0] for c in "*?["):
                d["file"] = paths[0]
                d["multiline"] = True
                # A global inline flag (`(?i)`) stays first: Python refuses
                # one anywhere else, so `^.*?(?i)...` crashed every run on
                # the repo (Fieldguide's feature-flags).
                lead = re.match(r"(?:\(\?[aiLmsux]+\))*", regex).group(0)
                if not regex[len(lead):].startswith("^"):
                    d["pattern"] = lead + r"^.*?" + regex[len(lead):]
            else:
                d["files"] = paths
            decls.append(d)
    return decls


def constant_files(repo, rev, families) -> list[dict]:
    """Files that bind many names to flag-key strings, with flags in their path."""
    decls = []
    specs = []
    if "go" in families:
        specs.append(("go", ["*.go"] + NOT_CODE,
                      r'^\s*([A-Z][A-Za-z0-9_]*)\s+(?:[A-Za-z_][\w.]*\s*)?=\s*"(' + KEY + r')"\s*$'))
    if families and set(families) & {"node", "js"}:
        specs.append(("ts", ["*.ts", "*.tsx", "*.js"] + NOT_CODE,
                      r"^\s*export\s+const\s+([A-Za-z_$][\w$]*)\s*(?::\s*[\w<>\[\]|' ]+)?=\s*['\"](" + KEY + r")['\"]"))
    for lang, paths, pat in specs:
        hits = grep(repo, rev, pat, paths)
        per = Counter(p for p, _, _ in hits)
        for path, n in per.items():
            if not re.search(r"flag", path, re.I):
                continue
            types = Counter((re.match(r"\s*[A-Z]\w*\s+([A-Za-z_][\w.]*)?\s*=", t) or [None, None])[1]
                            for q, _, t in hits if q == path) if lang == "go" else Counter()
            top, c = types.most_common(1)[0] if types else (None, 0)
            vals = [m.group(1) for q, _, t in hits if q == path
                    for m in [re.search(r'=\s*"([^"]*)"', t)] if m] if lang == "go" else []
            typed_flags = (lang == "go" and bool(top) and bool(re.search(r"(?:^|\.)\w*Flag(?:Key)?$", top))
                           and c >= 2 and sum("-" in v for v in vals) * 2 >= len(vals))
            small = n < 10  # the file's own count, before a type restriction narrows n
            if n >= 10 or typed_flags:
                file_pat = pat
                if lang == "go":
                    # Typed constants: keep the type most of them share (the
                    # flag-key type), so an enum beside them (FlagTypeJSON
                    # FlagType = "json") isn't read as a key.
                    # A file of ten or more keeps the rule it always had; the key-type
                    # restriction only decides a small file, which counts no other way.
                    if (len(types) > 1 and c >= 0.8 * n) or (typed_flags and small):
                        file_pat = (r'^\s*([A-Z][A-Za-z0-9_]*)\s+' + (re.escape(top) + r"\s*" if top else "")
                                    + r'=\s*"(' + KEY + r')"\s*$')
                        n = c
                if typed_flags and small:
                    # code in the declaring package names these constants bare
                    syms = [m.group(1) for q, _, tx in hits if q == path for m in [re.match(file_pat, tx)] if m]
                else:
                    syms = []
                d = {"id": f"{lang}-constants-{Path(path).stem}", "file": path, "pattern": file_pat,
                     "symbol_group": 1, "key_group": 2, "multiline": True, "expect_at_least": min(n, max(5, n // 2))}
                if syms:
                    d["_bare"] = syms
                if lang == "go":
                    pkg = re.search(r"^package\s+(\w+)", show(repo, rev, path) or "", re.M)
                    d["_package"] = pkg.group(1) if pkg else Path(path).parent.name
                else:
                    d["_package"] = None
                decls.append(d)
    return decls


def flag_constructor_packages(repo, rev, decls) -> list[str]:
    """."""
    syms = set()
    for d in decls:
        if not d.get("file", "").endswith(".go") or d["id"].startswith("coderefs"):
            continue
        text = show(repo, rev, d["file"]) or ""
        syms |= {m.group(d["symbol_group"]) for m in re.finditer(d["pattern"], text, re.M)}
    if not syms:
        return []
    fed = defaultdict(set)
    for _, _, t in grep(repo, rev, r"\b[A-Za-z_]\w*\.New\w*\(\s*[A-Z]\w*\s*[,)]", ["*.go"] + NOT_CODE):
        for m in re.finditer(r"\b([A-Za-z_]\w*\.New\w*)\(\s*([A-Z]\w*)\s*[,)]", t):
            if m.group(2) in syms:
                fed[m.group(1)].add(m.group(2))
    # the package that owns a proven constructor (`flagfn`) builds every flag type
    # with its other `New*` constructors too, whether or not one is fed a constant
    return sorted({c.split(".")[0] for c, s in fed.items() if len(s) >= 3})


def flag_var_methods(repo, rev, var_pattern) -> list[str]:
    """The methods the code calls on vars bound through a flag constructor
    (`EvalContext`, `EvalContextNoisy`): only those calls evaluate the flag, so a
    flag-named struct field's own methods (`Campaigns.SignupCampaign.IsZero()`)
    aren't read as one."""
    names = {m.group(1) for _, _, t in grep(repo, rev, var_pattern, ["*.go"] + NOT_CODE)
             for m in [re.match(var_pattern, t)] if m}
    if not names:
        return []
    alt = "|".join(map(re.escape, sorted(names)))
    called = Counter(m.group(1) for _, _, t in grep(repo, rev, r"\b(?:" + alt + r")\.\w+\(", ["*.go"] + NOT_CODE)
                     for m in re.finditer(r"\b(?:" + alt + r")\.(\w+)\(", t))
    # `DefaultValue()` reads the declared default; only an evaluation gates
    return sorted(m for m in called if re.search(r"Eval|Variation", m, re.I))


def wrapper_files(repo, rev, families) -> list[str]:
    """Files whose SDK evaluation calls take a variable key: the repo's helper."""
    out = set()
    for fam in families:
        pat = KEYED.get(fam)
        if not pat:
            continue
        dynamic = pat + r"\s*(?!['\"`])[A-Za-z_]"
        literal = pat + r"\s*['\"`]"
        paths = EXT[fam] + NOT_CODE
        dyn = Counter(p for p, _, _ in grep(repo, rev, dynamic, paths))
        lit = Counter(p for p, _, _ in grep(repo, rev, literal, paths))
        for path, n in dyn.items():
            if lit.get(path, 0) == 0:
                out.add(path)
    return sorted(out)


def path_roles(repo, rev, all_files) -> dict:
    roles = {k: list(v) for k, v in PATH_ROLES.items()}
    attrs = show(repo, rev, ".gitattributes") or ""
    for line in attrs.splitlines():
        bits = line.split()
        if len(bits) < 2 or bits[0].startswith("#"):
            continue
        pat = bits[0] if "/" in bits[0] or bits[0].startswith("*") else f"**/{bits[0]}"
        pat = pat.lstrip("/")
        if any(b in ("linguist-generated", "linguist-generated=true") for b in bits[1:]):
            roles["generated"].append(pat)
        if any(b in ("linguist-documentation", "linguist-documentation=true") for b in bits[1:]):
            roles["docs"].append(pat)
    return roles


def generated_files(repo, rev) -> list[str]:
    """Files carrying the standard generated-code header (Go's `Code generated
    ... DO NOT EDIT.`, `@generated`)."""
    hits = git(repo, "grep", "-l", "-I", "-E", r"^// Code generated .* DO NOT EDIT\.|@generated\b", rev, "--",
               "*.go", "*.ts", "*.tsx", "*.js", ":!**/node_modules/**", ":!**/vendor/**").splitlines()
    return sorted(h.split(":", 1)[1] for h in hits if ":" in h)


def codeowners(all_files) -> str | None:
    for c in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"):
        if c in all_files:
            return c
    return None


def import_specifiers(repo, rev, all_files, decl_file) -> list[str]:
    """How the code imports a TypeScript declaration file: its package's name
    (the nearest package.json above it) and the subpaths actually imported."""
    d = Path(decl_file).parent
    name = None
    while True:
        pj = (d / "package.json").as_posix()
        if pj in all_files:
            try:
                name = json.loads(show(repo, rev, pj) or "{}").get("name")
            except ValueError:
                name = None
            break
        if d == d.parent or str(d) in ("", "."):
            break
        d = d.parent
    if not name:
        return []
    seen = Counter(m.group(1) for _, _, t in grep(repo, rev, r"from\s+['\"]" + re.escape(name) + r"(?:/[^'\"]*)?['\"]",
                                                  ["*.ts", "*.tsx", "*.js", "*.jsx"] + NOT_CODE)
                   for m in re.finditer(r"from\s+['\"](" + re.escape(name) + r"(?:/[^'\"]*)?)['\"]", t))
    return sorted(seen) or [name]


def derive(repo, rev="HEAD") -> dict:
    repo = Path(repo)
    all_files = files_at(repo, rev)
    families = sdk_families(repo, rev, all_files)
    cr = coderefs(repo, rev)
    decls = alias_declarations(cr) + constant_files(repo, rev, families)
    langs = sorted({"go" if f.endswith(".go") else "typescript" if f.endswith((".ts", ".tsx")) else
                    "python" if f.endswith(".py") else "" for f in all_files} - {""})

    keyed = [{"pattern": KEYED[f], "key_arg": 0} for f in families if f in KEYED]
    if set(families) & {"js"}:
        keyed.append({"pattern": REACT_HOOKS, "key_arg": 0})
    seen = set()
    keyed = [k for k in keyed if not (k["pattern"] in seen or seen.add(k["pattern"]))]

    for d in decls:
        if d.get("file", "").endswith((".ts", ".tsx", ".js", ".jsx")):
            specs = import_specifiers(repo, rev, all_files, d["file"])
            if specs:
                d["import_specifiers"] = specs
    resolved, symbol_call = [], False
    for d in decls:
        pkg = d.pop("_package", None)
        bare = d.pop("_bare", None)
        if d["id"].startswith("coderefs"):
            if re.search(r"=\s*\w+\\?\(|Function", d["pattern"]):
                symbol_call = True
            elif d.get("file", "").endswith(".go"):
                # struct fields read as accessor calls: `.Flags.X()`, `f.X()`
                resolved.append(r"\.([A-Z][A-Za-z0-9_]*)\(\)")
        elif pkg:
            resolved.append(r"\b" + re.escape(pkg) + r"\.([A-Za-z0-9_]+)\b")
            if bare:
                # A small flags file's own package names its constants bare
                # (`p.flagOn(FlagX, ctx)`): match exactly those names.
                resolved.append(r"(?<![\w.])(" + "|".join(map(re.escape, bare)) + r")\b")
        else:
            resolved.append(r"\b\w*[Ff]lags?\.([A-Za-z0-9_$]+)\b")
    ctor_pkgs = flag_constructor_packages(repo, rev, decls)
    if ctor_pkgs:
        var_pat = (r"^\s*(?:var\s+)?([A-Za-z_]\w*)\s*(?:[\w.*\[\]]+\s*)?=\s*(?:"
                   + "|".join(map(re.escape, ctor_pkgs)) + r')\.New\w*\(\s*"(' + KEY + r')"')
        decls.append({"id": "go-flag-vars", "files": ["*.go"] + NOT_CODE,
                      "pattern": var_pat + r"(?:\s*,\s*(true|false)\b)?",
                      "symbol_group": 1, "key_group": 2, "default_group": 3})
        methods = flag_var_methods(repo, rev, var_pat)
        if methods:
            # an evaluating call on the var, bare or through its package (`pkg.X.Eval(...)`)
            resolved.append(r"(?:\b\w+\.)?\b([A-Za-z_]\w*)\.(?:" + "|".join(map(re.escape, methods)) + r")\(")
    resolved = list(dict.fromkeys(resolved))

    exclude = sorted(set(wrapper_files(repo, rev, families)) |
                     {d["file"] for d in decls if d.get("file")})

    ld = {}
    if cr.get("projKey"):
        ld["project"] = cr["projKey"]
    if cr.get("baseUri"):
        ld["base_url"] = cr["baseUri"].rstrip("/")

    prof = {
        "name": (origin_slug(repo) or repo.name).split("/")[-1],
        "repo": origin_slug(repo) or "",
        "derived_from": rev,
        "language": langs,
        "sdks": families,
        "flag_declarations": decls,
        "evaluation": {
            "symbol_call": symbol_call,
            "keyed_calls": keyed,
            "resolved_patterns": resolved,
            "search_exclude": ["**/*.md", "docs/**", "**/__tests__/**", "**/__mocks__/**", "**/*_test.go",
                               "**/node_modules/**", "**/vendor/**"],
            "exclude_files": exclude,
        },
        "roles_that_ship": ["ships", "generated"],
        "path_roles": path_roles(repo, rev, all_files),
    }
    prof["path_roles"]["generated"] += [f for f in generated_files(repo, rev)
                                        if f not in prof["path_roles"]["generated"]]
    co = codeowners(all_files)
    if co:
        prof["codeowners"] = co
    if ld:
        prof["launchdarkly"] = ld
    return prof


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("repo")
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("-o", "--out")
    a = ap.parse_args(argv)
    prof = derive(a.repo, a.rev)
    text = json.dumps(prof, indent=1) + "\n"
    if a.out:
        Path(a.out).write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
