"""Ollama HTTP client — JISP (llama3.2)"""
import json, os, urllib.request, urllib.error, time
from dataclasses import dataclass

OLLAMA_HOST    = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

class OllamaUnavailableError(Exception): pass

@dataclass
class OllamaConfig:
    host: str = None
    model: str = None
    timeout: int = None

    def __post_init__(self):
        if self.host    is None: self.host    = OLLAMA_HOST
        if self.model   is None: self.model   = OLLAMA_MODEL
        if self.timeout is None: self.timeout = OLLAMA_TIMEOUT

    @classmethod
    def from_env(cls) -> "OllamaConfig":
        return cls(host=OLLAMA_HOST, model=OLLAMA_MODEL, timeout=OLLAMA_TIMEOUT)

@dataclass
class OllamaResponse:
    text: str
    model: str
    done: bool

def generate(prompt: str, model: str | None = None, timeout: int | None = None,
             config: OllamaConfig | None = None, max_retries: int = 2) -> str:
    cfg  = config or OllamaConfig.from_env()
    url  = f"{cfg.host}/api/generate"
    body = json.dumps({"model": model or cfg.model, "prompt": prompt, "stream": False}).encode()
    
    for attempt in range(max_retries + 1):
        try:
            req  = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout or cfg.timeout) as r:
                data = json.loads(r.read())
                return data["response"]
        except (urllib.error.URLError, urllib.error.HTTPError, EOFError) as e:
            if attempt < max_retries:
                time.sleep(1 + attempt)
                continue
            raise OllamaUnavailableError(f"Ollama failed after {max_retries + 1} attempts at {cfg.host}: {e}") from e
        except json.JSONDecodeError as e:
            raise OllamaUnavailableError(f"Invalid Ollama response: {e}") from e

def health_check() -> bool:
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            return any("llama3.2" in m.get("name","") for m in data.get("models",[]))
    except Exception:
        return False
