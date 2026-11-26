"""Shared fixtures: a throwaway database and generated-projects folder per run."""
import os
import shutil
import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_environment():
    """Point the app at temporary paths before it is imported anywhere."""
    tmp = tempfile.mkdtemp(prefix="nexora-test-")
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["GENERATED_PROJECTS_DIR"] = f"{tmp}/generated_projects"
    os.environ["LLM_PROVIDER"] = "ollama"
    # Nothing listens here, so the AI layer always reports "offline" in tests.
    os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
    os.environ["OLLAMA_MODEL"] = "llama3.2"
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture()
def client(isolated_environment):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def project(client):
    response = client.post("/api/projects", json={
        "name": "Online Shopping Platform",
        "description": (
            "Build a real online shopping platform where customers register, log in, browse "
            "products, add items to a cart, check out and manage orders, with an admin dashboard."
        ),
        "business_line": "client",
        "autostart": False,
    })
    assert response.status_code == 201, response.text
    return response.json()
