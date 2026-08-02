// The contract between the declaring document, the server-side dispatch
// table, and the generated client.
//
// The projection is not compared against a restated expectation here: the
// document is walked again, independently of the projector, and the two
// results must agree exactly in both directions.  The generated client is
// checked the same way, so an operation can only reach a caller if the
// document declares it and the server binding can see it.

import assert from "node:assert/strict";
import test from "node:test";

import * as generatedClient from "../../../../web/src/generated/ui-client/index.mjs";
import {
  CANONICAL_OPENAPI_PATH,
  COVERAGE_STATES,
  HTTP_METHODS,
  OpenApiSurfaceError,
  bindServerSurface,
  loadRouteTable,
  parseYamlSubset,
  projectRouteTableFromText,
  readRepositoryDocument,
  routeFor,
} from "./index.mjs";
import { VALID_DOCUMENT } from "./openapi-test-fixtures.mjs";

const TABLE = loadRouteTable();
const DOCUMENT = parseYamlSubset(readRepositoryDocument(CANONICAL_OPENAPI_PATH).text);

/** Walk the document without the projector and list what it declares. */
const declaredByDocument = () => {
  const declared = [];
  for (const [path, pathItem] of Object.entries(DOCUMENT.paths)) {
    for (const [key, operation] of Object.entries(pathItem)) {
      if (!HTTP_METHODS.includes(key)) continue;
      declared.push({
        method: key.toUpperCase(),
        operationId: operation.operationId,
        path,
        summary: operation.summary ?? "",
      });
    }
  }
  return declared.sort((left, right) => (left.operationId < right.operationId ? -1 : 1));
};

const everyHandler = () =>
  Object.fromEntries(TABLE.operationIds.map((name) => [name, () => name]));

test("the projection and the document declare exactly the same operations", () => {
  const declared = declaredByDocument();
  assert.equal(declared.length, TABLE.operationCount);
  assert.deepEqual(
    TABLE.operations.map((row) => ({
      method: row.method,
      operationId: row.operationId,
      path: row.path,
      summary: row.summary,
    })),
    declared,
  );
});

test("the projection resolves component references the document indirects through", () => {
  // `pauseRun` reaches its request body through `#/components/requestBodies`
  // and its success response through `#/components/responses`; both have to
  // land on the schema the component names, not on the pointer itself.
  const pause = routeFor(TABLE, "pauseRun");
  const requestBody =
    DOCUMENT.components.requestBodies[
      DOCUMENT.paths[pause.path].post.requestBody.$ref.split("/").at(-1)
    ];
  assert.equal(
    pause.requestSchemaRef,
    requestBody.content["application/json"].schema.$ref,
  );
  assert.equal(pause.requestRequired, requestBody.required);
  const accepted =
    DOCUMENT.components.responses[
      DOCUMENT.paths[pause.path].post.responses["202"].$ref.split("/").at(-1)
    ];
  assert.equal(pause.responseSchemaRef, accepted.content["application/json"].schema.$ref);
  assert.equal(pause.successStatus, "202");
});

test("an inline composed response schema is projected as inline, not invented", () => {
  const evolutionRun = routeFor(TABLE, "getEvolutionRun");
  assert.equal(evolutionRun.responseSchemaKind, "inline");
  assert.equal(evolutionRun.responseSchemaRef, null);
  assert.ok(
    Array.isArray(
      DOCUMENT.paths[evolutionRun.path].get.responses["200"].content["application/json"].schema
        .allOf,
    ),
  );
});

test("a complete handler map covers the surface with no gap", () => {
  const surface = bindServerSurface(TABLE, everyHandler());
  assert.equal(surface.coverage.coverageState, COVERAGE_STATES.COMPLETE);
  assert.equal(surface.coverage.boundOperationCount, 33);
  assert.equal(surface.coverage.missingOperationCount, 0);
  assert.deepEqual([...surface.coverage.missingOperationIds], []);
  assert.deepEqual([...surface.coverage.boundOperationIds], [...TABLE.operationIds]);
  assert.ok(Object.isFrozen(surface.coverage));
});

test("a declared operation with no handler is listed rather than tolerated", () => {
  const handlers = everyHandler();
  delete handlers.cancelRun;
  delete handlers.getRunEvents;
  const surface = bindServerSurface(TABLE, handlers);
  assert.equal(surface.coverage.coverageState, COVERAGE_STATES.PARTIAL);
  assert.equal(surface.coverage.boundOperationCount, 31);
  assert.deepEqual([...surface.coverage.missingOperationIds], ["cancelRun", "getRunEvents"]);
  assert.equal(surface.isBound("cancelRun"), false);
  assert.throws(() => surface.dispatch("cancelRun", {}), (error) => {
    assert.ok(error instanceof OpenApiSurfaceError);
    assert.equal(error.code, "ROUTE_UNDECLARED");
    return true;
  });
});

test("dispatch hands the handler the route the document declares", () => {
  const seen = [];
  const surface = bindServerSurface(TABLE, {
    getRun: (request, route) => {
      seen.push({ request, route });
      return "handled";
    },
  });
  assert.equal(surface.dispatch("getRun", { runId: "RUN-1" }), "handled");
  assert.equal(seen.length, 1);
  assert.deepEqual(seen[0].request, { runId: "RUN-1" });
  assert.equal(seen[0].route.method, "GET");
  assert.equal(seen[0].route.path, "/runs/{run_id}");
  assert.equal(seen[0].route.responseSchemaRef, "#/components/schemas/RunView");
});

test("the generated client exports exactly one function per declared operation", () => {
  assert.deepEqual([...generatedClient.OPERATION_IDS], [...TABLE.operationIds]);
  const exportedFunctions = Object.keys(generatedClient)
    .filter((name) => typeof generatedClient[name] === "function")
    .filter((name) => name !== "UiClientError")
    .sort();
  assert.deepEqual(exportedFunctions, [...TABLE.operationIds]);
  assert.equal(exportedFunctions.length, 33);
});

test("the generated client bakes the same route rows the server projects", () => {
  assert.equal(generatedClient.BASE_PATH, TABLE.basePath);
  assert.equal(generatedClient.SOURCE_DOCUMENT.path, TABLE.documentPath);
  assert.equal(generatedClient.SOURCE_DOCUMENT.sha256, TABLE.documentSha256);
  assert.equal(generatedClient.SOURCE_DOCUMENT.routeTableSha256, TABLE.routeTableSha256);
  assert.equal(generatedClient.SOURCE_DOCUMENT.operationCount, TABLE.operationCount);
  for (const row of TABLE.operations) {
    assert.deepEqual(
      JSON.parse(JSON.stringify(generatedClient.OPERATIONS[row.operationId])),
      JSON.parse(JSON.stringify(row)),
      row.operationId,
    );
  }
});

test("each client function bakes its own method and path template", () => {
  for (const row of TABLE.operations) {
    const input = {
      path: Object.fromEntries(row.pathParameters.map((name) => [name, `${name}-value`])),
      ...(row.requestRequired ? { body: {} } : {}),
    };
    const descriptor = generatedClient[row.operationId](input);
    assert.equal(descriptor.method, row.method, row.operationId);
    assert.equal(descriptor.pathTemplate, row.path, row.operationId);
    assert.equal(descriptor.operationId, row.operationId, row.operationId);
    assert.equal(descriptor.responseSchemaRef, row.responseSchemaRef, row.operationId);
    assert.ok(descriptor.url.startsWith(`${TABLE.basePath}/`), row.operationId);
    assert.ok(!descriptor.url.includes("{"), `${row.operationId} left a placeholder unresolved`);
    assert.ok(Object.isFrozen(descriptor), row.operationId);
  }
});

test("the client builds a deterministic URL from path and query values", () => {
  const listed = generatedClient.listRuns({
    query: { limit: 50, snapshot_id: "SNAP-1", cursor: "c/1", skipped: undefined },
  });
  assert.equal(listed.url, "/api/v1/runs?cursor=c%2F1&limit=50&snapshot_id=SNAP-1");
  const events = generatedClient.getRunEvents({ path: { run_id: "RUN/1" } });
  assert.equal(events.url, "/api/v1/runs/RUN%2F1/events");
  assert.equal(
    generatedClient.listRuns({ query: { limit: 50, cursor: "a" } }).url,
    generatedClient.listRuns({ query: { cursor: "a", limit: 50 } }).url,
  );
});

test("the client hands its descriptor to an injected transport and performs no I/O itself", () => {
  const calls = [];
  const result = generatedClient.getRun({ path: { run_id: "RUN-1" } }, (descriptor) => {
    calls.push(descriptor);
    return { status: 200 };
  });
  assert.deepEqual(result, { status: 200 });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/runs/RUN-1");
  assert.equal(generatedClient.getRun({ path: { run_id: "RUN-1" } }).body, null);
});

test("a request body is sent only where the document declares one", () => {
  const created = generatedClient.createRun({ body: { plan: "P" } });
  assert.deepEqual(created.body, { plan: "P" });
  assert.equal(created.headers["content-type"], "application/json");
  assert.equal(created.requestSchemaRef, "../schemas/run-spec.schema.json");
  const live = generatedClient.getLiveness();
  assert.equal(live.body, null);
  assert.equal(live.requestSchemaRef, null);
  assert.deepEqual(live.headers, {});
});

test("the projector is document-shaped, not canonical-document-shaped", () => {
  // The same projector has to work on any conforming document, or the
  // invariants it enforces would only be true of one file.
  const fixture = projectRouteTableFromText(VALID_DOCUMENT, "fixture.yaml");
  assert.equal(fixture.operationCount, 2);
  assert.deepEqual([...fixture.operationIds], ["createThing", "getThing"]);
  assert.equal(fixture.basePath, "/fixture/v9");
  assert.equal(routeFor(fixture, "getThing").pathParameters[0], "thing_id");
  assert.notEqual(fixture.routeTableSha256, TABLE.routeTableSha256);
});
