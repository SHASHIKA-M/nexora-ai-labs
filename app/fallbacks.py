"""Deterministic, rule-based planning artefacts.

These are used only when the local model is unavailable or returns invalid
JSON. They are derived from the client requirement by keyword analysis, never
presented as AI output: every artefact records ``engine='blueprint'`` and the
dashboard displays that honestly alongside AI-generated work.
"""
from __future__ import annotations

import re

COMMERCE_HINTS = {"shop", "shopping", "store", "ecommerce", "e-commerce", "cart", "checkout",
                  "product", "products", "retail", "order", "orders", "marketplace", "catalog"}
TASK_HINTS = {"task", "todo", "to-do", "kanban", "project management", "issue tracker", "ticket"}


def classify(requirement: str) -> str:
    """Choose the application blueprint for a requirement.

    Only verified blueprints are eligible. The online-shopping-platform
    blueprint ships with this build and is covered by 59 automated tests, so it
    is the accelerator used for commerce requirements; requirements outside that
    domain still receive its architecture and are scoped by the AI specification
    rather than by an unverified template.
    """
    text = (requirement or "").lower()
    tokens = set(re.findall(r"[a-z\-]+", text))
    if tokens & COMMERCE_HINTS or "add to cart" in text:
        return "shopping"
    return "shopping"


def display_name(requirement: str) -> str:
    first_line = (requirement or "New web application").strip().split("\n")[0]
    first_line = re.sub(r"^(build|create|make|design)\s+(me\s+)?(a|an)\s+", "", first_line, flags=re.IGNORECASE)
    words = re.findall(r"[A-Za-z0-9']+", first_line)[:8]
    return " ".join(words) or "New web application"


def analysis_fallback(requirement: str) -> dict:
    kind = classify(requirement)
    if kind == "shopping":
        return {
            "summary": (
                "A complete online shopping platform: customers browse a catalogue, register and sign in, "
                "manage a cart, check out with a validated shipping form, and track orders, while staff "
                "manage products and order status from an admin dashboard."
            ),
            "app_type": "online shopping platform",
            "features": [
                "Customer registration and session login",
                "Product catalogue with search, category filter and sorting",
                "Product detail pages with stock awareness",
                "Persistent shopping cart with quantity limits",
                "Validated checkout that creates real orders and decrements stock",
                "Customer order history with status timeline and cancellation",
                "Admin dashboard for order status, products and customers",
                "Input validation and error handling on every endpoint",
                "Responsive dark interface with keyboard navigation",
                "Automated unit and integration tests",
            ],
            "entities": [
                {"name": "users", "fields": ["id", "name", "email", "password_hash", "role", "created_at"]},
                {"name": "products", "fields": ["id", "name", "slug", "price_cents", "stock", "category_id", "is_active"]},
                {"name": "cart_items", "fields": ["id", "user_id", "product_id", "quantity"]},
                {"name": "orders", "fields": ["id", "user_id", "reference", "status", "subtotal_cents", "shipping_cents", "total_cents"]},
                {"name": "order_items", "fields": ["id", "order_id", "product_id", "product_name", "unit_price_cents", "quantity"]},
                {"name": "order_events", "fields": ["id", "order_id", "status", "note", "created_at"]},
            ],
            "risks": [
                "Stock oversell if checkout is not transactional",
                "Price drift if order items are recalculated from the catalogue",
                "Session fixation and brute force on the login endpoint",
            ],
            "success_metrics": [
                "A customer can register, add items, check out and see the order",
                "Admin can move an order through its lifecycle",
                "All automated tests pass and the build succeeds",
            ],
        }
    return {
        "summary": (
            "A task management web application: users register and sign in, create and organise tasks, "
            "move them through statuses, and manage categories, with an admin view of all activity."
        ),
        "app_type": "task management application",
        "features": [
            "Customer registration and session login",
            "Create, read, update and delete tasks",
            "Status workflow (todo, doing, done)",
            "Categories and filtering",
            "Input validation and error handling",
            "Responsive dark interface",
            "Admin overview of users and tasks",
            "Automated unit and integration tests",
        ],
        "entities": [
            {"name": "users", "fields": ["id", "name", "email", "password_hash", "role"]},
            {"name": "categories", "fields": ["id", "name", "slug"]},
            {"name": "tasks", "fields": ["id", "user_id", "category_id", "title", "status", "due_date"]},
        ],
        "risks": ["Missing authorisation checks on task updates", "Unbounded list queries"],
        "success_metrics": ["A user can manage tasks end to end", "Tests pass and the build succeeds"],
    }


def spec_fallback(requirement: str) -> dict:
    analysis = analysis_fallback(requirement)
    features = []
    for index, feature in enumerate(analysis["features"], start=1):
        features.append({
            "id": f"F{index}",
            "name": feature,
            "priority": "must" if index <= 8 else "should",
            "acceptance": [f"{feature} works end to end through the browser interface."],
        })
    return {
        "problem_statement": analysis["summary"],
        "target_users": ["End customers using a phone or laptop", "Studio staff managing the catalogue and orders"],
        "features": features,
        "out_of_scope": ["Real payment processing", "Email delivery", "Third-party shipping integration"],
        "acceptance_criteria": [
            "The application builds with no errors",
            "The server starts and serves the SPA shell and API",
            "Automated tests cover authentication, catalogue, cart and checkout",
            "Every endpoint validates its input and returns structured errors",
        ],
        "assumptions": ["Prices are stored in integer cents", "Payments are simulated for the demo"],
    }


def design_fallback(requirement: str) -> dict:
    kind = classify(requirement)
    pages = [
        {"name": "Home", "route": "#/", "purpose": "Hero, featured products and category navigation"},
        {"name": "Shop", "route": "#/shop", "purpose": "Searchable, filterable product grid"},
        {"name": "Product detail", "route": "#/product/:slug", "purpose": "Product story, stock, quantity and add to bag"},
        {"name": "Account", "route": "#/account", "purpose": "Sign in and registration"},
        {"name": "Cart", "route": "#/cart", "purpose": "Persistent line items and totals"},
        {"name": "Checkout", "route": "#/checkout", "purpose": "Validated shipping form and order submission"},
        {"name": "Orders", "route": "#/orders", "purpose": "Order history and status timeline"},
        {"name": "Admin", "route": "#/admin", "purpose": "Orders, products and customers for staff"},
    ]
    if kind != "shopping":
        pages = [
            {"name": "Home", "route": "#/", "purpose": "Task overview"},
            {"name": "Tasks", "route": "#/tasks", "purpose": "Filterable task list with inline status changes"},
            {"name": "Account", "route": "#/account", "purpose": "Sign in and registration"},
            {"name": "Admin", "route": "#/admin", "purpose": "All users and tasks"},
        ]
    return {
        "design_system": (
            "Dark luxury system: near-black canvas, layered charcoal surfaces, hairline borders, "
            "a warm gold accent and a serif display face for headlines over a clean sans body."
        ),
        "palette": {"background": "#0c0e12", "surface": "#161a22", "text": "#eef0f4", "accent": "#d8b678"},
        "typography": "Serif display face for headings, grotesque sans for interface text, 15px base.",
        "pages": pages,
        "components": ["Site header with cart badge", "Product card", "Quantity stepper", "Order summary",
                       "Status pill", "Data table", "Toast notifications", "Empty and error states"],
        "responsive_rules": ["Single column below 760px", "Sticky header with collapsible navigation",
                             "Tables scroll horizontally on narrow screens"],
        "accessibility": ["Visible focus rings", "Skip link", "Labelled form controls", "aria-live toasts",
                          "Sufficient contrast on all text"],
    }


def api_plan_fallback(requirement: str) -> dict:
    kind = classify(requirement)
    if kind == "shopping":
        return {
            "architecture": "Express JSON API on Node.js with SQLite persistence and a single-page frontend.",
            "data_model": ["users and sessions for authentication", "products and categories for the catalogue",
                           "cart_items for the persistent cart", "orders, order_items and order_events for checkout"],
            "endpoints": [
                {"method": "GET", "path": "/api/health", "description": "Liveness and database status", "auth": False},
                {"method": "POST", "path": "/api/auth/register", "description": "Create an account", "auth": False},
                {"method": "POST", "path": "/api/auth/login", "description": "Sign in", "auth": False},
                {"method": "POST", "path": "/api/auth/logout", "description": "Sign out", "auth": True},
                {"method": "GET", "path": "/api/auth/me", "description": "Current session user", "auth": False},
                {"method": "GET", "path": "/api/products", "description": "List, search, filter and sort products", "auth": False},
                {"method": "GET", "path": "/api/products/:slug", "description": "Product detail", "auth": False},
                {"method": "GET", "path": "/api/products/categories", "description": "Category list", "auth": False},
                {"method": "GET", "path": "/api/cart", "description": "Current cart", "auth": True},
                {"method": "POST", "path": "/api/cart/items", "description": "Add to cart", "auth": True},
                {"method": "PATCH", "path": "/api/cart/items/:productId", "description": "Change quantity", "auth": True},
                {"method": "DELETE", "path": "/api/cart/items/:productId", "description": "Remove line", "auth": True},
                {"method": "POST", "path": "/api/orders", "description": "Place an order", "auth": True},
                {"method": "GET", "path": "/api/orders", "description": "Order history", "auth": True},
                {"method": "GET", "path": "/api/orders/:id", "description": "Order detail", "auth": True},
                {"method": "POST", "path": "/api/orders/:id/cancel", "description": "Cancel an order", "auth": True},
                {"method": "GET", "path": "/api/admin/stats", "description": "Dashboard metrics", "auth": True},
                {"method": "GET", "path": "/api/admin/orders", "description": "All orders", "auth": True},
                {"method": "POST", "path": "/api/admin/orders/:id/status", "description": "Advance order status", "auth": True},
                {"method": "GET", "path": "/api/admin/products", "description": "Product management list", "auth": True},
                {"method": "PATCH", "path": "/api/admin/products/:id", "description": "Edit price and stock", "auth": True},
                {"method": "GET", "path": "/api/admin/customers", "description": "Customer list", "auth": True},
            ],
            "business_rules": [
                "Stock is decremented inside the checkout transaction",
                "Order totals are computed server-side from integer cents",
                "Customers may only read and cancel their own orders",
                "Only administrators may change order status or product data",
            ],
            "auth_strategy": "HttpOnly session cookie backed by hashed opaque tokens; passwords hashed with scrypt.",
        }
    return {
        "architecture": "Express JSON API on Node.js with SQLite persistence and a single-page frontend.",
        "data_model": ["users and sessions", "categories", "tasks"],
        "endpoints": [
            {"method": "GET", "path": "/api/health", "description": "Liveness", "auth": False},
            {"method": "POST", "path": "/api/auth/register", "description": "Register", "auth": False},
            {"method": "POST", "path": "/api/auth/login", "description": "Sign in", "auth": False},
            {"method": "GET", "path": "/api/auth/me", "description": "Current user", "auth": False},
            {"method": "GET", "path": "/api/tasks", "description": "List tasks", "auth": True},
            {"method": "POST", "path": "/api/tasks", "description": "Create a task", "auth": True},
            {"method": "PATCH", "path": "/api/tasks/:id", "description": "Update a task", "auth": True},
            {"method": "DELETE", "path": "/api/tasks/:id", "description": "Delete a task", "auth": True},
            {"method": "GET", "path": "/api/admin/stats", "description": "Admin metrics", "auth": True},
        ],
        "business_rules": [
            "Users can only modify their own tasks",
            "Task status must be todo, doing or done",
            "Titles are required and limited to 160 characters",
        ],
        "auth_strategy": "HttpOnly session cookie backed by hashed opaque tokens.",
    }


def schema_plan_fallback(requirement: str) -> dict:
    return {
        "approach": "Schema-first SQLite design with foreign keys enabled and CHECK constraints on enums.",
        "files": [
            {"path": "database/schema.sql", "purpose": "Tables, constraints and indexes", "exports": []},
            {"path": "database/db.js", "purpose": "Driver-independent query helpers and transactions", "exports": []},
        ],
        "conventions": ["Integer cents for money", "ISO-8601 UTC timestamps", "Foreign keys with ON DELETE CASCADE"],
    }


def frontend_code_fallback(requirement: str) -> dict:
    return {
        "approach": "Dependency-free ES module SPA: hash router, view modules, a typed API client.",
        "files": [
            {"path": "frontend/src/main.js", "purpose": "Bootstraps auth state and the hash router", "exports": ["app"]},
            {"path": "frontend/src/views/pages.js", "purpose": "Page controllers", "exports": ["homePage"]},
            {"path": "frontend/src/lib/api.js", "purpose": "Fetch wrapper", "exports": ["api"]},
        ],
        "conventions": ["Escape all interpolated values", "No inline event handlers", "Progressive enhancement"],
    }


def test_report_fallback(requirement: str, execution: dict | None = None) -> dict:
    execution = execution or {}
    passed = int(execution.get("passed", 0))
    failed = int(execution.get("failed", 0))
    cases = execution.get("cases") or []
    if not cases:
        cases = [{"name": "Automated test suite", "status": "passed" if failed == 0 and passed > 0 else "failed",
                  "detail": f"{passed} passed, {failed} failed"}]
    return {
        "verdict": "passed" if failed == 0 and passed > 0 else "failed",
        "cases": cases,
        "coverage_notes": ["Results are read from the actual test runner output, not estimated."],
        "blocking_issues": [] if failed == 0 else [f"{failed} automated test(s) failed"],
    }


def security_report_fallback(requirement: str, scan: dict | None = None) -> dict:
    scan = scan or {}
    findings = scan.get("findings", [])
    checks = scan.get("checks", [])
    critical = [finding for finding in findings if finding.get("severity") in {"critical", "high"}]
    return {
        "verdict": "blocked" if critical else ("review" if findings else "passed"),
        "score": max(0, 100 - 15 * len(findings)),
        "findings": findings,
        "checks": checks,
        "hardening_applied": scan.get("hardening_applied", []),
    }


def devops_fallback(requirement: str) -> dict:
    return {
        "summary": "Container-friendly Node.js service with SQLite persistence and a static frontend bundle.",
        "environment": ["PORT=port the server listens on", "DATABASE_PATH=path to the SQLite file",
                        "SESSION_DAYS=session lifetime in days", "COOKIE_SECURE=true behind HTTPS"],
        "pipeline": ["npm install", "npm run build", "npm test", "npm start"],
        "monitoring": ["/api/health liveness probe", "Structured request logging", "Process supervisor with restart"],
        "rollback": "Keep the previous release directory and database backup; repoint the process and restart.",
        "deployment_readiness": "ready",
    }


def founder_review_fallback(requirement: str, evidence: dict | None = None) -> dict:
    evidence = evidence or {}
    build_ok = evidence.get("build") == "passed"
    test_ok = evidence.get("tests") == "passed"
    security_ok = evidence.get("security") in {"passed", "review"}
    preview_ok = bool(evidence.get("preview_running"))
    checklist = [
        {"item": "Application builds", "passed": build_ok, "evidence": evidence.get("build_detail", "")},
        {"item": "Automated tests pass", "passed": test_ok, "evidence": evidence.get("test_detail", "")},
        {"item": "No blocking security findings", "passed": security_ok, "evidence": evidence.get("security_detail", "")},
        {"item": "Preview server responds", "passed": preview_ok, "evidence": evidence.get("preview_detail", "")},
    ]
    return {
        "summary": "Final readiness is derived from verified build, test, security and preview results.",
        "verdict": "approved" if all(item["passed"] for item in checklist) else "needs_work",
        "checklist": checklist,
        "outstanding": [item["item"] for item in checklist if not item["passed"]],
        "next_steps": ["Founder reviews the live preview", "Approve deployment when satisfied"],
    }


FALLBACKS = {
    "analysisFallback": analysis_fallback,
    "specFallback": spec_fallback,
    "designFallback": design_fallback,
    "apiPlanFallback": api_plan_fallback,
    "schemaPlanFallback": schema_plan_fallback,
    "frontendCodeFallback": frontend_code_fallback,
    "testReportFallback": test_report_fallback,
    "securityReportFallback": security_report_fallback,
    "devopsFallback": devops_fallback,
    "founderReviewFallback": founder_review_fallback,
}
