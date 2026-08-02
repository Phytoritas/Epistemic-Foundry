// GENERATED FILE - DO NOT EDIT.
//
// generator: artifacts/work_packages/U01/attempts/0001/generate_client.py
// generator_version: 1.0.0
// source_document: openapi/epistemic-foundry-v1.openapi.yaml
// source_document_sha256: sha256:43429ad9c583b1026bd2445fb77d38b12410d2f6db065cffad45c64297db2cd7
// route_table_sha256: sha256:a8ca1da4dd7566082b0b342ca921dc7563ce1d645e0efb493d71760acfa129a1
// operation_count: 33

export type UiClientFindingCode =
  | "PATH_PARAMETER_MISSING"
  | "PATH_PARAMETER_UNKNOWN"
  | "QUERY_PARAMETER_INVALID"
  | "REQUEST_BODY_MISSING"
  | "REQUEST_BODY_UNEXPECTED"
  | "TRANSPORT_INVALID";

export declare const UI_CLIENT_FINDING_CODES: Readonly<
  Record<UiClientFindingCode, string>
>;

export declare class UiClientError extends Error {
  readonly code: UiClientFindingCode;
  readonly detail: string;
  readonly reason: string;
  readonly context: Readonly<Record<string, unknown>>;
}

export interface UiRequestDescriptor {
  readonly body: unknown;
  readonly headers: Readonly<Record<string, string>>;
  readonly method: string;
  readonly operationId: OperationId;
  readonly path: string;
  readonly pathTemplate: string;
  readonly query: string;
  readonly requestSchemaRef: string | null;
  readonly responseSchemaRef: string | null;
  readonly successStatus: string | null;
  readonly url: string;
}

export interface UiRequestInput {
  readonly path?: Readonly<Record<string, string | number>>;
  readonly query?: Readonly<Record<string, string | number | boolean | undefined>>;
  readonly headers?: Readonly<Record<string, string>>;
  readonly body?: unknown;
}

export type UiTransport<T> = (request: UiRequestDescriptor) => T;

export interface UiOperation {
  readonly method: string;
  readonly operationId: OperationId;
  readonly path: string;
  readonly pathParameters: readonly string[];
  readonly requestMediaType: string | null;
  readonly requestRequired: boolean;
  readonly requestSchemaKind: "ref" | "inline" | "none";
  readonly requestSchemaRef: string | null;
  readonly responseMediaType: string | null;
  readonly responseSchemaKind: "ref" | "inline" | "none";
  readonly responseSchemaRef: string | null;
  readonly responses: readonly {
    readonly mediaType: string | null;
    readonly responseRef: string | null;
    readonly schemaKind: "ref" | "inline" | "none";
    readonly schemaRef: string | null;
    readonly status: string;
  }[];
  readonly statusCodes: readonly string[];
  readonly successStatus: string | null;
  readonly summary: string;
  readonly tags: readonly string[];
}

export declare const SOURCE_DOCUMENT: Readonly<{
  operationCount: number;
  path: string;
  routeTableSha256: string;
  sha256: string;
}>;

export declare const BASE_PATH: string;

export type OperationId =
  | "cancelRun"
  | "createApproval"
  | "createDeliberationRun"
  | "createEvolutionRun"
  | "createReplicationRun"
  | "createRetrievalRun"
  | "createRun"
  | "createValidationRun"
  | "getAdjudication"
  | "getApproval"
  | "getArtifact"
  | "getArtifactContent"
  | "getCandidate"
  | "getCapabilities"
  | "getClaim"
  | "getCoverageSnapshot"
  | "getDocument"
  | "getEvidence"
  | "getEvidencePack"
  | "getEvolutionRun"
  | "getLiveness"
  | "getPassport"
  | "getPromotionDecision"
  | "getReadiness"
  | "getReplicationResult"
  | "getRun"
  | "getRunEvents"
  | "listEvolutionCandidates"
  | "listRuns"
  | "pauseRun"
  | "registerDocument"
  | "requestCandidatePromotion"
  | "resumeRun";

export declare const OPERATIONS: Readonly<Record<OperationId, UiOperation>>;

export declare const OPERATION_IDS: readonly OperationId[];

/** `POST /runs/{run_id}/actions/cancel` - Request an expected-revision cancellation transition */
export declare function cancelRun(input?: UiRequestInput): UiRequestDescriptor;
export declare function cancelRun<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `POST /approvals` - Create an approval after server-side authority and policy verification */
export declare function createApproval(input?: UiRequestInput): UiRequestDescriptor;
export declare function createApproval<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `POST /deliberation-runs` - Accept a RunSpec whose workflow_id is insight_deliberation */
export declare function createDeliberationRun(input?: UiRequestInput): UiRequestDescriptor;
export declare function createDeliberationRun<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `POST /evolution-runs` - Accept a sealed asynchronous evolution run */
export declare function createEvolutionRun(input?: UiRequestInput): UiRequestDescriptor;
export declare function createEvolutionRun<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `POST /replication-runs` - Accept an asynchronous preregistered replication run */
export declare function createReplicationRun(input?: UiRequestInput): UiRequestDescriptor;
export declare function createReplicationRun<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `POST /retrieval-runs` - Accept an asynchronous retrieval run */
export declare function createRetrievalRun(input?: UiRequestInput): UiRequestDescriptor;
export declare function createRetrievalRun<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `POST /runs` - Accept a new asynchronous run */
export declare function createRun(input?: UiRequestInput): UiRequestDescriptor;
export declare function createRun<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `POST /validation-runs` - Accept an asynchronous preregistered validation run */
export declare function createValidationRun(input?: UiRequestInput): UiRequestDescriptor;
export declare function createValidationRun<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /adjudications/{adjudication_id}` - Read a canonical Evidence Parliament adjudication */
export declare function getAdjudication(input?: UiRequestInput): UiRequestDescriptor;
export declare function getAdjudication<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /approvals/{approval_id}` - Read a server-issued approval record */
export declare function getApproval(input?: UiRequestInput): UiRequestDescriptor;
export declare function getApproval<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /artifacts/{artifact_id}` - Read artifact metadata without implicitly granting content access */
export declare function getArtifact(input?: UiRequestInput): UiRequestDescriptor;
export declare function getArtifact<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /artifacts/{artifact_id}/content` - Stream authorized content or return a bounded redirect */
export declare function getArtifactContent(input?: UiRequestInput): UiRequestDescriptor;
export declare function getArtifactContent<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /candidates/{candidate_id}` - Read a candidate envelope */
export declare function getCandidate(input?: UiRequestInput): UiRequestDescriptor;
export declare function getCandidate<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /capabilities` - Read qualified host capabilities */
export declare function getCapabilities(input?: UiRequestInput): UiRequestDescriptor;
export declare function getCapabilities<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /claims/{claim_id}` - Read a canonical claim card */
export declare function getClaim(input?: UiRequestInput): UiRequestDescriptor;
export declare function getClaim<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /coverage-snapshots/{coverage_snapshot_id}` - Read searched-scope coverage without inventing completeness */
export declare function getCoverageSnapshot(input?: UiRequestInput): UiRequestDescriptor;
export declare function getCoverageSnapshot<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /documents/{document_id}` - Read a canonical document manifest */
export declare function getDocument(input?: UiRequestInput): UiRequestDescriptor;
export declare function getDocument<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /evidence/{evidence_id}` - Read a canonical evidence node */
export declare function getEvidence(input?: UiRequestInput): UiRequestDescriptor;
export declare function getEvidence<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /evidence-packs/{evidence_pack_id}` - Read a canonical evidence pack */
export declare function getEvidencePack(input?: UiRequestInput): UiRequestDescriptor;
export declare function getEvidencePack<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /evolution-runs/{evolution_run_id}` - Read a run view carrying its EvolutionRunSpec artifact reference */
export declare function getEvolutionRun(input?: UiRequestInput): UiRequestDescriptor;
export declare function getEvolutionRun<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /health/live` - Minimal unauthenticated process liveness */
export declare function getLiveness(input?: UiRequestInput): UiRequestDescriptor;
export declare function getLiveness<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /passports/{passport_id}` - Read an immutable hypothesis passport revision */
export declare function getPassport(input?: UiRequestInput): UiRequestDescriptor;
export declare function getPassport<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /promotion-decisions/{decision_id}` - Read an immutable promotion decision revision */
export declare function getPromotionDecision(input?: UiRequestInput): UiRequestDescriptor;
export declare function getPromotionDecision<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /health/ready` - Readiness and dependency health */
export declare function getReadiness(input?: UiRequestInput): UiRequestDescriptor;
export declare function getReadiness<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /replication-results/{replication_result_id}` - Read a canonical replication result */
export declare function getReplicationResult(input?: UiRequestInput): UiRequestDescriptor;
export declare function getReplicationResult<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /runs/{run_id}` - Read a run and its terminal scientific result, when present */
export declare function getRun(input?: UiRequestInput): UiRequestDescriptor;
export declare function getRun<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /runs/{run_id}/events` - Read ordered run events; JSON polling is canonical and SSE is a projection */
export declare function getRunEvents(input?: UiRequestInput): UiRequestDescriptor;
export declare function getRunEvents<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /evolution-runs/{evolution_run_id}/candidates` - List candidates using snapshot-bound cursor pagination */
export declare function listEvolutionCandidates(input?: UiRequestInput): UiRequestDescriptor;
export declare function listEvolutionCandidates<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `GET /runs` - List runs using snapshot-bound cursor pagination */
export declare function listRuns(input?: UiRequestInput): UiRequestDescriptor;
export declare function listRuns<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `POST /runs/{run_id}/actions/pause` - Request an expected-revision pause transition */
export declare function pauseRun(input?: UiRequestInput): UiRequestDescriptor;
export declare function pauseRun<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `POST /documents` - Register one already-staged source artifact */
export declare function registerDocument(input?: UiRequestInput): UiRequestDescriptor;
export declare function registerDocument<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `POST /candidates/{candidate_id}/promotion-requests` - Map a sealed promotion request to ActionIntent(request_promotion) */
export declare function requestCandidatePromotion(input?: UiRequestInput): UiRequestDescriptor;
export declare function requestCandidatePromotion<T>(input: UiRequestInput, transport: UiTransport<T>): T;

/** `POST /runs/{run_id}/actions/resume` - Request an expected-revision resume transition */
export declare function resumeRun(input?: UiRequestInput): UiRequestDescriptor;
export declare function resumeRun<T>(input: UiRequestInput, transport: UiTransport<T>): T;
