# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
ModelClientRegistry: يربط بين اسم المزوّد (provider في ModelProfile) والعميل
الفعلي المسؤول عن استدعائه. هذا ما يسمح لـ ModelRouter باختيار أنسب نموذج عبر
كل المزوّدين المسجَّلين معًا (Anthropic, OpenAI, Google...)، بينما ModelRoutingExecutor
لا يحتاج معرفة أي تفاصيل عن أي SDK على الإطلاق — فقط "أعطني عميل هذا المزوّد".
"""
from __future__ import annotations

from infrastructure.model_client import ModelClient


class UnknownProvider(Exception):
    def __init__(self, provider: str):
        super().__init__(f"لا يوجد عميل مسجَّل للمزوّد: '{provider}'")


class ModelClientRegistry:
    def __init__(self, clients: dict[str, ModelClient] | None = None) -> None:
        self._clients: dict[str, ModelClient] = dict(clients or {})

    def register(self, provider: str, client: ModelClient) -> None:
        self._clients[provider] = client

    def get(self, provider: str) -> ModelClient:
        client = self._clients.get(provider)
        if client is None:
            raise UnknownProvider(provider)
        return client

    def providers(self) -> list[str]:
        return list(self._clients.keys())
