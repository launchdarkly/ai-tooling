import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/agentcontrol/legacy-sdk-migrate/SKILL.md"
API_MAPPING = (
    ROOT
    / "skills/agentcontrol/legacy-sdk-migrate/references/api-mapping.md"
)


class LegacySdkMigrateTests(unittest.TestCase):
    def test_go_routing_and_release_sources(self):
        skill = SKILL.read_text(encoding="utf-8")
        mapping = API_MAPPING.with_name("go-api-mapping.md").read_text(encoding="utf-8")

        self.assertIn("references/go-api-mapping.md", skill)
        self.assertIn("go-server-sdk-ai/ldai", skill)
        self.assertIn("go-server-sdk/ldai", skill)
        self.assertIn("Go 1.26+", skill)
        self.assertIn("go-ai-sdk/tree/v1.0.0", mapping)
        self.assertIn("go-server-sdk-ai/tree/v0.11.0", mapping)
        self.assertIn("openaimessages.OpenAIMessages", mapping)
        self.assertIn("aiserver.WithHistory", mapping)
        self.assertIn("no global registry", mapping)

    def test_go_empty_and_error_paths_are_preserved(self):
        mapping = API_MAPPING.with_name("go-api-mapping.md").read_text(encoding="utf-8")

        self.assertIn("errors.Is(err, aiserver.ErrConfigDisabled)", mapping)
        self.assertIn("errors.Is(err, aiserver.ErrConfigNotFound)", mapping)
        self.assertIn("initialization/evaluation/parse failures return errors", mapping)
        self.assertIn('res != nil && task.EvaluationMetricKey != ""', mapping)
        self.assertIn("res.TrackData, res.Score", mapping)
        self.assertIn("Stream events have no `TrackData`", mapping)
        self.assertIn("empty input/history/tools", mapping)
        self.assertNotIn("go runJudgeWorker(ctx", mapping)

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
