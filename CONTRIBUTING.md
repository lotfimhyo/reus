# Contributing to Reus

**Project:** Reus
**Founder:** Lotfi Mahiddine
**Organization:** Reulink

## Contribution status

Reus is currently private and pre-publication. External pull requests will be
enabled only after the founder selects a licence and opens the repository.
This document defines the standards that will apply at that point.

## Engineering principles

Contributions must preserve local-first behavior, least privilege, explicit
human approval for sensitive actions, and reproducible tests. Do not represent
an idea, mock, or planned connector as production behavior. Describe both the
capability added and its operational boundary.

## Before submitting a change

1. Open an issue or discussion for significant architecture, security,
   distributed-systems, model-training, or product changes.
2. Keep one concern per pull request and include tests for behavior changes.
3. Run `bash scripts/run_local_quality.sh` and state the result in the pull
   request description.
4. Update English documentation when an operator-visible behavior, environment
   variable, trust boundary, or safety property changes.
5. Never add secrets, real user data, model weights without a compatible
   licence, credentials, certificates, audit records, or generated runtime
   state.

## Review requirements

Changes affecting permissions, network exposure, Telegram approval flows,
provider integrations, infrastructure purchasing, remote-device control, or
distributed consensus require founder approval. Security fixes should follow
[SECURITY.md](SECURITY.md) rather than public disclosure while unpatched.

## Commit and pull-request quality

Use clear, imperative commit subjects. Explain the motivation, security impact,
test evidence, and documentation impact. A passing test suite is necessary but
does not replace architectural review.
