"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

DailyReportService — "تقارير يومية لتطوره" المطلوبة صراحةً. كل دورة
(`run_once`) حقيقية بالكامل: تحصد حلقات ناجحة جديدة فعليًا من الذاكرة
الحدثية عبر `TrainingDatasetStore.harvest()`، تحاول بناء النموذج المتطوّر
المعزول عبر `LocalModelBuilder.build()` (يتخطّى البناء بأمان إن كانت
الأمثلة صفرًا — موثَّق في `local_model_builder.py`)، ثم تُركّب تقريرًا
نصيًا حقيقيًا من هذه الأرقام الفعلية وتُرسله لكل محادثات الإدارة.

قرار تصميم متعمَّد: الحلقة الخلفية (`start`/`stop`) تستخدم
`threading.Event.wait(interval)` لا `time.sleep()` — يسمح بإيقاف فوري ونظيف
(`stop()` لا ينتظر انتهاء الفاصل الزمني الكامل)، وهذا فرق حقيقي مهم عمليًا
لخدمة قد يكون فاصلها اليومي 24 ساعة.
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
            # لا يُعاد بناء النموذج المتطوّر إلا عند وجود أمثلة جديدة فعلية —
            # بناؤه من نفس البيانات القديمة يوميًا بلا داعٍ يُهدر موارد حقيقية
            # (استدعاء ollama create فعليًا) دون أي قيمة مضافة.
            try:
                model_result = self._model_builder.build()
            except Exception:  # لا نُسقط التقرير كله بسبب فشل بناء النموذج
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
            "📊 تقرير Reus اليومي",
            f"أمثلة تدريب جديدة اليوم: {summary.newly_harvested}",
            f"إجمالي أمثلة التدريب المتراكمة: {summary.total_examples}",
        ]
        if summary.model_build is not None:
            if summary.model_build.success:
                lines.append(
                    f"✅ أُعيد بناء النموذج المتطوّر '{summary.model_build.model_name}' "
                    f"({summary.model_build.examples_used} مثال)."
                )
            else:
                lines.append(f"⚠️ فشل إعادة بناء النموذج المتطوّر: {summary.model_build.stderr or 'غير معروف'}")
        if summary.proposal_counts:
            formatted_counts = ", ".join(f"{status}: {count}" for status, count in sorted(summary.proposal_counts.items()))
            lines.append(f"حالة مقترحات الحوكمة: {formatted_counts}")
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
