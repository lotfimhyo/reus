# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from domain.workflow import (
    CycleDetected,
    InvalidDependency,
    InvalidTaskTransition,
    TaskSpec,
    TaskState,
    Workflow,
)


def test_create_simple_linear_workflow():
    wf = Workflow.create("pipeline", [
        TaskSpec(name="fetch"),
        TaskSpec(name="process", depends_on=["fetch"]),
        TaskSpec(name="store", depends_on=["process"]),
    ])
    assert len(wf.tasks) == 3


def test_cycle_is_detected():
    with pytest.raises(CycleDetected):
        Workflow.create("bad", [
            TaskSpec(name="a", depends_on=["b"]),
            TaskSpec(name="b", depends_on=["a"]),
        ])


def test_invalid_dependency_raises():
    with pytest.raises(InvalidDependency):
        Workflow.create("bad", [TaskSpec(name="a", depends_on=["ghost"])])


def test_only_root_tasks_are_ready_initially():
    wf = Workflow.create("pipeline", [
        TaskSpec(name="fetch"),
        TaskSpec(name="process", depends_on=["fetch"]),
    ])
    ready_names = {t.name for t in wf.ready_tasks()}
    assert ready_names == {"fetch"}


def test_completing_task_unlocks_dependents():
    wf = Workflow.create("pipeline", [
        TaskSpec(name="fetch"),
        TaskSpec(name="process", depends_on=["fetch"]),
    ])
    fetch = next(t for t in wf.tasks.values() if t.name == "fetch")
    wf.mark_ready(fetch.task_id)
    wf.start_task(fetch.task_id)
    wf.complete_task(fetch.task_id, result="data")

    ready_names = {t.name for t in wf.ready_tasks()}
    assert ready_names == {"process"}


def test_diamond_dependency_waits_for_both_branches():
    wf = Workflow.create("diamond", [
        TaskSpec(name="a"),
        TaskSpec(name="b", depends_on=["a"]),
        TaskSpec(name="c", depends_on=["a"]),
        TaskSpec(name="d", depends_on=["b", "c"]),
    ])
    by_name = {t.name: t for t in wf.tasks.values()}

    wf.mark_ready(by_name["a"].task_id)
    wf.start_task(by_name["a"].task_id)
    wf.complete_task(by_name["a"].task_id)

    ready = {t.name for t in wf.ready_tasks()}
    assert ready == {"b", "c"}

    wf.mark_ready(by_name["b"].task_id)
    wf.start_task(by_name["b"].task_id)
    wf.complete_task(by_name["b"].task_id)
    # d لا يجب أن تصبح جاهزة قبل اكتمال c أيضًا
    assert "d" not in {t.name for t in wf.ready_tasks()}

    wf.mark_ready(by_name["c"].task_id)
    wf.start_task(by_name["c"].task_id)
    wf.complete_task(by_name["c"].task_id)
    assert "d" in {t.name for t in wf.ready_tasks()}


def test_invalid_transition_raises():
    wf = Workflow.create("pipeline", [TaskSpec(name="only")])
    task_id = list(wf.tasks.keys())[0]
    with pytest.raises(InvalidTaskTransition):
        wf.complete_task(task_id)  # لا يمكن الإكمال قبل RUNNING


def test_fail_retries_before_permanent_failure():
    wf = Workflow.create("pipeline", [TaskSpec(name="flaky", max_retries=2)])
    task_id = list(wf.tasks.keys())[0]

    wf.mark_ready(task_id)
    wf.start_task(task_id)
    node, cancelled = wf.fail_task(task_id, error="timeout")
    assert node.state == TaskState.PENDING  # أُعيدت المحاولة (إصلاح ذاتي)
    assert node.retry_count == 1
    assert cancelled == []


def test_fail_after_exhausting_retries_is_permanent_and_cascades():
    wf = Workflow.create("pipeline", [
        TaskSpec(name="root", max_retries=0),
        TaskSpec(name="child", depends_on=["root"]),
    ])
    by_name = {t.name: t for t in wf.tasks.values()}
    root_id = by_name["root"].task_id

    wf.mark_ready(root_id)
    wf.start_task(root_id)
    node, cancelled = wf.fail_task(root_id, error="fatal")

    assert node.state == TaskState.FAILED
    assert len(cancelled) == 1
    assert cancelled[0].name == "child"
    assert wf.has_permanent_failure() is True


def test_is_complete_true_only_when_all_tasks_completed():
    wf = Workflow.create("pipeline", [TaskSpec(name="a"), TaskSpec(name="b")])
    assert wf.is_complete() is False
    for task_id in list(wf.tasks.keys()):
        wf.mark_ready(task_id)
        wf.start_task(task_id)
        wf.complete_task(task_id)
    assert wf.is_complete() is True
