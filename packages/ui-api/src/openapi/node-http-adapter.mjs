// A deliberately narrow Node HTTP transport for the one canonical public
// constant operation. Importing this module performs no I/O and creates no
// server; all source reads, derivation, binding and construction happen inside
// the factory.

import { createServer as createHttpServer } from "node:http";
import { isIP } from "node:net";

import {
  CANONICAL_OPENAPI_PATH,
  readRepositoryDocument,
} from "./openapi-source.mjs";
import { BODILESS_STATUS_CODES, projectRouteTable } from "./route-table.mjs";
import { bindServerSurface, COVERAGE_STATES } from "./server-surface.mjs";
import { parseYamlSubset } from "./yaml-subset.mjs";

const MAX_REFERENCE_DEPTH = 32;
const MAX_SCHEMA_DEPTH = 64;
const MAX_POINTER_SEGMENTS = 64;

const HEADERS_TIMEOUT_MS = 5_000;
const REQUEST_TIMEOUT_MS = 5_000;
const KEEP_ALIVE_TIMEOUT_MS = 1_000;
const SOCKET_TIMEOUT_MS = 5_000;
const MAX_HEADER_SIZE_BYTES = 8_192;
const MAX_HEADERS_COUNT = 32;
const MAX_REQUESTS_PER_SOCKET = 16;
const MAX_CONNECTIONS = 64;

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 0;

const FORBIDDEN_REQUEST_HEADERS = Object.freeze([
  "content-length",
  "expect",
  "trailer",
  "transfer-encoding",
]);

const SCHEMA_KEYS = Object.freeze([
  "$anchor",
  "$comment",
  "$defs",
  "$id",
  "$ref",
  "$schema",
  "additionalProperties",
  "allOf",
  "anyOf",
  "const",
  "default",
  "deprecated",
  "description",
  "enum",
  "example",
  "examples",
  "exclusiveMaximum",
  "exclusiveMinimum",
  "items",
  "maxItems",
  "maxLength",
  "maxProperties",
  "maximum",
  "minItems",
  "minLength",
  "minProperties",
  "minimum",
  "multipleOf",
  "not",
  "oneOf",
  "prefixItems",
  "properties",
  "readOnly",
  "required",
  "title",
  "type",
  "uniqueItems",
  "writeOnly",
]);

const ANNOTATION_SCHEMA_KEYS = Object.freeze([
  "$anchor",
  "$comment",
  "$defs",
  "$id",
  "$schema",
  "default",
  "deprecated",
  "description",
  "example",
  "examples",
  "readOnly",
  "title",
  "writeOnly",
]);

const NO_SINGLETON = Symbol("NO_SINGLETON");
const UNKNOWN_VALIDITY = Symbol("UNKNOWN_VALIDITY");

const isRecord = (value) => {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
};

const configurationFailure = (detail, cause = undefined) => {
  const error = new Error(`Node HTTP liveness adapter refused configuration: ${detail}`);
  error.name = "NodeHttpLivenessAdapterError";
  if (cause !== undefined) error.cause = cause;
  return error;
};

const refuseConfiguration = (detail, cause = undefined) => {
  throw configurationFailure(detail, cause);
};

const ownDataKeys = (value) => {
  let keys;
  let descriptors;
  try {
    keys = Reflect.ownKeys(value);
    descriptors = Object.getOwnPropertyDescriptors(value);
  } catch (error) {
    refuseConfiguration("a value could not be inspected as ordinary data", error);
  }
  if (keys.some((key) => typeof key !== "string")) {
    refuseConfiguration("symbol-keyed values are not accepted as canonical JSON data");
  }
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (
      descriptor === undefined ||
      descriptor.enumerable !== true ||
      !Object.hasOwn(descriptor, "value")
    ) {
      refuseConfiguration("canonical JSON objects must contain enumerable data properties only");
    }
  }
  return { descriptors, keys };
};

const canonicalJson = (value, seen = new Set(), depth = 0) => {
  if (depth > MAX_SCHEMA_DEPTH) {
    refuseConfiguration("canonical JSON data exceeds the nesting bound");
  }
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      refuseConfiguration("canonical JSON data contains a non-finite number");
    }
    return JSON.stringify(value);
  }
  if (typeof value !== "object") {
    refuseConfiguration(`canonical JSON data contains a ${typeof value} value`);
  }
  if (seen.has(value)) refuseConfiguration("canonical JSON data contains a cycle");
  const nextSeen = new Set(seen);
  nextSeen.add(value);

  if (Array.isArray(value)) {
    const keys = Reflect.ownKeys(value);
    const allowed = new Set(["length"]);
    const values = [];
    for (let index = 0; index < value.length; index += 1) {
      const key = String(index);
      allowed.add(key);
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (
        descriptor === undefined ||
        descriptor.enumerable !== true ||
        !Object.hasOwn(descriptor, "value")
      ) {
        refuseConfiguration("canonical JSON arrays must be dense data arrays");
      }
      values.push(canonicalJson(descriptor.value, nextSeen, depth + 1));
    }
    if (keys.some((key) => typeof key !== "string" || !allowed.has(key))) {
      refuseConfiguration("canonical JSON arrays cannot carry extra properties");
    }
    return `[${values.join(",")}]`;
  }

  if (!isRecord(value)) {
    refuseConfiguration("canonical JSON objects must have an ordinary object prototype");
  }
  const { descriptors, keys } = ownDataKeys(value);
  keys.sort();
  return `{${keys
    .map(
      (key) =>
        `${JSON.stringify(key)}:${canonicalJson(descriptors[key].value, nextSeen, depth + 1)}`,
    )
    .join(",")}}`;
};

const copyAndFreezeJson = (value, depth = 0) => {
  if (depth > MAX_SCHEMA_DEPTH) refuseConfiguration("canonical JSON data exceeds the copy bound");
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) refuseConfiguration("a response value is not JSON-safe");
    return Object.is(value, -0) ? 0 : value;
  }
  if (Array.isArray(value)) {
    const copy = value.map((entry) => copyAndFreezeJson(entry, depth + 1));
    return Object.freeze(copy);
  }
  if (!isRecord(value)) refuseConfiguration("a response value is not plain JSON data");
  const copy = {};
  const { descriptors, keys } = ownDataKeys(value);
  for (const key of keys.sort()) {
    Object.defineProperty(copy, key, {
      configurable: false,
      enumerable: true,
      value: copyAndFreezeJson(descriptors[key].value, depth + 1),
      writable: false,
    });
  }
  return Object.freeze(copy);
};

const jsonEqual = (left, right) => {
  try {
    return canonicalJson(left) === canonicalJson(right);
  } catch {
    return false;
  }
};

const decodePointerSegment = (segment, pointer) => {
  if (/~(?:[^01]|$)/u.test(segment)) {
    refuseConfiguration(`local reference ${pointer} contains an invalid JSON Pointer escape`);
  }
  return segment.replaceAll("~1", "/").replaceAll("~0", "~");
};

const resolveLocalPointer = (document, pointer, where) => {
  if (typeof pointer !== "string" || !pointer.startsWith("#/")) {
    refuseConfiguration(`${where} uses a non-local or malformed reference`);
  }
  const rawSegments = pointer.slice(2).split("/");
  if (rawSegments.length > MAX_POINTER_SEGMENTS) {
    refuseConfiguration(`${where} reference exceeds the JSON Pointer segment bound`);
  }
  let node = document;
  for (const rawSegment of rawSegments) {
    const segment = decodePointerSegment(rawSegment, pointer);
    if (Array.isArray(node)) {
      if (!/^(?:0|[1-9][0-9]*)$/u.test(segment)) {
        refuseConfiguration(`${where} reference does not name an array element`);
      }
      const index = Number.parseInt(segment, 10);
      if (index >= node.length || !Object.hasOwn(node, index)) {
        refuseConfiguration(`${where} reference points outside an array`);
      }
      node = node[index];
      continue;
    }
    if (!isRecord(node) || !Object.hasOwn(node, segment)) {
      refuseConfiguration(`${where} reference points to missing canonical data`);
    }
    node = node[segment];
  }
  return node;
};

const resolveReferenceObject = (document, initial, where) => {
  let node = initial;
  const seen = new Set();
  for (let depth = 0; depth <= MAX_REFERENCE_DEPTH; depth += 1) {
    if (!isRecord(node) || !Object.hasOwn(node, "$ref")) return node;
    const pointer = node.$ref;
    if (typeof pointer !== "string") refuseConfiguration(`${where} has a non-string $ref`);
    if (seen.has(pointer)) refuseConfiguration(`${where} contains a reference cycle`);
    seen.add(pointer);
    node = resolveLocalPointer(document, pointer, where);
  }
  refuseConfiguration(`${where} exceeds the local reference depth bound`);
};

const withoutReference = (schema) => {
  const copy = {};
  for (const key of Object.keys(schema)) {
    if (key !== "$ref") copy[key] = schema[key];
  }
  return copy;
};

const jsonTypeMatches = (value, type) => {
  if (type === "null") return value === null;
  if (type === "array") return Array.isArray(value);
  if (type === "object") return isRecord(value);
  if (type === "string") return typeof value === "string";
  if (type === "boolean") return typeof value === "boolean";
  if (type === "number") return typeof value === "number" && Number.isFinite(value);
  if (type === "integer") return typeof value === "number" && Number.isInteger(value);
  return false;
};

const combineAll = (results) => {
  if (results.includes(false)) return false;
  return results.includes(UNKNOWN_VALIDITY) ? UNKNOWN_VALIDITY : true;
};

const validateSchema = (document, schema, value, state = { depth: 0, refs: new Set() }) => {
  if (state.depth > MAX_SCHEMA_DEPTH) {
    refuseConfiguration("a singleton response schema exceeds the nesting bound");
  }
  if (schema === true) return true;
  if (schema === false) return false;
  if (!isRecord(schema)) return UNKNOWN_VALIDITY;
  const keys = Object.keys(schema);
  if (keys.some((key) => !SCHEMA_KEYS.includes(key))) return UNKNOWN_VALIDITY;

  const results = [];
  const descend = (child, childValue = value, refs = state.refs) =>
    validateSchema(document, child, childValue, { depth: state.depth + 1, refs });

  if (Object.hasOwn(schema, "$ref")) {
    const pointer = schema.$ref;
    if (typeof pointer !== "string") refuseConfiguration("a response schema has a non-string $ref");
    if (state.refs.has(pointer)) refuseConfiguration("a response schema contains a reference cycle");
    if (state.refs.size >= MAX_REFERENCE_DEPTH) {
      refuseConfiguration("a response schema exceeds the local reference depth bound");
    }
    const refs = new Set(state.refs);
    refs.add(pointer);
    results.push(descend(resolveLocalPointer(document, pointer, "response schema"), value, refs));
  }

  if (Object.hasOwn(schema, "type")) {
    const types = Array.isArray(schema.type) ? schema.type : [schema.type];
    if (
      types.length === 0 ||
      types.some((type) => typeof type !== "string") ||
      new Set(types).size !== types.length
    ) {
      return UNKNOWN_VALIDITY;
    }
    results.push(types.some((type) => jsonTypeMatches(value, type)));
  }
  if (Object.hasOwn(schema, "const")) results.push(jsonEqual(value, schema.const));
  if (Object.hasOwn(schema, "enum")) {
    if (!Array.isArray(schema.enum) || schema.enum.length === 0) return UNKNOWN_VALIDITY;
    results.push(schema.enum.some((entry) => jsonEqual(value, entry)));
  }

  for (const key of ["allOf", "anyOf", "oneOf"]) {
    if (!Object.hasOwn(schema, key)) continue;
    const branches = schema[key];
    if (!Array.isArray(branches) || branches.length === 0) return UNKNOWN_VALIDITY;
    const branchResults = branches.map((branch) => descend(branch));
    const trueCount = branchResults.filter((entry) => entry === true).length;
    const unknownCount = branchResults.filter((entry) => entry === UNKNOWN_VALIDITY).length;
    if (key === "allOf") results.push(combineAll(branchResults));
    else if (key === "anyOf") {
      results.push(trueCount > 0 ? true : unknownCount > 0 ? UNKNOWN_VALIDITY : false);
    } else {
      results.push(
        trueCount > 1
          ? false
          : unknownCount > 0
            ? UNKNOWN_VALIDITY
            : trueCount === 1,
      );
    }
  }
  if (Object.hasOwn(schema, "not")) {
    const result = descend(schema.not);
    results.push(result === UNKNOWN_VALIDITY ? result : !result);
  }

  if (isRecord(value)) {
    const valueKeys = Object.keys(value);
    if (Object.hasOwn(schema, "minProperties")) {
      if (!Number.isInteger(schema.minProperties) || schema.minProperties < 0) {
        return UNKNOWN_VALIDITY;
      }
      results.push(valueKeys.length >= schema.minProperties);
    }
    if (Object.hasOwn(schema, "maxProperties")) {
      if (!Number.isInteger(schema.maxProperties) || schema.maxProperties < 0) {
        return UNKNOWN_VALIDITY;
      }
      results.push(valueKeys.length <= schema.maxProperties);
    }
    if (Object.hasOwn(schema, "required")) {
      if (
        !Array.isArray(schema.required) ||
        schema.required.some((key) => typeof key !== "string") ||
        new Set(schema.required).size !== schema.required.length
      ) {
        return UNKNOWN_VALIDITY;
      }
      results.push(schema.required.every((key) => Object.hasOwn(value, key)));
    }
    let properties = {};
    if (Object.hasOwn(schema, "properties")) {
      if (!isRecord(schema.properties)) return UNKNOWN_VALIDITY;
      properties = schema.properties;
      for (const key of Object.keys(properties)) {
        if (Object.hasOwn(value, key)) results.push(descend(properties[key], value[key]));
      }
    }
    const extras = valueKeys.filter((key) => !Object.hasOwn(properties, key));
    if (Object.hasOwn(schema, "additionalProperties")) {
      if (schema.additionalProperties === false) results.push(extras.length === 0);
      else if (schema.additionalProperties !== true) {
        results.push(...extras.map((key) => descend(schema.additionalProperties, value[key])));
      }
    }
  }

  if (Array.isArray(value)) {
    if (Object.hasOwn(schema, "minItems")) {
      if (!Number.isInteger(schema.minItems) || schema.minItems < 0) return UNKNOWN_VALIDITY;
      results.push(value.length >= schema.minItems);
    }
    if (Object.hasOwn(schema, "maxItems")) {
      if (!Number.isInteger(schema.maxItems) || schema.maxItems < 0) return UNKNOWN_VALIDITY;
      results.push(value.length <= schema.maxItems);
    }
    let prefixLength = 0;
    if (Object.hasOwn(schema, "prefixItems")) {
      if (!Array.isArray(schema.prefixItems)) return UNKNOWN_VALIDITY;
      prefixLength = schema.prefixItems.length;
      for (let index = 0; index < Math.min(prefixLength, value.length); index += 1) {
        results.push(descend(schema.prefixItems[index], value[index]));
      }
    }
    if (Object.hasOwn(schema, "items")) {
      const remaining = value.slice(prefixLength);
      if (schema.items === false) results.push(remaining.length === 0);
      else if (schema.items !== true) {
        results.push(...remaining.map((entry) => descend(schema.items, entry)));
      }
    }
    if (Object.hasOwn(schema, "uniqueItems")) {
      if (typeof schema.uniqueItems !== "boolean") return UNKNOWN_VALIDITY;
      if (schema.uniqueItems) {
        const fingerprints = value.map((entry) => canonicalJson(entry));
        results.push(new Set(fingerprints).size === fingerprints.length);
      }
    }
  }

  if (typeof value === "string") {
    for (const key of ["minLength", "maxLength"]) {
      if (!Object.hasOwn(schema, key)) continue;
      if (!Number.isInteger(schema[key]) || schema[key] < 0) return UNKNOWN_VALIDITY;
      const length = [...value].length;
      results.push(key === "minLength" ? length >= schema[key] : length <= schema[key]);
    }
  }

  if (typeof value === "number" && Number.isFinite(value)) {
    for (const key of ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"]) {
      if (!Object.hasOwn(schema, key)) continue;
      const bound = schema[key];
      if (typeof bound !== "number" || !Number.isFinite(bound)) return UNKNOWN_VALIDITY;
      if (key === "minimum") results.push(value >= bound);
      else if (key === "maximum") results.push(value <= bound);
      else if (key === "exclusiveMinimum") results.push(value > bound);
      else results.push(value < bound);
    }
    if (Object.hasOwn(schema, "multipleOf")) {
      const divisor = schema.multipleOf;
      if (typeof divisor !== "number" || !Number.isFinite(divisor) || divisor <= 0) {
        return UNKNOWN_VALIDITY;
      }
      results.push(Number.isInteger(value / divisor));
    }
  }

  for (const key of keys) {
    if (ANNOTATION_SCHEMA_KEYS.includes(key)) continue;
    if (
      ![
        "$ref",
        "additionalProperties",
        "allOf",
        "anyOf",
        "const",
        "enum",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "items",
        "maxItems",
        "maxLength",
        "maxProperties",
        "maximum",
        "minItems",
        "minLength",
        "minProperties",
        "minimum",
        "multipleOf",
        "not",
        "oneOf",
        "prefixItems",
        "properties",
        "required",
        "type",
        "uniqueItems",
      ].includes(key)
    ) {
      return UNKNOWN_VALIDITY;
    }
  }
  return combineAll(results);
};

const deriveSingleton = (document, schema, state = { depth: 0, refs: new Set() }) => {
  if (state.depth > MAX_SCHEMA_DEPTH) {
    refuseConfiguration("a singleton response schema exceeds the derivation bound");
  }
  if (schema === true || schema === false || !isRecord(schema)) return NO_SINGLETON;
  if (Object.keys(schema).some((key) => !SCHEMA_KEYS.includes(key))) return NO_SINGLETON;

  const candidates = [];
  const descend = (child, refs = state.refs) =>
    deriveSingleton(document, child, { depth: state.depth + 1, refs });

  if (Object.hasOwn(schema, "$ref")) {
    const pointer = schema.$ref;
    if (typeof pointer !== "string") refuseConfiguration("a response schema has a non-string $ref");
    if (state.refs.has(pointer)) refuseConfiguration("a response schema contains a reference cycle");
    if (state.refs.size >= MAX_REFERENCE_DEPTH) {
      refuseConfiguration("a response schema exceeds the local reference depth bound");
    }
    const refs = new Set(state.refs);
    refs.add(pointer);
    const referenced = descend(resolveLocalPointer(document, pointer, "response schema"), refs);
    if (referenced !== NO_SINGLETON) candidates.push(referenced);
    const siblings = withoutReference(schema);
    if (Object.keys(siblings).some((key) => !ANNOTATION_SCHEMA_KEYS.includes(key))) {
      const siblingCandidate = descend(siblings);
      if (siblingCandidate !== NO_SINGLETON) candidates.push(siblingCandidate);
    }
  }

  if (Object.hasOwn(schema, "const")) {
    try {
      canonicalJson(schema.const);
      candidates.push(copyAndFreezeJson(schema.const));
    } catch {
      return NO_SINGLETON;
    }
  }
  if (Object.hasOwn(schema, "enum") && Array.isArray(schema.enum) && schema.enum.length > 0) {
    const unique = new Map();
    try {
      for (const entry of schema.enum) unique.set(canonicalJson(entry), entry);
    } catch {
      return NO_SINGLETON;
    }
    if (unique.size === 1) candidates.push(copyAndFreezeJson(unique.values().next().value));
  }

  if (schema.type === "null") candidates.push(null);

  if (schema.type === "object" && schema.additionalProperties === false) {
    const properties = Object.hasOwn(schema, "properties") ? schema.properties : {};
    const required = Object.hasOwn(schema, "required") ? schema.required : [];
    if (
      isRecord(properties) &&
      Array.isArray(required) &&
      required.every((key) => typeof key === "string") &&
      new Set(required).size === required.length
    ) {
      const propertyKeys = Object.keys(properties).sort();
      const requiredKeys = [...required].sort();
      if (
        propertyKeys.length === requiredKeys.length &&
        propertyKeys.every((key, index) => key === requiredKeys[index])
      ) {
        const candidate = {};
        let complete = true;
        for (const key of propertyKeys) {
          const propertyValue = descend(properties[key]);
          if (propertyValue === NO_SINGLETON) {
            complete = false;
            break;
          }
          candidate[key] = propertyValue;
        }
        if (complete) candidates.push(copyAndFreezeJson(candidate));
      }
    }
  }

  if (schema.type === "array") {
    if (schema.maxItems === 0 && (schema.minItems === undefined || schema.minItems === 0)) {
      candidates.push(Object.freeze([]));
    }
    if (Array.isArray(schema.prefixItems) && schema.items === false) {
      const length = schema.prefixItems.length;
      const forcesAllPrefixItems =
        (length === 0 && (schema.minItems === undefined || schema.minItems === 0)) ||
        schema.minItems === length;
      const permitsNoMoreThanPrefix = schema.maxItems === undefined || schema.maxItems === length;
      if (forcesAllPrefixItems && permitsNoMoreThanPrefix) {
        const candidate = [];
        let complete = true;
        for (const itemSchema of schema.prefixItems) {
          const item = descend(itemSchema);
          if (item === NO_SINGLETON) {
            complete = false;
            break;
          }
          candidate.push(item);
        }
        if (complete) candidates.push(Object.freeze(candidate));
      }
    }
    if (
      Number.isInteger(schema.minItems) &&
      schema.minItems >= 0 &&
      schema.minItems === schema.maxItems &&
      (!Array.isArray(schema.prefixItems) || schema.prefixItems.length === 0) &&
      isRecord(schema.items)
    ) {
      const item = descend(schema.items);
      if (item !== NO_SINGLETON) {
        candidates.push(
          Object.freeze(
            Array.from({ length: schema.minItems }, () => copyAndFreezeJson(item)),
          ),
        );
      }
    }
  }

  if (Array.isArray(schema.allOf)) {
    for (const branch of schema.allOf) {
      const candidate = descend(branch);
      if (candidate !== NO_SINGLETON) candidates.push(candidate);
    }
  }
  for (const key of ["anyOf", "oneOf"]) {
    if (!Array.isArray(schema[key]) || schema[key].length === 0) continue;
    const branchCandidates = schema[key].map((branch) => descend(branch));
    if (branchCandidates.some((entry) => entry === NO_SINGLETON)) continue;
    const fingerprints = new Set(branchCandidates.map((entry) => canonicalJson(entry)));
    if (key === "anyOf" && fingerprints.size === 1) candidates.push(branchCandidates[0]);
    if (key === "oneOf" && branchCandidates.length === 1) candidates.push(branchCandidates[0]);
  }

  const uniqueCandidates = new Map();
  for (const candidate of candidates) uniqueCandidates.set(canonicalJson(candidate), candidate);
  for (const candidate of uniqueCandidates.values()) {
    if (validateSchema(document, schema, candidate, state) === true) {
      return copyAndFreezeJson(candidate);
    }
  }
  return NO_SINGLETON;
};

const readParameterList = (owner, where) => {
  if (!Object.hasOwn(owner, "parameters")) return [];
  if (!Array.isArray(owner.parameters)) {
    refuseConfiguration(`${where} parameters are not an array`);
  }
  return owner.parameters;
};

const hasPathOrQueryParameter = (document, pathItem, operation, where) => {
  const parameterLists = [];
  if (Object.hasOwn(pathItem, "$ref")) {
    const referencedPathItem = resolveReferenceObject(document, pathItem, `${where} path item`);
    if (!isRecord(referencedPathItem)) {
      refuseConfiguration(`${where} referenced path item is not an object`);
    }
    if (referencedPathItem !== pathItem) {
      parameterLists.push(readParameterList(referencedPathItem, `${where} referenced path item`));
    }
  }
  parameterLists.push(readParameterList(pathItem, `${where} path item`));
  parameterLists.push(readParameterList(operation, `${where} operation`));

  const merged = new Map();
  for (const parameters of parameterLists) {
    for (const entry of parameters) {
      const parameter = resolveReferenceObject(document, entry, `${where} parameter`);
      if (
        !isRecord(parameter) ||
        typeof parameter.name !== "string" ||
        typeof parameter.in !== "string"
      ) {
        refuseConfiguration(`${where} contains a malformed parameter`);
      }
      merged.set(`${parameter.in}\u0000${parameter.name}`, parameter);
    }
  }
  return [...merged.values()].some(
    (parameter) => parameter.in === "path" || parameter.in === "query",
  );
};

const isExplicitEmptyArray = (owner, key) =>
  Object.hasOwn(owner, key) && Array.isArray(owner[key]) && owner[key].length === 0;

const isJsonMediaType = (mediaType) =>
  typeof mediaType === "string" &&
  /^application\/(?:[A-Za-z0-9!#$&^_.+-]+\+)?json$/iu.test(mediaType);

const deriveEligibleOperation = (document, table, route) => {
  const pathItem = document.paths[route.path];
  const operation = isRecord(pathItem) ? pathItem[route.method.toLowerCase()] : undefined;
  if (!isRecord(pathItem) || !isRecord(operation)) {
    refuseConfiguration("a projected route cannot be recovered from the parsed snapshot");
  }
  if (!isExplicitEmptyArray(operation, "security")) return null;
  if (!isExplicitEmptyArray(operation, "x-required-capabilities")) return null;
  if (route.pathParameters.length !== 0 || /[{}]/u.test(route.path)) return null;
  if (hasPathOrQueryParameter(document, pathItem, operation, route.operationId)) return null;
  if (Object.hasOwn(operation, "requestBody")) return null;
  if (!isRecord(operation.responses)) return null;

  const successCodes = Object.keys(operation.responses).filter((code) => /^2[0-9]{2}$/u.test(code));
  if (successCodes.length !== 1) return null;
  const statusText = successCodes[0];
  if (BODILESS_STATUS_CODES.includes(statusText)) return null;
  const response = resolveReferenceObject(
    document,
    operation.responses[statusText],
    `${route.operationId} success response`,
  );
  if (!isRecord(response) || !isRecord(response.content)) return null;
  const mediaTypes = Object.keys(response.content);
  if (mediaTypes.length !== 1 || !isJsonMediaType(mediaTypes[0])) return null;
  const mediaType = mediaTypes[0];
  const media = response.content[mediaType];
  if (!isRecord(media) || !Object.hasOwn(media, "schema")) return null;
  if (!isRecord(media.schema)) return null;
  const responseSchemaKind = typeof media.schema.$ref === "string" ? "ref" : "inline";
  const responseSchemaRef = responseSchemaKind === "ref" ? media.schema.$ref : null;

  const body = deriveSingleton(document, media.schema);
  if (body === NO_SINGLETON) return null;
  if (Object.hasOwn(media, "examples")) return null;
  if (Object.hasOwn(media, "example") && !jsonEqual(media.example, body)) return null;

  if (
    route.successStatus !== statusText ||
    route.responseMediaType !== mediaType ||
    route.responseSchemaKind !== responseSchemaKind ||
    route.responseSchemaRef !== responseSchemaRef
  ) {
    refuseConfiguration("the route projection and eligible response disagree");
  }
  const statusCode = Number.parseInt(statusText, 10);
  if (!Number.isInteger(statusCode) || statusCode < 200 || statusCode > 299) return null;
  return Object.freeze({
    body,
    mediaType,
    method: route.method,
    operationId: route.operationId,
    path: route.path,
    statusCode,
  });
};

const deriveOriginFormTarget = (basePath, path) => {
  if (typeof basePath !== "string" || typeof path !== "string" || !path.startsWith("/")) {
    refuseConfiguration("the canonical server base and route do not form an origin target");
  }
  if (
    (basePath !== "" && !basePath.startsWith("/")) ||
    /[?#\u0000-\u0020\u007f]/u.test(basePath) ||
    /[?#\u0000-\u0020\u007f]/u.test(path)
  ) {
    refuseConfiguration("the canonical server base or route is not a bounded origin-form path");
  }
  const prefix = basePath === "/" ? "" : basePath.endsWith("/") ? basePath.slice(0, -1) : basePath;
  const target = `${prefix}${path}`;
  if (!target.startsWith("/") || !/^[\x21-\x7e]+$/u.test(target)) {
    refuseConfiguration("the derived request target is not byte-stable origin-form ASCII");
  }
  return target;
};

const readFactoryOptions = (options) => {
  if (options === undefined) return { serverFactory: createHttpServer };
  if (!isRecord(options)) throw new TypeError("factory options must be a plain object");
  const keys = Reflect.ownKeys(options);
  if (keys.some((key) => typeof key !== "string" || key !== "serverFactory")) {
    throw new TypeError("serverFactory is the only accepted factory option");
  }
  const serverFactory = Object.hasOwn(options, "serverFactory")
    ? options.serverFactory
    : createHttpServer;
  if (typeof serverFactory !== "function") throw new TypeError("serverFactory must be callable");
  return { serverFactory };
};

const destroySilently = (target) => {
  try {
    if (target !== null && target !== undefined && typeof target.destroy === "function") {
      target.destroy();
    }
  } catch {
    // Refusal paths must not turn a failed exchange into an uncaught process error.
  }
};

const socketOf = (target) => {
  try {
    return target === null || target === undefined ? null : target.socket ?? null;
  } catch {
    return null;
  }
};

const destroyExchange = (request, response = null, socket = null) => {
  destroySilently(response);
  destroySilently(request);
  destroySilently(socket);
  destroySilently(socketOf(response));
  destroySilently(socketOf(request));
};

const hasForbiddenOrMalformedHeaders = (rawHeaders) => {
  if (!Array.isArray(rawHeaders) || rawHeaders.length % 2 !== 0) return true;
  for (let index = 0; index < rawHeaders.length; index += 2) {
    const name = rawHeaders[index];
    const value = rawHeaders[index + 1];
    if (typeof name !== "string" || typeof value !== "string") return true;
    if (FORBIDDEN_REQUEST_HEADERS.includes(name.toLowerCase())) return true;
  }
  return false;
};

const chunkByteLength = (chunk) => {
  if (typeof chunk === "string") return Buffer.byteLength(chunk, "utf8");
  if (Buffer.isBuffer(chunk)) return chunk.byteLength;
  if (ArrayBuffer.isView(chunk)) return chunk.byteLength;
  if (chunk instanceof ArrayBuffer) return chunk.byteLength;
  return null;
};

const isExactResponseRecord = (actual, expected) => {
  try {
    if (actual !== expected || Object.getPrototypeOf(actual) !== Object.prototype) return false;
    const keys = Reflect.ownKeys(actual);
    const expectedKeys = ["body", "mediaType", "statusCode"];
    if (
      keys.length !== expectedKeys.length ||
      keys.some((key) => typeof key !== "string" || !expectedKeys.includes(key))
    ) {
      return false;
    }
    const descriptors = Object.getOwnPropertyDescriptors(actual);
    for (const key of expectedKeys) {
      const descriptor = descriptors[key];
      if (
        descriptor === undefined ||
        descriptor.enumerable !== true ||
        !Object.hasOwn(descriptor, "value") ||
        descriptor.value !== expected[key]
      ) {
        return false;
      }
    }
    return true;
  } catch {
    return false;
  }
};

const isExactResponseBody = (actual, expected) => {
  try {
    if (actual !== expected || !isRecord(actual)) return false;
    ownDataKeys(actual);
    return canonicalJson(actual) === canonicalJson(expected);
  } catch {
    return false;
  }
};

const isIpv6Loopback = (host) => {
  if (host.includes(".")) return false;
  const parts = host.toLowerCase().split("::");
  if (parts.length > 2) return false;
  const left = parts[0] === "" ? [] : parts[0].split(":");
  const right = parts.length === 1 || parts[1] === "" ? [] : parts[1].split(":");
  const missing = 8 - left.length - right.length;
  if ((parts.length === 1 && missing !== 0) || (parts.length === 2 && missing < 1)) return false;
  const groups = parts.length === 1 ? left : [...left, ...Array(missing).fill("0"), ...right];
  return (
    groups.length === 8 &&
    groups.slice(0, 7).every((group) => Number.parseInt(group, 16) === 0) &&
    Number.parseInt(groups[7], 16) === 1
  );
};

const isLoopbackHost = (host) => {
  if (typeof host !== "string" || host === "" || host.trim() !== host) return false;
  const version = isIP(host);
  if (version === 4) return Number.parseInt(host.split(".")[0], 10) === 127;
  if (version === 6) return isIpv6Loopback(host);
  return false;
};

const readListenOptions = (options) => {
  if (options === undefined) return { host: DEFAULT_HOST, port: DEFAULT_PORT };
  if (!isRecord(options)) throw new TypeError("listen options must be a plain object");
  const keys = Reflect.ownKeys(options);
  if (keys.some((key) => typeof key !== "string" || !["host", "port"].includes(key))) {
    throw new TypeError("listen accepts only host and port");
  }
  const host = Object.hasOwn(options, "host") ? options.host : DEFAULT_HOST;
  const port = Object.hasOwn(options, "port") ? options.port : DEFAULT_PORT;
  if (!isLoopbackHost(host)) throw new RangeError("listen host must be a numeric loopback address");
  if (!Number.isInteger(port) || port < 0 || port > 65_535) {
    throw new RangeError("listen port must be an integer from 0 through 65535");
  }
  return { host, port };
};

const requireServerSurface = (server) => {
  if (typeof server !== "object" || server === null) {
    refuseConfiguration("serverFactory did not return a server object");
  }
  for (const method of ["address", "close", "listen", "on", "once", "removeListener", "setTimeout"]) {
    if (typeof server[method] !== "function") {
      refuseConfiguration(`serverFactory result has no ${method} method`);
    }
  }
};

const setServerLimit = (server, property, value) => {
  try {
    server[property] = value;
  } catch (error) {
    refuseConfiguration(`serverFactory result rejects ${property}`, error);
  }
  if (server[property] !== value) {
    refuseConfiguration(`serverFactory result does not retain ${property}`);
  }
};

const isNotRunningError = (error) =>
  error !== null &&
  typeof error === "object" &&
  Object.hasOwn(error, "code") &&
  error.code === "ERR_SERVER_NOT_RUNNING";

/**
 * Construct a closed, loopback-only Node HTTP lifecycle for the one operation
 * the canonical OpenAPI snapshot proves to be public and constant.
 *
 * @param {{serverFactory?: typeof createHttpServer}} [options]
 */
export const createNodeHttpLivenessAdapter = (options = undefined) => {
  const { serverFactory } = readFactoryOptions(options);

  // Read once, then use this exact parsed snapshot and byte hash for both the
  // projected route table and the stricter constant-operation proof.
  const source = readRepositoryDocument(CANONICAL_OPENAPI_PATH);
  const document = parseYamlSubset(source.text);
  const table = projectRouteTable(document, {
    documentPath: source.relativePath,
    documentSha256: source.sha256,
  });
  const eligible = table.operations
    .map((route) => deriveEligibleOperation(document, table, route))
    .filter((entry) => entry !== null);
  if (eligible.length !== 1) {
    refuseConfiguration(
      `the canonical snapshot proves ${eligible.length} public constant operations instead of exactly one`,
    );
  }

  const operation = eligible[0];
  if (!isRecord(operation.body)) {
    refuseConfiguration("the canonical constant response is not a plain object");
  }
  ownDataKeys(operation.body);
  const target = deriveOriginFormTarget(table.basePath, operation.path);
  const responseRecord = Object.freeze({
    body: operation.body,
    mediaType: operation.mediaType,
    statusCode: operation.statusCode,
  });
  if (!isExactResponseRecord(responseRecord, responseRecord)) {
    refuseConfiguration("the derived constant handler result is not an exact response record");
  }
  const responseBytes = Buffer.from(canonicalJson(responseRecord.body), "utf8");
  const contentLength = String(responseBytes.byteLength);

  const constantHandler = () => responseRecord.body;
  const handlers = {};
  Object.defineProperty(handlers, operation.operationId, {
    configurable: false,
    enumerable: true,
    value: constantHandler,
    writable: false,
  });
  Object.freeze(handlers);
  const surface = bindServerSurface(table, handlers);
  if (
    surface.coverage.coverageState !== COVERAGE_STATES.PARTIAL ||
    surface.coverage.boundOperationCount !== 1
  ) {
    refuseConfiguration("the one-handler binding does not retain PARTIAL coverage");
  }

  const dispatchRequest = Object.freeze({});
  let lifecycle = "created";
  let listenAttempted = false;
  let pendingListen = null;
  let closePromise = null;
  let terminalServerError = null;
  const sockets = new Set();

  const requestListener = (request, response) => {
    let ended = false;
    let failed = false;
    const fail = () => {
      if (failed) return;
      failed = true;
      destroyExchange(request, response);
    };

    try {
      if (
        request === null ||
        response === null ||
        typeof request !== "object" ||
        typeof response !== "object" ||
        typeof request.on !== "function" ||
        typeof request.once !== "function" ||
        typeof response.once !== "function"
      ) {
        fail();
        return;
      }
      response.once("error", fail);
      if (
        request.method !== operation.method ||
        request.url !== target ||
        hasForbiddenOrMalformedHeaders(request.rawHeaders)
      ) {
        fail();
        return;
      }

      request.once("aborted", fail);
      request.once("error", fail);
      request.once("close", () => {
        if (!ended) fail();
      });
      request.on("data", (chunk) => {
        if (failed) return;
        const length = chunkByteLength(chunk);
        if (length === null || length > 0) fail();
      });
      request.once("end", () => {
        if (failed) return;
        ended = true;
        if (request.aborted === true || request.complete !== true) {
          fail();
          return;
        }
        try {
          const actual = surface.dispatch(operation.operationId, dispatchRequest);
          if (!isExactResponseBody(actual, responseRecord.body)) {
            refuseConfiguration("the bound constant handler returned a non-exact response body");
          }
          if (
            response.headersSent === true ||
            response.writableEnded === true ||
            response.destroyed === true ||
            typeof response.setHeader !== "function" ||
            typeof response.end !== "function"
          ) {
            fail();
            return;
          }
          response.statusCode = responseRecord.statusCode;
          response.setHeader("Content-Type", responseRecord.mediaType);
          response.setHeader("Cache-Control", "no-store");
          response.setHeader("Content-Length", contentLength);
          response.end(responseBytes);
        } catch {
          fail();
        }
      });
    } catch {
      fail();
    }
  };

  const serverOptions = {
    connectionsCheckingInterval: 1_000,
    headersTimeout: HEADERS_TIMEOUT_MS,
    insecureHTTPParser: false,
    keepAliveTimeout: KEEP_ALIVE_TIMEOUT_MS,
    maxHeaderSize: MAX_HEADER_SIZE_BYTES,
    maxRequestsPerSocket: MAX_REQUESTS_PER_SOCKET,
    requestTimeout: REQUEST_TIMEOUT_MS,
    requireHostHeader: true,
  };
  const server = serverFactory(serverOptions, requestListener);
  requireServerSurface(server);
  setServerLimit(server, "headersTimeout", HEADERS_TIMEOUT_MS);
  setServerLimit(server, "requestTimeout", REQUEST_TIMEOUT_MS);
  setServerLimit(server, "keepAliveTimeout", KEEP_ALIVE_TIMEOUT_MS);
  setServerLimit(server, "maxHeadersCount", MAX_HEADERS_COUNT);
  setServerLimit(server, "maxRequestsPerSocket", MAX_REQUESTS_PER_SOCKET);
  setServerLimit(server, "maxConnections", MAX_CONNECTIONS);

  server.setTimeout(SOCKET_TIMEOUT_MS, (socket) => destroySilently(socket));
  if (server.timeout !== SOCKET_TIMEOUT_MS) {
    refuseConfiguration("serverFactory result does not retain the finite socket timeout");
  }

  const destroyTrackedSockets = () => {
    for (const socket of [...sockets]) destroySilently(socket);
  };
  const recordServerFailure = (error) => {
    if (terminalServerError === null) {
      terminalServerError =
        error instanceof Error ? error : new Error("the Node HTTP server emitted an error");
    }
    if (lifecycle !== "closing" && lifecycle !== "closed") lifecycle = "failed";
    destroyTrackedSockets();
    try {
      server.close(() => {});
    } catch {
      // The stored failure remains observable through address(), listen(), or close().
    }
  };
  server.on("connection", (socket) => {
    if (
      socket === null ||
      typeof socket !== "object" ||
      typeof socket.destroy !== "function" ||
      typeof socket.once !== "function"
    ) {
      destroySilently(socket);
      return;
    }
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
    socket.once("error", () => destroySilently(socket));
    if (lifecycle === "closing" || lifecycle === "closed") destroySilently(socket);
  });
  server.on("checkContinue", (request, response) => destroyExchange(request, response));
  server.on("checkExpectation", (request, response) => destroyExchange(request, response));
  server.on("upgrade", (request, socket) => destroyExchange(request, null, socket));
  server.on("connect", (request, socket) => destroyExchange(request, null, socket));
  server.on("clientError", (_error, socket) => destroySilently(socket));
  server.on("dropRequest", (request, socket) => destroyExchange(request, null, socket));
  server.on("error", recordServerFailure);

  const address = () => {
    if (terminalServerError !== null) throw terminalServerError;
    const reported = server.address();
    if (reported === null) return null;
    if (
      !isRecord(reported) ||
      typeof reported.address !== "string" ||
      !isLoopbackHost(reported.address) ||
      !Number.isInteger(reported.port) ||
      reported.port < 0 ||
      reported.port > 65_535
    ) {
      refuseConfiguration("serverFactory reported a non-loopback or malformed address");
    }
    return Object.freeze({
      address: reported.address,
      family: reported.family,
      port: reported.port,
    });
  };

  const listen = (listenOptions = undefined) => {
    const normalized = readListenOptions(listenOptions);
    if (listenAttempted || lifecycle !== "created") {
      throw new Error("listen may be invoked only once");
    }
    listenAttempted = true;
    lifecycle = "starting";
    return new Promise((resolve, reject) => {
      let settled = false;
      const cleanup = () => {
        server.removeListener("listening", onListening);
        server.removeListener("error", onError);
        if (pendingListen !== null && pendingListen.cleanup === cleanup) pendingListen = null;
      };
      const settleReject = (error) => {
        if (settled) return;
        settled = true;
        cleanup();
        if (lifecycle !== "closing" && lifecycle !== "closed") lifecycle = "failed";
        reject(error);
      };
      const onListening = () => {
        if (settled) return;
        if (terminalServerError !== null) {
          settleReject(terminalServerError);
          return;
        }
        if (lifecycle === "closing" || lifecycle === "closed") {
          settleReject(new Error("the adapter was closed while listen was pending"));
          return;
        }
        try {
          const boundAddress = address();
          settled = true;
          cleanup();
          lifecycle = "listening";
          resolve(boundAddress);
        } catch (error) {
          recordServerFailure(error);
          settleReject(error);
        }
      };
      const onError = (error) => settleReject(error);
      pendingListen = { cleanup, reject: settleReject };
      server.once("listening", onListening);
      server.once("error", onError);
      try {
        server.listen(normalized);
      } catch (error) {
        settleReject(error);
      }
    });
  };

  const close = () => {
    if (closePromise !== null) return closePromise;
    const previousLifecycle = lifecycle;
    lifecycle = "closing";
    if (pendingListen !== null) {
      pendingListen.reject(new Error("the adapter was closed while listen was pending"));
    }
    if (previousLifecycle === "created") {
      lifecycle = "closed";
      closePromise = Promise.resolve();
      return closePromise;
    }

    closePromise = new Promise((resolve, reject) => {
      let settled = false;
      const finish = (error = undefined) => {
        if (settled) return;
        settled = true;
        destroyTrackedSockets();
        lifecycle = "closed";
        const closeError =
          error !== undefined && error !== null && !isNotRunningError(error) ? error : null;
        if (terminalServerError !== null) reject(terminalServerError);
        else if (closeError !== null) reject(closeError);
        else resolve();
      };
      try {
        server.close((error) => finish(error));
      } catch (error) {
        finish(error);
      }
      destroyTrackedSockets();
    });
    return closePromise;
  };

  return Object.freeze({ address, close, coverage: surface.coverage, listen });
};
