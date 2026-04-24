"""Thin HTTP client for a local Ollama server.

Responsibility (strict): single-shot text generation against Ollama's
`POST /api/generate`. The caller supplies a fully-rendered prompt; this
module does no prompt composition and no template loading.

Design choices:
- Single-shot only (`stream: false`). Streaming can be added later if
  the UI layer needs it.
- `urllib` from the stdlib — no new runtime dependency.
- Typed error surface (`OllamaUnavailableError`) so the API layer can
  map failures to a clean 503.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_TIMEOUT_SECONDS = 60.0


class OllamaUnavailableError(RuntimeError):
    """Raised when Ollama is unreachable or returns an unusable response."""


@dataclass(frozen=True)
class OllamaConfig:
    host: str
    model: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "OllamaConfig":
        return cls(
            host=os.environ.get("JISP_OLLAMA_HOST", DEFAULT_OLLAMA_HOST),
            model=os.environ.get("JISP_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            timeout_seconds=float(
                os.environ.get(
                    "JISP_OLLAMA_TIMEOUT_SECONDS",
                    DEFAULT_TIMEOUT_SECONDS,
                )
            ),
        )


def generate(prompt: str, config: OllamaConfig | None = None) -> str:
    """Single-shot completion via Ollama's `/api/generate`.

    Raises:
        OllamaUnavailableError: when the server is unreachable, returns a
            non-2xx status, or returns an unexpected response body.
    """
    cfg = config or OllamaConfig.from_env()
    url = cfg.host.rstrip("/") + "/api/generate"
    body = json.dumps(
        {"model": cfg.model, "prompt": prompt, "stream": False}
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=cfg.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise OllamaUnavailableError(
            f"Ollama at {cfg.host} returned HTTP {e.code}: {e.reason}"
        ) from e
    except urllib.error.URLError as e:
        raise OllamaUnavailableError(
            f"Ollama at {cfg.host} unreachable: {e.reason}"
        ) from e
    except TimeoutError as e:
        raise OllamaUnavailableError(
            f"Ollama at {cfg.host} timed out after {cfg.timeout_seconds}s"
        ) from e

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise OllamaUnavailableError("Ollama returned a non-JSON response") from e

    text = payload.get("response")
    if not isinstance(text, str):
        raise OllamaUnavailableError(
            "Ollama response missing a string 'response' field"
        )
    return text
