"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
from unittest.mock import MagicMock

from application.task_worker import TaskWorker


def _worker(lease):
    orchestrator = MagicMock()
    executor = MagicMock()
    worker = TaskWorker(orchestrator, executor, MagicMock(), pool_size=1, lease_coordinator=lease)
    return worker, orchestrator, executor


def test_worker_commits_lease_before_execution_and_completion_after_result():
    lease = MagicMock()
    lease.acquire.return_value = True
    lease.complete.return_value = True
    worker, orchestrator, executor = _worker(lease)
    task = MagicMock()
    orchestrator.start_task.return_value = task
    executor.execute.return_value = {"answer": "ok"}

    worker._process("wf", "task")

    lease.acquire.assert_called_once_with("wf:task")
    executor.execute.assert_called_once_with(task)
    lease.complete.assert_called_once_with("wf:task")
    orchestrator.complete_task.assert_called_once_with("wf", "task", result={"answer": "ok"})


def test_worker_holds_execution_when_lease_commit_fails():
    lease = MagicMock()
    lease.acquire.return_value = False
    worker, orchestrator, executor = _worker(lease)
    orchestrator.start_task.return_value = MagicMock()

    worker._process("wf", "task")

    executor.execute.assert_not_called()
    orchestrator.complete_task.assert_not_called()
    orchestrator.fail_task.assert_called_once()
