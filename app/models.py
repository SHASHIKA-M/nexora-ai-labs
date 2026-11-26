from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def now():
    return datetime.now(timezone.utc)


class Project(Base):
    """A client project. `slug` names its real workspace folder on disk."""
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    business_line: Mapped[str] = mapped_column(String(30), default="both")
    status: Mapped[str] = mapped_column(String(40), default="planning")
    slug: Mapped[str | None] = mapped_column(String(120), nullable=True)
    app_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    stack: Mapped[str | None] = mapped_column(String(200), nullable=True)
    workspace_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    workspace: Mapped["Workspace | None"] = relationship(back_populates="project", uselist=False, cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    department: Mapped[str] = mapped_column(String(80))
    agent_role: Mapped[str] = mapped_column(String(100))
    agent_id: Mapped[str] = mapped_column(String(40), default="backend")
    title: Mapped[str] = mapped_column(String(200))
    details: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    project: Mapped[Project] = relationship(back_populates="tasks")


class Workspace(Base):
    """One run of the autonomous development pipeline against a real folder."""
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True)
    slug: Mapped[str] = mapped_column(String(120))
    path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    current_phase: Mapped[str | None] = mapped_column(String(60), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    engine: Mapped[str] = mapped_column(String(30), default="blueprint")
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    log: Mapped[str] = mapped_column(Text, default="")
    build_status: Mapped[str] = mapped_column(String(30), default="not_started")
    test_status: Mapped[str] = mapped_column(String(30), default="not_started")
    security_status: Mapped[str] = mapped_column(String(30), default="not_started")
    preview_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preview_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preview_status: Mapped[str] = mapped_column(String(30), default="stopped")
    preview_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    repository_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    project: Mapped[Project] = relationship(back_populates="workspace")
    events: Mapped[list["WorkspaceEvent"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceEvent(Base):
    """Audit trail: every agent action, file write, build and test result."""
    __tablename__ = "workspace_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    phase: Mapped[str] = mapped_column(String(60))
    agent_id: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    workspace: Mapped[Workspace] = relationship(back_populates="events")


class Approval(Base):
    """Founder approval checkpoint."""
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    kind: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BuildRun(Base):
    """One execution of a build / test / security / install command."""
    __tablename__ = "build_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    kind: Mapped[str] = mapped_column(String(40))
    command: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="running")
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    output: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProjectFile(Base):
    """Indexed metadata for a workspace file (content lives on disk, never here)."""
    __tablename__ = "project_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    path: Mapped[str] = mapped_column(Text)
    agent_id: Mapped[str] = mapped_column(String(40))
    phase: Mapped[str] = mapped_column(String(60))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    lines: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str] = mapped_column(String(64), default="")
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentRun(Base):
    """A single AI employee turn with its structured input/output."""
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    phase: Mapped[str] = mapped_column(String(60))
    agent_id: Mapped[str] = mapped_column(String(40))
    engine: Mapped[str] = mapped_column(String(30))
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="running")
    prompt: Mapped[str] = mapped_column(Text, default="")
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_chars: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
