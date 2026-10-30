# Phase 2 implementation notes

The live success path was verified on GitHub Actions run 41034247358: OpenAI generated `SUB-001`, TestRail case `C1` and run `R1` were created, the generated Playwright test passed, and the result was synchronized to TestRail.

## Current workflow actions

- `preview`: run offline unit tests, verify API access and generate a case without external writes.
- `full-demo`: generate, reconcile existing cases by `[SUB-001]`, create a run, execute Playwright and synchronize TestRail results. It should reuse case `C1` rather than create another case.
- `jira-demo`: as above, but inject an intentionally wrong assertion and then attempt to create/reuse a **synthetic** Jira Bug in project `KAN` with `synthetic-demo` and `demo-autotest-tr-c1` labels. No production defect is implied.

All workflow actions are manual. Secrets stay in GitHub Actions. Tests under `tests/` use mocks and do not require live credentials.

**Important:** The new remote deduplication and Jira negative path still require first live validation; don't repeatedly run `jira-demo` until the first controlled result has been inspected. Cross-run deduplication is best-effort based on TestRail case titles and Jira labels, not a transactional guarantee. The `jira-demo` action writes a real synthetic Bug to the configured Jira project. Close/remove it after demonstration.

For the full setup and architecture, see [README.md](README.md).

## Execution evidence and retention

New live workflow runs publish a GitHub Actions **Summary** with linked TestRail case/run IDs, any Jira issue key and URL, Playwright counts, and retained/deleted TestRail run IDs. The workflow uses `TESTRAIL_RETENTION_SCOPE=project` and retains only the latest three TestRail runs in project `1`, permanently deleting **all older runs in that project**, including unrelated runs. Test cases, Jira issues, and runs in different TestRail projects are untouched. Use `TESTRAIL_RETENTION_SCOPE=project python -m phase2.runner prune-runs` to preview; add `--apply` to permanently delete. This new retention behavior requires validation by a fresh Actions run.
