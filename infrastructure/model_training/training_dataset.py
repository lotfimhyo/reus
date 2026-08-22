"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

TrainingDatasetStore — يحصد أزواج تدريب حقيقية (لا مُصطنَعة) من التنفيذ
الفعلي للنظام: كل حلقة (Episode) ناجحة مُسجَّلة فعلًا في MemoryLayer.episodic
(عبر CognitiveEngine.run() الحقيقي، انظر التعديل في cognitive/engine.py
الذي أضاف `input` لحمولة الحلقة تحديدًا من أجل هذا) تصبح سطرًا واحدًا في
ملف JSONL تراكمي محلي — هذا هو "تراكم المعارف عبر الوقت" المطلوب حرفيًا:
بيانات حقيقية من استخدام حقيقي، لا بيانات وهمية أو مولَّدة صناعيًا.

هذا الملف مسؤول فقط عن **الحصاد والتخزين**. البناء الفعلي لنموذج من هذه
البيانات (عبر Modelfile مُوجَّه لـOllama) في `local_model_builder.py` — يبقى
كل واحد قابلًا للاختبار منفصلًا.

قرار تصميم متعمَّد: الحصاد idempotent بالكامل (يعتمد على `episode_id` كمفتاح
تفرّد، لا على "آخر مرة شغّلنا فيها") — يمكن استدعاء `harvest()` بأي تكرار
(كل ساعة، كل يوم، بعد كل حلقة) دون خطر تكرار سطر واحد مرتين في الملف
الناتج، ودون فقدان أي حلقة إن تأخّر الحصاد.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infrastructure.cognitive_core.memory.memory_layer import MemoryLayer


@dataclass(frozen=True)
class TrainingExample:
    episode_id: str
    task_id: str
    capability_id: str
    capability_name: str
    input: Any
    output: Any

    def to_json_line(self) -> str:
        return json.dumps(
            {
                "episode_id": self.episode_id,
                "task_id": self.task_id,
                "capability_id": self.capability_id,
                "capability_name": self.capability_name,
                "input": self.input,
                "output": self.output,
            },
            ensure_ascii=False,
        )


class TrainingDatasetStore:
    def __init__(self, dataset_path: str | Path):
        self.dataset_path = Path(dataset_path)
        self.dataset_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._known_episode_ids: set[str] = set()
        if self.dataset_path.exists():
            with self.dataset_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._known_episode_ids.add(json.loads(line)["episode_id"])
                    except (json.JSONDecodeError, KeyError):
                        continue  # سطر تالف لا يوقف تحميل بقية الملف

    def harvest(self, memory: MemoryLayer, limit: int = 500) -> int:
        """يفحص أحدث `limit` حلقة من فعل `goal.completed` فقط (الفاشلة
        متروكة عمدًا — تدريب نموذج على مخرجات فاشلة كأمثلة "صحيحة" يُفسد
        الهدف)، ويُضيف كل حلقة جديدة (لم تُحصَد من قبل) كسطر واحد. يُعيد
        عدد الأسطر الجديدة المُضافة فعليًا."""
        with self._lock:
            episodes = memory.episodes_by_action("goal.completed", limit=limit)
            new_examples: list[TrainingExample] = []
            for episode in episodes:
                if episode.id in self._known_episode_ids:
                    continue
                result = episode.result or {}
                if not result.get("success"):
                    continue
                new_examples.append(
                    TrainingExample(
                        episode_id=episode.id,
                        task_id=episode.task_id,
                        capability_id=episode.payload.get("capability_id", ""),
                        capability_name=episode.payload.get("capability_name", ""),
                        input=episode.payload.get("input"),
                        output=result.get("output"),
                    )
                )

            if not new_examples:
                return 0

            with self.dataset_path.open("a", encoding="utf-8") as f:
                for example in new_examples:
                    f.write(example.to_json_line() + "\n")
                    self._known_episode_ids.add(example.episode_id)

            return len(new_examples)

    def count(self) -> int:
        with self._lock:
            return len(self._known_episode_ids)

    def read_all(self) -> list[TrainingExample]:
        with self._lock:
            if not self.dataset_path.exists():
                return []
            examples = []
            with self.dataset_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    examples.append(
                        TrainingExample(
                            episode_id=data["episode_id"],
                            task_id=data["task_id"],
                            capability_id=data["capability_id"],
                            capability_name=data["capability_name"],
                            input=data["input"],
                            output=data["output"],
                        )
                    )
            return examples

    def examples_by_capability(self) -> dict[str, list[TrainingExample]]:
        grouped: dict[str, list[TrainingExample]] = {}
        for example in self.read_all():
            grouped.setdefault(example.capability_name, []).append(example)
        return grouped
