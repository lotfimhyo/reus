# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, Request, status

from config import Settings, get_settings
from infrastructure.rate_limiter import client_key_from_request

logger = logging.getLogger("reus_veritas.security")


def _enforce_admin_rate_limit(request: Request) -> None:
    """يُطبَّق قبل أي مقارنة مفتاح في هذا الملف — عمدًا، لا بعدها. المفتاح
    الإداري (REUS_API_KEY) أقوى صلاحية في النظام؛ لو طُبِّق تحديد المعدل
    بعد رفض 401، لَما احتُسِبت محاولات تخمين المفتاح الفاشلة ضمن الحد
    أصلًا، فيبقى تخمينه مفتوحًا بلا حدود على نفس السطح الشبكي العام الذي
    يخدم /chat. نفس الترتيب المطبَّق فعليًا على /chat (انظر api/routes/
    chat.py) — هنا مركزيًا لكل نقاط النهاية الإدارية دفعة واحدة، لا مبعثرًا
    عبر كل ملف مسارات على حدة، حتى لا يُنسى سهوًا في ملف جديد مستقبلًا."""
    from container import get_admin_rate_limiter

    limiter = get_admin_rate_limiter()
    allowed, retry_after = limiter.allow(client_key_from_request(request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="تجاوزت الحد المسموح من الطلبات. حاول لاحقًا.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def verify_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> str:
    """
    يتحقق من مفتاح API عبر مقارنة آمنة زمنيًا (hmac.compare_digest)
    لمنع Timing Attacks. يرفض التنفيذ غير الآمن (طلب بلا مفتاح أو مفتاح خاطئ).
    """
    _enforce_admin_rate_limit(request)
    settings: Settings = get_settings()
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        logger.warning("unauthorized_access_attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="مفتاح API مفقود أو غير صحيح",
        )
    return x_api_key


def verify_user_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """
    اعتمادية منفصلة تمامًا عن verify_api_key — تتحقق حصرًا من user_api_key
    (مفتاح واجهة الويب العامة للمستخدمين). **لا** تقبل api_key الإداري
    كبديل — هذا الفصل مقصود: من يملك المفتاح الإداري الكامل الصلاحيات لا
    يحصل تلقائيًا على وصول لمسار المستخدمين، والعكس. كل مسار يتحقق من بيانات
    اعتماده الخاصة فقط. (تحديد المعدل لهذا المسار يُطبَّق في api/routes/
    chat.py على مستوى الموجِّه مباشرة، لا هنا — راجع enforce_chat_rate_limit.)
    """
    settings: Settings = get_settings()
    pairing_authorized = False
    if x_api_key:
        from container import get_control_plane_pairing_store

        pairing_authorized = get_control_plane_pairing_store().verify_user_key(x_api_key)
    if not x_api_key or (not settings.user_api_key or not hmac.compare_digest(x_api_key, settings.user_api_key)) and not pairing_authorized:
        logger.warning("unauthorized_user_access_attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="مفتاح API الخاص بالمستخدمين مفقود أو غير صحيح",
        )
    return x_api_key


def verify_agent_access(agent_id: str, request: Request, x_api_key: str | None = Header(default=None)) -> str:
    """
    يسمح بالوصول إما عبر مفتاح API الرئيسي (صلاحية كاملة، للاستخدام الإداري)،
    أو عبر رمز خاص بوكيل واحد (Self-Service) بشرط أن يطابق agent_id في مسار
    الطلب بالضبط — رمز الوكيل A لا يمنحه أي صلاحية على مسارات الوكيل B إطلاقًا.
    يتحقق من الهوية فقط، دون أي فحص نطاق (Scope)؛ يُستخدم للمسارات التي لا
    تحتاج صلاحية محدَّدة. للمسارات التي تحتاج صلاحية بعينها استخدم require_agent_scope.
    """
    _enforce_admin_rate_limit(request)
    settings: Settings = get_settings()
    if x_api_key and hmac.compare_digest(x_api_key, settings.api_key):
        return agent_id

    if x_api_key:
        from container import get_agent_token_service  # استيراد مؤجَّل لتفادي استيراد دائري مع container.py

        token = get_agent_token_service().authenticate(x_api_key)
        if token is not None and hmac.compare_digest(token.agent_id, agent_id):
            return agent_id

    logger.warning("unauthorized_agent_access_attempt", extra={"agent_id": agent_id})
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="مطلوب مفتاح API رئيسي صالح أو رمز خاص بهذا الوكيل بالتحديد",
    )


def require_agent_scope(required_permission: str):
    """
    مصنع اعتماديات (Dependency Factory): يُعيد اعتمادية FastAPI تتحقق من الهوية
    (كـ verify_agent_access تمامًا) **بالإضافة** إلى أن الرمز المستخدَم يشمل
    نطاقه الفعلي (Effective Scopes — تقاطع نطاق الرمز مع صلاحيات الوكيل الحالية)
    الصلاحية المطلوبة تحديدًا لهذا المسار. مفتاح API الرئيسي يتجاوز فحص النطاق
    (وصول إداري كامل)؛ فحص صلاحيات الوكيل نفسه (domain/entities.py) يبقى مستقلًا
    ويُطبَّق لاحقًا في MemoryService بصرف النظر عن نتيجة هذه الاعتمادية.
    """

    def dependency(agent_id: str, request: Request, x_api_key: str | None = Header(default=None)) -> str:
        _enforce_admin_rate_limit(request)
        settings: Settings = get_settings()
        if x_api_key and hmac.compare_digest(x_api_key, settings.api_key):
            return agent_id

        if x_api_key:
            from container import get_agent_token_service

            token_service = get_agent_token_service()
            token = token_service.authenticate(x_api_key)
            if token is not None and hmac.compare_digest(token.agent_id, agent_id):
                effective_scopes = token_service.get_effective_scopes(token)
                if required_permission in effective_scopes:
                    return agent_id
                logger.warning(
                    "token_scope_denied",
                    extra={
                        "agent_id": agent_id,
                        "payload": {"required_permission": required_permission, "token_id": token.token_id},
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"نطاق هذا الرمز لا يشمل الصلاحية المطلوبة: '{required_permission}'",
                )

        logger.warning("unauthorized_agent_access_attempt", extra={"agent_id": agent_id})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="مطلوب مفتاح API رئيسي صالح أو رمز خاص بهذا الوكيل بالتحديد",
        )

    return dependency
