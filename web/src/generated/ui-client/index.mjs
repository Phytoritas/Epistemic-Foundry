// GENERATED FILE - DO NOT EDIT.
//
// generator: artifacts/work_packages/U01/attempts/0001/generate_client.py
// generator_version: 1.0.0
// source_document: openapi/epistemic-foundry-v1.openapi.yaml
// source_document_sha256: sha256:43429ad9c583b1026bd2445fb77d38b12410d2f6db065cffad45c64297db2cd7
// route_table_sha256: sha256:a8ca1da4dd7566082b0b342ca921dc7563ce1d645e0efb493d71760acfa129a1
// operation_count: 33
//
// Every exported binding below is one operationId from the canonical
// OpenAPI document, with its HTTP method and path template baked in at
// generation time.  No route, schema reference or status code in this
// file was written by hand; regenerate with the generator above rather
// than editing, or the client stops describing the declared surface.

export const SOURCE_DOCUMENT = Object.freeze({
  operationCount: 33,
  path: "openapi/epistemic-foundry-v1.openapi.yaml",
  routeTableSha256: "sha256:a8ca1da4dd7566082b0b342ca921dc7563ce1d645e0efb493d71760acfa129a1",
  sha256: "sha256:43429ad9c583b1026bd2445fb77d38b12410d2f6db065cffad45c64297db2cd7",
});

/** The single server base path the document declares. */
export const BASE_PATH = "/api/v1";

/** Machine codes this client refuses with, each with its standing reason. */
export const UI_CLIENT_FINDING_CODES = Object.freeze({
  PATH_PARAMETER_MISSING:
    "A path parameter the operation's path template declares was not supplied, so the request URL could not be built without leaving an unresolved placeholder in the path.",
  PATH_PARAMETER_UNKNOWN:
    "A path parameter was supplied that the operation's path template does not declare, so it would be silently dropped and the caller would believe it was sent.",
  REQUEST_BODY_MISSING:
    "The operation declares a required request body and none was supplied, so the request would be rejected by the server after a needless round trip.",
  REQUEST_BODY_UNEXPECTED:
    "A request body was supplied for an operation the document declares as carrying no request body, so the payload has no declared schema to be checked against.",
  QUERY_PARAMETER_INVALID:
    "A query parameter value is neither a string, a finite number, nor a boolean, so it has no deterministic single-valued encoding in the request URL.",
  TRANSPORT_INVALID:
    "A transport argument was supplied that is not a function, so the request descriptor could not be handed to anything able to send it.",
});

/** A refusal raised while building a request from a declared operation. */
export class UiClientError extends Error {
  constructor(code, detail, context = {}) {
    super(`${code}: ${detail}`);
    this.name = "UiClientError";
    this.code = code;
    this.detail = detail;
    this.reason = UI_CLIENT_FINDING_CODES[code];
    this.context = Object.freeze({ ...context });
    Object.freeze(this);
  }
}

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of Object.keys(value)) deepFreeze(value[key]);
  return Object.freeze(value);
};

const encodeQueryValue = (name, value) => {
  const kind = typeof value;
  if (kind === "string") return encodeURIComponent(value);
  if (kind === "boolean") return String(value);
  if (kind === "number" && Number.isFinite(value)) return String(value);
  throw new UiClientError(
    "QUERY_PARAMETER_INVALID",
    `query parameter ${name} is a ${kind} with no deterministic encoding`,
    { name },
  );
};

/**
 * Build one immutable request descriptor from a declared operation.
 *
 * This client performs no I/O of its own and reads no clock or random source:
 * it returns a descriptor, and hands it to `transport` only when one is given.
 */
const buildRequest = (operation, input, transport) => {
  const pathValues = input.path ?? {};
  for (const name of operation.pathParameters) {
    if (!Object.hasOwn(pathValues, name) || pathValues[name] === undefined) {
      throw new UiClientError(
        "PATH_PARAMETER_MISSING",
        `${operation.operationId} requires path parameter ${name}`,
        { operationId: operation.operationId, parameter: name },
      );
    }
  }
  for (const name of Object.keys(pathValues)) {
    if (!operation.pathParameters.includes(name)) {
      throw new UiClientError(
        "PATH_PARAMETER_UNKNOWN",
        `${operation.operationId} declares no path parameter ${name}`,
        { operationId: operation.operationId, parameter: name },
      );
    }
  }
  const hasBody = Object.hasOwn(input, "body") && input.body !== undefined;
  if (hasBody && operation.requestMediaType === null) {
    throw new UiClientError(
      "REQUEST_BODY_UNEXPECTED",
      `${operation.operationId} declares no request body`,
      { operationId: operation.operationId },
    );
  }
  if (!hasBody && operation.requestRequired) {
    throw new UiClientError(
      "REQUEST_BODY_MISSING",
      `${operation.operationId} declares a required request body`,
      { operationId: operation.operationId },
    );
  }
  const path = operation.pathParameters.reduce(
    (accumulated, name) =>
      accumulated.replace(`{${name}}`, encodeURIComponent(String(pathValues[name]))),
    operation.path,
  );
  const query = input.query ?? {};
  const search = Object.keys(query)
    .filter((name) => query[name] !== undefined)
    .sort()
    .map((name) => `${encodeURIComponent(name)}=${encodeQueryValue(name, query[name])}`)
    .join("&");
  const headers = { ...(input.headers ?? {}) };
  if (hasBody && operation.requestMediaType !== null) {
    headers["content-type"] = operation.requestMediaType;
  }
  const descriptor = deepFreeze({
    body: hasBody ? input.body : null,
    headers,
    method: operation.method,
    operationId: operation.operationId,
    path,
    pathTemplate: operation.path,
    query: search,
    requestSchemaRef: operation.requestSchemaRef,
    responseSchemaRef: operation.responseSchemaRef,
    successStatus: operation.successStatus,
    url: `${BASE_PATH}${path}${search === "" ? "" : `?${search}`}`,
  });
  if (transport === undefined) return descriptor;
  if (typeof transport !== "function") {
    throw new UiClientError(
      "TRANSPORT_INVALID",
      `${operation.operationId} was given a ${typeof transport} as transport`,
      { operationId: operation.operationId },
    );
  }
  return transport(descriptor);
};

/** Every declared operation, exactly as projected from the document. */
export const OPERATIONS = deepFreeze({
  "cancelRun": {
    "method": "POST",
    "operationId": "cancelRun",
    "path": "/runs/{run_id}/actions/cancel",
    "pathParameters": [
      "run_id"
    ],
    "requestMediaType": "application/json",
    "requestRequired": true,
    "requestSchemaKind": "ref",
    "requestSchemaRef": "#/components/schemas/CommandRequest",
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunHandle",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": "#/components/responses/AsyncAccepted",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunHandle",
        "status": "202"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "202",
      "default"
    ],
    "successStatus": "202",
    "summary": "Request an expected-revision cancellation transition",
    "tags": [
      "Runs"
    ]
  },
  "createApproval": {
    "method": "POST",
    "operationId": "createApproval",
    "path": "/approvals",
    "pathParameters": [],
    "requestMediaType": "application/json",
    "requestRequired": true,
    "requestSchemaKind": "ref",
    "requestSchemaRef": "#/components/schemas/ApprovalCommand",
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/approval-record.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/approval-record.schema.json",
        "status": "201"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "201",
      "default"
    ],
    "successStatus": "201",
    "summary": "Create an approval after server-side authority and policy verification",
    "tags": [
      "Approvals"
    ]
  },
  "createDeliberationRun": {
    "method": "POST",
    "operationId": "createDeliberationRun",
    "path": "/deliberation-runs",
    "pathParameters": [],
    "requestMediaType": "application/json",
    "requestRequired": true,
    "requestSchemaKind": "inline",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunHandle",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": "#/components/responses/AsyncAccepted",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunHandle",
        "status": "202"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "202",
      "default"
    ],
    "successStatus": "202",
    "summary": "Accept a RunSpec whose workflow_id is insight_deliberation",
    "tags": [
      "Deliberation"
    ]
  },
  "createEvolutionRun": {
    "method": "POST",
    "operationId": "createEvolutionRun",
    "path": "/evolution-runs",
    "pathParameters": [],
    "requestMediaType": "application/json",
    "requestRequired": true,
    "requestSchemaKind": "ref",
    "requestSchemaRef": "../schemas/evolution-run-spec.schema.json",
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunHandle",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": "#/components/responses/AsyncAccepted",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunHandle",
        "status": "202"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "202",
      "default"
    ],
    "successStatus": "202",
    "summary": "Accept a sealed asynchronous evolution run",
    "tags": [
      "Evolution"
    ]
  },
  "createReplicationRun": {
    "method": "POST",
    "operationId": "createReplicationRun",
    "path": "/replication-runs",
    "pathParameters": [],
    "requestMediaType": "application/json",
    "requestRequired": true,
    "requestSchemaKind": "ref",
    "requestSchemaRef": "../schemas/replication-plan.schema.json",
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunHandle",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": "#/components/responses/AsyncAccepted",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunHandle",
        "status": "202"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "202",
      "default"
    ],
    "successStatus": "202",
    "summary": "Accept an asynchronous preregistered replication run",
    "tags": [
      "Validation and replication"
    ]
  },
  "createRetrievalRun": {
    "method": "POST",
    "operationId": "createRetrievalRun",
    "path": "/retrieval-runs",
    "pathParameters": [],
    "requestMediaType": "application/json",
    "requestRequired": true,
    "requestSchemaKind": "ref",
    "requestSchemaRef": "../schemas/query-plan.schema.json",
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunHandle",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": "#/components/responses/AsyncAccepted",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunHandle",
        "status": "202"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "202",
      "default"
    ],
    "successStatus": "202",
    "summary": "Accept an asynchronous retrieval run",
    "tags": [
      "Documents and evidence"
    ]
  },
  "createRun": {
    "method": "POST",
    "operationId": "createRun",
    "path": "/runs",
    "pathParameters": [],
    "requestMediaType": "application/json",
    "requestRequired": true,
    "requestSchemaKind": "ref",
    "requestSchemaRef": "../schemas/run-spec.schema.json",
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunHandle",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": "#/components/responses/AsyncAccepted",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunHandle",
        "status": "202"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "202",
      "default"
    ],
    "successStatus": "202",
    "summary": "Accept a new asynchronous run",
    "tags": [
      "Runs"
    ]
  },
  "createValidationRun": {
    "method": "POST",
    "operationId": "createValidationRun",
    "path": "/validation-runs",
    "pathParameters": [],
    "requestMediaType": "application/json",
    "requestRequired": true,
    "requestSchemaKind": "ref",
    "requestSchemaRef": "../schemas/validation-plan.schema.json",
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunHandle",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": "#/components/responses/AsyncAccepted",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunHandle",
        "status": "202"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "202",
      "default"
    ],
    "successStatus": "202",
    "summary": "Accept an asynchronous preregistered validation run",
    "tags": [
      "Validation and replication"
    ]
  },
  "getAdjudication": {
    "method": "GET",
    "operationId": "getAdjudication",
    "path": "/adjudications/{adjudication_id}",
    "pathParameters": [
      "adjudication_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/adjudication.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/adjudication.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read a canonical Evidence Parliament adjudication",
    "tags": [
      "Deliberation"
    ]
  },
  "getApproval": {
    "method": "GET",
    "operationId": "getApproval",
    "path": "/approvals/{approval_id}",
    "pathParameters": [
      "approval_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/approval-record.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/approval-record.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read a server-issued approval record",
    "tags": [
      "Approvals"
    ]
  },
  "getArtifact": {
    "method": "GET",
    "operationId": "getArtifact",
    "path": "/artifacts/{artifact_id}",
    "pathParameters": [
      "artifact_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/artifact-manifest.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/artifact-manifest.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read artifact metadata without implicitly granting content access",
    "tags": [
      "Artifacts"
    ]
  },
  "getArtifactContent": {
    "method": "GET",
    "operationId": "getArtifactContent",
    "path": "/artifacts/{artifact_id}/content",
    "pathParameters": [
      "artifact_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/octet-stream",
    "responseSchemaKind": "inline",
    "responseSchemaRef": null,
    "responses": [
      {
        "mediaType": "application/octet-stream",
        "responseRef": null,
        "schemaKind": "inline",
        "schemaRef": null,
        "status": "200"
      },
      {
        "mediaType": null,
        "responseRef": null,
        "schemaKind": "none",
        "schemaRef": null,
        "status": "307"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "307",
      "default"
    ],
    "successStatus": "200",
    "summary": "Stream authorized content or return a bounded redirect",
    "tags": [
      "Artifacts"
    ]
  },
  "getCandidate": {
    "method": "GET",
    "operationId": "getCandidate",
    "path": "/candidates/{candidate_id}",
    "pathParameters": [
      "candidate_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/CandidateEnvelope",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/CandidateEnvelope",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read a candidate envelope",
    "tags": [
      "Evolution"
    ]
  },
  "getCapabilities": {
    "method": "GET",
    "operationId": "getCapabilities",
    "path": "/capabilities",
    "pathParameters": [],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/host-capability-report.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/host-capability-report.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read qualified host capabilities",
    "tags": [
      "System"
    ]
  },
  "getClaim": {
    "method": "GET",
    "operationId": "getClaim",
    "path": "/claims/{claim_id}",
    "pathParameters": [
      "claim_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/claim-card.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/claim-card.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read a canonical claim card",
    "tags": [
      "Documents and evidence"
    ]
  },
  "getCoverageSnapshot": {
    "method": "GET",
    "operationId": "getCoverageSnapshot",
    "path": "/coverage-snapshots/{coverage_snapshot_id}",
    "pathParameters": [
      "coverage_snapshot_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/coverage-snapshot.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/coverage-snapshot.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read searched-scope coverage without inventing completeness",
    "tags": [
      "Documents and evidence"
    ]
  },
  "getDocument": {
    "method": "GET",
    "operationId": "getDocument",
    "path": "/documents/{document_id}",
    "pathParameters": [
      "document_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/document-manifest.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/document-manifest.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read a canonical document manifest",
    "tags": [
      "Documents and evidence"
    ]
  },
  "getEvidence": {
    "method": "GET",
    "operationId": "getEvidence",
    "path": "/evidence/{evidence_id}",
    "pathParameters": [
      "evidence_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/evidence-node.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/evidence-node.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read a canonical evidence node",
    "tags": [
      "Documents and evidence"
    ]
  },
  "getEvidencePack": {
    "method": "GET",
    "operationId": "getEvidencePack",
    "path": "/evidence-packs/{evidence_pack_id}",
    "pathParameters": [
      "evidence_pack_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/evidence-pack.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/evidence-pack.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read a canonical evidence pack",
    "tags": [
      "Documents and evidence"
    ]
  },
  "getEvolutionRun": {
    "method": "GET",
    "operationId": "getEvolutionRun",
    "path": "/evolution-runs/{evolution_run_id}",
    "pathParameters": [
      "evolution_run_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "inline",
    "responseSchemaRef": null,
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "inline",
        "schemaRef": null,
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read a run view carrying its EvolutionRunSpec artifact reference",
    "tags": [
      "Evolution"
    ]
  },
  "getLiveness": {
    "method": "GET",
    "operationId": "getLiveness",
    "path": "/health/live",
    "pathParameters": [],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/Liveness",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/Liveness",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Minimal unauthenticated process liveness",
    "tags": [
      "System"
    ]
  },
  "getPassport": {
    "method": "GET",
    "operationId": "getPassport",
    "path": "/passports/{passport_id}",
    "pathParameters": [
      "passport_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/hypothesis-passport.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/hypothesis-passport.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read an immutable hypothesis passport revision",
    "tags": [
      "Evolution"
    ]
  },
  "getPromotionDecision": {
    "method": "GET",
    "operationId": "getPromotionDecision",
    "path": "/promotion-decisions/{decision_id}",
    "pathParameters": [
      "decision_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/promotion-decision.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/promotion-decision.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read an immutable promotion decision revision",
    "tags": [
      "Evolution"
    ]
  },
  "getReadiness": {
    "method": "GET",
    "operationId": "getReadiness",
    "path": "/health/ready",
    "pathParameters": [],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/plugin-health-report.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/plugin-health-report.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Readiness and dependency health",
    "tags": [
      "System"
    ]
  },
  "getReplicationResult": {
    "method": "GET",
    "operationId": "getReplicationResult",
    "path": "/replication-results/{replication_result_id}",
    "pathParameters": [
      "replication_result_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "../schemas/replication-result.schema.json",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "../schemas/replication-result.schema.json",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read a canonical replication result",
    "tags": [
      "Validation and replication"
    ]
  },
  "getRun": {
    "method": "GET",
    "operationId": "getRun",
    "path": "/runs/{run_id}",
    "pathParameters": [
      "run_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunView",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunView",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read a run and its terminal scientific result, when present",
    "tags": [
      "Runs"
    ]
  },
  "getRunEvents": {
    "method": "GET",
    "operationId": "getRunEvents",
    "path": "/runs/{run_id}/events",
    "pathParameters": [
      "run_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/EventRecordPage",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/EventRecordPage",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "Read ordered run events; JSON polling is canonical and SSE is a projection",
    "tags": [
      "Runs"
    ]
  },
  "listEvolutionCandidates": {
    "method": "GET",
    "operationId": "listEvolutionCandidates",
    "path": "/evolution-runs/{evolution_run_id}/candidates",
    "pathParameters": [
      "evolution_run_id"
    ],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/CandidatePage",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/CandidatePage",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "List candidates using snapshot-bound cursor pagination",
    "tags": [
      "Evolution"
    ]
  },
  "listRuns": {
    "method": "GET",
    "operationId": "listRuns",
    "path": "/runs",
    "pathParameters": [],
    "requestMediaType": null,
    "requestRequired": false,
    "requestSchemaKind": "none",
    "requestSchemaRef": null,
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunViewPage",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": null,
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunViewPage",
        "status": "200"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "200",
      "default"
    ],
    "successStatus": "200",
    "summary": "List runs using snapshot-bound cursor pagination",
    "tags": [
      "Runs"
    ]
  },
  "pauseRun": {
    "method": "POST",
    "operationId": "pauseRun",
    "path": "/runs/{run_id}/actions/pause",
    "pathParameters": [
      "run_id"
    ],
    "requestMediaType": "application/json",
    "requestRequired": true,
    "requestSchemaKind": "ref",
    "requestSchemaRef": "#/components/schemas/CommandRequest",
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunHandle",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": "#/components/responses/AsyncAccepted",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunHandle",
        "status": "202"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "202",
      "default"
    ],
    "successStatus": "202",
    "summary": "Request an expected-revision pause transition",
    "tags": [
      "Runs"
    ]
  },
  "registerDocument": {
    "method": "POST",
    "operationId": "registerDocument",
    "path": "/documents",
    "pathParameters": [],
    "requestMediaType": "application/json",
    "requestRequired": true,
    "requestSchemaKind": "ref",
    "requestSchemaRef": "../schemas/document-registration-request.schema.json",
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunHandle",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": "#/components/responses/AsyncAccepted",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunHandle",
        "status": "202"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "202",
      "default"
    ],
    "successStatus": "202",
    "summary": "Register one already-staged source artifact",
    "tags": [
      "Documents and evidence"
    ]
  },
  "requestCandidatePromotion": {
    "method": "POST",
    "operationId": "requestCandidatePromotion",
    "path": "/candidates/{candidate_id}/promotion-requests",
    "pathParameters": [
      "candidate_id"
    ],
    "requestMediaType": "application/json",
    "requestRequired": true,
    "requestSchemaKind": "ref",
    "requestSchemaRef": "#/components/schemas/PromotionRequest",
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunHandle",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": "#/components/responses/AsyncAccepted",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunHandle",
        "status": "202"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "202",
      "default"
    ],
    "successStatus": "202",
    "summary": "Map a sealed promotion request to ActionIntent(request_promotion)",
    "tags": [
      "Evolution"
    ]
  },
  "resumeRun": {
    "method": "POST",
    "operationId": "resumeRun",
    "path": "/runs/{run_id}/actions/resume",
    "pathParameters": [
      "run_id"
    ],
    "requestMediaType": "application/json",
    "requestRequired": true,
    "requestSchemaKind": "ref",
    "requestSchemaRef": "#/components/schemas/CommandRequest",
    "responseMediaType": "application/json",
    "responseSchemaKind": "ref",
    "responseSchemaRef": "#/components/schemas/RunHandle",
    "responses": [
      {
        "mediaType": "application/json",
        "responseRef": "#/components/responses/AsyncAccepted",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/RunHandle",
        "status": "202"
      },
      {
        "mediaType": "application/problem+json",
        "responseRef": "#/components/responses/Problem",
        "schemaKind": "ref",
        "schemaRef": "#/components/schemas/ApiProblem",
        "status": "default"
      }
    ],
    "statusCodes": [
      "202",
      "default"
    ],
    "successStatus": "202",
    "summary": "Request an expected-revision resume transition",
    "tags": [
      "Runs"
    ]
  }
});

/** Every declared operationId, sorted. */
export const OPERATION_IDS = Object.freeze(Object.keys(OPERATIONS));

/** `POST /runs/{run_id}/actions/cancel` - Request an expected-revision cancellation transition */
export const cancelRun = (input = {}, transport) =>
  buildRequest(OPERATIONS.cancelRun, input, transport);

/** `POST /approvals` - Create an approval after server-side authority and policy verification */
export const createApproval = (input = {}, transport) =>
  buildRequest(OPERATIONS.createApproval, input, transport);

/** `POST /deliberation-runs` - Accept a RunSpec whose workflow_id is insight_deliberation */
export const createDeliberationRun = (input = {}, transport) =>
  buildRequest(OPERATIONS.createDeliberationRun, input, transport);

/** `POST /evolution-runs` - Accept a sealed asynchronous evolution run */
export const createEvolutionRun = (input = {}, transport) =>
  buildRequest(OPERATIONS.createEvolutionRun, input, transport);

/** `POST /replication-runs` - Accept an asynchronous preregistered replication run */
export const createReplicationRun = (input = {}, transport) =>
  buildRequest(OPERATIONS.createReplicationRun, input, transport);

/** `POST /retrieval-runs` - Accept an asynchronous retrieval run */
export const createRetrievalRun = (input = {}, transport) =>
  buildRequest(OPERATIONS.createRetrievalRun, input, transport);

/** `POST /runs` - Accept a new asynchronous run */
export const createRun = (input = {}, transport) =>
  buildRequest(OPERATIONS.createRun, input, transport);

/** `POST /validation-runs` - Accept an asynchronous preregistered validation run */
export const createValidationRun = (input = {}, transport) =>
  buildRequest(OPERATIONS.createValidationRun, input, transport);

/** `GET /adjudications/{adjudication_id}` - Read a canonical Evidence Parliament adjudication */
export const getAdjudication = (input = {}, transport) =>
  buildRequest(OPERATIONS.getAdjudication, input, transport);

/** `GET /approvals/{approval_id}` - Read a server-issued approval record */
export const getApproval = (input = {}, transport) =>
  buildRequest(OPERATIONS.getApproval, input, transport);

/** `GET /artifacts/{artifact_id}` - Read artifact metadata without implicitly granting content access */
export const getArtifact = (input = {}, transport) =>
  buildRequest(OPERATIONS.getArtifact, input, transport);

/** `GET /artifacts/{artifact_id}/content` - Stream authorized content or return a bounded redirect */
export const getArtifactContent = (input = {}, transport) =>
  buildRequest(OPERATIONS.getArtifactContent, input, transport);

/** `GET /candidates/{candidate_id}` - Read a candidate envelope */
export const getCandidate = (input = {}, transport) =>
  buildRequest(OPERATIONS.getCandidate, input, transport);

/** `GET /capabilities` - Read qualified host capabilities */
export const getCapabilities = (input = {}, transport) =>
  buildRequest(OPERATIONS.getCapabilities, input, transport);

/** `GET /claims/{claim_id}` - Read a canonical claim card */
export const getClaim = (input = {}, transport) =>
  buildRequest(OPERATIONS.getClaim, input, transport);

/** `GET /coverage-snapshots/{coverage_snapshot_id}` - Read searched-scope coverage without inventing completeness */
export const getCoverageSnapshot = (input = {}, transport) =>
  buildRequest(OPERATIONS.getCoverageSnapshot, input, transport);

/** `GET /documents/{document_id}` - Read a canonical document manifest */
export const getDocument = (input = {}, transport) =>
  buildRequest(OPERATIONS.getDocument, input, transport);

/** `GET /evidence/{evidence_id}` - Read a canonical evidence node */
export const getEvidence = (input = {}, transport) =>
  buildRequest(OPERATIONS.getEvidence, input, transport);

/** `GET /evidence-packs/{evidence_pack_id}` - Read a canonical evidence pack */
export const getEvidencePack = (input = {}, transport) =>
  buildRequest(OPERATIONS.getEvidencePack, input, transport);

/** `GET /evolution-runs/{evolution_run_id}` - Read a run view carrying its EvolutionRunSpec artifact reference */
export const getEvolutionRun = (input = {}, transport) =>
  buildRequest(OPERATIONS.getEvolutionRun, input, transport);

/** `GET /health/live` - Minimal unauthenticated process liveness */
export const getLiveness = (input = {}, transport) =>
  buildRequest(OPERATIONS.getLiveness, input, transport);

/** `GET /passports/{passport_id}` - Read an immutable hypothesis passport revision */
export const getPassport = (input = {}, transport) =>
  buildRequest(OPERATIONS.getPassport, input, transport);

/** `GET /promotion-decisions/{decision_id}` - Read an immutable promotion decision revision */
export const getPromotionDecision = (input = {}, transport) =>
  buildRequest(OPERATIONS.getPromotionDecision, input, transport);

/** `GET /health/ready` - Readiness and dependency health */
export const getReadiness = (input = {}, transport) =>
  buildRequest(OPERATIONS.getReadiness, input, transport);

/** `GET /replication-results/{replication_result_id}` - Read a canonical replication result */
export const getReplicationResult = (input = {}, transport) =>
  buildRequest(OPERATIONS.getReplicationResult, input, transport);

/** `GET /runs/{run_id}` - Read a run and its terminal scientific result, when present */
export const getRun = (input = {}, transport) =>
  buildRequest(OPERATIONS.getRun, input, transport);

/** `GET /runs/{run_id}/events` - Read ordered run events; JSON polling is canonical and SSE is a projection */
export const getRunEvents = (input = {}, transport) =>
  buildRequest(OPERATIONS.getRunEvents, input, transport);

/** `GET /evolution-runs/{evolution_run_id}/candidates` - List candidates using snapshot-bound cursor pagination */
export const listEvolutionCandidates = (input = {}, transport) =>
  buildRequest(OPERATIONS.listEvolutionCandidates, input, transport);

/** `GET /runs` - List runs using snapshot-bound cursor pagination */
export const listRuns = (input = {}, transport) =>
  buildRequest(OPERATIONS.listRuns, input, transport);

/** `POST /runs/{run_id}/actions/pause` - Request an expected-revision pause transition */
export const pauseRun = (input = {}, transport) =>
  buildRequest(OPERATIONS.pauseRun, input, transport);

/** `POST /documents` - Register one already-staged source artifact */
export const registerDocument = (input = {}, transport) =>
  buildRequest(OPERATIONS.registerDocument, input, transport);

/** `POST /candidates/{candidate_id}/promotion-requests` - Map a sealed promotion request to ActionIntent(request_promotion) */
export const requestCandidatePromotion = (input = {}, transport) =>
  buildRequest(OPERATIONS.requestCandidatePromotion, input, transport);

/** `POST /runs/{run_id}/actions/resume` - Request an expected-revision resume transition */
export const resumeRun = (input = {}, transport) =>
  buildRequest(OPERATIONS.resumeRun, input, transport);
