# Prompt-Engineered Test Generation Framework

A portfolio framework for prompt-engineered test generation, TestRail test management, Playwright execution, and Jira defect synchronization, using synthetic streaming subscription scenarios.

## Getting started

The repository is being initialized with a safe, read-only TestRail/Jira connection-verification workflow. The full Python/Playwright project is packaged separately for upload.

### Configure GitHub Actions secrets

In **Settings → Secrets and variables → Actions**, create the following repository secrets:

- `TESTRAIL_EMAIL`
- `TESTRAIL_API_KEY`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`

Then open **Actions → Verify TestRail and Jira connections → Run workflow**. The workflow only performs GET requests; it cannot create test cases or bugs.

Instance metadata: TestRail `https://testrailspersonal.testrail.io`, project `1`, section `1`; Jira `https://dhendeaditya510.atlassian.net`, project `KAN`.

Never commit `.env` files or access tokens.
