"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

DailyReportService produces a factual daily development report. Every
`run_once` cycle harvests new successful episodes from episodic memory via
`TrainingDatasetStore.harvest()`, attempts an isolated evolved-model build
through `LocalModelBuilder.build()` only when new examples exist, and sends
the resulting operational counts to each administrative chat.

The background `start`/`stop` loop intentionally uses
`threading.Event.wait(interval)` instead of `time.sleep()`, allowing a prompt,
clean stop without waiting for an entire daily interval to elapse.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Optional

from application.telegram_service import TelegramService
from infrastructure.cognitive_core.memory.memory_layer import MemoryLayer
from infrastructure.model_training.local_model_builder import LocalModelBuilder, ModelBuildResult
from infrastructure.model_training.training_dataset import TrainingDatasetStore

logger = logging.getLogger("reus.daily_report")


@dataclass(frozen=True)
class DailyReportSummary:
    newly_harvested: int
    total_examples: int
    model_build: Optional[ModelBuildResult]
    proposal_counts: dict[str, int]


class DailyReportService:
    def __init__(
        self,
        memory: MemoryLayer,
        dataset: TrainingDatasetStore,
        model_builder: LocalModelBuilder,
        telegram: TelegramService,
        admin_chat_ids: frozenset[str],
        interval_seconds: float = 86400.0,
        promotion_service=None,
        governance=None,
    ):
        self._memory = memory
        self._dataset = dataset
        self._model_builder = model_builder
        self._telegram = telegram
        self._admin_chat_ids = admin_chat_ids
        self._interval_seconds = interval_seconds
        self._promotion_service = promotion_service
        self._governance = governance
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def run_once(self) -> DailyReportSummary:
        newly_harvested = self._dataset.harvest(self._memory)
        total_examples = self._dataset.count()

        model_result: Optional[ModelBuildResult] = None
        if newly_harvested > 0:
            # Rebuild only when genuinely new examples exist. Rebuilding from
            # the same data every day would consume local Ollama resources
            # without adding value.
            try:
                model_result = self._model_builder.build()
            except Exception:  # Do not suppress the complete report on build failure.
                logger.exception("daily_report.model_build_failed")
                model_result = None

        proposal_counts = self._governance.status_counts() if self._governance is not None else {}
        summary = DailyReportSummary(
            newly_harvested=newly_harvested,
            total_examples=total_examples,
            model_build=model_result,
            proposal_counts=proposal_counts,
        )
        self._send_report(summary)

        if self._promotion_service is not None:
            try:
                self._promotion_service.notify_if_newly_ready()
            except Exception:
                logger.exception("daily_report.promotion_check_failed")

        return summary

    def _send_report(self, summary: DailyReportSummary) -> None:
        lines = [
            "📊 Reus daily report",
            f"New training examples today: {summary.newly_harvested}",
            f"Total accumulated training examples: {summary.total_examples}",
        ]
        if summary.model_build is not None:
            if summary.model_build.success:
                lines.append(
                    f"✅ Evolved model '{summary.model_build.model_name}' was rebuilt "
                    f"using {summary.model_build.examples_used} example(s)."
                )
            else:
                lines.append(f"⚠️ Evolved-model rebuild failed: {summary.model_build.stderr or 'unknown error'}")
        if summary.proposal_counts:
            formatted_counts = ", ".join(f"{status}: {count}" for status, count in sorted(summary.proposal_counts.items()))
            lines.append(f"Governance proposal status: {formatted_counts}")
        text = "\n".join(lines)
        for chat_id in self._admin_chat_ids:
            self._telegram.deliver(chat_id, text)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("daily_report.cycle_failed")
            self._stop_event.wait(self._interval_seconds)
