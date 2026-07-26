# Bootstrap with Codex

## Place the bundle

Copy this specification bundle to the intended repository root. Do not overwrite an existing `AGENTS.md` without merging authority intentionally.

## Preflight prompt

```text
Read AGENTS.md and MASTER_SPEC.md. Do not edit yet.

Inspect repository status, current instruction sources, available runtimes,
and the development manifest. Validate JSON schemas and workflow DAGs.
List dependency-ready work packages, shared-resource conflicts, missing
external prerequisites, and pre-existing user changes. Recommend exactly
one first package. Do not implement it in this turn.
```

## Implement A01

```text
Execute work package A01 only.

Treat MASTER_SPEC.md and development_manifest.yaml as authoritative.
Preserve all pre-existing changes. Keep edits inside A01 write_scope.
Add only the minimal repository scaffold and verification commands required
by A01. Run every required check available in this environment. Request an
independent review, but do not allow the author to approve itself.
Return the WorkPackageReport from AGENTS.md and distinguish executed checks
from checks that were unavailable.
```

## Continue

Use one prompt per dependency layer or let a Parent Integrator dispatch bounded subagents. Never give several write agents a shared schema/API file.

## Recommended verification prompt

```text
Review work package A01 read-only against its exact authority and exit
criteria. Inspect the actual diff and command artifacts. Report only
contract, correctness, security, reproducibility, or test-evidence defects
with severity and file:line. Do not modify files.
```
