import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from phase2 import runner


class Phase2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.patch_state = patch.object(runner, "STATE", self.state)
        self.patch_state.start()
        self.addCleanup(self.patch_state.stop)
        self.env = patch.dict(os.environ, {
            "TESTRAIL_PROJECT_ID": "1", "TESTRAIL_SECTION_ID": "1",
            "JIRA_PROJECT_KEY": "KAN", "GITHUB_RUN_ID": "test123"
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_remote_reconciliation_reuses_existing_case(self):
        with patch.object(runner, "tr", return_value={"cases": [
            {"id": 1, "section_id": 1, "title": "[SUB-001] Already published"}
        ], "_links": {"next": None}}):
            self.assertEqual(runner.existing_testrail_cases(), {"SUB-001": 1})

    def test_duplicate_requirement_id_rejected(self):
        with patch.object(runner, "tr", return_value={"cases": [
            {"id": 1, "section_id": 1, "title": "[SUB-001] First"},
            {"id": 2, "section_id": 1, "title": "[SUB-001] Duplicate"}
        ], "_links": {"next": None}}):
            with self.assertRaisesRegex(RuntimeError, "Duplicate TestRail"):
                runner.existing_testrail_cases()

    def test_publish_skips_duplicate_creation(self):
        with patch.object(runner, "tr", return_value={"cases": [
            {"id": 1, "section_id": 1, "title": "[SUB-001] Published"}
        ], "_links": {"next": None}}), patch.object(runner, "playwright"):
            runner.publish(True, "mock")
        self.assertEqual(runner.read(self.state / "case-map.json", {}), {"SUB-001": 1})

    def test_explicit_failure_injection(self):
        with patch.object(runner, "ROOT", self.state):
            with patch.dict(os.environ, {"DEMO_INJECT_FAILURE": "true"}):
                runner.playwright(runner.REQUIREMENTS, {"SUB-001": 1})
            self.assertIn("INTENTIONALLY WRONG - DEMO",
                          (self.state / "generated" / "subscription.spec.ts").read_text())

    def test_jira_creation_rejected_outside_demo_mode(self):
        root = self.state
        (root / "reports").mkdir()
        (root / "reports" / "playwright-results.json").write_text(json.dumps({
            "suites": [{"specs": [{"title": "[TR:C1] demo", "tests": [
                {"status": "unexpected", "results": [{"error": {"message": "failed"}}]}
            ]}]}]
        }))
        runner.save(self.state / "run.json", {"id": 10})
        with patch.object(runner, "ROOT", root), patch.dict(os.environ, {"DEMO_INJECT_FAILURE": "false"}):
            with self.assertRaisesRegex(RuntimeError, "explicit synthetic"):
                runner.sync(True, True)


if __name__ == "__main__":
    unittest.main()
