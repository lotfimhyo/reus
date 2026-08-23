"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

ModelPromotionService closes the governed evolution loop: an evolved model can
replace the active model only through a human Telegram decision, never
automatically.

**Readiness criteria (`evaluate_readiness`) are auditable and configurable:**
1. The accumulated training-example count meets `min_examples`. The default is
   intentionally small for testing; real production operation should increase it
   substantially before trusting the threshold.
2. The last actual evolved-model build (`LocalModelBuilder.last_build`) succeeded.
   This is evidence from a prior attempt, not a promise that a build will work.
3. No capability represented in training data has a learned negative reliability
   score after actual `learn_from_capability` processing. A capability shown to
   be unreliable blocks maturity irrespective of other criteria.

Meeting all criteria **does not promote anything automatically**. It only
enables an administrator to request `/promote_model`; `ActiveModelStore` changes
only after dual human approval through `request_approval`. `/demote_model` has
no maturity prerequisite because a safety rollback must remain easy.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from application.telegram_service import TelegramService
from infrastructure.cognitive_core.cognitive.learning import LearningLayer
from infrastructure.event_bus import Event, EventBus
from infrastructure.model_promotion import ActiveModelStore
from infrastructure.model_training.local_model_builder import LocalModelBuilder
from infrastructure.model_training.training_dataset import TrainingDatasetStore

# Matches the penalty spectrum in reliability_advisor.py. A lower value means
# actual unreliability rather than merely missing evidence (neutral is 0.0).
_UNRELIABLE_THRESHOLD = -1.0


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    total_examples: int
    min_examples: int
    last_build_succeeded: Optional[bool]
    unreliable_capabilities: list[str]

    def reason(self) -> str:
        if self.ready:
            return "All maturity criteria are met."
        reasons = []
        if self.total_examples < self.min_examples:
            reasons.append(f"training examples ({self.total_examples}) are below the minimum ({self.min_examples})")
        if self.last_build_succeeded is not True:
            reasons.append("the last actual evolved-model build has not succeeded")
        if self.unreliable_capabilities:
            reasons.append(f"capabilities shown to be unreliable: {', '.join(self.unreliable_capabilities)}")
        return "; ".join(reasons)


class ModelPromotionService:
    def __init__(
        self,
        dataset: TrainingDatasetStore,
        learning: LearningLayer,
        model_builder: LocalModelBuilder,
        active_model_store: ActiveModelStore,
        telegram: TelegramService,
        admin_chat_ids: frozenset[str],
        evolved_model_name: str,
        min_examples: int = 20,
        event_bus: Optional[EventBus] = None,
    ):
        self._dataset = dataset
        self._learning = learning
        self._model_builder = model_builder
        self._active_model_store = active_model_store
        self._telegram = telegram
        self._admin_chat_ids = admin_chat_ids
        self._evolved_model_name = evolved_model_name
        self._min_examples = min_examples
        self._bus = event_bus
        self._already_notified = False

        telegram.register_admin_command("/model_status", self._cmd_status)
        telegram.register_admin_command("/promote_model", self._cmd_promote)
        telegram.register_admin_command("/demote_model", self._cmd_demote)

    def evaluate_readiness(self) -> ReadinessReport:
        total_examples = self._dataset.count()
        last_build = self._model_builder.last_build
        last_build_succeeded = last_build.success if last_build is not None else None

        unreliable: list[str] = []
        for capability_name, examples in self._dataset.examples_by_capability().items():
            capability_id = examples[0].capability_id if examples else None
            if not capability_id:
                continue
            # Always learn from current evidence, never a stale stored value.
            self._learning.learn_from_capability(capability_id)
            if self._learning.score_adjustment(capability_id) < _UNRELIABLE_THRESHOLD:
                unreliable.append(capability_name)

        ready = total_examples >= self._min_examples and last_build_succeeded is True and not unreliable
        return ReadinessReport(
            ready=ready,
            total_examples=total_examples,
            min_examples=self._min_examples,
            last_build_succeeded=last_build_succeeded,
            unreliable_capabilities=unreliable,
        )

    def notify_if_newly_ready(self) -> None:
        """Run periodically, for example after each DailyReportService harvest.
        Send one notification per not-ready-to-ready transition, reset the
        notification state if readiness is later lost, and avoid daily spam."""
        report = self.evaluate_readiness()
        if not report.ready:
            self._already_notified = False
            return
        if self._already_notified or self._active_model_store.is_promoted():
            return

        self._already_notified = True
        for chat_id in self._admin_chat_ids:
            self._telegram.deliver(
                chat_id,
                "🧬 The evolved model meets the configured maturity criteria (see /model_status).\n"
                "To request promotion as the active model: /promote_model\n"
                "A promotion applies to the next task without a restart.",
            )

    def _cmd_status(self, chat_id: str, args: str) -> None:
        report = self.evaluate_readiness()
        active = self._active_model_store.get_active()
        lines = [
            f"Active model: {active}",
            f"Promoted? {'yes' if self._active_model_store.is_promoted() else 'no'}",
            f"Accumulated training examples: {report.total_examples} (minimum: {report.min_examples})",
            f"Last build succeeded? {report.last_build_succeeded}",
            f"Ready for promotion? {'yes' if report.ready else 'no — ' + report.reason()}",
        ]
        self._telegram.deliver(chat_id, "\n".join(lines))

    def _cmd_promote(self, chat_id: str, args: str) -> None:
        # Always re-evaluate; never rely on a possibly stale earlier check.
        report = self.evaluate_readiness()
        if not report.ready:
            self._telegram.deliver(chat_id, f"❌ The evolved model is not ready for promotion: {report.reason()}")
            return

        approval_id = f"model-promote-{uuid.uuid4().hex[:8]}"
        self._telegram.request_approval(
            chat_id,
            approval_id,
            f"Promote the active model from its current value to '{self._evolved_model_name}'. "
            f"The promotion applies to the next task through Ollama.",
            on_approve=lambda: self._execute_promote(chat_id),
            on_reject=lambda: self._telegram.deliver(chat_id, "Promotion cancelled."),
        )

    def _execute_promote(self, chat_id: str) -> None:
        self._active_model_store.set_active(self._evolved_model_name)
        self._publish("model.promoted", {"model_name": self._evolved_model_name})
        self._telegram.deliver(chat_id, f"✅ The active model was promoted to '{self._evolved_model_name}'.")

    def _cmd_demote(self, chat_id: str, args: str) -> None:
        if not self._active_model_store.is_promoted():
            self._telegram.deliver(chat_id, "The active model is already the base model; there is nothing to demote.")
            return
        previous = self._active_model_store.get_active()
        self._active_model_store.reset_to_base()
        self._already_notified = False  # Permit a new notice if the model becomes ready again.
        self._publish("model.demoted", {"previous_model_name": previous})
        self._telegram.deliver(chat_id, f"↩️ The active model was restored to '{self._active_model_store.base_model}'.")

    def _publish(self, name: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(Event(name=name, payload=payload))
