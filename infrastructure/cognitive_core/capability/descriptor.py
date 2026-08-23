"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

CapabilityDescriptor — the machine-discoverable manifest every agent/tool
publishes about itself, per master architecture doc section 2.4:
every system component must declare its capabilities in an automatically
discoverable form,
and the vision doc's requirement to capture cost, resources, time, and risk
as inputs to plan evaluation (section "Cognitive Engine", step 4).

Design decision: input_schema/output_schema are plain dicts (JSON Schema
style), per the master doc's choice of JSON Schema over Protobuf for this
phase (documented in the architecture doc, section 4) — easy to inspect and
validate without generated code.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from infrastructure.cognitive_core.capability.exceptions import InvalidDescriptorError

_VALID_NAME_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
)


class RiskLevel(str, Enum):
    """Coarse risk classification used by the Cognitive Engine's plan
    evaluation step to weigh candidate plans."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class CapabilityDescriptor:
    """
    A single published capability. Immutable once created — updating a
    capability produces a new descriptor with an incremented `version`
    rather than mutating fields in place, so past plan evaluations that
    referenced a specific descriptor remain reproducible.
    """

    capability_id: str
    component_id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    estimated_cost: float
    risk_level: RiskLevel
    tags: tuple[str, ...]
    version: int
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "component_id": self.component_id,
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "estimated_cost": self.estimated_cost,
            "risk_level": self.risk_level.value,
            "tags": list(self.tags),
            "version": self.version,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "CapabilityDescriptor":
        return CapabilityDescriptor(
            capability_id=data["capability_id"],
            component_id=data["component_id"],
            name=data["name"],
            description=data["description"],
            input_schema=data["input_schema"],
            output_schema=data["output_schema"],
            estimated_cost=data["estimated_cost"],
            risk_level=RiskLevel(data["risk_level"]),
            tags=tuple(data.get("tags", [])),
            version=data["version"],
            created_at=data["created_at"],
        )


def build_descriptor(
    component_id: str,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    estimated_cost: float,
    risk_level: RiskLevel,
    tags: Optional[tuple[str, ...]] = None,
    version: int = 1,
    capability_id: Optional[str] = None,
) -> CapabilityDescriptor:
    """Validate inputs and construct a new CapabilityDescriptor."""
    if not name or not name.strip():
        raise InvalidDescriptorError("Capability name must be non-empty.")
    if not set(name) <= _VALID_NAME_CHARS:
        raise InvalidDescriptorError(
            f"Capability name {name!r} contains invalid characters; "
            "use letters, digits, '.', '_' or '-' only."
        )
    if estimated_cost < 0:
        raise InvalidDescriptorError("estimated_cost must be >= 0.")
    if not isinstance(risk_level, RiskLevel):
        raise InvalidDescriptorError("risk_level must be a RiskLevel value.")

    return CapabilityDescriptor(
        capability_id=capability_id or str(uuid.uuid4()),
        component_id=component_id,
        name=name,
        description=description,
        input_schema=input_schema,
        output_schema=output_schema,
        estimated_cost=estimated_cost,
        risk_level=risk_level,
        tags=tags or (),
        version=version,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
