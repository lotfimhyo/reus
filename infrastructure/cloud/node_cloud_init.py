"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

node_cloud_init — يبني سكربت bash حقيقي (سياسة user_data/cloud-init، مدعوم
فعليًا من DigitalOcean/معظم مزوّدي السحابة) يُشغَّل تلقائيًا عند أول إقلاع
لخادم سحابي جديد. يثبّت المتطلبات، يجلب كود مصدر Reus، ثم يُشغِّل
`scripts/run_node.py` كخدمة نظام (`systemd`) تنضم تلقائيًا لعنقود موجود
عبر `--seed-url`.

**فجوة حقيقية واجب إشهارها صراحةً، لا إخفاؤها:** هذا الملف **لا** يحل مشكلة
"كيف يصل كود مصدر Reus فعليًا لخادم سحابي فارغ لأول مرة" — لا توجد في هذه
الجلسة بنية نشر (CI/CD) تُصدِر أرشيف كود منشور يمكن تنزيله. `source_fetch_cmd`
معامل **إلزامي** (لا قيمة افتراضية صامتة) يجب على المُشغِّل توفيره صراحةً —
مثال واقعي: `git clone https://github.com/<user>/reus.git /opt/reus` لمستودع
خاص بمفتاح نشر (deploy key) مُضمَّن مسبقًا في صورة الخادم. طرح الأمر كمعامل
صريح إلزامي بدل افتراض قيمة تبدو معقولة يمنع نشر خادم "ناجح" لا يحتوي فعليًا
على أي كود يعمل.
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
    """يرفع `ValueError` فورًا لدور غير معروف أو `source_fetch_cmd` فارغ —
    لا سكربت جزئي يبدو صالحًا لكنه سيفشل فعليًا عند التنفيذ على الخادم."""
    get_node_role(role_id)  # يرفع ValueError مبكرًا لدور غير معروف، قبل توليد أي سكربت
    if not source_fetch_cmd.strip():
        raise ValueError(
            "source_fetch_cmd إلزامي — لا توجد آلية توزيع كود افتراضية في هذا المشروع بعد؛ "
            "زوِّد أمرًا فعليًا (مثل git clone من مستودعك الخاص)."
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

    # وحدة systemd حقيقية — تُعيد تشغيل العقدة تلقائيًا إن انهارت، وتبدأ فعليًا
    # بعد إعادة إقلاع الخادم (enable)، لا مجرد عملية تُشغَّل مرة واحدة وتُفقَد
    # صامتة عند أول تعطّل أو إعادة إقلاع.
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
        "# 1) تثبيت المتطلبات الأساسية",
        "apt-get update -y",
        "apt-get install -y python3 python3-pip git",
        "",
        "# 2) جلب كود المصدر — أمر مُزوَّد صراحةً من المُشغِّل، لا افتراض ضمني",
        f"mkdir -p {shlex.quote(repo_dir)}",
        source_fetch_cmd,
        "",
        f"pip3 install --break-system-packages -r {shlex.quote(repo_dir)}/requirements.txt || true",
        "",
        "# 3) تثبيت وتفعيل وحدة systemd لتشغيل العقدة تلقائيًا",
        f"mkdir -p {shlex.quote(node_data_dir)}",
        "cat > /etc/systemd/system/reus-node.service << 'REUS_UNIT_EOF'",
        systemd_unit.rstrip("\n"),
        "REUS_UNIT_EOF",
        "systemctl daemon-reload",
        "systemctl enable --now reus-node.service",
    ]
    return "\n".join(lines) + "\n"
