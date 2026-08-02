# C01 attempt 0005 shared-contract review

Status: `SPEC_GAP (C01-SG004)`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`. The product-owner execution contract prohibits
Fleet and subagents. This is a separate primary-session review of the captured
authority, manifest ownership, test oracles, and proposed classification; it is
not external actor-independent certification and does not waive any gate.

## Outcome

The K01 HumanDecision is authentic and complete enough to define the new
`DocumentRegistrationRequest`, immutable `DocumentRegistration`, final
`DocumentManifest` lineage, and the target count of 126 schemas and 126
examples. The active successor development manifest correctly grants C01 the
canonical schema/example/OpenAPI/document paths.

C01 nevertheless cannot lawfully start the product change. Eight active
authority or acceptance paths retain 124-era assumptions:

1. `MASTER_SPEC.md` still declares 124/124 and is owned only by A01.
2. `manifests/acceptance_matrix.yaml` still gates on 124/124 and is owned only
   by F01.
3. `tests/contracts/openapi/test_scientific_contracts.py` fixes four 124-count
   assertions and has no manifest owner.
4. `tests/contracts/openapi/test_openapi_contract.py` classifies
   `DocumentRegistrationRequest` as transport-only, fixes the schema count at
   124, and tests the obsolete `source_uri`/`uploaded_artifact_id` shape; it has
   no manifest owner.
5. `tests/test_contracts.py` fixes the registry count at 124 and has no owner.
6. `tests/test_cli.py` fixes the loaded-schema count at 124 and has no owner.
7. `tests/test_f01_epistemic_work_classifier.py` reads the root trees and fixes
   them at 124/124; F01 owns it but no F01 correction occurs before C04.
8. `tests/packaging/test_canonical_registry.py` is B04-owned, but B04 is fixed
   after C04 even though C04 must run the full Python suite against the stale
   package projection.

The generated C02 files, C03 migration documentation, C01 API documentation,
and B04 snapshot have known owners and are correctly deferred to their named
stages. `docs/verification_report.md` is separately recorded as a stale report,
not treated as live C01 acceptance authority.

## Adversarial checks

- Treating the HumanDecision as implicit permission to edit every affected
  test would violate its exact C01 write scope.
- Partially adding the two schemas would make the current C01 targeted oracle
  false immediately and would make the fixed C04-before-B04 full-suite gate
  unreachable.
- Calling the resulting failures ordinary implementation defects would hide
  the missing correction owner and timing authority.
- Calling this BLOCKED would be inaccurate because all evidence and tools are
  local and available.
- Weakening counts, skipping tests, hand-editing generated outputs, or treating
  the derived package snapshot as authority is forbidden.

The current pre-implementation contract baseline remains 124 schemas, 124
examples, and 66/66 targeted OpenAPI contract tests. The four newly authorized
schema/example paths are all absent, proving that no partial C01 product change
was applied by this attempt.

## Required decision

The minimum resolving HumanDecision must name the correction owner and exact
write scope for all eight paths above, authorize the two higher authority count
changes, and put the oracle/projection corrections before the gate that consumes
them. It must state explicitly whether B04 projection moves before C04 for this
attempt-level repair or whether C04 receives a bounded projection-pending gate
with mandatory post-B04 reconciliation. Broad `tests/**`, `docs/**`, schema
weakening, history rewriting, and silent test exclusion remain forbidden.

## Decision

`C01-0005` is `SPEC_GAP`, not PASS, FAIL, or BLOCKED. No canonical product file
is modified. C02 and all later packages remain waiting. Existing dirty-worktree
content and C01-0001 through C01-0004 remain preserved.
