# Phase 2 - controlled synthetic test generation and TestRail/Jira integration

Use Actions > Phase 2 - Controlled TestRail and Playwright Demo and first select `preview` (no writes). Select `full-demo` only once after confirming the preview, to publish one sample TestRail test case, create a dedicated run, execute Playwright, and upload the result. Jira issue creation is implemented as an explicit opt-in CLI command (`python -m phase2.runner sync --apply --create-bugs`) but NOT enabled in GitHub Actions; do not enable it until defect triage and deduplication are verified. For real generation add `OPENAI_API_KEY` GitHub Secret and select provider `openai`; mock mode is deterministic and does not demonstrate LLM improvements.

**Important:** The workflow saves mapping and run ID in a per-run artifact only. Re-running `full-demo` independently can create duplicate TestRail cases/runs. Add durable storage/idempotency before recurring scheduling. This is a controlled demonstration, not a production integration.

If TestRail rejects case fields, inspect custom-case template configuration. A multi-suite project may require repository variable `TESTRAIL_SUITE_ID`. No credentials are committed.
