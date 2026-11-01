# Architecture: BrowserStack execution and quality integrations

```text
OpenAI-generated, validated login case plans
   -> safe Playwright action compiler
   -> generated_tests/login.spec.ts
   -> BrowserStack Node SDK (cloud Chrome)
   -> Playwright JSON report
      |-> TestRail result synchronization
      |-> repeat-failure triage -> Jira Bug candidate
      |-> GitHub Actions summary + retention
```

BrowserStack hosts the browser, while SauceDemo remains the example application under test.

## Responsibilities

- `test_generation/login.py`: bounded login requirements and approved Playwright commands.
- `test_generation/runner.py`: generation, TestRail/Jira APIs, run management, reporting and quality gate.
- `test_generation/failure_triage.py`: excludes flaky, infrastructure and non-reproducible failures from automatic Jira filing.
- `browserstack.yml`: browser platform and BrowserStack build settings.
- `playwright.config.ts`: Playwright JSON reporter, evidence attachments, CI retry.
- `tests/`: offline regression tests; no BrowserStack or Jira credentials required.
- `.github/workflows/test-generation.yml`: manual live integration.
- `.github/workflows/code-quality.yml`: lightweight local browser and unit-test CI.

## Operational design

BrowserStack credentials come from GitHub Actions Secrets, not source files. An OpenAI-backed or deterministic provider generates the test plans. The model cannot execute arbitrary code. TestRail case reconciliation uses stable requirement identifiers.

The `full-demo` workflow verifies BrowserStack credentials before creating a TestRail run. It executes remotely, syncs the results, optionally creates Jira Bug *candidates* for repeated assertion failures and then fails CI if anything remains failed, flaky or missing. The reporter and TestRail run IDs are captured in GitHub Actions artifacts.

Jira classification is intentionally conservative. Two identical failing outcomes plus assertion evidence is not proof of a product defect; created Jira tickets are labeled `needs-triage` and require human review. Infrastructure/network failures are excluded from automatic tickets.

The existing live TestRail cleanup keeps the newest three execution runs in project 1, permanently removing older runs in that project, including unrelated runs. It does not remove test cases or Jira issues.

## Add-to-cart and known training-defect test

The default regression suite contains five login scenarios and five post-login cart scenarios. Cart tests cover single/multiple item addition, removal, empty state, and duplicate prevention. The action compiler lives in `test_generation/cart.py`.

The separate `known-defect-demo` manual workflow option (provider `mock` only) includes `DEMO-001`, which logs in as SauceDemo's publicly documented intentionally defective `problem_user`, attempts to add the Sauce Labs Fleece Jacket and verifies the cart badge. If this known fault reproduces twice with assertion evidence, it is published as a Failed TestRail result and a Jira Bug **labeled `known-training-defect` and `synthetic-demo`**. It is a real execution of a known demo defect, not proof of a newly discovered production bug.

The training workflow's quality gate expects ten baseline passes plus one failing demo. For ordinary `full-demo` runs, unexpected repeated assertion failures are filed only as `needs-triage` Jira candidates. The absence of a defect cannot be simulated as a genuine bug by intentionally changing assertions.
