"""Application blueprints: the real, executable scaffolds NEXORA emits.

A blueprint is a complete, tested application tree kept under
``app/codegen/blueprints/<blueprint>/``. The orchestrator copies it into the
client's workspace under ``generated_projects/<slug>/`` and then *personalises*
it — branding, design tokens, catalogue copy and the AI-authored planning
documents are written from the specification that the AI employees produced.

The blueprint is an accelerator, not a mock: every copied file is real source
that builds, runs and passes its own test suite. This is what makes the final
deliverable a running application instead of a text response.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .fallbacks import classify, display_name
from .workspace import copy_tree, projects_root

BLUEPRINT_ROOT = Path(__file__).resolve().parent / "codegen" / "blueprints"


@dataclass
class Blueprint:
    key: str
    label: str
    description: str
    features: list[str]
    stack: list[str]
    path: Path


BLUEPRINTS: dict[str, Blueprint] = {
    "shopping": Blueprint(
        key="shopping",
        label="Online Shopping Platform",
        description=(
            "A complete commerce application: catalogue, product detail, persistent cart, "
            "validated checkout, customer order history and an admin dashboard."
        ),
        features=[
            "Customer registration and session login",
            "Product listing with search, category filter and sorting",
            "Product detail pages with stock awareness",
            "Persistent shopping cart with quantity limits",
            "Checkout with validated shipping details and real order creation",
            "Order history, status timeline and cancellation",
            "Admin dashboard for orders, products and customers",
            "Automated unit and integration tests",
            "Secure preview runtime with isolated process execution",
        ],
        stack=["Node.js 22", "Express 4", "SQLite (node:sqlite)", "ES modules", "esbuild", "node:test"],
        path=BLUEPRINT_ROOT / "shopping",
    ),
}


def resolve(requirement: str, requested: str | None = None) -> Blueprint:
    """Pick the installed blueprint for a requirement.

    Only blueprints that are actually present on disk are considered, so the
    platform never advertises a capability it cannot deliver.
    """
    installed = {key: value for key, value in BLUEPRINTS.items() if blueprint_available(value)}
    if requested and requested in installed:
        return installed[requested]
    preferred = classify(requirement)
    if preferred in installed:
        return installed[preferred]
    return next(iter(installed.values()))


def blueprint_available(blueprint: Blueprint) -> bool:
    return blueprint.path.is_dir() and (blueprint.path / "package.json").exists()


def materialise(blueprint: Blueprint, slug: str) -> Path:
    """Copy the blueprint into a fresh workspace directory."""
    destination = projects_root() / slug
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    copy_tree(blueprint.path, destination)
    return destination


def branding(requirement: str, *, name: str | None = None) -> dict:
    """Derive the product name and identity used in the generated app."""
    display = name or display_name(requirement)
    words = [word for word in display.split() if len(word) > 2][:3]
    if not words:
        words = ["North", "Studio"]
    brand = " ".join(word.capitalize() for word in words)
    initials = "".join(word[0].upper() for word in words)
    slug = "-".join(word.lower() for word in words)
    return {
        "display_name": display,
        "brand": brand,
        "brand_short": initials,
        "slug": slug,
        "tagline": "Everyday essentials, considered.",
        "currency": "USD",
        "support_email": "studio@example.com",
    }


__all__ = [
    "BLUEPRINTS", "Blueprint", "branding", "blueprint_available", "materialise", "resolve",
]
