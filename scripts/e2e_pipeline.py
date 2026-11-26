#!/usr/bin/env python3
"""End-to-end driver for the NEXORA pipeline (local verification script)."""
import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"


def call(method, path, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(f"{API}{path}", data=data, method=method,
                                     headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode()
            return response.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def wait_for(project_id, states, limit=200, interval=3, label=""):
    last = None
    for index in range(limit):
        status, workspace = call("GET", f"/api/projects/{project_id}/workspace")
        if status == 200:
            current = workspace["status"]
            line = (f"  [{label}] {current:32s} {workspace['progress']:3d}% "
                    f"build={workspace['build_status']:11s} tests={workspace['test_status']:11s} "
                    f"security={workspace['security_status']:7s} preview={workspace['preview_status']}")
            if line != last:
                print(line, flush=True)
                last = line
            if current in states:
                return workspace
        time.sleep(interval)
    return None


def main():
    print("1. Creating project with the acceptance-test requirement")
    status, project = call("POST", "/api/projects", {
        "name": "Online Shopping Platform",
        "description": (
            "Build a real online shopping platform. Customers must be able to register and log in, "
            "browse a product listing, open product details, add items to a shopping cart, complete a "
            "checkout, and manage their orders. Staff need an admin dashboard for orders, products and "
            "customers. Use a real database."
        ),
        "business_line": "client",
    })
    assert status == 201, (status, project)
    project_id = project["id"]
    print(f"   project #{project_id} created")

    print("2. Running AI analysis / specification / design / architecture")
    print("  ", call("POST", f"/api/projects/{project_id}/generate"))
    workspace = wait_for(project_id, {"awaiting_architecture_approval", "failed"}, limit=60, label="plan")
    assert workspace and workspace["status"] == "awaiting_architecture_approval", workspace

    print("3. Founder approval gates")
    _, approvals = call("GET", f"/api/projects/{project_id}/approvals")
    for approval in approvals:
        print(f"   {approval['kind']:18s} {approval['status']:8s} {approval['summary'].splitlines()[0][:70]}")
    for approval in approvals:
        if approval["status"] == "pending":
            code, body = call("POST", f"/api/approvals/{approval['id']}/decide",
                              {"decision": "approve", "note": "Approved for build."})
            assert code == 200, body

    print("4. Implementation → build → test → security → preview → founder review")
    print("  ", call("POST", f"/api/projects/{project_id}/build"))
    workspace = wait_for(project_id, {"awaiting_application_review", "failed", "blocked"},
                         limit=200, label="build")
    assert workspace, "pipeline did not finish"

    print("5. Dashboard")
    _, dashboard = call("GET", f"/api/projects/{project_id}/dashboard")
    ws = dashboard["workspace"]
    print(f"   status={ws['status']} progress={ws['progress']} engine={ws['engine']}")
    print(f"   files_indexed={ws['file_count']} size={ws['size_kb']}KB preview={ws['preview_status']} {ws['preview_url']}")
    builds = {b["kind"]: b for b in dashboard["builds"]}
    for kind in ("install", "build", "test"):
        if kind in builds:
            print(f"   {kind:8s} {builds[kind]['status']:8s} exit={builds[kind]['exit_code']} "
                  f"{builds[kind]['passed']} passed / {builds[kind]['failed']} failed")

    print("6. File explorer + source viewer")
    _, files = call("GET", f"/api/projects/{project_id}/files")
    print(f"   {len(files['files'])} files on disk")
    for sample in ("backend/server.js", "database/schema.sql", "frontend/src/main.js"):
        code, payload = call("GET", f"/api/projects/{project_id}/file?path={sample}")
        print(f"   {sample:28s} HTTP {code} {payload.get('lines', '?')} lines")

    print("7. Live preview through the NEXORA proxy")
    if ws["preview_status"] == "running":
        code, health = call("GET", f"/preview/{ws['slug']}/api/health")
        print(f"   proxy /api/health -> HTTP {code} {health}")
        with urllib.request.urlopen(f"{API}/preview/{ws['slug']}/", timeout=15) as response:
            html = response.read().decode()
        print(f"   proxy / -> HTTP {response.status}, {len(html)} bytes, banner={'nexora-preview-banner' in html}")

    print("8. Founder review + deployment approvals")
    _, approvals = call("GET", f"/api/projects/{project_id}/approvals")
    for approval in approvals:
        print(f"   {approval['kind']:18s} {approval['status']:8s}")
    return 0 if ws["status"] == "awaiting_application_review" else 1


if __name__ == "__main__":
    sys.exit(main())
