"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

CloudDeploymentManager لا يمكن بناؤه كـsingleton ثابت وقت تركيب الحاوية —
يعتمد على مزوّد (provider) لا يُختار إلا حين ينفّذ مدير حقيقي /configure_cloud
عبر تلغرام (`CloudTelegramCommands._cmd_configure`). قبل هذه الحلقة، كانت
النتيجة مخزَّنة كحالة خاصة داخل `CloudTelegramCommands` فقط (`self._manager`)
— لا مسار للوحة التحكم (HTTP) لرؤيتها إطلاقًا، رغم أن المدير نفسه (منطق
الحدود والقائمة) لا علاقة له بتلغرام تحديدًا.

`CloudManagerHolder` صندوق مشترك بسيط: `CloudTelegramCommands` يملأه فور
نجاح `/configure_cloud`، ومسار `/nodes` (api/routes/nodes.py) يقرأه فقط —
مصدر حقيقة واحد، لا حالتان منفصلتان قد تتباعدان."""
from __future__ import annotations

from typing import Optional

from infrastructure.cloud.deployment_manager import CloudDeploymentManager


class CloudManagerHolder:
    def __init__(self) -> None:
        self.manager: Optional[CloudDeploymentManager] = None
