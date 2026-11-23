import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_directory_policy as cdp  # noqa: E402


class PolicyTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def write(self, rel, content, binary=False):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8"})) as fh:
            fh.write(content)

    def findings(self, level=None):
        found = cdp.run(self.root)
        return [m for lvl, m in found if level is None or lvl == level]


class LauncherTests(PolicyTestCase):
    def mcp(self, command, args):
        self.write(".mcp.json", json.dumps({"mcpServers": {"s": {"command": command, "args": args}}}))

    def test_npx_latest_blocks(self):
        self.mcp("npx", ["-y", "some-pkg@latest"])
        self.assertEqual(len(self.findings("BLOCKS")), 1)

    def test_npx_unversioned_and_range_block(self):
        self.mcp("npx", ["some-pkg"])
        self.assertEqual(len(self.findings("BLOCKS")), 1)
        self.mcp("npx", ["-y", "@scope/pkg@^1.2.0"])
        self.assertEqual(len(self.findings("BLOCKS")), 1)

    def test_npx_pinned_passes(self):
        self.mcp("npx", ["-y", "@scope/pkg@1.2.3"])
        self.assertEqual(self.findings(), [])
        self.mcp("npx", ["-y", "some-pkg@1.2.3-beta.1"])
        self.assertEqual(self.findings(), [])

    def test_uvx_unpinned_blocks_pinned_passes(self):
        self.mcp("uvx", ["some-pkg"])
        self.assertEqual(len(self.findings("BLOCKS")), 1)
        self.mcp("uvx", ["some-pkg>=1.0"])
        self.assertEqual(len(self.findings("BLOCKS")), 1)
        self.mcp("uvx", ["some-pkg==1.2.3"])
        self.assertEqual(self.findings(), [])

    def test_uvx_from_flag_checks_the_package(self):
        self.mcp("uvx", ["--from", "some-pkg", "tool"])
        self.assertEqual(len(self.findings("BLOCKS")), 1)
        self.mcp("uvx", ["--from", "some-pkg==1.0.0", "tool"])
        self.assertEqual(self.findings(), [])

    def test_uv_run_needs_locked(self):
        self.mcp("uv", ["run", "server.py"])
        self.assertEqual(len(self.findings("BLOCKS")), 1)
        self.mcp("uv", ["run", "--locked", "server.py"])
        self.assertEqual(self.findings(), [])

    def test_hooks_json_command_string_is_scanned(self):
        hooks = {"hooks": {"PostToolUse": [{"hooks": [{"type": "command", "command": "npx tool@latest --x"}]}]}}
        self.write("hooks/hooks.json", json.dumps(hooks))
        self.assertEqual(len(self.findings("BLOCKS")), 1)

    def test_plugin_json_mcp_servers_scanned(self):
        manifest = {"name": "x", "mcpServers": {"s": {"command": "npx", "args": ["pkg@latest"]}}}
        self.write(".claude-plugin/plugin.json", json.dumps(manifest))
        self.assertEqual(len(self.findings("BLOCKS")), 1)

    def test_remote_and_plugin_root_commands_pass(self):
        self.write(".mcp.json", json.dumps({"mcpServers": {"r": {"type": "http", "url": "https://x.test/mcp"}}}))
        self.write("hooks/hooks.json", json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/run.sh"}]}]}}))
        self.assertEqual(self.findings(), [])

    def test_blocks_exit_code(self):
        self.mcp("npx", ["pkg@latest"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cdp.main(["x", self.root]), 1)


class FileTests(PolicyTestCase):
    def test_zip_binary_held(self):
        self.write("tool.pyz", b"PK\x03\x04\x00\x00data", binary=True)
        held = self.findings("HELD")
        self.assertEqual(len(held), 1)
        self.assertIn("tool.pyz", held[0])

    def test_images_and_fonts_pass_even_when_large(self):
        self.write("a.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * (300 * 1024), binary=True)
        self.write("b.woff2", b"wOF2\x00\x00" + b"\x00" * 100, binary=True)
        self.write("c.svg", "<svg/>")
        self.write("d.webp", b"RIFF\x00\x00\x00\x00WEBP\x00\x00", binary=True)
        self.assertEqual(self.findings(), [])

    def test_large_text_file_held_small_passes(self):
        self.write("big.json", "a" * (257 * 1024))
        self.write("small.json", "a" * 1024)
        held = self.findings("HELD")
        self.assertEqual(len(held), 1)
        self.assertIn("big.json", held[0])

    def test_file_count_limit(self):
        for i in range(cdp.MAX_FILES):
            self.write(f"f/{i}.txt", "x")
        self.assertEqual(self.findings(), [])
        self.write("f/extra.txt", "x")
        held = self.findings("HELD")
        self.assertEqual(len(held), 1)
        self.assertIn("513 files", held[0])

    def test_lockfile_beside_package_json_held(self):
        self.write("package.json", "{}")
        self.assertEqual(self.findings(), [])
        self.write("package-lock.json", "{}")
        held = self.findings("HELD")
        self.assertEqual(len(held), 1)
        self.assertIn("package-lock.json", held[0])

    def test_lockfile_without_package_json_passes(self):
        self.write("package-lock.json", "{}")
        self.assertEqual(self.findings(), [])

    def test_held_only_exits_zero(self):
        self.write("tool.pyz", b"PK\x03\x04\x00\x00", binary=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cdp.main(["x", self.root]), 0)


class CredentialTests(PolicyTestCase):
    def skill(self, body, rel="skills/x/SKILL.md"):
        self.write(rel, "---\nname: x\ndescription: d\n---\n" + body)

    def test_pr181_era_phrasing_is_caught(self):
        self.skill("Find the API token in the `LD_API_KEY` environment variable or in `~/.claude/config.json`.\n")
        held = self.findings("HELD")
        self.assertEqual(len(held), 1)
        self.assertIn("SKILL.md:5", held[0])

    def test_env_var_instruction_alone_is_caught(self):
        self.skill("Read the access token from the LD_ACCESS_TOKEN environment variable.\n")
        self.assertEqual(len(self.findings("HELD")), 1)

    def test_config_json_alone_is_caught(self):
        self.skill("Look in ~/.claude/config.json for the key.\n")
        self.assertEqual(len(self.findings("HELD")), 1)

    def test_negated_guidance_passes(self):
        self.skill("Do not search environment variables, `.env` files, or `~/.claude/config.json` for an API token.\n")
        self.assertEqual(self.findings(), [])

    def test_ask_the_user_passes(self):
        self.skill("Ask the user for an API token; never read the LD_ACCESS_TOKEN environment variable.\n")
        self.assertEqual(self.findings(), [])

    def test_code_fence_passes(self):
        self.skill("```python\ntoken = os.environ['LD_API_KEY']  # read the api token from the environment\n```\n")
        self.assertEqual(self.findings(), [])

    def test_references_dir_not_scanned(self):
        self.write("skills/x/references/guide.md", "Read the API token from the LD_API_KEY environment variable.\n")
        self.write("skills/x/references/SKILL.md", "Read the API token from the LD_API_KEY environment variable.\n")
        self.assertEqual(self.findings(), [])

    def test_sdk_key_env_setup_and_mcp_tool_names_pass(self):
        self.skill("Use `get-sdk-key` to retrieve the server-side SDK key.\n"
                   "Set `LAUNCHDARKLY_SDK_KEY` as an environment variable; the SDK reads it at startup.\n")
        self.assertEqual(self.findings(), [])


class RepoTests(unittest.TestCase):
    def test_current_repo_has_no_blocks(self):
        blocks = [m for lvl, m in cdp.run(str(ROOT)) if lvl == "BLOCKS"]
        self.assertEqual(blocks, [])


if __name__ == "__main__":
    unittest.main()
