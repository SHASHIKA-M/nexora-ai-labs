"""Full pipeline acceptance test.

This is the real thing: the orchestrator copies a blueprint into a temporary
workspace, installs dependencies, builds, seeds a database, runs the generated
application's own 59-test suite, scans it for security issues, boots the
generated server on a real port, probes it over HTTP and records a founder
review. It is the slowest test in the repository and it is worth the wait.

Skipped automatically when Node.js is unavailable.
"""
import json
import shutil
import urllib.request

import pytest

from app import engine, orchestrator
from app.database import SessionLocal
from app.models import Approval, BuildRun, Project, WorkspaceEvent

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")


def _approve_all(db, project_id):
    for approval in db.query(Approval).filter(Approval.project_id == project_id).all():
        if approval.status == "pending":
            approval.status = "approved"
    db.commit()


def _open_http(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def test_full_pipeline_produces_a_running_application(isolated_environment):
    db = SessionLocal()
    try:
        project = Project(
            name="Online Shopping Platform",
            description=(
                "Build a real online shopping platform where customers register and log in, "
                "browse products, add items to a cart, complete a checkout and manage orders, "
                "with an admin dashboard for products, orders and customers."
            ),
            business_line="client",
            status="planning",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # 1-4: analysis, specification, design, architecture → approval gates
        workspace = orchestrator.generate(db, project)
        assert workspace.status == "awaiting_architecture_approval"
        assert workspace.progress == 34
        gates = {row.kind for row in db.query(Approval).filter(Approval.project_id == project.id)}
        assert {"architecture", "design", "development_plan"} <= gates

        # The AI is offline in tests, so every artefact must be labelled as the
        # deterministic planner rather than pretending to be model output.
        assert workspace.engine == "blueprint"

        # 5-11: implementation, build, tests, security, deployment prep, review
        _approve_all(db, project.id)
        workspace = orchestrator.build_application(db, project)

        assert workspace.build_status == "passed", "the generated application must build"
        assert workspace.test_status == "passed", "the generated application's tests must pass"
        assert workspace.security_status in {"passed", "review"}
        assert workspace.progress == 100
        assert workspace.status == "awaiting_application_review"

        test_runs = (
            db.query(BuildRun)
            .filter(BuildRun.workspace_id == workspace.id, BuildRun.kind == "test")
            .order_by(BuildRun.id.desc())
            .all()
        )
        assert test_runs and test_runs[0].passed >= 40, "the suite must actually execute"
        assert test_runs[0].failed == 0

        # Real source files exist on disk (not just as database text).
        from pathlib import Path

        from app.workspace import list_files
        files = {entry["path"] for entry in list_files(Path(workspace.path))}
        for required in ("backend/server.js", "database/schema.sql", "frontend/src/main.js",
                         "tests/integration/auth.test.js", "documentation/api.md", "README.md",
                         ".env.example"):
            assert required in files, f"{required} must be generated on disk"

        # The generated database was created and seeded with real rows.
        health_status, health_body = _open_http(f"http://127.0.0.1:{workspace.preview_port}/api/health")
        assert health_status == 200
        payload = json.loads(health_body)
        assert payload["status"] == "ok"
        assert payload["product_count"] >= 12

        # A customer journey works over real HTTP against the generated app.
        status, products = _open_http(f"http://127.0.0.1:{workspace.preview_port}/api/products")
        assert status == 200
        assert len(json.loads(products)["products"]) >= 12

        # Founder review evidence must reflect these verified results.
        review = (
            db.query(Approval)
            .filter(Approval.project_id == project.id, Approval.kind == "application")
            .order_by(Approval.id.desc())
            .first()
        )
        assert review is not None
        assert review.payload["evidence"]["build"] == "passed"
        assert review.payload["evidence"]["tests"] == "passed"
        assert review.payload["evidence"]["preview_running"] is True

        # Deployment is still gated: nothing is published automatically.
        deployment = (
            db.query(Approval)
            .filter(Approval.project_id == project.id, Approval.kind == "deployment")
            .order_by(Approval.id.desc())
            .first()
        )
        assert deployment is not None and deployment.status == "pending"

        # Every stage left an audit trail.
        kinds = {row.kind for row in db.query(WorkspaceEvent).filter(WorkspaceEvent.workspace_id == workspace.id)}
        assert {"start", "agent", "scaffold", "install", "build", "test", "scan", "preview", "gate"} <= kinds

        orchestrator.stop_preview(db, workspace)
        assert workspace.preview_status == "stopped"
    finally:
        db.close()
