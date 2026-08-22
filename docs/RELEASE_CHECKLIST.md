# Reus Release Checklist

**Project:** Reus
**Founder:** Lotfi Mahiddine
**Organization:** Reulink

Use this checklist before changing repository visibility, tagging a public
release, publishing a binary, or making a public capability claim.

## Source and security

- [ ] Confirm no `.env`, credentials, certificates, memory data, audit logs,
  training data, database files, or runtime state are present.
- [ ] Run `bash scripts/run_local_quality.sh` and record the exact result.
- [ ] Review dependency, secret-scanning, and licence findings.
- [ ] Confirm that security reporting instructions are current.

## Documentation and claims

- [ ] Ensure all public GitHub documentation is English and names Reulink and
  [reulink.app](https://reulink.app) as the official project identity.
- [ ] Select and publish an explicit licence before allowing redistribution or
  contributions.
- [ ] Verify every benchmark, comparison, availability number, and model claim
  against a dated reproducible evidence record.
- [ ] State operational boundaries, including features that are intentionally
  not connected or not available.

## Governance and release control

- [ ] Obtain founder approval for the release version, contents, visibility,
  changelog, and public announcement.
- [ ] Confirm that no release workflow can publish unreviewed artifacts.
- [ ] Preserve a checksum and reproducible source archive for the release.
- [ ] Publish support and vulnerability-reporting channels before inviting
  users or contributors.
