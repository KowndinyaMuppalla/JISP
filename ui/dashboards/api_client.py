"""Thin HTTP client the Streamlit dashboard uses to reach the JISP API.

Responsibility (strict, per ADR 001): UI-layer only. No business logic. Wraps
the two endpoints the dashboard actually touches so error handling lives in
one place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


DEFAULT_BASE_URL = os.environ.get("JISP_API_BASE_URL", "http://localhost:8000")
DEFAULT_TIMEOUT = int(os.environ.get("JISP_API_TIMEOUT_SECONDS", "90"))


class JispApiError(RuntimeError):
    """Raised when the API returns a non-200 response or is unreachable.

    Kept as a single error type because the Streamlit layer renders all
    failures the same way (banner + retry).
    """


@dataclass(frozen=True)
class HealthStatus:
    ok: bool
    detail: str


def check_health(base_url: str = DEFAULT_BASE_URL) -> HealthStatus:
    """Hit GET /health. Never raises — the dashboard renders the dot either way."""
    try:
        r = requests.get(f"{base_url}/health", timeout=5)
        if r.status_code == 200 and r.json().get("status") == "ok":
            return HealthStatus(ok=True, detail=r.json().get("version", "unknown"))
        return HealthStatus(ok=False, detail=f"HTTP {r.status_code}")
    except requests.RequestException as exc:
        return HealthStatus(ok=False, detail=str(exc))


def explain(
    subject: str,
    template: str,
    context: dict[str, Any],
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """POST /explain and return the parsed response.

    Raises:
        JispApiError: for any non-200, timeout, or connection failure. The
            message is safe to show in the UI.
    """
    payload = {"subject": subject, "template": template, "context": context}
    try:
        r = requests.post(f"{base_url}/explain", json=payload, timeout=timeout)
    except requests.Timeout as exc:
        raise JispApiError(
            f"Reasoning timed out after {timeout}s. Is Ollama busy or the model unloaded?"
        ) from exc
    except requests.ConnectionError as exc:
        raise JispApiError(
            f"Cannot reach JISP API at {base_url}. Is `uvicorn api.main:app` running?"
        ) from exc

    if r.status_code == 200:
        return r.json()

    # Translate the three documented error codes to human messages.
    detail = _safe_detail(r)
    if r.status_code == 400:
        raise JispApiError(f"Unknown template or malformed request: {detail}")
    if r.status_code == 422:
        raise JispApiError(f"Schema validation failed: {detail}")
    if r.status_code == 503:
        raise JispApiError(
            f"Reasoning service unavailable — likely Ollama is offline. {detail}"
        )
    raise JispApiError(f"Unexpected API response {r.status_code}: {detail}")


def _safe_detail(r: requests.Response) -> str:
    try:
        body = r.json()
    except ValueError:
        return r.text[:200]
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return str(body)[:200]
