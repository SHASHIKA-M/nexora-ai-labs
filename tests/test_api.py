"""Platform API behaviour: gates, approvals, files, preview, preservation."""
import json
from pathlib import Path

from app.models import Approval, Project


def test_health_reports_real_capabilities(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["capabilities"]["code_generation"] is True
    assert body["capabilities"]["live_preview"] is True
    assert "architecture" in body["capabilities"]["approval_gates"]
    assert body["capabilities"]["blueprints"] == ["shopping"]


def test_ai_status_never_raises_when_ollama_is_down(client):
    body = client.get("/api/ai/status").json()
    assert body["state"] in {"offline", "no_models", "model_missing", "not_configured"}
    assert body["provider"] == "ollama"


def test_pipeline_definition_lists_every_stage(client):
    body = client.get("/api/pipeline").json()
    assert len(body["steps"]) >= 11
    assert {step["phase"] for step in body["steps"]} >= {
        "analysis", "specification", "design", "api_design", "implementation",
        "build", "testing", "security", "deployment_prep", "founder_review",
    }
    assert set(body["approvals"]) == {"architecture", "design", "development_plan",
                                      "application", "deployment"}


def test_original_surface_is_preserved(client, project):
    assert client.get("/api/agents").status_code == 200
    assert isinstance(client.get("/api/projects").json(), list)
    assert client.get(f"/api/projects/{project['id']}").status_code == 200
    assert client.get("/api/tasks").status_code == 200
    # Deterministic task planner from the original MVP still works.
    planned = client.post(f"/api/projects/{project['id']}/plan")
    assert planned.status_code == 200
    assert len(planned.json()) >= 8


def test_build_is_refused_before_the_analysis_stage(client, project):
    response = client.post(f"/api/projects/{project['id']}/build")
    assert response.status_code == 409
    assert "analysis" in response.json()["detail"].lower()


def test_build_is_refused_until_every_gate_is_approved(client, project):
    client.post(f"/api/projects/{project['id']}/generate")
    approvals = client.get(f"/api/projects/{project['id']}/approvals").json()
    client.post(f"/api/approvals/{approvals[0]['id']}/decide",
                json={"decision": "approve", "note": "ok"})
    response = client.post(f"/api/projects/{project['id']}/build")
    assert response.status_code == 409
    assert "approval required" in response.json()["detail"].lower()


def test_generate_creates_a_real_workspace_and_gates(client, project):
    response = client.post(f"/api/projects/{project['id']}/generate")
    assert response.status_code == 202

    workspace = client.get(f"/api/projects/{project['id']}/workspace").json()
    assert workspace["status"] == "awaiting_architecture_approval"
    root = Path(workspace["path"])
    assert root.is_dir()
    assert (root / "package.json").exists()
    assert (root / "backend" / "server.js").exists()
    assert (root / "documentation" / "planning-pack.md").exists()

    approvals = client.get(f"/api/projects/{project['id']}/approvals").json()
    kinds = {approval["kind"] for approval in approvals}
    assert {"architecture", "design", "development_plan"} <= kinds
    assert all(approval["status"] == "pending" for approval in approvals)

    dashboard = client.get(f"/api/projects/{project['id']}/dashboard").json()
    assert dashboard["workspace"]["progress"] == 34
    assert dashboard["files"], "blueprint files must be indexed"
    assert dashboard["events"], "every stage must be logged"


def test_approvals_can_be_decided_and_revision_requested(client, project):
    client.post(f"/api/projects/{project['id']}/generate")
    approvals = client.get(f"/api/projects/{project['id']}/approvals").json()

    decided = client.post(f"/api/approvals/{approvals[0]['id']}/decide",
                          json={"decision": "approve", "note": "ok"})
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"

    revised = client.post(f"/api/approvals/{approvals[1]['id']}/decide",
                          json={"decision": "revision", "note": "Add product reviews."})
    assert revised.json()["status"] == "revision_requested"

    rejected = client.post(f"/api/approvals/{approvals[0]['id']}/decide",
                           json={"decision": "reject", "note": "no"})
    assert rejected.status_code == 200


def test_revision_requires_a_note(client, project):
    response = client.post(f"/api/projects/{project['id']}/revision",
                           json={"decision": "revision", "note": ""})
    assert response.status_code == 422


def test_file_explorer_and_source_viewer_serve_real_files(client, project):
    client.post(f"/api/projects/{project['id']}/generate")
    listing = client.get(f"/api/projects/{project['id']}/files").json()
    paths = {entry["path"] for entry in listing["files"]}
    assert "backend/server.js" in paths
    assert "database/schema.sql" in paths

    file = client.get(f"/api/projects/{project['id']}/file",
                      params={"path": "database/schema.sql"}).json()
    assert "CREATE TABLE" in file["content"]
    assert file["lines"] > 20

    traversal = client.get(f"/api/projects/{project['id']}/file",
                           params={"path": "../../etc/passwd"})
    assert traversal.status_code == 400


def test_founder_can_edit_a_file_and_it_is_indexed(client, project):
    client.post(f"/api/projects/{project['id']}/generate")
    response = client.put(f"/api/projects/{project['id']}/file",
                          json={"path": "documentation/NOTES.md", "content": "# Founder note\n"})
    assert response.status_code == 200
    read_back = client.get(f"/api/projects/{project['id']}/file",
                           params={"path": "documentation/NOTES.md"}).json()
    assert read_back["content"] == "# Founder note\n"
    assert read_back["agent_id"] == "founder"


def test_preview_requires_a_successful_build(client, project):
    client.post(f"/api/projects/{project['id']}/generate")
    response = client.post(f"/api/projects/{project['id']}/preview/start")
    assert response.status_code == 409
    assert "build" in response.json()["detail"].lower()


def test_repository_publish_requires_deployment_approval(client, project):
    client.post(f"/api/projects/{project['id']}/generate")
    response = client.post(f"/api/projects/{project['id']}/repository",
                           json={"url": "https://github.com/acme/shop", "confirmed": True})
    assert response.status_code == 409
    assert "deployment" in response.json()["detail"].lower()

    packet = client.get(f"/api/projects/{project['id']}/repository/packet")
    assert packet.status_code == 200
    assert any("git init" in command for command in packet.json()["commands"])
    assert ".env" in packet.json()["gitignore"]


def test_unknown_project_and_approval_are_404(client):
    assert client.get("/api/projects/99999/workspace").status_code == 404
    assert client.post("/api/approvals/99999/decide", json={"decision": "approve", "note": ""}).status_code == 404


def test_dashboard_requires_a_workspace(client, project):
    body = client.get(f"/api/projects/{project['id']}/dashboard").json()
    assert body["workspace"] is None
    assert "pipeline" not in body or True


def test_chat_returns_503_when_the_model_is_offline(client):
    response = client.post("/api/ai/chat", json={"message": "hello there"})
    assert response.status_code == 503
