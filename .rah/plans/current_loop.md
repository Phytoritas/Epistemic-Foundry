# Current Loop

## Earliest Restart Point
Stage 0. Source intake for the Epistemic Foundry v4 spec bundle

## Read First
- `AGENTS.md` (Epistemic Foundry v4 bundle; authoritative)
- `MASTER_SPEC.md`, then `manifests/development_manifest.yaml`
- `.rah/state/status.json`
- `.rah/state/gates.json`
- `.rah/memory/wakeup.md`

## Next Actions
Done during setup (2026-07-27): doctor + status surfaces run, Memento context/recall
hydrated and fed back, repo-local `AGENTS.md` confirmed present.

1. Register the real goal and source binding:
   `rah run <repo-root> --goal "<objective>" --source MASTER_SPEC.md`
   (or the specific work package from `manifests/development_manifest.yaml`).
2. Work coverage rows one at a time; record evidence/validation/semantic/provenance/negative-test.
3. Perform current-system recon against the v4 bundle and update `00_workspace_audit.md`.
4. Keep implementation blocked until acceptance, coverage, validation, review, and closeout are honest.

## Repo-specific constraints
- The bundle is a SPEC_BUNDLE / REFERENCE_BLUEPRINT: do not claim runtime, search,
  ledger, MCP, or UI components are implemented merely because contracts exist.
- Bundle authority order (`MASTER_SPEC.md` first) outranks the harness overlay at
  `.rah/runtime/AGENTS.overlay.md`; conflicts stop with `SPEC_GAP`.
- `PACKAGE_MANIFEST.json` verifies clean against `MANIFEST.sha256`; keep it that way.
