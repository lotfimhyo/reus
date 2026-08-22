# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
TaskExecutor Port: يحدد "كيف تُنفَّذ مهمة فعليًا" دون أن يعرف OrchestratorService
أو TaskWorker أي تفاصيل عن ذلك (Plugin Architecture). أي منطق تنفيذ مستقبلي
(استدعاء نموذج، أداة خارجية، خط أنابيب بيانات) يُطبَّق هنا فقط.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from domain.workflow import TaskNode


class TaskExecutionError(Exception):
    """تُرفع عند فشل تنفيذ مهمة لأي سبب (وكيل مفقود، صلاحية منقوصة، خطأ داخلي)."""


class TaskExecutor(ABC):
    @abstractmethod
    def execute(self, task: TaskNode) -> Any:
        """ينفّذ المهمة ويُعيد نتيجة قابلة للتسلسل (JSON-serializable)، أو يرفع TaskExecutionError."""
        ...
