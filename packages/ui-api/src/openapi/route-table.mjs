// Project the canonical OpenAPI document into a typed route table.
//
// The document is the declaring source.  Nothing in this file restates a path,
// a method, an operation name or a schema reference: every row is read out of
// the document, and any structural invariant the document breaks is a typed
// refusal rather than a row this surface quietly drops.
//
// Structural invariants enforced here:
//   1. every path item key is a documented path-item field, an `x-` extension,
//      or an HTTP method this surface accepts;
//   2. every operation carries a non-empty, unique operationId;
//   3. every declared response either references a component response or
//      declares a schema for each media type it serves, unless its status code
//      is one HTTP defines as carrying no body.

import { canonicalJsonSha256 } from "./canonical-hash.mjs";
import { refuse } from "./surface-errors.mjs";

/** HTTP methods an OpenAPI 3.1 path item may declare. */
export const HTTP_METHODS = Object.freeze([
  "delete",
  "get",
  "head",
  "options",
  "patch",
  "post",
  "put",
  "trace",
]);

/** Path-item fields that are not operations. */
export const PATH_ITEM_FIELDS = Object.freeze([
  "$ref",
  "description",
  "parameters",
  "servers",
  "summary",
]);

/** Status codes HTTP defines as carrying no response body. */
export const BODILESS_STATUS_CODES = Object.freeze([
  "204",
  "205",
  "301",
  "302",
  "303",
  "304",
  "307",
  "308",
]);

const PATH_PARAMETER_PATTERN = /\{([A-Za-z0-9_]+)\}/gu;
const SUCCESS_STATUS_PATTERN = /^[23][0-9]{2}$/u;

const isPlainObject = (value) =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Follow one `#/components/...` pointer, refusing a dangling one. */
const resolveLocalReference = (document, pointer, where) => {
  if (!pointer.startsWith("#/")) {
    refuse("REFERENCE_UNRESOLVABLE", `${where} uses non-local reference ${pointer}`, {
      pointer,
      where,
    });
  }
  let node = document;
  for (const rawSegment of pointer.slice(2).split("/")) {
    const segment = rawSegment.replaceAll("~1", "/").replaceAll("~0", "~");
    if (!isPlainObject(node) || !Object.hasOwn(node, segment)) {
      refuse("REFERENCE_UNRESOLVABLE", `${where} references missing component ${pointer}`, {
        pointer,
        where,
      });
    }
    node = node[segment];
  }
  return node;
};

/** Resolve a node that may itself be a `$ref`, once. */
const dereference = (document, node, where) => {
  if (isPlainObject(node) && typeof node.$ref === "string") {
    return { ref: node.$ref, value: resolveLocalReference(document, node.$ref, where) };
  }
  return { ref: null, value: node };
};

/**
 * Read the schema reference for one media-type map.
 *
 * @returns {{kind: "ref"|"inline"|"none", mediaType: string|null, ref: string|null}}
 */
const readContentSchema = (content, where) => {
  if (content === undefined || content === null) {
    return { kind: "none", mediaType: null, ref: null };
  }
  if (!isPlainObject(content)) {
    refuse("DOCUMENT_MALFORMED", `${where} content is not a media-type object`, { where });
  }
  const mediaTypes = Object.keys(content);
  if (mediaTypes.length === 0) {
    refuse("RESPONSE_SCHEMA_MISSING", `${where} declares content with no media type`, { where });
  }
  for (const mediaType of mediaTypes) {
    const entry = content[mediaType];
    if (!isPlainObject(entry) || !isPlainObject(entry.schema)) {
      refuse("RESPONSE_SCHEMA_MISSING", `${where} media type ${mediaType} declares no schema`, {
        mediaType,
        where,
      });
    }
  }
  const primary = mediaTypes[0];
  const schema = content[primary].schema;
  return {
    kind: typeof schema.$ref === "string" ? "ref" : "inline",
    mediaType: primary,
    ref: typeof schema.$ref === "string" ? schema.$ref : null,
  };
};

const projectResponses = (document, responses, where) => {
  if (!isPlainObject(responses) || Object.keys(responses).length === 0) {
    refuse("RESPONSE_SCHEMA_MISSING", `${where} declares no responses`, { where });
  }
  const rows = [];
  for (const status of Object.keys(responses)) {
    const label = `${where} response ${status}`;
    const { ref, value } = dereference(document, responses[status], label);
    if (!isPlainObject(value)) {
      refuse("DOCUMENT_MALFORMED", `${label} is not a response object`, { status, where });
    }
    const hasContent = Object.hasOwn(value, "content");
    if (!hasContent && ref === null && !BODILESS_STATUS_CODES.includes(status)) {
      refuse("RESPONSE_SCHEMA_MISSING", `${label} declares neither $ref nor content`, {
        status,
        where,
      });
    }
    const schema = hasContent
      ? readContentSchema(value.content, label)
      : { kind: "none", mediaType: null, ref: null };
    rows.push(
      Object.freeze({
        mediaType: schema.mediaType,
        responseRef: ref,
        schemaKind: schema.kind,
        schemaRef: schema.ref,
        status,
      }),
    );
  }
  return Object.freeze(rows);
};

const projectRequestBody = (document, operation, where) => {
  if (!Object.hasOwn(operation, "requestBody")) {
    return { mediaType: null, ref: null, required: false, schemaKind: "none", schemaRef: null };
  }
  const label = `${where} requestBody`;
  const { ref, value } = dereference(document, operation.requestBody, label);
  if (!isPlainObject(value)) {
    refuse("DOCUMENT_MALFORMED", `${label} is not a request body object`, { where });
  }
  const schema = readContentSchema(value.content, label);
  if (schema.kind === "none") {
    refuse("DOCUMENT_MALFORMED", `${label} declares no content`, { where });
  }
  return {
    mediaType: schema.mediaType,
    ref,
    required: value.required === true,
    schemaKind: schema.kind,
    schemaRef: schema.ref,
  };
};

const pathParametersOf = (path) =>
  Object.freeze([...path.matchAll(PATH_PARAMETER_PATTERN)].map((match) => match[1]));

const pickSuccessStatus = (responses) => {
  const successes = responses
    .map((row) => row.status)
    .filter((status) => SUCCESS_STATUS_PATTERN.test(status))
    .sort();
  return successes.length === 0 ? null : successes[0];
};

/**
 * Project a parsed OpenAPI document into an immutable route table.
 *
 * @param {unknown} document parsed canonical OpenAPI document
 * @param {{documentPath: string, documentSha256: string}} provenance
 */
export const projectRouteTable = (document, provenance) => {
  if (!isPlainObject(document)) {
    refuse("DOCUMENT_MALFORMED", "the canonical OpenAPI document is not an object");
  }
  if (typeof document.openapi !== "string" || !document.openapi.startsWith("3.")) {
    refuse("DOCUMENT_MALFORMED", "the document declares no OpenAPI 3.x version", {
      openapi: document.openapi ?? null,
    });
  }
  if (!isPlainObject(document.paths) || Object.keys(document.paths).length === 0) {
    refuse("DOCUMENT_MALFORMED", "the document declares no paths object");
  }

  const operations = [];
  const seen = new Map();
  for (const path of Object.keys(document.paths)) {
    if (!path.startsWith("/")) {
      refuse("DOCUMENT_MALFORMED", `path key ${path} does not start with '/'`, { path });
    }
    const pathItem = document.paths[path];
    if (!isPlainObject(pathItem)) {
      refuse("DOCUMENT_MALFORMED", `path item ${path} is not an object`, { path });
    }
    for (const key of Object.keys(pathItem)) {
      if (key.startsWith("x-") || PATH_ITEM_FIELDS.includes(key)) continue;
      if (!HTTP_METHODS.includes(key)) {
        refuse("HTTP_METHOD_UNDECLARED", `path ${path} declares unknown path-item key ${key}`, {
          key,
          path,
        });
      }
      const operation = pathItem[key];
      const where = `${key.toUpperCase()} ${path}`;
      if (!isPlainObject(operation)) {
        refuse("DOCUMENT_MALFORMED", `${where} is not an operation object`, { method: key, path });
      }
      const operationId = operation.operationId;
      if (typeof operationId !== "string" || operationId.trim() === "") {
        refuse("OPERATION_ID_MISSING", `${where} declares no operationId`, {
          method: key,
          path,
        });
      }
      if (seen.has(operationId)) {
        refuse(
          "OPERATION_ID_DUPLICATED",
          `operationId ${operationId} is declared by ${seen.get(operationId)} and ${where}`,
          { first: seen.get(operationId), operationId, second: where },
        );
      }
      seen.set(operationId, where);
      const responses = projectResponses(document, operation.responses, where);
      const request = projectRequestBody(document, operation, where);
      const successStatus = pickSuccessStatus(responses);
      const success = responses.find((row) => row.status === successStatus) ?? null;
      operations.push(
        Object.freeze({
          method: key.toUpperCase(),
          operationId,
          path,
          pathParameters: pathParametersOf(path),
          requestMediaType: request.mediaType,
          requestRequired: request.required,
          requestSchemaKind: request.schemaKind,
          requestSchemaRef: request.schemaRef,
          responseMediaType: success === null ? null : success.mediaType,
          responseSchemaKind: success === null ? "none" : success.schemaKind,
          responseSchemaRef: success === null ? null : success.schemaRef,
          responses,
          statusCodes: Object.freeze(responses.map((row) => row.status)),
          successStatus,
          summary: typeof operation.summary === "string" ? operation.summary : "",
          tags: Object.freeze(Array.isArray(operation.tags) ? [...operation.tags] : []),
        }),
      );
    }
  }

  operations.sort((left, right) => (left.operationId < right.operationId ? -1 : 1));
  const servers = Array.isArray(document.servers) ? document.servers : [];
  const basePath =
    servers.length > 0 && isPlainObject(servers[0]) && typeof servers[0].url === "string"
      ? servers[0].url
      : "";
  const table = {
    apiVersion: isPlainObject(document.info) ? String(document.info.version ?? "") : "",
    basePath,
    documentPath: provenance.documentPath,
    documentSha256: provenance.documentSha256,
    openapiVersion: document.openapi,
    operationCount: operations.length,
    operationIds: Object.freeze(operations.map((row) => row.operationId)),
    operations: Object.freeze(operations),
  };
  return Object.freeze({ ...table, routeTableSha256: canonicalJsonSha256(table) });
};

/**
 * Find one projected route by operationId.
 *
 * @param {ReturnType<typeof projectRouteTable>} table
 * @param {string} operationId
 */
export const routeFor = (table, operationId) => {
  const row = table.operations.find((entry) => entry.operationId === operationId);
  if (row === undefined) {
    refuse("ROUTE_UNDECLARED", `no declared operation is named ${String(operationId)}`, {
      documentPath: table.documentPath,
      operationId,
    });
  }
  return row;
};
