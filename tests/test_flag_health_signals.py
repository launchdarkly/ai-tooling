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


if __name__ == "__main__":
    unittest.main()
