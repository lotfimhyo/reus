# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Embedder port: converts text to a numeric embedding for semantic search.

The current environment does not download pre-trained models, so the default is
HashingEmbedder. Feature hashing provides fully local embeddings without an
external model. Because Embedder is an abstract interface, a preloaded
SentenceTransformerEmbedder can later replace it through container.py without
changing domain or application layers.
"""
from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod

import numpy as np

_TOKEN_RE = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)  # Supports Arabic and English tokens.


class Embedder(ABC):
    dimension: int

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder(Embedder):
    """
    Bag-of-Words + Feature Hashing + TF-weighting + L2 Normalization.
    Fully deterministic: identical text always produces the same vector, with
    no training or model download required.
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
            sign = 1.0 if digest[4] % 2 == 0 else -1.0  # Signed hashing reduces biased collisions.
            vector[index] += sign
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector.tolist()
