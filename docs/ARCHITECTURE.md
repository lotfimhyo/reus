# Reus Architecture

**Project:** Reus
**Founder:** Lotfi Mahiddine
**Organization:** Reulink

## System shape

Reus follows a clean architecture: the `domain` layer contains entities and
ports, `application` contains use cases, `infrastructure` contains adapters,
and `api` exposes the FastAPI service. `container.py` is the composition root.
This separation keeps core logic testable without binding it to a particular
model provider, storage system, or transport.

## Local execution and governance

The normal operating mode is local-first. Ollama can be selected for local
model execution; compatible remote providers are optional rather than default.
Sensitive decisions are represented as expiring, auditable approvals. Telegram
administration requires an authorized chat and a confirmation flow; it does not
convert a conversation into an unrestricted control channel.

## Distributed coordination

Nodes are identified through X.509 and Ed25519 material and communicate over
mutual TLS. Raft supplies committed leadership and replicated decision state.
Task execution uses committed leases, so a worker must obtain a lease before it
acts and records completion through the same coordination path. Peer-liveness
handling can return work from an unavailable peer through Raft.

Reus federation is intentionally metadata-only. Capability directories, trust
domains, and resource reservations exchange scoped descriptions and work
fingerprints rather than raw memory, secrets, or arbitrary task payloads.

## Explicit non-capabilities

The current codebase does not provide unattended purchasing, payment-card
storage, a live hosting-provider connector, silent cloud deployment, or a
connected remote-desktop control client. A future implementation of any of
these features must pass human approval, threat modelling, audit logging, and
integration testing before it is represented as available.
