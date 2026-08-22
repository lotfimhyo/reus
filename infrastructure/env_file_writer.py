"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

قارئ/كاتب آمن ومحدود بقائمة سماح لملف .env — يتيح تغيير إعدادات مختارة
(تلغرام، منفِّذ المهام، مفاتيح النماذج) من لوحة التحكم مباشرة بدل فتح
الملف وتحريره يدويًا، مع الحفاظ على أمان الملف:

- قائمة سماح صريحة (`ALLOWED_SETTINGS_KEYS`): لا يمكن كتابة أي متغيّر خارج
  هذه القائمة عبر هذا المسار مهما كان — تحديدًا REUS_API_KEY وREUS_USER_API_KEY
  (المفتاحان الإداريان) مُستبعَدان عمدًا؛ تغييرهما عبر الويب نفسه، بلا
  تحقق يدوي، يفتح ثغرة تصعيد صلاحيات واضحة.
- رفض أي قيمة تحتوي سطرًا جديدًا: بلا هذا الفحص، يمكن لقيمة مثل
  "x\\nREUS_API_KEY=attacker_key" أن "تُهرِّب" متغيّرًا كاملًا خارج قائمة
  السماح عبر إدراج سطر جديد في الملف نفسه.
- يحافظ على كل الأسطر والتعليقات غير المذكورة في التحديث كما هي تمامًا —
  لا إعادة كتابة كاملة للملف تفقد أي تخصيص يدوي سابق.
"""
from __future__ import annotations

import re

ALLOWED_SETTINGS_KEYS = frozenset(
    {
        "REUS_TELEGRAM_ENABLED",
        "REUS_TELEGRAM_BOT_TOKEN",
        "REUS_TELEGRAM_ALLOWED_CHAT_IDS",
        "REUS_TASK_EXECUTOR",
        "REUS_ANTHROPIC_API_KEY",
        "REUS_OPENAI_API_KEY",
        "REUS_GOOGLE_API_KEY",
        "REUS_OLLAMA_ENABLED",
        "REUS_OLLAMA_BASE_URL",
        "REUS_OLLAMA_MODEL",
    }
)

# قيم لا تُعاد أبدًا للواجهة بنصها الصريح — تُقنَّع بدلًا من ذلك (موجودة/فارغة فقط)
_SECRET_KEYS = frozenset(
    {"REUS_TELEGRAM_BOT_TOKEN", "REUS_ANTHROPIC_API_KEY", "REUS_OPENAI_API_KEY", "REUS_GOOGLE_API_KEY"}
)


class InvalidSettingKey(Exception):
    pass


class InvalidSettingValue(Exception):
    pass


def read_env_file(env_path: str = ".env") -> dict[str, str]:
    """يُعيد فقط المفاتيح المسموح بها من الملف، بقيمها الحقيقية للحقول غير
    الحساسة، ومقنَّعة (موجودة/فارغة) للحقول الحساسة — لا تُعاد أي أسرار
    فعلية لواجهة المتصفح إطلاقًا."""
    result: dict[str, str] = {}
    try:
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return result

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key in ALLOWED_SETTINGS_KEYS:
            if key in _SECRET_KEYS:
                result[key] = "***configured***" if value.strip() else ""
            else:
                result[key] = value.strip()
    return result


def update_env_file(updates: dict[str, str], env_path: str = ".env") -> None:
    """يُحدِّث فقط المفاتيح الموجودة في `updates` (يجب أن تكون كلها ضمن
    ALLOWED_SETTINGS_KEYS)، يستبدل قيمتها إن كانت موجودة في الملف، يُضيفها
    في النهاية إن لم تكن موجودة، ويحافظ على كل سطر آخر (بما فيه REUS_API_KEY/
    REUS_USER_API_KEY الحساسان) بلا أي تغيير."""
    for key, value in updates.items():
        if key not in ALLOWED_SETTINGS_KEYS:
            raise InvalidSettingKey(f"'{key}' ليس ضمن الإعدادات القابلة للتعديل عبر هذا المسار")
        if "\n" in value or "\r" in value:
            raise InvalidSettingValue(f"القيمة الخاصة بـ '{key}' تحتوي سطرًا جديدًا — مرفوضة")

    try:
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []

    remaining = dict(updates)
    new_lines = []
    for line in lines:
        stripped = line.strip()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=", stripped) if stripped and not stripped.startswith("#") else None
        if match and match.group(1) in remaining:
            key = match.group(1)
            new_lines.append(f"{key}={remaining.pop(key)}\n")
        else:
            new_lines.append(line)

    for key, value in remaining.items():
        new_lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
