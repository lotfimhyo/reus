"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

node_cloud_init builds a real Bash user-data/cloud-init script for first boot
of a new cloud server. It installs prerequisites, fetches Reus source code,
and runs `scripts/run_node.py` as a systemd service that can join an existing
cluster through `--seed-url`.

**Explicit boundary:** this module does not solve initial source distribution
to an empty cloud server. It has no CI/CD mechanism that publishes a downloadable
source archive. `source_fetch_cmd` is required with no silent default, so an
operator must supply an actual source acquisition command. Making the command
explicit prevents a superficially successful deployment that contains no
working Reus code.
"""
from __future__ import annotations

import shlex
from typing import Optional

from infrastructure.node_roles import get_node_role


def build_node_cloud_init_script(
    role_id: str,
    source_fetch_cmd: str,
    seed_bootstrap_url: Optional[str] = None,
    mtls_port: int = 8443,
    bootstrap_port: int = 8080,
    repo_dir: str = "/opt/reus",
    node_data_dir: str = "/var/lib/reus/node",
) -> str:
    """Raise ValueError immediately for an unknown role or empty
    source_fetch_cmd; never return a partial script that will fail on the server."""
    get_node_role(role_id)  # Reject an unknown role before generating any script.
    if not source_fetch_cmd.strip():
        raise ValueError(
            "source_fetch_cmd is required because this project has no default source-distribution mechanism; "
            "provide an actual command such as git clone from your repository."
        )

    run_node_cmd = [
        "python3",
        f"{repo_dir}/scripts/run_node.py",
        "--role",
        role_id,
        "--data-dir",
        node_data_dir,
        "--mtls-port",
        str(mtls_port),
        "--bootstrap-port",
        str(bootstrap_port),
    ]
    if seed_bootstrap_url:
        run_node_cmd += ["--seed-url", seed_bootstrap_url]
    run_node_cmd_str = " ".join(shlex.quote(part) for part in run_node_cmd)

    # A real systemd unit restarts a failed node and starts it after server
    # reboot, rather than launching a one-off process that silently disappears.
    systemd_unit = f"""[Unit]
Description=Reus node ({role_id})
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={run_node_cmd_str}
Restart=always
RestartSec=5
WorkingDirectory={repo_dir}

[Install]
WantedBy=multi-user.target
"""

    lines = [
        "#!/bin/bash",
        "set -euxo pipefail",
        "",
        "# 1) Install prerequisites",
        "apt-get update -y",
        "apt-get install -y python3 python3-pip git",
        "",
        "# 2) Fetch source code with the operator-supplied command; no implicit default",
        f"mkdir -p {shlex.quote(repo_dir)}",
        source_fetch_cmd,
        "",
        f"pip3 install --break-system-packages -r {shlex.quote(repo_dir)}/requirements.txt || true",
        "",
        "# 3) Install and enable the systemd unit for automatic node startup",
        f"mkdir -p {shlex.quote(node_data_dir)}",
        "cat > /etc/systemd/system/reus-node.service << 'REUS_UNIT_EOF'",
        systemd_unit.rstrip("\n"),
        "REUS_UNIT_EOF",
        "systemctl daemon-reload",
        "systemctl enable --now reus-node.service",
    ]
    return "\n".join(lines) + "\n"
