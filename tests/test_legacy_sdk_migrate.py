import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/agentcontrol/legacy-sdk-migrate/SKILL.md"
API_MAPPING = (
    ROOT
    / "skills/agentcontrol/legacy-sdk-migrate/references/api-mapping.md"
)


class LegacySdkMigrateTests(unittest.TestCase):
    def test_background_judge_examples_track_returned_metrics(self):
        mapping = API_MAPPING.read_text(encoding="utf-8")

        self.assertIn("get_client().track", mapping)
        self.assertIn("getClient().track", mapping)
        self.assertNotIn("asyncio.create_task(judge_worker(task))", mapping)
        self.assertNotIn("void runJudge(task, handlers)", mapping)

    def test_skill_preserves_tracking_for_background_judges(self):
        skill = SKILL.read_text(encoding="utf-8")

        self.assertIn("Background judges are the exception", skill)
        self.assertIn("Do not fire and forget", skill)
        self.assertIn("returned score", skill)
        self.assertIn("launchdarkly-server-sdk", skill)
        self.assertNotIn("must be a tuple", skill)


if __name__ == "__main__":
    unittest.main()
