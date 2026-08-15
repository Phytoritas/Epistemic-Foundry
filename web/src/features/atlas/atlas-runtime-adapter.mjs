/**
 * U03 feature-local HTTP bridge for one canonical CoverageSnapshot.
 *
 * The generated client remains the sole route authority. This adapter accepts
 * no origin, credential, header, retry, or shared transport configuration: it
 * performs one same-origin GET and projects only a valid successful body.
 */

import { types as utilTypes } from "node:util";

import { atlasSnapshotRequest, buildAtlasView } from "./atlas-view.mjs";

const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;

export const ATLAS_RUNTIME_VERSION = "4.0.0-u03.runtime.1";

export const ATLAS_RUNTIME_FINDING_CODES = OBJECT_FREEZE({
  ATLAS_RUNTIME_ABORTED:
    "The Atlas request was aborted before a canonical snapshot could be projected.",
  ATLAS_RUNTIME_DESCRIPTOR_INVALID:
    "The generated Atlas descriptor no longer described a credential-opaque bodyless same-origin GET.",
  ATLAS_RUNTIME_FETCH_UNAVAILABLE:
    "No callable fetch surface was supplied or available for the Atlas request.",
  ATLAS_RUNTIME_HTTP_PROBLEM:
    "The Atlas endpoint returned a status other than its generated success status.",
  ATLAS_RUNTIME_INPUT_INVALID:
    "The Atlas runtime input did not match the closed snapshot-id and optional-signal contract.",
  ATLAS_RUNTIME_JSON_INVALID:
    "The declared JSON response could not be decoded, so no Atlas view was produced.",
  ATLAS_RUNTIME_MEDIA_TYPE_INVALID:
    "The declared-success response did not carry an application JSON media type.",
  ATLAS_RUNTIME_OPTIONS_INVALID:
    "The Atlas runtime options did not match the closed fetch-only contract.",
  ATLAS_RUNTIME_RESPONSE_INVALID:
    "The fetch result was not a Response-compatible HTTP observation.",
  ATLAS_RUNTIME_TRANSPORT_FAILURE:
    "The Atlas request failed before an HTTP response was observed.",
});

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of Reflect.ownKeys(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

export class AtlasRuntimeError extends Error {
  constructor(code, detail, context = {}) {
    super(`${code}: ${detail}`);
    this.name = "AtlasRuntimeError";
    this.code = code;
    this.detail = detail;
    this.reason = ATLAS_RUNTIME_FINDING_CODES[code];
    this.context = deepFreeze({ ...context });
    OBJECT_FREEZE(this);
  }
}

const fail = (code, detail, context = {}) => {
  if (!OBJECT_HAS_OWN(ATLAS_RUNTIME_FINDING_CODES, code)) {
    throw new Error(`undeclared Atlas runtime finding code ${code}`);
  }
  throw new AtlasRuntimeError(code, detail, context);
};

const isPlainDataObject = (value) => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  try {
    if (utilTypes.isProxy(value)) return false;
    const prototype = OBJECT_GET_PROTOTYPE_OF(value);
    return prototype === Object.prototype || prototype === null;
  } catch {
    return false;
  }
};

const requireClosedObject = (candidate, { allowed, required = [], label, code }) => {
  if (!isPlainDataObject(candidate)) {
    fail(code, `${label} must be a plain data object`);
  }
  const keys = Reflect.ownKeys(candidate);
  if (keys.some((key) => typeof key !== "string")) {
    fail(code, `${label} may not contain symbol fields`);
  }
  const stringKeys = keys.map(String).sort();
  const unknown = stringKeys.filter((key) => !allowed.includes(key));
  const missing = required.filter((key) => !OBJECT_HAS_OWN(candidate, key));
  const accessor = stringKeys.filter((key) => {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(candidate, key);
    return descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value");
  });
  if (unknown.length > 0 || missing.length > 0 || accessor.length > 0) {
    fail(code, `${label} does not match its closed data field set`, {
      accessor,
      allowed: [...allowed],
      missing,
      received: stringKeys,
      unknown,
    });
  }
  return candidate;
};

const readDataField = (candidate, key, code, label) => {
  const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(candidate, key);
  if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
    fail(code, `${label}.${key} must be an own data field`);
  }
  return descriptor.value;
};

const requireSnapshotId = (value) => {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.normalize("NFC") !== value ||
    /\p{Cc}/u.test(value)
  ) {
    fail(
      "ATLAS_RUNTIME_INPUT_INVALID",
      "snapshot_id must be a non-empty NFC string without control characters",
    );
  }
  return value;
};

const requireSignal = (signal) => {
  if (signal === undefined) return undefined;
  let compatible = false;
  try {
    compatible =
      signal !== null &&
      typeof signal === "object" &&
      !utilTypes.isProxy(signal) &&
      typeof signal.aborted === "boolean" &&
      typeof signal.addEventListener === "function" &&
      typeof signal.removeEventListener === "function";
  } catch {
    compatible = false;
  }
  if (!compatible) {
    fail("ATLAS_RUNTIME_INPUT_INVALID", "signal must be AbortSignal-compatible");
  }
  return signal;
};

const DESCRIPTOR_FIELDS = OBJECT_FREEZE([
  "body",
  "headers",
  "method",
  "operationId",
  "path",
  "pathTemplate",
  "query",
  "requestSchemaRef",
  "responseSchemaRef",
  "successStatus",
  "url",
]);

const requireSafeRelativeUrl = (value) => {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\") ||
    value.includes("#") ||
    /[\u0000-\u001f\u007f]/u.test(value) ||
    /^[a-z][a-z0-9+.-]*:/iu.test(value)
  ) {
    fail(
      "ATLAS_RUNTIME_DESCRIPTOR_INVALID",
      "generated Atlas URL must be a relative same-origin path",
    );
  }
  return value;
};

const requireSafeHeaders = (headers) => {
  if (!isPlainDataObject(headers)) {
    fail("ATLAS_RUNTIME_DESCRIPTOR_INVALID", "generated headers must be plain data");
  }
  for (const key of Reflect.ownKeys(headers)) {
    if (typeof key !== "string") {
      fail("ATLAS_RUNTIME_DESCRIPTOR_INVALID", "generated headers may not use symbols");
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(headers, key);
    if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail("ATLAS_RUNTIME_DESCRIPTOR_INVALID", "generated headers must use data fields");
    }
    const normalized = key.trim().toLowerCase();
    if (
      normalized.length === 0 ||
      /(authorization|cookie|token|api[-_]?key|session|secret)/u.test(normalized) ||
      typeof descriptor.value !== "string"
    ) {
      fail(
        "ATLAS_RUNTIME_DESCRIPTOR_INVALID",
        "generated Atlas headers must be string-valued and credential-free",
      );
    }
  }
  return headers;
};

const requireGeneratedDescriptor = (descriptor) => {
  requireClosedObject(descriptor, {
    allowed: DESCRIPTOR_FIELDS,
    required: DESCRIPTOR_FIELDS,
    label: "generated Atlas request descriptor",
    code: "ATLAS_RUNTIME_DESCRIPTOR_INVALID",
  });
  const operationId = readDataField(
    descriptor,
    "operationId",
    "ATLAS_RUNTIME_DESCRIPTOR_INVALID",
    "descriptor",
  );
  const successStatus = readDataField(
    descriptor,
    "successStatus",
    "ATLAS_RUNTIME_DESCRIPTOR_INVALID",
    "descriptor",
  );
  const responseSchemaRef = readDataField(
    descriptor,
    "responseSchemaRef",
    "ATLAS_RUNTIME_DESCRIPTOR_INVALID",
    "descriptor",
  );
  if (
    readDataField(descriptor, "method", "ATLAS_RUNTIME_DESCRIPTOR_INVALID", "descriptor") !==
      "GET" ||
    readDataField(descriptor, "body", "ATLAS_RUNTIME_DESCRIPTOR_INVALID", "descriptor") !==
      null ||
    readDataField(descriptor, "query", "ATLAS_RUNTIME_DESCRIPTOR_INVALID", "descriptor") !==
      "" ||
    typeof operationId !== "string" ||
    operationId.length === 0 ||
    typeof successStatus !== "string" ||
    !/^2\d\d$/u.test(successStatus) ||
    typeof responseSchemaRef !== "string" ||
    responseSchemaRef.length === 0 ||
    typeof readDataField(
      descriptor,
      "path",
      "ATLAS_RUNTIME_DESCRIPTOR_INVALID",
      "descriptor",
    ) !== "string" ||
    typeof readDataField(
      descriptor,
      "pathTemplate",
      "ATLAS_RUNTIME_DESCRIPTOR_INVALID",
      "descriptor",
    ) !== "string"
  ) {
    fail(
      "ATLAS_RUNTIME_DESCRIPTOR_INVALID",
      "generated Atlas descriptor changed its GET, status, route, or response-schema semantics",
    );
  }
  requireSafeRelativeUrl(
    readDataField(descriptor, "url", "ATLAS_RUNTIME_DESCRIPTOR_INVALID", "descriptor"),
  );
  requireSafeHeaders(
    readDataField(descriptor, "headers", "ATLAS_RUNTIME_DESCRIPTOR_INVALID", "descriptor"),
  );
  return descriptor;
};

const requireResponseCompatible = (response) => {
  let compatible = false;
  try {
    compatible =
      response !== null &&
      (typeof response === "object" || typeof response === "function") &&
      !utilTypes.isProxy(response) &&
      Number.isInteger(response.status) &&
      response.status >= 100 &&
      response.status <= 599 &&
      response.headers !== null &&
      typeof response.headers === "object" &&
      typeof response.headers.get === "function" &&
      typeof response.json === "function";
  } catch {
    compatible = false;
  }
  if (!compatible) {
    fail(
      "ATLAS_RUNTIME_RESPONSE_INVALID",
      "fetch must return a Response-compatible value with status, headers.get, and json",
    );
  }
  return response;
};

const isJsonMediaType = (value) => {
  if (typeof value !== "string") return false;
  const mediaType = value.split(";", 1)[0].trim().toLowerCase();
  return (
    mediaType === "application/json" ||
    /^application\/[a-z0-9!#$&^_.+-]+\+json$/u.test(mediaType)
  );
};

export const createAtlasRuntimeAdapter = (options = {}) => {
  requireClosedObject(options, {
    allowed: ["fetch"],
    label: "Atlas runtime options",
    code: "ATLAS_RUNTIME_OPTIONS_INVALID",
  });
  const fetchImpl = OBJECT_HAS_OWN(options, "fetch")
    ? readDataField(options, "fetch", "ATLAS_RUNTIME_OPTIONS_INVALID", "options")
    : globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    fail("ATLAS_RUNTIME_FETCH_UNAVAILABLE", "fetch must be a callable function");
  }

  const loadAtlasSnapshotView = async (input = {}) => {
    requireClosedObject(input, {
      allowed: ["signal", "snapshot_id"],
      required: ["snapshot_id"],
      label: "Atlas snapshot load input",
      code: "ATLAS_RUNTIME_INPUT_INVALID",
    });
    const snapshotId = requireSnapshotId(
      readDataField(input, "snapshot_id", "ATLAS_RUNTIME_INPUT_INVALID", "input"),
    );
    const signal = OBJECT_HAS_OWN(input, "signal")
      ? requireSignal(readDataField(input, "signal", "ATLAS_RUNTIME_INPUT_INVALID", "input"))
      : undefined;
    if (signal?.aborted) {
      fail("ATLAS_RUNTIME_ABORTED", "Atlas snapshot loading was aborted before fetch");
    }

    const descriptor = requireGeneratedDescriptor(atlasSnapshotRequest({ snapshot_id: snapshotId }));
    const operationId = descriptor.operationId;
    let response;
    try {
      response = await fetchImpl(descriptor.url, {
        cache: "no-store",
        credentials: "same-origin",
        headers: descriptor.headers,
        method: descriptor.method,
        redirect: "error",
        referrerPolicy: "no-referrer",
        ...(signal === undefined ? {} : { signal }),
      });
    } catch {
      if (signal?.aborted) {
        fail("ATLAS_RUNTIME_ABORTED", "Atlas snapshot loading was aborted during fetch");
      }
      fail("ATLAS_RUNTIME_TRANSPORT_FAILURE", "fetch rejected before an HTTP response", {
        operation_id: operationId,
      });
    }

    requireResponseCompatible(response);
    if (String(response.status) !== descriptor.successStatus) {
      fail("ATLAS_RUNTIME_HTTP_PROBLEM", "Atlas endpoint returned a non-success status", {
        operation_id: operationId,
        status: String(response.status),
      });
    }

    let contentType;
    try {
      contentType = response.headers.get("content-type");
    } catch {
      fail("ATLAS_RUNTIME_RESPONSE_INVALID", "response headers could not be read");
    }
    if (!isJsonMediaType(contentType)) {
      fail("ATLAS_RUNTIME_MEDIA_TYPE_INVALID", "successful Atlas response was not JSON", {
        operation_id: operationId,
        status: String(response.status),
      });
    }

    let decoded;
    try {
      decoded = await response.json();
    } catch {
      fail("ATLAS_RUNTIME_JSON_INVALID", "successful Atlas response contained invalid JSON", {
        operation_id: operationId,
        status: String(response.status),
      });
    }
    return buildAtlasView(decoded);
  };

  return OBJECT_FREEZE({ loadAtlasSnapshotView });
};
