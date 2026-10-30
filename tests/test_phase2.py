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

    def test_clean_error_removes_terminal_ansi_codes(self):
        dirty = "\x1b[31mAssertion failed\x1b[0m"
        self.assertEqual(runner.clean_error(dirty), "Assertion failed")

    def test_jira_demo_executes_browser_and_result_sync(self):
        workflow = (Path(__file__).resolve().parent.parent /
                    ".github" / "workflows" / "phase2.yml").read_text()
        for step in ("Install browser dependencies", "Run generated Playwright test",
                     "Synchronize TestRail results"):
            block = workflow.split("- name: " + step + "\n", 1)[1].split("\n      - name:", 1)[0]
            self.assertIn("if: inputs.action != 'preview'", block)

    def test_testrail_pagination_uses_ampersand(self):
        calls = []
        def fake_tr(endpoint):
            calls.append(endpoint)
            return {"cases": [{"id": 1, "section_id": 1,
                               "title": "[SUB-001] Already published"}],
                    "_links": {"next": None}}
        with patch.object(runner, "tr", side_effect=fake_tr):
            runner.existing_testrail_cases()
        self.assertEqual(calls[0], "get_cases/1&limit=250&offset=0")

    def test_run_listing_uses_ampersand(self):
        runner.save(self.state / "case-map.json", {"SUB-001": 1})
        calls = []
        def fake_tr(endpoint, method="GET", body=None):
            calls.append((endpoint, method))
            if endpoint.startswith("get_runs/"):
                return {"runs": [{"id": 8, "name": "PromptTestGen phase 2 run test123"}],
                        "_links": {"next": None}}
            raise AssertionError("Unexpected TestRail write")
        with patch.object(runner, "tr", side_effect=fake_tr):
            runner.create_run(True)
        self.assertEqual(calls, [("get_runs/1&limit=250&offset=0", "GET")])

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
