import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIGNALS = (
    ROOT
    / "skills/feature-flags/launchdarkly-flag-discovery/references/flag-health-signals.md"
)


class DecisionMatrixTests(unittest.TestCase):
    def _matrix_rows(self):
        body = SIGNALS.read_text(encoding="utf-8")
        start = body.index("## Decision Matrix")
        return [line for line in body[start:].splitlines() if line.startswith("| ")]

    def test_flags_that_are_not_launched_are_not_ready_for_code_removal(self):
        """A flag with no evaluations is not `launched`, so removing it can
        delete a feature that was never released (EMSR-2643)."""
        for state in ("Never requested", "OFF in every critical environment"):
            row = next(r for r in self._matrix_rows() if state in r)
            self.assertIn("Not ready for code removal", row)
            self.assertNotIn("before removing", row)


class CodeAlreadyRemovedTests(unittest.TestCase):
    def test_discovery_checks_this_repository_before_archiving(self):
        """`codeAlreadyRemoved` can mean the code is in a repository that
        LaunchDarkly does not scan, so discovery must not recommend archiving
        while this repository still references the flag (EMSR-2643 Bugbot)."""
        discovery = ROOT / "skills/feature-flags/launchdarkly-flag-discovery"
        for path in (
            discovery / "SKILL.md",
            discovery / "references/removal-readiness-checklist.md",
        ):
            line = next(
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if "code_already_removed" in line and "archiving" in line
            )
            self.assertIn("Search this repository for the flag key first", line, path)
            self.assertIn("do not recommend archiving", line, path)

    def test_discovery_checks_this_repository_before_archiving_a_ready_to_archive_flag(self):
        """`readyToArchive` also relies on LaunchDarkly's code references, which
        may not cover this repository (EMSR-2643 review)."""
        discovery = ROOT / "skills/feature-flags/launchdarkly-flag-discovery"
        for path in (
            discovery / "SKILL.md",
            discovery / "references/removal-readiness-checklist.md",
        ):
            line = next(
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if "readyToArchive` is `true`" in line or "readyToArchive: true" in line
            )
            self.assertIn("Search this repository for the flag key first", line, path)


class DecisionMatrixLaunchedTests(unittest.TestCase):
    def test_launched_rows_follow_the_ready_for_cleanup_rule(self):
        body = SIGNALS.read_text(encoding="utf-8")
        rows = [l for l in body[body.index("## Decision Matrix"):].splitlines() if l.startswith("| ")]
        temporary = next(r for r in rows if r.startswith("| Yes | Launched"))
        self.assertIn("every critical environment", temporary)
        self.assertIn("30+ days", temporary)
        permanent = next(r for r in rows if r.startswith("| No | Launched"))
        self.assertIn("Not ready for code removal", permanent)
        self.assertIn("notTemporary", permanent)


class CleanupSkillTests(unittest.TestCase):
    CLEANUP = ROOT / "skills/feature-flags/launchdarkly-flag-cleanup/SKILL.md"

    def _paragraph(self, start):
        body = self.CLEANUP.read_text(encoding="utf-8")
        return next(p for p in body.split("\n\n") if p.startswith(start))

    def test_blocked_names_the_only_exception(self):
        blocked = self._paragraph("**`blocked`**")
        self.assertIn("Do not remove code", blocked)
        self.assertIn("OFF in every critical environment", blocked)

    def test_code_already_removed_with_references_continues_without_a_second_ask(self):
        rule = self._paragraph("If `details.lifecycle.readyForCodeRemoval` is `false`")
        exception = rule[rule.index("One exception"):]
        self.assertNotIn("unless the user explicitly asks", exception)
        self.assertIn("continue", exception)

    def test_forward_value_stops_when_the_tool_cannot_name_one_value(self):
        body = self.CLEANUP.read_text(encoding="utf-8")
        row = next(l for l in body.splitlines() if l.startswith("| ") and "recommended_value_unknown" in l)
        self.assertIn("NOT SAFE", row)
        self.assertIn("`recommendedValue`", body)

    def test_ready_to_archive_with_references_stops(self):
        archive = self.CLEANUP.read_text(encoding="utf-8")
        line = next(l for l in archive.splitlines() if l.startswith("- If you found references in Step 1, do not offer to archive it: an archived"))
        self.assertIn("Stop.", line)

    def test_after_cleanup_rechecks_before_archiving(self):
        body = self.CLEANUP.read_text(encoding="utf-8")
        after = body[body.index("## After Cleanup"):]
        step = next(l for l in after.splitlines() if "**Archive the flag in LaunchDarkly**" in l)
        self.assertIn("run `get-removal-readiness` again", step)
        self.assertIn("do not archive", step)


if __name__ == "__main__":
    unittest.main()
