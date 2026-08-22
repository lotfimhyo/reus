# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Code synthesizers: given an AgentSpec, produce Python source text defining
a `GeneratedTool` class with a `run(self, input_data)` method.

`TemplateSynthesizer` is a small, fully offline, deterministic library of
known-safe logic patterns — enough to prove out the full pipeline
(synthesize -> static check -> sandbox test -> install) without needing a
live LLM. This is the "learning" component's training-wheels version.

`LLMSynthesizer` is the real upgrade path: it would ask an LLM to write the
`run` method's body for a *novel* capability description, then feed that
straight into the same static-check + sandbox pipeline. Nothing about the
safety pipeline changes based on where the code came from — a human, a
template, or a model all go through identical scrutiny before being
trusted.
"""

from abc import ABC, abstractmethod

from infrastructure.agent_factory.manifest import AgentSpec

# Each template maps to a *body* for run(self, input_data), written as
# plain, import-free Python. Keeping these hand-written (not built via
# string concatenation of untrusted input) means the only variable part of
# the generated file is which template was selected — the code text itself
# is always one of these known-safe snippets.
_TEMPLATES = {
    "uppercase": "return str(input_data).upper()",
    "lowercase": "return str(input_data).lower()",
    "reverse_text": "return str(input_data)[::-1]",
    "word_count": "return len(str(input_data).split())",
    "char_count": "return len(str(input_data))",
    "is_palindrome": (
        "text = ''.join(ch.lower() for ch in str(input_data) if ch.isalnum())\n"
        "        return text == text[::-1]"
    ),
    "sort_words": "return ' '.join(sorted(str(input_data).split()))",
    # -- عقدة النصوص (إضافات) ------------------------------------------------
    "title_case": "return ' '.join(w.capitalize() for w in str(input_data).split())",
    "remove_whitespace": "return ''.join(str(input_data).split())",
    "vowel_count": "return sum(1 for ch in str(input_data).lower() if ch in 'aeiou')",
    # -- عقدة الترميز (Caesar cipher + Run-Length Encoding) ------------------
    "caesar_encode": (
        "shift = 3\n"
        "        text = str(input_data)\n"
        "        result = ''\n"
        "        for ch in text:\n"
        "            if ch.isalpha():\n"
        "                base = 65 if ch.isupper() else 97\n"
        "                result += chr((ord(ch) - base + shift) % 26 + base)\n"
        "            else:\n"
        "                result += ch\n"
        "        return result"
    ),
    "caesar_decode": (
        "shift = -3\n"
        "        text = str(input_data)\n"
        "        result = ''\n"
        "        for ch in text:\n"
        "            if ch.isalpha():\n"
        "                base = 65 if ch.isupper() else 97\n"
        "                result += chr((ord(ch) - base + shift) % 26 + base)\n"
        "            else:\n"
        "                result += ch\n"
        "        return result"
    ),
    "run_length_encode": (
        "text = str(input_data)\n"
        "        if not text:\n"
        "            return ''\n"
        "        result = ''\n"
        "        count = 1\n"
        "        prev = text[0]\n"
        "        for ch in text[1:]:\n"
        "            if ch == prev:\n"
        "                count += 1\n"
        "            else:\n"
        "                result += prev + str(count)\n"
        "                prev = ch\n"
        "                count = 1\n"
        "        result += prev + str(count)\n"
        "        return result"
    ),
    "run_length_decode": (
        "text = str(input_data)\n"
        "        result = ''\n"
        "        i = 0\n"
        "        while i < len(text):\n"
        "            ch = text[i]\n"
        "            i += 1\n"
        "            num = ''\n"
        "            while i < len(text) and text[i].isdigit():\n"
        "                num += text[i]\n"
        "                i += 1\n"
        "            result += ch * int(num) if num else ch\n"
        "        return result"
    ),
    "checksum_sum": "return sum(ord(ch) for ch in str(input_data)) % 256",
    # -- عقدة الحساب ----------------------------------------------------------
    "digit_sum": "return sum(int(ch) for ch in str(input_data) if ch.isdigit())",
    "is_numeric": "return str(input_data).strip().lstrip('-').replace('.', '', 1).isdigit()",
    "decimal_to_binary": (
        "n = int(input_data)\n"
        "        if n == 0:\n"
        "            return '0'\n"
        "        negative = n < 0\n"
        "        n = abs(n)\n"
        "        digits = ''\n"
        "        while n > 0:\n"
        "            digits = str(n % 2) + digits\n"
        "            n //= 2\n"
        "        return ('-' if negative else '') + digits"
    ),
    "decimal_to_hex": (
        "n = int(input_data)\n"
        "        if n == 0:\n"
        "            return '0'\n"
        "        negative = n < 0\n"
        "        n = abs(n)\n"
        "        hex_chars = '0123456789abcdef'\n"
        "        digits = ''\n"
        "        while n > 0:\n"
        "            digits = hex_chars[n % 16] + digits\n"
        "            n //= 16\n"
        "        return ('-' if negative else '') + digits"
    ),
    "is_prime": (
        "n = int(input_data)\n"
        "        if n < 2:\n"
        "            return False\n"
        "        i = 2\n"
        "        while i * i <= n:\n"
        "            if n % i == 0:\n"
        "                return False\n"
        "            i += 1\n"
        "        return True"
    ),
    "factorial": (
        "n = int(input_data)\n"
        "        if n < 0:\n"
        "            return None\n"
        "        result = 1\n"
        "        for i in range(2, n + 1):\n"
        "            result *= i\n"
        "        return result"
    ),
    # -- عقدة التنسيق -----------------------------------------------------------
    "slugify": (
        "text = str(input_data).strip().lower()\n"
        "        result = ''\n"
        "        for ch in text:\n"
        "            if ch.isalnum():\n"
        "                result += ch\n"
        "            elif ch in (' ', '-', '_'):\n"
        "                result += '-'\n"
        "        while '--' in result:\n"
        "            result = result.replace('--', '-')\n"
        "        return result.strip('-')"
    ),
    "snake_to_camel": (
        "parts = str(input_data).split('_')\n"
        "        return parts[0] + ''.join(p.capitalize() for p in parts[1:])"
    ),
    "camel_to_snake": (
        "result = ''\n"
        "        for ch in str(input_data):\n"
        "            if ch.isupper():\n"
        "                result += '_' + ch.lower()\n"
        "            else:\n"
        "                result += ch\n"
        "        return result.lstrip('_')"
    ),
    "strip_html_tags": (
        "text = str(input_data)\n"
        "        result = ''\n"
        "        inside = False\n"
        "        for ch in text:\n"
        "            if ch == '<':\n"
        "                inside = True\n"
        "            elif ch == '>':\n"
        "                inside = False\n"
        "            elif not inside:\n"
        "                result += ch\n"
        "        return result"
    ),
    "truncate_ellipsis": (
        "text = str(input_data)\n"
        "        max_len = 20\n"
        "        if len(text) <= max_len:\n"
        "            return text\n"
        "        return text[:max_len - 3] + '...'"
    ),
    # -- عقدة التدقيق -----------------------------------------------------------
    "luhn_check": (
        "digits = [int(ch) for ch in str(input_data) if ch.isdigit()]\n"
        "        if not digits:\n"
        "            return False\n"
        "        digits.reverse()\n"
        "        total = 0\n"
        "        for i, d in enumerate(digits):\n"
        "            if i % 2 == 1:\n"
        "                d *= 2\n"
        "                if d > 9:\n"
        "                    d -= 9\n"
        "            total += d\n"
        "        return total % 10 == 0"
    ),
    "is_balanced_brackets": (
        "pairs = {')': '(', ']': '[', '}': '{'}\n"
        "        stack = []\n"
        "        for ch in str(input_data):\n"
        "            if ch in '([{':\n"
        "                stack.append(ch)\n"
        "            elif ch in ')]}':\n"
        "                if not stack or stack.pop() != pairs[ch]:\n"
        "                    return False\n"
        "        return len(stack) == 0"
    ),
    "has_duplicate_words": (
        "words = str(input_data).lower().split()\n"
        "        seen = set()\n"
        "        for w in words:\n"
        "            if w in seen:\n"
        "                return True\n"
        "            seen.add(w)\n"
        "        return False"
    ),
    "count_unique_words": "return len(set(str(input_data).lower().split()))",
    "mask_sensitive_middle": (
        "text = str(input_data)\n"
        "        if len(text) <= 4:\n"
        "            return '*' * len(text)\n"
        "        return text[:2] + '*' * (len(text) - 4) + text[-2:]"
    ),
    "is_valid_username": (
        "text = str(input_data)\n"
        "        if not (3 <= len(text) <= 20):\n"
        "            return False\n"
        "        if not text[0].isalpha():\n"
        "            return False\n"
        "        for ch in text:\n"
        "            if not (ch.isalnum() or ch == '_'):\n"
        "                return False\n"
        "        return True"
    ),
}


class BaseSynthesizer(ABC):
    @abstractmethod
    def synthesize(self, spec: AgentSpec) -> str:
        ...


class TemplateSynthesizer(BaseSynthesizer):
    def synthesize(self, spec: AgentSpec) -> str:
        if spec.template not in _TEMPLATES:
            raise ValueError(
                f"Unknown template '{spec.template}'. Known templates: {sorted(_TEMPLATES)}"
            )
        body = _TEMPLATES[spec.template]
        return (
            "class GeneratedTool:\n"
            f"    name = {spec.name!r}\n"
            f"    capability = {spec.capability!r}\n\n"
            "    def run(self, input_data):\n"
            f"        {body}\n"
        )

    @staticmethod
    def available_templates() -> list[str]:
        return sorted(_TEMPLATES)


class LLMSynthesizer(BaseSynthesizer):
    """NOT used by default (requires network + ANTHROPIC_API_KEY). Shows
    how a real model would plug into the exact same pipeline. Everything
    downstream (static_analyze, AgentSandbox) treats its output identically
    to the template synthesizer's — model-authored code gets no special
    trust."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        import anthropic  # imported lazily; no hard dependency for Stage 3 offline use
        self._client = anthropic.Anthropic()
        self._model = model

    def synthesize(self, spec: AgentSpec) -> str:
        prompt = (
            "Write ONLY the body of a Python method `run(self, input_data)` "
            "for a class named GeneratedTool, implementing this capability:\n"
            f"{spec.description}\n\n"
            "Rules: no imports, no eval/exec/open/getattr/dunder access, "
            "pure logic only, return the result directly. "
            "Return ONLY the method body, properly indented, nothing else."
        )
        response = self._client.messages.create(
            model=self._model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        body = "".join(block.text for block in response.content if block.type == "text").strip()
        return (
            "class GeneratedTool:\n"
            f"    name = {spec.name!r}\n"
            f"    capability = {spec.capability!r}\n\n"
            "    def run(self, input_data):\n"
            f"        {body}\n"
        )
