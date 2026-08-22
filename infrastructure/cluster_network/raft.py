# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
RaftNode: a minimal, honestly-scoped implementation of Raft leader election
+ log replication — used for the one thing the architecture doc calls for
from consensus: "which node leads a given task", i.e. electing a stable
coordinator among trusted peers and replicating a small decision log
(task assignments) so every node agrees on who's doing what.

Scope, stated plainly:
  - Leader election is a full RequestVote/AppendEntries term-based
    election with randomized timeouts and majority voting — a faithful
    (if simplified) implementation of that part of the Raft paper.
  - Log replication commits entries via majority acknowledgment and
    applies them to a local state machine via `on_commit`. currentTerm,
    votedFor, and log[] persist to disk (see raft_storage.py) — a crash
    and restart no longer forgets a vote already cast or entries already
    accepted, per Raft's core safety requirement.
  - Log compaction / snapshotting: `compact_log()` discards committed log
    entries below a chosen index, persisting an application-supplied
    snapshot of state in their place, so the persisted file no longer
    grows unbounded. A follower too far behind to catch up via normal
    AppendEntries (because the leader already compacted past what it
    needs) is caught up via a basic InstallSnapshot RPC instead.
  - Authentication: RPCs travel over the same mutual-TLS channel as the
    rest of the network layer, so the client certificate already
    authenticates the sender. These frequent, low-latency internal RPCs
    are not additionally payload-signed the way knowledge/agent-sync
    messages are (see network/node.py for why those are signed).
"""

import random
import threading
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from infrastructure.cluster_network.raft_storage import RaftStorage


class Role(str, Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


@dataclass
class LogEntry:
    term: int
    index: int
    command: dict


class RaftNode:
    def __init__(
        self,
        node_id: str,
        get_peer_ids: Callable[[], List[str]],
        rpc_client,
        election_timeout_range: Tuple[float, float] = (1.0, 2.0),
        heartbeat_interval: float = 0.3,
        storage: Optional[RaftStorage] = None,
    ):
        self.node_id = node_id
        self._get_peer_ids = get_peer_ids  # cluster membership can grow (see discovery.py)
        self._rpc = rpc_client
        self._storage = storage

        self._lock = threading.RLock()
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.role = Role.FOLLOWER
        self.log: List[LogEntry] = []
        self.commit_index = -1
        self.leader_id: Optional[str] = None

        # Snapshotting: entries with absolute index <= this have been
        # compacted out of `self.log` and folded into a snapshot instead.
        # -1 means "nothing has ever been compacted".
        self._snapshot_last_included_index = -1
        self._snapshot_last_included_term = 0
        # Populated from disk at startup if a snapshot exists; the owner
        # (PhoenixNode) reads this right after construction to restore
        # its own state machine (e.g. the task ledger) — see the note on
        # callback ordering in _load_persisted_state below.
        self.restored_snapshot_data: Optional[dict] = None

        # Callbacks the owning application wires in AFTER construction:
        #   on_commit(entry)          -> apply a newly committed entry
        #   get_snapshot_data()       -> dict: current state to snapshot
        #   on_snapshot_restore(data) -> restore state from a received/loaded snapshot
        self.on_commit: Optional[Callable[[LogEntry], None]] = None
        self.get_snapshot_data: Optional[Callable[[], dict]] = None
        self.on_snapshot_restore: Optional[Callable[[dict], None]] = None
        self.on_leader_tick: Optional[Callable[[], None]] = None
        self.on_peer_liveness: Optional[Callable[[str, bool], None]] = None

        self._load_persisted_state()

        self._next_index: Dict[str, int] = {}
        self._match_index: Dict[str, int] = {}

        self._election_timeout_range = election_timeout_range
        self._heartbeat_interval = heartbeat_interval
        self._election_deadline = self._new_election_deadline()

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- persistence -----------------------------------------------------------

    def _load_persisted_state(self) -> None:
        if not self._storage:
            return

        snap = self._storage.load_snapshot()
        if snap is not None:
            self._snapshot_last_included_index, self._snapshot_last_included_term, data = snap
            # Can't call on_snapshot_restore yet — the owner sets that
            # callback AFTER constructing this RaftNode. Stash the data;
            # the owner is expected to read `restored_snapshot_data`
            # itself right after construction (see network/node.py).
            self.restored_snapshot_data = data

        loaded = self._storage.load()
        if loaded is None:
            return  # brand-new node, nothing more to restore
        current_term, voted_for, log_dicts = loaded
        self.current_term = current_term
        self.voted_for = voted_for
        self.log = [LogEntry(term=e["term"], index=e["index"], command=e["command"]) for e in log_dicts]
        persisted_commit = self._storage.load_commit_index()
        # A stored commit beyond the local log is never trusted blindly. This
        # bounds a damaged/stale local state file while honoring a restored
        # snapshot, whose base is necessarily committed.
        self.commit_index = max(
            self._snapshot_last_included_index,
            min(persisted_commit, self._last_log_index()),
        )

    def _persist(self) -> None:
        """Must be called (while holding self._lock) after any change to
        current_term, voted_for, or log — and BEFORE responding to the RPC
        that triggered the change, per Raft's persistence requirement.
        A no-op if no RaftStorage was configured."""
        if self._storage:
            self._storage.save(
                self.current_term,
                self.voted_for,
                [asdict(e) for e in self.log],
                commit_index=self.commit_index,
            )

    # -- log index/term helpers (account for compacted-away entries) ------------

    def _last_log_index(self) -> int:
        return self.log[-1].index if self.log else self._snapshot_last_included_index

    def _last_log_term(self) -> int:
        return self.log[-1].term if self.log else self._snapshot_last_included_term

    def _log_entry_at(self, absolute_index: int) -> Optional[LogEntry]:
        """The entry at `absolute_index`, or None if it's before the start
        of what we have (compacted into a snapshot, or simply doesn't
        exist yet)."""
        pos = absolute_index - self._snapshot_last_included_index - 1
        if 0 <= pos < len(self.log):
            return self.log[pos]
        return None

    def _term_at(self, absolute_index: int) -> int:
        if absolute_index == self._snapshot_last_included_index:
            return self._snapshot_last_included_term
        entry = self._log_entry_at(absolute_index)
        return entry.term if entry else 0

    # -- log compaction / snapshotting -------------------------------------------

    def compact_log(self, upto_index: Optional[int] = None) -> bool:
        """Discards log entries up to and including `upto_index` (default:
        self.commit_index — never compact past what's committed, since
        an uncommitted entry might still be rolled back), persisting a
        snapshot of application state (from `get_snapshot_data()`) in
        their place. Returns False if there's nothing new to compact."""
        with self._lock:
            target = self.commit_index if upto_index is None else min(upto_index, self.commit_index)
            if target <= self._snapshot_last_included_index:
                return False
            entry = self._log_entry_at(target)
            if entry is None:
                return False  # already compacted at or past this point

            snapshot_term = entry.term
            snapshot_data = self.get_snapshot_data() if self.get_snapshot_data else {}

            old_base = self._snapshot_last_included_index
            keep_from_pos = target - old_base  # first list position to KEEP
            self.log = self.log[keep_from_pos:]
            self._snapshot_last_included_index = target
            self._snapshot_last_included_term = snapshot_term

            if self._storage:
                self._storage.save_snapshot(target, snapshot_term, snapshot_data)
                self._persist()  # the now-shorter log needs re-persisting too
            return True

    def _new_election_deadline(self) -> float:
        return time.monotonic() + random.uniform(*self._election_timeout_range)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                role = self.role
            if role == Role.LEADER:
                self._send_heartbeats()
                if self.on_leader_tick:
                    self.on_leader_tick()
                time.sleep(self._heartbeat_interval)
            else:
                if time.monotonic() >= self._election_deadline:
                    self._start_election()
                time.sleep(0.05)

    # -- election ------------------------------------------------------------

    def _start_election(self) -> None:
        with self._lock:
            self.current_term += 1
            self.role = Role.CANDIDATE
            self.voted_for = self.node_id
            self._persist()  # must hit disk before we ask anyone to trust this term/vote
            term = self.current_term
            last_log_index = self._last_log_index()
            last_log_term = self._last_log_term()
            self._election_deadline = self._new_election_deadline()
            peer_ids = list(self._get_peer_ids())

        votes = 1  # vote for self
        for peer_id in peer_ids:
            try:
                resp_term, granted = self._rpc.request_vote(peer_id, term, self.node_id, last_log_index, last_log_term)
            except Exception:
                continue
            with self._lock:
                if resp_term > self.current_term:
                    self._step_down(resp_term)
                    return
                if self.role != Role.CANDIDATE or self.current_term != term:
                    return  # state changed mid-election
            if granted:
                votes += 1

        majority = (len(peer_ids) + 1) // 2 + 1
        with self._lock:
            if self.role == Role.CANDIDATE and self.current_term == term and votes >= majority:
                self._become_leader(peer_ids)

    def _become_leader(self, peer_ids: List[str]) -> None:
        self.role = Role.LEADER
        self.leader_id = self.node_id
        for peer_id in peer_ids:
            self._next_index[peer_id] = self._last_log_index() + 1
            self._match_index[peer_id] = -1

    def _step_down(self, new_term: int) -> None:
        self.current_term = new_term
        self.role = Role.FOLLOWER
        self.voted_for = None
        self._election_deadline = self._new_election_deadline()
        self._persist()

    # -- RPC handlers (invoked by the network layer on inbound calls) --------

    def handle_request_vote(self, term: int, candidate_id: str, last_log_index: int, last_log_term: int) -> Tuple[int, bool]:
        with self._lock:
            if term < self.current_term:
                return self.current_term, False
            if term > self.current_term:
                self._step_down(term)

            my_last_index = self._last_log_index()
            my_last_term = self._last_log_term()
            log_ok = (last_log_term > my_last_term) or (
                last_log_term == my_last_term and last_log_index >= my_last_index
            )

            if self.voted_for in (None, candidate_id) and log_ok:
                self.voted_for = candidate_id
                self._election_deadline = self._new_election_deadline()
                self._persist()  # must hit disk before granting the vote
                return self.current_term, True
            return self.current_term, False

    def handle_append_entries(
        self, term: int, leader_id: str, prev_log_index: int, prev_log_term: int,
        entries: List[dict], leader_commit: int,
    ) -> Tuple[int, bool]:
        with self._lock:
            if term < self.current_term:
                return self.current_term, False

            if term > self.current_term:
                self.current_term = term
                self.role = Role.FOLLOWER
                self.leader_id = leader_id
                self.voted_for = None
                self._persist()  # term/voted_for changed — must hit disk even if we reject below
            else:
                self.role = Role.FOLLOWER
                self.leader_id = leader_id
            self._election_deadline = self._new_election_deadline()

            if prev_log_index >= 0:
                if prev_log_index < self._snapshot_last_included_index:
                    pass  # both sides already agree on everything up to our snapshot
                elif prev_log_index > self._last_log_index():
                    return self.current_term, False  # we're missing entries entirely
                else:
                    if self._term_at(prev_log_index) != prev_log_term:
                        return self.current_term, False

            insert_at = prev_log_index + 1
            log_changed = False
            for i, entry_dict in enumerate(entries):
                idx = insert_at + i
                if idx <= self._snapshot_last_included_index:
                    continue  # already compacted into our snapshot, nothing to do
                entry = LogEntry(term=entry_dict["term"], index=idx, command=entry_dict["command"])
                pos = idx - self._snapshot_last_included_index - 1
                if pos < len(self.log):
                    if self.log[pos].term != entry.term:
                        self.log = self.log[:pos]
                        self.log.append(entry)
                        log_changed = True
                else:
                    self.log.append(entry)
                    log_changed = True
            if log_changed:
                self._persist()  # log[] changed — must hit disk before acking success

            if leader_commit > self.commit_index:
                self._apply_committed(min(leader_commit, self._last_log_index()))

            return self.current_term, True

    def handle_install_snapshot(
        self, term: int, leader_id: str, last_included_index: int, last_included_term: int, snapshot_data: dict,
    ) -> Tuple[int, bool]:
        """Catches up a follower that's too far behind for normal
        AppendEntries because the leader already compacted past what the
        follower needs."""
        with self._lock:
            if term < self.current_term:
                return self.current_term, False
            if term > self.current_term:
                self._step_down(term)
            self.role = Role.FOLLOWER
            self.leader_id = leader_id
            self._election_deadline = self._new_election_deadline()

            if last_included_index <= self._snapshot_last_included_index:
                return self.current_term, True  # we already have this or a newer snapshot

            self.log = [e for e in self.log if e.index > last_included_index]
            self._snapshot_last_included_index = last_included_index
            self._snapshot_last_included_term = last_included_term
            if self.commit_index < last_included_index:
                self.commit_index = last_included_index

            if self._storage:
                self._storage.save_snapshot(last_included_index, last_included_term, snapshot_data)
                self._persist()

            if self.on_snapshot_restore:
                self.on_snapshot_restore(snapshot_data)

            return self.current_term, True

    def _apply_committed(self, new_commit_index: int) -> None:
        for idx in range(self.commit_index + 1, new_commit_index + 1):
            entry = self._log_entry_at(idx)
            if entry is not None and self.on_commit:
                self.on_commit(entry)
        self.commit_index = new_commit_index
        self._persist()

    def replay_committed(self) -> None:
        """Replay the durable committed suffix after a process restart.

        The owner installs its state-machine callback after constructing this
        object.  Replaying only entries after the snapshot base restores that
        state machine without changing `commit_index` or pretending the
        commands were newly committed.
        """
        with self._lock:
            callback = self.on_commit
            entries = [
                self._log_entry_at(index)
                for index in range(self._snapshot_last_included_index + 1, self.commit_index + 1)
            ]
        if callback is not None:
            for entry in entries:
                if entry is not None:
                    callback(entry)

    # -- leader operations -----------------------------------------------------

    def _send_heartbeats(self) -> None:
        with self._lock:
            if self.role != Role.LEADER:
                return
            term = self.current_term
            log_snapshot = list(self.log)
            snapshot_base = self._snapshot_last_included_index
            snapshot_term = self._snapshot_last_included_term
            snapshot_data = self.get_snapshot_data() if self.get_snapshot_data else {}
            commit_index = self.commit_index
            peer_ids = list(self._get_peer_ids())

        for peer_id in peer_ids:
            next_idx = self._next_index.get(peer_id, (log_snapshot[-1].index if log_snapshot else snapshot_base) + 1)

            if next_idx <= snapshot_base:
                # The peer needs entries we've already compacted away —
                # send a snapshot instead of (impossible) log entries.
                try:
                    resp_term, success = self._rpc.install_snapshot(
                        peer_id, term, self.node_id, snapshot_base, snapshot_term, snapshot_data,
                    )
                except Exception:
                    if self.on_peer_liveness:
                        self.on_peer_liveness(peer_id, False)
                    continue
                with self._lock:
                    if resp_term > self.current_term:
                        self._step_down(resp_term)
                        return
                    if self.role != Role.LEADER:
                        return
                    if success:
                        if self.on_peer_liveness:
                            self.on_peer_liveness(peer_id, True)
                        self._match_index[peer_id] = snapshot_base
                        self._next_index[peer_id] = snapshot_base + 1
                    elif self.on_peer_liveness:
                        self.on_peer_liveness(peer_id, False)
                continue

            prev_log_index = next_idx - 1
            if prev_log_index == snapshot_base:
                prev_log_term = snapshot_term
            else:
                prev_entry = next((e for e in log_snapshot if e.index == prev_log_index), None)
                prev_log_term = prev_entry.term if prev_entry else 0

            entries_to_send = [
                {"term": e.term, "command": e.command} for e in log_snapshot if e.index >= next_idx
            ]
            try:
                resp_term, success = self._rpc.append_entries(
                    peer_id, term, self.node_id, prev_log_index, prev_log_term, entries_to_send, commit_index
                )
            except Exception:
                if self.on_peer_liveness:
                    self.on_peer_liveness(peer_id, False)
                continue

            with self._lock:
                if resp_term > self.current_term:
                    self._step_down(resp_term)
                    return
                if self.role != Role.LEADER:
                    return
                if success:
                    if self.on_peer_liveness:
                        self.on_peer_liveness(peer_id, True)
                    self._match_index[peer_id] = next_idx + len(entries_to_send) - 1
                    self._next_index[peer_id] = self._match_index[peer_id] + 1
                else:
                    if self.on_peer_liveness:
                        self.on_peer_liveness(peer_id, False)
                    self._next_index[peer_id] = max(0, self._next_index.get(peer_id, 0) - 1)

        with self._lock:
            # Checked once per round, unconditionally — not just as a
            # side effect of a peer's ack. A single-node "cluster" (zero
            # peers) has a trivial majority of 1 (itself) and must still
            # be able to commit its own proposed entries; gating this
            # entirely behind "a peer just acked" meant nothing ever
            # committed with no peers at all.
            if self.role == Role.LEADER:
                self._maybe_advance_commit_index(peer_ids)

    def _maybe_advance_commit_index(self, peer_ids: List[str]) -> None:
        last_idx = self._last_log_index()
        for idx in range(last_idx, self.commit_index, -1):
            entry = self._log_entry_at(idx)
            if entry is None or entry.term != self.current_term:
                continue  # Raft safety: only directly commit entries from our own term
            replicated = 1 + sum(1 for p in peer_ids if self._match_index.get(p, -1) >= idx)
            majority = (len(peer_ids) + 1) // 2 + 1
            if replicated >= majority:
                self._apply_committed(idx)
                break

    def propose(self, command: dict) -> bool:
        """Leader-only: append a new command to the log for replication.
        Returns False if this node isn't currently the leader."""
        with self._lock:
            if self.role != Role.LEADER:
                return False
            self.log.append(LogEntry(term=self.current_term, index=self._last_log_index() + 1, command=command))
            self._persist()
        return True

    def propose_and_wait(self, command: dict, timeout_seconds: float = 5.0) -> bool:
        """Append a leader command and wait, bounded, for its Raft commit.

        Returning from :meth:`propose` means only that the leader appended the
        entry.  Callers that must not act before quorum confirmation (such as
        task execution) use this method instead.
        """
        with self._lock:
            if self.role != Role.LEADER:
                return False
            self.log.append(LogEntry(term=self.current_term, index=self._last_log_index() + 1, command=command))
            index = self.log[-1].index
            self._persist()
        deadline = time.monotonic() + max(0.01, timeout_seconds)
        while time.monotonic() < deadline:
            self._send_heartbeats()
            with self._lock:
                if self.commit_index >= index:
                    return True
                if self.role != Role.LEADER:
                    return False
            time.sleep(0.01)
        return False

    def status(self) -> dict:
        with self._lock:
            return {
                "node_id": self.node_id,
                "role": self.role.value,
                "term": self.current_term,
                "leader_id": self.leader_id,
                "log_length": len(self.log),
                "commit_index": self.commit_index,
                "snapshot_last_included_index": self._snapshot_last_included_index,
            }
