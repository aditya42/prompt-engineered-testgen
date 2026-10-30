# AI-Powered Login Test Generation — SauceDemo

Generate, validate and execute login tests for **[SauceDemo](https://www.saucedemo.com/)** using OpenAI, Python, Playwright/TypeScript, TestRail and Jira.

This portfolio project asks an LLM to produce structured login test cases from predefined acceptance criteria. The resulting plans must pass a strict action validator before the framework compiles them into executable Playwright tests. A deterministic mock provider supports offline testing without API credentials.

## Login scenarios

| Requirement | Scenario | Expected outcome |
| --- | --- | --- |
| LOGIN-001 | Valid credentials | Standard user reaches inventory |
| LOGIN-002 | Incorrect password | Invalid-credentials error |
| LOGIN-003 | Locked-out user | Locked-user error |
| LOGIN-004 | Missing username | Username-required error |
| LOGIN-005 | Missing password | Password-required error |

SauceDemo publicly displays demonstration users and a shared demo password; only these public credentials are used.

## End-to-end workflow

```text
Login acceptance criteria
        |
        v
OpenAI (or deterministic mock)
        |
        v
Five structured test-case plans: ID, title, intent, steps
        |
        v
Strict scenario validation and action allowlist
        |
        v
generated_tests/login.spec.ts
        |
        v
Playwright against https://www.saucedemo.com/
        |
        +--> Playwright JSON report
        +--> TestRail case/run and execution status
        +--> Optional synthetic Jira Bug
        +--> GitHub Actions execution summary
```

**Generation model:** The LLM proposes scenario titles and structured test plans based on five explicit login requirements. The browser actions and expected results are predefined and validated. The LLM does not generate executable TypeScript code.

## Repository structure

```text
.github/workflows/
    code-quality.yml         Offline checks and SauceDemo browser smoke
    test-generation.yml      Manual OpenAI/TestRail/Jira execution
    verify-integrations.yml  Read-only API verification
docs/
    ARCHITECTURE.md
    INTEGRATION_GUIDE.md
test_generation/
    login.py                 Login requirements, validation and compiler
    runner.py                OpenAI provider, TestRail/Jira, CLI and reporting
tests/
    test_runner.py           Mocked offline regression tests
generated_tests/            Generated specs (not committed)
reports/                    Playwright reports (not committed)
state/                      Integration ledgers (not committed)
playwright.config.ts
```

The old local subscription sample application has been removed. SauceDemo is now the website under test.

## Quick start — offline generation, real browser execution

Prerequisites: Python 3.12+, Node.js 22+, Playwright Chromium, Internet access.

```bash
git clone https://github.com/aditya42/prompt-engineered-testgen.git
cd prompt-engineered-testgen

npm install
npx playwright install chromium

# Create 5 deterministic login test cases
python -m test_generation.runner generate --provider mock

# Run all generated login tests on live SauceDemo
npx playwright test

# Run offline Python regression tests
python -m unittest discover -s tests -v
```

To use an LLM instead of the mock, set `OPENAI_API_KEY` and execute:

```bash
python -m test_generation.runner generate --provider openai
npx playwright test
```

By default, the model is `gpt-4.1-mini`; override using `OPENAI_MODEL`. The OpenAI path incurs API usage charges. The response must pass the same validation checks as mock cases.

## GitHub Actions demo

Open [SauceDemo Login — LLM Test Generation](https://github.com/aditya42/prompt-engineered-testgen/actions/workflows/test-generation.yml).

| Action | What happens |
| --- | --- |
| `preview` | Create test cases without TestRail/Jira writes |
| `full-demo` | Publish/reconcile 5 login cases, run Playwright, sync TestRail results |
| `jira-demo` | Inject one *intentional* failure into LOGIN-001 and demonstrate synthetic Jira Bug creation/reuse |

The `provider` input supports `mock` (deterministic) and `openai` (real LLM).

Secrets configured under GitHub Actions: `TESTRAIL_EMAIL`, `TESTRAIL_API_KEY`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, and `OPENAI_API_KEY` for the OpenAI provider.

The older `SUB-001` subscription test case is excluded from new login test runs; existing TestRail cases are not deleted by this migration.

### TestRail retention — destructive

The live workflow keeps only the **three newest TestRail execution runs in project 1** and permanently deletes older runs in that project, even if another workflow created them. TestRail test cases and Jira issues are not deleted. Export important historical run results first.

Preview deletion candidates with `TESTRAIL_RETENTION_SCOPE=project python -m test_generation.runner prune-runs`.

## Validation and limitations

The updated [code-quality workflow](https://github.com/aditya42/prompt-engineered-testgen/actions/workflows/code-quality.yml) runs linting, Python regression tests and generated Playwright login tests. Connected TestRail/Jira login-case publishing needs a new manually triggered run to validate the integration after this change.

Historical [TestRail/Jira integration proof](https://github.com/aditya42/prompt-engineered-testgen/actions/runs/41037773572) concerns the earlier subscription demonstration; it should not be presented as evidence of the new login tests.

The five scenarios are constrained, reviewed acceptance checks, **not autonomous open-ended test discovery** or an empirical benchmark of LLM test generation effectiveness. The project follows PEP 8, KISS, DRY, YAGNI and separation of concerns.

[Architecture](docs/ARCHITECTURE.md) | [Integration guide](docs/INTEGRATION_GUIDE.md) | [Contributing](CONTRIBUTING.md)
