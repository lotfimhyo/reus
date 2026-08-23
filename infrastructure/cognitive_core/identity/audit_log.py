"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

AppendOnlyAuditLog: tamper-evident audit trail for every operation performed
between layers, per the master architecture document section 5: a complete
audit log.

Design decision (section 4 of the master architecture doc): JSONL + hash
chaining was chosen over a full relational database for this phase, because
it is simple, tamper-resistant, and sufficient for single-machine Local Mode.
Each entry embeds the hash of the previous entry, so any retroactive edit or
deletion breaks the chain and is detectable by verify_chain().
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from infrastructure.cognitive_core.identity.exceptions import AuditChainCorruptedError
from infrastructure.cognitive_core.identity.identity import ComponentIdentity
from infrastructure.cognitive_core.identity.keys import is_valid

GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class AuditEntry:
    """A single, signed, hash-chained audit log entry."""

    seq: int
    timestamp: str
    actor_id: str
    actor_public_key_hex: str
    action: str
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str
    signature_hex: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "AuditEntry":
        return AuditEntry(**data)

    def _hashable_body(self) -> bytes:
        """
        The exact byte sequence that was hashed and signed. Kept as a
        separate method so append() and verify_chain() can never drift
        apart in what they hash.
        """
        body = {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "actor_id": self.actor_id,
            "actor_public_key_hex": self.actor_public_key_hex,
            "action": self.action,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


class AppendOnlyAuditLog:
    """
    A JSONL-backed, hash-chained, signed audit log.

    Every append() call:
      1. computes prev_hash from the last entry (or GENESIS_HASH if empty),
      2. builds the entry body and hashes it -> entry_hash,
      3. signs entry_hash with the actor's private key,
      4. appends the entry as one JSON line to the log file.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _last_entry(self) -> AuditEntry | None:
        last: AuditEntry | None = None
        for entry in self._iter_entries():
            last = entry
        return last

    def _iter_entries(self) -> Iterator[AuditEntry]:
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield AuditEntry.from_dict(json.loads(line))

    def append(
        self, actor: ComponentIdentity, action: str, payload: dict[str, Any]
    ) -> AuditEntry:
        """Append a new signed, hash-chained entry performed by `actor`."""
        last = self._last_entry()
        prev_hash = last.entry_hash if last is not None else GENESIS_HASH
        seq = (last.seq + 1) if last is not None else 0

        draft = AuditEntry(
            seq=seq,
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor_id=actor.component_id,
            actor_public_key_hex=actor.public_key_hex,
            action=action,
            payload=payload,
            prev_hash=prev_hash,
            entry_hash="",
            signature_hex="",
        )
        entry_hash = hashlib.sha256(draft._hashable_body()).hexdigest()
        signature = actor.sign(bytes.fromhex(entry_hash))

        final_entry = AuditEntry(
            seq=draft.seq,
            timestamp=draft.timestamp,
            actor_id=draft.actor_id,
            actor_public_key_hex=draft.actor_public_key_hex,
            action=draft.action,
            payload=draft.payload,
            prev_hash=draft.prev_hash,
            entry_hash=entry_hash,
            signature_hex=signature.hex(),
        )

        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(final_entry.to_dict(), sort_keys=True) + "\n")

        return final_entry

    def verify_chain(self) -> bool:
        """
        Verify the full integrity of the log: hash chain continuity,
        entry_hash correctness, and signature validity for every entry.

        Raises AuditChainCorruptedError with a specific reason on failure,
        rather than silently returning False, so operators can see exactly
        where tampering occurred.
        """
        prev_hash = GENESIS_HASH
        expected_seq = 0

        for entry in self._iter_entries():
            if entry.seq != expected_seq:
                raise AuditChainCorruptedError(
                    f"Out-of-order sequence at seq={entry.seq}, "
                    f"expected {expected_seq}."
                )
            if entry.prev_hash != prev_hash:
                raise AuditChainCorruptedError(
                    f"Broken hash chain at seq={entry.seq}: "
                    f"prev_hash mismatch."
                )
            recomputed_hash = hashlib.sha256(entry._hashable_body()).hexdigest()
            if recomputed_hash != entry.entry_hash:
                raise AuditChainCorruptedError(
                    f"Entry hash mismatch at seq={entry.seq}: entry was "
                    f"modified after being written."
                )
            if not is_valid(
                entry.actor_public_key_hex,
                bytes.fromhex(entry.entry_hash),
                bytes.fromhex(entry.signature_hex),
            ):
                raise AuditChainCorruptedError(
                    f"Invalid signature at seq={entry.seq}."
                )

            prev_hash = entry.entry_hash
            expected_seq += 1

        return True

    def all_entries(self) -> list[AuditEntry]:
        return list(self._iter_entries())
