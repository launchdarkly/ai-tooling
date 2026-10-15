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

    def test_requires_all_four_non_secret_handoff_keys(self):
        for value in (
            "LAUNCHDARKLY_AI_CONFIG_KEY=<config-key>",
            "LAUNCHDARKLY_PROJECT_KEY=<project-key>",
            "LAUNCHDARKLY_ENVIRONMENT_KEY=<environment-key>",
            "LAUNCHDARKLY_SETUP_CONFIG_KEY=<setup-config-key>",
        ):
            self.assertIn(value, self.content)
        self.assertIn("Do not proceed until all four are present", self.content)
        self.assertIn(
            "Project and environment keys are required",
            self.content,
        )
        self.assertIn(
            "Never ask for or echo an SDK credential, API token, or provider key",
            self.content,
        )
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
            "Call `get-ai-config` again with `LAUNCHDARKLY_PROJECT_KEY`",
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
        self.assertIn(
            "there is no project-resolution step or unresolvable-project hard stop",
            self.content,
        )
        self.assertNotIn(
            "cannot resolve this AI Config to a project",
            self.content,
        )

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

    def test_uses_setup_config_with_required_fallback_order(self):
        self.assertIn(
            "use the setup Config and variations returned for "
            "`LAUNCHDARKLY_SETUP_CONFIG_KEY`",
            self.content,
        )
        ordered_variations = (
            "1. `<language>-<sdkGeneration>`;",
            "2. `legacy` when `sdkGeneration` is `legacy`;",
            "3. `alpha` when `language` is `go`, `dotnet`, or `ruby`;",
            "4. `default`.",
        )
        offsets = [self.content.index(value) for value in ordered_variations]
        self.assertEqual(offsets, sorted(offsets))

    def test_keeps_setup_instructions_out_of_the_application(self):
        self.assertIn(
            "wire the application call to `LAUNCHDARKLY_AI_CONFIG_KEY`, "
            "never `LAUNCHDARKLY_SETUP_CONFIG_KEY`",
            self.content,
        )
        self.assertIn(
            "never copy setup Config instructions, messages, or prompt text "
            "into the application",
            self.content,
        )
        self.assertIn(
            "Never wire `LAUNCHDARKLY_SETUP_CONFIG_KEY` into application code",
            self.content,
        )

    def test_future_setup_and_reporting_tools_are_optional(self):
        self.assertIn(
            "If `get-setup-instructions` is advertised, prefer it",
            self.content,
        )
        self.assertIn("It is optional, never required", self.content)
        self.assertIn(
            "If it is unavailable or its call fails",
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
