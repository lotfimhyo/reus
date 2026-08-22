# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from domain.workflow import TaskNode
from infrastructure.agent_factory.builder import AgentBuilder
from infrastructure.capability_binder import AgentCapabilityBinder
from infrastructure.cognitive_core.capability import CapabilityLayer
from infrastructure.cognitive_core.cognitive.engine import CognitiveEngine
from infrastructure.cognitive_core.cognitive.learning import LearningLayer
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog
from infrastructure.cognitive_core.memory import MemoryLayer
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor
from infrastructure.cognitive_task_executor import CognitiveTaskExecutor
from infrastructure.seed_capabilities import DEFAULT_SPECS, seed_default_capabilities


@pytest.fixture
def audit_log(tmp_path):
    return AppendOnlyAuditLog(path=str(tmp_path / "audit.jsonl"))


@pytest.fixture
def capability_layer(audit_log, tmp_path):
    return CapabilityLayer(audit_log=audit_log, data_dir=str(tmp_path))


@pytest.fixture
def local_executor():
    return LocalExecutor()


@pytest.fixture
def binder(capability_layer, local_executor, tmp_path):
    builder = AgentBuilder(output_dir=str(tmp_path / "agents"))
    return AgentCapabilityBinder(builder=builder, capability_layer=capability_layer, local_executor=local_executor)


@pytest.fixture
def task_executor(audit_log, capability_layer, local_executor, tmp_path):
    memory_layer = MemoryLayer(audit_log=audit_log, data_dir=str(tmp_path))
    learning = LearningLayer(memory=memory_layer, audit_log=audit_log)
    engine = CognitiveEngine(
        memory=memory_layer, capabilities=capability_layer, audit_log=audit_log, learning=learning
    )
    return CognitiveTaskExecutor(engine=engine, executor=local_executor)


def test_seeding_publishes_all_default_specs(binder, capability_layer):
    published = seed_default_capabilities(binder, capability_layer)
    assert set(published) == {spec.capability for spec in DEFAULT_SPECS}


def test_seeding_is_idempotent_across_restart(binder, capability_layer):
    seed_default_capabilities(binder, capability_layer)
    second_run = seed_default_capabilities(binder, capability_layer)
    assert second_run == []


def test_seeded_capability_is_immediately_executable(binder, capability_layer, task_executor):
    seed_default_capabilities(binder, capability_layer)
    task = TaskNode(name="t", payload={"required_capability_name": "text.uppercase", "input": "hi"})
    assert task_executor.execute(task) == "HI"
