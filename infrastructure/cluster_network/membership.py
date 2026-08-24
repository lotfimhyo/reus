"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink.

Membership primitives for a single Raft cell.  Large Reus deployments use
many small cells; this module deliberately models only one cell's voters.
It supports a joint configuration so replacement never switches quorums in
one unsafe step.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class MembershipError(ValueError):
    """Raised when a Raft voter configuration is malformed or unsafe."""


def _normalise_voters(values: Iterable[str]) -> frozenset[str]:
    voters = frozenset(values)
    if not voters or any(not isinstance(node_id, str) or not node_id for node_id in voters):
        raise MembershipError("a voter configuration requires non-empty node identifiers")
    return voters


def _majority_size(voters: frozenset[str]) -> int:
    return len(voters) // 2 + 1


@dataclass(frozen=True)
class VoterConfiguration:
    """A committed voter set, optionally in a joint-consensus transition."""

    voters: frozenset[str]
    joint_voters: frozenset[str] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "voters", _normalise_voters(self.voters))
        if self.joint_voters is not None:
            object.__setattr__(self, "joint_voters", _normalise_voters(self.joint_voters))

    @property
    def all_voters(self) -> frozenset[str]:
        return self.voters | (self.joint_voters or frozenset())

    def peer_ids(self, local_node_id: str) -> list[str]:
        return sorted(self.all_voters - {local_node_id})

    def has_quorum(self, acknowledgements: Iterable[str]) -> bool:
        acknowledged = frozenset(acknowledgements)
        old_quorum = len(acknowledged & self.voters) >= _majority_size(self.voters)
        if self.joint_voters is None:
            return old_quorum
        new_quorum = len(acknowledged & self.joint_voters) >= _majority_size(self.joint_voters)
        return old_quorum and new_quorum

    def to_payload(self) -> dict[str, list[str]]:
        payload: dict[str, list[str]] = {"voters": sorted(self.voters)}
        if self.joint_voters is not None:
            payload["joint_voters"] = sorted(self.joint_voters)
        return payload

    @classmethod
    def from_payload(cls, payload: dict) -> "VoterConfiguration":
        if not isinstance(payload, dict) or not isinstance(payload.get("voters"), list):
            raise MembershipError("membership payload requires a voter list")
        joint = payload.get("joint_voters")
        if joint is not None and not isinstance(joint, list):
            raise MembershipError("joint voter configuration must be a list")
        return cls(frozenset(payload["voters"]), frozenset(joint) if joint is not None else None)
