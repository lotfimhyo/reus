# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
AgentCapabilityBinder connects the agent factory (`AgentBuilder`) with the
cognitive core (`CapabilityLayer` and `LocalExecutor`).

Without this module, `AgentBuilder.build()` may write code to disk but the
result is not executable through `REUS_TASK_EXECUTOR=cognitive`.

The central invariant is strict: only a `BuildResult` with `approved=True` may
be registered or bound. It has already passed generation, static restrictions
(including no imports or dangerous builtins), and isolated sandbox tests for
all test cases. This module never weakens or bypasses those gates; it binds only
what has passed them.

Every newly bound capability is recorded in `AppendOnlyAuditLog` through
`CapabilityLayer.publish`, preserving traceability for what the system added,
its origin, and time. Every accepted or rejected build is also published on the
shared EventBus (`capability.built` or `capability.rejected`) so the existing
ObservabilityService can include self-built capabilities in its unified view.
"""
from __future__ import annotations

from infrastructure.agent_factory.builder import AgentBuilder, BuildResult
from infrastructure.cognitive_core.capability import CapabilityLayer
from infrastructure.cognitive_core.capability.descriptor import CapabilityDescriptor, RiskLevel
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor
from infrastructure.event_bus import Event, EventBus


class CapabilityBindingRejected(Exception):
    """Raised when a BuildResult is not approved: explicit rejection, never silent failure."""


class AgentCapabilityBinder:
    def __init__(
        self,
        builder: AgentBuilder,
        capability_layer: CapabilityLayer,
        local_executor: LocalExecutor,
        component_id: str = "agent_factory",
        default_risk_level: RiskLevel = RiskLevel.LOW,
        event_bus: EventBus | None = None,
    ) -> None:
        self._builder = builder
        self._capabilities = capability_layer
        self._executor = local_executor
        self._component_id = component_id
        self._default_risk_level = default_risk_level
        self._bus = event_bus

    def build_and_bind(self, spec) -> CapabilityDescriptor:
        """Build through the complete AgentBuilder pipeline and, only on
        success, bind immediately without further review. This is retained for
        trusted template-built capabilities with fixed, hand-authored logic.

        For an Ollama-proposed capability in the node-evolution flow, call
        `build()` and `bind()` separately through
        `application/capability_evolution_service.py`, which inserts Telegram
        human approval between them.

        Rejecting a build raises CapabilityBindingRejected with the complete
        AgentBuilder reason; the failure is never silently discarded.
        """
        result: BuildResult = self.build(spec)
        return self.bind(result)

    def build(self, spec) -> BuildResult:
        """Run generation, static analysis, and sandboxing only; do not
        publish or bind. Always return `BuildResult`, leaving callers to reject
        a result immediately or surface its reason for human review."""
        result: BuildResult = self._builder.build(spec)
        if not result.approved:
            self._publish(
                "capability.rejected",
                {"spec_name": spec.name, "capability": spec.capability, "reason": result.reason},
            )
        return result

    def bind(self, result: BuildResult) -> CapabilityDescriptor:
        """Load the tool into the real process, publish it in CapabilityLayer,
        and bind its execution in LocalExecutor. Only an approved BuildResult
        is accepted; a rejected result raises CapabilityBindingRejected with its
        original reason."""
        if not result.approved:
            raise CapabilityBindingRejected(result.reason)

        spec = result.spec
        tool = self._builder.load_tool_instance(result)

        # LocalExecutor invokes every handler with the complete payload dict,
        # while generated factory tools expect one raw `input_data` value. The
        # convention is therefore explicit: the raw value arrives under
        # payload["input"].
        #
        # Validate this key rather than relying on a silent .get(). For example,
        # a missing input on a text capability can yield the apparently
        # successful but meaningless value "NONE" because str(None).upper()
        # does not fail. Other capability templates would fail differently. A
        # single explicit invariant keeps that behavior consistent.
        def handler(payload: dict, _tool=tool):
            if "input" not in payload:
                raise ValueError(
                    f"Capability '{spec.capability}' requires an \"input\" key in the payload; "
                    f"it was not sent. Received keys: {sorted(payload.keys())}"
                )
            return _tool.run(payload["input"])

        descriptor = self._capabilities.publish(
            component_id=self._component_id,
            name=spec.capability,
            description=spec.description,
            input_schema={"input": "any — raw value passed directly to GeneratedTool.run"},
            output_schema={},
            estimated_cost=0.0,
            risk_level=self._default_risk_level,
            tags=("self-built", f"spec:{spec.name}"),
        )
        self._executor.register_handler(descriptor.capability_id, handler)
        self._publish(
            "capability.built",
            {"spec_name": spec.name, "capability": spec.capability, "capability_id": descriptor.capability_id},
        )
        return descriptor

    def _publish(self, name: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(Event(name=name, payload=payload))
