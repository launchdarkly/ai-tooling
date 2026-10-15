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

    def test_requires_all_three_non_secret_handoff_keys(self):
        for value in (
            "LAUNCHDARKLY_AI_CONFIG_KEY=<config-key>",
            "LAUNCHDARKLY_PROJECT_KEY=<project-key>",
            "LAUNCHDARKLY_ENVIRONMENT_KEY=<environment-key>",
        ):
            self.assertIn(value, self.content)
        self.assertIn("Do not proceed until all three are present", self.content)
        self.assertIn("sdkKeySupplied: false", self.content)

    def test_requires_oauth_and_existing_v1_tools(self):
        self.assertIn(
            "OAuth is required for the v1 onboarding path",
            self.content,
        )
        self.assertIn(
            "Call `get-ai-config` with `LAUNCHDARKLY_PROJECT_KEY`",
            self.content,
        )
        self.assertIn(
            "Call `get-environments` with `LAUNCHDARKLY_PROJECT_KEY`",
            self.content,
        )
        self.assertIn(
            "key exactly equals `LAUNCHDARKLY_ENVIRONMENT_KEY`",
            self.content,
        )
        self.assertIn(
            "choose the first, `production`, or any other environment by convention",
            self.content,
        )
        self.assertNotIn("token authentication", self.content)

    def test_protects_credentials_and_uses_one_explicit_approval(self):
        self.assertIn(
            "write the credential to that location",
            self.content,
        )
        self.assertIn(
            "This may be one approval prompt",
            self.content,
        )
        self.assertIn("Do not separately re-ask", self.content)
        self.assertIn(
            "do not add a standalone branch confirmation",
            self.content,
        )
        self.assertIn(
            "Do not write a secret before explicit approval that names its destination",
            self.content,
        )
        self.assertIn(
            "Never reset, discard, overwrite, or stash unrelated changes",
            self.content,
        )
        self.assertIn(
            "Redact SDK credentials, provider keys, tokens",
            self.content,
        )
        self.assertIn(
            "Never place raw error output in chat",
            self.content,
        )
        self.assertIn("Do not commit during onboarding", self.content)

    def test_uses_ai_config_variations_as_the_complete_v1_instruction_path(self):
        self.assertIn(
            "already returned by `get-ai-config`",
            self.content,
        )
        self.assertIn(
            "Select the variation named `<language>-<sdkGeneration>`",
            self.content,
        )
        self.assertNotIn("LAUNCHDARKLY_SETUP_CONFIG_KEY", self.content)

    def test_future_setup_and_reporting_tools_are_optional(self):
        self.assertIn(
            "Its absence or failure is not a blocker",
            self.content,
        )
        self.assertIn(
            "`report-setup-outcome` is a future optional capability",
            self.content,
        )
        self.assertIn(
            "absence or failure a blocker",
            self.content,
        )


if __name__ == "__main__":
    unittest.main()
