# F05 stop-certificate final source review

Review the attached current `machine.py` after the authorized EF4-I62 repair.

Current diff:

- imports the canonical `ContractViolation` and `validate_artifact`;
- validates every non-null stop certificate against `evolution-stop-certificate` immediately after mapping;
- records deterministic `schema_errors` and performs no semantic field reads on schema failure;
- otherwise preserves the existing reason, adverse-stop, conditions, visibility, committed-checkpoint, and partial-work accounting;
- preserves the prior zero-return fix requiring every certified checkpoint to appear in committed return-edge IDs;
- leaves enclosing run-ID equality to F06;
- does not invent certificate-hash re-derivation absent a higher-authority consumer rule.

No schema, workflow, manifest, F06/W05, test artifact, evidence, or report was changed, and no tests were run.

Return only `PASS` if no material F05 correctness/contract/compatibility blocker remains. Otherwise state the concrete blocker and smallest F05-local correction. Do not request tests, evidence regeneration, or unrelated changes.
