"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

مسار للقراءة فقط يعرض: (1) أدوار العقد المتاحة محليًا (خمسة، ثابتة، مُعرَّفة
في node_roles.py — معلومات مرجعية دائمة حتى لو لم يُنشَر أي منها بعد)،
و(2) العقد السحابية الفعلية المنشورة إن كانت السحابة مضبوطة (عبر
/configure_cloud في تلغرام).

قرار تصميم مقصود: **لا يوجد نشر أو حذف عقدة عبر هذا المسار إطلاقًا** —
النشر يبقى حصريًا عبر بوابة الموافقة المزدوجة في تلغرام
(/deploy_node ← /approve)، الموثَّقة صراحة في infrastructure/cloud/
provider_base.py كنموذج أمان: كل إنشاء وتدمير عقدة يمرّ عبر نفس بوابة
موافقة تلغرام — لا شيء يُنشَر أو يُدمَّر بلا /approve صريح من محادثة
مصرَّح بها. إضافة زر "انشر" هنا كان سيتجاوز تلك البوابة عمدًا لمجرد
راحة واجهة المستخدم — تراجع أمني حقيقي، لا تحسين. القراءة فقط تنقل نفس
المعلومة التي يعرضها /list_nodes في تلغرام، دون فتح أي مسار تنفيذ جديد.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from container import get_cloud_manager_holder
from infrastructure.node_roles import NODE_ROLES
from infrastructure.security import verify_api_key

router = APIRouter(prefix="/nodes", tags=["nodes"], dependencies=[Depends(verify_api_key)])


@router.get("")
def list_nodes() -> dict:
    available_roles = [
        {
            "role_id": role.role_id,
            "label": role.label_ar,
            "description": role.description_ar,
            "skill_count": len(role.specs),
        }
        for role in NODE_ROLES.values()
    ]

    holder = get_cloud_manager_holder()
    manager = holder.manager
    cloud_configured = manager is not None and manager.is_configured

    deployed_instances: list[dict] = []
    cloud_error: str | None = None
    if cloud_configured:
        try:
            deployed_instances = [
                {
                    "id": instance.id,
                    "name": instance.name,
                    "provider": instance.provider,
                    "region": instance.region,
                    "size": instance.size,
                    "status": instance.status,
                    "ip_address": instance.ip_address,
                    "monthly_cost_usd": instance.monthly_cost_usd,
                }
                for instance in manager.list_instances()
            ]
        except Exception as exc:  # noqa: BLE001 - أي فشل مزوّد سحابي (شبكة، مصادقة، توقف
            # مؤقت للخدمة) يجب ألا يُسقِط الاستجابة كاملة، بما فيها معلومات
            # أدوار العقد المرجعية المتاحة دائمًا بصرف النظر عن حالة السحابة.
            # اكتُشِف هذا فعليًا عبر محاكاة حية لـ/configure_cloud متبوعة بطلب
            # /nodes حقيقي — لا افتراضًا نظريًا.
            cloud_error = f"{type(exc).__name__}: {exc}"

    return {
        "available_roles": available_roles,
        "cloud_configured": cloud_configured,
        "deployed_instances": deployed_instances,
        "cloud_error": cloud_error,
    }
