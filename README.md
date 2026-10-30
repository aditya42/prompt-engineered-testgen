# Prompt-Engineered Test Generation Framework

A reproducible **GenAI quality-engineering portfolio project** that converts structured streaming-subscription requirements into validated Playwright tests and connects their execution lifecycle to **TestRail** and **Jira Cloud**.

The application under test, **StreamBox**, is fictional; all scenarios and test data are synthetic. This project is inspired by common streaming subscription QA workflows and does **not** contain Amazon/Prime Video source code, customer information, or internal tooling.

## Architecture

```text
Synthetic subscription requirements (SUB-001)
           |
           v
Prompt strategy + OpenAI Chat Completions (or deterministic mock)
           |
           v
Structured JSON validation, requirement traceability, step allowlist
           |
           v
TestRail project 1, section 1 <--- existing-case reconciliation by [SUB-001]
           |
           v
Generated Playwright / TypeScript tests tagged [TR:C1]
           |
           v
StreamBox demo app -> Playwright JSON report
           |
           v
TestRail run + pass/fail result
           |
           +--> Explicit synthetic Jira demo on failure
                -> check existing Jira label -> create Bug in KAN if absent
```

## What this project demonstrates

- **Prompt engineering:** explicit output schema, allowed automation actions, stable requirement IDs, reference intent, JSON-only response, and output validation.
- **Safe test generation:** generated steps come from an allowlist translated into known Playwright commands. No free-form model-generated code is executed.
- **Traceability:** `SUB-001` → TestRail `C<ID>` → Playwright title `[TR:C<ID>]` → TestRail run/result → optional Jira issue.
- **Cross-run duplicate prevention:** on each live publish, the runner queries TestRail cases for the project and reconciles requirement markers such as `[SUB-001]`, rather than relying on ephemeral GitHub runner files.
- **Controlled Jira creation:** only the manually selected `jira-demo` workflow action enables issue creation. It intentionally fails a synthetic test, labels the issue `synthetic-demo`, and searches existing Jira issues by a stable case-specific label before creating another one.
- **CI evidence:** GitHub Actions uploads generated tests and mappings, and adds an execution summary with clickable TestRail and Jira links.
- **Three-run retention:** After live executions, older runs in TestRail project 1 are permanently deleted, preserving the latest three runs in that project; TestRail cases and other projects are unaffected.

### Validated versus unvalidated functionality

A previous live workflow generated one case using OpenAI, published **TestRail C1**, created **run R1**, executed Playwright successfully (1/1 passed), and synchronized the TestRail result. Read-only access to Jira project `KAN` was verified. Subsequent live workflows verified TestRail case reuse, Playwright failure synchronization, and Jira Bug create/reuse in [run 41037773572](https://github.com/aditya42/prompt-engineered-testgen/actions/runs/41037773572). **The newly added retention and Actions summary features require fresh CI validation.** Mock-provider runs are demonstrations, not measurements of LLM output quality.

## Repository layout

| Path | Purpose |
| --- | --- |
| `phase2/runner.py` | JSON-validated generation, TestRail case/run publishing, Playwright compilation, result sync, Jira demo |
| `demo/index.html` | Fictional subscription UI |
| `demo/server.cjs` | Local web server |
| `playwright.config.ts` | Playwright config, JSON results, and local demo web server |
| `.github/workflows/verify-integrations.yml` | Read-only API authentication and project access checks |
| `.github/workflows/phase2.yml` | Manual preview, live case execution, or synthetic Jira defect demo |
| `PHASE2.md` | Additional integration notes |
| `state/`, `generated/`, `reports/` | Runtime artifacts (excluded from Git) |

## Configure GitHub Actions

In the repository go to **Settings → Secrets and variables → Actions** and create the encrypted repository secrets:

| Secret | Description |
| --- | --- |
| `TESTRAIL_EMAIL` | TestRail API account email |
| `TESTRAIL_API_KEY` | Dedicated TestRail API key |
| `JIRA_EMAIL` | Atlassian account email |
| `JIRA_API_TOKEN` | Jira Cloud API token |
| `OPENAI_API_KEY` | Optional; needed only for real OpenAI generation |

The GitHub workflow currently targets these **demo-only** instance settings:

- TestRail: `https://testrailspersonal.testrail.io`, project `1`, section `1` (`UserInterface`)
- Jira: `https://dhendeaditya510.atlassian.net`, project key `KAN`, issue type `Bug`
- For a TestRail multi-suite project, define optional GitHub Actions variable `TESTRAIL_SUITE_ID`.

Do not put API tokens in the README, source code, workflow YAML, public issue comments, or screenshots. The `.gitignore` excludes local `.env` credentials.

## Run from GitHub Actions

Open **Actions → Phase 2 - Controlled TestRail and Playwright Demo → Run workflow**.

| Action | Provider | Writes |
| --- | --- | --- |
| `preview` | `mock` (default) or `openai` | No TestRail/Jira changes |
| `full-demo` | `mock` or `openai` | Reuse/create TestRail case, create a run, execute Playwright, send result |
| `jira-demo` | `mock` recommended | Same as full-demo, but deliberately inject a failing assertion and create/reuse one clearly labeled synthetic Jira issue |

**Start with `preview`, then `full-demo`. Select `jira-demo` only if you explicitly approve creating a synthetic Bug in project `KAN`.** A synthetic failure is not a real product defect. Delete or close demo issues after reviewing them.

The workflow uses a concurrency group to avoid overlapping runs. It searches TestRail for existing requirement IDs on each live publish. The TestRail execution run is named using the GitHub run ID, allowing a distinct run per execution; local mapping files are not a durable database. The Jira issue search uses a persistent per-case label.

## TestRail run retention: latest three

Following each live `full-demo` or `jira-demo`, GitHub Actions uses **`TESTRAIL_RETENTION_SCOPE=project`** to retain the newest **three test runs in TestRail project `1`** by run ID. **All older runs in that project are permanently deleted, regardless of their names or which workflow created them.** TestRail test cases, Jira issues, and runs in other TestRail projects are not deleted.

Cleanup is attempted after the execution even when the Playwright or Jira step fails. Before deleting each run, the workflow verifies the run belongs to project 1, sends TestRail's explicit deletion payload, and records successful deletions individually. If deletion fails partway through, the artifact records the IDs already removed and the failed run ID. It checks the current run is in the newest three before deleting older runs. Download any historical execution evidence first; this project provides no rollback for deleted TestRail runs.

With the same environment variable, preview the exact run IDs that would be removed:

```bash
TESTRAIL_RETENTION_SCOPE=project python3 -m phase2.runner prune-runs
```

To apply the deletion explicitly outside GitHub Actions:

```bash
TESTRAIL_RETENTION_SCOPE=project python3 -m phase2.runner prune-runs --apply
```

The default CLI scope without this environment variable is `managed` and deletes only older PromptTestGen-managed runs. The GitHub Actions workflow deliberately uses the broader `project` scope to enforce the requested maximum of three visible runs for project `1`.

## GitHub Actions execution summary

Every workflow produces a **Summary** section showing Playwright pass/fail counts, TestRail case and run links, the Jira issue key and link if created/reused, and the IDs of any deleted demo runs. The same report is stored as `state/summary.md` in the workflow artifact.

## Run locally

Requires Python 3.12+, Node.js 22+, and Playwright Chromium.

```bash
npm install
npx playwright install chromium

# Offline generation; writes local generated/ and state/
python3 -m phase2.runner generate --provider mock

# Execute the generated test against the synthetic app
npx playwright test
```

For a read-only account check, export the required environment variables locally and run:

```bash
python3 -m phase2.runner verify
```

Live publishing, run creation and synchronization require explicit `--apply`:

```bash
python3 -m phase2.runner publish --apply --provider mock
python3 -m phase2.runner create-run --apply
npx playwright test
python3 -m phase2.runner sync --apply
```

The local `--create-bugs` option is guarded by `DEMO_INJECT_FAILURE=true` and is intended for synthetic demonstrations only.

## How generated cases are evaluated

The current implementation validates **requirement ID coverage**, exact requirement intent, an **allowlisted step vocabulary**, and required opening/closing steps. These are deterministic quality gates, not a measured claim that prompt engineering improved productivity. For future benchmarking, compare prompt variants on human acceptance rate, valid generation rate, requirement coverage, runtime success, token usage, and elapsed test-authoring time with repeatable datasets.

## Operational constraints and next improvements

- The example has one synthetic subscription requirement, not a complete subscription/billing regression suite.
- TestRail test case templates differ; custom field names and suite selection may require configuration.
- Duplicate checking is based on exact requirement markers and case-specific Jira labels; it does not replace a transactional database or handle external concurrent modifications.
- Jira failures in the automated test may originate from test code/environment; real incident creation should include triage, reruns, and severity assessment before deployment to production.
- The explicit synthetic Jira demo is deliberately scoped to one case and must not be scheduled against production Jira.
- Tests and the GitHub pipeline are not proof of broad LLM benchmarking or real-world release-quality improvements until independently measured.

## Security

Only HTTPS API endpoints are permitted by the Python client. API secrets are supplied from GitHub Actions Secrets or local environment variables. The runner reports HTTP status failures without dumping response bodies or authorization headers. Actions use read-only repository permissions; external writes are controlled separately by workflow inputs.
