from pydantic import BaseModel, Field

class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=4000)
    business_line: str = Field(default="both", pattern="^(client|own|both)$")

class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    business_line: str
    status: str
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
    class Config:
        from_attributes = True

class TaskReview(BaseModel):
    decision: str = Field(pattern="^(accept|revise)$")
