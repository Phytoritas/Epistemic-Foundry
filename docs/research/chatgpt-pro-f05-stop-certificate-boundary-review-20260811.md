AUTHORIZED

**HASH:** Canonical schema validation is sufficient for this bounded repair. The governing schema requires all certificate fields, constrains the arrays and their members, closes additional properties, and validates `certificate_hash` only as a `sha256:<64 lowercase hex>` string; no attached higher authority requires F05 to recompute that field. The builder’s `hash_excluding(...)` behavior is construction logic, not an independently stated F05 verification contract.  

**RUN_ID:** Equality between `certificate.evolution_run_id` and the enclosing run remains intentionally F06-owned. F05 has no expected run ID parameter, while F06 explicitly performs that integration binding after F05 accepts the certificate’s internal shape. 

**MINIMUM PATCH:** In `machine.py`, import `ContractViolation` and `validate_artifact` from `...contracts`; after `_mapping`, call `validate_artifact("evolution-stop-certificate", record)`. On `ContractViolation`, set `certificate_findings["schema_errors"] = list(error.errors)` and execute none of the semantic certificate branch. On success, run the existing reason, visibility, conditions, committed-checkpoint, and preserved-work logic unchanged. The existing validity calculation and `require_valid_run()` will then deterministically map `schema_errors` to `STOP_CERTIFICATE_INVALID`. Preserve the current committed-checkpoint membership check, including the zero-return case. 

**BLOCKER:** none. This is within F05’s owned source scope and directly implements its obligation to enforce the canonical typed stop-certificate contract. 
