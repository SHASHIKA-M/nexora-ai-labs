"""Real project workspaces on disk.

Every generated application lives in its own folder under
``generated_projects/<slug>``. Source files are written to disk — never stored
as text blobs in the database — and the database only indexes metadata
(path, size, checksum, which agent produced it).
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from .models import ProjectFile, Workspace

REPO_ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {
    ".js", ".mjs", ".cjs", ".json", ".css", ".html", ".md", ".sql", ".yml", ".yaml",
    ".txt", ".env", ".example", ".gitignore", ".nvmrc", ".svg", ".sh", ".py", ".ini",
}
MAX_FILE_BYTES = 512 * 1024          # a single generated file may not exceed 512 KB
MAX_WORKSPACE_FILES = 600            # hard cap so a runaway agent cannot fill the disk

SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI-style secret key"),
    (re.compile(r"mstrl_[A-Za-z0-9_]{20,}"), "Mistral API key"),
    (re.compile(r"ghp_[A-Za-z0-9]{30,}"), "GitHub personal access token"),
    (re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"password\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE), "hard-coded password"),
]


class WorkspaceError(RuntimeError):
    """Raised for unsafe or invalid workspace operations."""


def projects_root() -> Path:
    configured = os.getenv("GENERATED_PROJECTS_DIR")
    root = Path(configured).expanduser() if configured else REPO_ROOT / "generated_projects"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def slugify(value: str, fallback: str = "project") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:60].strip("-")
    return slug or fallback


def unique_slug(db: Session, base: str) -> str:
    slug = slugify(base)
    candidate = slug
    counter = 2
    while db.query(Workspace).filter(Workspace.slug == candidate).first():
        candidate = f"{slug}-{counter}"
        counter += 1
    return candidate


def resolve_within(root: Path, relative: str) -> Path:
    """Resolve a workspace-relative path, refusing to escape the workspace."""
    if not relative or relative.strip() in {"", ".", "/"}:
        raise WorkspaceError("A file path is required.")
    if relative.replace("\\", "/").startswith("/"):
        raise WorkspaceError(f"Absolute paths are not allowed: {relative}")
    cleaned = relative.replace("\\", "/").lstrip("/")
    if cleaned.startswith("../") or "/../" in cleaned or cleaned == "..":
        raise WorkspaceError(f"Refusing path traversal: {relative}")
    if re.match(r"^[A-Za-z]:", cleaned):
        raise WorkspaceError(f"Absolute paths are not allowed: {relative}")
    target = (root / cleaned).resolve()
    root_resolved = root.resolve()
    if root_resolved != target and root_resolved not in target.parents:
        raise WorkspaceError(f"Refusing to write outside the workspace: {relative}")
    return target


@dataclass
class WrittenFile:
    path: str
    size_bytes: int
    lines: int
    checksum: str


def write_file(
    root: Path,
    relative: str,
    content: str,
    *,
    agent_id: str = "backend",
    phase: str = "implementation",
    is_ai_generated: bool = False,
    is_template: bool = False,
    db: Session | None = None,
    workspace: Workspace | None = None,
) -> WrittenFile:
    """Write one real file inside the workspace and index it in the database."""
    if not isinstance(content, str):
        raise WorkspaceError(f"Content for {relative} must be text.")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_FILE_BYTES:
        raise WorkspaceError(
            f"{relative} is {len(encoded) // 1024} KB which exceeds the {MAX_FILE_BYTES // 1024} KB limit."
        )
    target = resolve_within(root, relative)

    if db is not None and workspace is not None:
        existing = (
            db.query(ProjectFile)
            .filter(ProjectFile.workspace_id == workspace.id, ProjectFile.path == relative.replace("\\", "/").lstrip("/"))
            .first()
        )
        file_count = db.query(ProjectFile).filter(ProjectFile.workspace_id == workspace.id).count()
        if not existing and file_count >= MAX_WORKSPACE_FILES:
            raise WorkspaceError(
                f"Workspace already holds {file_count} files; refusing to add more."
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    info = WrittenFile(
        path=relative.replace("\\", "/").lstrip("/"),
        size_bytes=len(encoded),
        lines=content.count("\n") + (1 if content and not content.endswith("\n") else 0),
        checksum=hashlib.sha256(encoded).hexdigest(),
    )

    if db is not None and workspace is not None:
        row = (
            db.query(ProjectFile)
            .filter(ProjectFile.workspace_id == workspace.id, ProjectFile.path == info.path)
            .first()
        )
        if row is None:
            row = ProjectFile(workspace_id=workspace.id, path=info.path)
            db.add(row)
        row.agent_id = agent_id
        row.phase = phase
        row.size_bytes = info.size_bytes
        row.lines = info.lines
        row.checksum = info.checksum
        row.is_ai_generated = is_ai_generated
        row.is_template = is_template
        db.flush()
    return info


def read_file(root: Path, relative: str) -> str:
    target = resolve_within(root, relative)
    if not target.exists() or not target.is_file():
        raise WorkspaceError(f"File not found: {relative}")
    if target.stat().st_size > 2 * 1024 * 1024:
        raise WorkspaceError(f"{relative} is too large to display.")
    return target.read_text(encoding="utf-8", errors="replace")


def delete_file(root: Path, relative: str) -> bool:
    target = resolve_within(root, relative)
    if target.exists() and target.is_file():
        target.unlink()
        return True
    return False


def list_files(root: Path, *, include_hidden: bool = False) -> list[dict]:
    """Walk the workspace, skipping heavy dependency folders."""
    skip_dirs = {"node_modules", ".git", "data", "dist", "build", ".cache", "coverage"}
    entries: list[dict] = []
    if not root.exists():
        return entries
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in skip_dirs and not d.startswith("."))
        current_path = Path(current)
        for name in sorted(files):
            if not include_hidden and name.startswith(".") and name not in {".env.example", ".gitignore", ".nvmrc"}:
                continue
            full = current_path / name
            relative = full.relative_to(root).as_posix()
            try:
                stat = full.stat()
            except OSError:
                continue
            entries.append({
                "path": relative,
                "size_bytes": stat.st_size,
                "extension": full.suffix.lower(),
                "is_text": full.suffix.lower() in TEXT_SUFFIXES or name.startswith(".env"),
                "modified_at": stat.st_mtime,
            })
    return entries


def tree(root: Path) -> dict:
    """Build a nested tree for the file explorer."""
    skip_dirs = {"node_modules", ".git", "data", ".cache", "coverage"}

    def walk(path: Path) -> list[dict]:
        nodes: list[dict] = []
        try:
            children = sorted(path.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
        except OSError:
            return nodes
        for child in children:
            if child.is_dir():
                if child.name in skip_dirs:
                    continue
                nodes.append({
                    "type": "dir",
                    "name": child.name,
                    "path": child.relative_to(root).as_posix(),
                    "children": walk(child),
                })
            else:
                try:
                    size = child.stat().st_size
                except OSError:
                    size = 0
                nodes.append({
                    "type": "file",
                    "name": child.name,
                    "path": child.relative_to(root).as_posix(),
                    "size_bytes": size,
                })
        return nodes

    return {"name": root.name, "type": "dir", "path": ".", "children": walk(root) if root.exists() else []}


def workspace_size_bytes(root: Path) -> int:
    total = 0
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {"node_modules", ".git"}]
        for name in files:
            try:
                total += (Path(current) / name).stat().st_size
            except OSError:
                continue
    return total


def scan_for_secrets(root: Path) -> list[dict]:
    """Static security scan over generated source files."""
    findings: list[dict] = []
    for entry in list_files(root):
        if entry["size_bytes"] > 256 * 1024:
            continue
        path = root / entry["path"]
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for pattern, label in SECRET_PATTERNS:
                if pattern.search(line):
                    # Templates intentionally use obvious placeholders.
                    if any(token in line for token in ("CHANGE_ME", "example", "placeholder", "${", "process.env")):
                        continue
                    findings.append({
                        "path": entry["path"],
                        "line": number,
                        "rule": label,
                        "snippet": line.strip()[:160],
                    })
    return findings


def index_existing_files(db: Session, workspace: Workspace, root: Path,
                         agent_by_path: dict[str, str] | None = None,
                         default_agent: str = "devops",
                         phase: str = "implementation") -> int:
    """Index files that already exist on disk (e.g. a copied blueprint)."""
    agent_by_path = agent_by_path or {}
    indexed = 0
    for entry in list_files(root):
        relative = entry["path"]
        row = (
            db.query(ProjectFile)
            .filter(ProjectFile.workspace_id == workspace.id, ProjectFile.path == relative)
            .first()
        )
        if row is None:
            row = ProjectFile(workspace_id=workspace.id, path=relative)
            db.add(row)
        row.agent_id = agent_by_path.get(relative) or _agent_for(relative, default_agent)
        row.phase = phase
        row.size_bytes = entry["size_bytes"]
        try:
            text = (root / relative).read_text(encoding="utf-8", errors="ignore")
            row.lines = text.count("\n") + 1
            row.checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        except OSError:
            row.lines = 0
        row.is_template = True
        indexed += 1
    db.flush()
    return indexed


def _agent_for(relative: str, default_agent: str) -> str:
    path = relative.lower()
    if path.startswith("backend/routes") or path.startswith("backend/services") or "server.js" in path:
        return "backend"
    if path.startswith("frontend/public/index.html") or path.endswith("styles.css"):
        return "design"
    if path.startswith("frontend/"):
        return "frontend"
    if path.startswith("database/"):
        return "database"
    if path.startswith("tests/"):
        return "qa"
    if path.startswith("documentation/"):
        return "product"
    if path.startswith(".github/") or path.startswith("scripts/") or path in {"package.json", ".env.example", ".gitignore"}:
        return "devops"
    return default_agent


def prepare_directory(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return root


def copy_tree(source: Path, destination: Path, *, skip: set[str] | None = None) -> int:
    skip = skip or {"node_modules", ".git", "data", ".cache"}
    count = 0
    for current, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if d not in skip]
        relative = Path(current).relative_to(source)
        (destination / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            if name in skip:
                continue
            shutil.copy2(Path(current) / name, destination / relative / name)
            count += 1
    return count


def remove_directory(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
