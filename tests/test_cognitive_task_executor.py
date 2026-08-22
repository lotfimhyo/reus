# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from application.task_executor import TaskExecutionError
from domain.workflow import TaskNode
from infrastructure.cognitive_core.capability import CapabilityLayer
from infrastructure.cognitive_core.capability.descriptor import RiskLevel
from infrastructure.cognitive_core.cognitive.engine import CognitiveEngine
from infrastructure.cognitive_core.cognitive.learning import LearningLayer
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog
from infrastructure.cognitive_core.memory import MemoryLayer
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor
from infrastructure.cognitive_task_executor import CognitiveTaskExecutor


@pytest.fixture
def audit_log(tmp_path):
    return AppendOnlyAuditLog(path=str(tmp_path / "audit_log.jsonl"))


@pytest.fixture
def capability_layer(audit_log, tmp_path):
    layer = CapabilityLayer(audit_log=audit_log, data_dir=str(tmp_path))
    layer.publish(
        component_id="test-component",
        name="echo",
        description="يُعيد نفس المدخلات كما هي — لأغراض الاختبار فقط",
        input_schema={},
        output_schema={},
        estimated_cost=0.0,
        risk_level=RiskLevel.LOW,
        tags=("test",),
    )
    return layer


@pytest.fixture
def memory_layer(audit_log, tmp_path):
    return MemoryLayer(audit_log=audit_log, data_dir=str(tmp_path))


@pytest.fixture
def engine(memory_layer, capability_layer, audit_log):
    learning = LearningLayer(memory=memory_layer, audit_log=audit_log)
    return CognitiveEngine(
        memory=memory_layer, capabilities=capability_layer, audit_log=audit_log, learning=learning
    )


@pytest.fixture
def local_executor(capability_layer):
    executor = LocalExecutor()
    [descriptor] = capability_layer.discover()
    executor.register_handler(descriptor.capability_id, lambda payload: {"echoed": payload})
    return executor


@pytest.fixture
def task_executor(engine, local_executor):
    return CognitiveTaskExecutor(engine=engine, executor=local_executor)


def test_execute_runs_matching_capability_and_returns_output(task_executor):
    task = TaskNode(
        name="echo-test",
        payload={"required_capability_name": "echo", "value": 42},
    )
    result = task_executor.execute(task)
    assert result["echoed"]["value"] == 42


def test_execute_without_capability_selector_raises(task_executor):
    task = TaskNode(name="no-selector", payload={})
    with pytest.raises(TaskExecutionError):
        task_executor.execute(task)


def test_execute_with_no_matching_capability_raises(task_executor):
    task = TaskNode(name="unknown", payload={"required_capability_name": "does-not-exist"})
    with pytest.raises(TaskExecutionError):
        task_executor.execute(task)
