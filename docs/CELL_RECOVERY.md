# Reus Cell Recovery and Controlled Scale

**Project:** Reus
**Founder:** Lotfi Mahiddine
**Organization:** Reulink

## Purpose and boundary

This guide describes the local-first operating model for making Reus clusters
more resilient without treating thousands of nodes as one global consensus
group. A **cell** is a small, trusted Raft voter set that owns only its local
coordination decisions and task leases. Federation remains metadata-only.

> This is a resilience design, not a claim of limitless scale, quantum
> equivalence, autonomous procurement, or autonomous authority.

Raft makes progress when a majority of a cell can communicate; a five-voter
cell can therefore tolerate two stopped voters, but not loss of a majority.[1]
Reus keeps cells small and uses separate routing and metadata layers between
cells rather than extending one Raft quorum across all nodes.

## Membership and standby lifecycle

| State | Entry condition | Rights | Exit condition |
| --- | --- | --- | --- |
| **Candidate** | Presents identity through bootstrap | None | Explicit human approval or rejection |
| **Trusted learner** | mTLS identity approved and membership snapshot received | Receives replication; no vote | Promoted by a committed joint change or removed |
| **Voter** | Joint configuration and final configuration are committed | Votes, elects, and acknowledges cell decisions | Replaced through a committed joint change |
| **Retired voter** | Final replacement configuration is committed | Receives its final commit acknowledgement only | Removed from the leader replication set |

The transition from one voter set to another uses a **joint configuration**:
the temporary configuration requires a majority of both the old and the new
sets. Only after that commitment does Reus commit the final voter set. This
prevents the old and new memberships from independently making conflicting
progress during replacement.[1]

## Failure recovery path

1. The leader observes peer liveness through the existing mTLS Raft channel.
2. Leases owned by an unreachable peer are requeued through the committed
   Raft log; no worker may continue solely on a stale local lease.
3. A recovery planner waits for a configurable number and duration of failed
   observations. One transient timeout cannot replace a node.
4. The planner selects only a **healthy, trusted learner** already registered
   as a standby. It never provisions a machine, grants trust, or chooses an
   untrusted endpoint.
5. The leader proposes the old-to-new voter replacement. The joint and final
   configurations must each commit before the standby becomes a voter.

If no standby is ready, Reus requeues eligible work but leaves membership
unchanged. This preserves safety rather than creating a guessed replacement.

## Recommended progressive deployment

Start with one local cell and one explicitly approved learner on separate
hardware. Validate a stopped-voter recovery test, then add cells only when a
clear workload boundary exists. Use small odd voter counts such as three or
five for a cell; do not use every available machine as a voter. Route
cross-cell work through metadata, resource reservation, and governed task
handoff rather than a single global quorum.

## Cloud purchasing boundary

The code can construct a one-time hosting authorization whose immutable
details include provider, plan, region, price, currency, and billing period.
Creation calls must consume that exact authorization immediately before the
provider call. Reus does **not** hold card details, select a provider, create
resources, or connect an account by default. A real purchase remains blocked
until an operator has selected a provider, configured a local credential, and
reviewed the exact price and scope in the same approval flow.

## Verification

Run the local tests before considering an operational rollout:

```bash
.venv/bin/pytest -q tests/test_cluster_recovery.py tests/test_raft_membership.py
bash scripts/run_local_quality.sh
```

These tests validate the in-process state machines and gates. They are not a
substitute for a staged hardware test with real mTLS identities, deliberate
fault injection, capacity monitoring, and founder review.

## References

[1] [Diego Ongaro and John Ousterhout, *In Search of an Understandable Consensus Algorithm*](https://www.usenix.org/system/files/conference/atc14/atc14-paper-ongaro.pdf).
