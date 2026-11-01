"""Offline tests for SauceDemo generation and integration safeguards."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_generation import cart, login, runner
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
            "KNOWN_DEFECT_DEMO": "false",
            "GITHUB_RUN_ID": "fixture-run",
        })
        env.start()
        self.addCleanup(env.stop)

    def test_testrail_run_name_is_descriptive_and_stable(self):
        name = runner.testrail_run_name("41327291819")
        self.assertIn("SauceDemo | Login + Cart Regression", name)
        self.assertIn("BrowserStack (Chrome / Windows 11)", name)
        self.assertNotIn("41327291819", name)
        self.assertNotIn("GitHub #", name)
        self.assertEqual(runner.testrail_run_description("41327291819"),
                         "GitHub Actions run: 41327291819")
        self.assertEqual(name, runner.testrail_run_name("41327291819"))

    def test_run_creation_keeps_github_identifier_out_of_title(self):
        runner.save(self.state / "case-map.json", {"LOGIN-001": 2})
        captured = []

        def fake_testrail(endpoint, method="GET", body=None):
            captured.append((endpoint, method, body))
            if endpoint.startswith("get_runs/"):
                return {"runs": [], "_links": {"next": None}}
            if endpoint == "add_run/1":
                return {"id": 42}
            raise AssertionError(endpoint)

        with patch.object(runner, "tr", side_effect=fake_testrail):
            runner.create_run(True)
        body = next(item[2] for item in captured if item[0] == "add_run/1")
        self.assertNotIn("fixture-run", body["name"])
        self.assertEqual(body["description"], "GitHub Actions run: fixture-run")

    def test_run_retry_reuses_same_description_not_same_title(self):
        runner.save(self.state / "case-map.json", {"LOGIN-001": 2})
        created = []

        def fake_testrail(endpoint, method="GET", body=None):
            if endpoint.startswith("get_runs/"):
                return {"runs": [
                    {"id": 30, "name": runner.testrail_run_name(),
                     "description": "GitHub Actions run: a-different-run"},
                    {"id": 31, "name": runner.testrail_run_name(),
                     "description": "GitHub Actions run: fixture-run"},
                ], "_links": {"next": None}}
            if endpoint == "add_run/1":
                created.append(body)
                return {"id": 55}
            raise AssertionError(endpoint)

        with patch.object(runner, "tr", side_effect=fake_testrail):
            runner.create_run(True)
        self.assertEqual(runner.read(self.state / "run.json", {})["id"], 31)
        self.assertFalse(created)

    def test_existing_run_renamed_without_changing_results(self):
        calls = []

        def fake_testrail(path, method="GET", body=None):
            calls.append((path, method, body))
            if path == "get_run/9":
                return {"id": 9, "project_id": 1,
                        "name": "SauceDemo login run 41327291819"}
            if path == "update_run/9":
                return {"id": 9}
            raise AssertionError(path)

        with patch.object(runner, "tr", side_effect=fake_testrail):
            runner.rename_testrail_run(9, "41327291819")
        self.assertEqual(calls[1][0], "update_run/9")
        self.assertEqual(calls[1][1], "POST")
        self.assertEqual(calls[1][2], {
            "name": runner.testrail_run_name("41327291819"),
        })

    def test_rename_refuses_unexpected_run_name(self):
        with patch.object(runner, "tr", return_value={
            "id": 9, "project_id": 1, "name": "Unrelated release run"
        }) as api:
            with self.assertRaisesRegex(RuntimeError, "unexpected TestRail run name"):
                runner.rename_testrail_run(9, "41327291819")
        api.assert_called_once()

    def test_mock_covers_five_login_requirements(self):
        cases = runner.generate("mock")
        self.assertEqual(len(cases), 10)
        self.assertEqual(
            {case["id"] for case in cases},
            {"LOGIN-001", "LOGIN-002", "LOGIN-003", "LOGIN-004", "LOGIN-005",
             "CART-001", "CART-002", "CART-003", "CART-004", "CART-005"},
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

    def test_known_training_defect_is_opt_in_and_labelled(self):
        with patch.dict(os.environ, {"KNOWN_DEFECT_DEMO": "true"}):
            cases = runner.generate("mock")
            self.assertEqual(len(cases), 11)
            runner.playwright(cases, {})
        spec = (self.root / "generated_tests" / "known_defect.spec.ts").read_text()
        self.assertIn("problem_user", spec)
        self.assertIn("DEMO-001", spec)
        self.assertIn("add-to-cart-sauce-labs-fleece-jacket", spec)
        self.assertNotIn("intentional-demo-failure", spec)

    def test_normal_generation_cleans_old_training_defect_spec(self):
        folder = self.root / "generated_tests"
        folder.mkdir()
        old = folder / "known_defect.spec.ts"
        old.write_text("stale")
        runner.playwright(runner.generate("mock"), {})
        self.assertFalse(old.exists())

    def test_known_training_defect_quality_gate_requires_baseline_pass(self):
        reports = self.root / "reports"
        reports.mkdir()
        good_cases = [
            {"title": "[LOGIN-001] pass", "tests": [{"status": "expected"}]}
            for _ in range(10)
        ]
        (reports / "playwright-results.json").write_text(json.dumps({
            "suites": [{"specs": good_cases + [{
                "title": "[DEMO-001] known training failure",
                "tests": [{"status": "unexpected"}],
            }]}],
        }))
        with patch.dict(os.environ, {"KNOWN_DEFECT_DEMO": "true"}):
            runner.quality_gate()

    def test_cart_positive_and_negative_specs_generated(self):
        runner.playwright(runner.generate("mock"), {})
        spec = (self.root / "generated_tests" / "cart.spec.ts").read_text()
        self.assertEqual(spec.count("test("), 5)
        self.assertIn("[CART-001]", spec)
        self.assertIn("[CART-005]", spec)
        self.assertIn("add-to-cart-sauce-labs-backpack", spec)
        self.assertIn("remove-sauce-labs-backpack", spec)
        self.assertIn("toHaveCount(0)", spec)

    def test_cart_validation_rejects_unreviewed_failure_injection(self):
        cases = cart.mock_cases()
        cases[0]["steps"].append("intentionally_break_product")
        with self.assertRaisesRegex(RuntimeError, "safety validation"):
            cart.validate_cases(cases)

    def test_cart_scenarios_start_with_login(self):
        for case in cart.REQUIREMENTS:
            self.assertEqual(case["steps"][0], "login")

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
            runner.playwright(login.mock_cases() + cart.mock_cases(), {})
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

    def test_known_training_defect_jira_issue_is_labelled_as_demo(self):
        runner.save(self.state / "run.json", {"id": 25})
        reports = self.root / "reports"
        reports.mkdir()
        (reports / "playwright-results.json").write_text(json.dumps({
            "suites": [{"specs": [{
                "title": "[TR:C7] [DEMO-001] known training cart failure",
                "tests": [{"status": "unexpected", "results": [
                    {"status": "failed", "error": {
                        "message": "expect(locator).toHaveText failed",
                    }},
                    {"status": "failed", "error": {
                        "message": "expect(locator).toHaveText failed",
                    }},
                ]}],
            }]}],
        }))
        created = []

        def fake_jira(path, method="GET", body=None):
            if path.startswith("search/jql?"):
                return {"issues": []}
            if path.startswith("project/"):
                return {"issueTypes": [{"name": "Bug", "id": "10010"}]}
            if path == "issue" and method == "POST":
                created.append(body["fields"])
                return {"key": "KAN-102"}
            raise AssertionError(path)

        with patch.dict(os.environ, {
            "KNOWN_DEFECT_DEMO": "true", "JIRA_PROJECT_KEY": "KAN"
        }):
            with patch.object(runner, "tr", return_value={"id": 30}):
                with patch.object(runner, "jira", side_effect=fake_jira):
                    runner.sync(True, True)
        self.assertEqual(len(created), 1)
        self.assertIn("known-training-defect", created[0]["labels"])
        self.assertIn("synthetic-demo", created[0]["labels"])
        self.assertNotIn("needs-triage", created[0]["labels"])
        self.assertIn("KNOWN TRAINING DEFECT", created[0]["summary"])

    def test_flaky_result_is_retest_in_testrail_not_jira_bug(self):
        runner.save(self.state / "run.json", {"id": 24})
        reports = self.root / "reports"
        reports.mkdir()
        (reports / "playwright-results.json").write_text(json.dumps({
            "suites": [{"specs": [{
                "title": "[TR:C12] [LOGIN-001] flaky login",
                "tests": [{
                    "status": "flaky",
                    "results": [
                        {"status": "failed", "error": {"message": "expect(page) failed"}},
                        {"status": "passed"},
                    ],
                }],
            }]}],
        }))
        with patch.object(runner, "tr", return_value={"id": 20}) as testrail:
            with patch.object(runner, "jira") as jira_api:
                runner.sync(True, True)
        self.assertEqual(testrail.call_args[0][2]["status_id"], 4)
        jira_api.assert_not_called()

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
