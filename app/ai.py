"""AI provider layer.

Keeps the existing local Ollama integration and adds what the autonomous
development pipeline needs:

* ``generate_reply``  — free-form completion (used by the AI CEO chat).
* ``generate_json``   — schema-validated structured generation with one repair
                        retry, so agents always return usable JSON.
* ``ai_status``       — live availability probe used by the dashboard.

Provider is deliberately restricted to local Ollama: generated code must never
be produced by a remote service the founder has not configured.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable

import httpx

SYSTEM_PROMPT = """You are an AI employee inside NEXORA AI LABS, a founder-controlled software studio.
Be accurate, practical, and concise. Do not claim to have executed code, accessed files,
contacted customers, sent money, changed accounts, or deployed anything unless the platform
has explicitly performed that action and reported the result to you.
You may prepare plans, specifications, code, checklists, and written deliverables.
All external actions and consequential decisions require explicit founder approval.
Never request or reveal API keys, passwords, or other secrets. Prefer secure, maintainable,
accessible web application designs. Clearly state assumptions and unknowns.
"""

JSON_SYSTEM_PROMPT = """You are a senior software engineer inside NEXORA AI LABS.
You respond with a single valid JSON object and nothing else: no prose before or after,
no markdown fences, no comments, no trailing commas. Every required key must be present
and the value types must exactly match the schema described by the user. Strings must be
unescaped correctly. Never include secrets, API keys or passwords.
"""


class AIUnavailable(RuntimeError):
    """Raised when the local model cannot be reached."""


class AIInvalidOutput(ValueError):
    """Raised when the model returns content that cannot satisfy the schema."""


def _provider() -> str:
    return os.getenv("LLM_PROVIDER", "ollama").strip().lower()


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def model_name() -> str:
    return os.getenv("OLLAMA_MODEL", "llama3.2")


def _post_generate(prompt: str, *, system: str, temperature: float | None = None,
                   timeout: float = 300.0) -> str:
    if _provider() != "ollama":
        raise AIUnavailable(
            "This build is configured for local Ollama only. Set LLM_PROVIDER=ollama."
        )
    payload: dict[str, Any] = {
        "model": model_name(),
        "prompt": f"{system}\n\nFounder request:\n{prompt}",
        "stream": False,
    }
    if temperature is not None:
        payload["options"] = {"temperature": temperature}
    try:
        response = httpx.post(
            f"{_base_url()}/api/generate",
            json=payload,
            timeout=httpx.Timeout(timeout, connect=5.0),
        )
        response.raise_for_status()
    except httpx.ConnectError as exc:
        raise AIUnavailable(
            "Cannot connect to Ollama. Make sure Ollama is running on the configured local URL."
        ) from exc
    except httpx.TimeoutException as exc:
        raise AIUnavailable("Ollama timed out. Try again or use a smaller local model.") from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise AIUnavailable(f"Ollama returned HTTP {exc.response.status_code}: {detail}") from exc

    result = (response.json().get("response") or "").strip()
    if not result:
        raise AIUnavailable("Ollama returned an empty response.")
    return result


def generate_reply(prompt: str, system_prompt: str | None = None) -> str:
    """Free-form completion using the configured local Ollama model."""
    return _post_generate(prompt, system=system_prompt or SYSTEM_PROMPT)


def extract_json(text: str) -> dict:
    """Parse a JSON object out of a model response, tolerating fences and prose."""
    if not text or not text.strip():
        raise AIInvalidOutput("The model returned an empty response.")
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise AIInvalidOutput("The model response did not contain a JSON object.")
        try:
            parsed = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            raise AIInvalidOutput(f"The model returned malformed JSON: {exc.msg}.") from exc
    if not isinstance(parsed, dict):
        raise AIInvalidOutput("The model returned JSON that is not an object.")
    return parsed


def generate_json(
    prompt: str,
    schema: str,
    validator: Callable[[dict], dict],
    *,
    temperature: float = 0.2,
    repair_attempts: int = 1,
    timeout: float = 300.0,
) -> tuple[dict, str]:
    """Generate schema-validated JSON.

    Returns ``(validated_payload, raw_response)``. One repair round trip is made
    when the first response fails validation; a second failure raises
    :class:`AIInvalidOutput` so the orchestrator can record a truthful error
    instead of inventing data.
    """
    attempt_prompt = prompt
    last_error: Exception | None = None
    raw = ""
    for attempt in range(repair_attempts + 1):
        raw = _post_generate(attempt_prompt, system=JSON_SYSTEM_PROMPT,
                             temperature=temperature, timeout=timeout)
        try:
            payload = extract_json(raw)
            return validator(payload), raw
        except (AIInvalidOutput, ValueError) as exc:
            last_error = exc
            if attempt >= repair_attempts:
                break
            attempt_prompt = (
                f"{prompt}\n\nYour previous reply was rejected by the JSON validator: {exc}\n"
                f"Return ONLY corrected JSON matching this schema:\n{schema}"
            )
    raise AIInvalidOutput(f"Model output failed validation: {last_error}")


def ai_status() -> dict:
    """Probe the configured local model. Never raises."""
    status: dict[str, Any] = {
        "provider": _provider(),
        "model": model_name(),
        "base_url": _base_url(),
        "state": "unknown",
        "models": [],
        "latency_ms": None,
        "detail": "",
    }
    if _provider() != "ollama":
        status.update(state="not_configured", detail="LLM_PROVIDER must be 'ollama'.")
        return status
    started = time.perf_counter()
    try:
        response = httpx.get(f"{_base_url()}/api/tags", timeout=3.0)
        response.raise_for_status()
        status["latency_ms"] = int((time.perf_counter() - started) * 1000)
        models = [entry.get("name", "") for entry in response.json().get("models", [])]
        status["models"] = models
        configured = model_name()
        if any(name == configured or name.split(":")[0] == configured for name in models):
            status["state"] = "online"
            status["detail"] = f"{configured} is available locally."
        elif models:
            status["state"] = "model_missing"
            status["detail"] = (
                f"Ollama is running but '{configured}' is not pulled. "
                f"Run: ollama pull {configured}"
            )
        else:
            status["state"] = "no_models"
            status["detail"] = f"Ollama is running with no models. Run: ollama pull {configured}"
    except Exception as exc:  # noqa: BLE001 - status probe must never raise
        status.update(state="offline", detail=f"Cannot reach Ollama: {type(exc).__name__}")
    return status


def ai_available() -> bool:
    return ai_status()["state"] == "online"
