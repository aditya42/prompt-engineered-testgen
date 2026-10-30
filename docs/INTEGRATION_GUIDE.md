# SauceDemo Login — connected execution guide

## Application under test

- Website: https://www.saucedemo.com/
- Public demo users: `standard_user` and `locked_out_user`
- Public demo password: `secret_sauce`
- Login locators: `[data-test="username"]`, `[data-test="password"]`, `[data-test="login-button"]` and `[data-test="error"]`

## Test generation

`python -m test_generation.runner generate --provider mock` generates five deterministic login cases. `--provider openai` requests structured plans from OpenAI, then validates them against the same acceptance contract before Playwright compilation.

## Manual GitHub Actions workflow

- `preview` generates the login test plans and test spec without remote writes.
- `full-demo` reconciles TestRail LOGIN-001 through LOGIN-005, creates a run, executes five tests on SauceDemo, and synchronizes pass/fail.
- `jira-demo` intentionally fails LOGIN-001 and creates/reuses a *synthetic* Jira Bug. This does not indicate a real product defect.

Required GitHub secrets are `TESTRAIL_EMAIL`, `TESTRAIL_API_KEY`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, and `OPENAI_API_KEY` for the OpenAI provider. The configured demo destinations are TestRail project 1/section 1 and Jira project KAN.

The old subscription case SUB-001 remains in TestRail but is not mapped to new SauceDemo test runs.

## Retention caution

The live workflow permanently deletes all but the latest **three** TestRail runs in project 1, even runs originating elsewhere. It does not delete TestRail test cases or Jira issues. Before triggering a connected run, export important historical results. Review deletion candidates with `TESTRAIL_RETENTION_SCOPE=project python -m test_generation.runner prune-runs`.

Previous live TestRail/Jira runs demonstrated the former subscription scenario. Validate the new SauceDemo integration using a new manual run before claiming its connected test management flow is proven.
