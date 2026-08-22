"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

node_roles: تعريف العقد الخمس الجاهزة ("5 عقد جاهزة ومهارات أولية جاهزة")
المطلوبة صراحةً. كل عقدة = دور (role) بمجموعة قدرات أولية حقيقية تُبنى عبر
نفس خط أنابيب AgentCapabilityBinder المستخدم لكل قدرة أخرى في النظام (توليد
من قالب معروف → فحص ثابت → sandbox معزول → نشر) — لا معاملة خاصة، ولا قدرة
"مُدرَجة يدويًا" تتجاوز أي بوابة أمان.

كل عقدة قابلة للتشغيل كعملية مستقلة تمامًا (`scripts/run_node.py
--role=<role_id>`)، وتنضم لنفس الكيان العنقودي الموحّد عبر آلية التمهيد
mTLS + موافقة تلغرام المبنية سابقًا (`infrastructure/cluster_network/
bootstrap_*`) إن زُوِّدت بعنوان عقدة تمهيد قائمة (`REUS_CLUSTER_SEED_URL`).
استقلالية التنفيذ (كل عقدة تُنفّذ مهامها محليًا دون انتظار عقدة أخرى) +
الانتماء لكيان واحد (نفس TrustStore الموزَّع + تبادل قدرات فعلي عبر
/cluster/snapshot) هو بالضبط ما طُلِب: "تنفيذ مستقل، لكنها كيان واحد".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from infrastructure.agent_factory.manifest import AgentSpec, TestCase
from infrastructure.seed_capabilities import DEFAULT_SPECS as _TEXT_BASE_SPECS


@dataclass(frozen=True)
class NodeRole:
    role_id: str
    label_ar: str
    description_ar: str
    specs: list[AgentSpec] = field(default_factory=list)


_TEXT_NODE_EXTRA = [
    AgentSpec(
        name="title_caser",
        capability="text.title_case",
        description="يحوّل أول حرف من كل كلمة إلى حرف كبير",
        template="title_case",
        test_cases=[TestCase(input="hello world", expected_output="Hello World")],
    ),
    AgentSpec(
        name="whitespace_remover",
        capability="text.remove_whitespace",
        description="يزيل كل الفراغات من النص",
        template="remove_whitespace",
        test_cases=[TestCase(input="a b  c", expected_output="abc")],
    ),
    AgentSpec(
        name="vowel_counter",
        capability="text.vowel_count",
        description="يعدّ عدد أحرف العلة الإنجليزية في نص",
        template="vowel_count",
        test_cases=[TestCase(input="Hello World", expected_output=3)],
    ),
]

_CIPHER_NODE_SPECS = [
    AgentSpec(
        name="caesar_encoder",
        capability="cipher.caesar_encode",
        description="يشفّر نصًا بتعمية قيصر (إزاحة 3)",
        template="caesar_encode",
        test_cases=[TestCase(input="abc", expected_output="def")],
    ),
    AgentSpec(
        name="caesar_decoder",
        capability="cipher.caesar_decode",
        description="يفكّ تعمية قيصر (إزاحة 3)",
        template="caesar_decode",
        test_cases=[TestCase(input="def", expected_output="abc")],
    ),
    AgentSpec(
        name="rle_encoder",
        capability="cipher.run_length_encode",
        description="ترميز طول التكرار (Run-Length Encoding)",
        template="run_length_encode",
        test_cases=[TestCase(input="aaabbc", expected_output="a3b2c1")],
    ),
    AgentSpec(
        name="rle_decoder",
        capability="cipher.run_length_decode",
        description="فكّ ترميز طول التكرار",
        template="run_length_decode",
        test_cases=[TestCase(input="a3b2c1", expected_output="aaabbc")],
    ),
    AgentSpec(
        name="checksum_calculator",
        capability="cipher.checksum_sum",
        description="مجموع تحقّق بسيط (مجموع قيم الأحرف modulo 256)",
        template="checksum_sum",
        test_cases=[TestCase(input="abc", expected_output=38)],
    ),
]

_NUMERIC_NODE_SPECS = [
    AgentSpec(
        name="digit_summer",
        capability="numeric.digit_sum",
        description="يجمع كل الأرقام الظاهرة داخل نص",
        template="digit_sum",
        test_cases=[TestCase(input="a1b2c3", expected_output=6)],
    ),
    AgentSpec(
        name="numeric_checker",
        capability="numeric.is_numeric",
        description="يتحقق هل النص يمثّل رقمًا صحيحًا أو عشريًا",
        template="is_numeric",
        test_cases=[TestCase(input="123", expected_output=True)],
    ),
    AgentSpec(
        name="binary_converter",
        capability="numeric.decimal_to_binary",
        description="يحوّل عددًا عشريًا إلى ثنائي (بلا استخدام bin())",
        template="decimal_to_binary",
        test_cases=[TestCase(input=10, expected_output="1010")],
    ),
    AgentSpec(
        name="hex_converter",
        capability="numeric.decimal_to_hex",
        description="يحوّل عددًا عشريًا إلى ست عشري (بلا استخدام hex())",
        template="decimal_to_hex",
        test_cases=[TestCase(input=255, expected_output="ff")],
    ),
    AgentSpec(
        name="prime_checker",
        capability="numeric.is_prime",
        description="يتحقق هل العدد أوّلي",
        template="is_prime",
        test_cases=[TestCase(input=17, expected_output=True)],
    ),
    AgentSpec(
        name="factorial_calculator",
        capability="numeric.factorial",
        description="يحسب مضروب عدد صحيح غير سالب",
        template="factorial",
        test_cases=[TestCase(input=5, expected_output=120)],
    ),
]

_FORMAT_NODE_SPECS = [
    AgentSpec(
        name="slugifier",
        capability="format.slugify",
        description="يحوّل نصًا إلى slug صالح لعنوان URL",
        template="slugify",
        test_cases=[TestCase(input="Hello World!", expected_output="hello-world")],
    ),
    AgentSpec(
        name="snake_to_camel_converter",
        capability="format.snake_to_camel",
        description="يحوّل snake_case إلى camelCase",
        template="snake_to_camel",
        test_cases=[TestCase(input="hello_world", expected_output="helloWorld")],
    ),
    AgentSpec(
        name="camel_to_snake_converter",
        capability="format.camel_to_snake",
        description="يحوّل camelCase إلى snake_case",
        template="camel_to_snake",
        test_cases=[TestCase(input="helloWorld", expected_output="hello_world")],
    ),
    AgentSpec(
        name="html_tag_stripper",
        capability="format.strip_html_tags",
        description="يزيل وسوم HTML بشكل بسيط (بلا دعم تعليقات/CDATA متداخلة)",
        template="strip_html_tags",
        test_cases=[TestCase(input="<b>hi</b>", expected_output="hi")],
    ),
    AgentSpec(
        name="ellipsis_truncator",
        capability="format.truncate_ellipsis",
        description="يقصّ نصًا طويلًا لعشرين حرفًا ويضيف نقاط حذف",
        template="truncate_ellipsis",
        test_cases=[TestCase(input="short", expected_output="short")],
    ),
]

_VALIDATION_NODE_SPECS = [
    AgentSpec(
        name="luhn_checker",
        capability="validation.luhn_check",
        description="يتحقق من رقم عبر خوارزمية Luhn (صيغة بطاقات/معرّفات)",
        template="luhn_check",
        test_cases=[TestCase(input="4532015112830366", expected_output=True)],
    ),
    AgentSpec(
        name="bracket_balance_checker",
        capability="validation.is_balanced_brackets",
        description="يتحقق من توازن الأقواس بأنواعها في نص",
        template="is_balanced_brackets",
        test_cases=[TestCase(input="([{}])", expected_output=True)],
    ),
    AgentSpec(
        name="duplicate_word_checker",
        capability="validation.has_duplicate_words",
        description="يتحقق هل يحتوي النص على كلمة مكرّرة",
        template="has_duplicate_words",
        test_cases=[TestCase(input="a b a", expected_output=True)],
    ),
    AgentSpec(
        name="unique_word_counter",
        capability="validation.count_unique_words",
        description="يعدّ عدد الكلمات الفريدة في نص",
        template="count_unique_words",
        test_cases=[TestCase(input="a a b c", expected_output=3)],
    ),
    AgentSpec(
        name="sensitive_masker",
        capability="validation.mask_sensitive_middle",
        description="يخفي منتصف نص حسّاس (كأرقام الحسابات) مبقيًا أول وآخر حرفين",
        template="mask_sensitive_middle",
        test_cases=[TestCase(input="1234567890", expected_output="12******90")],
    ),
    AgentSpec(
        name="username_validator",
        capability="validation.is_valid_username",
        description="يتحقق من صلاحية اسم مستخدم وفق قواعد بسيطة",
        template="is_valid_username",
        test_cases=[TestCase(input="user_123", expected_output=True)],
    ),
]


NODE_ROLES: dict[str, NodeRole] = {
    "text-node": NodeRole(
        role_id="text-node",
        label_ar="عقدة النصوص",
        description_ar="معالجة نصية أساسية: تحويل حالة الأحرف، عكس، عدّ، ترتيب، تنظيف الفراغات.",
        specs=[*_TEXT_BASE_SPECS, *_TEXT_NODE_EXTRA],
    ),
    "cipher-node": NodeRole(
        role_id="cipher-node",
        label_ar="عقدة الترميز",
        description_ar="تعمية وترميز رمزي بسيط: قيصر، طول التكرار، مجموع تحقّق.",
        specs=_CIPHER_NODE_SPECS,
    ),
    "numeric-node": NodeRole(
        role_id="numeric-node",
        label_ar="عقدة الحساب",
        description_ar="عمليات رقمية: تحويل قواعد عدّ، فحص الأوليّة، المضروب، جمع الأرقام.",
        specs=_NUMERIC_NODE_SPECS,
    ),
    "format-node": NodeRole(
        role_id="format-node",
        label_ar="عقدة التنسيق",
        description_ar="تنسيق نصوص/معرّفات: slug، تحويل التسميات، تنظيف HTML، الاختصار.",
        specs=_FORMAT_NODE_SPECS,
    ),
    "validation-node": NodeRole(
        role_id="validation-node",
        label_ar="عقدة التدقيق",
        description_ar="تحقق وسلامة بيانات: Luhn، توازن الأقواس، التكرار، الإخفاء، صلاحية المعرّفات.",
        specs=_VALIDATION_NODE_SPECS,
    ),
}


def get_node_role(role_id: str) -> NodeRole:
    try:
        return NODE_ROLES[role_id]
    except KeyError:
        raise ValueError(
            f"دور عقدة غير معروف: {role_id!r}. الأدوار المتاحة: {sorted(NODE_ROLES)}"
        ) from None
