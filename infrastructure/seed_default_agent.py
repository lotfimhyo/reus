"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

يبذُر وكيلًا افتراضيًا واحدًا جاهزًا للعمل عند أول إقلاع — طلب مباشر من
المؤسس: نظام جديد تمامًا (بلا أي وكيل مسجَّل بعد) يتطلب فتح لوحة التحكم
وتسجيل وكيل يدويًا قبل أن يصبح ربط تلغرام أو أي ميزة تعتمد على وكيل قابلة
للاستخدام إطلاقًا. هذا يزيل تلك الخطوة اليدوية الأولى فقط — لا يزال بالإمكان
تسجيل وكلاء إضافيين يدويًا كالمعتاد.

يعمل مرة واحدة فقط عبر عمر قاعدة البيانات (لا يُنشئ نسخة مكرَّرة عند كل
إعادة تشغيل): يتحقق أولًا أن لا وكلاء مسجَّلين إطلاقًا قبل الإنشاء. إن كان
هناك وكيل واحد على الأقل (سواء المبذور نفسه من تشغيل سابق، أو أي وكيل
سجَّله المستخدم يدويًا)، لا يُنشئ شيئًا جديدًا — لا يفترض أن غياب الوكيل
المبذور بالتحديد يعني إعادة البذر، لأن المستخدم قد يكون حذفه عمدًا.
"""
from __future__ import annotations

import logging

from application.agent_service import AgentService, RegisterAgentCommand
from domain.entities import AgentState

logger = logging.getLogger("reus_veritas.seed_default_agent")

DEFAULT_AGENT_PERMISSIONS = frozenset(
    {"read:memory", "write:memory", "invoke:model", "invoke:tool", "spawn:subagent"}
)


def seed_default_agent(agent_service: AgentService, *, name: str = "default-agent") -> str | None:
    """يُعيد agent_id للوكيل المبذور إن أُنشئ فعليًا هذه المرة، أو None إن
    كان هناك وكيل واحد على الأقل مسجَّلًا مسبقًا (لا بذر مكرَّر)."""
    if agent_service.list_agents():
        return None

    agent = agent_service.register_agent(
        RegisterAgentCommand(name=name, permissions=set(DEFAULT_AGENT_PERMISSIONS), goals=[])
    )
    # الانتقال إلى IDLE اختياري دلاليًا (لا شيء يتطلبه فعليًا لاستخدام الوكيل
    # حاليًا)، لكنه يعكس بصدق أن هذا الوكيل "جاهز للعمل" لا مجرد مُنشَأ للتو.
    agent_service.change_state(agent.agent_id, AgentState.IDLE)

    logger.info(
        "default_agent_seeded",
        extra={"event_name": "default_agent_seeded", "payload": {"agent_id": agent.agent_id, "name": name}},
    )
    return agent.agent_id
