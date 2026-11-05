import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_claude_plugin", ROOT / "scripts" / "build_claude_plugin.py")
build_claude_plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_claude_plugin)

# Directory limits from https://claude.com/docs/plugins/pre-submission-checklist.md
MAX_FILE_BYTES = 256 * 1024
MAX_FILES = 512
IMAGE_OR_FONT = re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|otf)$", re.IGNORECASE)


class BuildClaudePluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name) / "plugin"
        build_claude_plugin.build(cls.out)
        cls.files = [p for p in cls.out.rglob("*") if p.is_file()]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_dev_tooling_is_left_out(self):
        for name in ("evals", "tests", "scripts", "template", ".github"):
            with self.subTest(name=name):
                self.assertFalse((self.out / name).exists(), f"{name}/ must not ship in the plugin")
        lockfiles = [p.name for p in self.files if p.name in {"package-lock.json", "package.json"}]
        self.assertEqual(lockfiles, [], "package files must not ship in the plugin")

    def test_every_listed_skill_ships(self):
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        for skill in manifest["skills"]:
            with self.subTest(skill=skill):
                self.assertTrue((self.out / skill / "SKILL.md").is_file())
        for rel in (".claude-plugin/plugin.json", ".mcp.json", "README.md", "LICENSE", manifest["icon"]):
            with self.subTest(file=rel):
                self.assertTrue((self.out / rel).is_file())

    def test_bundle_fits_directory_file_limits(self):
        self.assertLessEqual(len(self.files), MAX_FILES)
        too_big = [
            str(p.relative_to(self.out))
            for p in self.files
            if not IMAGE_OR_FONT.search(p.name) and p.stat().st_size > MAX_FILE_BYTES
        ]
        self.assertEqual(too_big, [], "non-image files over 256 KiB are held for review")

    def test_relative_links_that_work_in_the_repo_work_in_the_bundle(self):
        broken = []
        for md in self.out.rglob("*.md"):
            for target in build_claude_plugin.LINK.findall(md.read_text(encoding="utf-8")):
                if re.match(r"[a-z][a-z0-9+.-]*:", target) or target.startswith("/"):
                    continue
                rel_dir = md.parent.relative_to(self.out)
                in_repo = (ROOT / rel_dir / target).resolve()
                if in_repo.exists() and not (md.parent / target).resolve().exists():
                    broken.append(f"{md.relative_to(self.out)} -> {target}")
        self.assertEqual(broken, [])


if __name__ == "__main__":
    unittest.main()
