from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
import httpx
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import Project, Task
from .schemas import ProjectCreate, ProjectOut, TaskOut, TaskReview
from .workflow import create_plan, create_ai_plan, approve_task, run_specialist_task
from .agents import AGENTS
from .ai import generate_reply

Base.metadata.create_all(bind=engine)
# Lightweight SQLite upgrade for databases created by earlier Nexora MVP versions.
with engine.begin() as connection:
    columns = {column["name"] for column in inspect(engine).get_columns("tasks")}
    if "agent_id" not in columns:
        connection.execute(text("ALTER TABLE tasks ADD COLUMN agent_id VARCHAR(40) NOT NULL DEFAULT 'backend'"))
    if "result" not in columns:
        connection.execute(text("ALTER TABLE tasks ADD COLUMN result TEXT"))
    if "status" in columns:
        connection.execute(text("""UPDATE tasks SET agent_id = CASE
            WHEN department LIKE '%Product%' THEN 'product'
            WHEN department LIKE '%Design%' OR department LIKE '%UX%' THEN 'design'
            WHEN department LIKE '%Quality%' OR department LIKE '%QA%' THEN 'qa'
            WHEN department LIKE '%DevOps%' THEN 'devops'
            WHEN department LIKE '%Marketing%' OR department LIKE '%Sales%' THEN 'growth'
            WHEN department LIKE '%Support%' THEN 'support'
            WHEN department LIKE '%Operations%' OR department LIKE '%Finance%' THEN 'operations'
            ELSE 'backend' END WHERE agent_id IS NULL OR agent_id = ''"""))

app = FastAPI(title="Nexora AI Labs", version="0.2.0",
              description="Founder-controlled local-AI software studio operations")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")

@app.get("/api/health")
def health():
    provider = os.getenv("LLM_PROVIDER", "ollama")
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    ollama_status = "not_configured"
    if provider == "ollama":
        try:
            check = httpx.get(f"{base_url}/api/tags", timeout=2.0)
            check.raise_for_status()
            ollama_status = "online"
        except Exception:
            ollama_status = "offline"
    return {"status": "ok", "service": "Nexora AI Labs", "provider": provider, "model": model, "ollama": ollama_status}

@app.get("/api/agents")
def list_agents():
    return AGENTS

@app.get("/api/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.id.desc()).all()

@app.post("/api/projects", response_model=ProjectOut, status_code=201)
def new_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=payload.name, description=payload.description, business_line=payload.business_line)
    db.add(project)
    db.commit()
    db.refresh(project)
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

class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=6000)

@app.post("/api/ai/chat")
def ai_chat(payload: ChatRequest):
    try:
        reply = generate_reply(payload.message)
        return {"provider": os.getenv("LLM_PROVIDER", "ollama"), "reply": reply}
    except Exception as exc:
        raise HTTPException(503, f"AI service unavailable: {type(exc).__name__}. Check that Ollama is running.") from exc
