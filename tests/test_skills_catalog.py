import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_JSON = ROOT / "skills.json"


class SkillsCatalogTests(unittest.TestCase):
    def test_launchdarkly_flag_command_skill_is_listed(self):
        data = json.loads(SKILLS_JSON.read_text(encoding="utf-8"))
        skills = data.get("skills", [])

        entry = next((s for s in skills if s.get("name") == "launchdarkly-flag-command"), None)
        self.assertIsNotNone(entry, "launchdarkly-flag-command must be present in skills.json")

        self.assertEqual(
            entry.get("path"),
            "skills/feature-flags/launchdarkly-flag-command",
            "catalog path for launchdarkly-flag-command is incorrect",
        )

        skill_dir = ROOT / entry["path"]
        self.assertTrue((skill_dir / "SKILL.md").is_file(), "SKILL.md is missing for launchdarkly-flag-command")
        self.assertTrue(
            (skill_dir / "marketplace.json").is_file(),
            "marketplace.json is missing for launchdarkly-flag-command",
        )


if __name__ == "__main__":
    unittest.main()
