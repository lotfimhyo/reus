# Reus

**Founder:** Lotfi Mahiddine
**Organization:** [Reulink](https://reulink.app)
**Project home:** [reulink.app](https://reulink.app)

Reus is a **local-first, human-governed distributed AI system**. It combines a
FastAPI core, local-model execution, durable governance controls, and optional
cluster coordination so that useful automation can remain inspectable, bounded,
and under explicit human authority.

> Reus is not a claim of consciousness or autonomous authority. It is an
> engineering system designed to propose, execute within defined limits, and
> request human approval for sensitive operations.

## Project status

This repository is in a **private pre-publication phase**. The core is tested
locally and the public contribution surface is being prepared, but the project
has not yet selected an open-source licence or opened public contributions.
See [LICENSE_STATUS.md](LICENSE_STATUS.md) before copying, redistributing, or
using this code outside an authorized review.

## Why Reus

| Principle | What it means in practice |
| --- | --- |
| Local-first | Ollama, sensitive memory, and governance records remain local by default. External model providers and cloud services are opt-in. |
| Human-governed | Telegram approvals are short-lived, bound to an approved administrative chat, auditable, and safe to cancel after restart. |
| Distributed by design | Nodes use X.509 identity, mutual TLS, Raft-backed decisions, and committed task leases rather than unauthenticated worker coordination. |
| Honest evaluation | Reus does not publish “best model” claims without versioned, reproducible evidence. See [the public-claims policy](docs/public_claims_evidence.md). |

## Current capabilities

The repository contains working, tested foundations for local task execution,
Ollama and compatible API model routing, governed capability evolution,
durable local memory, Telegram administration, and a modular FastAPI service.
Its distributed core includes mTLS node identity, controlled membership,
Raft-led consensus, replicated leases for task coordination, peer-liveness
handling, and metadata-only federation primitives. Hosting governance can
prepare a one-time, expiring authorization and present offer details through
Telegram; it does **not** store card data, purchase hosting, create resources,
or control a developer device.

For a concise technical map, read [Architecture](docs/ARCHITECTURE.md). For the
current boundaries and public-claim requirements, read
[Release checklist](docs/RELEASE_CHECKLIST.md) and
[Public claims evidence](docs/public_claims_evidence.md).

## Quick start

Reus is intended to start locally and conservatively. It does not install
Ollama, enable Telegram, connect a cloud account, or expose a network port
without an explicit operator decision.

```bash
git clone https://github.com/lotfimhyo/reus.git
cd reus
bash scripts/reusctl.sh install
bash scripts/reusctl.sh doctor --strict
bash scripts/reusctl.sh start-core
```

Run the local quality gate with:

```bash
bash scripts/run_local_quality.sh
```

The most recently recorded local gate result was **501 passing tests and five
passing subtests**. It intentionally excludes only integration checks requiring
separately provisioned PostgreSQL, Redis, or Alembic services.

## Security and data boundaries

Never commit `.env` files, model keys, Telegram tokens, certificates, node
identities, memory stores, audit logs, or production data. Reus is designed so
that sensitive memory and secrets stay inside the local core by default.

Read [SECURITY.md](SECURITY.md) before reporting a vulnerability and
[GOVERNANCE.md](GOVERNANCE.md) before proposing work that affects permissions,
network exposure, cloud infrastructure, model training, or safety controls.

## Community preparation

Reus welcomes rigorous engineering feedback once the project is opened for
public contribution. Until a licence is selected and visibility is changed,
please do not open pull requests or redistribute the repository. The intended
standards are documented in [CONTRIBUTING.md](CONTRIBUTING.md) and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Official identity

Reus is a Reulink project. The official website is
[reulink.app](https://reulink.app); GitHub repositories, releases, and public
announcements must link to that domain and must not imply unverified benchmarks,
vendor partnerships, or autonomous purchasing capability.

## Contact

For project and security contact, use **Contact@reulink.app**. Do not include
secrets, private prompts, credentials, or exploit details in public issues.
