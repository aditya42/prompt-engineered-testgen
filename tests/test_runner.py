"""Offline tests for SauceDemo generation and integration safeguards."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_generation import login, runner
from test_generation.failure_triage import classify_failure


class LoginGenerationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.state = self.root / "state"
        self.state.mkdir()
        for name, value in (("ROOT", self.root), ("STATE", self.state)):
            mocked = patch.object(runner, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        env = patch.dict(os.environ, {
            "TESTRAIL_PROJECT_ID": "1",
            "TESTRAIL_SECTION_ID": "1",
            "TESTRAIL_RETENTION_SCOPE": "managed",
            "GITHUB_RUN_ID": "fixture-run",
        })
        env.start()
        self.addCleanup(env.stop)

    def test_mock_covers_five_login_requirements(self):
        cases = runner.generate("mock")
        self.assertEqual(len(cases), 5)
        self.assertEqual(
            {case["id"] for case in cases},
            {"LOGIN-001", "LOGIN-002", "LOGIN-003", "LOGIN-004", "LOGIN-005"},
        )

    def test_compiler_generates_five_playwright_cases(self):
        runner.playwright(runner.generate("mock"), {})
        spec = (self.root / "generated_tests" / "login.spec.ts").read_text()
        self.assertEqual(spec.count("test("), 5)
        self.assertIn("standard_user", spec)
        self.assertIn("locked_out_user", spec)
        self.assertIn("Username is required", spec)
        self.assertIn("Password is required", spec)
        self.assertIn("inventory", spec)

    def test_llm_can_generate_valid_case_titles(self):
        cases = runner.generate("mock")
        cases[0]["title"] = "Verify standard user authentication succeeds"
        response = {"choices": [{"message": {
            "content": json.dumps({"cases": cases})
        }}]}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "offline-fixture"}):
            with patch.object(runner, "api", return_value=response):
                result = runner.generate("openai")
        self.assertEqual(result[0]["title"], cases[0]["title"])

    def test_llm_cannot_invent_executable_steps(self):
        cases = login.mock_cases()
        cases[0]["steps"] = ["open_login", "execute_python"]
        with self.assertRaisesRegex(RuntimeError, "safety validation"):
            login.validate_cases(cases)

    def test_llm_cannot_omit_negative_login_scenarios(self):
        with self.assertRaisesRegex(RuntimeError, "incomplete or duplicate"):
            login.validate_cases(login.mock_cases()[:1])

    def test_compiler_revalidates_cases(self):
        cases = login.mock_cases()
        cases[0]["intent"] = "other"
        with self.assertRaisesRegex(RuntimeError, "safety validation"):
            login.compile_playwright(cases, {}, self.root)

    def test_negative_demo_only_fails_positive_case(self):
        with patch.dict(os.environ, {"DEMO_INJECT_FAILURE": "true"}):
            runner.playwright(login.mock_cases(), {})
        spec = (self.root / "generated_tests" / "login.spec.ts").read_text()
        self.assertEqual(spec.count("intentional-demo-failure"), 1)

    def test_publish_excludes_old_subscription_cases(self):
        with patch.object(runner, "existing_testrail_cases", return_value={
            "SUB-001": 1,
            "LOGIN-001": 12,
        }):
            with patch.object(runner, "tr", return_value={"id": 13}):
                runner.publish(True, "mock")
        mapping = runner.read(self.state / "case-map.json", {})
        self.assertEqual(mapping["LOGIN-001"], 12)
        self.assertNotIn("SUB-001", mapping)

    def test_preview_does_not_write_external_cases(self):
        with patch.object(runner, "tr", side_effect=AssertionError("unexpected write")):
            runner.publish(False, "mock")

    def test_case_lookup_uses_testrail_pagination(self):
        with patch.object(runner, "tr", return_value={
            "cases": [{"id": 3, "section_id": 1, "title": "[LOGIN-001] valid"}],
            "_links": {"next": None},
        }) as request:
            self.assertEqual(runner.existing_testrail_cases(), {"LOGIN-001": 3})
        request.assert_called_once_with("get_cases/1&limit=250&offset=0")

    def test_retention_keeps_three_in_project_scope(self):
        runner.save(self.state / "run.json", {"id": 6})
        runs = [{"id": i, "name": "Previous run"} for i in range(1, 7)]

        def fake_api(endpoint, method="GET", body=None):
            if endpoint.startswith("get_runs/"):
                return {"runs": runs, "_links": {"next": None}}
            if endpoint.startswith("get_run/"):
                return {"project_id": 1}
            if endpoint.startswith("delete_run/"):
                self.assertEqual(body, {"soft": 0})
                return {}
            raise AssertionError(endpoint)

        with patch.dict(os.environ, {"TESTRAIL_RETENTION_SCOPE": "project"}):
            with patch.object(runner, "tr", side_effect=fake_api):
                result = runner.prune_runs(True)
        self.assertEqual(result["preserved"], [4, 5, 6])
        self.assertEqual(result["deleted"], [3, 2, 1])

    def test_repeated_assertion_failure_is_jira_candidate(self):
        test = {
            "status": "unexpected",
            "results": [
                {"status": "failed", "error": {"message": "expect(locator).toHaveText failed"}},
                {"status": "failed", "error": {"message": "expect(locator).toHaveText failed"}},
            ],
        }
        self.assertTrue(classify_failure(test)[0])

    def test_flaky_failure_is_not_jira_candidate(self):
        test = {
            "status": "flaky",
            "results": [
                {"status": "failed", "error": {"message": "expect(locator) failed"}},
                {"status": "passed"},
            ],
        }
        self.assertFalse(classify_failure(test)[0])

    def test_single_failure_does_not_create_jira_candidate(self):
        test = {
            "status": "unexpected",
            "results": [
                {"status": "failed", "error": {"message": "expect(locator) failed"}},
            ],
        }
        self.assertFalse(classify_failure(test)[0])

    def test_infrastructure_failure_does_not_create_jira_candidate(self):
        test = {
            "status": "unexpected",
            "results": [
                {"status": "failed", "error": {"message": "browserstack connection timed out"}},
                {"status": "failed", "error": {"message": "browserstack connection timed out"}},
            ],
        }
        self.assertFalse(classify_failure(test)[0])

    def test_sync_never_files_jira_for_untriaged_failure(self):
        runner.save(self.state / "run.json", {"id": 22})
        reports = self.root / "reports"
        reports.mkdir()
        (reports / "playwright-results.json").write_text(json.dumps({
            "suites": [{"specs": [{
                "title": "[TR:C12] [LOGIN-001] login",
                "tests": [{"status": "unexpected", "results": [{
                    "status": "failed",
                    "error": {"message": "BrowserStack connection timed out"},
                }, {
                    "status": "failed",
                    "error": {"message": "BrowserStack connection timed out"},
                }]}],
            }]}],
        }))
        with patch.object(runner, "tr", return_value={"id": 15}):
            with patch.object(runner, "jira") as jira_api:
                runner.sync(True, True)
        jira_api.assert_not_called()

    def test_sync_creates_jira_candidate_for_repeated_assertion(self):
        runner.save(self.state / "run.json", {"id": 23})
        reports = self.root / "reports"
        reports.mkdir()
        (reports / "playwright-results.json").write_text(json.dumps({
            "suites": [{"specs": [{
                "title": "[TR:C12] [LOGIN-001] valid login",
                "tests": [{"status": "unexpected", "results": [{
                    "status": "failed",
                    "error": {"message": "expect(page).toHaveURL failed"},
                }, {
                    "status": "failed",
                    "error": {"message": "expect(page).toHaveURL failed"},
                }]}],
            }]}],
        }))

        jira_calls = []

        def fake_jira(endpoint, method="GET", body=None):
            jira_calls.append((endpoint, method))
            if endpoint.startswith("search/jql?"):
                return {"issues": []}
            if endpoint.startswith("project/"):
                return {"issueTypes": [{"name": "Bug", "id": "10010"}]}
            if endpoint == "issue" and method == "POST":
                self.assertIn("needs-triage", body["fields"]["labels"])
                return {"key": "KAN-101"}
            raise AssertionError(endpoint)

        with patch.dict(os.environ, {"JIRA_PROJECT_KEY": "KAN"}):
            with patch.object(runner, "tr", return_value={"id": 15}):
                with patch.object(runner, "jira", side_effect=fake_jira):
                    runner.sync(True, True)
        self.assertIn(("issue", "POST"), jira_calls)
        ledger = runner.read(self.state / "ledger.json", {})
        self.assertEqual(ledger["23:12:failed"]["jira_key"], "KAN-101")

    def test_missing_report_fails_quality_gate(self):
        with self.assertRaisesRegex(RuntimeError, "Missing Playwright"):
            runner.quality_gate()

    def test_workflow_requires_browserstack_and_triggers_jira_triage(self):
        source = (Path(__file__).resolve().parent.parent
                  / ".github" / "workflows" / "test-generation.yml").read_text()
        self.assertIn("BROWSERSTACK_USERNAME", source)
        self.assertIn("BROWSERSTACK_ACCESS_KEY", source)
        self.assertIn("browserstack-node-sdk playwright test", source)
        self.assertIn("sync --apply --create-bugs", source)
        self.assertIn("quality-gate", source)
        self.assertNotIn("jira-demo", source)


if __name__ == "__main__":
    unittest.main()
