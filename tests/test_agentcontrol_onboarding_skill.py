import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = (
    ROOT
    / "skills"
    / "agentcontrol"
    / "agentcontrol-onboarding"
    / "SKILL.md"
)


class AgentControlOnboardingSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = SKILL.read_text(encoding="utf-8")

    def test_accepts_only_the_ai_config_key_from_the_handoff(self):
        self.assertIn(
            "LAUNCHDARKLY_AI_CONFIG_KEY=<config-key>",
            self.content,
        )
        self.assertIn(
            "Do not ask for a project key, environment key, SDK credential",
            self.content,
        )
        self.assertIn("sdkKeySupplied: false", self.content)

    def test_requires_authenticated_context_without_guessing(self):
        self.assertIn(
            "resolve the project from the AI Config key",
            self.content,
        )
        self.assertIn(
            "choose the first, `production`, or any other environment by convention",
            self.content,
        )
        self.assertIn(
            "Do not invent a LaunchDarkly capability",
            self.content,
        )

    def test_protects_credentials_and_existing_work(self):
        self.assertIn(
            "Ask separately before writing the retrieved SDK credential",
            self.content,
        )
        self.assertIn(
            "Detect only the presence of `LD_API_KEY`",
            self.content,
        )
        self.assertIn(
            "Never reset, discard, overwrite, or stash unrelated changes",
            self.content,
        )
        self.assertIn("Do not commit during onboarding", self.content)

    def test_uses_the_supplied_key_for_fallback_instructions(self):
        self.assertIn(
            "the supplied `LAUNCHDARKLY_AI_CONFIG_KEY`",
            self.content,
        )
        self.assertNotIn("LAUNCHDARKLY_SETUP_CONFIG_KEY", self.content)


if __name__ == "__main__":
    unittest.main()
