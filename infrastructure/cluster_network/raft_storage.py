# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
RaftStorage: durable persistence for Raft's three required persistent
fields (Raft paper §5.1): currentTerm, votedFor, log[]. All three MUST be
persisted to stable storage before a node responds to a RequestVote or
AppendEntries RPC — otherwise a crash-and-restart could vote twice in the
same term, or "forget" log entries it already promised to a leader,
violating Raft's core safety guarantees.

Also persists log SNAPSHOTS (a separate file, `<path>.snapshot`): when
`RaftNode.compact_log()` discards committed entries below a chosen index,
it stores an application-supplied snapshot of state here instead, so the
main state file's log[] doesn't grow unboundedly. On restart, the
snapshot is loaded first (to restore the point compaction reached),
then only the remaining, not-yet-compacted log entries are loaded from
the main state file.

Writes (both the main state file and the snapshot file) are atomic
(write to a temp file, then `os.replace`), so a crash mid-write leaves
the previous valid file intact rather than a corrupted, partially-written
one.
"""

import json
import os
from typing import List, Optional, Tuple


class RaftStorage:
    def __init__(self, path: str):
        self._path = path
        self._snapshot_path = f"{path}.snapshot"

    def load(self) -> Optional[Tuple[int, Optional[str], List[dict]]]:
        """Returns (current_term, voted_for, log_entries_as_dicts), or
        None if nothing has ever been persisted (a brand-new node)."""
        if not os.path.exists(self._path):
            return None
        with open(self._path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["current_term"], data["voted_for"], data["log"]

    def load_commit_index(self) -> int:
        """Load the durable committed position, preserving old state files.

        Older Reus releases stored only Raft's minimum persistent fields.  A
        missing position is therefore interpreted as "no unapplied commit";
        a loaded snapshot still supplies its own committed lower bound.
        """
        if not os.path.exists(self._path):
            return -1
        with open(self._path, "r", encoding="utf-8") as f:
            return int(json.load(f).get("commit_index", -1))

    def save(
        self,
        current_term: int,
        voted_for: Optional[str],
        log_entries: List[dict],
        commit_index: int = -1,
    ) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        tmp_path = f"{self._path}.tmp"
        data = {
            "current_term": current_term,
            "voted_for": voted_for,
            "log": log_entries,
            "commit_index": commit_index,
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())  # ensure bytes actually hit disk before the atomic rename
        os.replace(tmp_path, self._path)  # atomic on POSIX

    def load_snapshot(self) -> Optional[Tuple[int, int, dict]]:
        """Returns (last_included_index, last_included_term, snapshot_data),
        or None if no snapshot has ever been taken."""
        if not os.path.exists(self._snapshot_path):
            return None
        with open(self._snapshot_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["last_included_index"], data["last_included_term"], data["snapshot_data"]

    def save_snapshot(self, last_included_index: int, last_included_term: int, snapshot_data: dict) -> None:
        os.makedirs(os.path.dirname(self._snapshot_path) or ".", exist_ok=True)
        tmp_path = f"{self._snapshot_path}.tmp"
        data = {
            "last_included_index": last_included_index,
            "last_included_term": last_included_term,
            "snapshot_data": snapshot_data,
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self._snapshot_path)
