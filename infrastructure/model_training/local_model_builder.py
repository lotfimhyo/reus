"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

LocalModelBuilder builds an isolated new Ollama model under a name distinct
from the daily-use model, such as `reus-evolved`, using the real `ollama create`
command. It consumes accumulated examples from `TrainingDatasetStore` and
reliability information from `ReliabilityAdvisor`.

**Important architectural boundary:** this is prompt/system distillation with
few-shot examples through Modelfile `MESSAGE` directives. It is not weight
fine-tuning such as LoRA or full fine-tuning. Weight tuning needs a dedicated
training framework and suitable compute that are outside the current local
execution environment. `ollama create` still creates a real, separately named
model in the local Ollama registry, but it should not be represented as weight
fine-tuning. `ModelfileBuilder` remains a replacement point for a future
weight-tuning builder without changing callers.

**Usage isolation:** this builder never automatically replaces the daily-use
model used by OllamaSynthesizer, IndependentTestReviewer, or daily execution.
The built model retains its separate `model_name` and is used only explicitly.
Replacing a base model requires a separate human decision; that decision is
intentionally outside this builder.
"""
from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from infrastructure.cognitive_core.cognitive.learning import LearningLayer
from infrastructure.model_training.training_dataset import TrainingDatasetStore

# Injectable command runner. The default is real subprocess.run; tests inject a
# double instead of requiring Ollama to be installed in the test environment.
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
    """Build textual Modelfile content from training examples and accumulated
    reliability knowledge. It is separate from LocalModelBuilder, which makes
    the real subprocess call, so content construction is independently testable."""

    def __init__(self, base_model: str = "llama3.1", max_examples_per_capability: int = 5):
        self.base_model = base_model
        self.max_examples_per_capability = max_examples_per_capability

    def build(self, examples_by_capability: dict[str, list], reliability_notes: list[str]) -> str:
        lines = [f"FROM {self.base_model}"]

        system_prompt = (
            "You are the evolved Reus model. Your knowledge has accumulated from "
            "actual execution of prior tasks within Reus, not from general data. "
            "When responding, prioritize patterns that succeeded in the examples below."
        )
        if reliability_notes:
            system_prompt += "\n\nAccumulated reliability notes:\n" + "\n".join(f"- {n}" for n in reliability_notes)
        lines.append(f'SYSTEM """{system_prompt}"""')

        for capability_name, examples in sorted(examples_by_capability.items()):
            for example in examples[: self.max_examples_per_capability]:
                user_text = f"[{capability_name}] input: {example.input!r}"
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
                    reliability_notes.append(f"{capability_name}: learned reliability adjustment = {adjustment:+.3f}")

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
                    stderr="No accumulated training examples exist yet; ollama create was not invoked.",
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
