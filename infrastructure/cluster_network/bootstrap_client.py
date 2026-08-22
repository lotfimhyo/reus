"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

BootstrapClient — initiating side of the trust bootstrap handshake against
a peer's plain-HTTP BootstrapServer. Submits this node's certificate +
identity, then polls (bounded, not indefinite) until a human administrator
on the peer's side approves or rejects via Telegram. On approval, returns
the peer's own certificate/address so the caller can add it to its local
TrustStore too (mutual trust) before any mTLS traffic is attempted.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests


class BootstrapRejected(Exception):
    pass


class BootstrapTimedOut(Exception):
    pass


class BootstrapConnectionError(Exception):
    pass


@dataclass(frozen=True)
class BootstrapApproval:
    """The peer's own identity, learned only after a human approved this
    node's join request — everything needed to add the peer as trusted."""

    node_id: str
    host: str
    mtls_port: int
    cert_pem: str
    signing_pubkey_hex: str
    component_public_key_hex: str
    component_created_at: str


class BootstrapClient:
    def __init__(self, timeout_seconds: float = 10.0, poll_interval_seconds: float = 2.0):
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def request_join(self, bootstrap_base_url: str, own_identity_payload: dict) -> str:
        """Submits the bootstrap request. Returns the request_id assigned
        by the peer — the caller is responsible for polling status with it."""
        try:
            response = requests.post(
                f"{bootstrap_base_url.rstrip('/')}/cluster/bootstrap-request",
                json=own_identity_payload,
                timeout=self.timeout_seconds,
            )
        except requests.exceptions.RequestException as exc:
            raise BootstrapConnectionError(
                f"Could not reach bootstrap server at {bootstrap_base_url!r}: {exc}"
            ) from exc

        if response.status_code != 202:
            raise BootstrapConnectionError(
                f"Bootstrap server at {bootstrap_base_url!r} rejected the request "
                f"(status {response.status_code}): {response.text}"
            )
        return response.json()["request_id"]

    def poll_until_decided(
        self, bootstrap_base_url: str, request_id: str, max_wait_seconds: float = 300.0
    ) -> BootstrapApproval:
        """Blocks (polling, not busy-waiting) until a human approves or
        rejects. Raises BootstrapRejected / BootstrapTimedOut accordingly.
        Bounded by `max_wait_seconds` so a node never hangs forever waiting
        on a human who never responds."""
        deadline = time.monotonic() + max_wait_seconds
        while time.monotonic() < deadline:
            status_payload = self._get_status(bootstrap_base_url, request_id)
            status = status_payload.get("status")
            if status == "approved":
                responder = status_payload["responder"]
                return BootstrapApproval(
                    node_id=responder["node_id"],
                    host=responder["host"],
                    mtls_port=int(responder["mtls_port"]),
                    cert_pem=responder["cert_pem"],
                    signing_pubkey_hex=responder["signing_pubkey_hex"],
                    component_public_key_hex=responder["component_public_key_hex"],
                    component_created_at=responder["component_created_at"],
                )
            if status == "rejected":
                raise BootstrapRejected(
                    f"Peer at {bootstrap_base_url!r} rejected join request {request_id!r}."
                )
            time.sleep(self.poll_interval_seconds)

        raise BootstrapTimedOut(
            f"No human decision on join request {request_id!r} within {max_wait_seconds}s."
        )

    def _get_status(self, bootstrap_base_url: str, request_id: str) -> dict:
        try:
            response = requests.get(
                f"{bootstrap_base_url.rstrip('/')}/cluster/bootstrap-status/{request_id}",
                timeout=self.timeout_seconds,
            )
        except requests.exceptions.RequestException as exc:
            raise BootstrapConnectionError(
                f"Could not reach bootstrap server at {bootstrap_base_url!r}: {exc}"
            ) from exc
        return response.json()
