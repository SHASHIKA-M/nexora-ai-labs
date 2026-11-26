"""Structured AI workflows for the eleven pipeline stages.

Each AI employee has:

* ``instruction`` — the specialist system brief (kept from the original app),
* ``schema``      — the exact JSON contract the model must return,
* ``validate``    — a defensive validator that normalises/clamps model output,
* ``deterministic``— a rule-based fallback used when the local model is offline.

The fallback is never presented as AI output: the orchestrator records which
engine produced each artefact (``ai`` vs ``blueprint``) and the dashboard shows
it. Nothing is fabricated.
"""
from __future__ import annotations

from typing import Any, Callable

from .agents import AGENT_BY_ID


class ContractError(ValueError):
    """Structured output did not satisfy the contract."""


def _text(value: Any, field: str, *, max_length: int = 4000, required: bool = True) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if required and not value:
        raise ContractError(f"'{field}' must be a non-empty string.")
    return value[:max_length]


def _list_of_text(value: Any, field: str, *, max_items: int = 30, item_length: int = 400) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [line.strip("-• ").strip() for line in value.split("\n") if line.strip()]
    if not isinstance(value, list):
        raise ContractError(f"'{field}' must be a list of strings.")
    cleaned: list[str] = []
    for item in value[:max_items]:
        if isinstance(item, dict):
            item = ", ".join(f"{k}: {v}" for k, v in item.items())
        item_text = str(item).strip()
        if item_text:
            cleaned.append(item_text[:item_length])
    return cleaned


def _int(value: Any, field: str, *, minimum: int = 0, maximum: int = 10_000, default: int = 0) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #

def validate_analysis(payload: dict) -> dict:
    summary = _text(payload.get("summary"), "summary", max_length=2000)
    features = _list_of_text(payload.get("features"), "features", max_items=25)
    if not features:
        raise ContractError("'features' must list at least one capability.")
    entities = payload.get("entities") or []
    normalised_entities: list[dict] = []
    if isinstance(entities, list):
        for entity in entities[:20]:
            if isinstance(entity, str):
                normalised_entities.append({"name": entity.strip()[:60], "fields": []})
            elif isinstance(entity, dict):
                normalised_entities.append({
                    "name": _text(entity.get("name"), "entities[].name", max_length=60),
                    "fields": _list_of_text(entity.get("fields"), "entities[].fields", max_items=30, item_length=80),
                })
    return {
        "summary": summary,
        "app_type": _text(payload.get("app_type"), "app_type", max_length=60, required=False) or "web application",
        "features": features,
        "entities": normalised_entities,
        "risks": _list_of_text(payload.get("risks"), "risks", max_items=12),
        "success_metrics": _list_of_text(payload.get("success_metrics"), "success_metrics", max_items=12),
    }


def validate_spec(payload: dict) -> dict:
    features = payload.get("features") or []
    normalised: list[dict] = []
    if isinstance(features, list):
        for index, feature in enumerate(features[:25], start=1):
            if isinstance(feature, str):
                normalised.append({"id": f"F{index}", "name": feature[:120], "priority": "must", "acceptance": []})
            elif isinstance(feature, dict):
                normalised.append({
                    "id": _text(feature.get("id") or f"F{index}", "features[].id", max_length=10),
                    "name": _text(feature.get("name"), "features[].name", max_length=120),
                    "priority": (_text(feature.get("priority") or "must", "features[].priority", max_length=10) or "must").lower(),
                    "acceptance": _list_of_text(feature.get("acceptance"), "features[].acceptance", max_items=8),
                })
    if not normalised:
        raise ContractError("'features' must contain at least one feature with a name.")
    return {
        "problem_statement": _text(payload.get("problem_statement"), "problem_statement", max_length=3000),
        "target_users": _list_of_text(payload.get("target_users"), "target_users", max_items=10),
        "features": normalised,
        "out_of_scope": _list_of_text(payload.get("out_of_scope"), "out_of_scope", max_items=15),
        "acceptance_criteria": _list_of_text(payload.get("acceptance_criteria"), "acceptance_criteria", max_items=20),
        "assumptions": _list_of_text(payload.get("assumptions"), "assumptions", max_items=12),
    }


def validate_design(payload: dict) -> dict:
    pages = payload.get("pages") or []
    normalised_pages: list[dict] = []
    if isinstance(pages, list):
        for page in pages[:20]:
            if isinstance(page, str):
                page = {"name": page, "route": "#/" + page.lower().replace(" ", "-"), "purpose": ""}
            if isinstance(page, dict):
                normalised_pages.append({
                    "name": _text(page.get("name"), "pages[].name", max_length=80),
                    "route": _text(page.get("route") or "/", "pages[].route", max_length=80),
                    "purpose": _text(page.get("purpose") or "", "pages[].purpose", max_length=400, required=False),
                })
    if not normalised_pages:
        raise ContractError("'pages' must contain at least one page.")
    palette = payload.get("palette") if isinstance(payload.get("palette"), dict) else {}
    return {
        "design_system": _text(payload.get("design_system"), "design_system", max_length=3000),
        "palette": {
            "background": _text(palette.get("background") or "#0c0e12", "palette.background", max_length=20),
            "surface": _text(palette.get("surface") or "#161a22", "palette.surface", max_length=20),
            "text": _text(palette.get("text") or "#eef0f4", "palette.text", max_length=20),
            "accent": _text(palette.get("accent") or "#d8b678", "palette.accent", max_length=20),
        },
        "typography": _text(payload.get("typography") or "A serif display face paired with a clean sans body.", "typography", max_length=400),
        "pages": normalised_pages,
        "components": _list_of_text(payload.get("components"), "components", max_items=25),
        "responsive_rules": _list_of_text(payload.get("responsive_rules"), "responsive_rules", max_items=10),
        "accessibility": _list_of_text(payload.get("accessibility"), "accessibility", max_items=12),
    }


def validate_api_plan(payload: dict) -> dict:
    endpoints = payload.get("endpoints") or []
    normalised: list[dict] = []
    if isinstance(endpoints, list):
        for endpoint in endpoints[:40]:
            if isinstance(endpoint, str):
                parts = endpoint.split()
                if len(parts) >= 2:
                    endpoint = {"method": parts[0], "path": parts[1]}
                else:
                    endpoint = {"method": "GET", "path": parts[0]}
            if isinstance(endpoint, dict):
                method = (_text(endpoint.get("method") or "GET", "endpoints[].method", max_length=10) or "GET").upper()
                path = _text(endpoint.get("path"), "endpoints[].path", max_length=120)
                if not path.startswith("/"):
                    path = "/" + path
                normalised.append({
                    "method": method if method in {"GET", "POST", "PATCH", "PUT", "DELETE"} else "GET",
                    "path": path,
                    "description": _text(endpoint.get("description") or "", "endpoints[].description", max_length=300, required=False),
                    "auth": bool(endpoint.get("auth", False)),
                })
    if not normalised:
        raise ContractError("'endpoints' must contain at least one endpoint.")
    return {
        "architecture": _text(payload.get("architecture"), "architecture", max_length=2000),
        "data_model": _list_of_text(payload.get("data_model"), "data_model", max_items=20),
        "endpoints": normalised,
        "business_rules": _list_of_text(payload.get("business_rules"), "business_rules", max_items=20),
        "auth_strategy": _text(payload.get("auth_strategy") or "Session cookies with hashed opaque tokens.", "auth_strategy", max_length=600),
    }


def validate_file_plan(payload: dict) -> dict:
    """A code-generation plan: which files an engineer will write and why."""
    files = payload.get("files") or []
    normalised: list[dict] = []
    if isinstance(files, list):
        for entry in files[:25]:
            if isinstance(entry, str):
                entry = {"path": entry, "purpose": "", "exports": []}
            if not isinstance(entry, dict):
                continue
            path = _text(entry.get("path"), "files[].path", max_length=200)
            if path.startswith("/") or ".." in path:
                raise ContractError(f"Unsafe file path in plan: {path}")
            normalised.append({
                "path": path,
                "purpose": _text(entry.get("purpose") or "", "files[].purpose", max_length=300, required=False),
                "exports": _list_of_text(entry.get("exports"), "files[].exports", max_items=15, item_length=80),
            })
    if not normalised:
        raise ContractError("'files' must list at least one file to create.")
    return {
        "approach": _text(payload.get("approach"), "approach", max_length=2000),
        "files": normalised,
        "conventions": _list_of_text(payload.get("conventions"), "conventions", max_items=15),
    }


def validate_code(payload: dict) -> dict:
    """One generated source file, returned by a developer agent."""
    path = _text(payload.get("path"), "path", max_length=200)
    if path.startswith("/") or ".." in path or path.endswith("/"):
        raise ContractError(f"Unsafe or invalid file path: {path}")
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ContractError("'content' must be the complete file contents.")
    if len(content.encode("utf-8")) > 512 * 1024:
        raise ContractError("'content' exceeds the 512 KB per-file limit.")
    if "```" in content and content.strip().startswith("```"):
        raise ContractError("'content' must not be wrapped in markdown fences.")
    return {
        "path": path,
        "content": content,
        "language": _text(payload.get("language") or "", "language", max_length=30, required=False) or None,
        "summary": _text(payload.get("summary") or "Generated file.", "summary", max_length=500, required=False),
        "notes": _list_of_text(payload.get("notes"), "notes", max_items=10),
    }


def validate_test_report(payload: dict) -> dict:
    cases = payload.get("cases") or []
    normalised: list[dict] = []
    if isinstance(cases, list):
        for case in cases[:60]:
            if isinstance(case, str):
                case = {"name": case, "status": "passed"}
            if isinstance(case, dict):
                status = (_text(case.get("status") or "passed", "cases[].status", max_length=10) or "passed").lower()
                normalised.append({
                    "name": _text(case.get("name"), "cases[].name", max_length=160),
                    "status": status if status in {"passed", "failed", "skipped"} else "failed",
                    "detail": _text(case.get("detail") or "", "cases[].detail", max_length=300, required=False),
                })
    if not normalised:
        raise ContractError("'cases' must contain at least one test case.")
    return {
        "verdict": (_text(payload.get("verdict") or "unknown", "verdict", max_length=20) or "unknown").lower(),
        "cases": normalised,
        "coverage_notes": _list_of_text(payload.get("coverage_notes"), "coverage_notes", max_items=12),
        "blocking_issues": _list_of_text(payload.get("blocking_issues"), "blocking_issues", max_items=12),
    }


def _severity(value: Any) -> str:
    text = str(value or "low").strip().lower()
    return text if text in {"critical", "high", "medium", "low", "info"} else "low"


def validate_security_report(payload: dict) -> dict:
    findings = payload.get("findings") or []
    normalised: list[dict] = []
    if isinstance(findings, list):
        for finding in findings[:30]:
            if isinstance(finding, str):
                finding = {"title": finding, "severity": "low"}
            if isinstance(finding, dict):
                normalised.append({
                    "title": _text(finding.get("title"), "findings[].title", max_length=160),
                    "severity": _severity(finding.get("severity")),
                    "area": _text(finding.get("area") or "general", "findings[].area", max_length=60, required=False),
                    "recommendation": _text(finding.get("recommendation") or "", "findings[].recommendation", max_length=600, required=False),
                })
    checks = payload.get("checks") or []
    normalised_checks: list[dict] = []
    if isinstance(checks, list):
        for check in checks[:30]:
            if isinstance(check, str):
                check = {"name": check, "passed": True}
            if isinstance(check, dict):
                normalised_checks.append({
                    "name": _text(check.get("name"), "checks[].name", max_length=160),
                    "passed": bool(check.get("passed", False)),
                    "detail": _text(check.get("detail") or "", "checks[].detail", max_length=300, required=False),
                })
    score = _int(payload.get("score"), "score", minimum=0, maximum=100, default=70)
    return {
        "verdict": (_text(payload.get("verdict") or "review", "verdict", max_length=20) or "review").lower(),
        "score": score,
        "findings": normalised,
        "checks": normalised_checks,
        "hardening_applied": _list_of_text(payload.get("hardening_applied"), "hardening_applied", max_items=20),
    }


def validate_devops_plan(payload: dict) -> dict:
    return {
        "summary": _text(payload.get("summary"), "summary", max_length=2000),
        "environment": _list_of_text(payload.get("environment"), "environment", max_items=20, item_length=160),
        "pipeline": _list_of_text(payload.get("pipeline"), "pipeline", max_items=20),
        "monitoring": _list_of_text(payload.get("monitoring"), "monitoring", max_items=15),
        "rollback": _text(payload.get("rollback") or "", "rollback", max_length=1200, required=False),
        "deployment_readiness": (_text(payload.get("deployment_readiness") or "pending", "deployment_readiness", max_length=30) or "pending").lower(),
    }


def validate_founder_review(payload: dict) -> dict:
    checklist = payload.get("checklist") or []
    normalised: list[dict] = []
    if isinstance(checklist, list):
        for item in checklist[:30]:
            if isinstance(item, str):
                item = {"item": item, "passed": True}
            if isinstance(item, dict):
                normalised.append({
                    "item": _text(item.get("item"), "checklist[].item", max_length=200),
                    "passed": bool(item.get("passed", False)),
                    "evidence": _text(item.get("evidence") or "", "checklist[].evidence", max_length=300, required=False),
                })
    if not normalised:
        raise ContractError("'checklist' must contain at least one item.")
    return {
        "summary": _text(payload.get("summary"), "summary", max_length=3000),
        "verdict": (_text(payload.get("verdict") or "needs_work", "verdict", max_length=30) or "needs_work").lower(),
        "checklist": normalised,
        "outstanding": _list_of_text(payload.get("outstanding"), "outstanding", max_items=15),
        "next_steps": _list_of_text(payload.get("next_steps"), "next_steps", max_items=15),
    }


CONTRACTS: dict[str, dict] = {
    "ceo": {
        "phase": "analysis",
        "title": "Requirement analysis",
        "schema": """{
  "summary": "string — what the client is really asking for",
  "app_type": "string — e.g. online shopping platform",
  "features": ["string — required capability"],
  "entities": [{"name": "string", "fields": ["string"]}],
  "risks": ["string"],
  "success_metrics": ["string"]
}""",
        "validate": validate_analysis,
        "fallback": "analysisFallback",
    },
    "product": {
        "phase": "specification",
        "title": "Technical specification",
        "schema": """{
  "problem_statement": "string",
  "target_users": ["string"],
  "features": [{"id": "F1", "name": "string", "priority": "must|should|could", "acceptance": ["string"]}],
  "out_of_scope": ["string"],
  "acceptance_criteria": ["string"],
  "assumptions": ["string"]
}""",
        "validate": validate_spec,
        "fallback": "specFallback",
    },
    "design": {
        "phase": "design",
        "title": "Design system and page structure",
        "schema": """{
  "design_system": "string",
  "palette": {"background": "#hex", "surface": "#hex", "text": "#hex", "accent": "#hex"},
  "typography": "string",
  "pages": [{"name": "string", "route": "#/route", "purpose": "string"}],
  "components": ["string"],
  "responsive_rules": ["string"],
  "accessibility": ["string"]
}""",
        "validate": validate_design,
        "fallback": "designFallback",
    },
    "backend": {
        "phase": "api_design",
        "title": "API and data plan",
        "schema": """{
  "architecture": "string",
  "data_model": ["string — table/collection and purpose"],
  "endpoints": [{"method": "GET|POST|PATCH|PUT|DELETE", "path": "/api/...", "description": "string", "auth": true}],
  "business_rules": ["string"],
  "auth_strategy": "string"
}""",
        "validate": validate_api_plan,
        "fallback": "apiPlanFallback",
    },
    "database": {
        "phase": "api_design",
        "title": "Data schema review",
        "schema": """{
  "approach": "string",
  "files": [{"path": "database/schema.sql", "purpose": "string", "exports": []}],
  "conventions": ["string"]
}""",
        "validate": validate_file_plan,
        "fallback": "schemaPlanFallback",
    },
    "frontend": {
        "phase": "implementation",
        "title": "Frontend file plan",
        "schema": """{
  "approach": "string",
  "files": [{"path": "frontend/src/views/home.js", "purpose": "string", "exports": ["pageName"]}],
  "conventions": ["string"]
}""",
        "validate": validate_file_plan,
        "fallback": "frontendCodeFallback",
    },
    "qa": {
        "phase": "testing",
        "title": "Test report",
        "schema": """{
  "verdict": "passed|failed",
  "cases": [{"name": "string", "status": "passed|failed|skipped", "detail": "string"}],
  "coverage_notes": ["string"],
  "blocking_issues": ["string"]
}""",
        "validate": validate_test_report,
        "fallback": "testReportFallback",
    },
    "security": {
        "phase": "security",
        "title": "Security review",
        "schema": """{
  "verdict": "passed|review|blocked",
  "score": 0,
  "checks": [{"name": "string", "passed": true, "detail": "string"}],
  "findings": [{"title": "string", "severity": "critical|high|medium|low|info", "area": "string", "recommendation": "string"}],
  "hardening_applied": ["string"]
}""",
        "validate": validate_security_report,
        "fallback": "securityReportFallback",
    },
    "devops": {
        "phase": "deployment_prep",
        "title": "Deployment readiness",
        "schema": """{
  "summary": "string",
  "environment": ["string — NAME=description"],
  "pipeline": ["string"],
  "monitoring": ["string"],
  "rollback": "string",
  "deployment_readiness": "ready|pending|blocked"
}""",
        "validate": validate_devops_plan,
        "fallback": "devopsFallback",
    },
    "founder": {
        "phase": "founder_review",
        "title": "Founder readiness review",
        "schema": """{
  "summary": "string",
  "verdict": "approved|needs_work|blocked",
  "checklist": [{"item": "string", "passed": true, "evidence": "string"}],
  "outstanding": ["string"],
  "next_steps": ["string"]
}""",
        "validate": validate_founder_review,
        "fallback": "founderReviewFallback",
    },
}


def agent_prompt(agent_id: str) -> str:
    agent = AGENT_BY_ID.get(agent_id, AGENT_BY_ID["backend"])
    base = (
        f"You are the {agent['role']} in the {agent['department']} department at NEXORA AI LABS. "
        f"Your mission: {agent['mission']} "
        "You are working on a real software project that will be built and executed by the platform. "
    )
    special = {
        "ceo": "Analyse the client requirement and decide what must be built. Prefer a realistic, buildable scope.",
        "product": "Write a technical specification precise enough for engineers to implement without guessing.",
        "design": "Define the design system and the exact page inventory. The product is a dark, premium web app.",
        "backend": "Design the HTTP API, data model, business rules and authentication strategy.",
        "database": "Review the persistence design: tables, constraints, indexes and transactions.",
        "frontend": "Plan the client-side files. The frontend is a dependency-free ES module SPA that talks to the API.",
        "qa": "Judge whether the delivered behaviour actually satisfies the specification. Be strict and specific.",
        "security": "Audit authentication, authorisation, input validation, injection, secret handling and headers.",
        "devops": "Prepare environment configuration, verification steps, monitoring and rollback for deployment.",
        "founder": "Perform the final readiness review as the accountable founder's assistant.",
    }.get(agent_id, "")
    return base + special


__all__ = ["CONTRACTS", "ContractError", "agent_prompt", "validate_code"]
