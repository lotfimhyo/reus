"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess


SPEC = importlib.util.spec_from_file_location("reus_doctor", Path(__file__).parents[1] / "scripts" / "reus_doctor.py")
doctor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(doctor)


def test_doctor_reports_default_executor_as_non_chat_ready(tmp_path: Path):
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").touch()
    (tmp_path / ".env").write_text(
        "REUS_API_KEY=valid-local-key\n"
        "REUS_USER_API_KEY=valid-local-user-key\n"
        "REUS_TASK_EXECUTOR=default\n",
        encoding="utf-8",
    )

    issues = doctor.check(tmp_path, strict=False)

    assert any("does not support /chat" in issue for issue in issues)


def test_doctor_accepts_local_model_router_configuration_without_external_probe(tmp_path: Path):
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").touch()
    (tmp_path / ".env").write_text(
        "REUS_API_KEY=valid-local-key\n"
        "REUS_USER_API_KEY=valid-local-user-key\n"
        "REUS_TASK_EXECUTOR=model_router\n",
        encoding="utf-8",
    )

    assert doctor.check(tmp_path, strict=False) == []


def test_control_surface_advertises_safe_first_and_join_node_commands():
    control_script = (Path(__file__).parents[1] / "scripts" / "reusctl.sh").read_text(encoding="utf-8")

    assert "start-first-node" in control_script
    assert "join-node" in control_script
    assert 'REUS_NODE_BIND_HOST:-127.0.0.1' in control_script


def _temporary_control_project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "reus"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy(Path(__file__).parents[1] / "scripts" / "reusctl.sh", scripts / "reusctl.sh")
    capture = tmp_path / "captured-args.txt"
    fake_python = project / ".venv" / "bin" / "python"
    fake_python.parent.mkdir(parents=True)
    fake_python.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$REUSCTL_CAPTURE\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    return project, capture


def test_start_first_node_passes_conservative_defaults_to_node_runner(tmp_path: Path):
    project, capture = _temporary_control_project(tmp_path)
    environment = {**os.environ, "REUSCTL_CAPTURE": str(capture), "HOME": str(tmp_path / "home")}

    result = subprocess.run(
        ["bash", "scripts/reusctl.sh", "start-first-node"],
        cwd=project,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    invocation = capture.read_text(encoding="utf-8")
    assert "scripts/run_node.py --role text-node" in invocation
    assert "--mtls-host 127.0.0.1" in invocation
    assert "--bootstrap-host 127.0.0.1" in invocation


def test_join_node_requires_seed_url_before_running_any_process(tmp_path: Path):
    project, capture = _temporary_control_project(tmp_path)
    environment = {**os.environ, "REUSCTL_CAPTURE": str(capture)}

    result = subprocess.run(
        ["bash", "scripts/reusctl.sh", "join-node"],
        cwd=project,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--seed-url" in result.stderr
    assert not capture.exists()


def test_join_node_passes_seed_and_conservative_defaults_to_node_runner(tmp_path: Path):
    project, capture = _temporary_control_project(tmp_path)
    environment = {**os.environ, "REUSCTL_CAPTURE": str(capture), "HOME": str(tmp_path / "home")}

    result = subprocess.run(
        ["bash", "scripts/reusctl.sh", "join-node", "--seed-url", "http://127.0.0.1:8080"],
        cwd=project,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    invocation = capture.read_text(encoding="utf-8")
    assert "scripts/run_node.py --role cipher-node" in invocation
    assert "--mtls-port 8444" in invocation
    assert "--bootstrap-host 127.0.0.1" in invocation
    assert "--seed-url http://127.0.0.1:8080" in invocation
