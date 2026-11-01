# LLM Test Generation + BrowserStack + TestRail + Jira

Generate structured login tests with an LLM, run **Playwright on BrowserStack cloud browsers**, publish results to TestRail, and create Jira defect candidates only for reproducible application assertion failures.

## Architecture

```text
Login requirements (LOGIN-001 ... LOGIN-005)
          |
          v
OpenAI / deterministic mock -> validate safe actions
          |
          v
generated_tests/login.spec.ts (Playwright)
          |
          v
BrowserStack Automate (remote Windows Chrome)
          |
          +-- Playwright JSON report + BrowserStack build
          +-- TestRail: one linked automated result per test
          +-- Jira: repeated assertion failures only (needs-triage)
          +-- GitHub Actions: summary and retention
```

**BrowserStack is the execution platform, not an application under test.** SauceDemo remains the public demo login website. Set `SAUCEDEMO_BASE_URL` to change the target URL, but the login selectors and scenarios must also be adapted for a different application.

## Coverage

| Case | Scenario |
| --- | --- |
| LOGIN-001 | Valid standard-user login |
| LOGIN-002 | Incorrect password |
| LOGIN-003 | Locked user |
| LOGIN-004 | Missing username |
| LOGIN-005 | Missing password |

The LLM produces test case titles and constrained steps, **not arbitrary executable code**. Test steps are validated against the reviewed action catalog in `test_generation/login.py`.

## Structure

```text
test_generation/
  login.py           Requirement catalog, bounded Playwright compiler
  runner.py          OpenAI generation, TestRail sync, Jira sync, summary and CLI
  failure_triage.py  Repeatability / assertion / infrastructure triage
tests/
  test_runner.py     Offline unit tests and integration safety checks
browserstack.yml     Cloud browser capabilities and build reporting
playwright.config.ts Playwright JSON reporting, 1 CI retry, traces
.github/workflows/
  test-generation.yml   Manually run BrowserStack -> TestRail -> Jira
  code-quality.yml      Local mock + lint/Playwright regression tests
docs/
  ARCHITECTURE.md
  INTEGRATION_GUIDE.md
```

## Set up BrowserStack

Create a BrowserStack Automate account and find its **Username** and **Access Key**. Add these as GitHub repository Actions secrets:

| Secret | Purpose |
| --- | --- |
| `BROWSERSTACK_USERNAME` | BrowserStack authentication |
| `BROWSERSTACK_ACCESS_KEY` | BrowserStack authentication |
| `TESTRAIL_EMAIL`, `TESTRAIL_API_KEY` | Publish test cases and results |
| `JIRA_EMAIL`, `JIRA_API_TOKEN` | Create/reuse Jira Bug candidates |
| `OPENAI_API_KEY` | Needed for the `openai` generation provider |

Do not put credentials in `browserstack.yml` or commit them. The SDK uses the environment variables from GitHub Actions secrets.

## Run locally

Requires Python 3.12+, Node.js 22+, and the BrowserStack SDK:

```bash
npm install

# Generate five deterministic test cases without an LLM API call
python -m test_generation.runner generate --provider mock

# Run locally (requires Playwright browser installation)
npx playwright install chromium
npx playwright test

# Execute on BrowserStack with exported BrowserStack credentials
npm run test:browserstack

# Offline tests
python -m unittest discover -s tests -v
```

For real LLM generation, configure `OPENAI_API_KEY` then use `python -m test_generation.runner generate --provider openai`.

BrowserStack's documented Playwright Node SDK integrates through `browserstack.yml` and `npx browserstack-node-sdk playwright test`. See [BrowserStack documentation](https://www.browserstack.com/docs/automate/playwright/getting-started/nodejs/integrate-your-tests).

## Connected workflow

[Open the BrowserStack execution workflow](https://github.com/aditya42/prompt-engineered-testgen/actions/workflows/test-generation.yml).

| Mode | Behavior |
| --- | --- |
| `preview` | Generate test cases without remote TestRail/Jira writes |
| `full-demo` | Run Playwright on BrowserStack, sync results to TestRail, triage failures for Jira |

Choose `openai` for genuine LLM case generation; `mock` remains useful for repeatable engineering checks. The workflow verifies BrowserStack credentials before publishing a TestRail run. The cloud execution step may fail while the downstream result sync still runs; the **quality gate reports failure after publishing**.

## Jira defect-creation policy

**Automatic Jira tickets are limited to high-confidence candidates, not guaranteed true product defects.** A failed test becomes eligible only when:

1. The same test fails on its original attempt **and retry**.
2. Both failure messages contain recognizable Playwright assertion evidence.
3. There is no evident BrowserStack, connection, browser or timeout failure.
4. The test maps to a TestRail case and passes the duplicate-issue check.

Tickets are labeled `browserstack`, `automated-qa`, and `needs-triage`, and include the case title, TestRail run and error evidence. A human should verify whether the application, test code, data or environment caused the problem. Flaky tests, missing reports, infrastructure failures and unclassified failures **do not generate automatic Jira Bugs**. Such executions still fail the quality gate.

## TestRail result and retention policy

Every executed Playwright test with a linked `[TR:C...] ` marker is synchronized to TestRail. Passing results use Passed; unexpected failures use Failed. A Jira issue is an additional triaged artifact, not a replacement for a failed TestRail result.

The existing workflow **permanently deletes every TestRail run older than the newest three in project 1**, including unrelated runs. Test cases and Jira issues are preserved. Export any historical run results before using `full-demo`.

## Validation status

Previously, five login tests passed on a local GitHub Actions runner. The BrowserStack integration and automatic Jira triage now require a **new credentialed cloud workflow run** to verify real remote sessions, BrowserStack build visibility, result synchronization and Jira creation behavior. No new cloud sessions or production defects are claimed until that validation succeeds.

See [architecture](docs/ARCHITECTURE.md), [integration guide](docs/INTEGRATION_GUIDE.md), and [contribution guidelines](CONTRIBUTING.md).
