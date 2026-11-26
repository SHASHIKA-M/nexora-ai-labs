"""Autonomous development orchestrator.

Runs the eleven-step NEXORA pipeline for one project and leaves behind:

* a real source tree in ``generated_projects/<slug>/``,
* indexed file metadata, agent runs and build runs in the database,
* a founder approval checkpoint at every consequential gate,
* an optionally running preview server.

Design rules enforced here:

* Nothing is marked complete unless its output was verified.
* The AI is always asked first; the deterministic planner is a clearly labelled
  fallback recorded as ``engine='blueprint'``.
* Approvals are required before implementation, preview and any repository or
  deployment action.
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from . import engine, sandbox
from .agent_contracts import CONTRACTS, ContractError, agent_prompt, validate_code
from .agents import PIPELINE
from .ai import AIInvalidOutput, AIUnavailable, ai_available, generate_json, model_name
from .blueprints import BLUEPRINTS, blueprint_available, branding, materialise, resolve
from .fallbacks import FALLBACKS
from .models import (
    AgentRun, Approval, BuildRun, Project, ProjectFile, Workspace, WorkspaceEvent,
)
from .personalizer import apply_branding, apply_design_tokens, write_documentation
from .workspace import (
    index_existing_files, list_files, prepare_directory, projects_root, read_file,
    unique_slug, workspace_size_bytes, write_file,
)

# Requirements the founder must clear before code generation / running / release.
APPROVAL_GATES = {
    "architecture": "Approve project architecture",
    "design": "Approve UI/UX design",
    "development_plan": "Approve development plan",
    "application": "Review completed application",
    "deployment": "Approve deployment",
}


class PipelineError(RuntimeError):
    """The pipeline could not continue; the workspace state is truthful."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


# --------------------------------------------------------------------------- #
# Persistence helpers
# --------------------------------------------------------------------------- #

def log_event(db: Session, workspace: Workspace, phase: str, agent_id: str, kind: str,
              message: str, detail: str | None = None) -> None:
    db.add(WorkspaceEvent(
        workspace_id=workspace.id, phase=phase, agent_id=agent_id,
        kind=kind, message=message[:2000], detail=(detail or "")[:20000] or None,
    ))
    line = f"[{_now()}] {phase:14s} {agent_id:9s} {kind:9s} {message}"
    workspace.log = (workspace.log + "\n" + line)[-60000:]
    db.commit()


def set_phase(db: Session, workspace: Workspace, phase: str, progress: int, status: str | None = None) -> None:
    workspace.current_phase = phase
    workspace.progress = max(0, min(100, progress))
    if status:
        workspace.status = status
    db.commit()


def ensure_approval(db: Session, project: Project, kind: str, summary: str,
                    payload: dict | None = None) -> Approval:
    existing = (
        db.query(Approval)
        .filter(Approval.project_id == project.id, Approval.kind == kind,
                Approval.status.in_(["pending", "approved", "revision_requested"]))
        .order_by(Approval.id.desc())
        .first()
    )
    if existing and existing.status in {"pending", "approved"}:
        if payload and existing.payload != payload:
            existing.payload = payload
            existing.summary = summary[:8000]
            db.commit()
        return existing
    approval = Approval(
        project_id=project.id, kind=kind, title=APPROVAL_GATES.get(kind, kind),
        summary=summary[:8000], payload=payload, status="pending",
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


def approval_status(db: Session, project_id: int, kind: str) -> str:
    row = (
        db.query(Approval)
        .filter(Approval.project_id == project_id, Approval.kind == kind)
        .order_by(Approval.id.desc())
        .first()
    )
    return row.status if row else "missing"


# --------------------------------------------------------------------------- #
# AI turn helper
# --------------------------------------------------------------------------- #

def run_agent(db: Session, workspace: Workspace, agent_id: str, requirement: str,
              context: dict[str, Any], extra: str = "") -> tuple[dict, str]:
    """Run one AI employee against its JSON contract.

    Returns ``(payload, engine)`` where engine is ``'ai'`` or ``'blueprint'``.
    Raises :class:`PipelineError` when the model fails twice and no deterministic
    fallback exists for the contract.
    """
    contract = CONTRACTS[agent_id]
    problem = (
        f"Project requirement from the client:\n{requirement}\n\n"
        f"Verified project context:\n{json.dumps(context, indent=2, default=str)[:9000]}\n\n"
        f"{extra}\n\n"
        f"Respond with ONLY a JSON object matching this schema:\n{contract['schema']}"
    )
    started = datetime.now(timezone.utc)
    run = AgentRun(
        workspace_id=workspace.id, phase=contract["phase"], agent_id=agent_id,
        engine="ai", model=model_name() if ai_available() else None, status="running",
        prompt=problem[:20000], started_at=started,
    )
    db.add(run)
    db.commit()

    if ai_available():
        try:
            payload, raw = generate_json(
                f"{agent_prompt(agent_id)}\n\n{problem}",
                contract["schema"],
                contract["validate"],
                temperature=0.2,
            )
            run.status = "succeeded"
            run.engine = "ai"
            run.response = raw[:20000]
            run.structured = payload
            run.tokens_chars = len(raw)
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            log_event(db, workspace, contract["phase"], agent_id, "agent",
                      f"{contract['title']} produced by the local model.", None)
            return payload, "ai"
        except (AIInvalidOutput, ContractError) as exc:
            run.status = "invalid_output"
            run.validation_error = str(exc)[:2000]
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            log_event(db, workspace, contract["phase"], agent_id, "error",
                      f"Model output rejected: {exc}", None)
            raise PipelineError(
                f"{agent_id} returned output that failed validation: {exc}"
            ) from exc
        except AIUnavailable as exc:
            run.status = "unavailable"
            run.validation_error = str(exc)[:2000]
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            log_event(db, workspace, contract["phase"], agent_id, "warn",
                      f"Local model unavailable ({exc}); using the documented deterministic planner.", None)

    fallback_name = contract.get("fallback")
    builder = FALLBACKS.get(fallback_name) if fallback_name else None
    if builder is None:
        run.status = "failed"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise PipelineError(
            f"{agent_id} could not run: the local model is offline and no deterministic plan exists for this stage."
        )
    payload = builder(requirement) if builder.__code__.co_argcount <= 1 else builder(requirement)
    run.status = "fallback"
    run.engine = "blueprint"
    run.structured = payload
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    log_event(db, workspace, contract["phase"], agent_id, "agent",
              f"{contract['title']} produced by the deterministic planner (engine=blueprint).", None)
    return payload, "blueprint"


# --------------------------------------------------------------------------- #
# Implementation: writing real files
# --------------------------------------------------------------------------- #

def _load_blueprint_manifest(root: Path) -> list[str]:
    return [entry["path"] for entry in list_files(root)]


def implement_with_agents(db: Session, workspace: Workspace, root: Path,
                          requirement: str, spec: dict, api_plan: dict,
                          design: dict) -> dict:
    """Give the AI engineers a chance to author real files in the workspace.

    For each eligible path we ask the backend/frontend engineer for the complete
    file, validate it, then prove it by rebuilding and re-running the suite. A
    failed verification reverts the AI file to the reviewed blueprint version and
    the revert is recorded — so the workspace is never left broken.
    """
    from .blueprints import resolve as resolve_blueprint
    blueprint = resolve_blueprint(requirement)
    reference_root = blueprint.path

    plan_targets = [
        ("backend", "backend/services/catalogService.js",
         "Rewrite the catalogue service with the same exports and behaviour, adding clear JSDoc comments."),
    ]
    results: list[dict] = []
    for agent_id, path, instruction in plan_targets:
        if not (reference_root / path).exists():
            continue
        reference = (reference_root / path).read_text(encoding="utf-8")
        context = {
            "file": path,
            "current_source": reference[:12000],
            "spec_features": [feature.get("name") for feature in spec.get("features", [])][:12],
            "endpoints": [f"{ep['method']} {ep['path']}" for ep in api_plan.get("endpoints", [])][:15],
        }
        prompt = (
            f"File to produce: {path}\n"
            f"{instruction}\n"
            "Return the COMPLETE file content in the 'content' field, importing the same modules "
            "and exporting the same symbols so the application still builds and every test passes. "
            "Do not change behaviour. 70-120 lines is appropriate.\n\n"
            'Schema: {"path": string, "content": string, "language": string, "summary": string, "notes": [string]}'
        )
        started = datetime.now(timezone.utc)
        run = AgentRun(workspace_id=workspace.id, phase="implementation", agent_id=agent_id,
                       engine="ai", model=model_name(), status="running",
                       prompt=prompt[:20000], started_at=started)
        db.add(run)
        db.commit()
        try:
            payload, raw = generate_json(
                f"{agent_prompt(agent_id)}\n\nClient requirement:\n{requirement}\n\n"
                f"Verified context:\n{json.dumps(context, indent=2)[:9000]}\n\n{prompt}",
                "see prompt", validate_code, temperature=0.1,
            )
        except (AIInvalidOutput, ContractError, AIUnavailable) as exc:
            run.status = "unavailable" if isinstance(exc, AIUnavailable) else "invalid_output"
            run.validation_error = str(exc)[:2000]
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            log_event(db, workspace, "implementation", agent_id, "warn",
                      f"{path}: no AI-authored revision ({exc}). Blueprint source kept.", None)
            results.append({"path": path, "status": "blueprint", "reason": str(exc)[:300]})
            continue

        run.response = raw[:40000]
        run.structured = {"path": payload["path"], "summary": payload.get("summary"), "lines": payload["content"].count("\n")}
        run.tokens_chars = len(payload["content"])
        run.status = "succeeded"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()

        if payload["path"] != path:
            log_event(db, workspace, "implementation", agent_id, "warn",
                      f"{agent_id} proposed {payload['path']} instead of {path}; rejected.", None)
            results.append({"path": path, "status": "rejected", "reason": "path mismatch"})
            continue

        backup = reference
        write_file(root, path, payload["content"], agent_id=agent_id, phase="implementation",
                   is_ai_generated=True, db=db, workspace=workspace)
        log_event(db, workspace, "implementation", agent_id, "file",
                  f"{agent_id} wrote {path} ({len(payload['content'].splitlines())} lines).", payload.get("summary"))

        build_result = engine.build(db, workspace, root)
        test_result = engine.run_tests(db, workspace, root) if build_result.status == "passed" else None
        verified = build_result.status == "passed" and (test_result is None or test_result.status == "passed")
        if verified:
            results.append({"path": path, "status": "ai_verified", "reason": "build and tests passed"})
            log_event(db, workspace, "implementation", agent_id, "verify",
                      f"AI-authored {path} verified by rebuild + test suite.", None)
        else:
            write_file(root, path, backup, agent_id=agent_id, phase="implementation",
                       is_template=True, db=db, workspace=workspace)
            log_event(db, workspace, "implementation", agent_id, "warn",
                      f"AI-authored {path} failed verification; reverted to the reviewed blueprint version.",
                      (build_result.detail + (f" {test_result.detail}" if test_result else ""))[:1000])
            results.append({"path": path, "status": "reverted", "reason": build_result.detail})
            engine.build(db, workspace, root)
            engine.run_tests(db, workspace, root)
    return {"attempts": results}


# --------------------------------------------------------------------------- #
# Documentation
# --------------------------------------------------------------------------- #

def _bullet(items: list[str], fallback: str = "None recorded.") -> str:
    if not items:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in items)


def write_spec_documents(db: Session, workspace: Workspace, root: Path, project: Project,
                         requirement: str, payloads: dict[str, dict], engines: dict[str, str],
                         brand: dict) -> list[str]:
    analysis = payloads.get("analysis", {})
    spec = payloads.get("specification", {})
    design = payloads.get("design", {})
    api_plan = payloads.get("api_design", {})
    security = payloads.get("security", {})
    devops = payloads.get("deployment_prep", {})
    review = payloads.get("founder_review", {})

    readme = f"""# {brand['brand']}

{brand['tagline']}

A working web application generated end-to-end by **NEXORA AI LABS** from this client requirement:

> {requirement.strip()[:600]}

## What this application does

{analysis.get('summary', blueprint_summary(project))}

## Features

{_bullet(analysis.get('features', []))}

## Quick start

```bash
npm install
npm run db:seed     # create the database and demo data
npm run build       # bundle the frontend
npm start           # http://localhost:3000
```

`npm test` runs the full unit and integration suite (the same suite QA executed).

## Stack

{_bullet(brand.get('stack', []))}

## Project layout

```
backend/      Express API, middleware, routes and services
database/     schema.sql, migration and seed scripts
frontend/     ES-module SPA (src/) compiled into public/assets
tests/        unit and integration tests run by node:test
documentation/ generated specification, design and review documents
```

## Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Customer | demo@shop.test | Demo1234! |
| Admin | admin@shop.test | Admin1234! |

Change these before any real deployment (see `.env.example`).

## Provenance

| Stage | Engine |
| --- | --- |
""" + "\n".join(f"| {stage} | {engine_name} |" for stage, engine_name in engines.items()) + f"""

Security review: **{security.get('verdict', 'n/a')}** · Deployment readiness: **{devops.get('deployment_readiness', 'n/a')}**

---

Generated by NEXORA AI LABS for project #{project.id}. Review `documentation/founder-review.md`
before deploying: every release requires explicit founder approval.
"""
    docs: dict[str, tuple[str, str]] = {"README.md": ("devops", readme)}

    spec_doc = f"""# Technical specification — {brand['brand']}

_Produced by the AI Product Manager (engine: {engines.get('specification', 'blueprint')})._

## Problem statement

{spec.get('problem_statement', '')}

## Target users

{_bullet(spec.get('target_users', []))}

## Features

| ID | Feature | Priority |
| --- | --- | --- |
""" + "\n".join(
        f"| {feature.get('id', '')} | {feature.get('name', '')} | {feature.get('priority', '')} |"
        for feature in spec.get("features", [])
    ) + f"""

## Acceptance criteria

{_bullet(spec.get('acceptance_criteria', []))}

## Out of scope

{_bullet(spec.get('out_of_scope', []))}

## Assumptions

{_bullet(spec.get('assumptions', []))}
"""
    docs["documentation/specification.md"] = ("product", spec_doc)

    design_doc = f"""# Design system — {brand['brand']}

_Produced by the AI UX/UI Designer (engine: {engines.get('design', 'blueprint')})._

{design.get('design_system', '')}

## Palette

| Token | Value |
| --- | --- |
| Background | `{design.get('palette', {}).get('background', '')}` |
| Surface | `{design.get('palette', {}).get('surface', '')}` |
| Text | `{design.get('palette', {}).get('text', '')}` |
| Accent | `{design.get('palette', {}).get('accent', '')}` |

## Typography

{design.get('typography', '')}

## Pages

| Page | Route | Purpose |
| --- | --- | --- |
""" + "\n".join(
        f"| {page.get('name', '')} | `{page.get('route', '')}` | {page.get('purpose', '')} |"
        for page in design.get("pages", [])
    ) + f"""

## Components

{_bullet(design.get('components', []))}

## Responsive rules

{_bullet(design.get('responsive_rules', []))}

## Accessibility

{_bullet(design.get('accessibility', []))}
"""
    docs["documentation/design-system.md"] = ("design", design_doc)

    api_doc = f"""# API reference

_Produced by the AI Backend Engineer (engine: {engines.get('api_design', 'blueprint')})._

{api_plan.get('architecture', '')}

## Authentication

{api_plan.get('auth_strategy', '')}

## Endpoints

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
""" + "\n".join(
        f"| {endpoint.get('method', '')} | `{endpoint.get('path', '')}` | {'yes' if endpoint.get('auth') else 'no'} | {endpoint.get('description', '')} |"
        for endpoint in api_plan.get("endpoints", [])
    ) + f"""

## Data model

{_bullet(api_plan.get('data_model', []))}

## Business rules

{_bullet(api_plan.get('business_rules', []))}
"""
    docs["documentation/api.md"] = ("backend", api_doc)

    security_findings = _bullet(
        [
            "{}: {} — {}".format(
                finding.get("severity", ""), finding.get("title", ""), finding.get("recommendation", "")
            )
            for finding in security.get("findings", [])
        ],
        "No findings recorded.",
    )
    security_doc = f"""# Security review

_Produced by the AI Security Engineer (engine: {engines.get('security', 'blueprint')})._

**Verdict:** {security.get('verdict', 'n/a')} · **Score:** {security.get('score', 0)}/100

## Checks

| Check | Result | Detail |
| --- | --- | --- |
""" + "\n".join(
        f"| {check.get('name', '')} | {'pass' if check.get('passed') else 'fail'} | {check.get('detail', '')} |"
        for check in security.get("checks", [])
    ) + f"""

## Findings

{security_findings}

## Hardening applied

{_bullet(security.get('hardening_applied', []))}
"""
    docs["documentation/security.md"] = ("security", security_doc)

    deployment_doc = f"""# Deployment preparation

_Produced by the AI DevOps Engineer (engine: {engines.get('deployment_prep', 'blueprint')})._

{devops.get('summary', '')}

**Readiness:** {devops.get('deployment_readiness', 'pending')}

## Environment variables

{_bullet(devops.get('environment', []))}

## Pipeline

{_bullet(devops.get('pipeline', []))}

## Monitoring

{_bullet(devops.get('monitoring', []))}

## Rollback

{devops.get('rollback', 'Not documented.')}

> No deployment, push or publication happens without explicit founder approval in NEXORA.
"""
    docs["documentation/deployment.md"] = ("devops", deployment_doc)

    founder_doc = f"""# Founder readiness review

_Produced by the AI Founder's Office (engine: {engines.get('founder_review', 'blueprint')})._

**Verdict:** {review.get('verdict', 'pending')}

{review.get('summary', '')}

## Checklist

| Item | Result | Evidence |
| --- | --- | --- |
""" + "\n".join(
        f"| {item.get('item', '')} | {'pass' if item.get('passed') else 'fail'} | {item.get('evidence', '')} |"
        for item in review.get("checklist", [])
    ) + f"""

## Outstanding

{_bullet(review.get('outstanding', []), 'Nothing outstanding.')}

## Next steps

{_bullet(review.get('next_steps', []))}
"""
    docs["documentation/founder-review.md"] = ("founder", founder_doc)

    return write_documentation(db, workspace, root, docs)


def write_planning_documents(db: Session, workspace: Workspace, root: Path, project: Project,
                             requirement: str, payloads: dict[str, dict],
                             engines: dict[str, str]) -> list[str]:
    """Write the reviewable planning pack before the founder approval gate."""
    analysis = payloads.get("analysis", {})
    spec = payloads.get("specification", {})
    design = payloads.get("design", {})
    api_plan = payloads.get("api_design", {})
    brand = branding(requirement, name=project.name)

    overview = f"""# Planning pack — {brand['brand']}

Created by NEXORA AI LABS for project #{project.id} before any code was generated.
Each section records the engine that produced it (`ai` = local Ollama model,
`blueprint` = deterministic planner used because the model was unavailable).

## Client requirement

```
{requirement.strip()[:2000]}
```

## AI CEO analysis ({engines.get('analysis', 'blueprint')})

{analysis.get('summary', '')}

**Application type:** {analysis.get('app_type', '')}

### Required capabilities

{_bullet(analysis.get('features', []))}

### Risks

{_bullet(analysis.get('risks', []))}

## Specification ({engines.get('specification', 'blueprint')})

{spec.get('problem_statement', '')}

### Features

{_bullet([f"{feature.get('id')} — {feature.get('name')} ({feature.get('priority')})" for feature in spec.get('features', [])])}

### Acceptance criteria

{_bullet(spec.get('acceptance_criteria', []))}

## Design ({engines.get('design', 'blueprint')})

{design.get('design_system', '')}

### Pages

{_bullet([f"{page.get('name')} — {page.get('route')}: {page.get('purpose', '')}" for page in design.get('pages', [])])}

## Architecture ({engines.get('api_design', 'blueprint')})

{api_plan.get('architecture', '')}

### Planned endpoints ({len(api_plan.get('endpoints', []))})

{_bullet([f"{endpoint.get('method')} {endpoint.get('path')} — {endpoint.get('description', '')}" for endpoint in api_plan.get('endpoints', [])])}

## Next step

Approve architecture, design and the development plan in the founder console.
Code generation, build and testing only start after those approvals.
"""
    return write_documentation(db, workspace, root, {
        "documentation/planning-pack.md": ("ceo", overview),
    })


def blueprint_summary(project: Project) -> str:
    blueprint = resolve(project.description or "")
    return blueprint.description


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #

def generate(db: Session, project: Project, *, requested_blueprint: str | None = None,
             force: bool = False) -> Workspace:
    """Run analysis → approval gates for a project, creating its workspace."""
    workspace = project.workspace
    if workspace and workspace.status in {"awaiting_architecture_approval", "awaiting_plan_approval"} and not force:
        return workspace
    if workspace and workspace.preview_pid:
        sandbox.stop_process(workspace.preview_pid)

    requirement = f"{project.name}. {project.description or ''}".strip()
    blueprint = resolve(requirement, requested_blueprint)
    if not blueprint_available(blueprint):
        available = ", ".join(
            key for key, item in BLUEPRINTS.items() if blueprint_available(item)
        )
        raise PipelineError(
            f"The '{blueprint.label}' blueprint is not installed in this build. "
            f"Available blueprints: {available}"
        )

    slug = workspace.slug if workspace else unique_slug(db, project.name)
    root = prepare_directory(projects_root() / slug)

    if workspace:
        workspace.status = "running"
        workspace.progress = 0
        workspace.build_status = "not_started"
        workspace.test_status = "not_started"
        workspace.security_status = "not_started"
        db.query(ProjectFile).filter(ProjectFile.workspace_id == workspace.id).delete()
        db.query(BuildRun).filter(BuildRun.workspace_id == workspace.id).delete()
        db.commit()
    else:
        workspace = Workspace(project_id=project.id, slug=slug, path=str(root),
                              engine="blueprint", status="running")
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

    project.slug = slug
    project.workspace_path = str(root)
    project.stack = " · ".join(blueprint.stack)
    project.app_type = blueprint.label
    project.status = "in_progress"
    db.commit()

    used_ai = ai_available()
    model = model_name() if used_ai else None
    workspace.model = model
    workspace.engine = "ai+blueprint" if used_ai else "blueprint"
    db.commit()

    log_event(db, workspace, "requirement", "ceo", "start",
              f"Pipeline started for '{project.name}'. Application type: {blueprint.label}. "
              f"Local model {'available' if used_ai else 'offline — deterministic planner will be used'}.")
    if not used_ai:
        log_event(db, workspace, "requirement", "ceo", "warn",
                  "Ollama is not reachable. Planning will be produced by the deterministic planner and "
                  "clearly labelled as such; AI-authored code will be skipped.")

    payloads: dict[str, dict] = {}
    engines: dict[str, str] = {}
    context: dict[str, Any] = {
        "project": project.name,
        "application_type": blueprint.label,
        "blueprint_capabilities": blueprint.features,
        "stack": blueprint.stack,
    }

    # 2. AI CEO analysis
    set_phase(db, workspace, "analysis", 6)
    analysis, engine_used = run_agent(db, workspace, "ceo", requirement, context)
    payloads["analysis"] = analysis
    engines["analysis"] = engine_used
    context["analysis"] = analysis

    # 3. Product specification
    set_phase(db, workspace, "specification", 14)
    spec, engine_used = run_agent(db, workspace, "product", requirement, context)
    payloads["specification"] = spec
    engines["specification"] = engine_used
    context["specification"] = {key: spec[key] for key in ("problem_statement", "features") if key in spec}

    # 4. Design system
    set_phase(db, workspace, "design", 22)
    design, engine_used = run_agent(db, workspace, "design", requirement, context)
    payloads["design"] = design
    engines["design"] = engine_used
    context["design"] = {"pages": design["pages"], "palette": design["palette"]}

    # 5. API and data plan
    set_phase(db, workspace, "api_design", 30)
    api_plan, engine_used = run_agent(db, workspace, "backend", requirement, context)
    payloads["api_design"] = api_plan
    engines["api_design"] = engine_used
    context["api"] = {"endpoints": api_plan["endpoints"], "architecture": api_plan["architecture"]}

    workspace.progress = 34
    workspace.status = "awaiting_architecture_approval"
    workspace.current_phase = "awaiting_approval"
    db.commit()

    architecture_summary = (
        f"Application: {analysis.get('app_type')}\n"
        f"Stack: {', '.join(blueprint.stack)}\n"
        f"Architecture: {api_plan.get('architecture')}\n"
        f"Authentication: {api_plan.get('auth_strategy')}\n"
        f"Data model: {'; '.join(api_plan.get('data_model', []))}\n"
        f"Endpoints planned: {len(api_plan.get('endpoints', []))}"
    )
    ensure_approval(db, project, "architecture", architecture_summary, {
        "analysis": analysis, "api_plan": api_plan, "stack": blueprint.stack,
    })
    ensure_approval(db, project, "design",
                    f"{design.get('design_system', '')}\n\nPages: "
                    + ", ".join(page["name"] for page in design.get("pages", [])),
                    {"design": design})
    ensure_approval(db, project, "development_plan",
                    f"{spec.get('problem_statement', '')}\n\nFeatures:\n"
                    + "\n".join(f"- {feature['name']} ({feature['priority']})" for feature in spec.get("features", [])),
                    {"specification": spec, "blueprint": blueprint.key})

    # Write the planning documents now so the founder can read them at the gate.
    brand = branding(requirement, name=project.name)
    brand["stack"] = blueprint.stack
    project.status = "awaiting_founder_approval"
    db.commit()
    materialised = materialise(blueprint, slug)
    write_planning_documents(db, workspace, materialised, project, requirement, payloads, engines)

    log_event(db, workspace, "awaiting_approval", "ceo", "gate",
              "Architecture, design and development plan are ready for founder review.")
    project.status = "awaiting_founder_approval"
    db.commit()
    return workspace


def ensure_approved(db: Session, project: Project, kind: str) -> None:
    status = approval_status(db, project.id, kind)
    if status != "approved":
        raise PipelineError(
            f"Founder approval required: '{APPROVAL_GATES.get(kind, kind)}' is currently '{status}'."
        )


def build_application(db: Session, project: Project) -> Workspace:
    """Phase 5-8: materialise code, personality, install, build, test, fix, preview."""
    workspace = project.workspace
    if not workspace:
        raise PipelineError("No workspace exists yet. Run the analysis phase first.")
    ensure_approved(db, project, "architecture")
    ensure_approved(db, project, "design")
    ensure_approved(db, project, "development_plan")

    root = Path(workspace.path)
    requirement = f"{project.name}. {project.description or ''}".strip()
    blueprint = resolve(requirement, project.app_type and None)
    workspace.status = "running"
    db.commit()

    approvals = {row.kind: row for row in db.query(Approval).filter(Approval.project_id == project.id).all()}
    engines: dict[str, str] = {}
    payloads = {
        "analysis": (approvals.get("architecture").payload or {}).get("analysis", {}) if approvals.get("architecture") else {},
        "api_design": (approvals.get("architecture").payload or {}).get("api_plan", {}) if approvals.get("architecture") else {},
        "design": (approvals.get("design").payload or {}).get("design", {}) if approvals.get("design") else {},
        "specification": (approvals.get("development_plan").payload or {}).get("specification", {}) if approvals.get("development_plan") else {},
    }
    plan_payload = (approvals.get("development_plan").payload or {}) if approvals.get("development_plan") else {}
    blueprint_key = plan_payload.get("blueprint") or blueprint.key
    blueprint = resolve(requirement, blueprint_key)

    # 5-8: real implementation
    set_phase(db, workspace, "implementation", 38)
    materialised = materialise(blueprint, workspace.slug)
    indexed = index_existing_files(db, workspace, materialised,
                                   default_agent="backend", phase="implementation")
    db.commit()
    log_event(db, workspace, "implementation", "backend", "scaffold",
              f"Materialised the {blueprint.label} blueprint: {indexed} real source files "
              f"copied into the workspace and indexed.")

    brand = branding(requirement, name=project.name)
    brand["stack"] = blueprint.stack
    changed = apply_branding(db, workspace, materialised, brand)
    changed += apply_design_tokens(db, workspace, materialised, payloads["design"])
    project.app_type = blueprint.label
    log_event(db, workspace, "implementation", "design", "brand",
              f"Applied client branding and design tokens to {len(changed)} file(s).")

    set_phase(db, workspace, "implementation", 48)
    try:
        agent_work = implement_with_agents(db, workspace, materialised, requirement,
                                           payloads["specification"], payloads["api_design"],
                                           payloads["design"])
        for attempt in agent_work.get("attempts", []):
            log_event(db, workspace, "implementation", "frontend" if "frontend" in attempt["path"] else "backend",
                      "agent", f"{attempt['path']}: {attempt['status']} ({attempt.get('reason', '')[:160]})")
    except Exception as exc:  # noqa: BLE001 - implementation failures must not abort the pipeline
        log_event(db, workspace, "implementation", "backend", "error",
                  f"AI implementation pass failed: {type(exc).__name__}: {exc}")

    # Build + test with a bounded AI-assisted repair loop
    set_phase(db, workspace, "build", 56)
    install = engine.install_dependencies(db, workspace, materialised)
    workspace.build_status = "failed" if install.status == "failed" else "installing"
    db.commit()
    log_event(db, workspace, "build", "devops", "install", install.detail,
              install.output[-4000:] if install.output else None)
    if install.status == "failed":
        workspace.status = "blocked"
        workspace.build_status = "failed"
        db.commit()
        raise PipelineError(f"Dependency installation failed: {install.detail}")

    seed = engine.seed_database(db, workspace, materialised)
    log_event(db, workspace, "implementation", "database", "seed", seed.detail,
              seed.output[-3000:] if seed.output else None)

    max_repair_rounds = 2
    build_result = engine.build(db, workspace, materialised)
    test_result = engine.run_tests(db, workspace, materialised) if build_result.status == "passed" else None
    repair_round = 0
    while repair_round < max_repair_rounds and (
        build_result.status != "passed" or (test_result and test_result.status != "passed")
    ):
        repair_round += 1
        failure = "\n".join(filter(None, [
            "" if build_result.status == "passed" else f"BUILD OUTPUT:\n{build_result.output}",
            "" if not test_result or test_result.status == "passed" else f"TEST OUTPUT:\n{test_result.output}",
        ]))
        log_event(db, workspace, "build", "devops", "repair",
                  f"Verification failed; starting AI-assisted repair round {repair_round}.")
        fixed = ai_repair(db, workspace, materialised, failure, requirement)
        if not fixed:
            break
        build_result = engine.build(db, workspace, materialised)
        test_result = engine.run_tests(db, workspace, materialised) if build_result.status == "passed" else None

    workspace.build_status = build_result.status
    workspace.test_status = test_result.status if test_result else "not_run"
    db.commit()
    log_event(db, workspace, "build", "devops", "build", build_result.detail,
              build_result.output[-6000:] if build_result.output else None)
    if test_result:
        log_event(db, workspace, "testing", "qa", "test", test_result.detail,
                  test_result.output[-8000:] if test_result.output else None)
    set_phase(db, workspace, "testing", 78)

    # 9: security
    set_phase(db, workspace, "security", 84)
    scan = engine.static_security_scan(materialised)
    workspace.security_status = scan["verdict"]
    db.commit()
    log_event(db, workspace, "security", "security", "scan",
              f"Security scan: {scan['verdict']} (score {scan['score']}/100, "
              f"{sum(1 for c in scan['checks'] if c['passed'])}/{len(scan['checks'])} checks passed).",
              json.dumps(scan, indent=2)[:8000])

    # 10: deployment preparation
    set_phase(db, workspace, "deployment_prep", 88)
    devops_doc, devops_engine = run_agent(db, workspace, "devops", requirement,
                                          {**context_for(payloads), "security": scan["verdict"]})
    payloads["deployment_prep"] = devops_doc
    engines["deployment_prep"] = devops_engine

    # Documentation, generated from the real artefacts. Engines are read back
    # from the recorded agent runs so provenance is always truthful.
    engines.update(engines_from_runs(db, workspace))
    engines["security"] = "verified-scan"
    written_docs = write_spec_documents(db, workspace, materialised, project, requirement,
                                        payloads, engines, brand)
    log_event(db, workspace, "deployment_prep", "devops", "docs",
              f"Wrote {len(written_docs)} documentation files from verified artefacts.")

    # Preview start (isolated process)
    set_phase(db, workspace, "preview", 92)
    preview = start_preview(db, workspace, materialised)

    # 11: founder review evidence
    set_phase(db, workspace, "founder_review", 96)
    evidence = {
        "build": build_result.status,
        "build_detail": build_result.detail,
        "tests": test_result.status if test_result else "not_run",
        "test_detail": test_result.detail if test_result else "Tests were not run.",
        "security": scan["verdict"],
        "security_detail": f"score {scan['score']}/100",
        "preview_running": preview.get("running", False),
        "preview_detail": preview.get("detail", ""),
        "files": len(list_files(materialised)),
        "size_kb": workspace_size_bytes(materialised) // 1024,
    }
    review, review_engine = run_agent(db, workspace, "founder", requirement,
                                      {**context_for(payloads), "evidence": evidence})
    payloads["founder_review"] = review
    engines["founder_review"] = review_engine
    write_spec_documents(db, workspace, materialised, project, requirement, payloads, engines, brand)

    workspace.progress = 100
    workspace.status = "awaiting_application_review"
    workspace.current_phase = "awaiting_approval"
    db.commit()

    summary = (
        f"Application: {blueprint.label} ({len(list_files(materialised))} files)\n"
        f"Build: {build_result.status} · Tests: {evidence['tests']}\n"
        f"Security: {scan['verdict']} (score {scan['score']})\n"
        f"Preview: {'running' if preview.get('running') else preview.get('detail', 'not running')}\n"
        f"Founder review verdict: {review.get('verdict')}"
    )
    ensure_approval(db, project, "application", summary, {"evidence": evidence, "review": review})
    ensure_approval(db, project, "deployment",
                    "Deployment requires a final founder decision. NEXORA will not push or deploy without it.",
                    {"evidence": evidence})
    project.status = "awaiting_founder_review"
    db.commit()
    log_event(db, workspace, "founder_review", "founder", "gate",
              "Application is ready for founder review. Waiting at the founder approval gate.")
    return workspace


def engines_from_runs(db: Session, workspace: Workspace) -> dict[str, str]:
    """Map each pipeline stage to the engine that actually produced it."""
    mapping: dict[str, str] = {}
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.workspace_id == workspace.id)
        .order_by(AgentRun.id)
        .all()
    )
    for run in runs:
        if run.status in {"succeeded", "fallback"}:
            mapping[run.phase] = run.engine
    mapping.setdefault("build", "verified-run")
    mapping.setdefault("testing", "verified-run")
    mapping.setdefault("security", "verified-scan")
    return mapping


def context_for(payloads: dict) -> dict:
    return {
        "analysis": payloads.get("analysis", {}),
        "specification": payloads.get("specification", {}),
        "design": payloads.get("design", {}),
        "api": payloads.get("api_design", {}),
    }


def start_preview(db: Session, workspace: Workspace, root: Path) -> dict:
    """Start the generated app as an isolated background process."""
    if workspace.preview_pid and sandbox.process_alive(workspace.preview_pid):
        sandbox.stop_process(workspace.preview_pid)
        workspace.preview_pid = None
        db.commit()

    port = engine.free_port()
    log_path = root / "preview.log"
    try:
        process = sandbox.spawn_background(
            ["node", "--disable-warning=ExperimentalWarning", "backend/server.js"],
            root, port=port, log_path=log_path,
        )
    except Exception as exc:  # noqa: BLE001
        workspace.preview_status = "failed"
        workspace.preview_url = None
        db.commit()
        log_event(db, workspace, "preview", "devops", "error",
                  f"Preview could not start: {type(exc).__name__}: {exc}")
        return {"running": False, "detail": f"could not start: {exc}"}

    ok, body, detail = engine.wait_for_http(port)
    workspace.preview_port = port
    workspace.preview_pid = process.pid
    if ok:
        workspace.preview_status = "running"
        workspace.preview_url = f"/preview/{workspace.slug}/"
        db.commit()
        log_event(db, workspace, "preview", "devops", "preview",
                  f"Preview server started on port {port} (pid {process.pid}) and is responding.",
                  body[:2000])
        return {"running": True, "detail": f"responding on port {port}", "port": port}

    sandbox.stop_process(process.pid)
    workspace.preview_status = "failed"
    workspace.preview_url = None
    db.commit()
    log_tail = ""
    if log_path.exists():
        log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
    log_event(db, workspace, "preview", "devops", "error",
              f"Preview server did not respond ({detail}).", log_tail)
    return {"running": False, "detail": f"not responding ({detail})"}


def stop_preview(db: Session, workspace: Workspace) -> None:
    if workspace.preview_pid:
        sandbox.stop_process(workspace.preview_pid)
        workspace.preview_pid = None
        workspace.preview_status = "stopped"
        db.commit()
        log_event(db, workspace, "preview", "devops", "preview", "Preview server stopped by founder.")


def ai_repair(db: Session, workspace: Workspace, root: Path, failure_output: str,
              requirement: str) -> bool:
    """Ask the engineers to fix a failing build/test using the real error output."""
    if not ai_available():
        log_event(db, workspace, "build", "backend", "warn",
                  "AI-assisted repair skipped: local model offline. Founder can request a revision instead.")
        return False

    candidate_files: list[str] = []
    for line in failure_output.splitlines():
        for token in line.replace("(", " ").replace(")", " ").split():
            if "/" in token and token.endswith((".js", ".mjs", ".json", ".sql", ".css", ".html")):
                cleaned = token.strip("'\"`,:")
                if "node_modules" in cleaned:
                    continue
                parts = cleaned.split("/")
                for index in range(len(parts)):
                    candidate = "/".join(parts[index:])
                    if (root / candidate).exists() and candidate not in candidate_files:
                        candidate_files.append(candidate)
    candidate_files = candidate_files[:3]
    if not candidate_files:
        log_event(db, workspace, "build", "backend", "warn",
                  "AI-assisted repair could not identify a failing file from the output.")
        return False

    repaired = False
    for path in candidate_files:
        current = read_file(root, path)
        prompt = (
            f"File: {path}\nThis file currently breaks the build or tests.\n"
            f"Current content:\n```\n{current[:14000]}\n```\n\n"
            f"Failure output:\n```\n{failure_output[-6000:]}\n```\n\n"
            "Return the COMPLETE corrected file so that the build and tests pass. "
            'Schema: {"path": string, "content": string, "language": string, "summary": string, "notes": [string]}'
        )
        run = AgentRun(workspace_id=workspace.id, phase="build", agent_id="backend", engine="ai",
                       model=model_name(), status="running", prompt=prompt[:20000],
                       started_at=datetime.now(timezone.utc))
        db.add(run)
        db.commit()
        try:
            payload, _raw = generate_json(
                f"{agent_prompt('backend')}\n\nClient requirement:\n{requirement}\n\n{prompt}",
                "see prompt", validate_code, temperature=0.05,
            )
        except (AIInvalidOutput, ContractError, AIUnavailable) as exc:
            run.status = "failed"
            run.validation_error = str(exc)[:2000]
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            log_event(db, workspace, "build", "backend", "warn",
                      f"AI repair for {path} failed: {exc}")
            continue
        if payload["path"] != path:
            run.status = "rejected"
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            continue
        write_file(root, path, payload["content"], agent_id="backend", phase="build",
                   is_ai_generated=True, db=db, workspace=workspace)
        run.status = "succeeded"
        run.response = payload["content"][:40000]
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        log_event(db, workspace, "build", "backend", "repair",
                  f"AI engineer rewrote {path} to fix the failure.", payload.get("summary"))
        repaired = True
    return repaired


def run_to_completion(db: Session, project: Project) -> Workspace:
    """Generate analysis, auto-approve nothing, then build if approved."""
    workspace = generate(db, project)
    return workspace


def record_failure(db: Session, project: Project, phase: str, error: Exception) -> None:
    workspace = project.workspace
    if not workspace:
        return
    workspace.status = "failed"
    db.commit()
    log_event(db, workspace, phase, "ceo", "error",
              f"{type(error).__name__}: {error}",
              traceback.format_exc()[-6000:])
