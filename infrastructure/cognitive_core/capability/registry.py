"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

CapabilityRegistry — the discoverable catalog of everything the system can
do, per master architecture doc section 2.4. The Cognitive Engine (Layer 5,
future phase) queries this registry to find candidate capabilities for a
goal, using cost/risk/tags to help evaluate plans.

Design decision: like IdentityRegistry (Layer 1), this phase uses a local,
in-memory registry with optional JSON file persistence — a distributed
registry is out of scope until Hybrid/Cloud mode is designed.

Re-registering a (component_id, name) pair does NOT overwrite the previous
descriptor in place; it stores a new version and keeps the old one queryable
by capability_id, so that a plan already evaluated against v1 stays valid
even after the component publishes v2.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from infrastructure.cognitive_core.capability.descriptor import (
    CapabilityDescriptor,
    RiskLevel,
    build_descriptor,
)
from infrastructure.cognitive_core.capability.exceptions import UnknownCapabilityError


class CapabilityRegistry:
    """In-memory capability catalog with optional JSON file persistence."""

    def __init__(self, persist_path: Optional[str | Path] = None):
        self._by_id: dict[str, CapabilityDescriptor] = {}
        # (component_id, name) -> latest capability_id, for version lookups
        self._latest: dict[tuple[str, str], str] = {}
        self.persist_path = Path(persist_path) if persist_path else None
        if self.persist_path and self.persist_path.exists():
            self._load()

    def register(
        self,
        component_id: str,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        estimated_cost: float,
        risk_level: RiskLevel,
        tags: Optional[tuple[str, ...]] = None,
    ) -> CapabilityDescriptor:
        """Publish a capability. If (component_id, name) was already
        registered, this creates the next version rather than a duplicate
        entry — satisfying the same "no duplicate knowledge" principle used
        in Memory Layer, applied here to capability metadata."""
        key = (component_id, name)
        previous_id = self._latest.get(key)
        next_version = self._by_id[previous_id].version + 1 if previous_id else 1

        descriptor = build_descriptor(
            component_id=component_id,
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            estimated_cost=estimated_cost,
            risk_level=risk_level,
            tags=tags,
            version=next_version,
        )
        self._by_id[descriptor.capability_id] = descriptor
        self._latest[key] = descriptor.capability_id

        if self.persist_path:
            self._save()
        return descriptor

    def get(self, capability_id: str) -> CapabilityDescriptor:
        try:
            return self._by_id[capability_id]
        except KeyError as exc:
            raise UnknownCapabilityError(
                f"No capability registered with id={capability_id!r}."
            ) from exc

    def get_latest(self, component_id: str, name: str) -> CapabilityDescriptor:
        """Look up the current (highest-version) descriptor for a
        (component_id, name) pair."""
        capability_id = self._latest.get((component_id, name))
        if capability_id is None:
            raise UnknownCapabilityError(
                f"No capability named {name!r} registered by component "
                f"{component_id!r}."
            )
        return self._by_id[capability_id]

    def find_by_name(self, name: str) -> list[CapabilityDescriptor]:
        """All *latest-version* descriptors across all components that
        publish a capability with this name."""
        return [
            self._by_id[cap_id]
            for (comp_id, cap_name), cap_id in self._latest.items()
            if cap_name == name
        ]

    def list_capabilities(
        self,
        component_id: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> list[CapabilityDescriptor]:
        """List latest-version capabilities, optionally filtered by owning
        component and/or tag. This is the primary discovery entry point."""
        results = [self._by_id[cap_id] for cap_id in self._latest.values()]
        if component_id is not None:
            results = [d for d in results if d.component_id == component_id]
        if tag is not None:
            results = [d for d in results if tag in d.tags]
        return results

    def unregister(self, component_id: str, name: str) -> None:
        """Remove a capability from discovery (e.g. the owning component
        went offline). Historical descriptor versions remain retrievable
        by capability_id via get() for audit purposes, but stop appearing
        in list_capabilities()/find_by_name()."""
        key = (component_id, name)
        if key in self._latest:
            del self._latest[key]
            if self.persist_path:
                self._save()

    def _save(self) -> None:
        assert self.persist_path is not None
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "descriptors": [d.to_dict() for d in self._by_id.values()],
            "latest": {f"{c}\u0000{n}": cid for (c, n), cid in self._latest.items()},
        }
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        assert self.persist_path is not None
        raw = json.loads(self.persist_path.read_text(encoding="utf-8"))
        for item in raw["descriptors"]:
            descriptor = CapabilityDescriptor.from_dict(item)
            self._by_id[descriptor.capability_id] = descriptor
        for key, cap_id in raw["latest"].items():
            component_id, name = key.split("\u0000", 1)
            self._latest[(component_id, name)] = cap_id
