"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
from __future__ import annotations

import os
import socket
import time
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _clear_container_caches() -> None:
    import container

    for value in vars(container).values():
        clear = getattr(value, "cache_clear", None)
        if callable(clear):
            clear()


class TestApiClusterWorkerStartup(unittest.TestCase):
    def setUp(self):
        os.environ["REUS_API_KEY"] = "admin-key"
        os.environ["REUS_USER_API_KEY"] = "user-key"
        os.environ["REUS_WORKER_ENABLED"] = "true"
        os.environ["REUS_CLUSTER_WORKER_ENABLED"] = "true"
        os.environ["REUS_AUTO_SEED_DEFAULT_AGENT"] = "false"
        os.environ["REUS_TASK_EXECUTOR"] = "default"

        import config

        config.get_settings.cache_clear()

    def tearDown(self):
        for key in [
            "REUS_API_KEY",
            "REUS_USER_API_KEY",
            "REUS_WORKER_ENABLED",
            "REUS_CLUSTER_WORKER_ENABLED",
            "REUS_AUTO_SEED_DEFAULT_AGENT",
            "REUS_TASK_EXECUTOR",
            "REUS_CLUSTER_WORKER_DATA_DIR",
            "REUS_CLUSTER_WORKER_MTLS_PORT",
            "REUS_CLUSTER_WORKER_BOOTSTRAP_PORT",
        ]:
            os.environ.pop(key, None)

        import config

        config.get_settings.cache_clear()
        _clear_container_caches()

    def test_admin_lifespan_starts_cluster_runtime_before_worker_and_stops_it_after(self):
        from api.main import create_app

        events: list[str] = []
        worker = MagicMock()
        worker.start.side_effect = lambda: events.append("worker-start")
        worker.stop.side_effect = lambda: events.append("worker-stop")
        observability = MagicMock()

        with patch("container.get_observability_service", return_value=observability), \
             patch("container.start_cluster_worker_runtime", side_effect=lambda: events.append("cluster-start")), \
             patch("container.stop_cluster_worker_runtime", side_effect=lambda: events.append("cluster-stop")), \
             patch("container.get_task_worker", return_value=worker):
            with TestClient(create_app(include_public=False, include_admin=True)) as client:
                self.assertEqual(client.get("/health").status_code, 200)

        self.assertEqual(events, ["cluster-start", "worker-start", "worker-stop", "cluster-stop"])
        observability.start.assert_called_once()

    def test_public_app_never_touches_cluster_worker_runtime_even_if_enabled(self):
        from api.main import create_app

        observability = MagicMock()
        with patch("container.get_observability_service", return_value=observability), \
             patch("container.start_cluster_worker_runtime") as start_cluster, \
             patch("container.get_task_worker") as get_worker:
            with TestClient(create_app(include_public=True, include_admin=False)) as client:
                self.assertEqual(client.get("/health").status_code, 200)

        start_cluster.assert_not_called()
        get_worker.assert_not_called()

    def test_real_admin_lifecycle_completes_then_blocks_workflow_through_raft_lease(self):
        import tempfile

        from application.agent_service import RegisterAgentCommand
        from application.orchestrator_service import CreateWorkflowCommand
        from domain.workflow import TaskSpec
        from infrastructure.cluster_network.raft import Role

        with tempfile.TemporaryDirectory() as data_dir:
            os.environ["REUS_CLUSTER_WORKER_DATA_DIR"] = data_dir
            os.environ["REUS_CLUSTER_WORKER_MTLS_PORT"] = str(_free_port())
            os.environ["REUS_CLUSTER_WORKER_BOOTSTRAP_PORT"] = str(_free_port())
            import config

            config.get_settings.cache_clear()
            _clear_container_caches()
            from api.main import create_app
            from container import get_agent_service, get_cluster_worker_node, get_orchestrator_service

            with TestClient(create_app(include_public=False, include_admin=True)):
                agent = get_agent_service().register_agent(
                    RegisterAgentCommand(name="cluster-api-agent", permissions={"read:memory", "write:memory"}, goals=[])
                )
                orchestrator = get_orchestrator_service()
                accepted = orchestrator.create_workflow(
                    CreateWorkflowCommand(
                        name="accepted",
                        tasks=[TaskSpec(name="raft-accepted", agent_id=agent.agent_id, payload={"prompt": "lease test"})],
                    )
                )
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and not orchestrator.get_workflow(accepted.workflow_id).is_complete():
                    time.sleep(0.02)

                node = get_cluster_worker_node()
                self.assertTrue(orchestrator.get_workflow(accepted.workflow_id).is_complete())
                accepted_task = next(iter(accepted.tasks))
                self.assertEqual(node.raft_cluster.task_state._tasks[f"{accepted.workflow_id}:{accepted_task}"]["status"], "completed")

                node.raft.role = Role.FOLLOWER
                rejected = orchestrator.create_workflow(
                    CreateWorkflowCommand(
                        name="blocked",
                        tasks=[TaskSpec(name="raft-blocked", agent_id=agent.agent_id, payload={"prompt": "leadership loss test"})],
                    )
                )
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and not orchestrator.get_workflow(rejected.workflow_id).has_permanent_failure():
                    time.sleep(0.02)

                self.assertTrue(orchestrator.get_workflow(rejected.workflow_id).has_permanent_failure())


if __name__ == "__main__":
    unittest.main()
