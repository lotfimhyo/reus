"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

IdentityRegistry: the single source of truth mapping component_id ->
public identity manifest, used by every other layer to verify "who is
calling me" before trusting a signed request. This is the root-of-trust
lookup table described in the master architecture doc section 2.1.

This phase implements a local, file-persisted registry (JSON). A
distributed registry (for Hybrid/Cloud mode) is intentionally out of
scope here, per the "no future-phase files" rule.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from infrastructure.cognitive_core.identity.exceptions import InvalidSignatureError, UnknownComponentError
from infrastructure.cognitive_core.identity.identity import ComponentIdentity, IdentityManifest
from infrastructure.cognitive_core.identity.keys import verify


class IdentityRegistry:
    """
    In-memory identity registry with optional JSON file persistence.

    Responsibilities:
      - register(): record a component's public manifest.
      - get(): look up a manifest by component_id.
      - verify_actor_signature(): confirm a signature really came from the
        holder of a registered identity, using only public data.
    """

    def __init__(self, persist_path: Optional[str | Path] = None):
        self._manifests: dict[str, IdentityManifest] = {}
        self.persist_path = Path(persist_path) if persist_path else None
        if self.persist_path and self.persist_path.exists():
            self._load()

    def register(self, identity: ComponentIdentity | IdentityManifest) -> IdentityManifest:
        """Register a component's public manifest. Idempotent by component_id."""
        manifest = (
            identity.manifest()
            if isinstance(identity, ComponentIdentity)
            else identity
        )
        self._manifests[manifest.component_id] = manifest
        if self.persist_path:
            self._save()
        return manifest

    def get(self, component_id: str) -> IdentityManifest:
        try:
            return self._manifests[component_id]
        except KeyError as exc:
            raise UnknownComponentError(
                f"No component registered with id={component_id!r}."
            ) from exc

    def is_registered(self, component_id: str) -> bool:
        return component_id in self._manifests

    def list_components(self, component_type: Optional[str] = None) -> list[IdentityManifest]:
        values = list(self._manifests.values())
        if component_type is None:
            return values
        return [m for m in values if m.component_type == component_type]

    def verify_actor_signature(
        self, component_id: str, payload: bytes, signature: bytes
    ) -> bool:
        """
        Verify that `signature` over `payload` was produced by the private
        key belonging to the registered component_id. Raises
        UnknownComponentError if the component was never registered.
        """
        manifest = self.get(component_id)
        try:
            verify(manifest.public_key_hex, payload, signature)
            return True
        except InvalidSignatureError:
            return False

    def _save(self) -> None:
        assert self.persist_path is not None
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [m.to_dict() for m in self._manifests.values()]
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        assert self.persist_path is not None
        raw = json.loads(self.persist_path.read_text(encoding="utf-8"))
        for item in raw:
            manifest = IdentityManifest.from_dict(item)
            self._manifests[manifest.component_id] = manifest
