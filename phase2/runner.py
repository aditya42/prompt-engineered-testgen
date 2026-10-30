"""Phase 2: controlled synthetic subscription test generation -> TestRail -> Playwright -> Jira."""
import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
STATE.mkdir(exist_ok=True)
REQUIREMENTS = [
    {"id": "SUB-001", "title": "Customer can purchase a basic subscription with a valid email",
     "intent": "successful_subscription", "steps": ["open_app", "enter_email", "subscribe", "assert_active"]},
]
ALLOWED = {"open_app", "enter_email", "subscribe", "assert_active"}

def api(url, email, secret, method="GET", body=None, bearer=False):
    if not url.startswith("https://"):
        raise RuntimeError("API URL must use HTTPS")
    token = ("Bearer " + secret) if bearer else "Basic " + base64.b64encode((email + ":" + secret).encode()).decode()
    headers = {"Authorization": token, "Accept": "application/json", "User-Agent": "prompt-testgen-phase2/1"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=headers, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        # No response bodies or authentication headers in logs
        raise RuntimeError(f"{method} request failed: HTTP {exc.code}") from None

def tr(path, method="GET", body=None):
    url = os.environ["TESTRAIL_URL"].rstrip("/") + "/index.php?/api/v2/" + path
    return api(url, os.environ["TESTRAIL_EMAIL"], os.environ["TESTRAIL_API_KEY"], method, body)

def jira(path, method="GET", body=None):
    url = os.environ["JIRA_URL"].rstrip("/") + "/rest/api/3/" + path
    return api(url, os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"], method, body)

def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")

def generate(provider):
    cases = REQUIREMENTS
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required for live LLM generation")
        prompt = ("Generate strictly valid JSON object with key cases containing one test case per "
                  "requirement, exactly the fields id,title,intent,steps. "
                  "Preserve IDs and intents. Steps MUST be chosen from this allowlist: "
                  + ", ".join(sorted(ALLOWED)) + ". Every test begins with open_app "
                  "and ends with assert_active. Return no other content.")
        body = {"model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": prompt},
                             {"role": "user", "content": json.dumps({"requirements": REQUIREMENTS})}]}
        response = api("https://api.openai.com/v1/chat/completions", "", key, "POST", body, bearer=True)
        cases = json.loads(response["choices"][0]["message"]["content"])["cases"]
    expected_ids = {r["id"] for r in REQUIREMENTS}
    if len(cases) != len(REQUIREMENTS) or {c.get("id") for c in cases} != expected_ids:
        raise RuntimeError("Generated test requirement coverage is incomplete")
    for c in cases:
        reference = next(r for r in REQUIREMENTS if r["id"] == c["id"])
        steps = c.get("steps")
        if (c.get("intent") != reference["intent"] or not isinstance(c.get("title"), str)
            or not isinstance(steps, list) or not steps
            or steps[0] != "open_app" or steps[-1] != "assert_active"
            or not all(isinstance(s, str) and s in ALLOWED for s in steps)):
            raise RuntimeError("Generated case failed validation")
    save(STATE / "plan.json", {"cases": cases, "provider": provider})
    print(json.dumps({"provider": provider, "generated": len(cases), "requirements_covered": len(expected_ids)}))
    return cases

def playwright(cases, mapping):
    lines = ["import { test, expect } from '@playwright/test';"]
    commands = {"open_app": "await page.goto('/');",
                "enter_email": "await page.locator('#email').fill('demo@example.com');",
                "subscribe": "await page.locator('#subscribe').click();",
                "assert_active": "await expect(page.locator('#status')).toHaveText('Subscription active');"}
    for c in cases:
        cid = mapping.get(c["id"])
        marker = f"[TR:C{cid}] " if cid else ""
        lines.append(f"test({json.dumps(marker + '[' + c['id'] + '] ' + c['title'])}, async ({{ page }}) => {{")
        for step in c["steps"]:
            lines.append("  " + commands[step])
        lines.append("});")
    target = ROOT / "generated" / "subscription.spec.ts"
    target.parent.mkdir(exist_ok=True)
    target.write_text("\n".join(lines) + "\n")

def verify():
    project = os.environ["TESTRAIL_PROJECT_ID"]
    section = os.environ["TESTRAIL_SECTION_ID"]
    info = tr("get_project/" + project)
    sections_resp = tr("get_sections/" + project)
    sections = sections_resp if isinstance(sections_resp, list) else sections_resp.get("sections", [])
    if str(info.get("id")) != project or not any(str(s.get("id")) == section for s in sections):
        raise RuntimeError("TestRail project or section mismatch")
    account = jira("myself")
    jproj = jira("project/" + urllib.parse.quote(os.environ["JIRA_PROJECT_KEY"], safe=""))
    if not account.get("accountId") or jproj.get("key") != os.environ["JIRA_PROJECT_KEY"]:
        raise RuntimeError("Jira user or project mismatch")
    print("PASS: read-only TestRail and Jira access")

def publish(apply, provider):
    cases = generate(provider)
    mapping = read(STATE / "case-map.json", {})
    for c in cases:
        if c["id"] in mapping:
            continue
        if apply:
            # Simple text fields; TestRail instances may require template-specific custom fields.
            result = tr("add_case/" + os.environ["TESTRAIL_SECTION_ID"], "POST", {
                "title": "[" + c["id"] + "] " + c["title"],
                "custom_preconds": "Synthetic demo requirement " + c["id"],
                "custom_steps": "1. Open sample application\n2. Enter valid email\n3. Subscribe",
                "custom_expected": "Subscription active"})
            mapping[c["id"]] = int(result["id"])
            save(STATE / "case-map.json", mapping)
    playwright(cases, mapping)
    print(json.dumps({"dry_run": not apply, "published_mapping": mapping,
                      "would_publish": [c["id"] for c in cases if c["id"] not in mapping]}))

def create_run(apply):
    mapping = read(STATE / "case-map.json", {})
    if not mapping:
        raise RuntimeError("Publish a TestRail case before creating a run")
    previous = read(STATE / "run.json", {})
    if previous.get("id"):
        print(json.dumps({"run_id": previous["id"], "reused": True}))
        return
    payload = {"name": "PromptTestGen phase 2 controlled demo", "include_all": False,
               "case_ids": sorted(set(mapping.values()))}
    if os.getenv("TESTRAIL_SUITE_ID"):
        payload["suite_id"] = int(os.environ["TESTRAIL_SUITE_ID"])
    if apply:
        res = tr("add_run/" + os.environ["TESTRAIL_PROJECT_ID"], "POST", payload)
        save(STATE / "run.json", {"id": int(res["id"])})
        print(json.dumps({"run_id": res["id"], "created": True}))
    else:
        print(json.dumps({"dry_run": True, "would_create": payload}))

def adf(message):
    return {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": x or " "}]} for x in message.splitlines()]}

def sync(apply, create_bugs):
    report = read(ROOT / "reports" / "playwright-results.json", {})
    run_id = read(STATE / "run.json", {}).get("id")
    if apply and not run_id:
        raise RuntimeError("Missing run ID")
    results = []
    def traverse(node):
        for spec in node.get("specs", []):
            marker = re.search(r"\[TR:C(\d+)\]", spec.get("title", ""))
            if not marker:
                continue
            case_id = int(marker.group(1))
            for test in spec.get("tests", []):
                outcome = test.get("status")
                if outcome == "skipped":
                    continue
                if outcome not in ("expected", "unexpected", "flaky"):
                    continue
                attempts = test.get("results") or []
                final = attempts[-1] if attempts else {}
                failure = outcome == "unexpected"
                error = final.get("error") or {}
                message = str(error.get("message", "")) if isinstance(error, dict) else str(error)
                results.append((case_id, failure, message[:2000], spec["title"]))
        for child in node.get("suites", []):
            traverse(child)
    for suite in report.get("suites", []):
        traverse(suite)
    if not results:
        raise RuntimeError("No TestRail-linked tests in Playwright JSON results")
    ledger = read(STATE / "ledger.json", {})
    for cid, failed, message, title in results:
        fingerprint = f"{run_id}:{cid}:{'failed' if failed else 'passed'}"
        if fingerprint in ledger:
            continue
        if not apply:
            print(json.dumps({"case_id": cid, "failed": failed, "would_create_jira_bug": failed and create_bugs}))
            continue
        response = tr(f"add_result_for_case/{run_id}/{cid}", "POST",
                      {"status_id": 5 if failed else 1,
                       "comment": ("Playwright regression\n" + message)[:2500]})
        ledger[fingerprint] = {"result_id": response.get("id")}
        save(STATE / "ledger.json", ledger)
        if failed and create_bugs:
            label = f"autotest-tr-c{cid}"
            key = os.environ["JIRA_PROJECT_KEY"]
            q = urllib.parse.urlencode({"jql": f'project = "{key}" AND labels = "{label}"',
                                        "maxResults": 1, "fields": "key"})
            existing = jira("search/jql?" + q).get("issues", [])
            if existing:
                bug_key = existing[0]["key"]
            else:
                body = {"fields": {"project": {"key": key}, "issuetype": {"name": "Bug"},
                       "summary": f"[Automation] TestRail C{cid} - failure"[:240],
                       "description": adf("Playwright failure\nTestRail run: " + str(run_id) +
                                          "\nTest: " + title + "\nEvidence: " + message),
                       "labels": ["automated-qa", label]}}
                bug_key = jira("issue", "POST", body)["key"]
            ledger[fingerprint]["jira_key"] = bug_key
            save(STATE / "ledger.json", ledger)
    print(json.dumps({"dry_run": not apply, "linked_tests": len(results),
                      "passed": sum(not r[1] for r in results), "failed": sum(r[1] for r in results)}))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["verify", "generate", "publish", "create-run", "sync"])
    p.add_argument("--apply", action="store_true")
    p.add_argument("--create-bugs", action="store_true")
    p.add_argument("--provider", choices=["mock", "openai"], default="mock")
    args = p.parse_args()
    try:
        if args.command == "verify":
            verify()
        elif args.command == "generate":
            generate(args.provider)
            playwright(read(STATE / "plan.json", {})["cases"], read(STATE / "case-map.json", {}))
        elif args.command == "publish":
            publish(args.apply, args.provider)
        elif args.command == "create-run":
            create_run(args.apply)
        else:
            sync(args.apply, args.create_bugs)
    except (RuntimeError, KeyError, ValueError, urllib.error.URLError) as exc:
        print(f"Integration failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
if __name__ == "__main__":
    main()
