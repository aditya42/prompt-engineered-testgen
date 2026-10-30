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

    def test_workflow_retention_and_summary_run_after_live_execution(self):
        workflow = (Path(__file__).resolve().parent.parent /
                    ".github" / "workflows" / "phase2.yml").read_text()
        self.assertIn("python -m phase2.runner prune-runs --apply", workflow)
        self.assertIn("TESTRAIL_RETENTION_SCOPE: project", workflow)
        self.assertIn("python -m phase2.runner summary", workflow)
        self.assertIn("if: ${{ always() && inputs.action != 'preview' }}", workflow)

    def test_retention_keeps_three_and_never_deletes_unrelated(self):
        records = [{"id": i, "name": "PromptTestGen phase 2 run " + str(i)}
                   for i in range(1, 7)]
        records.append({"id": 99, "name": "Business critical regression"})
        runner.save(self.state / "run.json", {"id": 6})
        calls = []
        def api(endpoint, method="GET", body=None):
            calls.append((endpoint, method))
            if endpoint.startswith("get_runs/"):
                return {"runs": records, "_links": {"next": None}}
            if endpoint.startswith("delete_run/"):
                return {}
            raise AssertionError(endpoint)
        with patch.object(runner, "tr", side_effect=api):
            result = runner.prune_runs(True)
        self.assertEqual(result["deleted"], [3, 2, 1])
        self.assertEqual(result["preserved"], [4, 5, 6])
        self.assertNotIn(("delete_run/99", "POST"), calls)

    def test_project_scope_removes_all_older_project_runs(self):
        runs = [{"id": i, "name": ("Other suite" if i == 1 else "PromptTestGen phase 2 run " + str(i))}
                for i in range(1, 6)]
        runner.save(self.state / "run.json", {"id": 5})
        calls = []
        def fake_tr(endpoint, method="GET", body=None):
            calls.append((endpoint, method))
            if endpoint.startswith("get_runs/"):
                return {"runs": runs, "_links": {"next": None}}
            if endpoint.startswith("delete_run/"):
                return {}
            raise AssertionError(endpoint)
        with patch.dict(os.environ, {"TESTRAIL_RETENTION_SCOPE": "project"}), patch.object(runner, "tr", side_effect=fake_tr):
            result = runner.prune_runs(True)
        self.assertEqual(result["deleted"], [2, 1])
        self.assertEqual(result["preserved"], [3, 4, 5])
        self.assertIn(("delete_run/1", "POST"), calls)

    def test_retention_dry_run_never_deletes(self):
        runs = [{"id": i, "name": "PromptTestGen phase 2 run " + str(i)}
                for i in range(1, 5)]
        with patch.object(runner, "tr", return_value={"runs": runs, "_links": {"next": None}}) as api:
            result = runner.prune_runs(False)
        self.assertEqual(result["delete"], [1])
        self.assertTrue(result["dry_run"])
        self.assertEqual(api.call_count, 1)

    def test_retention_preserves_active_run(self):
        runs = [{"id": i, "name": "PromptTestGen phase 2 run " + str(i)}
                for i in range(1, 6)]
        runner.save(self.state / "run.json", {"id": 2})
        with patch.object(runner, "tr", return_value={"runs": runs, "_links": {"next": None}}):
            result = runner.prune_runs(False)
        self.assertNotIn(2, result["delete"])

    def test_summary_contains_testrail_and_jira_links(self):
        runner.save(self.state / "run.json", {"id": 6})
        runner.save(self.state / "case-map.json", {"SUB-001": 1})
        runner.save(self.state / "ledger.json", {"6:1:failed": {"jira_key": "KAN-7"}})
        runner.save(self.state / "retention.json", {"deleted": [1, 2, 3]})
        runner.save(self.state / "plan.json", {"provider": "mock"})
        with patch.object(runner, "ROOT", self.state), patch.dict(os.environ, {
            "TESTRAIL_URL": "https://example.testrail.io",
            "JIRA_URL": "https://example.atlassian.net",
            "GITHUB_STEP_SUMMARY": ""
        }):
            summary = runner.execution_summary()
        self.assertIn("runs/view/6", summary)
        self.assertIn("cases/view/1", summary)
        self.assertIn("browse/KAN-7", summary)
        self.assertIn("R1, R2, R3", summary)

    def test_jira_bug_type_resolved_by_id(self):
        with patch.object(runner, "jira", return_value={
            "issueTypes": [{"id": "10001", "name": "Task"},
                           {"id": "10004", "name": "Bug"}]
        }):
            self.assertEqual(runner.jira_issue_type("KAN"), "10004")

    def test_jira_missing_bug_type_fails_without_substitution(self):
        with patch.object(runner, "jira", return_value={
            "issueTypes": [{"id": "10001", "name": "Task"}]
        }):
            with self.assertRaisesRegex(RuntimeError, "Bug.*unavailable"):
                runner.jira_issue_type("KAN")

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
