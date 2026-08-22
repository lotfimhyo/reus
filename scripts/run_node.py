#!/usr/bin/env python3
"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

scripts/run_node.py — نقطة الدخول الفعلية لتشغيل عقدة واحدة مستقلة كاملة
(أي دور من أدوار `infrastructure/node_roles.py`) كعملية طويلة الأمد — على
جهاز مطوّر محلي أو داخل عقدة سحابية (`node_cloud_init.py` يولّد سكربت
cloud-init يستدعي هذا الملف بالضبط، بنفس المعاملات).

كل المنطق الفعلي في `infrastructure/node_runtime.py` (مُختبَر مباشرة هناك
بمعزل عن سطر الأوامر) — هذا الملف مجرد ربط argparse + إشارات إيقاف نظيفة.

أمثلة استخدام:
    # عقدة أولى مستقلة (بلا انضمام لعنقود):
    python3 scripts/run_node.py --role text-node --data-dir /var/lib/reus/node1

    # عقدة ثانية تنضم لعنقود العقدة الأولى (تنتظر موافقة بشرية عبر تلغرام
    # على الطرف الأول — لا تعليق صامت، الرسالة تُطبع فورًا مع مهلة الانتظار):
    python3 scripts/run_node.py --role cipher-node --data-dir /var/lib/reus/node2 \\
        --mtls-port 8444 --bootstrap-port 8081 \\
        --seed-url http://<عنوان-العقدة-الأولى>:8080
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
    parser = argparse.ArgumentParser(description="تشغيل عقدة Reus مستقلة كاملة.")
    parser.add_argument("--role", required=True, choices=sorted(NODE_ROLES), help="دور العقدة")
    parser.add_argument("--data-dir", required=True, help="مسار تخزين بيانات العقدة (هوية، ذاكرة، قدرات)")
    parser.add_argument(
        "--mtls-host",
        default="127.0.0.1",
        help="عنوان الاستماع لـmTLS؛ loopback افتراضياً. مرر 0.0.0.0 صراحةً فقط مع جدار حماية مناسب.",
    )
    parser.add_argument("--mtls-port", type=int, default=8443)
    parser.add_argument(
        "--bootstrap-host",
        default="127.0.0.1",
        help="عنوان بوابة التمهيد؛ loopback افتراضياً. مرر 0.0.0.0 صراحةً فقط عند الحاجة لعقدة خارجية.",
    )
    parser.add_argument("--bootstrap-port", type=int, default=8080)
    parser.add_argument("--node-label", default=None, help="تسمية مقروءة للعقدة (اختياري)")
    parser.add_argument(
        "--seed-url", default=None, help="عنوان بوابة تمهيد عقدة موجودة للانضمام إليها (اختياري)"
    )
    parser.add_argument(
        "--join-timeout-seconds",
        type=float,
        default=300.0,
        help="أقصى مدة انتظار لموافقة بشرية على طلب الانضمام قبل الفشل",
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
