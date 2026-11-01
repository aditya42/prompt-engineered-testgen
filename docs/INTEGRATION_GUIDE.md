# BrowserStack, TestRail and Jira integration guide

## 1. BrowserStack setup

Create or use a BrowserStack Automate account. Under GitHub repository **Settings → Secrets and variables → Actions**, configure:

- `BROWSERSTACK_USERNAME`
- `BROWSERSTACK_ACCESS_KEY`

The BrowserStack Node SDK uses these environment variables. The checked-in `browserstack.yml` contains **placeholders only** and declares a Windows 11 Chrome run with BrowserStack reporting enabled. The workflow executes:

```bash
npm install
npx browserstack-node-sdk playwright test
```

Use the [BrowserStack Playwright Node SDK guide](https://www.browserstack.com/docs/automate/playwright/getting-started/nodejs/integrate-your-tests) to locate credential and dashboard settings.

## 2. TestRail

Secrets: `TESTRAIL_EMAIL`, `TESTRAIL_API_KEY`. Configured project `1`, section `1`; optional `TESTRAIL_SUITE_ID` Actions variable.

The workflow publishes/reconciles LOGIN-001 through LOGIN-005 and CART-001 through CART-005, starts a TestRail run, then submits a linked result for every Playwright test found in the JSON report. The old subscription scenario remains a TestRail case but is excluded from new login runs.

**Destructive retention:** the live workflow permanently deletes *all* TestRail project-1 runs older than the newest three. This includes unrelated runs. TestRail test cases are preserved. Export historical results before running.

## 3. Jira

Secrets: `JIRA_EMAIL`, `JIRA_API_TOKEN`; configured Jira project `KAN`.

A candidate is eligible for automatic Jira Bug creation only after Playwright attempts the test twice, both attempts fail, recognized assertion evidence is present and no infrastructure-related error is seen. The created ticket is tagged `automated-qa`, `browserstack`, `needs-triage` and a stable per-TestRail-case label to avoid duplicate issues. A team member must verify the root cause and close non-product issues.

A single failure, passing retry, timeout, BrowserStack outage or absent JSON report does not produce a Jira ticket. TestRail still records linked results when available. The final quality gate makes failing/flaky execution visible to stakeholders even when a Jira issue was not created.

## 4. GitHub Actions

Use [BrowserStack Playwright - TestRail and Jira](https://github.com/aditya42/prompt-engineered-testgen/actions/workflows/test-generation.yml).

- `preview`: generates case plans only (does not modify TestRail/Jira)
- `full-demo`: requires BrowserStack, TestRail, Jira, and (if selected) OpenAI credentials; runs end to end

Use `provider=mock` for deterministic validation, `provider=openai` for real structured case generation. `preview` still verifies read access to external integrations.

The quality workflow `.github/workflows/code-quality.yml` continues to use local Playwright for no-credential pull-request smoke testing; this does not replace BrowserStack live execution.

## 5. Validation

Offline unit tests, lint and local browser smoke checks are automatic. Live BrowserStack execution and Jira behavior need a credentialed manual run; no successful remote session is claimed until confirmed.

## Add-to-cart and known training-defect test

The default regression suite contains five login scenarios and five post-login cart scenarios. Cart tests cover single/multiple item addition, removal, empty state, and duplicate prevention. The action compiler lives in `test_generation/cart.py`.

The separate `known-defect-demo` manual workflow option (provider `mock` only) includes `DEMO-001`, which logs in as SauceDemo's publicly documented intentionally defective `problem_user`, attempts to add the Sauce Labs Fleece Jacket and verifies the cart badge. If this known fault reproduces twice with assertion evidence, it is published as a Failed TestRail result and a Jira Bug **labeled `known-training-defect` and `synthetic-demo`**. It is a real execution of a known demo defect, not proof of a newly discovered production bug.

The training workflow's quality gate expects ten baseline passes plus one failing demo. For ordinary `full-demo` runs, unexpected repeated assertion failures are filed only as `needs-triage` Jira candidates. The absence of a defect cannot be simulated as a genuine bug by intentionally changing assertions.
