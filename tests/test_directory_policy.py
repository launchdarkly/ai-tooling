import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_directory_policy", ROOT / "scripts" / "check_directory_policy.py")
policy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = policy
spec.loader.exec_module(policy)


# The examples below are masked so this file doesn't trip the rule itself,
# since the directory scans tests too. unmask() fills them in at run time.
MASKS = {
    "<npx>": "n" + "px",
    "<uvx>": "u" + "vx",
    "<pipe>": "|",
    "<at>": "@",
    "<interp>": "$" + "{BASE}",
    "<dlx>": "d" + "lx",
    "<run>": "r" + "un",
    "<curl>": "cu" + "rl",
    "<irm>": "i" + "rm",
    "<iex>": "i" + "ex",
    "<sh>": "s" + "h",
    "<pnpm>": "pn" + "pm",
    "<pipx>": "pi" + "px",
    "<go>": "g" + "o",
}


def unmask(text):
    for token, value in MASKS.items():
        text = text.replace(token, value)
    return text


def fetch_exec_hits(text):
    text = unmask(text)
    return [
        why
        for line in text.splitlines()
        for pattern, why in policy.FETCH_EXEC_PATTERNS
        if pattern.search(line)
    ]


class RepoMeetsDirectoryPolicy(unittest.TestCase):
    def test_no_violations(self):
        violations = policy.check()
        self.assertEqual([], [str(v) for v in violations])


class FetchExecRule(unittest.TestCase):
    """RUNTIME_FETCH_EXEC held plugin 1.0.12 on README.md and two eval tests."""

    def test_flags_package_launchers(self):
        for text in (
            "<npx> skills add launchdarkly/ai-tooling",
            "run `<npx> pod-install` on bare React Native",
            "<npx> -y @launchdarkly/mcp-server",
            "<uvx> some-tool",
            "<pnpm> <dlx> create-thing",
            "<pipx> <run> cowsay",
            "<go> <run> github.com/x/y<at>latest",
            '"command": "<npx>",',
        ):
            self.assertTrue(fetch_exec_hits(text), text)

    def test_flags_piping_a_download_into_a_shell(self):
        self.assertTrue(fetch_exec_hits("<curl> -fsSL https://example.com/install.sh <pipe> <sh>"))
        self.assertTrue(fetch_exec_hits("<irm> https://example.com/install.ps1 <pipe> <iex>"))

    def test_flags_curl_with_a_computed_url_on_one_line(self):
        self.assertTrue(fetch_exec_hits('`<curl> -sS -H "x" "<interp>"`'))

    def test_allows_prose_and_api_calls(self):
        for text in (
            "- **<npx> not available:** copy the skill directory",
            "Requires `<npx>` on PATH",
            "the old <npx>-based server",
            '<curl> -sS "https://app.launchdarkly.com/api/v2/projects"',
            "pip install launchdarkly-server-sdk",
        ):
            self.assertEqual([], fetch_exec_hits(text), text)


class ManifestRule(unittest.TestCase):
    """ICON_MISSING and PRIVACY_URL_MISSING (1.0.0), UNKNOWN_KEY (1.0.12)."""

    listing = {"icon": "logo.svg", "privacyPolicyUrl": "https://launchdarkly.com/policies/privacy/"}

    def rules(self, manifest, listing):
        return [v.rule for v in policy.check_manifest(manifest, listing, ROOT)]

    def test_listing_fields_present(self):
        self.assertEqual([], self.rules({"name": "x"}, self.listing))

    def test_logo_instead_of_icon(self):
        listing = {k: v for k, v in self.listing.items() if k != "icon"}
        self.assertEqual(["listing-fields", "known-keys"], self.rules({"name": "x", "logo": "logo.svg"}, listing))

    def test_missing_privacy_url(self):
        listing = {k: v for k, v in self.listing.items() if k != "privacyPolicyUrl"}
        self.assertEqual(["listing-fields"], self.rules({"name": "x"}, listing))

    def test_listing_fields_in_plugin_json_are_unknown_keys(self):
        self.assertEqual(["known-keys", "known-keys"], self.rules({"name": "x", "icon": "logo.svg", "privacyPolicyUrl": "https://x"}, self.listing))


class FileRules(unittest.TestCase):
    """BINARIES_NOT_INSPECTED / INVENTORY_GAPS (1.0.0), uninspectable files (1.0.12)."""

    manifest = {"skills": ["./skills/demo"]}

    def test_symlink(self):
        self.assertEqual(1, len(policy.check_symlinks([("120000", "skills/demo-link"), ("100644", "README.md")])))

    def test_shipped_archive_needs_a_reason(self):
        files = [("100644", "skills/demo/tool.pyz"), ("100644", "evals/fixture.zip")]
        self.assertEqual(["skills/demo/tool.pyz"], [v.path for v in policy.check_uninspectable(files, self.manifest)])


if __name__ == "__main__":
    unittest.main()
