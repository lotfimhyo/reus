# Security Policy

**Project:** Reus
**Founder:** Lotfi Mahiddine
**Organization:** Reulink

## Reporting a vulnerability

Do **not** publish vulnerabilities, proof-of-concept exploits, credentials, or
private user data in a public issue. Send a concise private report to
**Contact@reulink.app** with the affected version or commit, reproduction steps,
impact, and any safe mitigation you identified.

We will acknowledge a well-formed report, assess impact, and coordinate a fix
before public disclosure when practical. Do not test against systems you do not
own or have explicit permission to assess.

## Security boundaries

Reus treats the following as sensitive: environment files, API and Telegram
tokens, X.509 keys and node identities, local memory, governance/audit records,
training data, cloud-provider access, and remote-control session material.
Never add them to commits, issue attachments, logs, model prompts, or external
benchmarking services.

## Supported development surface

The current support target is the latest repository main branch while the
project remains in pre-publication. Deployment connectors, provider purchases,
and remote-device control are intentionally not enabled as public production
features.
