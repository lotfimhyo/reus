"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

ActiveModelStore — الحقيقة الوحيدة (single source of truth) لـ"أي نموذج
Ollama يُستخدَم فعليًا الآن للإجابة على مهام حقيقية". يبدأ دائمًا بالنموذج
الأساسي (`base_model`، مثل `llama3.1`)، ولا يتحوّل للنموذج المتطوّر
(`reus-evolved`) إلا عبر `ModelPromotionService` بعد موافقة بشرية صريحة عبر
تلغرام.

قرار تصميم متعمَّد: **محفوظ على القرص، لا في الذاكرة فقط**. قرار الترقية
قرار بشري واعٍ — فقدانه بصمت عند إعادة تشغيل الخدمة (بالعودة التلقائية
للنموذج الأساسي دون علم أحد) يُلغي أثر ذلك القرار بصمت، وهو أخطر من مجرد
إزعاج تشغيلي. من يريد التراجع عن الترقية يفعل ذلك صراحة عبر `/demote_model`
أو `set_active(base_model)`، لا عبر إعادة تشغيل عرَضية.
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
