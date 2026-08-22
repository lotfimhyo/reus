# GitHub Actions Support Request: Orphaned `BuildFailed` Workflow

**Project:** Reus
**Founder:** Lotfi Mahiddine
**Organization:** Reulink
**Repository:** `lotfimhyo/reus`
**Prepared:** 2026-08-22

## Summary

The repository has an orphaned GitHub Actions workflow registry entry. It
creates `startup_failure` runs before any job is created, even when a known
valid workflow is dispatched manually. This appears to be a GitHub-side
workflow-registry problem rather than an error in the repository YAML.

## Evidence

| Item | Observed value |
| --- | --- |
| Orphan workflow ID | `340027799` |
| Orphan workflow path | `BuildFailed` |
| Orphan workflow name | Empty |
| Orphan workflow state | `deleted` |
| Affected manual quality run | `32574673059` |
| Affected push run | `32574633045` |
| Failure conclusion | `startup_failure` |
| Jobs created | `0` |
| Active Reus workflow IDs | `340027782` through `340027785`, plus Dependabot `340027826` |

The orphan workflow resolves through the workflow API but is absent from the
normal active workflow list. Repository Actions are enabled with
`allowed_actions: all`. The intended Reus quality gate was dispatched manually
from `main` and still ended with `startup_failure` before jobs or logs existed.

## Requested action

Please remove or repair the stale workflow registry entry with ID `340027799`
for `lotfimhyo/reus`, so that normal repository workflows can create jobs and
check runs. The repository intentionally does not contain a workflow file named
`BuildFailed`; recreating or renaming a workflow file should not be required.

## Relevant public precedent

GitHub Community discussion
[“Orphaned deleted Actions workflow (path BuildFailed)”](https://github.com/orgs/community/discussions/204465)
describes the same pattern: a deleted, GitHub-side workflow entry yields
zero-job `startup_failure` runs and requires platform-side intervention.
