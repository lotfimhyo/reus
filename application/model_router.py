# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
ModelRouter: يختار "النموذج الأنسب" لمهمة معيّنة من سجل نماذج معروف مسبقًا،
بناءً على القدرات المطلوبة وسقف الكلفة وحجم السياق. منطق التوجيه هنا حتمي
ومحلي بالكامل (بلا شبكة)، وقابل للاختبار الكامل دون أي اعتماد خارجي.
الاستدعاء الفعلي للنموذج المُختار مسؤولية طبقة أخرى تمامًا (ModelProvider).
"""
from __future__ import annotations

from dataclasses import dataclass, field


class NoSuitableModel(Exception):
    def __init__(self, reason: str):
        super().__init__(f"لا يوجد نموذج مناسب: {reason}")


@dataclass(frozen=True)
class ModelProfile:
    """ملف تعريف نموذج واحد: خصائصه التقنية والاقتصادية المعروفة مسبقًا."""

    name: str
    provider: str
    capability_tags: frozenset[str]
    input_cost_per_1k_tokens_usd: float
    output_cost_per_1k_tokens_usd: float
    max_context_tokens: int
    # تقدير نسبي لسرعة الاستجابة (1 = الأسرع)، يُستخدم فقط لترتيب "الأسرع" عند التعادل
    relative_speed_rank: int


@dataclass
class TaskRequirements:
    """ما تحتاجه مهمة معيّنة من نموذج، وليس النموذج بعينه."""

    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    min_context_tokens: int = 0
    max_input_cost_per_1k_tokens_usd: float | None = None
    prefer: str = "cheapest"  # "cheapest" | "fastest" | "most_capable"


class ModelRouter:
    def __init__(self, profiles: list[ModelProfile]) -> None:
        if not profiles:
            raise ValueError("يجب تسجيل نموذج واحد على الأقل في ModelRouter")
        self._profiles = list(profiles)

    def list_profiles(self) -> list[ModelProfile]:
        return list(self._profiles)

    def select(self, requirements: TaskRequirements) -> ModelProfile:
        candidates = [p for p in self._profiles if requirements.required_capabilities <= p.capability_tags]
        if not candidates:
            raise NoSuitableModel(
                f"لا يوجد نموذج يملك كل القدرات المطلوبة: {sorted(requirements.required_capabilities)}"
            )

        candidates = [p for p in candidates if p.max_context_tokens >= requirements.min_context_tokens]
        if not candidates:
            raise NoSuitableModel(f"لا يوجد نموذج بسياق يكفي {requirements.min_context_tokens} رمزًا")

        if requirements.max_input_cost_per_1k_tokens_usd is not None:
            candidates = [
                p for p in candidates if p.input_cost_per_1k_tokens_usd <= requirements.max_input_cost_per_1k_tokens_usd
            ]
            if not candidates:
                raise NoSuitableModel(
                    f"لا يوجد نموذج ضمن سقف الكلفة {requirements.max_input_cost_per_1k_tokens_usd}$ لكل 1000 رمز إدخال"
                )

        if requirements.prefer == "fastest":
            return min(candidates, key=lambda p: p.relative_speed_rank)
        if requirements.prefer == "most_capable":
            return max(candidates, key=lambda p: len(p.capability_tags))
        # الافتراضي: "cheapest" — الأرخص إدخالًا، وعند التعادل الأرخص إخراجًا
        return min(candidates, key=lambda p: (p.input_cost_per_1k_tokens_usd, p.output_cost_per_1k_tokens_usd))
