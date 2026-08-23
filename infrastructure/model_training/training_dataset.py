"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

TrainingDatasetStore harvests real, non-synthetic training pairs from actual
system execution. Each successful episode recorded in MemoryLayer.episodic by
CognitiveEngine.run becomes one line in a local, accumulating JSONL file. This
is knowledge accumulation over time from genuine use, not mocked or generated
training data.

This module is responsible only for harvesting and storage. Actual model
building from this data through an Ollama-oriented Modelfile belongs to
local_model_builder.py, so both remain independently testable.

Harvesting is intentionally idempotent: it uses episode_id as the uniqueness
key rather than a last-run timestamp. harvest() may run hourly, daily, or after
each episode without duplicating an output line or losing an episode after a
delayed harvest.
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
                        continue  # A corrupt line does not prevent loading the rest of the file.

    def harvest(self, memory: MemoryLayer, limit: int = 500) -> int:
        """Inspect the newest `limit` goal.completed episodes only. Failed
        episodes are deliberately excluded because treating their output as a
        correct training example would corrupt the goal. Append each previously
        unharvested episode as one line and return the number actually added."""
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
