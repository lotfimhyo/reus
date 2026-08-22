# Reus Local Quick Start

**Project:** Reus
**Founder:** Lotfi Mahiddine
**Organization:** Reulink

## Prerequisites

Use a supported Linux or macOS shell with Python available. Reus can operate
with local defaults; Ollama, Telegram, Kimi-compatible APIs, Supabase, Redis,
PostgreSQL, and cloud services are optional and require explicit configuration.

## Install and validate

```bash
bash scripts/reusctl.sh install
bash scripts/reusctl.sh doctor --strict
bash scripts/run_local_quality.sh
```

`install` creates a local virtual environment and an environment file without
overwriting an existing secret. Review the generated `.env` locally; do not
commit it.

## Start the local core

```bash
bash scripts/reusctl.sh start-core
```

Use the project’s documented configuration values to enable an optional local
Ollama executor or a controlled administrative integration. Do not expose an
admin endpoint, join a node, enable an external provider, or create cloud
infrastructure until you have reviewed the relevant configuration and security
boundary.

## Quality gate

```bash
bash scripts/run_local_quality.sh
```

The quality gate exercises local logic and intentionally excludes only tests
that need separately provisioned integration services. Treat an excluded test
as unverified until it has run against its required isolated service.
