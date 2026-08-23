# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
ModelClientRegistry maps a provider name from ModelProfile to the concrete
client that invokes it. This lets ModelRouter select an appropriate model
across all registered providers while ModelRoutingExecutor remains independent
of provider SDK details and only requests that provider's client.
"""
from __future__ import annotations

from infrastructure.model_client import ModelClient


class UnknownProvider(Exception):
    def __init__(self, provider: str):
        super().__init__(f"No client is registered for provider: '{provider}'")


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
