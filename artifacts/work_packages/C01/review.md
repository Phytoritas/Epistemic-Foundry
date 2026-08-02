# C01 contract review record

Status: `SPEC_GAP_WITH_RECORDED_PROCEDURE_DEVIATION`

Review mode: `USER_AUTHORIZED_SELF_REVIEW`

The user prohibited subagents and authorized the independent-review steps to
be handled directly. The primary author therefore performed the contract
review. This is the primary author's direct review and is not independent
assurance. The procedure deviation cannot waive a missing authority contract.

Reviewed authority bindings:

- `MASTER_SPEC.md`: `43fbb63f2b4cf697d10be15521a4d8ddaf123fb822b4d563ba4e026ed82cf3f3`
- `docs/api_contract.md`: `31b202badad974828aa213bdb1a9f0bfddfb1e2f1bc1626d84fa0cf7be54cebb`
- `docs/plugin_ux_cli_and_mcp.md`: `2ee67657a192e8e1086949ab689e4a81d656dc9c86f943791b51c97eb2279b7b`
- `docs/schema_evolution.md`: `c940fdbc22c55d72291be0f567d739ad7e4f3fcfb1e34cc51e6d995b5c49788b`
- `docs/inherited_v3_master_spec.md`: `c3204e8fc09aaac64f88bcd5bc6ddb4a17564f266e3551041c461e37d0c5219c`
- canonical schema set: `817ee24563255b92dce464dfbd457d4d54bd81b22f2ff05e409a5de8f000cc8e`

Review confirmed:

1. All 124 existing canonical JSON Schemas pass Draft 2020-12
   meta-validation, have 124 unique `$id` values, and validate all 124 mapped
   canonical examples.
2. C01 requires both `schema_meta_validation` and `openapi_validation`; the
   schema result alone cannot satisfy the package.
3. `docs/api_contract.md` says canonical endpoint details are in
   `MASTER_SPEC.md` section 18, but that section is `Parent acquisition` and
   contains no HTTP paths, methods, request shapes, responses, or status codes.
4. The current and inherited UX/API prose defines `/api/v1`, authentication,
   idempotency, pagination, errors, long-running handles, source rendering,
   OpenAPI authority, CLI commands, and MCP tools. It does not define a
   canonical REST resource and operation inventory.
5. A repository-wide canonical-document search found zero method/path
   definitions. The sole `/api/v1/runs/RUN-...` occurrence is an example
   `status_url`, not a route declaration and not enough to infer its method or
   response contract.
6. `manifests/144_lens_audit_matrix.yaml` expects the phrase `REST API v1` in
   `MASTER_SPEC.md`, but that expected token is absent. This reinforces rather
   than repairs the missing higher-order contract.
7. `MASTER_SPEC.md` section 43 and `docs/migration_v3_to_v4.md` preserve v3
   domain artifacts and workflows, but neither supplies the missing HTTP
   transport semantics.
8. Creating plausible paths from CLI or MCP names would duplicate or invent
   transport authority and could make incompatible choices about mutation,
   revisions, pagination, asynchronous runs, authorization, and errors.
9. No `schemas/**` file was changed and no `openapi/**` file was created. This
   is the required fail-closed behavior, not an implementation claim.
10. The bundle-wide validator currently reports six pre-existing
    `PACKAGE_MANIFEST` mismatches from the dirty worktree. Its schema subsection
    still reports 124 schemas, 124 unique IDs, and 124 valid examples. Those
    unrelated inventory mismatches are not reclassified as a C01 defect.

Finding: one blocking `SPEC_GAP`.

Required resolution:

- Correct the endpoint-authority reference and define a versioned REST v1
  operation inventory with method/path, canonical request/response schema
  mappings, status and error responses, authorization, idempotency scope,
  pagination, expected-revision behavior, and asynchronous run semantics.
- After that decision, author OpenAPI 3.1 under `openapi/**`, reuse canonical
  JSON Schema references without duplicating domain enums, add deterministic
  positive and negative validation, and rerun C01.

Decision: C01 is not integrated. Packages depending on C01 are not
dependency-ready. This report does not claim that an OpenAPI server or REST API
exists.
