"""The sandbox must refuse anything that could escape or escalate."""
import pytest

from app import sandbox
from app.sandbox import SandboxError, build_argv, run
from app.workspace import projects_root


@pytest.mark.parametrize("command", [
    "rm -rf /",
    "curl http://evil.example",
    "bash -c 'echo hi'",
    "sh -c ls",
    "npm install && rm -rf .",
    "node -e 'require(\"child_process\")' | cat",
    "python3 -c 'import os' > /tmp/out",
])
def test_disallowed_binaries_and_shell_operators_are_rejected(command):
    with pytest.raises(SandboxError):
        build_argv(command)


def test_allowed_commands_are_parsed_without_a_shell():
    assert build_argv("npm run build") == ["npm", "run", "build"]
    assert build_argv(["node", "--test"]) == ["node", "--test"]


def test_absolute_path_arguments_are_rejected():
    with pytest.raises(SandboxError):
        build_argv("node /etc/passwd")


def test_commands_cannot_run_outside_generated_projects(tmp_path):
    with pytest.raises(SandboxError):
        run(["node", "--version"], tmp_path)


def test_environment_is_scrubbed_of_studio_secrets(isolated_environment, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "mstrl_should_not_leak")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///studio.db")
    root = projects_root() / "env-probe"
    root.mkdir(parents=True, exist_ok=True)
    result = run(["node", "-e", "console.log(JSON.stringify({m:process.env.MISTRAL_API_KEY,d:process.env.DATABASE_URL,n:process.env.NODE_ENV}))"], root, timeout=30)
    assert result.ok, result.output
    assert '"m":""' in result.output.replace(" ", "")
    assert '"d":""' in result.output.replace(" ", "")
    assert '"n":"test"' in result.output.replace(" ", "")


def test_timeout_kills_a_runaway_process(isolated_environment):
    root = projects_root() / "timeout-probe"
    root.mkdir(parents=True, exist_ok=True)
    result = run(["node", "-e", "setTimeout(()=>{}, 60000)"], root, timeout=2)
    assert result.timed_out
    assert not result.ok


def test_run_reports_missing_binaries_instead_of_raising(isolated_environment):
    root = projects_root() / "missing-bin"
    root.mkdir(parents=True, exist_ok=True)
    result = run(["node", "does-not-exist.js"], root, timeout=20)
    assert result.exit_code != 0
    assert "Cannot find module" in result.output or result.exit_code != 0
