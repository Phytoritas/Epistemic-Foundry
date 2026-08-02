// Structural invariants of the canonical OpenAPI document and of the route
// table projected from it.  Counts are pinned deliberately: a route appearing
// or disappearing is a contract change, and it should fail here rather than
// pass quietly because the assertion said "at least one".

import assert from "node:assert/strict";
import test from "node:test";

import {
  BODILESS_STATUS_CODES,
  CANONICAL_OPENAPI_PATH,
  FINDING_CODES,
  HTTP_METHODS,
  PATH_ITEM_FIELDS,
  loadRouteTable,
  parseYamlSubset,
  readRepositoryDocument,
} from "./index.mjs";

const TABLE = loadRouteTable();
const DOCUMENT = parseYamlSubset(readRepositoryDocument(CANONICAL_OPENAPI_PATH).text);

/** Every operationId the canonical document declares, in projected order. */
const EXPECTED_OPERATION_IDS = [
  "cancelRun",
  "createApproval",
  "createDeliberationRun",
  "createEvolutionRun",
  "createReplicationRun",
  "createRetrievalRun",
  "createRun",
  "createValidationRun",
  "getAdjudication",
  "getApproval",
  "getArtifact",
  "getArtifactContent",
  "getCandidate",
  "getCapabilities",
  "getClaim",
  "getCoverageSnapshot",
  "getDocument",
  "getEvidence",
  "getEvidencePack",
  "getEvolutionRun",
  "getLiveness",
  "getPassport",
  "getPromotionDecision",
  "getReadiness",
  "getReplicationResult",
  "getRun",
  "getRunEvents",
  "listEvolutionCandidates",
  "listRuns",
  "pauseRun",
  "registerDocument",
  "requestCandidatePromotion",
  "resumeRun",
];

test("the surface binds the repository-root OpenAPI document", () => {
  assert.equal(TABLE.documentPath, "openapi/epistemic-foundry-v1.openapi.yaml");
  assert.match(TABLE.documentSha256, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(TABLE.openapiVersion, "3.1.1");
  assert.equal(TABLE.apiVersion, "1.0.0");
  assert.equal(TABLE.basePath, "/api/v1");
});

test("the projection pins the declared operation count", () => {
  assert.equal(TABLE.operationCount, 33);
  assert.equal(TABLE.operations.length, 33);
  assert.deepEqual([...TABLE.operationIds], EXPECTED_OPERATION_IDS);
});

test("the projection pins the declared method and path distribution", () => {
  const byMethod = {};
  for (const row of TABLE.operations) {
    byMethod[row.method] = (byMethod[row.method] ?? 0) + 1;
  }
  assert.deepEqual(byMethod, { GET: 21, POST: 12 });
  assert.equal(new Set(TABLE.operations.map((row) => row.path)).size, 32);
  assert.equal(Object.keys(DOCUMENT.paths).length, 32);
  assert.equal(TABLE.operations.filter((row) => row.pathParameters.length > 0).length, 21);
  assert.equal(TABLE.operations.filter((row) => row.requestMediaType !== null).length, 12);
});

test("every projected row has the declared shape", () => {
  for (const row of TABLE.operations) {
    assert.ok(Object.isFrozen(row), `${row.operationId} row is not frozen`);
    assert.equal(typeof row.operationId, "string");
    assert.ok(HTTP_METHODS.includes(row.method.toLowerCase()));
    assert.ok(row.path.startsWith("/"));
    assert.ok(Array.isArray(row.pathParameters));
    assert.ok(["ref", "inline", "none"].includes(row.requestSchemaKind));
    assert.ok(["ref", "inline", "none"].includes(row.responseSchemaKind));
    assert.equal(typeof row.summary, "string");
    assert.ok(row.responses.length >= 2, `${row.operationId} declares too few responses`);
  }
});

test("every path parameter in a template is projected exactly once", () => {
  for (const row of TABLE.operations) {
    const templated = [...row.path.matchAll(/\{([A-Za-z0-9_]+)\}/gu)].map((match) => match[1]);
    assert.deepEqual([...row.pathParameters], templated, row.operationId);
    assert.equal(new Set(templated).size, templated.length, row.operationId);
  }
});

test("every operation declares a default problem response", () => {
  for (const row of TABLE.operations) {
    assert.ok(row.statusCodes.includes("default"), `${row.operationId} has no default response`);
    const fallback = row.responses.find((entry) => entry.status === "default");
    assert.equal(fallback.schemaRef, "#/components/schemas/ApiProblem", row.operationId);
    assert.equal(fallback.mediaType, "application/problem+json", row.operationId);
  }
});

test("every operation declares one success status with a described body", () => {
  for (const row of TABLE.operations) {
    assert.match(row.successStatus, /^[23][0-9]{2}$/u, row.operationId);
    const success = row.responses.find((entry) => entry.status === row.successStatus);
    assert.notEqual(success.schemaKind, "none", `${row.operationId} success body is undescribed`);
  }
});

test("a schema reference is either an internal pointer or a canonical schema file", () => {
  const references = TABLE.operations
    .flatMap((row) => [row.requestSchemaRef, row.responseSchemaRef])
    .filter((reference) => reference !== null);
  assert.equal(references.length, 42);
  for (const reference of references) {
    assert.ok(
      reference.startsWith("#/components/schemas/") ||
        /^\.\.\/schemas\/[a-z0-9-]+\.schema\.json$/u.test(reference),
      `unexpected schema reference shape: ${reference}`,
    );
  }
});

test("the accepted verb and field vocabularies are frozen and complete", () => {
  assert.ok(Object.isFrozen(HTTP_METHODS));
  assert.ok(Object.isFrozen(PATH_ITEM_FIELDS));
  assert.ok(Object.isFrozen(BODILESS_STATUS_CODES));
  assert.deepEqual(
    [...HTTP_METHODS],
    ["delete", "get", "head", "options", "patch", "post", "put", "trace"],
  );
  assert.deepEqual(
    [...PATH_ITEM_FIELDS],
    ["$ref", "description", "parameters", "servers", "summary"],
  );
});

test("every finding code states a reason long enough to stand alone", () => {
  assert.ok(Object.isFrozen(FINDING_CODES));
  const codes = Object.keys(FINDING_CODES);
  assert.equal(codes.length, 10);
  for (const code of codes) {
    assert.match(code, /^[A-Z][A-Z_]+$/u);
    assert.ok(
      FINDING_CODES[code].length > 50,
      `${code} reason is only ${FINDING_CODES[code].length} characters`,
    );
    assert.ok(FINDING_CODES[code].endsWith("."), `${code} reason is not a sentence`);
  }
  for (const required of [
    "OPERATION_ID_MISSING",
    "OPERATION_ID_DUPLICATED",
    "RESPONSE_SCHEMA_MISSING",
    "ROUTE_UNDECLARED",
  ]) {
    assert.ok(codes.includes(required), `${required} is not declared`);
  }
});

test("the surface declares no route of its own", () => {
  // The document is the declaring source.  If a path string were hard-coded in
  // the product modules, this projection could drift from the contract without
  // any test noticing, so the modules are checked for literal route text.
  const sources = [
    "./route-table.mjs",
    "./server-surface.mjs",
    "./openapi-source.mjs",
    "./yaml-subset.mjs",
  ].map((relative) => readRepositoryDocument(`packages/ui-api/src/openapi/${relative.slice(2)}`));
  for (const source of sources) {
    for (const row of TABLE.operations) {
      assert.ok(
        !source.text.includes(`"${row.path}"`) && !source.text.includes(`'${row.path}'`),
        `${source.relativePath} restates the declared path ${row.path}`,
      );
      assert.ok(
        !source.text.includes(`"${row.operationId}"`),
        `${source.relativePath} restates the declared operationId ${row.operationId}`,
      );
    }
  }
});
