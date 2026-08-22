# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
ModelClient: يفصل "كيفية استدعاء نموذج فعليًا عبر الشبكة" عن قرار "أي نموذج نختار"
(ModelRouter). العميل قابل للحقن، ما يسمح باختبار المنطق المحيط دون شبكة فعلية.

يدعم هذا الملف الآن عدة مزوّدين (Anthropic, OpenAI, Google) خلف واجهة واحدة موحّدة،
واستدعاء بأدوات (Tool Use) لمن يدعمه من المزوّدين.

قرار هندسي موثّق بصدق: كل عميل هنا كود حقيقي وكامل يستخدم SDK الرسمي لمزوّده،
لكن تشغيله الفعلي يتطلب مفتاح API صالحًا ووصولًا شبكيًا لنطاق ذلك المزوّد. بيئة
تطوير هذا المشروع تحديدًا مُقيَّدة شبكيًا بحيث لا تصل إلا إلى api.anthropic.com
(انظر إعدادات الشبكة)؛ لا يمكنها الوصول إلى api.openai.com أو googleapis.com إطلاقًا،
بغض النظر عن وجود مفتاح API. لذلك عميلا OpenAI وGoogle هنا **كود إنتاجي كامل وصحيح
بنيويًا**، لكن لم يُتحقق منهما عبر نداء شبكي فعلي في هذه البيئة تحديدًا — فقط عبر
حقن عميل SDK وهمي (نفس أسلوب اختبار AnthropicModelClient). أي بيئة تشغيل فعلية بلا
هذا التقييد الشبكي المحدد يمكنها استخدامهما مباشرة بضبط مفتاح API المناسب فقط.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable

import anthropic

logger = logging.getLogger("reus_veritas.model_client")


class ModelInvocationError(Exception):
    """تُرفع عند فشل استدعاء النموذج فعليًا (خطأ شبكة، مصادقة، أو استجابة API)."""


class ToolUseNotSupported(Exception):
    def __init__(self, provider: str):
        super().__init__(f"المزوّد '{provider}' لا يدعم Tool Use في هذا التطبيق حاليًا")


class ModelClient(ABC):
    @abstractmethod
    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        """يستدعي النموذج ويُعيد النص المُولَّد، أو يرفع ModelInvocationError."""
        ...

    def invoke_with_tools(
        self,
        model_id: str,
        prompt: str,
        tools: list[dict],
        tool_dispatcher: Callable[[str, dict], Any],
        max_tokens: int = 1024,
        max_iterations: int = 5,
    ) -> str:
        """
        استدعاء بحلقة أدوات كاملة (Agentic Loop): يستدعي النموذج، وإن طلب استخدام
        أداة ينفّذها فعليًا عبر tool_dispatcher ثم يُعيد النتيجة للنموذج، ويكرر
        حتى يُنتج ردًا نصيًا نهائيًا أو يبلغ max_iterations. التطبيق الافتراضي
        يرفع ToolUseNotSupported؛ فقط العملاء الذين يطبّقونه فعليًا يدعمونه.
        """
        raise ToolUseNotSupported(self.__class__.__name__)


class AnthropicModelClient(ModelClient):
    def __init__(self, api_key: str, client: anthropic.Anthropic | None = None) -> None:
        # السماح بحقن client يتيح اختبار المنطق بالكامل دون مفتاح API حقيقي أو شبكة.
        self._client = client or anthropic.Anthropic(api_key=api_key)

    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        try:
            response = self._client.messages.create(
                model=model_id,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise ModelInvocationError(f"فشل استدعاء النموذج '{model_id}': {exc}") from exc

        return self._extract_text(response, model_id)

    def invoke_with_tools(
        self,
        model_id: str,
        prompt: str,
        tools: list[dict],
        tool_dispatcher: Callable[[str, dict], Any],
        max_tokens: int = 1024,
        max_iterations: int = 5,
    ) -> str:
        messages: list[dict] = [{"role": "user", "content": prompt}]

        for _ in range(max_iterations):
            try:
                response = self._client.messages.create(
                    model=model_id, max_tokens=max_tokens, messages=messages, tools=tools
                )
            except anthropic.APIError as exc:
                raise ModelInvocationError(f"فشل استدعاء النموذج '{model_id}': {exc}") from exc

            if response.stop_reason != "tool_use":
                return self._extract_text(response, model_id)

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                logger.info(
                    "tool_use_invoked", extra={"event_name": "tool_use", "payload": {"tool": block.name}}
                )
                result = tool_dispatcher(block.name, block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": str(result)}
                )
            messages.append({"role": "user", "content": tool_results})

        raise ModelInvocationError(
            f"تجاوز النموذج '{model_id}' الحد الأقصى لتكرارات استخدام الأدوات ({max_iterations}) دون رد نهائي"
        )

    @staticmethod
    def _extract_text(response: Any, model_id: str) -> str:
        text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        if not text_blocks:
            raise ModelInvocationError(f"لم يُعِد النموذج '{model_id}' أي محتوى نصي")
        return "".join(text_blocks)


class OpenAIModelClient(ModelClient):
    """
    عميل حقيقي وكامل عبر SDK الرسمي لـ OpenAI. راجع ملاحظة الصدق أعلى الملف بخصوص
    قيود الشبكة في هذه البيئة تحديدًا.
    """

    def __init__(self, api_key: str, client: Any = None) -> None:
        self._api_key = api_key
        self._injected_client = client
        self._client: Any = None  # يُبنى كسوليًا (Lazy) عند أول استخدام فعلي فقط

    def _get_client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        if self._client is None:
            import openai

            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        import openai as openai_module

        try:
            response = self._get_client().chat.completions.create(
                model=model_id,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except openai_module.APIError as exc:
            raise ModelInvocationError(f"فشل استدعاء النموذج '{model_id}': {exc}") from exc

        choice = response.choices[0] if response.choices else None
        content = getattr(getattr(choice, "message", None), "content", None) if choice else None
        if not content:
            raise ModelInvocationError(f"لم يُعِد النموذج '{model_id}' أي محتوى نصي")
        return content


class KimiModelClient(OpenAIModelClient):
    """عميل Kimi عبر واجهته الرسمية المتوافقة مع OpenAI.

    لا يمنح هذا العميل Kimi أي صلاحيات أدوات أو تنفيذ محلي؛ يقتصر دوره على
    توليد النص عندما يفعّل المطور المزود صراحة ضمن مسار النماذج الثانوية.
    """

    def __init__(self, api_key: str, base_url: str, client: Any = None) -> None:
        super().__init__(api_key=api_key, client=client)
        self._base_url = base_url.rstrip("/")

    def _get_client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        if self._client is None:
            import openai

            self._client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client


class GoogleModelClient(ModelClient):
    """
    عميل حقيقي وكامل عبر SDK الرسمي لـ Google (google-genai، عائلة نماذج Gemini).
    راجع ملاحظة الصدق أعلى الملف بخصوص قيود الشبكة في هذه البيئة تحديدًا.
    """

    def __init__(self, api_key: str, client: Any = None) -> None:
        self._api_key = api_key
        self._injected_client = client
        self._client: Any = None  # يُبنى كسوليًا (Lazy) عند أول استخدام فعلي فقط

    def _get_client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        try:
            response = self._get_client().models.generate_content(
                model=model_id,
                contents=prompt,
                config={"max_output_tokens": max_tokens},
            )
        except Exception as exc:  # مكتبة google-genai لا تُصدّر تسلسل استثناءات موحّدًا واحدًا فقط
            raise ModelInvocationError(f"فشل استدعاء النموذج '{model_id}': {exc}") from exc

        text = getattr(response, "text", None)
        if not text:
            raise ModelInvocationError(f"لم يُعِد النموذج '{model_id}' أي محتوى نصي")
        return text
