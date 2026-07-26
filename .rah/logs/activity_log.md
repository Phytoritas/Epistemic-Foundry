# Harness Activity Log

## Boot Event
- time_utc: 2026-07-26T15:52:13+00:00
- mode: auto-bootstrap
- scope: project
- event: bootstrap_scaffold_initialized
- session_id: epistemic-foundry#adhoc:bootstrap
- note: No repo-local AGENTS.md detected at bootstrap root.

## Later Updates
Append dated entries here instead of replacing history.

### 2026-07-27 setup session
- event: harness_setup_verified
- package: `verify --tier smoke` pass (manifest / compile / byte-contracts); `admin parity` in_parity (53 managed files, codex canonical vs claude mirror).
- tests: full package pytest run file-by-file from outside the package root: 354 passed, 4 skipped, 0 failed.
- incident: pytest executed with the package root as CWD created `.rah/` and `.pytest_cache/` inside the skill package, breaking the closed package manifest (unmanaged_extra: .rah) and causing 6 false failures with "refusing state-mutating dispatch". Both directories were moved to a temp quarantine (bytes preserved), after which the suite passed clean.
- memory: Memento `context()` hydrated 23 fragments; caseMode `recall()` (searchEventId 88182) returned 3 prior RAH harness cases; `tool_feedback` 3755 recorded. Ledgers under `.rah/memory/` and freshness timestamps in `.rah/state/` updated.
- repo: the Epistemic Foundry v4 spec bundle landed at the root during this session. Its own `AGENTS.md` is authoritative (`MASTER_SPEC.md` > `manifests/*` > schemas/workflows > role_registry > AGENTS.md); the harness overlay at `.rah/runtime/AGENTS.overlay.md` stays advisory. `PACKAGE_MANIFEST.json` verifies clean against `MANIFEST.sha256`.
- correction to the boot event note above: a repo-local `AGENTS.md` is now present at the bootstrap root.
- state: no RALPH goal registered yet; implementation gate intentionally blocked until `rah run` binds a goal and source.
