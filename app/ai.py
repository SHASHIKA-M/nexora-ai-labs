import os
import httpx

SYSTEM_PROMPT = """You are an AI employee inside NEXORA AI LABS, a founder-controlled software studio.
Be accurate, practical, and concise. Do not claim to have executed code, accessed files,
contacted customers, sent messages, spent money, changed accounts, or deployed anything.
You may prepare plans, specifications, code suggestions, checklists, and written deliverables.
All external actions and consequential decisions require explicit founder approval.
Never request or reveal API keys, passwords, or other secrets. Prefer secure, maintainable,
accessible web application designs. Clearly state assumptions and unknowns.
"""


def generate_reply(prompt: str, system_prompt: str | None = None) -> str:
    """Generate a response using the configured local Ollama model."""
    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    if provider != "ollama":
        raise RuntimeError("This build is configured for local Ollama only. Set LLM_PROVIDER=ollama.")

    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    full_prompt = f"{system_prompt or SYSTEM_PROMPT}\n\nFounder request:\n{prompt}"

    try:
        response = httpx.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": full_prompt, "stream": False},
            timeout=httpx.Timeout(300.0, connect=5.0),
        )
        response.raise_for_status()
    except httpx.ConnectError as exc:
        raise RuntimeError("Cannot connect to Ollama. Make sure Ollama is running on the configured local URL.") from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError("Ollama timed out. Try again or use a smaller local model.") from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise RuntimeError(f"Ollama returned HTTP {exc.response.status_code}: {detail}") from exc

    result = response.json().get("response", "").strip()
    if not result:
        raise RuntimeError("Ollama returned an empty response.")
    return result
