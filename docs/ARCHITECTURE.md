# SauceDemo login testing architecture

The application under test is the public [SauceDemo](https://www.saucedemo.com/) training site.

```text
LOGIN-001 ... LOGIN-005 acceptance criteria
  -> OpenAI or deterministic mock
  -> structured test plans
  -> login.py (scenario validation and allowlisted action compiler)
  -> generated_tests/login.spec.ts
  -> Playwright on SauceDemo
  -> TestRail results and optional synthetic Jira Bug
  -> GitHub Actions execution summary / retention
```

## Responsibility boundaries

- `test_generation/login.py` owns login acceptance requirements, test case validation, the deterministic fixture and the action compiler.
- `test_generation/runner.py` owns OpenAI requests, orchestration, TestRail/Jira API calls, result synchronization and run retention.
- `tests/test_runner.py` tests validation and side-effect guards without external credentials.
- `playwright.config.ts` targets the public site; `SAUCEDEMO_BASE_URL` can override it.
- `generated_tests/`, `reports/` and `state/` hold runtime artifacts and are excluded from Git.

## Design decisions

The LLM generates readable test case titles and plans, but cannot supply executable code. Each requested step sequence must match a reviewed scenario. Adding new login capabilities means extending the acceptance catalog and allowlisted action compiler, rather than permitting arbitrary model commands.

The `preview` workflow performs no external writes. The `jira-demo` mode intentionally fails the positive login case and creates/reuses a clearly labeled *synthetic* defect.

The existing TestRail run-retention rule permanently removes older runs, keeping only three in project 1; it does not remove cases.
