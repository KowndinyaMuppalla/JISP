"""Ollama HTTP client — JISP (llama3.2)"""
import json, os, urllib.request, urllib.error
from dataclasses import dataclass

OLLAMA_HOST    = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "90"))

class OllamaUnavailableError(Exception): pass

@dataclass
class OllamaResponse:
    text: str
    model: str
    done: bool

def generate(prompt: str, model: str | None = None, timeout: int | None = None) -> OllamaResponse:
    url  = f"{OLLAMA_HOST}/api/generate"
    body = json.dumps({"model": model or OLLAMA_MODEL, "prompt": prompt, "stream": False}).encode()
    req  = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout or OLLAMA_TIMEOUT) as r:
            data = json.loads(r.read())
            return OllamaResponse(text=data["response"], model=data.get("model","llama3.2"), done=data.get("done",True))
    except urllib.error.URLError as e:
        raise OllamaUnavailableError(f"Ollama unreachable at {OLLAMA_HOST}: {e}") from e

def health_check() -> bool:
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            models = [m.get("name","") for m in data.get("models",[])]
            return any("llama3.2" in m for m in models)
    except Exception:
        return False
