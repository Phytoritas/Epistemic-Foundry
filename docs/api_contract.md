# Epistemic Foundry REST v1 Contract

Status: `CANONICAL TRANSPORT CONTRACT`

Canonical document: `openapi/epistemic-foundry-v1.openapi.yaml`

OpenAPI version: `3.1.1`

Base path: `/api/v1`

JSON Schema dialect: Draft 2020-12

This document describes the transport contract fixed by C01. It does not
claim that API handlers, authentication middleware, queues, persistence, or a
production server exist; those are U01 and later runtime responsibilities.
Scientific artifact meaning remains authoritative in the existing
`schemas/*.schema.json` files. OpenAPI references those files and defines only
transport envelopes in `components`.

## Endpoint matrix

| Area | Method and path | Request | Success response | Required capability |
| --- | --- | --- | --- | --- |
| System | `GET /health/live` | none | `200 Liveness` | none; response is deliberately minimal |
| System | `GET /health/ready` | none | `200 PluginHealthReport` | `system:read` |
| System | `GET /capabilities` | none | `200 HostCapabilityReport` | `system:read` |
| Runs | `POST /runs` | `RunSpec` | `202 RunHandle` | `run:create` |
| Runs | `GET /runs` | cursor query | `200` page of `RunView` | `run:read` |
| Runs | `GET /runs/{run_id}` | none | `200 RunView` | `run:read` |
| Runs | `GET /runs/{run_id}/events` | cursor query or SSE accept | `200` page/stream of `EventRecord` | `run:read` |
| Runs | `POST /runs/{run_id}/actions/pause` | `CommandRequest` | `202 RunHandle` | `run:control` |
| Runs | `POST /runs/{run_id}/actions/resume` | `CommandRequest` | `202 RunHandle` | `run:control` |
| Runs | `POST /runs/{run_id}/actions/cancel` | `CommandRequest` | `202 RunHandle` | `run:control` |
| Documents | `POST /documents` | `DocumentRegistrationRequest` | `202 RunHandle` | `document:ingest` |
| Documents | `GET /documents/{document_id}` | none | `200 DocumentManifest` | `document:read` |
| Evidence | `GET /claims/{claim_id}` | none | `200 ClaimCard` | `evidence:read` |
| Evidence | `GET /evidence/{evidence_id}` | none | `200 EvidenceNode` | `evidence:read` |
| Evidence | `POST /retrieval-runs` | `QueryPlan` | `202 RunHandle` | `retrieval:execute` |
| Evidence | `GET /evidence-packs/{evidence_pack_id}` | none | `200 EvidencePack` | `evidence:read` |
| Evidence | `GET /coverage-snapshots/{coverage_snapshot_id}` | none | `200 CoverageSnapshot` | `evidence:read` |
| Deliberation | `POST /deliberation-runs` | `RunSpec` with `workflow_id=insight_deliberation` | `202 RunHandle` | `deliberation:execute` |
| Deliberation | `GET /adjudications/{adjudication_id}` | none | `200 Adjudication` | `deliberation:read` |
| Evolution | `POST /evolution-runs` | `EvolutionRunSpec` | `202 RunHandle` | `evolution:execute` |
| Evolution | `GET /evolution-runs/{evolution_run_id}` | none | `200 RunView` plus sealed spec artifact reference | `evolution:read` |
| Evolution | `GET /evolution-runs/{evolution_run_id}/candidates` | cursor query | `200` page of `CandidateEnvelope` | `candidate:read` |
| Evolution | `GET /candidates/{candidate_id}` | none | `200 CandidateEnvelope` | `candidate:read` |
| Evolution | `POST /candidates/{candidate_id}/promotion-requests` | requested level, expected revision, phase-E artifact-set ID, reason | `202 RunHandle` | `promotion:request` |
| Evolution | `GET /promotion-decisions/{decision_id}` | none | `200 PromotionDecision` | `promotion:read` |
| Evolution | `GET /passports/{passport_id}` | none | `200 HypothesisPassport` | `passport:read` |
| Validation | `POST /validation-runs` | `ValidationPlan` | `202 RunHandle` | `validation:execute` |
| Replication | `POST /replication-runs` | `ReplicationPlan` | `202 RunHandle` | `replication:execute` |
| Replication | `GET /replication-results/{replication_result_id}` | none | `200 ReplicationResult` | `replication:read` |
| Approvals | `POST /approvals` | `ApprovalCommand` | `201 ApprovalRecord` | `promotion:approve` or `action:approve` |
| Approvals | `GET /approvals/{approval_id}` | none | `200 ApprovalRecord` | `approval:read` |
| Artifacts | `GET /artifacts/{artifact_id}` | none | `200 ArtifactManifest` | `artifact:read` |
| Artifacts | `GET /artifacts/{artifact_id}/content` | none | `200` binary or bounded `307` | `artifact:content` |

There are 33 canonical operations. Direct multipart upload is outside v1.
`DocumentRegistrationRequest` names one immutable `staged_source_artifact_id`;
an `original_uri` is acquisition provenance and never a fetch command. Accepted
work creates an immutable `DocumentRegistration` before any final
`DocumentManifest`. The final manifest is lineage-bound to that registration
through matching registration IDs, source-blob and receipt references, and
append-only lineage events. Artifact metadata, locator, and raw-content access
remain separate authority surfaces. Source license, confidentiality, retention,
and access policy still apply to the content endpoint.

## Asynchronous execution and scientific outcomes

Execution, retrieval, ingest, deliberation, evolution, validation,
replication, and promotion do not finish on the request thread. A successful
admission returns:

```http
HTTP/1.1 202 Accepted
Location: /api/v1/runs/RUN-...
Retry-After: 2
Content-Type: application/json
```

`RunHandle` contains `run_id`, `status`, `status_url`, `events_url`,
`submitted_at`, `request_id`, `idempotency_key`, and `input_hash`. Schema,
authorization, and admission failures are rejected synchronously and never
queued.

After acceptance, `BLOCKED`, `SPEC_GAP`, and `FAIL` are truthful terminal run
states carried in `RunView` and `ResultEnvelope`. `UNDERDETERMINED`,
`CONDITIONAL`, `REJECT`, and `MIXED` are ordinary scientific results, not HTTP
errors. JSON polling of `EventRecord` is canonical. SSE carries the same
ordered records only as a delivery projection.

## Idempotency and concurrency

Every mutation operation requires `Idempotency-Key`:

- same key and same canonical request hash returns the first logical result;
- same key and different request hash returns `409 IDEMPOTENCY_KEY_REUSED`;
- a retry never duplicates an effect or immutable revision.

State transitions require `CommandRequest.expected_revision` or `If-Match`.
A mismatch returns `412 PRECONDITION_FAILED`. The three run-control commands
require `expected_revision`; promotion and approval commands carry their own
expected revision. `GET` never changes state, and query parameters cannot
pause, cancel, promote, approve, or trigger another effect.

## Authentication, capability, and authority separation

The supported profiles are local plugin session, team/OIDC bearer, and service
automation credential. OpenAPI names `LocalSession` and `BearerAuth` security
schemes. Scientific roles do not grant infrastructure capability; the policy
engine maps an authenticated principal to an explicit capability.

Candidate, model, prompt, and backend identities never receive:

- `holdout:read`
- `evaluator:write`
- `policy:write`
- `promotion:approve`
- `promotion:commit`
- `approval:issue`
- `ledger:rewrite`

`promotion:commit` is available only as a short `CapabilityLease` after
G00-G13 pass. `ApprovalCommand` contains no client-asserted `authority_role`;
the server verifies the authenticated authority and sealed policy before
issuing `ApprovalRecord`.

## Cursor pagination

Offset pagination is not canonical. Collection operations accept `cursor`,
`limit` (default 50, maximum 200), `snapshot_id`, and documented
resource-specific filters. Ordering is `created_at DESC`, then immutable
resource ID `DESC`.

```json
{
  "items": [],
  "next_cursor": null,
  "snapshot_id": "SNAP-...",
  "has_more": false
}
```

A cursor is opaque and bound to the principal, authorization scope,
filter/query hash, snapshot ID, ordering, and expiry. Malformed cursors return
400; query or snapshot mismatch returns 409; expiry returns 410. `total_count`
is optional and appears only when actually calculated.

## Error contract

Errors use `application/problem+json`. `ApiProblem` requires `type`, `title`,
`status`, `detail`, `instance`, `code`, `request_id`, `retryable`, `details`,
and `evidence_artifact_ids`.

| Status | Canonical use |
| ---: | --- |
| 400 | malformed request, filter, or cursor |
| 401 | missing or invalid authentication |
| 403 | capability, license, confidentiality, or policy denial |
| 404 | resource absent or concealed |
| 409 | idempotency conflict, illegal transition, cursor mismatch, or synchronous shared-contract conflict/SPEC_GAP |
| 410 | expired cursor or retired projection |
| 412 | expected-revision or `If-Match` failure |
| 413 | payload too large |
| 415 | unsupported media type |
| 422 | schema/semantic validation, invalid pin/hash, or invalid falsifier/scope registration |
| 429 | rate, quota, or hard-budget admission denial |
| 500 | internal integrity or reconciliation failure |
| 502 | invalid external-backend response |
| 503 | required backend, credential, service, or licensed source unavailable/BLOCKED |
| 504 | bounded operation timeout |

Scientific verdicts are never translated into 4xx or 5xx responses.

## Promotion decision semantics

Promotion levels use one closed order: `INBOX < CANDIDATE <
LITERATURE_GROUNDED < VALIDATION_SCREENED < EMPIRICALLY_TESTED < REPLICATED`.
`requested_level` is the target of the sealed request. Required field
`granted_level` records only a level newly conferred by this decision; it is
not the candidate's current, retained, or historical Passport level.

`PROMOTE` requires a non-null `granted_level` exactly equal to
`requested_level`. `CONDITIONAL` requires a non-null level strictly below the
request and still bounded by the promotion ceiling; the runtime additionally
verifies that it is above the candidate's current level. `REJECT`,
`UNDERDETERMINED`, and `BLOCKED` require `granted_level: null` and leave the
existing candidate and Passport revisions unchanged. A later downgrade,
retraction, or invalidation is a separate reassessment workflow with its own
immutable decision and effect receipt; rejection of a promotion request is
never an implicit demotion.

## Canonical schema and change policy

Scientific request and response bodies reference the canonical schemas under
`schemas/`. Transport-only envelopes—`RunHandle`, `RunView`,
`CommandRequest`, `ApiProblem`, `CursorPageMetadata`,
`CandidateEnvelope`, and `ApprovalCommand`—are defined only in OpenAPI
components. `DocumentRegistrationRequest` and `DocumentRegistration` are
canonical scientific artifacts referenced from OpenAPI rather than redefined by
the transport layer. The active inventory is exactly 127 canonical schemas and
127 matching examples, including the provider-neutral `RetrievalCandidate`
business artifact. C01 does not generate clients; client generation belongs
to C02.

Additive optional response fields require a minor-version compatibility note.
A required field, removed operation, changed authorization requirement, or
changed scientific meaning is a breaking change and requires a new versioned
contract or explicit migration window. Old immutable artifacts remain readable
through declared migration or adapter contracts; they are never silently
reinterpreted.
