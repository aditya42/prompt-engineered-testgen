"""Opt-in reproduction of a known SauceDemo training defect.

SauceDemo's problem_user account intentionally includes malfunctioning
shopping-cart behavior. This is NOT a newly discovered production defect.
"""

import json
from pathlib import Path


REQUIREMENTS = [{
    "id": "DEMO-001",
    "intent": "known_problem_user_add_to_cart_failure",
    "goal": "Known demo defect: problem_user cannot add Fleece Jacket to cart.",
    "steps": ["login_problem_user", "add_fleece_jacket", "assert_badge_one"],
}]


def mock_cases():
    item = REQUIREMENTS[0]
    return [{"id": item["id"], "intent": item["intent"],
             "title": item["goal"], "steps": item["steps"][:]}]


def validate_cases(cases):
    if (not isinstance(cases, list) or len(cases) != 1
            or not isinstance(cases[0], dict)
            or any(cases[0].get(field) != REQUIREMENTS[0][field]
                   for field in ("id", "intent", "steps"))
            or not isinstance(cases[0].get("title"), str)
            or not 8 <= len(cases[0]["title"]) <= 160):
        raise RuntimeError("Known demo-defect case failed validation")
    return cases


def compile_playwright(cases, mapping, root):
    """Check actual demo behavior; do not inject a deliberately wrong expected value."""
    validate_cases(cases)
    item = cases[0]
    prefix = f"[TR:C{mapping[item['id']}]" if item["id"] in mapping else ""
    title = f"{prefix} [DEMO-001] {item['title']}".strip()
    statements = [
        "await page.goto('/');",
        """await page.locator('[data-test="username"]').fill('problem_user');""",
        """await page.locator('[data-test="password"]').fill('secret_sauce');""",
        """await page.locator('[data-test="login-button"]').click();""",
        r"await expect(page).toHaveURL(/\/inventory\.html$/);",
        """await page.locator('[data-test="add-to-cart-sauce-labs-fleece-jacket"]').click();""",
        """await expect(page.locator('[data-test="shopping-cart-badge"]')).toHaveText('1');""",
    ]
    output = ["import { test, expect } from '@playwright/test';",
              f"test({json.dumps(title)}, async ({{ page }}) => {{",
              *("  " + line for line in statements), "});"]
    path = Path(root) / "generated_tests" / "known_defect.spec.ts"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")
