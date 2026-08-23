"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Simple in-memory implementation for governance. Used for tests and initial
local operation; it can be replaced by a PostgreSQL repository without
changing the autonomy supervisor contract.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from domain.autonomy import GeneratedAgentDraft, ImprovementProposal, ProposalStatus
from infrastructure.agent_factory.manifest import AgentSpec
from infrastructure.cognitive_core.capability.descriptor import RiskLevel


class InMemoryGovernanceLedger:
    def __init__(self) -> None:
        self._proposals: dict[str, ImprovementProposal] = {}

    def record(self, proposal: ImprovementProposal) -> None:
        if proposal.proposal_id in self._proposals:
            raise ValueError("proposal already exists")
        self._proposals[proposal.proposal_id] = proposal

    def get(self, proposal_id: str) -> ImprovementProposal:
        try:
            return self._proposals[proposal_id]
        except KeyError as exc:
            raise KeyError(f"unknown proposal {proposal_id}") from exc

    def update(self, proposal: ImprovementProposal) -> None:
        if proposal.proposal_id not in self._proposals:
            raise KeyError(f"unknown proposal {proposal.proposal_id}")
        self._proposals[proposal.proposal_id] = proposal

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for proposal in self._proposals.values():
            key = proposal.status.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def list_pending(self) -> list[ImprovementProposal]:
        return [proposal for proposal in self._proposals.values() if proposal.status is ProposalStatus.PENDING]

    def list_all(self) -> list[ImprovementProposal]:
        return list(self._proposals.values())


class FileGovernanceLedger(InMemoryGovernanceLedger):
    """Local durable ledger for governed autonomy proposals.

    The record contains declarative specs and review state, never generated
    executable code or model memory.  Each change is written atomically and
    emitted to an append-only local audit file.
    """

    def __init__(self, persist_path: str, audit_path: str | None = None) -> None:
        super().__init__()
        self._path = Path(persist_path)
        self._audit_path = Path(audit_path or f"{persist_path}.audit.jsonl")
        self._load()

    @staticmethod
    def _serialize(proposal: ImprovementProposal) -> dict:
        draft = proposal.draft
        return {
            "proposal_id": proposal.proposal_id,
            "goal_id": proposal.goal_id,
            "draft": {
                "spec": draft.spec.to_dict(),
                "tags": list(draft.tags),
                "risk_level": draft.risk_level.value,
                "estimated_cost": draft.estimated_cost,
                "input_schema": draft.input_schema,
                "output_schema": draft.output_schema,
            },
            "status": proposal.status.value,
            "rationale": proposal.rationale,
            "validation_summary": proposal.validation_summary,
            "file_path": proposal.file_path,
            "reviewer_note": proposal.reviewer_note,
        }

    @staticmethod
    def _deserialize(record: dict) -> ImprovementProposal:
        draft_data = record["draft"]
        draft = GeneratedAgentDraft(
            spec=AgentSpec.from_dict(draft_data["spec"]),
            tags=tuple(draft_data.get("tags", [])),
            risk_level=RiskLevel(draft_data["risk_level"]),
            estimated_cost=float(draft_data["estimated_cost"]),
            input_schema=draft_data.get("input_schema", {}),
            output_schema=draft_data.get("output_schema", {}),
        )
        return ImprovementProposal(
            proposal_id=record["proposal_id"],
            goal_id=record["goal_id"],
            draft=draft,
            status=ProposalStatus(record["status"]),
            rationale=record["rationale"],
            validation_summary=record["validation_summary"],
            file_path=record.get("file_path"),
            reviewer_note=record.get("reviewer_note"),
        )

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            records = json.loads(self._path.read_text(encoding="utf-8"))
            self._proposals = {record["proposal_id"]: self._deserialize(record) for record in records}
        except (OSError, TypeError, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"cannot load autonomy governance ledger: {exc}") from exc

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temporary.write_text(
            json.dumps([self._serialize(proposal) for proposal in self._proposals.values()], sort_keys=True),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self._path)

    def _audit(self, event: str, proposal: ImprovementProposal) -> None:
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "event": event,
            "proposal_id": proposal.proposal_id,
            "goal_id": proposal.goal_id,
            "status": proposal.status.value,
            "reviewer_note": proposal.reviewer_note,
        }
        with self._audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(self._audit_path, 0o600)

    def record(self, proposal: ImprovementProposal) -> None:
        super().record(proposal)
        self._save()
        self._audit("created", proposal)

    def update(self, proposal: ImprovementProposal) -> None:
        super().update(proposal)
        self._save()
        self._audit("updated", proposal)
