# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
تشغيل: python3 -m infrastructure.postgres.init_db
ينشئ كل الجداول (agents, memory_records, workflows) إن لم تكن موجودة.

⚠️ ملاحظة مهمة: هذا السكربت مفيد فقط للتجريب السريع المحلي (إنشاء الجداول دفعة
واحدة من الحالة الحالية للنماذج). **الطريقة المعتمدة لإدارة تطور المخطط فعليًا
هي Alembic** (راجع مجلد alembic/) لأنها الوحيدة التي تدعم الترقية/التراجع الآمن
والتاريخ الكامل للتغييرات. لا تستخدم هذا السكربت في بيئة إنتاج تُدار عبر Alembic،
لأن create_all لا يُسجَّل في جدول alembic_version وسيُحدث تعارضًا لاحقًا.
"""
from __future__ import annotations

# يجب استيراد كل النماذج قبل create_all حتى تُسجَّل في Base.metadata
from infrastructure.postgres.models import AgentModel, MemoryRecordModel, WorkflowModel  # noqa: F401
from infrastructure.postgres.session import Base, get_engine


def init_db() -> None:
    Base.metadata.create_all(get_engine())
    print("تم إنشاء/التحقق من كل الجداول بنجاح. (تذكير: استخدم Alembic في الإنتاج)")


if __name__ == "__main__":
    init_db()
