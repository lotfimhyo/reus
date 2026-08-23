"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Optional Supabase mirror for approved data. This component does not accept raw
conversation text, memory, or secrets; it accepts only a field-limited
operational summary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

import requests


@dataclass(frozen=True)
class ApprovedSyncEvent:
    event_id: str
    kind: str
    summary: str
    occurred_at: str
    status: str

    def __post_init__(self) -> None:
        if len(self.summary) > 4_000:
            raise ValueError("Supabase summary exceeds the approved sync limit")


class HttpClient(Protocol):
    def post(self, url: str, **kwargs): ...


class SupabaseApprovedEventMirror:
    def __init__(self, base_url: str, api_key: str, table: str = "reus_sync_events", client: HttpClient = requests) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._table = table
        self._client = client

    def mirror(self, event: ApprovedSyncEvent) -> None:
        response = self._client.post(
            f"{self._base_url}/rest/v1/{self._table}",
            params={"on_conflict": "event_id"},
            headers={
                "apikey": self._api_key,
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json=asdict(event),
            timeout=10,
        )
        if not getattr(response, "ok", False):
            raise RuntimeError(f"Supabase mirror failed with status {getattr(response, 'status_code', 'unknown')}")
