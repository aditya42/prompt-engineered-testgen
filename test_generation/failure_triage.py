"""Conservative triage of Playwright failures before automatic Jira creation.

A repeated assertion failure is eligible for review or automatic filing, but
cannot prove a product defect by itself. Infrastructure failures are excluded.
"""

import re

INFRASTRUCTURE_PATTERNS = (
    "net::err_", "econnreset", "enotfound", "econnrefused",
    "browser has been closed", "target page, context or browser has been closed",
    "browserstack", "connection timed out", "page.goto: timeout",
    "test timeout", "timed out after", "navigation timeout",
)

ASSERTION_PATTERNS = (
    "expect(", "assertionerror", "tohavetext", "tohaveurl",
    "tocontaintext", "tobevisible",
)


def classify_failure(test):
    """Return (eligible, reason) for reproducible assertion failures.

    Eligibility requires a Playwright unexpected test and at least two failed
    execution attempts. A passed retry is not eligible. These checks are
    intentionally restrictive to minimize false-positive Jira tickets.
    """
    if test.get("status") != "unexpected":
        return False, "not an unexpected failure"
    attempts = test.get("results") or []
    if len(attempts) < 2:
        return False, "insufficient retry evidence"
    if any(attempt.get("status") != "failed" for attempt in attempts):
        return False, "not reproducible across retries"
    for attempt in attempts:
        err = attempt.get("error") or {}
        message = str(err.get("message", "")) if isinstance(err, dict) else str(err)
        message = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", message).lower()
        if any(pattern in message for pattern in INFRASTRUCTURE_PATTERNS):
            return False, "possible infrastructure or timeout failure"
        if not any(pattern in message for pattern in ASSERTION_PATTERNS):
            return False, "no recognizable assertion evidence"
    return True, "repeated application assertion failure"
