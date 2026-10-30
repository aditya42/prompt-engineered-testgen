"""SauceDemo login acceptance criteria and safe Playwright action compiler."""

import json
import os
from pathlib import Path

REQUIREMENTS = [
    {"id": "LOGIN-001", "intent": "valid_login",
     "goal": "A standard user can sign in and reach inventory.",
     "steps": ["open_login", "standard_username", "valid_password", "submit", "inventory"]},
    {"id": "LOGIN-002", "intent": "invalid_password",
     "goal": "An incorrect password is rejected.",
     "steps": ["open_login", "standard_username", "wrong_password", "submit", "invalid_error"]},
    {"id": "LOGIN-003", "intent": "locked_account",
     "goal": "A locked-out user cannot sign in.",
     "steps": ["open_login", "locked_username", "valid_password", "submit", "locked_error"]},
    {"id": "LOGIN-004", "intent": "missing_username",
     "goal": "A missing username shows a validation error.",
     "steps": ["open_login", "valid_password", "submit", "username_error"]},
    {"id": "LOGIN-005", "intent": "missing_password",
     "goal": "A missing password shows a validation error.",
     "steps": ["open_login", "standard_username", "submit", "password_error"]},
]

ACTIONS = {
    "open_login": "await page.goto('/');",
    "standard_username": """await page.locator('[data-test="username"]').fill('standard_user');""",
    "locked_username": """await page.locator('[data-test="username"]').fill('locked_out_user');""",
    "valid_password": """await page.locator('[data-test="password"]').fill('secret_sauce');""",
    "wrong_password": """await page.locator('[data-test="password"]').fill('wrong_password');""",
    "submit": """await page.locator('[data-test="login-button"]').click();""",
    "inventory": r"await expect(page).toHaveURL(/\/inventory\.html$/);",
    "invalid_error": (
        """await expect(page.locator('[data-test="error"]'))"""
        ".toContainText('Username and password do not match');"
    ),
    "locked_error": (
        """await expect(page.locator('[data-test="error"]'))"""
        ".toContainText('Sorry, this user has been locked out.');"
    ),
    "username_error": (
        """await expect(page.locator('[data-test="error"]'))"""
        ".toContainText('Username is required');"
    ),
    "password_error": (
        """await expect(page.locator('[data-test="error"]'))"""
        ".toContainText('Password is required');"
    ),
}


def mock_cases():
    """Deterministic, realistic baseline for offline test runs."""
    return [
        {"id": requirement["id"], "intent": requirement["intent"],
         "title": requirement["goal"], "steps": requirement["steps"][:]}
        for requirement in REQUIREMENTS
    ]


def validate_cases(cases):
    """Reject hallucinated actions, incomplete coverage and scenario mismatches."""
    expected = {item["id"]: item for item in REQUIREMENTS}
    if (not isinstance(cases, list) or len(cases) != len(expected)
            or any(not isinstance(case, dict) for case in cases)
            or {case.get("id") for case in cases} != set(expected)):
        raise RuntimeError("Generated login cases have incomplete or duplicate coverage")
    for case in cases:
        requirement = expected[case["id"]]
        if (case.get("intent") != requirement["intent"]
                or case.get("steps") != requirement["steps"]
                or not isinstance(case.get("title"), str)
                or not 8 <= len(case["title"]) <= 160):
            raise RuntimeError("Generated login case failed safety validation")
    return cases


def compile_playwright(cases, mapping, root):
    """Compile only approved actions; the LLM never supplies executable code."""
    validate_cases(cases)
    lines = ["import { test, expect } from '@playwright/test';"]
    for case in cases:
        cid = mapping.get(case["id"])
        title = (f"[TR:C{cid}] " if cid else "") + f"[{case['id']}] {case['title']}"
        lines.append(f"test({json.dumps(title)}, async ({{ page }}) => {{")
        for action in case["steps"]:
            statement = ACTIONS[action]
            if (os.getenv("DEMO_INJECT_FAILURE") == "true"
                    and case["id"] == "LOGIN-001" and action == "inventory"):
                statement = "await expect(page).toHaveURL(/intentional-demo-failure/);"
            lines.append("  " + statement)
        lines.append("});")
    target = Path(root) / "generated_tests" / "login.spec.ts"
    target.parent.mkdir(exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
