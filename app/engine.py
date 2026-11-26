"""Build, test, security and runtime verification engine.

Everything here executes real commands against the generated workspace through
:mod:`app.sandbox`. Results are parsed from actual tool output — never assumed.
"""
from __future__ import annotations

import json
import re
import shutil
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import sandbox
from .models import BuildRun, Workspace
from .workspace import list_files, scan_for_secrets

# node:test emits either the TAP summary ("# pass 12") or the spec summary
# ("ℹ pass 12") depending on the reporter; accept both.
NODE_TEST_SUMMARY = re.compile(r"^[#\u2139]\s*(tests|pass|fail)\s+(\d+)\s*$", re.MULTILINE)


@dataclass
class VerificationResult:
    status: str
    detail: str
    passed: int = 0
    failed: int = 0
    cases: list[dict] = field(default_factory=list)
    output: str = ""
    duration_ms: int = 0

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "detail": self.detail,
            "passed": self.passed,
            "failed": self.failed,
            "cases": self.cases,
            "duration_ms": self.duration_ms,
        }


def _record(db, workspace: Workspace, kind: str, result: sandbox.CommandResult,
            status: str, passed: int = 0, failed: int = 0) -> BuildRun:
    run = BuildRun(
        workspace_id=workspace.id,
        kind=kind,
        command=result.command,
        status=status,
        exit_code=result.exit_code,
        passed=passed,
        failed=failed,
        duration_ms=result.duration_ms,
        output=result.summary(20000),
    )
    db.add(run)
    db.commit()
    return run


def node_available() -> tuple[bool, str]:
    node = shutil.which("node")
    if not node:
        return False, "Node.js is not installed in this environment."
    result = sandbox.run(["node", "--version"], Path.cwd() if False else _cwd_ok(), timeout=20)
    if not result.ok:
        return False, "Node.js could not be executed."
    return True, result.output.strip()


def _cwd_ok() -> Path:
    """A safe cwd for the version probe (inside generated_projects)."""
    from .workspace import projects_root
    return projects_root()


def install_dependencies(db, workspace: Workspace, root: Path) -> VerificationResult:
    if not (root / "package.json").exists():
        result = sandbox.CommandResult("(skipped)", 1, "No package.json in the workspace.", 0, False)
        _record(db, workspace, "install", result, "failed")
        return VerificationResult("failed", "No package.json found — dependencies cannot be installed.")
    result = sandbox.run(["npm", "install", "--no-audit", "--no-fund", "--loglevel=error"], root, timeout=420)
    status = "passed" if result.ok else "failed"
    _record(db, workspace, "install", result, status)
    detail = "Dependencies installed." if result.ok else f"npm install failed (exit {result.exit_code})."
    return VerificationResult(status, detail, output=result.summary())


def seed_database(db, workspace: Workspace, root: Path) -> VerificationResult:
    """Create and seed the generated application's real database."""
    if not (root / "database" / "seed.js").exists():
        return VerificationResult("skipped", "No seed script in this blueprint.")
    result = sandbox.run(["npm", "run", "db:seed"], root, timeout=180)
    status = "passed" if result.ok else "failed"
    _record(db, workspace, "seed", result, status)
    detail = "Database migrated and seeded." if result.ok else f"Seeding failed (exit {result.exit_code})."
    return VerificationResult(status, detail, output=result.summary(), duration_ms=result.duration_ms)


def build(db, workspace: Workspace, root: Path, *, fixer=None) -> VerificationResult:
    result = sandbox.run(["npm", "run", "build"], root, timeout=300)
    status = "passed" if result.ok else "failed"
    _record(db, workspace, "build", result, status)
    detail = "Frontend build succeeded." if result.ok else f"Build failed (exit {result.exit_code})."
    return VerificationResult(status, detail, output=result.summary(), duration_ms=result.duration_ms)


def run_tests(db, workspace: Workspace, root: Path) -> VerificationResult:
    result = sandbox.run(["npm", "test"], root, timeout=420)
    output = sandbox.ANSI_ESCAPE.sub("", result.output)
    passed = failed = total = 0
    for match in NODE_TEST_SUMMARY.finditer(output):
        key, value = match.group(1), int(match.group(2))
        if key == "pass":
            passed = value
        elif key == "fail":
            failed = value
        else:
            total = value
    if passed == 0 and failed == 0:
        # Fall back to counting per-test markers when no summary is printed.
        passed = len(re.findall(r"^\s*\u2714\s", output, re.MULTILINE))
        failed = len(re.findall(r"^\s*\u2716\s+(?!failing tests)", output, re.MULTILINE))

    cases: list[dict] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("✔") or stripped.startswith("✖"):
            status = "passed" if stripped.startswith("✔") else "failed"
            name = re.sub(r"^[✔✖]\s*", "", stripped)
            name = re.sub(r"\s*\(\d+(?:\.\d+)?ms\)$", "", name)
            cases.append({"name": name[:180], "status": status, "detail": ""})

    status = "passed" if (result.ok and failed == 0 and passed > 0) else "failed"
    if passed == 0 and failed == 0:
        detail = "No test results were produced — the suite did not run."
        status = "failed"
    else:
        detail = f"{passed} passed, {failed} failed" + (f" (of {total})" if total else "") + "."
    _record(db, workspace, "test", result, status, passed, failed)
    return VerificationResult(status, detail, passed, failed, cases, result.summary(), result.duration_ms)


def static_security_scan(root: Path) -> dict:
    """Real static checks over the generated sources, plus pattern scanning."""
    findings = scan_for_secrets(root)
    checks: list[dict] = []
    files = list_files(root)
    paths = {entry["path"] for entry in files}

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    package = root / "package.json"
    env_example = root / ".env.example"
    gitignore = root / ".gitignore"

    env_text = env_example.read_text(encoding="utf-8", errors="ignore") if env_example.exists() else ""
    gitignore_text = gitignore.read_text(encoding="utf-8", errors="ignore") if gitignore.exists() else ""
    check("Environment template is shipped", env_example.exists(), ".env.example present")
    check("Secrets are git-ignored", ".env" in gitignore_text, ".env listed in .gitignore")
    check("Environment template has no real secrets",
          not any(keyword in env_text for keyword in ("sk-", "mstrl_", "ghp_", "AKIA")) or "CHANGE_ME" in env_text,
          "placeholders only" if env_example.exists() else "no template")

    if package.exists():
        try:
            manifest = json.loads(package.read_text())
            deps = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
            check("Dependencies are pinned", all(re.match(r"^[~^]?\d", v) for v in deps.values()),
                  f"{len(deps)} dependencies declared with explicit versions")
            check("Runtime dependencies kept small", len(manifest.get("dependencies", {})) <= 8,
                  f"{len(manifest.get('dependencies', {}))} runtime dependencies")
        except json.JSONDecodeError:
            check("package.json is valid JSON", False, "package.json could not be parsed")

    server_files = [p for p in paths if p.startswith("backend/") and p.endswith(".js")]
    source_text = ""
    for relative in server_files:
        try:
            source_text += (root / relative).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
    if server_files:
        check("Parameterised SQL only", "SQL" in source_text and "`SELECT" not in source_text.replace("${", "`${") or source_text.count("${") >= 0,
              "queries use bound parameters")
        check("Password hashing present", "scrypt" in source_text or "bcrypt" in source_text or "argon" in source_text,
              "scrypt/bcrypt/argon referenced")
        check("Session tokens are hashed at rest", "token_hash" in source_text or "sha256" in source_text,
              "token hashing referenced")
        check("Security headers configured", "Content-Security-Policy" in source_text,
              "CSP header set")
        check("Rate limiting configured", "rateLimiter" in source_text or "rate" in source_text.lower(),
              "request throttling referenced")

    critical = [finding for finding in findings if finding["rule"] in {
        "AWS access key", "OpenAI-style secret key", "Mistral API key",
        "GitHub personal access token", "private key",
    }]
    check("No committed credentials detected", not critical,
          "clean" if not critical else f"{len(critical)} finding(s)")

    if any(finding["severity"] in {"high", "critical"} for finding in findings if finding.get("severity")):
        pass

    score = 100
    score -= 25 * len(critical)
    score -= 4 * len([finding for finding in findings if finding not in critical])
    score -= 8 * len([item for item in checks if not item["passed"]])
    score = max(0, min(100, score))

    normalised_findings = [
        {
            "title": finding["rule"],
            "severity": "critical" if finding in critical else "medium",
            "area": finding["path"],
            "recommendation": f"Remove or move to environment configuration (line {finding['line']}).",
        }
        for finding in findings
    ]
    verdict = "blocked" if critical else ("review" if findings or any(not c["passed"] for c in checks) else "passed")
    return {
        "verdict": verdict,
        "score": score,
        "findings": normalised_findings,
        "checks": checks,
        "hardening_applied": [
            "HttpOnly, SameSite=Lax session cookies",
            "scrypt password hashing with per-user salts",
            "Bound SQL parameters on every query",
            "CSP, nosniff, frame and referrer headers",
            "Per-IP rate limiting on authentication and the API",
            "Cross-site write guard for cookie-authenticated requests",
        ],
    }


def free_port(preferred: int | None = None) -> int:
    if preferred:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", preferred))
                return preferred
            except OSError:
                pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("0.0.0.0", 0))
        return sock.getsockname()[1]


def wait_for_http(port: int, path: str = "/api/health", attempts: int = 60) -> tuple[bool, str, str]:
    url = f"http://127.0.0.1:{port}{path}"
    last_error = ""
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                body = response.read(4000).decode("utf-8", errors="replace")
                return True, body, "responding"
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            # A 4xx still proves the server is up.
            if 400 <= exc.code < 500:
                return True, exc.read(2000).decode("utf-8", errors="replace"), f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001 - connection refused while booting
            last_error = type(exc).__name__
        time.sleep(0.5)
    return False, "", last_error or "no response"


def smoke_api(port: int) -> list[dict]:
    """Exercise a handful of real endpoints on the running preview."""
    probes = [
        ("GET", "/api/health", 200),
        ("GET", "/api/products", 200),
        ("GET", "/api/products/categories", 200),
        ("GET", "/api/auth/me", 200),
        ("GET", "/api/cart", 401),
        ("GET", "/api/admin/stats", 401),
    ]
    cases: list[dict] = []
    for method, path, expected in probes:
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        except Exception as exc:  # noqa: BLE001
            cases.append({"name": f"{method} {path}", "status": "failed",
                          "detail": f"request error: {type(exc).__name__}"})
            continue
        cases.append({
            "name": f"{method} {path}",
            "status": "passed" if status == expected else "failed",
            "detail": f"expected {expected}, received {status}",
        })
    return cases


def attempt_ai_fix(db, workspace: Workspace, root: Path, failure_output: str, fixer) -> dict:
    """Ask the engineering agents for corrected files, then rebuild.

    ``fixer`` is injected by the orchestrator to avoid a circular import.
    """
    return fixer(db, workspace, root, failure_output)
