"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Join-time snapshot exchange, per architecture doc section 3.4 step 4:
"يُعيد لقطة ابتدائية (قدرات + معرفة دلالية حاليتين) لتسريع إحماء B."

Scope decision: this is a ONE-TIME bootstrap transfer at the moment of
joining, not the ongoing periodic gossip described in the doc's sections 4
and 5 (deliberately still deferred — see the architecture doc's own
roadmap). It reuses the exact same idempotent Memory/Capability facade
methods every other layer already goes through; no new merge logic exists
here, only serialization.

Known limitation (documented, not an oversight): a cached capability
receives a newly-generated local capability_id distinct from the
originating peer's own id for that capability. CapabilityDescriptor.
component_id still correctly names the true owner, so this is a caching
identity, not an ownership claim — but reconciling capability_ids across
nodes precisely is left to the still-deferred gossip-sync phase, which will
need a real answer for this; a join-time bootstrap does not.
"""

from __future__ import annotations

from typing import Any

from infrastructure.cognitive_core.capability.capability_layer import CapabilityLayer
from infrastructure.cognitive_core.capability.descriptor import RiskLevel
from infrastructure.cognitive_core.memory.memory_layer import MemoryLayer


def build_capability_snapshot(capabilities: CapabilityLayer) -> list[dict[str, Any]]:
    """Serialize every currently-discoverable capability for transfer."""
    return [d.to_dict() for d in capabilities.discover()]


def apply_capability_snapshot(
    capabilities: CapabilityLayer, snapshot: list[dict[str, Any]]
) -> list:
    """
    Ingest a peer's capability snapshot as local cache entries, preserving
    the true owning component_id from each descriptor. Returns the newly
    created local CapabilityDescriptor objects (not just a count) so a
    caller — specifically JoinClient — can record, for each one, which
    peer node it actually came from (see peer_directory.py); Capability
    Registry itself has no notion of "which node," only "which agent."
    """
    ingested = []
    for item in snapshot:
        descriptor = capabilities.publish(
            component_id=item["component_id"],
            name=item["name"],
            description=item.get("description", ""),
            input_schema=item.get("input_schema") or {},
            output_schema=item.get("output_schema") or {},
            estimated_cost=item.get("estimated_cost", 0.0),
            risk_level=RiskLevel(item.get("risk_level", "low")),
            tags=tuple(item.get("tags", [])),
        )
        ingested.append(descriptor)
    return ingested


def build_semantic_snapshot(memory: MemoryLayer) -> list[dict[str, Any]]:
    """
    Serialize every current fact as a portable (name, type) triple rather
    than raw entity ids — entity ids are node-local SQLite rows, meaningless
    on another device. The receiving side re-resolves entities by
    (name, entity_type) through the same idempotent add_entity(), so two
    nodes independently referring to "translate_text"/"capability" always
    converge on the same logical entity without ever comparing raw ids.
    """
    portable: list[dict[str, Any]] = []
    for fact in memory.query_facts():
        subject = memory.get_entity(fact.subject_id)
        obj = memory.get_entity(fact.object_id)
        portable.append(
            {
                "subject_name": subject.name,
                "subject_type": subject.entity_type,
                "predicate": fact.predicate,
                "object_name": obj.name,
                "object_type": obj.entity_type,
                "confidence": fact.confidence,
            }
        )
    return portable


def apply_semantic_snapshot(memory: MemoryLayer, snapshot: list[dict[str, Any]]) -> int:
    """Ingest a peer's semantic snapshot via the same idempotent
    add_entity()/add_fact() every local caller already uses — no separate
    merge algorithm, per architecture doc section 4's whole premise.
    Returns the number of facts ingested."""
    count = 0
    for item in snapshot:
        subject = memory.add_entity(item["subject_name"], item["subject_type"])
        obj = memory.add_entity(item["object_name"], item["object_type"])
        memory.add_fact(
            subject.id, item["predicate"], obj.id, confidence=item.get("confidence", 1.0)
        )
        count += 1
    return count
