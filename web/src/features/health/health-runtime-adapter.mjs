/**
 * U02 read-only runtime bridge from the generated UI client to health receipts.
 *
 * Credentials remain opaque to this module. The browser or injected fetch
 * closure owns authentication; the adapter accepts only generated same-origin
 * GET descriptors and returns transient UI response receipts.
 */

import { types as utilTypes } from "node:util";

import { getLiveness, getReadiness } from "../../generated/ui-client/index.mjs";
import { isAuthorized, validateAuthState } from "../../app/auth.mjs";
import { canonicalJsonSha256, deepFreeze } from "../../app/record-hash.mjs";
import { validateHealthReport } from "./health-view.mjs";

export const HEALTH_RUNTIME_VERSION = "4.0.0-u02.2";

export const HEALTH_RUNTIME_FINDING_CODES = Object.freeze({
  HEALTH_RUNTIME_AUTH_REQUIRED:
    "Readiness was requested without a validated authenticated console state, so the adapter refused before contacting the secured operation.",
  HEALTH_RUNTIME_DESCRIPTOR_INVALID:
    "The generated health request descriptor did not remain a bodyless same-origin GET, so the adapter refused rather than sending an invented or unsafe request.",
  HEALTH_RUNTIME_FETCH_UNAVAILABLE:
    "No callable fetch surface was supplied or available, so the adapter could not perform a health observation.",
  HEALTH_RUNTIME_INPUT_INVALID:
    "A runtime call carried fields or values outside its closed input contract, so the adapter refused rather than silently accepting transport authority.",
  HEALTH_RUNTIME_OPTIONS_INVALID:
    "The runtime adapter options were not the closed fetch-only configuration, so credential, origin, or header authority might otherwise enter U02.",
  HEALTH_RUNTIME_RESPONSE_INVALID:
    "The injected fetch returned a value that was not a Response-compatible HTTP observation, so no health receipt could truthfully be derived.",
});

export class ConsoleHealthRuntimeError extends Error {
  constructor(code, detail, context = {}) {
    super(`${code}: ${detail}`);
    this.name = "ConsoleHealthRuntimeError";
    this.code = code;
    this.detail = detail;
    this.reason = HEALTH_RUNTIME_FINDING_CODES[code];
    this.context = deepFreeze({ ...context });
    Object.freeze(this);
  }
}

const fail = (code, detail, context = {}) => {
  throw new ConsoleHealthRuntimeError(code, detail, context);
};

const isPlainDataObject = (value) =>
  value !== null &&
  typeof value === "object" &&
  !Array.isArray(value) &&
  !utilTypes.isProxy(value) &&
  (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);

const requireClosedObject = (candidate, { allowed, required = [], label, code }) => {
  if (!isPlainDataObject(candidate)) {
    fail(code, `${label} must be a plain data object`, {
      received: candidate === null ? "null" : typeof candidate,
    });
  }
  const keys = Object.keys(candidate).sort();
  const unknown = keys.filter((key) => !allowed.includes(key));
  const missing = required.filter((key) => !Object.hasOwn(candidate, key));
  if (unknown.length > 0 || missing.length > 0) {
    fail(code, `${label} does not match its closed field set`, {
      allowed: [...allowed],
      missing,
      received: keys,
      unknown,
    });
  }
  return candidate;
};

const requireSignal = (signal) => {
  if (signal === undefined) return undefined;
  if (
    signal === null ||
    typeof signal !== "object" ||
    utilTypes.isProxy(signal) ||
    typeof signal.aborted !== "boolean" ||
    typeof signal.addEventListener !== "function" ||
    typeof signal.removeEventListener !== "function"
  ) {
    fail("HEALTH_RUNTIME_INPUT_INVALID", "signal must be AbortSignal-compatible");
  }
  return signal;
};

const DESCRIPTOR_FIELDS = Object.freeze([
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

const CREDENTIAL_HEADER_NAMES = new Set([
  "authorization",
  "cookie",
  "proxy-authorization",
  "set-cookie",
  "x-api-key",
  "x-local-session",
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
      "HEALTH_RUNTIME_DESCRIPTOR_INVALID",
      "generated health URL must be a relative same-origin path",
    );
  }
  return value;
};

const requireSafeHeaders = (headers) => {
  if (!isPlainDataObject(headers)) {
    fail("HEALTH_RUNTIME_DESCRIPTOR_INVALID", "generated headers must be plain data");
  }
  for (const [name, value] of Object.entries(headers)) {
    const normalized = name.toLowerCase();
    if (CREDENTIAL_HEADER_NAMES.has(normalized) || normalized.includes("token")) {
      fail(
        "HEALTH_RUNTIME_DESCRIPTOR_INVALID",
        "generated health request carried a credential-bearing header",
      );
    }
    if (typeof value !== "string") {
      fail(
        "HEALTH_RUNTIME_DESCRIPTOR_INVALID",
        "generated health header values must be strings",
      );
    }
  }
  return headers;
};

const requireGeneratedDescriptor = (descriptor, expected) => {
  requireClosedObject(descriptor, {
    allowed: DESCRIPTOR_FIELDS,
    required: DESCRIPTOR_FIELDS,
    label: "generated health request descriptor",
    code: "HEALTH_RUNTIME_DESCRIPTOR_INVALID",
  });
  if (
    descriptor.operationId !== expected.operationId ||
    descriptor.successStatus !== expected.successStatus ||
    descriptor.path !== expected.path ||
    descriptor.pathTemplate !== expected.pathTemplate ||
    descriptor.url !== expected.url ||
    descriptor.method !== "GET" ||
    descriptor.body !== null ||
    descriptor.query !== "" ||
    typeof descriptor.operationId !== "string" ||
    typeof descriptor.successStatus !== "string"
  ) {
    fail(
      "HEALTH_RUNTIME_DESCRIPTOR_INVALID",
      "generated health descriptor changed operation, route, status, or GET semantics",
    );
  }
  requireSafeRelativeUrl(descriptor.url);
  requireSafeHeaders(descriptor.headers);
  return descriptor;
};

const transportFailureReceipt = (operationId) =>
  deepFreeze({
    body: null,
    body_hash: null,
    operation_id: operationId,
    outcome: "TRANSPORT_FAILURE",
    status: null,
  });

const problemReceipt = (operationId, status) =>
  deepFreeze({
    body: null,
    body_hash: null,
    operation_id: operationId,
    outcome: "PROBLEM",
    status: String(status),
  });

const successReceipt = (operationId, status, body) =>
  deepFreeze({
    body,
    body_hash: canonicalJsonSha256(body),
    operation_id: operationId,
    outcome: "SUCCESS",
    status: String(status),
  });

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
      "HEALTH_RUNTIME_RESPONSE_INVALID",
      "fetch must return a Response-compatible object with status, headers.get, and json",
    );
  }
  return response;
};

const isJsonMediaType = (value) => {
  if (typeof value !== "string") return false;
  const mediaType = value.split(";", 1)[0].trim().toLowerCase();
  return mediaType === "application/json" || /^application\/[a-z0-9!#$&^_.+-]+\+json$/u.test(mediaType);
};

const validateLivenessBody = (candidate) => {
  if (
    !isPlainDataObject(candidate) ||
    Object.keys(candidate).length !== 1 ||
    !Object.hasOwn(candidate, "status") ||
    candidate.status !== "live"
  ) {
    throw new TypeError("liveness response is not the declared constant body");
  }
  return deepFreeze({ status: "live" });
};

const validateReadinessBody = (candidate) => validateHealthReport(candidate);

const executeGeneratedOperation = async ({ fetchImpl, operation, signal, validateBody }) => {
  const expected = operation({});
  return operation({}, async (descriptor) => {
    requireGeneratedDescriptor(descriptor, expected);
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
      return transportFailureReceipt(descriptor.operationId);
    }
    requireResponseCompatible(response);
    if (String(response.status) !== descriptor.successStatus) {
      return problemReceipt(descriptor.operationId, response.status);
    }
    let contentType;
    try {
      contentType = response.headers.get("content-type");
    } catch {
      fail("HEALTH_RUNTIME_RESPONSE_INVALID", "response headers could not be read");
    }
    if (!isJsonMediaType(contentType)) {
      return problemReceipt(descriptor.operationId, response.status);
    }
    let decoded;
    try {
      decoded = await response.json();
    } catch {
      return problemReceipt(descriptor.operationId, response.status);
    }
    let body;
    try {
      body = validateBody(decoded);
    } catch {
      return problemReceipt(descriptor.operationId, response.status);
    }
    return successReceipt(descriptor.operationId, response.status, body);
  });
};

export const createHealthRuntimeAdapter = (options = {}) => {
  requireClosedObject(options, {
    allowed: ["fetch"],
    label: "health runtime options",
    code: "HEALTH_RUNTIME_OPTIONS_INVALID",
  });
  const fetchImpl = Object.hasOwn(options, "fetch") ? options.fetch : globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    fail("HEALTH_RUNTIME_FETCH_UNAVAILABLE", "fetch must be a callable function");
  }

  const probeLiveness = async (input = {}) => {
    requireClosedObject(input, {
      allowed: ["signal"],
      label: "liveness probe input",
      code: "HEALTH_RUNTIME_INPUT_INVALID",
    });
    return executeGeneratedOperation({
      fetchImpl,
      operation: getLiveness,
      signal: requireSignal(input.signal),
      validateBody: validateLivenessBody,
    });
  };

  const probeReadiness = async (input = {}) => {
    requireClosedObject(input, {
      allowed: ["auth", "signal"],
      required: ["auth"],
      label: "readiness probe input",
      code: "HEALTH_RUNTIME_INPUT_INVALID",
    });
    let auth;
    try {
      auth = validateAuthState(input.auth);
    } catch {
      fail("HEALTH_RUNTIME_INPUT_INVALID", "auth must be a valid console auth state");
    }
    if (!isAuthorized(auth)) {
      fail(
        "HEALTH_RUNTIME_AUTH_REQUIRED",
        "readiness requires an authenticated console state",
      );
    }
    return executeGeneratedOperation({
      fetchImpl,
      operation: getReadiness,
      signal: requireSignal(input.signal),
      validateBody: validateReadinessBody,
    });
  };

  return Object.freeze({ probeLiveness, probeReadiness });
};
