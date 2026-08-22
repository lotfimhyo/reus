# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
OllamaClient: a minimal, dependency-free (stdlib-only) client for a local
Ollama server (`ollama serve`, default http://localhost:11434).

This is the ONLY LLM backend wired into Project Phoenix by user preference
— no Anthropic/OpenAI/etc. API calls anywhere in the "self-directed" path.
Everything runs against a model already pulled locally (`ollama pull
<model>`), so there is no external network dependency at inference time
either — consistent with the project's offline-first design so far.
"""

import json
import urllib.error
import urllib.request
from typing import Optional


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate(
        self, prompt: str, system: Optional[str] = None, json_mode: bool = False, model: Optional[str] = None
    ) -> str:
        """Single-turn generation. Returns the model's raw text response.
        `model` overrides `self.model` for this call only — used by
        OllamaTaskExecutor to route to a dynamically-promoted evolved model
        without recreating the client (see infrastructure/model_promotion.py)."""
        effective_model = model or self.model
        payload = {
            "model": effective_model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
        except urllib.error.URLError as e:
            raise OllamaError(
                f"Could not reach Ollama at {self.base_url}. "
                f"Is `ollama serve` running and is model '{effective_model}' pulled "
                f"(`ollama pull {effective_model}`)? Original error: {e}"
            ) from e

        return data.get("response", "")

    def is_reachable(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3.0):
                return True
        except urllib.error.URLError:
            return False
