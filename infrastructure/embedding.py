# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Embedder Port: يحوّل نصًا إلى متجه رقمي (Embedding) لتمكين البحث الدلالي.

قرار هندسي مهم (موثّق بصدق):
هذه البيئة الحالية لا تملك وصولًا شبكيًا لتحميل نماذج جاهزة (مثل Hugging Face)،
لذلك التطبيق الافتراضي هنا هو HashingEmbedder: تقنية "Feature Hashing"
(تُستخدم إنتاجيًا في أنظمة مثل Vowpal Wabbit) تعمل محليًا بالكامل دون أي نموذج خارجي.

بما أن Embedder واجهة مجردة، يمكن استبدالها لاحقًا بـ SentenceTransformerEmbedder
(sentence-transformers + نموذج محمّل مسبقًا) بتغيير سطر واحد في container.py،
دون أي تعديل على طبقتي Domain أو Application.
"""
from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod

import numpy as np

_TOKEN_RE = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)  # يدعم العربية والإنجليزية


class Embedder(ABC):
    dimension: int

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder(Embedder):
    """
    Bag-of-Words + Feature Hashing + TF-weighting + L2 Normalization.
    حتمي تمامًا (نفس النص ينتج دائمًا نفس المتجه)، ولا يحتاج تدريبًا أو تحميل نموذج.
    """

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def _tokenize(self, text: str) -> list[str]:
        return _TOKEN_RE.findall(text.lower())

    def embed(self, text: str) -> list[float]:
        vector = np.zeros(self.dimension, dtype=np.float32)
        tokens = self._tokenize(text)
        if not tokens:
            return vector.tolist()
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0  # توزيع إشارات لتقليل التصادم المنحاز
            vector[index] += sign
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector.tolist()
