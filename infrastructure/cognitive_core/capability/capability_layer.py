"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

CapabilityLayer — the single public entry point for Layer 4 (Capability
Registry), following the same "no leaky abstractions" pattern as
MemoryLayer: other layers depend only on this facade, never on
CapabilityRegistry directly.

Every publish/unpublish is signed by this layer's own ComponentIdentity and
recorded in the shared AppendOnlyAuditLog (Layer 1) — publishing a new
capability is exactly the kind of system-changing event the master
architecture doc requires to be fully traceable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from infrastructure.cognitive_core.capability.descriptor import CapabilityDescriptor, RiskLevel
from infrastructure.cognitive_core.capability.registry import CapabilityRegistry
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog, ComponentIdentity


class CapabilityLayer:
    """Facade for publishing and discovering capabilities, audited and
    identity-bound."""

    def __init__(
        self,
        audit_log: AppendOnlyAuditLog,
        data_dir: str | Path = "data",
        identity: Optional[ComponentIdentity] = None,
    ):
        self.identity = identity or ComponentIdentity.create("capability_layer")
        self._audit_log = audit_log
        self._registry = CapabilityRegistry(
            persist_path=Path(data_dir) / "capabilities.json"
        )

    def publish(
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
        """Publish (or re-publish a new version of) a capability."""
        descriptor = self._registry.register(
            component_id=component_id,
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            estimated_cost=estimated_cost,
            risk_level=risk_level,
            tags=tags,
        )
        self._audit_log.append(
            self.identity,
            "capability.publish",
            {
                "capability_id": descriptor.capability_id,
                "component_id": component_id,
                "name": name,
                "version": descriptor.version,
                "risk_level": descriptor.risk_level.value,
            },
        )
        return descriptor

    def unpublish(self, component_id: str, name: str) -> None:
        """Remove a capability from discovery."""
        self._registry.unregister(component_id, name)
        self._audit_log.append(
            self.identity,
            "capability.unpublish",
            {"component_id": component_id, "name": name},
        )

    def get(self, capability_id: str) -> CapabilityDescriptor:
        return self._registry.get(capability_id)

    def get_latest(self, component_id: str, name: str) -> CapabilityDescriptor:
        return self._registry.get_latest(component_id, name)

    def find_by_name(self, name: str) -> list[CapabilityDescriptor]:
        return self._registry.find_by_name(name)

    def discover(
        self, component_id: Optional[str] = None, tag: Optional[str] = None
    ) -> list[CapabilityDescriptor]:
        """Primary discovery entry point used by the Cognitive Engine to
        find candidate capabilities for a goal."""
        return self._registry.list_capabilities(component_id=component_id, tag=tag)
