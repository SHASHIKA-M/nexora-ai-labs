"""NEXORA AI LABS — founder-controlled autonomous AI software studio.

Preserves the original MVP surface (projects, AI CEO planning, specialist task
board, founder approvals, local Ollama chat) and adds the real development
platform: generated application workspaces, an eleven-stage AI pipeline, live
preview proxy, build/test engine and founder approval gates.
"""
from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from . import orchestrator, preview, sandbox, workspace as workspace_io
from .agents import AGENTS, AGENT_BY_ID, PHASE_LABELS
from .ai import ai_available, ai_status, generate_reply
from .blueprints import BLUEPRINTS, blueprint_available
from .database import Base, engine as db_engine, get_db
from .models import (
    AgentRun, Approval, BuildRun, Project, ProjectFile, Task, Workspace, WorkspaceEvent,
)
from .schemas import (
    ApprovalDecision, BuildRequest, ChatRequest, FileWrite, ProjectCreate, ProjectOut,
    RepositoryRequest, TaskOut, TaskReview, WorkspaceOut,
)
from .workflow import approve_task, create_ai_plan, create_plan, run_specialist_task

Base.metadata.create_all(bind=db_engine)

# --------------------------------------------------------------------------- #
# Lightweight SQLite upgrades keep databases from earlier versions usable.
# --------------------------------------------------------------------------- #
PROJECT_COLUMNS = {
    "slug": "VARCHAR(120)",
    "app_type": "VARCHAR(60)",
    "stack": "VARCHAR(200)",
    "workspace_path": "VARCHAR(400)",
    "updated_at": "DATETIME",
}
TASK_COLUMNS = {
    "agent_id": "VARCHAR(40) NOT NULL DEFAULT 'backend'",
    "result": "TEXT",
}

with db_engine.begin() as connection:
    project_columns = {column["name"] for column in inspect(db_engine).get_columns("projects")}
    for name, ddl in PROJECT_COLUMNS.items():
        if name not in project_columns:
            connection.execute(text(f"ALTER TABLE projects ADD COLUMN {name} {ddl}"))
    task_columns = {column["name"] for column in inspect(db_engine).get_columns("tasks")}
    for name, ddl in TASK_COLUMNS.items():
        if name not in task_columns:
            connection.execute(text(f"ALTER TABLE tasks ADD COLUMN {name} {ddl}"))
    if "status" in task_columns:
        connection.execute(text("""UPDATE tasks SET agent_id = CASE
            WHEN department LIKE '%Product%' THEN 'product'
            WHEN department LIKE '%Design%' OR department LIKE '%UX%' THEN 'design'
            WHEN department LIKE '%Quality%' OR department LIKE '%QA%' THEN 'qa'
            WHEN department LIKE '%DevOps%' THEN 'devops'
            WHEN department LIKE '%Marketing%' OR department LIKE '%Sales%' THEN 'growth'
            WHEN department LIKE '%Support%' THEN 'support'
            WHEN department LIKE '%Operations%' OR department LIKE '%Finance%' THEN 'operations'
            ELSE 'backend' END WHERE agent_id IS NULL OR agent_id = ''"""))

app = FastAPI(
    title="Nexora AI Labs",
    version="1.0.0",
    description="Founder-controlled autonomous AI software development studio",
)
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.include_router(preview.router)


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


# --------------------------------------------------------------------------- #
# Health & agents
# --------------------------------------------------------------------------- #

@app.get("/api/health")
def health():
    provider = os.getenv("LLM_PROVIDER", "ollama")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    ollama_status = "not_configured"
    if provider == "ollama":
        try:
            check = httpx.get(f"{base_url}/api/tags", timeout=2.0)
            check.raise_for_status()
            ollama_status = "online"
        except Exception:
            ollama_status = "offline"
    node_ok, node_detail = True, ""
    try:
        import shutil
        node_ok = shutil.which("node") is not None
        node_detail = "available" if node_ok else "Node.js not found"
    except Exception:
        node_detail = "unknown"
    return {
        "status": "ok",
        "service": "Nexora AI Labs",
        "version": app.version,
        "provider": provider,
        "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
        "ollama": ollama_status,
        "node": node_detail,
        "capabilities": {
            "code_generation": True,
            "sandboxed_execution": True,
            "live_preview": True,
            "approval_gates": list(orchestrator.APPROVAL_GATES.keys()),
            "blueprints": [key for key, item in BLUEPRINTS.items() if blueprint_available(item)],
        },
    }


@app.get("/api/ai/status")
def ai_health():
    return ai_status()


@app.get("/api/agents")
def list_agents():
    return AGENTS


@app.get("/api/pipeline")
def pipeline_definition():
    return {
        "steps": orchestrator.PIPELINE,
        "approvals": orchestrator.APPROVAL_GATES,
        "labels": PHASE_LABELS,
    }


# --------------------------------------------------------------------------- #
# Original project + task board API (kept working)
# --------------------------------------------------------------------------- #

@app.get("/api/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.id.desc()).all()


@app.post("/api/projects", response_model=ProjectOut, status_code=201)
def new_project(payload: ProjectCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    project = Project(
        name=payload.name.strip(),
        description=payload.description.strip(),
        business_line=payload.business_line,
        status="planning",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    if payload.autostart:
        background.add_task(_safe_generate, project.id, payload.blueprint)
    return project


@app.get("/api/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@app.post("/api/projects/{project_id}/plan", response_model=list[TaskOut])
def plan_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if project.tasks:
        raise HTTPException(409, "A workflow plan already exists for this project")
    return create_plan(db, project)


@app.post("/api/projects/{project_id}/ai-plan", response_model=list[TaskOut])
def ai_plan_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if project.tasks:
        raise HTTPException(409, "A workflow plan already exists for this project")
    try:
        return create_ai_plan(db, project)
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"AI CEO could not create the plan: {type(exc).__name__}. Check that Ollama is running.") from exc


@app.get("/api/projects/{project_id}/tasks", response_model=list[TaskOut])
def project_tasks(project_id: int, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    return db.query(Task).filter(Task.project_id == project_id).order_by(Task.id).all()


@app.get("/api/tasks", response_model=list[TaskOut])
def all_tasks(db: Session = Depends(get_db)):
    return db.query(Task).order_by(Task.id.desc()).all()


@app.post("/api/tasks/{task_id}/approve", response_model=TaskOut)
def approve(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    try:
        return approve_task(db, task)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/tasks/{task_id}/execute", response_model=TaskOut)
def execute_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != "approved_for_execution":
        raise HTTPException(409, "Founder approval is required before an AI specialist can work on this task.")
    try:
        task.result = run_specialist_task(task)
        task.status = "awaiting_founder_review"
        db.commit()
        db.refresh(task)
        return task
    except Exception as exc:
        raise HTTPException(503, f"AI specialist could not complete the task: {type(exc).__name__}. Check Ollama.") from exc


@app.post("/api/tasks/{task_id}/review", response_model=TaskOut)
def review_task(task_id: int, payload: TaskReview, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != "awaiting_founder_review":
        raise HTTPException(409, "Only AI outputs awaiting founder review can be reviewed.")
    if payload.decision == "accept":
        task.status = "completed"
    else:
        task.status = "approved_for_execution"
        task.result = None
    db.commit()
    db.refresh(task)
    return task


# --------------------------------------------------------------------------- #
# Autonomous development pipeline
# --------------------------------------------------------------------------- #

def _safe_generate(project_id: int, blueprint: str | None) -> None:
    from .database import SessionLocal
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        if not project:
            return
        orchestrator.generate(db, project, requested_blueprint=blueprint)
    except Exception as exc:  # noqa: BLE001 - recorded truthfully for the founder
        orchestrator.record_failure(db, db.get(Project, project_id), "analysis", exc)
    finally:
        db.close()


def _safe_build(project_id: int) -> None:
    from .database import SessionLocal
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        if not project:
            return
        orchestrator.build_application(db, project)
    except Exception as exc:  # noqa: BLE001
        orchestrator.record_failure(db, db.get(Project, project_id), "build", exc)
    finally:
        db.close()


def _require_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@app.post("/api/projects/{project_id}/generate", status_code=202)
def generate_project(project_id: int, background: BackgroundTasks,
                     blueprint: str | None = Query(default=None),
                     db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if project.workspace and project.workspace.status == "running":
        raise HTTPException(409, "The pipeline is already running for this project.")
    background.add_task(_safe_generate, project_id, blueprint)
    return {"status": "started", "project_id": project_id,
            "message": "AI analysis started. Approvals will appear when the planning stage completes."}


@app.post("/api/projects/{project_id}/build", status_code=202)
def build_project(project_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if not project.workspace:
        raise HTTPException(409, "Run the analysis stage first.")
    for kind in ("architecture", "design", "development_plan"):
        status = orchestrator.approval_status(db, project.id, kind)
        if status != "approved":
            raise HTTPException(
                409,
                f"Founder approval required before code generation: '{orchestrator.APPROVAL_GATES[kind]}' is {status}.",
            )
    if project.workspace.status == "running":
        raise HTTPException(409, "A build is already running for this project.")
    background.add_task(_safe_build, project_id)
    return {"status": "started", "project_id": project_id,
            "message": "Implementation, build, test, security and preview stages started."}


@app.post("/api/projects/{project_id}/preview/start")
def start_preview(project_id: int, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    workspace = project.workspace
    if not workspace:
        raise HTTPException(409, "No workspace exists for this project yet.")
    root = Path(workspace.path)
    if not (root / "backend" / "server.js").exists():
        raise HTTPException(409, "The application has not been built yet.")
    if workspace.build_status != "passed":
        raise HTTPException(409, "The application must build successfully before it can run.")
    result = orchestrator.start_preview(db, workspace, root)
    if not result.get("running"):
        raise HTTPException(502, f"Preview failed to start: {result.get('detail')}")
    return result


@app.post("/api/projects/{project_id}/preview/stop")
def stop_preview(project_id: int, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if project.workspace:
        orchestrator.stop_preview(db, project.workspace)
    return {"status": "stopped"}


# --------------------------------------------------------------------------- #
# Workspace: dashboard, file explorer, source viewer
# --------------------------------------------------------------------------- #

def _workspace_out(workspace: Workspace | None):
    return workspace


@app.get("/api/projects/{project_id}/workspace", response_model=WorkspaceOut)
def get_workspace(project_id: int, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if not project.workspace:
        raise HTTPException(404, "No workspace yet. Start the AI pipeline first.")
    workspace = project.workspace
    # Reconcile preview liveness so the dashboard never shows a dead server as running.
    if workspace.preview_pid and not sandbox.process_alive(workspace.preview_pid):
        workspace.preview_status = "stopped"
        workspace.preview_pid = None
        db.commit()
    return workspace


@app.get("/api/projects/{project_id}/dashboard")
def project_dashboard(project_id: int, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    workspace = project.workspace
    if not workspace:
        return {
            "project": {"id": project.id, "name": project.name, "status": project.status},
            "workspace": None,
            "message": "No pipeline run yet. Start the AI analysis to create a real workspace.",
        }
    if workspace.preview_pid and not sandbox.process_alive(workspace.preview_pid):
        workspace.preview_status = "stopped"
        workspace.preview_pid = None
        db.commit()

    root = Path(workspace.path)
    events = (
        db.query(WorkspaceEvent)
        .filter(WorkspaceEvent.workspace_id == workspace.id)
        .order_by(WorkspaceEvent.id.desc())
        .limit(120)
        .all()
    )
    files = (
        db.query(ProjectFile)
        .filter(ProjectFile.workspace_id == workspace.id)
        .order_by(ProjectFile.id.desc())
        .all()
    )
    builds = (
        db.query(BuildRun)
        .filter(BuildRun.workspace_id == workspace.id)
        .order_by(BuildRun.id.desc())
        .limit(12)
        .all()
    )
    agents = (
        db.query(AgentRun)
        .filter(AgentRun.workspace_id == workspace.id)
        .order_by(AgentRun.id.desc())
        .limit(20)
        .all()
    )
    approvals = (
        db.query(Approval)
        .filter(Approval.project_id == project.id)
        .order_by(Approval.id)
        .all()
    )
    current_agent = next((event.agent_id for event in events if event.kind in {"agent", "file", "verify", "build", "test", "scan"}), "ceo")

    return {
        "project": {
            "id": project.id, "name": project.name, "status": project.status,
            "app_type": project.app_type, "stack": project.stack, "slug": project.slug,
        },
        "workspace": {
            "slug": workspace.slug,
            "path": workspace.path,
            "status": workspace.status,
            "current_phase": workspace.current_phase,
            "phase_label": PHASE_LABELS.get(workspace.current_phase or "", workspace.current_phase),
            "progress": workspace.progress,
            "engine": workspace.engine,
            "model": workspace.model,
            "build_status": workspace.build_status,
            "test_status": workspace.test_status,
            "security_status": workspace.security_status,
            "preview_status": workspace.preview_status,
            "preview_port": workspace.preview_port,
            "preview_url": workspace.preview_url,
            "repository_url": workspace.repository_url,
            "current_agent": current_agent,
            "current_agent_name": AGENT_BY_ID.get(current_agent, {}).get("role", current_agent),
            "file_count": len(files),
            "size_kb": workspace_io.workspace_size_bytes(root) // 1024 if root.exists() else 0,
        },
        "files": [
            {
                "path": row.path, "agent_id": row.agent_id, "phase": row.phase,
                "lines": row.lines, "size_bytes": row.size_bytes,
                "is_ai_generated": row.is_ai_generated,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in files
        ],
        "events": [
            {
                "id": row.id, "phase": row.phase, "agent_id": row.agent_id, "kind": row.kind,
                "message": row.message, "detail": row.detail,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in events
        ],
        "builds": [
            {
                "id": row.id, "kind": row.kind, "command": row.command, "status": row.status,
                "exit_code": row.exit_code, "passed": row.passed, "failed": row.failed,
                "duration_ms": row.duration_ms, "output": row.output[-4000:],
            }
            for row in builds
        ],
        "agent_runs": [
            {
                "id": row.id, "phase": row.phase, "agent_id": row.agent_id, "engine": row.engine,
                "model": row.model, "status": row.status, "validation_error": row.validation_error,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }
            for row in agents
        ],
        "approvals": [
            {
                "id": row.id, "kind": row.kind, "title": row.title, "status": row.status,
                "summary": row.summary, "decision_note": row.decision_note,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            }
            for row in approvals
        ],
        "pipeline": [
            {"phase": step["phase"], "agent_id": step["agent_id"], "label": step["label"]}
            for step in orchestrator.PIPELINE
        ],
    }


@app.get("/api/projects/{project_id}/files")
def workspace_files(project_id: int, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if not project.workspace:
        raise HTTPException(404, "No workspace yet.")
    root = Path(project.workspace.path)
    return {
        "root": project.workspace.slug,
        "path": project.workspace.path,
        "tree": workspace_io.tree(root) if root.exists() else {"children": []},
        "files": workspace_io.list_files(root) if root.exists() else [],
    }


@app.get("/api/projects/{project_id}/file")
def read_workspace_file(project_id: int, path: str = Query(min_length=1), db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if not project.workspace:
        raise HTTPException(404, "No workspace yet.")
    root = Path(project.workspace.path)
    try:
        content = workspace_io.read_file(root, path)
    except workspace_io.WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc
    indexed = (
        db.query(ProjectFile)
        .filter(ProjectFile.workspace_id == project.workspace.id, ProjectFile.path == path)
        .first()
    )
    return {
        "path": path,
        "content": content,
        "lines": content.count("\n") + 1,
        "size_bytes": len(content.encode("utf-8")),
        "agent_id": indexed.agent_id if indexed else None,
        "is_ai_generated": indexed.is_ai_generated if indexed else False,
    }


@app.put("/api/projects/{project_id}/file")
def write_workspace_file(project_id: int, payload: FileWrite, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if not project.workspace:
        raise HTTPException(404, "No workspace yet.")
    root = Path(project.workspace.path)
    try:
        written = workspace_io.write_file(
            root, payload.path, payload.content, agent_id="founder", phase="manual_edit",
            db=db, workspace=project.workspace,
        )
    except workspace_io.WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc
    orchestrator.log_event(db, project.workspace, "manual_edit", "founder", "file",
                           f"Founder edited {payload.path} ({written.lines} lines).")
    return {"path": written.path, "size_bytes": written.size_bytes, "lines": written.lines}


# --------------------------------------------------------------------------- #
# Founder approvals
# --------------------------------------------------------------------------- #

@app.get("/api/projects/{project_id}/approvals")
def list_approvals(project_id: int, db: Session = Depends(get_db)):
    _require_project(db, project_id)
    rows = db.query(Approval).filter(Approval.project_id == project_id).order_by(Approval.id).all()
    return [
        {
            "id": row.id, "kind": row.kind, "title": row.title, "status": row.status,
            "summary": row.summary, "payload": row.payload, "decision_note": row.decision_note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@app.post("/api/approvals/{approval_id}/decide")
def decide_approval(approval_id: int, payload: ApprovalDecision, db: Session = Depends(get_db)):
    approval = db.get(Approval, approval_id)
    if not approval:
        raise HTTPException(404, "Approval not found")
    if approval.status in {"approved", "rejected"} and payload.decision == "approve":
        raise HTTPException(409, f"This checkpoint is already {approval.status}.")
    from datetime import datetime, timezone
    approval.status = {
        "approve": "approved",
        "reject": "rejected",
        "revision": "revision_requested",
    }[payload.decision]
    approval.decision_note = payload.note
    approval.decided_at = datetime.now(timezone.utc)
    db.commit()

    project = db.get(Project, approval.project_id)
    workspace = project.workspace if project else None
    if workspace:
        orchestrator.log_event(
            db, workspace, "founder_decision", "founder", "approval",
            f"{approval.title}: {approval.status}" + (f" — {payload.note}" if payload.note else ""),
        )
        if approval.kind == "deployment" and payload.decision == "approve":
            workspace.status = "deployment_approved"
        elif approval.kind == "application" and payload.decision == "approve":
            workspace.status = "approved"
        elif payload.decision == "revision":
            workspace.status = "revision_requested"
    if project:
        project.status = {
            "architecture": "architecture_approved" if payload.decision == "approve" else project.status,
            "design": "design_approved" if payload.decision == "approve" else project.status,
            "development_plan": "development_approved" if payload.decision == "approve" else project.status,
            "application": "approved" if payload.decision == "approve" else project.status,
            "deployment": "deployment_approved" if payload.decision == "approve" else project.status,
        }.get(approval.kind, project.status)
        db.commit()
    return {"id": approval.id, "status": approval.status, "kind": approval.kind}


@app.post("/api/projects/{project_id}/revision")
def request_revision(project_id: int, payload: ApprovalDecision, background: BackgroundTasks,
                     db: Session = Depends(get_db)):
    """Request a revision and re-run the pipeline with the founder's note."""
    project = _require_project(db, project_id)
    if not payload.note.strip():
        raise HTTPException(422, "Describe the revision you want before re-running the pipeline.")
    project.description = f"{project.description}\n\nFounder revision note: {payload.note}".strip()[:8000]
    latest = (
        db.query(Approval)
        .filter(Approval.project_id == project_id, Approval.status == "pending")
        .order_by(Approval.id.desc())
        .first()
    )
    if latest:
        from datetime import datetime, timezone
        latest.status = "revision_requested"
        latest.decision_note = payload.note
        latest.decided_at = datetime.now(timezone.utc)
    project.status = "revision_requested"
    db.commit()
    background.add_task(_safe_generate, project_id, None)
    return {"status": "revision_started", "project_id": project_id}


# --------------------------------------------------------------------------- #
# GitHub preparation (never pushes)
# --------------------------------------------------------------------------- #

@app.post("/api/projects/{project_id}/repository")
def prepare_repository(project_id: int, payload: RepositoryRequest, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    workspace = project.workspace
    if not workspace:
        raise HTTPException(409, "No workspace yet.")
    if orchestrator.approval_status(db, project_id, "deployment") != "approved":
        raise HTTPException(
            409,
            "A repository can only be prepared for publishing after the founder approves deployment. "
            "NEXORA never pushes to GitHub on its own.",
        )
    workspace.repository_url = payload.url or None
    db.commit()
    orchestrator.log_event(db, workspace, "repository", "devops", "repository",
                           f"Repository details recorded for {payload.url or 'manual publish'}.")
    return {"status": "recorded", "repository_url": workspace.repository_url,
            "note": "NEXORA does not push to GitHub. Run the git commands shown in documentation/deployment.md yourself."}


@app.get("/api/projects/{project_id}/repository/packet")
def repository_packet(project_id: int, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if not project.workspace:
        raise HTTPException(404, "No workspace yet.")
    root = Path(project.workspace.path)
    if not root.exists():
        raise HTTPException(404, "Workspace directory is missing.")
    gitignore = (root / ".gitignore").read_text(encoding="utf-8") if (root / ".gitignore").exists() else ""
    return {
        "slug": project.workspace.slug,
        "commands": [
            "git init",
            f"git add .",
            'git commit -m "Initial commit — generated by NEXORA AI LABS"',
            "git branch -M main",
            "git remote add origin <your-repository-url>",
            "git push -u origin main",
        ],
        "gitignore": gitignore,
        "excluded": [".env", "node_modules/", "data/", "*.db"],
        "approval_status": orchestrator.approval_status(db, project_id, "deployment"),
    }


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #

@app.post("/api/ai/chat")
def ai_chat(payload: ChatRequest):
    try:
        reply = generate_reply(payload.message)
        return {"provider": os.getenv("LLM_PROVIDER", "ollama"), "reply": reply}
    except Exception as exc:
        raise HTTPException(503, f"AI service unavailable: {type(exc).__name__}. Check that Ollama is running.") from exc


@app.get("/api/projects/{project_id}/events")
def project_events(project_id: int, limit: int = Query(default=200, le=1000), db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if not project.workspace:
        return {"events": []}
    rows = (
        db.query(WorkspaceEvent)
        .filter(WorkspaceEvent.workspace_id == project.workspace.id)
        .order_by(WorkspaceEvent.id.desc())
        .limit(limit)
        .all()
    )
    return {"events": [
        {"id": row.id, "phase": row.phase, "agent_id": row.agent_id, "kind": row.kind,
         "message": row.message, "detail": row.detail,
         "created_at": row.created_at.isoformat() if row.created_at else None}
        for row in reversed(rows)
    ]}


@app.get("/api/projects/{project_id}/builds")
def project_builds(project_id: int, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if not project.workspace:
        return {"builds": []}
    rows = (
        db.query(BuildRun)
        .filter(BuildRun.workspace_id == project.workspace.id)
        .order_by(BuildRun.id.desc())
        .limit(25)
        .all()
    )
    return {"builds": [
        {"id": row.id, "kind": row.kind, "command": row.command, "status": row.status,
         "exit_code": row.exit_code, "passed": row.passed, "failed": row.failed,
         "duration_ms": row.duration_ms, "output": row.output,
         "created_at": row.created_at.isoformat() if row.created_at else None}
        for row in rows
    ]}
