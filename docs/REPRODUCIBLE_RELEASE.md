# Reproducible Source Archive Procedure

**Project:** Reus
**Founder:** Lotfi Mahiddine
**Organization:** Reulink

This procedure prepares a source-only archive for founder review. It does not
publish a GitHub Release, alter repository visibility, upload a binary, create
infrastructure, or transmit credentials.

## Build and verify

From a reviewed checkout of the intended commit, run:

```bash
bash scripts/run_local_quality.sh
bash scripts/package_release.sh ../Reus_release_lotfi_Mahiddine.zip
sha256sum ../Reus_release_lotfi_Mahiddine.zip
unzip -t ../Reus_release_lotfi_Mahiddine.zip
```

The packaging test is part of the local quality gate. It confirms that the
archive contains source, tests, and conservative startup material while
excluding local credentials, certificates, private keys, runtime state, local
database files, audit data, virtual environments, and build caches.

## Evidence to retain

Record the Git commit SHA, exact quality-gate result, SHA-256 checksum,
release-builder operating system, Python version, and the date. Store this
evidence in a founder-controlled release record before publishing any tag or
archive.

## Boundary

An archive passing this procedure is **not** approval to publish. Complete
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), select a licence, resolve any
critical security findings, and obtain explicit founder approval before
changing repository visibility or inviting external contributions.
