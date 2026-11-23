import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_directory_policy as cdp  # noqa: E402


PNG_HEAD = b"\x89PNG\r\n\x1a\n"
PNG_END = b"\x00\x00\x00\x00IEND\xaeB`\x82"
GH_TOKEN = "ghp_" + "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3z5A"


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
        self.assertEqual(self.findings("BLOCKS"), [])  # pinned: HELD only
        self.mcp("npx", ["-y", "some-pkg@1.2.3-beta.1"])
        self.assertEqual(self.findings("BLOCKS"), [])  # pinned: HELD only

    def test_uvx_unpinned_blocks_pinned_passes(self):
        self.mcp("uvx", ["some-pkg"])
        self.assertEqual(len(self.findings("BLOCKS")), 1)
        self.mcp("uvx", ["some-pkg>=1.0"])
        self.assertEqual(len(self.findings("BLOCKS")), 1)
        self.mcp("uvx", ["some-pkg==1.2.3"])
        self.assertEqual(self.findings("BLOCKS"), [])  # pinned: HELD only

    def test_uvx_from_flag_checks_the_package(self):
        self.mcp("uvx", ["--from", "some-pkg", "tool"])
        self.assertEqual(len(self.findings("BLOCKS")), 1)
        self.mcp("uvx", ["--from", "some-pkg==1.0.0", "tool"])
        self.assertEqual(self.findings("BLOCKS"), [])  # pinned: HELD only

    def test_uv_run_needs_locked(self):
        self.mcp("uv", ["run", "server.py"])
        self.assertEqual(len(self.findings("BLOCKS")), 1)
        self.mcp("uv", ["run", "--locked", "server.py"])
        self.assertEqual(self.findings("BLOCKS"), [])  # pinned: HELD only

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

    def test_package_flag_with_equals(self):
        self.mcp("npx", ["-y", "--package=some-pkg@latest", "tool"])
        blocks = self.findings("BLOCKS")
        self.assertEqual(len(blocks), 1)
        self.assertIn("some-pkg@latest", blocks[0])

    def test_uvx_with_does_not_hide_the_main_package(self):
        self.mcp("uvx", ["--with", "dep==1.0.0", "some-pkg"])
        blocks = self.findings("BLOCKS")
        self.assertEqual(len(blocks), 1)
        self.assertIn("some-pkg", blocks[0])

    def test_uv_tool_run_is_a_launcher(self):
        self.mcp("uv", ["tool", "run", "some-pkg"])
        self.assertEqual(len(self.findings("BLOCKS")), 1)

    def test_pinned_launcher_is_held(self):
        self.mcp("npx", ["-y", "some-pkg@1.2.3"])
        held = self.findings("HELD")
        self.assertEqual(len(held), 1)
        self.assertIn("Runs a pinned npx or uvx package", held[0])

    def test_manifest_named_mcp_file_is_scanned(self):
        self.write(".claude-plugin/plugin.json", json.dumps({"name": "x", "mcpServers": "./config/servers.json"}))
        self.write("config/servers.json", json.dumps({"s": {"command": "npx", "args": ["pkg@latest"]}}))
        self.assertEqual(len(self.findings("BLOCKS")), 1)

    def test_npmrc_registry_beside_launcher_blocks(self):
        self.mcp("npx", ["-y", "some-pkg@1.2.3"])
        self.write(".npmrc", "registry=https://registry.example.test/\n")
        blocks = self.findings("BLOCKS")
        self.assertEqual(len(blocks), 1)
        self.assertIn(".npmrc", blocks[0])

    def test_npmrc_beside_package_install_held(self):
        self.write("package.json", "{}")
        self.write("uv.toml", 'index-url = "https://pypi.example.test/simple"\n')
        held = self.findings("HELD")
        self.assertEqual(len(held), 1)
        self.assertIn("uv.toml", held[0])

    def test_npmrc_without_launcher_or_install_passes(self):
        self.write(".npmrc", "registry=https://registry.example.test/\n")
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
        self.write("a.png", PNG_HEAD + b"\x00" * (300 * 1024) + PNG_END, binary=True)
        self.write("b.woff2", b"wOF2\x00\x00" + b"\x00" * 100, binary=True)
        self.write("c.svg", "<svg/>")
        body = b"WEBP" + b"\x00" * 8
        self.write("d.webp", b"RIFF" + len(body).to_bytes(4, "little") + body, binary=True)
        self.write("e.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 10 + b"\xff\xd9", binary=True)
        self.write("f.gif", b"GIF89a" + b"\x00" * 10 + b";", binary=True)
        self.assertEqual(self.findings(), [])

    def test_image_extension_on_other_bytes_held(self):
        self.write("x.png", b"\x7fELF\x02\x01\x01\x00", binary=True)
        self.write("y.woff2", b"PK\x03\x04\x00", binary=True)
        held = self.findings("HELD")
        self.assertEqual(len(held), 2, held)

    def test_truncated_image_held(self):
        self.write("t.png", PNG_HEAD + b"\x00\x00\x00\rIHDR", binary=True)
        self.write("t.gif", b"GIF89a\x00\x00", binary=True)
        self.assertEqual(len(self.findings("HELD")), 2)

    def test_file_over_5_mib_blocks_even_for_images(self):
        self.write("big.png", PNG_HEAD + b"\x00" * (5 * 1024 * 1024) + PNG_END, binary=True)
        blocks = self.findings("BLOCKS")
        self.assertEqual(len(blocks), 1)
        self.assertIn("5 MiB", blocks[0])

    def test_entry_limit_blocks(self):
        old = cdp.MAX_ENTRIES
        cdp.MAX_ENTRIES = 20
        self.addCleanup(setattr, cdp, "MAX_ENTRIES", old)
        for i in range(15):
            self.write(f"d{i}/f.txt", "x")
        self.assertEqual(len(self.findings("BLOCKS")), 1)  # 15 files + 15 folders

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


class CommandTests(PolicyTestCase):
    def mcp(self, cfg):
        self.write(".mcp.json", json.dumps({"mcpServers": {"s": cfg}}))

    def hook(self, hook):
        self.write("hooks/hooks.json", json.dumps({"hooks": {"Stop": [{"hooks": [hook]}]}}))

    def assertBlocks(self, text):
        blocks = self.findings("BLOCKS")
        self.assertEqual(len(blocks), 1, blocks)
        self.assertIn(text, blocks[0])

    def test_dotdot_in_command_blocks(self):
        self.hook({"type": "command", "command": '"${CLAUDE_PLUGIN_ROOT}/../x.sh"'})
        self.assertBlocks("Command reaches above the plugin folder")

    def test_other_variable_blocks(self):
        self.hook({"type": "command", "command": '"$CLAUDE_PROJECT_DIR/x.sh"'})
        self.assertBlocks("$CLAUDE_PROJECT_DIR")

    def test_command_substitution_wildcard_and_inline_block(self):
        for args, text in ((["$(pwd)/s.js"], "command substitution"), (["${CLAUDE_PLUGIN_ROOT}/*.sh"], "wildcard")):
            self.mcp({"command": "node", "args": args})
            self.assertIn(text, " ".join(self.findings("BLOCKS")))
        self.mcp({"command": "python3", "args": ["-c", "print(1)"]})
        self.assertBlocks("inline program")

    def test_url_query_and_user_config_are_not_flagged(self):
        self.mcp({"command": "${CLAUDE_PLUGIN_ROOT}/run.sh", "args": ["--url", "https://x.test/?a=1",
                                                                    "${user_config.API_KEY}"]})
        self.assertEqual(self.findings(), [])

    def test_shell_or_npm_run_mcp_held(self):
        self.mcp({"command": "npm", "args": ["run", "start"]})
        held = self.findings("HELD")
        self.assertEqual(len(held), 1)
        self.assertIn("MCP server command wasn't read", held[0])

    def test_non_shell_plugin_file_held(self):
        self.mcp({"command": "node", "args": ["${CLAUDE_PLUGIN_ROOT}/server.js"]})
        held = self.findings("HELD")
        self.assertEqual(len(held), 1)
        self.assertIn("Scripts the validator couldn't follow", held[0])

    def test_mcpb_bundle_url_blocks(self):
        self.mcp({"type": "http", "url": "https://x.test/server.mcpb"})
        self.assertBlocks("Bundled MCP server")

    def test_env_credential_in_mcp_headers_held(self):
        self.mcp({"type": "http", "url": "https://x.test/mcp", "headers": {"Authorization": "Bearer ${GITHUB_TOKEN}"}})
        held = self.findings("HELD")
        self.assertEqual(len(held), 1)
        self.assertIn("$GITHUB_TOKEN", held[0])
        self.mcp({"type": "http", "url": "https://x.test/mcp",
                  "headers": {"Authorization": "Bearer ${user_config.TOKEN}"}})
        self.assertEqual(self.findings(), [])

    def test_http_hook_must_be_https(self):
        self.hook({"type": "http", "url": "http://x.test/hook"})
        self.assertBlocks("not https://")
        self.hook({"type": "http", "url": "https://x.test/hook", "headers": {"Authorization": "$GITHUB_TOKEN"}})
        self.assertBlocks("credential from the user's environment")


class LayoutTests(PolicyTestCase):
    def test_windows_invalid_names_block(self):
        self.write("docs/a:b.md", "x")  # on disk too, so the walk path is exercised
        self.assertEqual(len(self.findings("BLOCKS")), 1)
        for name in ("notes.", "trailing ", "con.md", "LPT1.txt", "aux"):
            with self.subTest(name=name):
                self.assertEqual(len(cdp.check_names([f"docs/{name}"])), 1)
        self.assertEqual(cdp.check_names(["docs/console.md", "docs/a.b.md"]), [])

    def test_case_collision_blocks(self):
        found = cdp.check_names(["docs/README.md", "docs/Readme.md", "Docs/x.md"])
        self.assertEqual(len(found), 2, found)

    def test_component_spelling_blocks(self):
        found = cdp.check_names(["skills/x/skill.md", "Hooks/hooks.json"])
        self.assertEqual(len(found), 2, found)

    def test_gitattributes(self):
        self.write(".gitattributes", "# comment with filter=lfs\n*.png -text\n")
        self.assertEqual(self.findings(), [])
        self.write(".gitattributes", "tests/ export-ignore\n*.bin filter=lfs diff=lfs\n")
        self.assertEqual(len(self.findings("BLOCKS")), 2)

    def test_lfs_pointer_blocks_where_loaded_warns_elsewhere(self):
        ptr = "version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 10\n"
        self.write("skills/x/data.md", ptr)
        self.write("docs/data.bin", ptr)
        found = cdp.run(self.root)
        self.assertEqual(sorted(lvl for lvl, _ in found), ["BLOCKS", "WARN"], found)

    def test_symlink_blocks_where_loaded(self):
        self.write("README.md", "x")
        os.makedirs(os.path.join(self.root, "skills"))
        os.symlink("../README.md", os.path.join(self.root, "skills", "link.md"))
        self.assertEqual(len(self.findings("BLOCKS")), 1)

    def test_literal_secrets_block_placeholders_pass(self):
        self.write("docs/a.md", f"token: {GH_TOKEN}\n")
        self.write("docs/b.md", "export LD_API_KEY=api" + "-0a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d\n")
        self.write("docs/c.md", "ANTHROPIC_API_KEY=sk-ant-...\nmob-00000000-0000-0000-0000-000000000001\n"
                                "AKIAIOSFODNN7EXAMPLE\n")
        blocks = self.findings("BLOCKS")
        self.assertEqual(len(blocks), 2, blocks)
        self.assertNotIn(GH_TOKEN, " ".join(blocks))  # never echo the secret

    def test_identity_look_alikes_block(self):
        manifest = {"name": "x", "displayName": "L\u0430unchDarkly", "author": {"name": "Launch\u200bDarkly"}}
        self.write(".claude-plugin/plugin.json", json.dumps(manifest))
        self.assertEqual(len(self.findings("BLOCKS")), 2)
        manifest = {"name": "x", "displayName": "Caf\u00e9 Flags", "author": {"name": "LaunchDarkly"}}
        self.write(".claude-plugin/plugin.json", json.dumps(manifest))
        self.assertEqual(self.findings(), [])


class GitTests(unittest.TestCase):
    """The CI path: files come from `git ls-files`, not the disk."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.root)
        self.git("init", "-q")

    def git(self, *args, cwd=None):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd or self.root,
                       check=True, capture_output=True)

    def write(self, rel, data):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)

    def test_untracked_files_ignored_and_deleted_tracked_file_does_not_crash(self):
        self.write("tracked.md", b"x")
        self.write("gone.md", b"x")
        self.git("add", "-A")
        os.remove(os.path.join(self.root, "gone.md"))
        self.write("untracked.pyz", b"PK\x03\x04\x00")
        self.assertEqual(cdp.run(self.root), [])

    def test_submodule_in_skills_blocks(self):
        self.git("update-index", "--add", "--cacheinfo",
                 "160000,4b825dc642cb6eb9a060e54bf8d69288fbee4904,skills/vendored")
        found = cdp.run(self.root)
        self.assertEqual([lvl for lvl, _ in found], ["BLOCKS"], found)
        self.assertIn("submodule", found[0][1])

    def test_spaces_and_non_utf8_names(self):
        self.write("dir with space/big file.md", b"a" * (300 * 1024))
        try:
            self.write(os.fsdecode(b"caf\xe9.md"), b"x")
        except OSError:  # APFS rejects non-UTF-8 names; Linux CI does not
            pass
        self.git("add", "-A")
        found = cdp.run(self.root)
        self.assertEqual([lvl for lvl, _ in found], ["HELD"], found)

    def test_linked_worktree_uses_git_index(self):
        self.write("a.md", b"x")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")
        wt = os.path.join(self._tmp.name, "wt")
        self.git("worktree", "add", "-q", wt)
        with open(os.path.join(wt, "untracked.pyz"), "wb") as fh:
            fh.write(b"PK\x03\x04\x00")
        self.assertEqual(cdp.run(wt), [])


class RepoTests(unittest.TestCase):
    def test_current_repo_has_no_blocks(self):
        blocks = [m for lvl, m in cdp.run(str(ROOT)) if lvl == "BLOCKS"]
        self.assertEqual(blocks, [])


if __name__ == "__main__":
    unittest.main()
