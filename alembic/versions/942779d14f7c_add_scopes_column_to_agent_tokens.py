# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""add scopes column to agent_tokens

Revision ID: 942779d14f7c
Revises: fc771ea98672
Create Date: 2026-07-11 19:27:13.710386

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '942779d14f7c'
down_revision: Union[str, Sequence[str], None] = 'fc771ea98672'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # الخطوة 1: إضافة العمود قابلًا لـ NULL أولًا، حتى نستطيع تعبئته لكل صف موجود مسبقًا
    op.add_column("agent_tokens", sa.Column("scopes", sa.JSON(), nullable=True))

    # الخطوة 2: ترحيل بيانات حقيقي — كل رمز مُصدَر قبل هذه الحلقة كان يرث ضمنيًا
    # كل صلاحيات وكيله وقتها (السلوك القديم قبل مفهوم Scopes)، لذا نُعبّئ scopes
    # بصلاحيات الوكيل الحالية بدل تركها فارغة (فراغ يعني "بلا صلاحيات إطلاقًا"
    # حسب المعنى الجديد، وهذا كان سيُسقط كل الرموز القديمة فجأة بلا صلاحيات — خطأ جسيم).
    op.execute(
        """
        UPDATE agent_tokens
        SET scopes = agents.permissions
        FROM agents
        WHERE agent_tokens.agent_id = agents.agent_id
        """
    )
    # رموز قد يكون وكيلها حُذف لاحقًا (بلا تطابق في JOIN أعلاه) تُعبَّأ بمصفوفة فارغة صراحة
    op.execute("UPDATE agent_tokens SET scopes = '[]'::json WHERE scopes IS NULL")

    # الخطوة 3: الآن وقد اكتملت التعبئة، نفرض NOT NULL كما في التصميم النهائي للعمود
    op.alter_column("agent_tokens", "scopes", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("agent_tokens", "scopes")
