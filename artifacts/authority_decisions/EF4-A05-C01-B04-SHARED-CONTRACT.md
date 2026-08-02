# EF4 A05 / C01 / B04 Shared-Contract Decision

- Decision ID: `HD-EF4-A05-C01-B04-20260727-001`
- Subject: `EF4-A05-C01-B04-SHARED-CONTRACT`
- Authority: `HUMAN-product-owner` (`product_owner`)
- Effective scope: prospective attempts only
- Non-mutation acknowledgement: `true`

## 1. Historical integrity and execution order

- R1: Preserve the prior A05, C01, and B04 `SPEC_GAP` results as valid immutable history; do not delete them or relabel them `PASS`.
- R2: Preserve RAH evidence `E0035`, terminal `blocked` state, iteration `24`, generation `000032-10d829ad`, prior reports, commands, reviews, and the dirty worktree.
- R3: Record new work as new attempts or revisions that supersede, but do not overwrite, prior results.
- R4: Execute serially in this exact order: authority decision and limited manifest correction; A05; C01; B04; full development-DAG recomputation; then the next dependency-ready packages under the existing manifest.
- R5: Do not use Fleet or subagents. Keep all work and review activity in the primary session until the three shared contracts have passed their required review gates.
- R6: Do not infer omitted behavior or expand authority beyond this decision.

## 2. Authorized development-manifest correction

- R7: Set C01 `depends_on` to `A04` and `A05`.
- R8: Add `docs/api_contract.md`, `tests/contracts/openapi/**`, and `artifacts/work_packages/C01/**` to C01 write scope, retaining its existing `schemas/**` and `openapi/**` scope.
- R9: Set B04 `depends_on` to `B02`, `B03`, and `C01`.
- R10: Grant B04 bounded write scope for `pyproject.toml`, the actual canonical package-resource projection, the one existing canonical registry implementation, deterministic registry build scripts, packaging tests, and B04 evidence artifacts.
- R11: The actual package root is `src/epistemic_foundry`; therefore use `src/epistemic_foundry/_canonical/**` and `src/epistemic_foundry/contracts/registry.py` as the authorized equivalents of the proposed `python/epistemic_foundry/**` paths.
- R12: Do not create a duplicate registry. Record the equivalent actual path in the B04 report.
- R13: Treat this manifest edit as the product-owner shared-contract correction that precedes C01 and B04, not as either package expanding its own scope.

## 3. A05 — evolution authority and promotion charter

### 3.1 EvolutionRunSpec resolution

- R14: A string ID in `EvolutionRunSpec` is not a pin. Before execution, resolve every reference to a tuple containing `logical_id`, exact version or revision, `sha256:<64 lowercase hex>` content hash, resolver identifier and version, resolved artifact locator, `resolved_at`, authority/source class, and reproducibility class.
- R15: Keep one existing EvolutionRunSpec schema and require `resolved_refs` to seal the base RunSpec, schema bundle, workflow ID/version/hash, policy bundle, corpus/evidence snapshot, ontology and DomainPack, evaluator bundle, holdout manifest, operator registry, prompt bundle, model-routing policy and provider-adapter versions, statistical plan, selection policy, stop policy, replication policy, archive/niche policy, budget envelope, execution environment/toolchain manifest, and optional external-backend manifest.
- R16: An external backend must have an exact source commit, immutable package digest, or immutable container digest.
- R17: Reject floating `main`, `latest`, unpinned tags, version ranges, and unversioned provider aliases.
- R18: If a provider supplies no model weight hash, record the provider, exact exposed model identifier, exposed snapshot/revision when available, adapter version/hash, decoding parameters, capability-report hash, and reproducibility class. If no immutable revision exists, disclose `provider_versioned_not_byte_pinned` and apply its replication ceiling.

### 3.2 Hashing and sealing

- R19: Hash JSON using deterministic RFC 8785 JCS-equivalent canonical JSON serialized as UTF-8.
- R20: Exclude `spec_hash` itself when calculating `spec_hash`; preserve order for order-semantic arrays and apply schema-declared canonical sorting to set-semantic arrays.
- R21: Calculate the final `spec_hash` only after all resolved references are included.
- R22: After sealing, do not change references, evaluator, holdout, policy, statistical family, or prompt bundle under the same `evolution_run_id`; create a new EvolutionRunSpec revision and new `evolution_run_id` instead.
- R23: Classify hash mismatch, sealed-artifact mutation, or tampering as `FAIL`; a clear reference whose artifact, credential, or backend is unavailable as `BLOCKED`; an undefined version/hash contract as `SPEC_GAP`; and never resolve a floating reference to an arbitrary current value.

### 3.3 Promotion vocabulary and levels

- R24: Restrict `requested_level` and `granted_level` to `INBOX`, `CANDIDATE`, `LITERATURE_GROUNDED`, `VALIDATION_SCREENED`, `EMPIRICALLY_TESTED`, and `REPLICATED`. `BLOCK` is a promotion decision, not a level.
- R25: `INBOX` means the falsifier, scope, or atomic claim is incomplete; the object may be stored but is not elevated to Parliament or validation.
- R26: `CANDIDATE` requires valid schema, lineage, falsifiability, and provenance and implies neither scientific support nor novelty.
- R27: `LITERATURE_GROUNDED` requires support/counter/null/boundary/method/prior-art lanes, a valid SearchCompletenessCertificate, scope/method/evidence-dependency audits, and Evidence Parliament adjudication.
- R28: `VALIDATION_SCREENED` requires a qualified EvaluatorBundle, public/hidden/OOD/adversarial/metamorphic stages, leakage audit, and adaptive-search statistics; it is not empirical confirmation.
- R29: `EMPIRICALLY_TESTED` requires real measurement, experiment, or independent-data validation under a preregistered ValidationPlan, plus ActionIntent, execution receipt, Result, and reconciliation; it does not imply independent replication.
- R30: `REPLICATED` requires an independent executor, preregistered ReplicationPlan, independence audit, a `REPLICATED` result, Parliament, attestation, and all required human/policy approvals.

### 3.4 Canonical deterministic gate order

- R31: Fix the gate order to `G00_PIN_RESOLUTION`, `G01_POLICY_AUTHORITY`, `G02_EVALUATOR_HOLDOUT_FIREWALL`, `G03_SCHEMA_LINEAGE_COUNT`, `G04_SOURCE_PROVENANCE`, `G05_SEARCH_COVERAGE`, `G06_METHOD_SCOPE_DEPENDENCY`, `G07_VALIDATION_LEAKAGE`, `G08_ADAPTIVE_STATISTICS`, `G09_RED_QUEEN`, `G10_REPLICATION_CEILING`, `G11_PARLIAMENT`, `G12_INDEPENDENT_ATTESTATION`, `G13_HUMAN_POLICY_APPROVAL`, and `G14_ATOMIC_PROMOTION_COMMIT`.
- R32: G00 verifies EvolutionRunSpec and every resolved-reference version and hash.
- R33: G01 verifies PolicyBundle, capabilities, approval policy, and non-waivable gates.
- R34: G02 requires an immutable evaluator, `candidate_access=false`, and no candidate/model/prompt/backend access to the holdout.
- R35: G03 validates candidate schema and parent lineage and reconciles expected/generated/evaluated/persisted/failed/cancelled/missing counts.
- R36: G04 verifies source spans, artifact receipts, evidence links, and trust labels.
- R37: G05 covers support/counter/null/boundary/method/novelty lanes, distinguishes `UNSEARCHED` from `SEARCHED_NONE`, and forbids absence or novelty claims beyond searched scope.
- R38: G06 verifies measurement comparability, scope overlap, shared sample/dataset/preprint dependencies, method vetoes, and promotion ceilings.
- R39: G07 verifies evaluator qualification, hidden/OOD/adversarial/metamorphic results, leakage, and evaluator gaming.
- R40: G08 verifies the sequential-testing ledger, multiple-testing adjustment, selective-inference report, winner-selection path, and holdout consumption.
- R41: G09 applies the strongest relevant and reproducible counterexample, null, confounder, method, or OOD challenge.
- R42: G10 calculates the replication requirement and ceiling for the requested level.
- R43: G11 verifies blind briefs, prosecutor/method/scope/causal/novelty/dependency audits, strongest counterevidence, minority report, and attempts to override deterministic gates.
- R44: G12 requires a PASS from an attestor independent of candidate generation, implementation, first adjudication, mutable prompt lineage, and promotion commit authority, reviewing only the sealed structured pack.
- R45: G13 requires either a policy finding of `NOT_REQUIRED` or a valid ApprovalRecord and verifies the necessary human authority.
- R46: G14 uses expected-revision compare-and-swap and atomically commits ActionIntent, CapabilityLease, EffectReceipt, ArtifactReceipt, EventRecord, a new PromotionDecision, and a new Passport revision.
- R47: Every gate emits a GateDecision with `input_hash`, `decision_hash`, `policy_version`, and evidence IDs.
- R48: Never waive a non-waivable gate. Human approval cannot turn evaluator mutation, hidden-holdout leakage, missing source provenance, self-approval, scalar-only promotion, missing count reconciliation, missing adaptive-search statistics, fabricated/missing receipts, or failed integrity checks into PASS.

### 3.5 Replication ceiling

- R49: If replication is not run or is `BLOCKED`, cap the grant at `EMPIRICALLY_TESTED` and require `CONDITIONAL` or `UNDERDETERMINED`.
- R50: If replication is `PARTIAL` or `INCONCLUSIVE`, cap at `EMPIRICALLY_TESTED` and require unresolved issues and limitations.
- R51: If replication is `FAILED`, forbid `REPLICATED`; if the core empirical effect failed, cap at `LITERATURE_GROUNDED` and make PromotionEffect `LOWER` or `BLOCK`.
- R52: A `REPLICATED` result permits `REPLICATED` only if every other gate, Parliament, attestation, and approval also passes.
- R53: A purely formal/deductive artifact may use a policy-declared replication-not-applicable class only with two independent formal-verifier paths or a formal verifier plus independent attestor; never apply this exception to ordinary empirical claims.

### 3.6 Parliament, attestation, and approval

- R54: Evolution Chamber, candidate generator, mutation model, parent selector, and Shinka backend have no promotion authority.
- R55: Every promotion above `CANDIDATE` requires Evidence Parliament; `VALIDATION_SCREENED` or higher also requires independent attestation.
- R56: The attestor receives only sealed EvolutionRunSpec/resolved references, candidate genome/lineage, Evidence Pack, SearchCompletenessCertificate, FitnessVector and receipts, deterministic GateDecisions, statistical reports, Red Queen result, replication result, Adjudication, MinorityReport, and unresolved limitations—not the persuasive conversation.
- R57: Require human approval for E4/E5 work, high-risk or controlled external effects, hidden-holdout unblinding, external release of `EMPIRICALLY_TESTED` or `REPLICATED` results, policy/evaluator change proposals, non-local data export, and publication-grade novelty claims.
- R58: Low-risk `CANDIDATE` or `LITERATURE_GROUNDED` promotion may use policy approval only when PolicyBundle explicitly permits it.
- R59: Never silently treat a missing ApprovalRecord as an empty array. When approval is unnecessary, leave a G13 Policy GateDecision proving it.

### 3.7 Receipt-bound workflow, retry, and immutability

- R60: Execute promotion only in this order: request-promotion ActionIntent; seal requested level and candidate revision; build the FORGE phase-E promotion pack; verify every required artifact and receipt; run G00–G10; run sealed Parliament adjudication; run G11; run G12; recheck G10; run G13; calculate granted level; create commit-promotion ActionIntent; acquire short-lived `promotion:commit` CapabilityLease; CAS the candidate/passport revision; record PromotionDecision and Passport revision; append the Noetic Ledger EventRecord; record EffectReceipt and ArtifactReceipt; complete G14.
- R61: Form the idempotency key from at least `candidate_id + candidate_revision + requested_level + promotion_pack_hash + policy_bundle_hash`.
- R62: Return the existing result for the same idempotency key and request hash; report conflict for the same key with a different request hash.
- R63: After a crash, do not infer success without EffectReceipt; reconcile external state and ledger before retrying or deciding `FAIL`/`BLOCKED`.
- R64: Never overwrite an existing Passport or PromotionDecision. Promotions and demotions are new immutable revisions.

### 3.8 A05 completion evidence

- R65: A05 must produce the authority contract, EvolutionRunSpec resolution table, requested-level gate applicability matrix, promotion-ceiling matrix, approval matrix, crash/retry/reconciliation sequence, negative tests, and independent review evidence.
- R66: Negative requirements must cover evaluator mutation, hidden-holdout access, scalar-only promotion, self-approval, missing replication ceiling, and missing receipts.
- R67: A05 must not modify schema or runtime files; C01 implements schemas and later packages implement runtime behavior.

## 4. C01 — canonical JSON Schema and REST v1 transport

### 4.1 Authority and schema changes

- R68: Start C01 only after A05 passes.
- R69: Use OpenAPI `3.1.1`, base path `/api/v1`, canonical file `openapi/epistemic-foundry-v1.openapi.yaml`, and JSON Schema Draft 2020-12.
- R70: Existing `schemas/*.schema.json` remain authority for scientific artifacts. OpenAPI references them and does not redefine their meaning. Define transport-only envelopes in OpenAPI components.
- R71: Keep the canonical schema count at 124 absent another higher-authority decision. Generated clients belong to C02; handlers/runtime belong to U01.
- R72: Add `resolved_refs` and pin/hash semantics to EvolutionRunSpec; restrict PromotionDecision levels to A05 enums and add ceiling plus promotion-pack artifact/receipt linkage semantics; align Adjudication recommendation levels; document phase-E promotion-pack required artifact kinds in PhaseArtifactSet.
- R73: Define transport-only `RunHandle`, `RunView`, `CommandRequest`, `ApiProblem`, `CursorPageMetadata`, `DocumentRegistrationRequest`, `CandidateEnvelope`, and `ApprovalCommand` in OpenAPI components.

### 4.2 Canonical endpoint matrix

- R74: Define unauthenticated `GET /api/v1/health/live` returning minimal liveness without sensitive versions, paths, or credentials.
- R75: Define `GET /api/v1/health/ready` (`system:read`, PluginHealthReport) and `GET /api/v1/capabilities` (`system:read`, HostCapabilityReport).
- R76: Define `POST /api/v1/runs` (`run:create`, RunSpec -> 202 RunHandle), `GET /api/v1/runs` (`run:read`, cursor page of RunView), and `GET /api/v1/runs/{run_id}` (`run:read`, RunView).
- R77: Define `GET /api/v1/runs/{run_id}/events` (`run:read`) with canonical JSON cursor pagination and an ordered EventRecord SSE delivery projection.
- R78: Define pause/resume/cancel action POSTs under `/api/v1/runs/{run_id}/actions/`, each accepting CommandRequest and returning 202 RunHandle under `run:control`.
- R79: Define document registration (`POST /documents`, `document:ingest`, exactly one of `source_uri` or `uploaded_artifact_id`, no canonical multipart v1, 202 RunHandle), document lookup, claim lookup, evidence lookup, retrieval-run creation, evidence-pack lookup, and coverage-snapshot lookup with their specified document/evidence/retrieval capabilities and canonical schemas.
- R80: Define deliberation-run creation using RunSpec with `workflow_id=insight_deliberation` and adjudication lookup with the specified deliberation capabilities.
- R81: Define evolution-run creation/lookup, candidate listing/lookup, promotion request creation, PromotionDecision lookup, and Passport lookup with the specified capabilities. A promotion request carries requested level, expected candidate revision, phase-E PhaseArtifactSet artifact ID, and reason and maps server-side to `ActionIntent(request_promotion)`.
- R82: Define validation-run creation, replication-run creation, and replication-result lookup with the specified canonical plans/results and capabilities.
- R83: Define approval creation (`promotion:approve` or `action:approve`) and lookup. The server derives authority from the authenticated principal and policy; the client may not assert an arbitrary `authority_role`.
- R84: Define artifact manifest lookup and separately authorized content retrieval; locator/manifest access never implies raw-content access, and content remains subject to license, confidentiality, retention, and source-access policy.

### 4.3 Async, idempotency, concurrency, and security

- R85: Execution, search, ingest, deliberation, evolution, validation, replication, and promotion never complete in the request thread. On acceptance return 202 with `Location`, `Retry-After`, and RunHandle containing `run_id`, status, status/events URLs, submitted time, request ID, idempotency key, and input hash.
- R86: Reject schema or authorization failures before queueing. After acceptance, expose `BLOCKED`, `SPEC_GAP`, and `FAIL` as RunView terminal states and ResultEnvelope, not as retroactive HTTP failures. Scientific verdicts such as `UNDERDETERMINED`, `CONDITIONAL`, `REJECT`, and `MIXED` are not HTTP errors.
- R87: Require `Idempotency-Key` on every mutation endpoint. Same key plus same canonical request hash returns the same logical result; same key plus different hash returns 409 `IDEMPOTENCY_KEY_REUSED`.
- R88: State transitions require `If-Match` or `CommandRequest.expected_revision`; mismatch returns 412 `PRECONDITION_FAILED`. GET never changes state and query parameters cannot pause, cancel, promote, or approve.
- R89: Support local plugin sessions, team/OIDC bearer tokens, and service automation credentials through OpenAPI `LocalSession` and `BearerAuth` schemes.
- R90: Scientific role names do not grant infrastructure capability. Policy maps principals to capabilities.
- R91: Candidate/model/backend identities never receive `holdout:read`, `evaluator:write`, `policy:write`, `promotion:approve`, `promotion:commit`, `approval:issue`, or `ledger:rewrite`. Issue `promotion:commit` only as a short CapabilityLease after G00–G13 pass.

### 4.4 Pagination and error contract

- R92: Use cursor pagination only, with `cursor`, `limit` (default 50, maximum 200), `snapshot_id`, and resource filters. Order by `created_at DESC` then immutable resource ID DESC.
- R93: Return `{items, next_cursor, snapshot_id, has_more}` and an optional total only when actually calculated.
- R94: Bind opaque cursors to principal, authorization scope, filter/query hash, snapshot, ordering, and expiry. Return 400 for malformed, 409 for snapshot/query mismatch, and 410 for expired cursors.
- R95: Use `application/problem+json` with `type`, `title`, `status`, `detail`, `instance`, `code`, `request_id`, `retryable`, `details`, and `evidence_artifact_ids`.
- R96: Implement status mappings: 400 malformed request/filter/cursor; 401 missing/invalid authentication; 403 capability/license/confidentiality/policy denial; 404 not found or concealment; 409 idempotency conflict, illegal transition, or synchronous SPEC_GAP; 410 expired cursor/retired projection; 412 revision/If-Match failure; 413 payload too large; 415 unsupported media type; 422 schema/semantic/pin/falsifier/scope validation; 429 rate/quota/hard-budget admission denial; 500 integrity/reconciliation failure; 502 invalid backend response; 503 unavailable required backend/credential/service/licensed source (`BLOCKED`); 504 bounded timeout.

### 4.5 C01 completion evidence

- R97: C01 must pass OpenAPI 3.1.1 validation, unique operation IDs, canonical scientific `$ref` checks, endpoint security-scope checks, mutation idempotency-header checks, transition-precondition checks, async Location/RunHandle checks, pagination tests, problem+json tests, unauthorized candidate promotion/holdout tests, generated-client dry run, schema/example validation, breaking-change recording, and independent contract review.
- R98: Remove the incorrect MASTER_SPEC section-18 API-authority reference from `docs/api_contract.md`.
- R99: Do not increase canonical schema count for transport types and do not implement API runtime in C01.

## 5. B04 — canonical registry packaging

### 5.1 Authority, layout, and fail-closed runtime

- R100: Start B04 only after C01 passes. Root `schemas/**` and `openapi/**` are source authority; packaged files are a content-addressed runtime snapshot from the build.
- R101: B04 must not modify root schemas or OpenAPI meaning.
- R102: Package `_canonical/canonical-registry.json`, `_canonical/schemas/**`, and `_canonical/openapi/**` under `src/epistemic_foundry`.
- R103: Each registry entry includes bundle version, build source revision, relative resource path, media type, schema `$id` or OpenAPI document ID, SHA-256, byte size, generated-at/build epoch, and source-bundle hash.
- R104: Runtime loading uses `importlib.resources` or an equivalent package-resource API and never depends on current working directory, repo-relative fallback, editable-install-only paths, missing-resource fallback to source, first-found source/dist authority, or duplicate registry implementations.
- R105: Fail closed with `CANONICAL_REGISTRY_MISSING`, `CANONICAL_REGISTRY_HASH_MISMATCH`, or `CANONICAL_REGISTRY_DUPLICATE_ID` for the corresponding integrity failures.

### 5.2 Build integration

- R106: Keep the build backend selected by B01/B02; do not replace it to solve packaging.
- R107: Use the backend's native deterministic build hook to materialize root schemas/OpenAPI into package resources automatically. A manual pre-build sync is not acceptable.
- R108: Configure wheel and sdist package data in `pyproject.toml`.
- R109: Record B04's `pyproject.toml` change as an integration correction superseding B01 for that path without deleting B01 history, and rerun B01 repository/package-boundary checks.

### 5.3 B04 acceptance

- R110: Build sdist and wheel from a clean-checkout-equivalent environment, unpack both, and compare source and packaged registry paths, counts, and hashes.
- R111: Verify unique schema IDs and OpenAPI presence/hash.
- R112: Install the wheel into an empty environment, remove the source repo from import path and current directory, enumerate the installed registry, validate a representative schema, load OpenAPI, and repeat from an arbitrary empty working directory.
- R113: Verify a one-byte tamper fixture fails integrity checks, two wheel builds are reproducible, source/dist divergence fails, and phase artifacts reconcile.
- R114: Require independent integration review and machine-readable ArtifactReceipt/build evidence.
- R115: PASS requires equal source and packaged canonical counts, zero missing/extra/hash mismatch/duplicate IDs/source-tree fallback, clean wheel install PASS, and sdist-to-wheel build PASS.

## 6. Per-stage bookkeeping and stop rules

- R116: After each package, run its schema/contract validation and required checks; create new attempt report/commands/review artifacts; append RAH evidence; verify the generation stamp; run `inspect --resume --json`; run `git diff --check`; confirm dirty-worktree preservation; and recompute the dependency graph.
- R117: Expected readiness immediately after the shared-contract correction is A05 `READY`, C01 waiting on A05, and B04 waiting on C01.
- R118: After all three pass, recompute the entire DAG and continue from the next dependency-ready package under the execution manifest.
- R119: Stop only on a genuinely new typed blocker, recording the exact unresolved contract and minimum higher-authority decision.
- R120: Never wash prior reports, weaken gates, change schema count without authority, create dual source/wheel authority, implement the API in C01, change schema meaning in B04, use human approval to bypass a non-waivable failure, claim completion without receipts, use Fleet/subagents, or reset/clean the dirty worktree.
