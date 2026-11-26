import json
import re
from sqlalchemy.orm import Session
from .models import Project, Task
from .agents import AGENT_BY_ID, AGENT_WORK_PROMPTS
from .ai import generate_reply

WORKFLOW = [
    ("Product Strategy", "AI Product Manager", "Create product brief", "Summarize the customer problem, target users, scope, and measurable acceptance criteria."),
    ("Design", "AI UX/UI Designer", "Prepare UX and screen specifications", "Define user journeys, page list, wireframe notes, accessibility, and responsive states."),
    ("Development", "AI Full-stack Developer", "Create implementation plan", "Break the app into frontend, backend, database, and integration tasks. Do not deploy."),
    ("Quality Assurance", "AI QA & Security Analyst", "Prepare test and security checklist", "List functional tests, edge cases, privacy checks, and authorization requirements."),
    ("DevOps", "AI DevOps Engineer", "Prepare deployment plan", "Document hosting, environment variables, backups, and rollback plan. Deployment requires approval."),
    ("Sales & Marketing", "AI Growth Strategist", "Prepare go-to-market brief", "Define positioning, ideal customer profile, launch content, and ethical outreach ideas."),
    ("Customer Support", "AI Customer Support Designer", "Prepare support workflow", "Define help content, escalation rules, and customer feedback collection."),
    ("Operations & Finance", "AI Operations Analyst", "Prepare cost and operations estimate", "Estimate service costs, free-tier constraints, risks, and operating procedures."),
]

CEO_PLANNER_PROMPT = """Act as the AI CEO of NEXORA AI LABS. Convert the founder's project into a realistic, coordinated plan for specialized AI departments.
Return ONLY valid JSON, no markdown fences, with this exact shape:
{"summary":"short project summary","tasks":[{"agent_id":"product|design|frontend|backend|qa|devops|growth|support|operations","title":"short deliverable title","details":"specific instructions and expected deliverable"}]}
Include one task for each relevant specialist, normally 6 to 9 tasks. Every agent_id must be from the allowed list. Make tasks specific to the project, not generic. Do not assign external actions, purchases, account changes, customer contact, code execution, or deployment. Those require separate founder approval. If requirements are missing, state assumptions and list open questions inside the product task details.
"""


def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("AI CEO did not return valid JSON. Please retry the plan.")
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("AI CEO returned malformed JSON. Please retry the plan.") from exc


def create_ai_plan(db: Session, project: Project):
    request = f"Project name: {project.name}\nBusiness line: {project.business_line}\nDescription: {project.description or 'Not provided'}"
    raw = generate_reply(request, CEO_PLANNER_PROMPT)
    plan = _extract_json(raw)
    task_specs = plan.get("tasks")
    if not isinstance(task_specs, list) or not task_specs:
        raise ValueError("AI CEO returned a plan without tasks. Please retry.")

    created = []
    for spec in task_specs[:12]:
        if not isinstance(spec, dict):
            continue
        agent = AGENT_BY_ID.get(str(spec.get("agent_id", "")))
        if not agent:
            continue
        title = str(spec.get("title", "")).strip()[:200]
        details = str(spec.get("details", "")).strip()[:6000]
        if not title or not details:
            continue
        task = Task(
            project_id=project.id,
            department=agent["department"],
            agent_role=agent["role"],
            agent_id=agent["id"],
            title=title,
            details=details,
            status="awaiting_founder_approval",
        )
        db.add(task)
        created.append(task)
    if not created:
        raise ValueError("AI CEO plan did not contain any recognized specialist tasks. Please retry.")
    project.status = "awaiting_founder_approval"
    db.commit()
    for task in created:
        db.refresh(task)
    return created


def create_plan(db: Session, project: Project):
    tasks = []
    for department, role, title, details in WORKFLOW:
        agent_id = next((a["id"] for a in AGENT_BY_ID.values() if a["role"] == role), None)
        task = Task(project_id=project.id, department=department, agent_role=role,
                    agent_id=agent_id or "backend", title=title, details=details,
                    status="awaiting_founder_approval")
        db.add(task)
        tasks.append(task)
    project.status = "awaiting_founder_approval"
    db.commit()
    for task in tasks:
        db.refresh(task)
    return tasks


def run_specialist_task(task: Task) -> str:
    agent_id = task.agent_id or "backend"
    agent = AGENT_BY_ID.get(agent_id, AGENT_BY_ID["backend"])
    specialist_instruction = AGENT_WORK_PROMPTS.get(agent_id, AGENT_WORK_PROMPTS["backend"])
    system_prompt = (
        f"You are {agent['role']} in the {agent['department']} department at NEXORA AI LABS. "
        "You are a specialist AI employee. Produce a useful, structured work deliverable. "
        "Do not claim to modify files, run commands, contact people, spend money, access accounts, "
        "or deploy. External actions require founder approval. Clearly label assumptions and risks."
    )
    user_prompt = f"Project: {task.project.name}\nTask: {task.title}\nTask instructions: {task.details}\n\nYour assignment: {specialist_instruction}"
    return generate_reply(user_prompt, system_prompt)


def approve_task(db: Session, task: Task):
    if task.status != "awaiting_founder_approval":
        raise ValueError("Only tasks awaiting founder approval can be approved.")
    task.status = "approved_for_execution"
    db.commit()
    db.refresh(task)
    return task
