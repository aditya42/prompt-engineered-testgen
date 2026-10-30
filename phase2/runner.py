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
        # Report only Jira's rejected field names; never log response values or tokens.
        diagnostic = ""
        if "/rest/api/3/issue" in url and method == "POST":
            try:
                detail = json.loads(exc.read(32768))
                fields = detail.get("errors", {}) if isinstance(detail, dict) else {}
                if isinstance(fields, dict) and fields:
                    names = [str(k)[:80] for k in fields.keys()]
                    diagnostic = " (rejected fields: " + ", ".join(names[:10]) + ")"
                else:
                    diagnostic = " (Jira rejected issue payload; inspect issue type and required fields)"
            except (ValueError, UnicodeError):
                diagnostic = " (non-JSON Jira validation response)"
        raise RuntimeError(f"{method} request failed: HTTP {exc.code}{diagnostic}") from None

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
    if os.getenv("DEMO_INJECT_FAILURE") == "true":
        commands["assert_active"] = "await expect(page.locator('#status')).toHaveText('INTENTIONALLY WRONG - DEMO');"
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

def existing_testrail_cases():
    """Find existing cases by stable requirement marker across workflow runs."""
    project = os.environ["TESTRAIL_PROJECT_ID"]
    section = os.environ["TESTRAIL_SECTION_ID"]
    found = {}
    offset = 0
    while True:
        url = f"get_cases/{project}&limit=250&offset={offset}"
        if os.getenv("TESTRAIL_SUITE_ID"):
            url += "&suite_id=" + urllib.parse.quote(os.environ["TESTRAIL_SUITE_ID"])
        response = tr(url)
        cases = response if isinstance(response, list) else response.get("cases", [])
        if not isinstance(cases, list):
            raise RuntimeError("Unexpected TestRail case list response")
        for item in cases:
            if str(item.get("section_id")) != section:
                continue
            match = re.match(r"^\[([A-Z]+-\d+)\] ", item.get("title", ""))
            if match:
                requirement = match.group(1)
                if requirement in found and found[requirement] != int(item["id"]):
                    raise RuntimeError("Duplicate TestRail cases exist for " + requirement)
                found[requirement] = int(item["id"])
        next_link = response.get("_links", {}).get("next") if isinstance(response, dict) else None
        if not next_link:
            break
        offset += len(cases)
        if not cases or offset > 10000:
            raise RuntimeError("TestRail pagination exceeded safety limit")
    return found

def publish(apply, provider):
    cases = generate(provider)
    mapping = existing_testrail_cases() if apply else read(STATE / "case-map.json", {})
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
    name = "PromptTestGen phase 2 run " + os.getenv("GITHUB_RUN_ID", "local")
    payload = {"name": name, "include_all": False,
               "case_ids": sorted(set(mapping.values()))}
    if os.getenv("TESTRAIL_SUITE_ID"):
        payload["suite_id"] = int(os.environ["TESTRAIL_SUITE_ID"])
    if apply:
        # A job retry uses the same GITHUB_RUN_ID, so locate that run before POST.
        project = os.environ["TESTRAIL_PROJECT_ID"]
        offset = 0
        existing = None
        while True:
            response = tr(f"get_runs/{project}&limit=250&offset={offset}")
            runs = response if isinstance(response, list) else response.get("runs", [])
            existing = next((r for r in runs if r.get("name") == name), None)
            if existing:
                break
            link = response.get("_links", {}).get("next") if isinstance(response, dict) else None
            if not link:
                break
            offset += len(runs)
            if not runs or offset > 10000:
                raise RuntimeError("TestRail run pagination exceeded safety limit")
        if existing:
            run_id = int(existing["id"])
            reused = True
        else:
            created = tr("add_run/" + project, "POST", payload)
            run_id = int(created["id"])
            reused = False
        save(STATE / "run.json", {"id": run_id})
        print(json.dumps({"run_id": run_id, "reused": reused}))
    else:
        print(json.dumps({"dry_run": True, "would_create": payload}))

RUN_PREFIX = "PromptTestGen phase 2 "
LEGACY_RUN_NAME = "PromptTestGen phase 2 controlled demo"

def project_runs():
    """Return all project runs; page fully before making retention decisions."""
    project = os.environ["TESTRAIL_PROJECT_ID"]
    runs = []
    offset = 0
    while True:
        response = tr(f"get_runs/{project}&limit=250&offset={offset}")
        batch = response if isinstance(response, list) else response.get("runs", [])
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected TestRail runs response")
        runs.extend(batch)
        link = response.get("_links", {}).get("next") if isinstance(response, dict) else None
        if not link:
            break
        if not batch:
            raise RuntimeError("TestRail returned an empty pagination page")
        offset += len(batch)
        if offset > 10000:
            raise RuntimeError("TestRail run pagination exceeded safety limit")
    return runs

def prune_runs(apply=False, keep=3):
    """Keep newest N runs managed by this demo; never delete unrelated project runs."""
    if keep < 1:
        raise RuntimeError("Retention must preserve at least one run")
    active_id = read(STATE / "run.json", {}).get("id")
    managed = [r for r in project_runs()
               if str(r.get("name", "")).startswith(RUN_PREFIX)]
    managed.sort(key=lambda r: int(r["id"]), reverse=True)
    keep_ids = {int(r["id"]) for r in managed[:keep]}
    if active_id is not None:
        keep_ids.add(int(active_id))
    # Refuse an unsafe cleanup that would delete a current execution run.
    victims = [r for r in managed if int(r["id"]) not in keep_ids]
    outcome = {"dry_run": not apply, "keep": keep,
               "preserved": sorted(keep_ids),
               "delete": [int(r["id"]) for r in victims]}
    if apply:
        for r in victims:
            tr("delete_run/" + str(int(r["id"])), "POST")
        outcome["deleted"] = [int(r["id"]) for r in victims]
    save(STATE / "retention.json", outcome)
    print(json.dumps(outcome))
    return outcome

def execution_summary():
    """Publish GitHub Actions run summary and stable result metadata."""
    run = read(STATE / "run.json", {})
    case_map = read(STATE / "case-map.json", {})
    ledger = read(STATE / "ledger.json", {})
    retention = read(STATE / "retention.json", {})
    report = read(ROOT / "reports" / "playwright-results.json", {})
    run_id = run.get("id")
    tr_url = os.getenv("TESTRAIL_URL", "").rstrip("/")
    jira_url = os.getenv("JIRA_URL", "").rstrip("/")
    entries = [v for v in ledger.values() if isinstance(v, dict)]
    jira_keys = sorted({v["jira_key"] for v in entries if v.get("jira_key")})
    failed = sum(1 for s in report.get("suites", []) for sp in walk_specs(s)
                 for t in sp.get("tests", []) if t.get("status") == "unexpected")
    passed = sum(1 for s in report.get("suites", []) for sp in walk_specs(s)
                 for t in sp.get("tests", []) if t.get("status") == "expected")
    lines = ["## PromptTestGen — execution report", "",
             f"- GitHub action: {os.getenv('DEMO_ACTION', 'local')}",
             f"- Generation provider: {read(STATE / 'plan.json', {}).get('provider', 'n/a')}",
             f"- Playwright: **{passed} passed / {failed} failed**",
             f"- Retention: last **3** managed TestRail runs; deleted: "
             + (", ".join("R" + str(n) for n in retention.get("deleted", [])) or "none"),
             "", "| Resource | Link |", "| --- | --- |"]
    for req, cid in sorted(case_map.items()):
        lines.append(f"| TestRail case {req} | [C{cid}]({tr_url}/index.php?/cases/view/{cid}) |")
    if run_id:
        lines.append(f"| TestRail execution | [R{run_id}]({tr_url}/index.php?/runs/view/{run_id}) |")
    for key in jira_keys:
        if re.fullmatch(r"[A-Z][A-Z0-9_]*-[0-9]+", key):
            lines.append(f"| Synthetic Jira Bug | [{key}]({jira_url}/browse/{key}) |")
    if not jira_keys:
        lines.append("| Jira Bug | Not created/reused in this execution |")
    text = "\n".join(lines) + "\n"
    target = STATE / "summary.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    step_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as out:
            out.write(text)
    print(json.dumps({"run_id": run_id, "cases": case_map, "jira_keys": jira_keys,
                      "passed": passed, "failed": failed,
                      "deleted_runs": retention.get("deleted", [])}))
    return text

def walk_specs(suite):
    for spec in suite.get("specs", []):
        yield spec
    for child in suite.get("suites", []):
        yield from walk_specs(child)

def clean_error(message):
    """Remove ANSI escape sequences and non-printable characters from test diagnostics."""
    message = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", message)
    return "".join(char for char in message if char.isprintable() or char in "\n\t")

def adf(message):
    return {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": x or " "}]} for x in message.splitlines()]}

def jira_issue_type(key, requested="Bug"):
    """Resolve the actual project-specific Jira issue-type ID, never substitute Task."""
    project = jira("project/" + urllib.parse.quote(key, safe=""))
    types = project.get("issueTypes", [])
    if not types:
        raise RuntimeError("Jira project API did not expose issue types; configure a supported Bug issue type")
    match = next((kind for kind in types if kind.get("name", "").casefold() == requested.casefold()), None)
    if not match:
        names = ", ".join(str(kind.get("name", ""))[:60] for kind in types[:15])
        raise RuntimeError("Jira issue type '" + requested + "' is unavailable in project " +
                           key + "; available: " + names)
    return str(match["id"])

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
                message = clean_error(str(error.get("message", "")) if isinstance(error, dict) else str(error))
                results.append((case_id, failure, message[:2000], spec["title"]))
        for child in node.get("suites", []):
            traverse(child)
    for suite in report.get("suites", []):
        traverse(suite)
    if not results:
        raise RuntimeError("No TestRail-linked tests in Playwright JSON results")
    ledger = read(STATE / "ledger.json", {})
    demo_failure = os.getenv("DEMO_INJECT_FAILURE") == "true"
    if create_bugs and not demo_failure:
        raise RuntimeError("Jira writes require the explicit synthetic demonstration mode")
    for cid, failed, message, title in results:
        fingerprint = f"{run_id}:{cid}:{'failed' if failed else 'passed'}"
        if fingerprint in ledger and (not failed or not create_bugs or ledger[fingerprint].get("jira_key")):
            continue
        if not apply:
            print(json.dumps({"case_id": cid, "failed": failed, "would_create_jira_bug": failed and create_bugs}))
            continue
        if fingerprint not in ledger:
            response = tr(f"add_result_for_case/{run_id}/{cid}", "POST",
                          {"status_id": 5 if failed else 1,
                           "comment": ("Synthetic demo\n" + message)[:2500]})
            ledger[fingerprint] = {"result_id": response.get("id")}
            save(STATE / "ledger.json", ledger)
        if failed and create_bugs:
            label = f"demo-autotest-tr-c{cid}"
            key = os.environ["JIRA_PROJECT_KEY"]
            q = urllib.parse.urlencode({"jql": f'project = "{key}" AND labels = "{label}"',
                                        "maxResults": 1, "fields": "key"})
            existing = jira("search/jql?" + q).get("issues", [])
            if existing:
                bug_key = existing[0]["key"]
            else:
                issue_type_id = jira_issue_type(key)
                body = {"fields": {"project": {"key": key}, "issuetype": {"id": issue_type_id},
                       "summary": f"[SYNTHETIC DEMO] TestRail C{cid} intentionally failed"[:240],
                       "description": adf("SYNTHETIC DEMONSTRATION - NOT A PRODUCTION DEFECT\nTestRail run: " + str(run_id) +
                                          "\nTest: " + title + "\nEvidence: " + message),
                       "labels": ["automated-qa", "synthetic-demo", label]}}
                bug_key = jira("issue", "POST", body)["key"]
            ledger[fingerprint]["jira_key"] = bug_key
            save(STATE / "ledger.json", ledger)
    print(json.dumps({"dry_run": not apply, "linked_tests": len(results),
                      "passed": sum(not r[1] for r in results), "failed": sum(r[1] for r in results)}))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["verify", "verify-jira-bug", "generate", "publish", "create-run", "sync", "prune-runs", "summary"])
    p.add_argument("--apply", action="store_true")
    p.add_argument("--create-bugs", action="store_true")
    p.add_argument("--provider", choices=["mock", "openai"], default="mock")
    args = p.parse_args()
    try:
        if args.command == "verify":
            verify()
        elif args.command == "verify-jira-bug":
            print("Jira Bug issue type ID:", jira_issue_type(os.environ["JIRA_PROJECT_KEY"]))
        elif args.command == "generate":
            generate(args.provider)
            playwright(read(STATE / "plan.json", {})["cases"], read(STATE / "case-map.json", {}))
        elif args.command == "publish":
            publish(args.apply, args.provider)
        elif args.command == "create-run":
            create_run(args.apply)
        elif args.command == "sync":
            sync(args.apply, args.create_bugs)
        elif args.command == "prune-runs":
            prune_runs(args.apply)
        else:
            execution_summary()
    except (RuntimeError, KeyError, ValueError, urllib.error.URLError) as exc:
        print(f"Integration failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
if __name__ == "__main__":
    main()
