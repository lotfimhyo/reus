# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from domain.workflow import TaskNode
from infrastructure.agent_factory.builder import AgentBuilder
from infrastructure.agent_factory.manifest import AgentSpec, TestCase
from infrastructure.capability_binder import AgentCapabilityBinder, CapabilityBindingRejected
from infrastructure.cognitive_core.capability import CapabilityLayer
from infrastructure.cognitive_core.cognitive.engine import CognitiveEngine
from infrastructure.cognitive_core.cognitive.learning import LearningLayer
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog
from infrastructure.cognitive_core.memory import MemoryLayer
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor
from infrastructure.cognitive_task_executor import CognitiveTaskExecutor


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


def test_approved_build_is_immediately_executable(binder, task_executor):
    spec = AgentSpec(
        name="uppercaser",
        capability="text.uppercase",
        description="test",
        template="uppercase",
        test_cases=[TestCase(input="hello", expected_output="HELLO")],
    )
    binder.build_and_bind(spec)

    task = TaskNode(name="t", payload={"required_capability_name": "text.uppercase", "input": "hello world"})
    assert task_executor.execute(task) == "HELLO WORLD"


def test_rejected_build_is_never_bound(binder, capability_layer):
    spec = AgentSpec(name="bad", capability="x", description="", template="uppercase", test_cases=[])
    with pytest.raises(CapabilityBindingRejected):
        binder.build_and_bind(spec)
    assert capability_layer.discover() == []


def test_multiple_self_built_capabilities_coexist(binder, task_executor):
    binder.build_and_bind(
        AgentSpec(
            name="uppercaser", capability="text.uppercase", description="test", template="uppercase",
            test_cases=[TestCase(input="a", expected_output="A")],
        )
    )
    binder.build_and_bind(
        AgentSpec(
            name="wordcounter", capability="text.word_count", description="test", template="word_count",
            test_cases=[TestCase(input="a b c", expected_output=3)],
        )
    )

    upper_task = TaskNode(name="t1", payload={"required_capability_name": "text.uppercase", "input": "hi"})
    count_task = TaskNode(name="t2", payload={"required_capability_name": "text.word_count", "input": "one two three"})

    assert task_executor.execute(upper_task) == "HI"
    assert task_executor.execute(count_task) == 3


def test_missing_input_key_fails_clearly_not_silently_as_none(binder, local_executor):
    """Live-node testing exposed this behavior: invoking a capability without
    an ``input`` key silently passed ``None`` to the template tool. For a text
    capability such as ``uppercase``, that produced ``"NONE"``
    (``str(None).upper()``) as an apparently successful result rather than a
    clear error. This test proves the failure is now explicit and consistent
    across all capabilities."""
    descriptor = binder.build_and_bind(
        AgentSpec(
            name="uppercaser", capability="text.uppercase", description="test", template="uppercase",
            test_cases=[TestCase(input="a", expected_output="A")],
        )
    )

    class FakeStep:
        capability_id = descriptor.capability_id

    result = local_executor(FakeStep(), {"wrong_key": "x"})

    assert result.success is False
    assert "input" in result.error
    assert "text.uppercase" in result.error
