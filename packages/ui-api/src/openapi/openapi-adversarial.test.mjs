// Every refusal this surface can raise, raised.
//
// A refusal code that no test reaches is a claim, not a control.  Each case
// below breaks exactly one invariant and asserts the typed code, so a future
// change that silently downgrades a refusal into a tolerated shape fails here.

import assert from "node:assert/strict";
import test from "node:test";

import * as generatedClient from "../../../../web/src/generated/ui-client/index.mjs";
import {
  FINDING_CODES,
  OpenApiSurfaceError,
  bindServerSurface,
  deriveCoverageRecord,
  loadRouteTable,
  parseYamlSubset,
  projectRouteTableFromText,
  readRepositoryDocument,
  routeFor,
} from "./index.mjs";
import {
  DANGLING_REFERENCE,
  DUPLICATED_OPERATION_ID,
  MISSING_OPERATION_ID,
  NON_OBJECT_DOCUMENT,
  NO_PATHS_DOCUMENT,
  OPERATION_WITHOUT_RESPONSES,
  RESPONSE_WITHOUT_BODY,
  RESPONSE_WITHOUT_SCHEMA,
  UNDECLARED_HTTP_VERB,
  UNSUPPORTED_YAML,
  VALID_DOCUMENT,
} from "./openapi-test-fixtures.mjs";

const TABLE = loadRouteTable();

/** Assert that `run` refuses with exactly `code`, and return the refusal. */
const refusalOf = (code, run) => {
  let raised = null;
  assert.throws(
    run,
    (error) => {
      raised = error;
      assert.ok(error instanceof OpenApiSurfaceError, `expected a typed refusal, got ${error}`);
      assert.equal(error.code, code, `expected ${code}, got ${error.code}: ${error.detail}`);
      return true;
    },
    `expected a ${code} refusal`,
  );
  return raised;
};

test("an operation without an operationId is refused", () => {
  const refusal = refusalOf("OPERATION_ID_MISSING", () =>
    projectRouteTableFromText(MISSING_OPERATION_ID),
  );
  assert.equal(refusal.context.method, "get");
  assert.equal(refusal.context.path, "/things/{thing_id}");
});

test("two operations sharing one operationId are refused", () => {
  const refusal = refusalOf("OPERATION_ID_DUPLICATED", () =>
    projectRouteTableFromText(DUPLICATED_OPERATION_ID),
  );
  assert.equal(refusal.context.operationId, "createThing");
  assert.equal(refusal.context.first, "POST /things");
  assert.equal(refusal.context.second, "GET /things/{thing_id}");
});

test("a response media type without a schema is refused", () => {
  const refusal = refusalOf("RESPONSE_SCHEMA_MISSING", () =>
    projectRouteTableFromText(RESPONSE_WITHOUT_SCHEMA),
  );
  assert.equal(refusal.context.mediaType, "application/json");
});

test("a non-bodiless response with neither $ref nor content is refused", () => {
  const refusal = refusalOf("RESPONSE_SCHEMA_MISSING", () =>
    projectRouteTableFromText(RESPONSE_WITHOUT_BODY),
  );
  assert.equal(refusal.context.status, "200");
});

test("an operation that declares no responses at all is refused", () => {
  refusalOf("RESPONSE_SCHEMA_MISSING", () =>
    projectRouteTableFromText(OPERATION_WITHOUT_RESPONSES),
  );
});

test("a bodiless redirect status is accepted rather than refused", () => {
  // `getArtifactContent` declares a 307 with headers and no body.  The
  // invariant is "an undescribed body", not "no body", and conflating the two
  // would force a fictional schema onto a redirect.
  const redirect = routeFor(TABLE, "getArtifactContent").responses.find(
    (row) => row.status === "307",
  );
  assert.equal(redirect.schemaKind, "none");
  assert.equal(redirect.responseRef, null);
});

test("a path item declaring an unknown verb is refused", () => {
  const refusal = refusalOf("HTTP_METHOD_UNDECLARED", () =>
    projectRouteTableFromText(UNDECLARED_HTTP_VERB),
  );
  assert.equal(refusal.context.key, "purge");
});

test("a dangling component reference is refused", () => {
  const refusal = refusalOf("REFERENCE_UNRESOLVABLE", () =>
    projectRouteTableFromText(DANGLING_REFERENCE),
  );
  assert.equal(refusal.context.pointer, "#/components/responses/NotDefined");
});

test("a document that is not an OpenAPI object is refused", () => {
  refusalOf("DOCUMENT_MALFORMED", () => projectRouteTableFromText(NON_OBJECT_DOCUMENT));
  refusalOf("DOCUMENT_MALFORMED", () => projectRouteTableFromText(NO_PATHS_DOCUMENT));
  refusalOf("DOCUMENT_MALFORMED", () =>
    projectRouteTableFromText("openapi: 2.0\npaths:\n  /a: {}\n"),
  );
});

test("a missing document source is refused rather than defaulted", () => {
  const refusal = refusalOf("DOCUMENT_SOURCE_MISSING", () =>
    readRepositoryDocument("openapi/no-such-document.openapi.yaml"),
  );
  assert.equal(refusal.context.relativePath, "openapi/no-such-document.openapi.yaml");
});

test("every YAML construct outside the accepted subset is refused, not guessed", () => {
  for (const [name, source] of Object.entries(UNSUPPORTED_YAML)) {
    refusalOf("YAML_CONSTRUCT_UNSUPPORTED", () => parseYamlSubset(source), name);
  }
  assert.equal(Object.keys(UNSUPPORTED_YAML).length, 9);
});

test("a handler for an operation the document does not declare is refused", () => {
  const refusal = refusalOf("ROUTE_UNDECLARED", () =>
    bindServerSurface(TABLE, { deleteEverything: () => null, getRun: () => null }),
  );
  assert.deepEqual(refusal.context.undeclaredOperationIds, ["deleteEverything"]);
  assert.equal(refusal.context.documentPath, TABLE.documentPath);
});

test("dispatching or resolving an undeclared operation is refused", () => {
  const surface = bindServerSurface(TABLE, { getRun: () => null });
  refusalOf("ROUTE_UNDECLARED", () => surface.dispatch("deleteEverything", {}));
  refusalOf("ROUTE_UNDECLARED", () => surface.routeFor("deleteEverything"));
  refusalOf("ROUTE_UNDECLARED", () => routeFor(TABLE, "deleteEverything"));
});

test("a handler entry that is not callable is refused at composition time", () => {
  const refusal = refusalOf("HANDLER_INVALID", () =>
    bindServerSurface(TABLE, { getRun: "not a function" }),
  );
  assert.equal(refusal.context.operationId, "getRun");
  refusalOf("HANDLER_INVALID", () => deriveCoverageRecord(TABLE, []));
  refusalOf("HANDLER_INVALID", () => deriveCoverageRecord(TABLE, null));
});

test("a refusal is frozen and carries its standing reason", () => {
  const refusal = refusalOf("ROUTE_UNDECLARED", () => routeFor(TABLE, "nope"));
  assert.ok(Object.isFrozen(refusal));
  assert.ok(Object.isFrozen(refusal.context));
  assert.equal(refusal.name, "OpenApiSurfaceError");
  assert.equal(refusal.reason, FINDING_CODES.ROUTE_UNDECLARED);
  assert.match(refusal.message, /^ROUTE_UNDECLARED: /u);
  assert.throws(
    () => new OpenApiSurfaceError("NOT_A_DECLARED_CODE", "detail"),
    /unknown OpenAPI surface finding code/u,
  );
});

test("a fixture that breaks nothing still projects", () => {
  // The adversarial fixtures share a base document; if that base were itself
  // invalid, every case above would pass for the wrong reason.
  const table = projectRouteTableFromText(VALID_DOCUMENT);
  assert.equal(table.operationCount, 2);
});

test("the generated client refuses malformed input rather than sending it", () => {
  const codes = [];
  const expectClientRefusal = (run) => {
    assert.throws(run, (error) => {
      assert.equal(error.name, "UiClientError");
      assert.ok(error.reason.length > 50, `${error.code} reason is too short to stand alone`);
      assert.ok(Object.isFrozen(error));
      codes.push(error.code);
      return true;
    });
  };
  expectClientRefusal(() => generatedClient.getRun({}));
  expectClientRefusal(() => generatedClient.getRun({ path: { run_id: "R", extra: "x" } }));
  expectClientRefusal(() => generatedClient.createRun({}));
  expectClientRefusal(() => generatedClient.getLiveness({ body: {} }));
  expectClientRefusal(() => generatedClient.listRuns({ query: { limit: {} } }));
  expectClientRefusal(() => generatedClient.getRun({ path: { run_id: "R" } }, "not callable"));
  assert.deepEqual(codes.sort(), [
    "PATH_PARAMETER_MISSING",
    "PATH_PARAMETER_UNKNOWN",
    "QUERY_PARAMETER_INVALID",
    "REQUEST_BODY_MISSING",
    "REQUEST_BODY_UNEXPECTED",
    "TRANSPORT_INVALID",
  ]);
  assert.deepEqual(
    Object.keys(generatedClient.UI_CLIENT_FINDING_CODES).sort(),
    [...codes].sort(),
  );
});
