# System architecture

## Workflow

```text
Synthetic requirement (SUB-001)
        │
        ▼
test_generation/runner.py — generate and validate an allowed action plan
        │
        ├── TestRail: reconcile case C1 or publish a case
        │
        ▼
generated_tests/subscription.spec.ts
        │
        ▼
Playwright ──► sample_app/ ──► JSON results
        │
        ├── TestRail: synchronize pass/fail
        ├── Jira: optionally create/reuse a synthetic Bug
        └── GitHub Actions: report execution and retain three runs
```

## Design boundaries

- `test_generation/`: Python CLI and external integration logic.
- `sample_app/`: isolated fictional subscription UI.
- `tests/`: unit tests with mocked API behavior.
- `generated_tests/`, `reports/` and `state/`: runtime outputs not committed.
- `.github/workflows/`: orchestration and access verification.

The runner intentionally remains a small, dependency-light orchestration
module rather than introducing a service layer or dependency injection framework
for a single synthetic scenario. Complexity should be introduced only when
multiple scenarios require it.

## Safety

The `preview` mode performs no remote writes. The `jira-demo` mode is
explicitly selected and marks defects as synthetic. The live workflow
permanently deletes older runs in TestRail project 1, keeping the newest three.
Test cases and Jira issues are not deleted.
