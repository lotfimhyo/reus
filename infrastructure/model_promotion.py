"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

ActiveModelStore is the single source of truth for which Ollama model currently
answers real tasks. It always starts with `base_model`, such as `llama3.1`, and
switches to an evolved model only through ModelPromotionService after explicit
human Telegram approval.

The decision is deliberately persisted to disk rather than memory alone. A
promotion is a conscious human decision; silently losing it after a service
restart and falling back to the base model would invalidate that decision. An
operator demotes explicitly through `/demote_model` or `set_active(base_model)`,
not through an accidental restart.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path


class ActiveModelStore:
    def __init__(self, state_path: str | Path, base_model: str):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.base_model = base_model
        self._lock = threading.RLock()

        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                self._active_model = data.get("active_model", base_model)
            except (json.JSONDecodeError, OSError):
                self._active_model = base_model
        else:
            self._active_model = base_model

    def get_active(self) -> str:
        with self._lock:
            return self._active_model

    def is_promoted(self) -> bool:
        with self._lock:
            return self._active_model != self.base_model

    def set_active(self, model_name: str) -> None:
        with self._lock:
            self._active_model = model_name
            self.state_path.write_text(json.dumps({"active_model": model_name}), encoding="utf-8")

    def reset_to_base(self) -> None:
        self.set_active(self.base_model)
