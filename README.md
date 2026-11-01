# LLM-Generated Login and Cart Testing — BrowserStack, TestRail and Jira

A reproducible quality-engineering demonstration that generates **five login** and **five add-to-cart** acceptance tests for the public [SauceDemo](https://www.saucedemo.com/) training store using an LLM or a deterministic mock. It compiles validated test plans into Playwright tests, executes them using BrowserStack, publishes automated results to TestRail, and triages reproducible assertion failures for Jira.

## Test coverage

| ID | Area | Positive / negative | Expected behavior |
| --- | --- | --- | --- |
| LOGIN-001 | Login | Positive | Valid standard user reaches inventory |
| LOGIN-002 | Login | Negative | Incorrect password is rejected |
| LOGIN-003 | Login | Negative | Locked account is rejected |
| LOGIN-004 | Login | Negative | Empty username is rejected |
| LOGIN-005 | Login | Negative | Empty password is rejected |
| CART-001 | Add to cart | Positive | Adding a backpack updates the badge and cart |
| CART-002 | Add to cart | Positive | Adding two products updates badge and cart |
| CART-003 | Remove from cart | Negative / state reversal | Removing the backpack empties cart |
| CART-004 | Empty cart | Negative / empty state | Fresh cart has no products or badge |
| CART-005 | Duplicate prevention | Negative | Added product switches to Remove; one line item remains |

All five cart scenarios perform a **fresh standard-user login** before interacting with products. Each browser test uses a new Playwright page. Test names carry stable requirement IDs and, when published, TestRail case IDs.

## Architecture

```text
Ten reviewed login and cart requirements
           |
OpenAI or deterministic mock generates structured titles and step plans
           |
Strict action/schema validation
           |
generated_tests/login.spec.ts + generated_tests/cart.spec.ts
           |
BrowserStack Playwright (Windows 11 Chrome)
           |
Playwright JSON -> TestRail automated run/results
                       |
              reproducible assertion failures
                       |
              Jira Bug candidates (needs-triage)
```

The LLM is **not allowed to execute arbitrary code**. It must preserve accepted step sequences and may propose readable test titles. The code compiler maps only predefined actions from `test_generation/login.py` and `test_generation/cart.py`.

## Quick start

Requires Python 3.12+, Node.js 22+, and Playwright Chromium for local execution.

```bash
npm install
npx playwright install chromium
python -m test_generation.runner generate --provider mock
npx playwright test
python -m unittest discover -s tests -v
```

For real LLM generation, configure `OPENAI_API_KEY` and use `python -m test_generation.runner generate --provider openai`.

For BrowserStack execution, configure `BROWSERSTACK_USERNAME` and `BROWSERSTACK_ACCESS_KEY` and run `npm run test:browserstack`.

## GitHub Actions integration

[Run the BrowserStack → TestRail → Jira workflow](https://github.com/aditya42/prompt-engineered-testgen/actions/workflows/test-generation.yml).

- **`preview`** generates ten plans and Playwright specs without writing to TestRail or Jira.
- **`full-demo`** publishes/reuses ten test cases, creates a TestRail run, runs Playwright on BrowserStack, synchronizes results and triages eligible failures for Jira.
- **`known-defect-demo`** (provider **`mock`** only) runs the ten standard cases plus one opt-in `DEMO-001` against SauceDemo's intentionally broken `problem_user` account. If the add-to-cart failure repeats, it publishes the failed TestRail result and creates/reuses an **actual Jira Bug record labeled `known-training-defect` and `synthetic-demo`**. It is a reproduction of a pre-existing training defect, not a newly discovered production defect.
- Choose provider `mock` for deterministic checks or `openai` for real LLM case-generation API calls.

Secrets required: `BROWSERSTACK_USERNAME`, `BROWSERSTACK_ACCESS_KEY`, `TESTRAIL_EMAIL`, `TESTRAIL_API_KEY`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, plus `OPENAI_API_KEY` for LLM generation.

## Genuine defects versus synthetic failures

This repository does **not** deliberately break SauceDemo and label the outcome a genuine production defect. SauceDemo is a public third-party demonstration site; the account `problem_user` has intentionally problematic training behavior. A test against that account can show a **known demonstration fault**, not establish a newly discovered production defect.

The standard-user regression tests can reveal **actual observed failures**. The Jira automation marks these as `needs-triage` candidates only if both the first attempt and retry fail with application assertion evidence and no recognized infrastructure failure. A human must inspect traces, product behavior and expected requirements before confirming a genuine defect.

No Jira Bug is automatically filed solely because an assertion was artificially made wrong. TestRail records Passed, Failed or Retest independently of Jira triage. Failures still fail the CI quality gate.

## Validating product failure and Jira creation

For a demonstration backed by **observed website behavior**, select **`known-defect-demo`** with **provider `mock`**. This adds:

- `DEMO-001`: Log in with public `problem_user` credentials, attempt to add the Sauce Labs Fleece Jacket, and verify the cart badge increments to `1`.
- SauceDemo's `problem_user` account is intentionally broken; public reports describe this add-to-cart action as nonfunctional. The test does not inject an incorrect assertion.
- If both BrowserStack attempts fail with application-assertion evidence, the automated TestRail result is **Failed**, and Jira receives a deduplicated **known training defect** issue, not a claimed new production bug.
- A special quality gate considers the demonstration successful only if **all ten baseline tests pass** and `DEMO-001` fails as expected. If the demo behavior changes or the baseline fails, the workflow reports failure.

No Jira ticket exists for this new demonstration until the workflow actually runs successfully. The ordinary `full-demo` mode continues to file only **candidate** genuine bugs for unexpected, repeatable failures that require human triage.

## TestRail run naming

TestRail run titles are intentionally human-readable, for example:

`SauceDemo | Login + Cart Regression | BrowserStack (Chrome / Windows 11)`

The **GitHub run number is not included in the TestRail run title**. To preserve traceability and prevent duplicate runs when the same GitHub job is retried, the GitHub Actions run ID is stored in the TestRail **description** instead.

Existing TestRail R9 can be renamed using the one-time [rename R9 workflow](https://github.com/aditya42/prompt-engineered-testgen/actions/workflows/rename-testrail-r9.yml); changing the code does not rename historical runs automatically.

## TestRail history retention

The connected workflow maintains your requested limit of the **latest three test runs in TestRail project 1** and **permanently deletes older runs in that project**, including unrelated project runs. Test cases and Jira issues are not deleted. Export historical evidence before a connected run.

## Repository

- `test_generation/login.py` — five login scenarios
- `test_generation/cart.py` — five post-login cart scenarios
- `test_generation/runner.py` — test-case generation, TestRail/Jira synchronization, CLI
- `test_generation/failure_triage.py` — repeat-failure qualification
- `tests/test_runner.py` — isolated regression tests
- `browserstack.yml` — cloud browser configuration
- `docs/ARCHITECTURE.md`, `docs/INTEGRATION_GUIDE.md` — implementation and operations

## Validation

The original five login flows were verified on BrowserStack and synchronized to TestRail in [run 41327291819](https://github.com/aditya42/prompt-engineered-testgen/actions/runs/41327291819). The new five cart cases need their own completed CI/browser execution before being described as verified. See the [quality checks](https://github.com/aditya42/prompt-engineered-testgen/actions/workflows/code-quality.yml).

Coding follows PEP 8 and favors KISS, DRY, YAGNI, separation of concerns, and avoiding speculative infrastructure.
