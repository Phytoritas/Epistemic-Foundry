# F05 typed stop-certificate boundary review

Review one narrow F05 production defect against EF4-I62 and the attached current sources.

`evaluate_run()` currently converts a caller-supplied stop certificate to a mapping and manually inspects only reason, conditions, visibility, checkpoint, and partial-work arrays. It never validates the canonical `evolution-stop-certificate` schema. A certificate missing required `certificate_id`, `evolution_run_id`, or `certificate_hash`, or with invalid array/member types, can therefore produce `report["valid"] == True`; `require_valid_run()` then accepts it.

Important current-state constraints:

- `machine.py` already has an unrelated one-line user change: a certified checkpoint must be in committed return IDs even when the run has zero returns. Preserve it.
- F06 intentionally owns comparison of `certificate.evolution_run_id` with the enclosing run ID; F05's public `evaluate_run` signature has no expected run ID.
- The canonical builder computes `certificate_hash = hash_excluding(certificate, "certificate_hash")`, then calls `validate_artifact`.
- F05's existing report/require split should remain: invalid certificates should become a deterministic certificate finding and then the existing `STOP_CERTIFICATE_INVALID`, not leak a raw `ContractViolation` or unrelated exception.
- Do not modify schemas, workflows, manifests, F06/W05, tests stored under `artifacts/`, or evidence/report files.

Proposed F05-local production patch in `machine.py`:

1. Import `ContractViolation` and `validate_artifact` from the canonical contracts package.
2. After `_mapping`, validate `record` against `evolution-stop-certificate`.
3. On `ContractViolation`, set a stable `schema_errors` finding from `error.errors` and skip all semantic field processing that could raise on malformed values.
4. On schema success, keep the current reason/conditions/visibility/committed-checkpoint/preserved-work logic unchanged.
5. Let `require_valid_run` map `schema_errors` through its existing `STOP_CERTIFICATE_INVALID` path.

Answer:

- `AUTHORIZED` or `SPEC_GAP`.
- Is canonical schema validation sufficient for this repair, or must F05 also re-derive `certificate_hash` to satisfy an existing attached authority? Do not invent new hash semantics merely because the field is named hash.
- Confirm whether run-ID equality remains intentionally F06-owned.
- List only concrete material blockers or the exact minimum patch shape.

Do not request test execution, evidence regeneration, artifact edits, or unrelated refactors.
