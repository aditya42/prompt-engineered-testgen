# Prompt-Engineered Test Generation

**From a written requirement to an executable Playwright test, with TestRail and Jira traceability.**

This open-source quality-engineering demonstration uses Python and OpenAI to turn a structured subscription requirement into validated test steps. It then generates a Playwright test, executes it against a fictional **StreamBox** application, and records the outcome in TestRail. An opt-in negative-test mode demonstrates synthetic Jira defect creation.

> **Scope:** StreamBox, its user accounts, and the test data are fictional. This repository does not include Prime Video/Amazon internal source code, credentials, or customer data.

## How it works

```text
Structured requirement: SUB-001
        │
        ▼
OpenAI or deterministic mock
        │
        ▼
Schema checks + allowed-action validation
        │
        ▼
Generate a Playwright test ──► StreamBox sample app
        │                                │
        │                         Playwright JSON
        ▼                                │
TestRail case (deduplicated) ◄───────────┘
        │
        ├── Execution result: pass / fail
        └── Optional Jira Bug (explicit synthetic failure only)

GitHub Actions: links + result summary + TestRail run retention
```

The generator maps a small **allowlist of known actions** to Playwright commands. It does not execute unrestricted code returned by a language model.

## What is implemented

| Capability | Implementation |
| --- | --- |
| Requirement traceability | Stable `SUB-001` requirement ID and `[TR:C<ID>]` Playwright marker |
| AI-assisted generation | OpenAI Chat Completions or a deterministic mock |
| Output validation | Requirement coverage, intent, allowed steps, required first/last steps |
| Test execution | Playwright + TypeScript against the local sample UI |
| Test management | TestRail case reconciliation, execution run and pass/fail synchronization |
| Defect demonstration | Intentional failure; create/reuse labeled **synthetic** Jira Bug |
| CI reporting | GitHub Actions summary, downloadable JSON and mapping artifacts |
| Run retention | Keep the newest **three execution runs** in the configured TestRail project |

## Repository structure

```text
prompt-engineered-testgen/
├── .github/
│   └── workflows/
│       ├── test-generation.yml       # Manual end-to-end demonstration
│       └── verify-integrations.yml   # Read-only external API verification
├── docs/
│   ├── ARCHITECTURE.md               # Components and design decisions
│   └── INTEGRATION_GUIDE.md          # TestRail/Jira setup and operations
├── sample_app/
│   ├── index.html                    # Synthetic subscription page
│   └── server.cjs                    # Local HTTP server
├── test_generation/
│   ├── __init__.py
│   └── runner.py                     # Generation + integration CLI
├── tests/
│   └── test_runner.py               # Offline, mocked regression tests
├── playwright.config.ts
├── package.json
├── pyproject.toml
├── CONTRIBUTING.md
└── README.md
```

The following directories are created during execution and **not committed**:

| Runtime directory | Contents |
| --- | --- |
| `generated_tests/` | Generated Playwright `.spec.ts` files |
| `reports/` | Playwright execution JSON |
| `state/` | TestRail case/run mappings, result ledger, retention status and summary |

## Quick start — no API keys required

**Prerequisites:** Python 3.12+, Node.js 22+, npm and Chromium for Playwright.

```bash
git clone https://github.com/aditya42/prompt-engineered-testgen.git
cd prompt-engineered-testgen

npm install
npx playwright install chromium

# Generate from a deterministic fixture
python -m test_generation.runner generate --provider mock

# Playwright automatically starts the local StreamBox sample app
npx playwright test

# Run mocked Python tests without external connections
python -m unittest discover -s tests -v
```

A successful local execution should produce one generated subscription test and a JSON report in `reports/`.

## Run the connected demonstration in GitHub Actions

Open [Synthetic Test Generation](https://github.com/aditya42/prompt-engineered-testgen/actions/workflows/test-generation.yml), select **Run workflow**, and choose:

| Action | Provider | External side effects |
| --- | --- | --- |
| `preview` | `mock` or `openai` | No TestRail/Jira writes |
| `full-demo` | `mock` or `openai` | Creates/reuses a TestRail case, executes Playwright, syncs a result |
| `jira-demo` | `mock` recommended | Deliberately fails the test, syncs the failure and creates/reuses a synthetic Jira Bug |

**Use `preview` first.** `jira-demo` intentionally creates a *real Jira record* clearly marked as a synthetic demonstration. It must not be presented as a production defect.

The workflow provides a GitHub Actions execution summary with TestRail links, Playwright counts, any Jira issue key, and deleted TestRail run IDs.

### Required GitHub secrets

Configure secrets at **Settings → Secrets and variables → Actions**:

| Secret | Purpose |
| --- | --- |
| `TESTRAIL_EMAIL` | TestRail username |
| `TESTRAIL_API_KEY` | TestRail API key |
| `JIRA_EMAIL` | Atlassian account username |
| `JIRA_API_TOKEN` | Jira API token |
| `OPENAI_API_KEY` | Only required when using the `openai` provider |

The demonstration workflow is currently configured for TestRail project `1`, section `1`, and Jira project `KAN`. The optional `TESTRAIL_SUITE_ID` Actions variable supports multi-suite TestRail projects. See the [integration guide](docs/INTEGRATION_GUIDE.md) for operational details.

## TestRail retention: important destructive behavior

After any connected `full-demo` or `jira-demo` workflow, **only the newest three test runs in TestRail project `1` are retained**. The workflow permanently deletes every older run in that project, **including runs from other workflows**. It does not delete test cases, Jira issues or runs in other projects.

To preview proposed deletions without changing TestRail (after configuring API environment variables):

```bash
TESTRAIL_RETENTION_SCOPE=project python -m test_generation.runner prune-runs
```

The standalone CLI defaults to a narrower `managed` retention scope; GitHub Actions explicitly sets `TESTRAIL_RETENTION_SCOPE=project`. Export historical results before executing the live workflow. Deletion is not reversible through this project.

## Verified integration evidence

| Demonstration | GitHub Actions evidence |
| --- | --- |
| Live OpenAI generation and passing Playwright execution | [Run 41034247358](https://github.com/aditya42/prompt-engineered-testgen/actions/runs/41034247358) |
| Cross-run TestRail case reuse | [Run 41035590823](https://github.com/aditya42/prompt-engineered-testgen/actions/runs/41035590823) |
| Intentional failure → TestRail → synthetic Jira Bug | [Run 41037773572](https://github.com/aditya42/prompt-engineered-testgen/actions/runs/41037773572) |
| Three-run TestRail retention and execution summary | [Run 41039303473](https://github.com/aditya42/prompt-engineered-testgen/actions/runs/41039303473) |

These demonstrate the integrations for **one synthetic subscription scenario**. They are not a benchmark of AI-generated test quality, nor evidence of performance on a real production application. After the directory refactor, a new run is required to reconfirm CI compatibility.

## Engineering principles

The project favors **KISS, DRY, YAGNI, separation of concerns and no premature optimization**. It intentionally avoids a database, queue or agent framework for a one-scenario example. Python naming conventions and style are guided by [PEP 8](https://peps.python.org/pep-0008/).

For implementation details, see [architecture](docs/ARCHITECTURE.md). For contributions and local checks, see [CONTRIBUTING.md](CONTRIBUTING.md).
