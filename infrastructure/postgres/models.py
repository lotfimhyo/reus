# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.postgres.session import Base


class AgentModel(Base):
    """
    صف واحد لكل وكيل. الحقول المركّبة (الصلاحيات، الأهداف، سجل العمليات، المؤشرات)
    تُخزَّن كـ JSON لأنها جزء من نفس الـ Aggregate (Agent) ولا تحتاج استعلامًا مستقلًا الآن.
    """

    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    goals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    memory_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    operation_log: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemoryRecordModel(Base):
    """
    مقطع ذاكرة واحد. عمود embedding من نوع pgvector يسمح بالبحث بالتشابه
    مباشرة داخل قاعدة البيانات (cosine distance) دون الحاجة لأي فهرس خارجي.

    content_encrypted: نص مشفّر (Fernet) وليس نصًا صافيًا — الاسم نفسه موثِّق
    عمدًا لمنع أي قراءة مباشرة خاطئة للعمود من أدوات أو استعلامات لا تمر عبر
    PostgresMemoryRepository (وهي الوحيدة التي تملك EncryptionService لفك التشفير).
    ملاحظة صدق: عمود embedding ليس مشفّرًا (يُحسب من النص الصافي قبل التشفير
    لتمكين البحث الدلالي)، وهذا حد معروف: المتجهات قد تسرّب معلومات إحصائية
    جزئية عن المحتوى حتى مع تشفير النص الخام نفسه.
    """

    __tablename__ = "memory_records"

    memory_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    embedding: Mapped[list] = mapped_column(Vector(384), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)


class AgentTokenModel(Base):
    """
    رمز خاص بوكيل واحد. token_hash فقط يُخزَّن (SHA-256)؛ النص الصافي لا يُحفَظ أبدًا
    في أي مكان بعد لحظة الإصدار — تمامًا كأي بيانات اعتماد حقيقية (كلمات المرور مثلًا).
    """

    __tablename__ = "agent_tokens"

    token_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    scopes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    revoked: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowModel(Base):
    """
    Workflow كاملًا (بكل مهامه) يُخزَّن كمستند JSON واحد، لأن Workflow هو حدود
    الـ Aggregate/Transaction بالكامل في هذا النظام (نمط DDD معروف: Aggregate-as-Document).
    هذا يضمن تحديثًا ذريًا لكل حالة المهام معًا دون تعارضات جزئية.
    """

    __tablename__ = "workflows"

    workflow_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)
