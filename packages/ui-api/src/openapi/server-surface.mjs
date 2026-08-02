// Bind handlers to the OpenAPI-derived route table.
//
// This is a dispatch table, not an HTTP server.  It owns exactly one question:
// does the set of registered handlers correspond, operation for operation, to
// the set of operations the canonical document declares?  A handler for an
// operation the document does not declare is refused outright; a declared
// operation with no handler is recorded as a named gap in an immutable
// coverage record rather than discovered later as a 404 in production.
//
// The coverage record carries its own digest and is re-derivable: hashing the
// record with `coverageSha256` removed must reproduce `coverageSha256`.

import { canonicalJsonSha256 } from "./canonical-hash.mjs";
import { refuse } from "./surface-errors.mjs";

/** Coverage states a binding can be in. */
export const COVERAGE_STATES = Object.freeze({
  COMPLETE: "COMPLETE",
  PARTIAL: "PARTIAL",
});

const readHandlerNames = (handlers) => {
  if (typeof handlers !== "object" || handlers === null || Array.isArray(handlers)) {
    refuse("HANDLER_INVALID", "the handler map must be a plain object keyed by operationId");
  }
  return Object.keys(handlers).sort();
};

/**
 * Build the immutable coverage record for a handler map.
 *
 * @param {import("./route-table.mjs").projectRouteTable extends never ? never : any} table
 * @param {Record<string, Function>} handlers
 */
export const deriveCoverageRecord = (table, handlers) => {
  const registered = readHandlerNames(handlers);
  const declared = new Set(table.operationIds);
  const undeclared = registered.filter((name) => !declared.has(name));
  if (undeclared.length > 0) {
    refuse(
      "ROUTE_UNDECLARED",
      `handlers registered for undeclared operations: ${undeclared.join(", ")}`,
      { documentPath: table.documentPath, undeclaredOperationIds: undeclared },
    );
  }
  for (const name of registered) {
    if (typeof handlers[name] !== "function") {
      refuse("HANDLER_INVALID", `handler for ${name} is a ${typeof handlers[name]}, not a function`, {
        operationId: name,
      });
    }
  }
  const bound = registered;
  const missing = [...table.operationIds].filter((name) => !registered.includes(name)).sort();
  const preimage = {
    boundOperationCount: bound.length,
    boundOperationIds: bound,
    coverageState: missing.length === 0 ? COVERAGE_STATES.COMPLETE : COVERAGE_STATES.PARTIAL,
    declaredOperationCount: table.operationCount,
    documentPath: table.documentPath,
    documentSha256: table.documentSha256,
    missingOperationCount: missing.length,
    missingOperationIds: missing,
    routeTableSha256: table.routeTableSha256,
  };
  return Object.freeze({
    ...preimage,
    boundOperationIds: Object.freeze(bound),
    coverageSha256: canonicalJsonSha256(preimage),
    missingOperationIds: Object.freeze(missing),
  });
};

/**
 * Recompute the digest of a coverage record from the record itself.
 *
 * @param {ReturnType<typeof deriveCoverageRecord>} record
 */
export const recomputeCoverageSha256 = (record) => {
  const { coverageSha256: _ignored, ...preimage } = record;
  return canonicalJsonSha256({
    ...preimage,
    boundOperationIds: [...preimage.boundOperationIds],
    missingOperationIds: [...preimage.missingOperationIds],
  });
};

/**
 * Bind a handler map to the route table and return the dispatch surface.
 *
 * The returned object never performs I/O: `dispatch` looks a route up by
 * operationId, hands the declared route row to the handler, and returns what
 * the handler returned.  Transport lives outside this component.
 *
 * @param {any} table
 * @param {Record<string, Function>} handlers
 */
export const bindServerSurface = (table, handlers) => {
  const coverage = deriveCoverageRecord(table, handlers);
  const routes = new Map(table.operations.map((row) => [row.operationId, row]));
  const bound = new Map(coverage.boundOperationIds.map((name) => [name, handlers[name]]));

  const dispatch = (operationId, request) => {
    const route = routes.get(operationId);
    if (route === undefined) {
      refuse("ROUTE_UNDECLARED", `no declared operation is named ${String(operationId)}`, {
        documentPath: table.documentPath,
        operationId,
      });
    }
    const handler = bound.get(operationId);
    if (handler === undefined) {
      refuse("ROUTE_UNDECLARED", `declared operation ${operationId} has no bound handler`, {
        documentPath: table.documentPath,
        operationId,
      });
    }
    return handler(request, route);
  };

  return Object.freeze({
    coverage,
    dispatch,
    isBound: (operationId) => bound.has(operationId),
    routeFor: (operationId) => {
      const route = routes.get(operationId);
      if (route === undefined) {
        refuse("ROUTE_UNDECLARED", `no declared operation is named ${String(operationId)}`, {
          documentPath: table.documentPath,
          operationId,
        });
      }
      return route;
    },
    table,
  });
};
