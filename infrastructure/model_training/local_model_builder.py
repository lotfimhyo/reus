"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

LocalModelBuilder — يبني نموذج Ollama جديد منعزل (باسم مختلف عن نموذج
"الاستخدام" اليومي، مثل `reus-evolved`) اعتمادًا فعليًا على `ollama create`
(أمر حقيقي مدعوم أصلًا من Ollama)، مُغذّى بأمثلة تدريب حقيقية متراكمة من
`TrainingDatasetStore` + معرفة موثوقية حقيقية من `ReliabilityAdvisor`.

**صدق معماري لازم إشهاره صراحةً، لا إخفاؤه:** هذا تقطير على مستوى
الـPrompt/System + أمثلة قليلة (few-shot عبر `Modelfile`'s `MESSAGE`
directives) — وليس ضبطًا دقيقًا حقيقيًا لأوزان النموذج (LoRA/full
fine-tune). ضبط الأوزان الحقيقي يتطلب إطار تدريب (مثل llama.cpp
LoRA/unsloth/axolotl) ووحدة معالجة رسومات (GPU) — غير متوفرين في بيئة
التنفيذ الحالية (بلا شبكة، بلا GPU). ما يُبنى هنا حقيقي وفعّال ومدعوم رسميًا
من Ollama (`ollama create` تنشئ فعليًا نموذجًا مسمّى جديدًا في سجل النماذج
المحلي، قابلًا للاستدعاء ككيان منفصل تمامًا)، لكنه ليس ما يفهمه أغلب الناس
تقنيًا من مصطلح "fine-tuning". نقطة التوسّع لضبط أوزان حقيقي لاحقًا محفوظة
عبر `ModelfileBuilder` (استبدال الباني بمكوّن LoRA حقيقي دون تغيير أي
مستدعٍ آخر — نفس نمط `BaseSynthesizer` القابل للاستبدال).

**العزل عن الاستخدام** (المطلوب صراحةً: "منعزل عن الاستخدام"): النموذج
المبني هنا لا يُستبدَل به نموذج الاستخدام (`OllamaClient` المُستخدَم في
`OllamaSynthesizer`/`IndependentTestReviewer`/التنفيذ اليومي) تلقائيًا أبدًا
— يبقى تحت اسم منفصل (`model_name`)، ولا يُستدعى إلا صراحةً، ولا يُستبدَل
النموذج الأساسي به إلا بقرار بشري صريح (أمر تلغرام منفصل، خارج نطاق هذا
الملف عمدًا — القرار بشأن "متى نثق بالنموذج المتطوّر كافيًا لاستخدامه" قرار
بشري لا آلي).
"""
from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from infrastructure.cognitive_core.cognitive.learning import LearningLayer
from infrastructure.model_training.training_dataset import TrainingDatasetStore

# دالة تشغيل أوامر قابلة للحقن — الافتراضي subprocess.run الحقيقي، لكن
# الاختبارات تحقن دالة وهمية بدل الاعتماد على وجود ollama مثبَّتًا فعليًا في
# بيئة الاختبار (لا شبكة، لا ollama هنا) — لا شيء آخر في هذا الملف يُحاكى.
CommandRunner = Callable[[list[str]], "subprocess.CompletedProcess"]


def _default_command_runner(args: list[str]) -> "subprocess.CompletedProcess":
    return subprocess.run(args, capture_output=True, text=True, timeout=600)


@dataclass(frozen=True)
class ModelBuildResult:
    success: bool
    model_name: str
    modelfile_path: str
    examples_used: int
    stdout: str
    stderr: str


class ModelfileBuilder:
    """يبني محتوى Modelfile نصيًا من أمثلة تدريب + معرفة موثوقية متراكمة.
    مفصول عن LocalModelBuilder (الذي يستدعي subprocess فعليًا) حتى يمكن
    اختبار منطق بناء المحتوى بمعزل تام عن أي عملية خارجية."""

    def __init__(self, base_model: str = "llama3.1", max_examples_per_capability: int = 5):
        self.base_model = base_model
        self.max_examples_per_capability = max_examples_per_capability

    def build(self, examples_by_capability: dict[str, list], reliability_notes: list[str]) -> str:
        lines = [f"FROM {self.base_model}"]

        system_prompt = (
            "أنت نموذج Reus المتطوّر — تراكمت معرفتك من تنفيذ فعلي حقيقي لمهام "
            "سابقة داخل نظام Reus، لا من بيانات عامة. عند الإجابة، اعتمد أولًا "
            "على الأنماط التي أثبتت نجاحها في الأمثلة أدناه."
        )
        if reliability_notes:
            system_prompt += "\n\nملاحظات موثوقية متراكمة:\n" + "\n".join(f"- {n}" for n in reliability_notes)
        lines.append(f'SYSTEM """{system_prompt}"""')

        for capability_name, examples in sorted(examples_by_capability.items()):
            for example in examples[: self.max_examples_per_capability]:
                user_text = f"[{capability_name}] المدخل: {example.input!r}"
                assistant_text = f"{example.output!r}"
                lines.append(f'MESSAGE user """{user_text}"""')
                lines.append(f'MESSAGE assistant """{assistant_text}"""')

        return "\n".join(lines) + "\n"


class LocalModelBuilder:
    def __init__(
        self,
        dataset: TrainingDatasetStore,
        learning: Optional[LearningLayer],
        modelfile_builder: Optional[ModelfileBuilder] = None,
        command_runner: CommandRunner = _default_command_runner,
        model_name: str = "reus-evolved",
        workdir: str | Path = "data/model_training",
    ):
        self.dataset = dataset
        self.learning = learning
        self.modelfile_builder = modelfile_builder or ModelfileBuilder()
        self._run = command_runner
        self.model_name = model_name
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.last_build: Optional[ModelBuildResult] = None

    def build(self) -> ModelBuildResult:
        with self._lock:
            examples_by_capability = self.dataset.examples_by_capability()
            total_examples = sum(len(v) for v in examples_by_capability.values())

            reliability_notes: list[str] = []
            if self.learning is not None:
                for capability_name, examples in examples_by_capability.items():
                    capability_id = examples[0].capability_id if examples else None
                    if not capability_id:
                        continue
                    adjustment = self.learning.score_adjustment(capability_id)
                    reliability_notes.append(f"{capability_name}: تعديل موثوقية متعلَّم = {adjustment:+.3f}")

            modelfile_content = self.modelfile_builder.build(examples_by_capability, reliability_notes)
            modelfile_path = self.workdir / "Modelfile"
            modelfile_path.write_text(modelfile_content, encoding="utf-8")

            if total_examples == 0:
                result = ModelBuildResult(
                    success=False,
                    model_name=self.model_name,
                    modelfile_path=str(modelfile_path),
                    examples_used=0,
                    stdout="",
                    stderr="لا توجد أمثلة تدريب متراكمة بعد — لم يُستدعَ ollama create.",
                )
                self.last_build = result
                return result

            process = self._run(["ollama", "create", self.model_name, "-f", str(modelfile_path)])
            success = process.returncode == 0
            result = ModelBuildResult(
                success=success,
                model_name=self.model_name,
                modelfile_path=str(modelfile_path),
                examples_used=total_examples,
                stdout=process.stdout,
                stderr=process.stderr,
            )
            self.last_build = result
            return result
