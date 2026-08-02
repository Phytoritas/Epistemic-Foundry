/**
 * U02 Foundry Console shell: navigation, view binding and honest read states.
 *
 * The shell is a view-model only.  There is no browser, no DOM, no HTTP and no
 * identity provider in this package, so nothing here renders pixels or sends a
 * request.  What it does own is the part that can be checked deterministically:
 *
 *   * every view binds one `operationId` of the generated client under
 *     `web/src/generated/ui-client`, which is itself generated from
 *     `openapi/epistemic-foundry-v1.openapi.yaml`.  A view naming an operation
 *     the client does not export is a refusal, so the console cannot grow a
 *     hand-written route that no contract test covers (EF4-I22);
 *   * whether a view mutates is *derived* from the operation's HTTP method in
 *     the generated route table, and a view that binds a non-GET operation
 *     without declaring the mutation is refused;
 *   * `READY`, `EMPTY_CONFIRMED`, `DEGRADED`, `UNAVAILABLE` and `UNKNOWN` are
 *     distinct, and a failed or absent response can never be rendered as an
 *     empty research state (EF4-I23);
 *   * a view that requires authentication refuses in any state other than
 *     `AUTHENTICATED` instead of rendering an empty page that reads like a
 *     confirmed absence of data.
 *
 * `UNKNOWN` is a client-local state, not an API state: it means no response has
 * been received yet.  It is kept separate from `EMPTY_CONFIRMED` (the backend
 * answered and there is nothing), `DEGRADED` (the backend answered with
 * declared limitations) and `UNAVAILABLE` (the backend failed or was not
 * reachable).
 */

import { types as utilTypes } from "node:util";

import * as generatedClient from "../generated/ui-client/index.mjs";

import {
  assertNoCredentialMaterial,
  AUTH_FINDING_CODES,
  ConsoleAuthError,
  isAuthorized,
  validateAuthState,
} from "./auth.mjs";
import { canonicalJsonSha256, deepFreeze, SHA256_PATTERN } from "./record-hash.mjs";

export const SHELL_VERSION = "4.0.0-u02.1";

/** Machine codes this module refuses with, each with its standing reason. */
export const SHELL_FINDING_CODES = Object.freeze({
  CLIENT_SURFACE_INVALID:
    "The supplied UI client does not expose the generated operation table, operation id list and source document provenance, so no view binding could be checked against a declared API surface.",
  CLIENT_OPERATION_UNBOUND:
    "The generated client declares an operation in its route table but exports no callable binding for it, so a view naming that operation would compile and then fail at call time.",
  VIEW_SPEC_INVALID:
    "A view specification is not a plain data object carrying exactly the declared view fields, so the shell could not tell what the view claims to bind or require.",
  VIEW_ID_DUPLICATE:
    "Two view specifications claim the same view id, so navigation could resolve one identifier to two different operations depending on registration order.",
  VIEW_OPERATION_UNKNOWN:
    "A view binds an operationId that the generated client does not export, which means the console would be inventing a route the canonical OpenAPI document never declared.",
  VIEW_MUTATION_UNDECLARED:
    "A view binds an operation whose declared HTTP method mutates server state while the view does not declare a mutation, so a write would be presented to the user as a read.",
  VIEW_MUTATION_OVERDECLARED:
    "A view declares a mutation while the operation it binds is a declared read, so the shell would warn about a write that the API surface cannot perform.",
  VIEW_UNKNOWN:
    "A render was requested for a view id that the navigation registry does not contain, so there is no operation binding, auth requirement or read model to render.",
  VIEW_REQUIRES_AUTHENTICATION:
    "A view that requires an authenticated session was requested while the session is not authenticated, and this shell refuses rather than rendering an empty page that reads as a confirmed absence of data.",
  RECEIPT_INVALID:
    "A response receipt is not a plain data object carrying exactly the declared receipt fields, so the read model state it implies could not be derived from anything checkable.",
  RECEIPT_OPERATION_MISMATCH:
    "A response receipt names a different operation than the view being rendered, so the shell would be labelling one operation's response as another operation's read model.",
  RECEIPT_OUTCOME_UNDECLARED:
    "A response receipt carries an outcome outside the declared SUCCESS, PROBLEM and TRANSPORT_FAILURE vocabulary, so no rule maps it to a read model state.",
  RECEIPT_STATUS_UNDECLARED:
    "A response receipt carries a status code the bound operation does not declare in the canonical document, so the shell would be rendering a response shape the contract never described.",
  READ_MODEL_STATE_OVERCLAIMED:
    "A caller claimed a read model state that does not follow from the receipt it supplied, so the rendered state would assert more or less than the response actually established.",
  BACKEND_FAILURE_AS_EMPTY:
    "A caller claimed a confirmed-empty read model on a receipt that records a backend problem or transport failure, and a backend failure is never rendered as an empty research state.",
});

/** A refusal raised by the console shell. */
export class ConsoleShellError extends Error {
  constructor(code, detail, context = {}) {
    super(`${code}: ${detail}`);
    this.name = "ConsoleShellError";
    this.code = code;
    this.detail = detail;
    this.reason = SHELL_FINDING_CODES[code] ?? AUTH_FINDING_CODES[code];
    this.context = deepFreeze({ ...context });
    Object.freeze(this);
  }
}

const fail = (code, detail, context = {}) => {
  throw new ConsoleShellError(code, detail, context);
};

/** The read model states a console view may be in. */
export const READ_MODEL_STATES = Object.freeze([
  "READY",
  "EMPTY_CONFIRMED",
  "DEGRADED",
  "UNAVAILABLE",
  "UNKNOWN",
]);

/** The outcomes a response receipt may record. */
export const RECEIPT_OUTCOMES = Object.freeze(["SUCCESS", "PROBLEM", "TRANSPORT_FAILURE"]);

const VIEW_SPEC_FIELDS = Object.freeze([
  "declares_mutation",
  "operation_id",
  "requires_auth",
  "title",
  "view_id",
]);

const RECEIPT_FIELDS = Object.freeze([
  "body_hash",
  "degraded_reasons",
  "item_count",
  "operation_id",
  "outcome",
  "status",
]);

/**
 * The local UI security posture this console is built to, restated as data.
 *
 * This is a declaration, not an enforcement point: binding, headers and policy
 * delivery belong to the packaged server, which this package does not own.  It
 * is stated here so a review can compare the console's assumptions against
 * `docs/plugin_ux_cli_and_mcp.md` section 6 without reading intent out of code.
 */
export const SHELL_SECURITY_POLICY = deepFreeze({
  content_security_policy: [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
  ],
  credential_storage: "NO_BROWSER_STORAGE_OF_CREDENTIAL_MATERIAL",
  cross_site_request_policy: "SAME_ORIGIN_AND_SESSION_BOUND_WRITES",
  evidence_rendering: "ESCAPED_TEXT_ONLY_NO_RAW_HTML",
  network_binding: "LOOPBACK_ONLY",
  write_methods_requiring_origin_check: ["DELETE", "PATCH", "POST", "PUT"],
});

const isPlainDataObject = (value) =>
  value !== null &&
  typeof value === "object" &&
  !Array.isArray(value) &&
  !utilTypes.isProxy(value) &&
  (Object.getPrototypeOf(value) === Object.prototype ||
    Object.getPrototypeOf(value) === null);

const isPlainArray = (value) =>
  Array.isArray(value) &&
  !utilTypes.isProxy(value) &&
  Object.getPrototypeOf(value) === Array.prototype;

const requireExactFields = (candidate, fields, label, code) => {
  if (!isPlainDataObject(candidate)) {
    fail(code, `${label} must be a plain data object`, {
      received: candidate === null ? "null" : typeof candidate,
    });
  }
  const keys = Object.keys(candidate).sort();
  const declared = [...fields].sort();
  if (keys.length !== declared.length || keys.some((key, index) => key !== declared[index])) {
    fail(code, `${label} must carry exactly the declared fields`, {
      declared,
      received: keys,
    });
  }
  return candidate;
};

const requireLabel = (value, field, code) => {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.length > 128 ||
    value.normalize("NFC") !== value ||
    /\p{Cc}/u.test(value)
  ) {
    fail(code, `${field} must be a printable NFC string of 1..128 characters`, { field });
  }
  return value;
};

/**
 * Check that a client really is a generated UI client surface.
 *
 * @param {Record<string, unknown>} client
 * @returns {Record<string, unknown>}
 */
const validateClientSurface = (client) => {
  if (client === null || typeof client !== "object") {
    fail("CLIENT_SURFACE_INVALID", "client must be a module namespace or object", {
      received: client === null ? "null" : typeof client,
    });
  }
  const operations = client.OPERATIONS;
  const operationIds = client.OPERATION_IDS;
  const sourceDocument = client.SOURCE_DOCUMENT;
  if (
    !isPlainDataObject(operations) ||
    !Array.isArray(operationIds) ||
    operationIds.length === 0 ||
    !isPlainDataObject(sourceDocument) ||
    typeof sourceDocument.sha256 !== "string" ||
    !SHA256_PATTERN.test(sourceDocument.sha256) ||
    typeof client.BASE_PATH !== "string"
  ) {
    fail(
      "CLIENT_SURFACE_INVALID",
      "client must expose OPERATIONS, OPERATION_IDS, SOURCE_DOCUMENT and BASE_PATH",
      { operation_id_count: Array.isArray(operationIds) ? operationIds.length : null },
    );
  }
  for (const operationId of operationIds) {
    if (!Object.hasOwn(operations, operationId)) {
      fail(
        "CLIENT_SURFACE_INVALID",
        `operation ${String(operationId)} is listed but absent from OPERATIONS`,
        { operation_id: operationId },
      );
    }
    if (typeof client[operationId] !== "function") {
      fail(
        "CLIENT_OPERATION_UNBOUND",
        `operation ${String(operationId)} is declared but not exported as a binding`,
        { operation_id: operationId },
      );
    }
  }
  return client;
};

/**
 * The console's default navigation, one view per bound operation.
 *
 * `mutating` is not listed here; it is derived from the generated route table
 * so a view cannot describe a write as a read.  `declares_mutation` is the
 * view's own claim, and the two must agree.
 */
export const DEFAULT_VIEW_SPECS = deepFreeze([
  {
    declares_mutation: false,
    operation_id: "getLiveness",
    requires_auth: false,
    title: "Process liveness",
    view_id: "liveness",
  },
  {
    declares_mutation: false,
    operation_id: "getReadiness",
    requires_auth: true,
    title: "Health and replay",
    view_id: "health",
  },
  {
    declares_mutation: false,
    operation_id: "getCapabilities",
    requires_auth: true,
    title: "Host capabilities",
    view_id: "capabilities",
  },
  {
    declares_mutation: false,
    operation_id: "listRuns",
    requires_auth: true,
    title: "Forge docket",
    view_id: "forge-docket",
  },
  {
    declares_mutation: false,
    operation_id: "getRun",
    requires_auth: true,
    title: "Run detail",
    view_id: "run-detail",
  },
  {
    declares_mutation: false,
    operation_id: "getRunEvents",
    requires_auth: true,
    title: "Run events",
    view_id: "run-events",
  },
  {
    declares_mutation: false,
    operation_id: "getClaim",
    requires_auth: true,
    title: "Claim forge",
    view_id: "claim-forge",
  },
  {
    declares_mutation: false,
    operation_id: "getCoverageSnapshot",
    requires_auth: true,
    title: "Epistemic atlas coverage",
    view_id: "atlas-coverage",
  },
  {
    declares_mutation: false,
    operation_id: "getAdjudication",
    requires_auth: true,
    title: "Evidence parliament",
    view_id: "parliament",
  },
  {
    declares_mutation: false,
    operation_id: "getPassport",
    requires_auth: true,
    title: "Hypothesis passport",
    view_id: "passport",
  },
  {
    declares_mutation: true,
    operation_id: "requestCandidatePromotion",
    requires_auth: true,
    title: "Request candidate promotion",
    view_id: "promotion-request",
  },
  {
    declares_mutation: true,
    operation_id: "pauseRun",
    requires_auth: true,
    title: "Pause run",
    view_id: "run-pause",
  },
]);

const bindView = (spec, index, client) => {
  const label = `view_specs[${index}]`;
  try {
    assertNoCredentialMaterial(spec, label);
  } catch (error) {
    if (error instanceof ConsoleAuthError && error.code === "CREDENTIAL_MATERIAL_PRESENT") {
      fail("CREDENTIAL_MATERIAL_PRESENT", error.detail, error.context);
    }
    throw error;
  }
  requireExactFields(spec, VIEW_SPEC_FIELDS, label, "VIEW_SPEC_INVALID");
  const viewId = requireLabel(spec.view_id, `${label}.view_id`, "VIEW_SPEC_INVALID");
  const title = requireLabel(spec.title, `${label}.title`, "VIEW_SPEC_INVALID");
  const operationId = spec.operation_id;
  if (typeof spec.requires_auth !== "boolean" || typeof spec.declares_mutation !== "boolean") {
    fail("VIEW_SPEC_INVALID", `${label} requires boolean requires_auth and declares_mutation`, {
      view_id: viewId,
    });
  }
  if (
    typeof operationId !== "string" ||
    !client.OPERATION_IDS.includes(operationId) ||
    typeof client[operationId] !== "function"
  ) {
    fail(
      "VIEW_OPERATION_UNKNOWN",
      `${viewId} binds ${String(operationId)}, which the generated client does not export`,
      { operation_id: operationId ?? null, view_id: viewId },
    );
  }
  const operation = client.OPERATIONS[operationId];
  const mutating = operation.method !== "GET";
  if (mutating && !spec.declares_mutation) {
    fail(
      "VIEW_MUTATION_UNDECLARED",
      `${viewId} binds ${operation.method} ${operation.path} without declaring a mutation`,
      { method: operation.method, operation_id: operationId, view_id: viewId },
    );
  }
  if (!mutating && spec.declares_mutation) {
    fail(
      "VIEW_MUTATION_OVERDECLARED",
      `${viewId} declares a mutation while ${operationId} is a declared read`,
      { method: operation.method, operation_id: operationId, view_id: viewId },
    );
  }
  return {
    method: operation.method,
    mutating,
    operation_id: operationId,
    path_template: operation.path,
    path_parameters: [...operation.pathParameters],
    requires_auth: spec.requires_auth,
    response_schema_ref: operation.responseSchemaRef,
    success_status: operation.successStatus,
    title,
    view_id: viewId,
  };
};

/**
 * Build the console navigation registry from view specifications.
 *
 * @param {ReadonlyArray<unknown>} [viewSpecs]
 * @param {Record<string, unknown>} [client] generated UI client namespace
 * @returns {Readonly<Record<string, unknown>>}
 */
export function buildShellNavigation(viewSpecs = DEFAULT_VIEW_SPECS, client = generatedClient) {
  validateClientSurface(client);
  if (!isPlainArray(viewSpecs) || viewSpecs.length === 0) {
    fail("VIEW_SPEC_INVALID", "view specifications must be a non-empty plain array", {
      received: Array.isArray(viewSpecs) ? "empty or exotic array" : typeof viewSpecs,
    });
  }
  const views = viewSpecs.map((spec, index) => bindView(spec, index, client));
  const seen = new Set();
  for (const view of views) {
    if (seen.has(view.view_id)) {
      fail("VIEW_ID_DUPLICATE", `view id ${view.view_id} is registered twice`, {
        view_id: view.view_id,
      });
    }
    seen.add(view.view_id);
  }
  const mutatingViewIds = views.filter((view) => view.mutating).map((view) => view.view_id);
  const body = {
    base_path: client.BASE_PATH,
    kind: "EpistemicFoundryConsoleNavigation",
    mutating_view_ids: mutatingViewIds,
    read_model_states: [...READ_MODEL_STATES],
    security_policy: SHELL_SECURITY_POLICY,
    source_document: {
      operation_count: client.SOURCE_DOCUMENT.operationCount,
      path: client.SOURCE_DOCUMENT.path,
      route_table_sha256: client.SOURCE_DOCUMENT.routeTableSha256,
      sha256: client.SOURCE_DOCUMENT.sha256,
    },
    version: SHELL_VERSION,
    view_ids: views.map((view) => view.view_id),
    views,
  };
  assertNoCredentialMaterial(body, "navigation");
  const record = { ...body, record_hash: canonicalJsonSha256(body) };
  // `mutating_view_ids` is exposed as a fresh copy on each read so a caller may
  // sort or otherwise reorder it locally without mutating the frozen record.
  Object.defineProperty(record, "mutating_view_ids", {
    configurable: false,
    enumerable: true,
    get: () => [...mutatingViewIds],
  });
  return deepFreeze(record);
}

const findView = (navigation, viewId) => {
  const view = navigation.views.find((candidate) => candidate.view_id === viewId);
  if (view === undefined) {
    fail("VIEW_UNKNOWN", `no view is registered under ${String(viewId)}`, {
      registered: [...navigation.view_ids],
      view_id: viewId ?? null,
    });
  }
  return view;
};

const validateReceipt = (candidate, view, client) => {
  assertNoCredentialMaterial(candidate, "receipt");
  requireExactFields(candidate, RECEIPT_FIELDS, "receipt", "RECEIPT_INVALID");
  if (candidate.operation_id !== view.operation_id) {
    fail("RECEIPT_OPERATION_MISMATCH", "receipt names a different operation than the view", {
      receipt_operation_id: candidate.operation_id ?? null,
      view_operation_id: view.operation_id,
    });
  }
  const outcome = candidate.outcome;
  if (typeof outcome !== "string" || !RECEIPT_OUTCOMES.includes(outcome)) {
    fail("RECEIPT_OUTCOME_UNDECLARED", "receipt outcome is outside the declared vocabulary", {
      declared: [...RECEIPT_OUTCOMES],
    });
  }
  const operation = client.OPERATIONS[view.operation_id];
  const status = candidate.status;
  if (outcome === "TRANSPORT_FAILURE") {
    if (status !== null) {
      fail("RECEIPT_STATUS_UNDECLARED", "a transport failure carries no HTTP status", {
        operation_id: view.operation_id,
      });
    }
  } else if (typeof status !== "string" || !/^[1-5][0-9]{2}$/u.test(status)) {
    fail("RECEIPT_STATUS_UNDECLARED", "receipt status must be a three digit HTTP status", {
      operation_id: view.operation_id,
    });
  } else if (outcome === "SUCCESS" && status !== operation.successStatus) {
    fail("RECEIPT_STATUS_UNDECLARED", "a success receipt must carry the declared success status", {
      declared: operation.successStatus,
      operation_id: view.operation_id,
      status,
    });
  } else if (
    outcome === "PROBLEM" &&
    !operation.statusCodes.includes("default") &&
    !operation.statusCodes.includes(status)
  ) {
    fail("RECEIPT_STATUS_UNDECLARED", "the operation declares no such problem status", {
      declared: [...operation.statusCodes],
      operation_id: view.operation_id,
      status,
    });
  }
  const itemCount = candidate.item_count;
  if (itemCount !== null && (!Number.isSafeInteger(itemCount) || itemCount < 0)) {
    fail("RECEIPT_INVALID", "item_count must be null or a non-negative safe integer", {
      operation_id: view.operation_id,
    });
  }
  const degradedReasons = candidate.degraded_reasons;
  if (
    !isPlainArray(degradedReasons) ||
    degradedReasons.some((reason) => typeof reason !== "string" || reason.length === 0)
  ) {
    fail("RECEIPT_INVALID", "degraded_reasons must be an array of non-empty strings", {
      operation_id: view.operation_id,
    });
  }
  const bodyHash = candidate.body_hash;
  if (bodyHash !== null && (typeof bodyHash !== "string" || !SHA256_PATTERN.test(bodyHash))) {
    fail("RECEIPT_INVALID", "body_hash must be null or sha256:<64 lowercase hex>", {
      operation_id: view.operation_id,
    });
  }
  if (outcome === "SUCCESS" && bodyHash === null && operation.responseMediaType !== null) {
    fail("RECEIPT_INVALID", "a success receipt with a declared response body must carry its hash", {
      operation_id: view.operation_id,
    });
  }
  return deepFreeze({
    body_hash: bodyHash,
    degraded_reasons: [...degradedReasons],
    item_count: itemCount,
    operation_id: candidate.operation_id,
    outcome,
    status,
  });
};

const deriveReadModelState = (receipt) => {
  if (receipt === null) return "UNKNOWN";
  if (receipt.outcome !== "SUCCESS") return "UNAVAILABLE";
  if (receipt.degraded_reasons.length > 0) return "DEGRADED";
  if (receipt.item_count === 0) return "EMPTY_CONFIRMED";
  return "READY";
};

/**
 * Render one registered view against an auth state and an optional receipt.
 *
 * @param {Readonly<Record<string, unknown>>} navigation registry from `buildShellNavigation`
 * @param {{view_id: string, auth: unknown, receipt?: unknown, claimed_state?: string}} request
 * @param {Record<string, unknown>} [client] generated UI client namespace
 * @returns {Readonly<Record<string, unknown>>}
 */
export function renderView(navigation, request, client = generatedClient) {
  validateClientSurface(client);
  if (!isPlainDataObject(request)) {
    fail("VIEW_SPEC_INVALID", "a render request must be a plain data object", {
      received: request === null ? "null" : typeof request,
    });
  }
  assertNoCredentialMaterial(request, "render_request");
  const view = findView(navigation, request.view_id);
  const auth = validateAuthState(request.auth);
  if (view.requires_auth && !isAuthorized(auth)) {
    fail(
      "VIEW_REQUIRES_AUTHENTICATION",
      `${view.view_id} requires an authenticated session and the session is ${auth.state}`,
      { auth_state: auth.state, view_id: view.view_id },
    );
  }
  const candidateReceipt = request.receipt ?? null;
  const receipt = candidateReceipt === null ? null : validateReceipt(candidateReceipt, view, client);
  const dataState = deriveReadModelState(receipt);
  const claimedState = request.claimed_state ?? null;
  if (claimedState !== null && claimedState !== dataState) {
    if (claimedState === "EMPTY_CONFIRMED") {
      fail(
        "BACKEND_FAILURE_AS_EMPTY",
        `${view.view_id} was claimed EMPTY_CONFIRMED while the receipt derives ${dataState}`,
        { derived_state: dataState, view_id: view.view_id },
      );
    }
    fail(
      "READ_MODEL_STATE_OVERCLAIMED",
      `${view.view_id} was claimed ${String(claimedState)} while the receipt derives ${dataState}`,
      { claimed_state: claimedState, derived_state: dataState, view_id: view.view_id },
    );
  }
  const body = {
    auth_state: auth.state,
    data_state: dataState,
    degraded_reasons: receipt === null ? [] : [...receipt.degraded_reasons],
    item_count: receipt === null ? null : receipt.item_count,
    kind: "EpistemicFoundryConsoleViewRecord",
    method: view.method,
    mutating: view.mutating,
    navigation_hash: navigation.record_hash,
    operation_id: view.operation_id,
    path_template: view.path_template,
    receipt_body_hash: receipt === null ? null : receipt.body_hash,
    receipt_outcome: receipt === null ? null : receipt.outcome,
    receipt_status: receipt === null ? null : receipt.status,
    requires_auth: view.requires_auth,
    scheme: auth.scheme,
    session_label: auth.session_label,
    state_is_confirmed_empty: dataState === "EMPTY_CONFIRMED",
    title: view.title,
    version: SHELL_VERSION,
    view_id: view.view_id,
  };
  assertNoCredentialMaterial(body, "view_record");
  return deepFreeze({ ...body, record_hash: canonicalJsonSha256(body) });
}

/**
 * Re-derive the hash of a record this module emitted.
 *
 * @param {Readonly<Record<string, unknown>>} record
 * @returns {string}
 */
export function rederiveRecordHash(record) {
  const { record_hash: ignored, ...body } = record;
  return canonicalJsonSha256(body);
}
