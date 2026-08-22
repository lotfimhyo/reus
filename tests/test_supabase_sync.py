"""Project: Reus | Developer: lotfi Mahiddine | Organization: Reulink."""
import pytest
from pydantic import ValidationError

from config import Settings
from infrastructure.supabase_sync import ApprovedSyncEvent, SupabaseApprovedEventMirror


class Response:
    ok = True
    status_code = 201


class Http:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response()


def test_sync_is_rejected_without_explicit_credentials():
    with pytest.raises(ValidationError, match="Supabase sync requires"):
        Settings(supabase_sync_enabled=True)


def test_mirror_writes_only_approved_event_shape():
    http = Http()
    mirror = SupabaseApprovedEventMirror("https://example.supabase.co", "secret", client=http)
    mirror.mirror(ApprovedSyncEvent("event-1", "daily_report", "approved summary", "2026-08-20T00:00:00Z", "approved"))
    assert http.calls[0][0].endswith("/rest/v1/reus_sync_events")
    assert set(http.calls[0][1]["json"]) == {"event_id", "kind", "summary", "occurred_at", "status"}


def test_mirror_rejects_oversized_summary_before_network():
    with pytest.raises(ValueError, match="approved sync limit"):
        ApprovedSyncEvent("event-1", "report", "x" * 4_001, "2026-08-20T00:00:00Z", "approved")
