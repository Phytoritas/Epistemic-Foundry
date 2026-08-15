# W03 follow-up: reject the graph proposal; assess one local timestamp defect

Delta from the prior turn:

- Two independent local reviews rejected the proposed `apply_passport_states(..., graph=...)` repair.
- `validate_plan` proves consistency only with a caller-supplied graph. No canonical graph snapshot/hash or Noetic-Ledger trusted-port contract binds that graph, so a caller can forge plan and graph together and replay cannot resolve the applied graph version.
- Treat that proposal as `SPEC_GAP`; do not repeat it and do not assume the graph is authoritative.
- `model_update` remains the previously established shared `SPEC_GAP`.

Assess exactly one different W03-local candidate from the already attached current source and schema:

`reassessment/contracts.py::_timestamp()` uses an uppercase-only shape regex and `datetime.fromisoformat(value.replace("Z", "+00:00"))`. Canonical JSON Schema `format: date-time` follows RFC 3339. Determine whether this wrongly rejects schema-valid lowercase `t`/`z`, year `0000`, and structurally valid offset-aware leap seconds, while still accepting or rejecting calendar/offset edges inconsistently.

Return exactly one verdict:

- `AUTHORIZED_LOCAL_REPAIR` if existing RFC3339/schema authority fully determines a W03-only fix; or
- `SPEC_GAP` if any required timestamp semantics are not already canonical; or
- `NONE` if the current implementation is already contract-correct.

If authorized, freeze exact accepted semantics and the smallest source-only hunk. Preserve original timestamp bytes/case in hashes, allow no normalization, add no external leap-second history table, preserve existing `TIMESTAMP_INVALID`, and do not touch tests, schemas, workflows, reports, or the unrelated dirty `span`/`decision` and seed-validation hunks.
