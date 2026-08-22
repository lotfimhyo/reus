#!/usr/bin/env python3
"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

scripts/run_node.py is the operational entry point for one complete standalone
node (any role in `infrastructure/node_roles.py`) running as a long-lived
process, either on a local developer machine or in a cloud node. The cloud-init
generator invokes this exact file with the same arguments.

All operating logic lives in `infrastructure/node_runtime.py`, where it is
tested directly. This file only connects argparse handling to clean shutdown
signals.

Usage examples:
    # First standalone node, without joining an existing cluster:
    python3 scripts/run_node.py --role text-node --data-dir /var/lib/reus/node1

    # A second node joins the first node's cluster. The first node requires a
    # human Telegram approval; the request is surfaced immediately and times out.
    python3 scripts/run_node.py --role cipher-node --data-dir /var/lib/reus/node2 \
        --mtls-port 8444 --bootstrap-port 8081 \
        --seed-url http://<first-node-address>:8080
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.node_roles import NODE_ROLES  # noqa: E402
from infrastructure.node_runtime import compose_node, join_cluster, start_node, stop_node  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("reus.run_node")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one complete standalone Reus node.")
    parser.add_argument("--role", required=True, choices=sorted(NODE_ROLES), help="Node role")
    parser.add_argument("--data-dir", required=True, help="Node data directory for identity, memory, and capabilities")
    parser.add_argument(
        "--mtls-host",
        default="127.0.0.1",
        help="mTLS bind address; loopback by default. Pass 0.0.0.0 explicitly only with an appropriate firewall.",
    )
    parser.add_argument("--mtls-port", type=int, default=8443)
    parser.add_argument(
        "--bootstrap-host",
        default="127.0.0.1",
        help="Bootstrap gateway address; loopback by default. Pass 0.0.0.0 explicitly only when an external node requires it.",
    )
    parser.add_argument("--bootstrap-port", type=int, default=8080)
    parser.add_argument("--node-label", default=None, help="Human-readable node label (optional)")
    parser.add_argument(
        "--seed-url", default=None, help="Existing node bootstrap gateway to join (optional)"
    )
    parser.add_argument(
        "--join-timeout-seconds",
        type=float,
        default=300.0,
        help="Maximum wait for a human approval of the join request before failing",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    composed = compose_node(
        role_id=args.role,
        data_dir=args.data_dir,
        mtls_host=args.mtls_host,
        mtls_port=args.mtls_port,
        bootstrap_host=args.bootstrap_host,
        bootstrap_port=args.bootstrap_port,
        node_label=args.node_label,
    )
    logger.info("node_composed", extra={"role": args.role, "skills_bound": composed.skills_bound})

    start_node(composed)

    if args.seed_url:
        logger.info("joining_cluster", extra={"seed_url": args.seed_url})
        try:
            result = join_cluster(composed, args.seed_url, max_wait_seconds=args.join_timeout_seconds)
            logger.info(
                "joined_cluster",
                extra={
                    "peer_component_id": result.peer_component_id,
                    "capabilities_ingested": result.capabilities_ingested,
                    "facts_ingested": result.facts_ingested,
                },
            )
        except Exception:
            logger.exception("join_cluster_failed")
            stop_node(composed)
            return 1

    stop_requested = {"flag": False}

    def _handle_signal(signum, frame):
        stop_requested["flag"] = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("node_running", extra={"node_id": composed.component_identity.component_id})
    try:
        while not stop_requested["flag"]:
            time.sleep(0.5)
    finally:
        stop_node(composed)
        logger.info("node_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
