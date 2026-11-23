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
        self.assertIn("missing from the variation is silently unavailable", mapping)
        self.assertIn("loop limit or default model", mapping)

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

    def test_go_metric_and_outage_migration_limits(self):
        mapping = API_MAPPING.with_name("go-api-mapping.md").read_text(encoding="utf-8")

        self.assertIn("No v1.0.0 TTFT event", mapping)
        self.assertIn("deprecated alias for `TrackTokens`", mapping)
        self.assertIn("caller-supplied latency/TTFT and token overrides", mapping)
        self.assertIn("catch-all initialization-error policy", mapping)
        self.assertIn("does not wrap `ErrNotInitialized`", mapping)
        self.assertIn("if _, err := aiserver.InitClient", mapping)
        self.assertIn("Do not apply a catch-all to `Invoke` errors", mapping)
        self.assertIn("returns nothing and silently does nothing", mapping)

    def test_go_tools_graphs_and_optional_review_guidance(self):
        mapping = API_MAPPING.with_name("go-api-mapping.md").read_text(encoding="utf-8")

        self.assertIn("model.parameters.tools", mapping)
        self.assertIn("openaiagents.Options.MaxTurns", mapping)
        self.assertIn("`max_turns` model parameter, which takes precedence", mapping)
        self.assertIn("Provider names match exactly, including case", mapping)
        self.assertIn("NativeGraphOptions.Context", mapping)
        self.assertIn("`AdapterOptions` has no `Context` field", mapping)
        self.assertIn("`$ld:ai:graph:path` became `$ld:ai:graph:node`", mapping)
        self.assertIn("`$ld:ai:graph:redirect` is gone", mapping)
        self.assertIn("GOTOOLCHAIN=auto", mapping)
        self.assertIn("raise the `go` line", mapping)
        self.assertIn("fresh handler on every call", mapping)
        self.assertIn("`Track`, and `AgentGraph`", SKILL.read_text(encoding="utf-8"))

    def test_skill_preserves_tracking_for_background_judges(self):
        skill = SKILL.read_text(encoding="utf-8")

        self.assertIn("Background judges are the exception", skill)
        self.assertIn("Do not fire and forget", skill)
        self.assertIn("returned score", skill)
        self.assertIn("launchdarkly-server-sdk", skill)
        self.assertNotIn("must be a tuple", skill)

    def test_public_exports_and_missing_tool_handler_guidance(self):
        skill = SKILL.read_text(encoding="utf-8")
        migrate_skill = (ROOT / "skills/agentcontrol/migrate/SKILL.md").read_text(encoding="utf-8")
        graph_ref = (ROOT / "skills/agentcontrol/migrate/references/agent-graph-reference.md").read_text(encoding="utf-8")

        self.assertIn("init_client(client=fake_ld)", skill)
        self.assertIn("toLangGraph", graph_ref)
        self.assertNotIn('No handler registered for tool "x"', migrate_skill)


if __name__ == "__main__":
    unittest.main()
