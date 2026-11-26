from datetime import datetime
from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=8000)
    business_line: str = Field(default="both", pattern="^(client|own|both)$")
    blueprint: str | None = Field(default=None, pattern="^(shopping)?$")
    autostart: bool = False


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    business_line: str
    status: str
    slug: str | None = None
    app_type: str | None = None
    stack: str | None = None
    workspace_path: str | None = None

    class Config:
        from_attributes = True


class TaskOut(BaseModel):
    id: int
    project_id: int
    department: str
    agent_role: str
    agent_id: str
    title: str
    details: str
    result: str | None = None
    status: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class TaskReview(BaseModel):
    decision: str = Field(pattern="^(accept|revise)$")


class WorkspaceOut(BaseModel):
    id: int
    project_id: int
    slug: str
    path: str
    status: str
    current_phase: str | None = None
    progress: int
    engine: str
    model: str | None = None
    build_status: str
    test_status: str
    security_status: str
    preview_status: str
    preview_port: int | None = None
    preview_url: str | None = None
    repository_url: str | None = None

    class Config:
        from_attributes = True


class ApprovalOut(BaseModel):
    id: int
    project_id: int
    kind: str
    title: str
    summary: str
    status: str
    decision_note: str | None = None
    created_at: datetime | None = None
    decided_at: datetime | None = None

    class Config:
        from_attributes = True


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject|revision)$")
    note: str = Field(default="", max_length=4000)


class FileWrite(BaseModel):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=500_000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=6000)


class BuildRequest(BaseModel):
    force: bool = False


class RepositoryRequest(BaseModel):
    url: str = Field(default="", max_length=500)
    confirmed: bool = False
