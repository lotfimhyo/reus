"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

يتيح هذا المسار تغيير مجموعة محدودة من الإعدادات (تلغرام، منفِّذ المهام،
مفاتيح مزوّدي النماذج) من لوحة التحكم مباشرة، بدل فتح ملف .env وتحريره
يدويًا — طلب مباشر من المؤسس. محمي بالكامل بمفتاح API الإداري (كبقية
لوحة التحكم)، ومحدود بقائمة سماح صريحة (`ALLOWED_SETTINGS_KEYS`) لا يمكن
تجاوزها — لا يمكن عبر هذا المسار مطلقًا تغيير REUS_API_KEY أو
REUS_USER_API_KEY نفسيهما.

صادق يجب توضيحه للمستخدم دائمًا، لا إخفاؤه: هذا يكتب فعليًا في ملف .env،
لكن `get_settings()` مخبَّأة (`lru_cache`) وتُقرَأ مرة واحدة عند بدء
العملية، وعمّال الخلفية (استقصاء تلغرام تحديدًا) تُبنى وتُشغَّل عند بدء
العملية أيضًا (انظر api/main.py) — فحفظ إعداد جديد هنا **لا يُفعِّله
فورًا**، يحتاج إعادة تشغيل الخادم (زر Run.bat مرة أخرى، أو إعادة تشغيل
الحاوية). كل استجابة من `POST /settings` تُضمِّن `restart_required: true`
صراحة لهذا السبب.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from infrastructure.env_file_writer import (
    ALLOWED_SETTINGS_KEYS,
    InvalidSettingKey,
    InvalidSettingValue,
    read_env_file,
    update_env_file,
)
from infrastructure.security import verify_api_key

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(verify_api_key)])


class SettingsUpdateRequest(BaseModel):
    values: dict[str, str]


@router.get("")
def get_settings_values() -> dict:
    """يُعيد القيم الحالية المسموح بتعديلها — الحقول الحساسة (مفاتيح
    النماذج، رمز تلغرام) تُعاد مقنَّعة (موجودة/فارغة) فقط، لا بنصها الفعلي."""
    return {
        "values": read_env_file(),
        "editable_keys": sorted(ALLOWED_SETTINGS_KEYS),
    }


@router.post("")
def update_settings_values(body: SettingsUpdateRequest) -> dict:
    try:
        update_env_file(body.values)
    except (InvalidSettingKey, InvalidSettingValue) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {
        "status": "saved",
        "restart_required": True,
        "message": "تم الحفظ في .env. أعد تشغيل الخادم (Run.bat مرة أخرى، أو إعادة تشغيل الحاوية) لتفعيل التغييرات فعليًا.",
    }
