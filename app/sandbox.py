"""Sandboxed command execution for generated applications.

Generated code is never imported into the FastAPI process. Every build, test,
install or preview command runs as a separate OS process with:

* an explicit argument list (``shell=False``, so no shell injection),
* a hard timeout with process-group kill,
* a scrubbed environment (no NEXORA secrets leaked into generated apps),
* output truncation and byte caps,
* a working directory that must resolve inside ``generated_projects``.
"""
from __future__ import annotations

import os
import re
import select
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .workspace import projects_root

MAX_OUTPUT_BYTES = 200_000
ANSI_ESCAPE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

# Only these executables may ever be launched.
ALLOWED_BINARIES = {
    "npm", "node", "npx", "python3", "git",
}

# Environment variables a child process is allowed to inherit.
SAFE_ENV_KEYS = {
    "PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TERM", "SHELL", "USER", "LOGNAME",
    "NODE_OPTIONS", "NPM_CONFIG_CACHE", "npm_config_cache", "PYTHONPATH",
}


class SandboxError(RuntimeError):
    """Command rejected by the sandbox policy."""


@dataclass
class CommandResult:
    command: str
    exit_code: int
    output: str
    duration_ms: int
    timed_out: bool

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def summary(self, limit: int = 4000) -> str:
        text = ANSI_ESCAPE.sub("", self.output).strip()
        return text[-limit:] if len(text) > limit else text


def _sandbox_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in SAFE_ENV_KEYS}
    env.update({
        "NODE_ENV": "test",
        "CI": "1",
        "NPM_CONFIG_UPDATE_NOTIFIER": "false",
        "NPM_CONFIG_FUND": "false",
        "NPM_CONFIG_AUDIT": "false",
        "NPM_CONFIG_PROGRESS": "false",
        # Generated apps must never inherit studio credentials.
        "LLM_PROVIDER": "",
        "MISTRAL_API_KEY": "",
        "GEMINI_API_KEY": "",
        "DATABASE_URL": "",
        "OLLAMA_BASE_URL": "",
    })
    if "PATH" not in env:
        env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    return env


def _validated_cwd(cwd: Path) -> Path:
    root = projects_root()
    resolved = cwd.resolve()
    if root != resolved and root not in resolved.parents:
        raise SandboxError(f"Refusing to run a command outside generated_projects: {cwd}")
    if not resolved.exists():
        raise SandboxError(f"Working directory does not exist: {cwd}")
    return resolved


def build_argv(command: str | list[str]) -> list[str]:
    argv = shlex.split(command) if isinstance(command, str) else list(command)
    if not argv:
        raise SandboxError("Empty command.")
    binary = os.path.basename(argv[0])
    if binary not in ALLOWED_BINARIES:
        raise SandboxError(f"Binary '{binary}' is not allowed in the sandbox.")
    for token in argv[1:]:
        if token in {"&&", "||", ";", "|", ">", "<", "`"} or "$(" in token:
            raise SandboxError(f"Shell operators are not allowed: {token}")
        if token.startswith("/") and binary != "python3":
            raise SandboxError(f"Absolute path arguments are not allowed: {token}")
    return argv


def run(command: str | list[str], cwd: Path, *, timeout: int = 180,
        extra_env: dict[str, str] | None = None) -> CommandResult:
    """Run one sandboxed command and never raise for a non-zero exit code."""
    argv = build_argv(command)
    working_dir = _validated_cwd(cwd)
    env = _sandbox_env()
    if extra_env:
        for key, value in extra_env.items():
            if key in SAFE_ENV_KEYS or key.startswith("npm_"):
                env[key] = value
    started = time.perf_counter()
    timed_out = False
    try:
        process = subprocess.Popen(
            argv,
            cwd=str(working_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        return CommandResult(
            command=" ".join(argv), exit_code=127,
            output=f"Executable not found: {argv[0]}", duration_ms=0, timed_out=False,
        )
    except Exception as exc:  # noqa: BLE001 - surface as a failed run, not a crash
        return CommandResult(
            command=" ".join(argv), exit_code=126,
            output=f"Could not start process: {type(exc).__name__}: {exc}",
            duration_ms=0, timed_out=False,
        )

    output_parts: list[str] = []
    total = 0
    deadline = started + timeout
    try:
        assert process.stdout is not None
        # Read incrementally, but enforce the timeout on wall-clock time too, so
        # a silent or CPU-bound process cannot outlive its budget.
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                timed_out = True
                _kill_group(process)
                break
            ready, _, _ = select.select([process.stdout], [], [], min(remaining, 0.5))
            if ready:
                line = process.stdout.readline()
                if not line:
                    break
                total += len(line)
                if total <= MAX_OUTPUT_BYTES:
                    output_parts.append(line)
            if process.poll() is not None and not ready:
                break
    finally:
        if process.poll() is None:
            _kill_group(process)

    try:
        exit_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(process)
        exit_code = -1

    if total > MAX_OUTPUT_BYTES:
        output_parts.append(f"\n… output truncated at {MAX_OUTPUT_BYTES} bytes …")

    if exit_code is None:
        exit_code = process.returncode if process.returncode is not None else -1
    if timed_out:
        output_parts.append(f"\n… command timed out after {timeout}s and was terminated …")
    return CommandResult(
        command=" ".join(argv),
        exit_code=exit_code,
        output="".join(output_parts),
        duration_ms=int((time.perf_counter() - started) * 1000),
        timed_out=timed_out,
    )


def _kill_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            process.kill()
        except Exception:  # noqa: BLE001
            pass


def spawn_background(command: list[str], cwd: Path, *, port: int,
                     log_path: Path) -> subprocess.Popen:
    """Start a long-lived process (the app preview) with a scrubbed env."""
    working_dir = _validated_cwd(cwd)
    argv = build_argv(command)
    env = _sandbox_env()
    env["PORT"] = str(port)
    env["NODE_ENV"] = "production"
    env["HOST"] = "0.0.0.0"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "ab", buffering=0)  # noqa: SIM115 - kept for child lifetime
    process = subprocess.Popen(
        argv,
        cwd=str(working_dir),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return process


def stop_process(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return False
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    return True


def process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
