/**
 * U02 explicit health states for the Foundry Console.
 *
 * The console's health surface is the pair of System operations the canonical
 * OpenAPI document declares, which the MCP tool catalogue names `foundry.health`
 * ("Component health with explicit degraded states"):
 *
 *   * `getLiveness`  -> `GET /health/live`, schema `Liveness` (`status: live`);
 *   * `getReadiness` -> `GET /health/ready`, schema
 *     `schemas/plugin-health-report.schema.json`.
 *
 * The rendered states are exactly the ones that schema declares - `PASS`,
 * `DEGRADED`, `FAIL`, `SAFE_MODE` for the report and `PASS`, `WARN`, `FAIL`,
 * `NOT_RUN` for each check - plus one client-local state, `UNKNOWN`, meaning no
 * response has been received.  `UNKNOWN` is not an API state and is never
 * collapsed into `PASS`.
 *
 * Two refusals carry the invariant:
 *
 *   * `HEALTH_OVERCLAIMED` - a shell may not claim an overall health state it
 *     has no successful readiness receipt for, and may not claim one that
 *     differs from the receipt it does have.  A liveness receipt is not a
 *     readiness receipt: a live process says nothing about dependency health.
 *   * `HEALTH_DEGRADATION_HIDDEN` - a report claiming overall `PASS` while
 *     carrying a `WARN`, `FAIL` or `NOT_RUN` check is refused rather than
 *     rendered, because that is degradation presented as health.
 *
 * There is no HTTP client here.  Receipts are supplied by the caller; this
 * module decides what may honestly be rendered from them.
 */

import { types as utilTypes } from "node:util";

import {
  assertNoCredentialMaterial,
  isAuthorized,
  validateAuthState,
} from "../../app/auth.mjs";
import { canonicalJsonSha256, deepFreeze, SHA256_PATTERN } from "../../app/record-hash.mjs";

export const HEALTH_VIEW_VERSION = "4.0.0-u02.1";

/** Machine codes this module refuses with, each with its standing reason. */
export const HEALTH_FINDING_CODES = Object.freeze({
  HEALTH_INPUT_INVALID:
    "The health view input is not a plain data object carrying exactly the declared fields, so the shell could not tell which receipts it was being asked to render from.",
  HEALTH_RECEIPT_INVALID:
    "A health receipt is not a plain data object carrying exactly the declared receipt fields, so the state it implies could not be derived from anything a review can check.",
  HEALTH_OPERATION_MISMATCH:
    "A health receipt names an operation other than the declared liveness or readiness operation of the canonical document, so it cannot describe the health surface it is being rendered as.",
  HEALTH_REPORT_INVALID:
    "A readiness body does not match the plugin health report schema field set, so it cannot be rendered as the canonical health report the API declares it returns.",
  HEALTH_STATE_UNDECLARED:
    "An overall health state was supplied that is outside the declared PASS, DEGRADED, FAIL and SAFE_MODE vocabulary of the plugin health report schema.",
  HEALTH_CHECK_STATUS_UNDECLARED:
    "A health check status was supplied that is outside the declared PASS, WARN, FAIL and NOT_RUN vocabulary of the plugin health report schema.",
  HEALTH_PROFILE_UNDECLARED:
    "A health report names a profile outside the declared LITE, RESEARCH, TEAM and REGULATED vocabulary, so the rendered profile indicator would not match any qualified deployment.",
  HEALTH_LIVENESS_INVALID:
    "A liveness body is not the declared constant liveness shape, so the console cannot state that the process answered the unauthenticated liveness probe.",
  HEALTH_OVERCLAIMED:
    "An overall health state was claimed without a successful readiness receipt to support it, or one that contradicts the receipt supplied, and this console never renders health it has not received.",
  HEALTH_DEGRADATION_HIDDEN:
    "A health report claims an overall PASS while carrying a check that warned, failed or was never run, which renders degradation as health instead of showing it.",
  HEALTH_REQUIRES_AUTHENTICATION:
    "The readiness operation is a secured operation and readiness was requested without an authenticated session, so the console refuses rather than presenting unknown health as confirmed health.",
});

/** A refusal raised by the console health view. */
export class ConsoleHealthError extends Error {
  constructor(code, detail, context = {}) {
    super(`${code}: ${detail}`);
    this.name = "ConsoleHealthError";
    this.code = code;
    this.detail = detail;
    this.reason = HEALTH_FINDING_CODES[code];
    this.context = deepFreeze({ ...context });
    Object.freeze(this);
  }
}

const fail = (code, detail, context = {}) => {
  throw new ConsoleHealthError(code, detail, context);
};

/** The overall states `schemas/plugin-health-report.schema.json` declares. */
export const HEALTH_OVERALL_STATES = Object.freeze(["PASS", "DEGRADED", "FAIL", "SAFE_MODE"]);

/** The per-check statuses the same schema declares. */
export const HEALTH_CHECK_STATUSES = Object.freeze(["PASS", "WARN", "FAIL", "NOT_RUN"]);

/** The profiles the same schema declares. */
export const HEALTH_PROFILES = Object.freeze(["LITE", "RESEARCH", "TEAM", "REGULATED"]);

/** What the console may render: the declared states plus an honest unknown. */
export const HEALTH_RENDER_STATES = Object.freeze(["UNKNOWN", ...HEALTH_OVERALL_STATES]);

/** Liveness as the console renders it; `LIVE` is the document's only constant. */
export const LIVENESS_RENDER_STATES = Object.freeze(["UNKNOWN", "LIVE", "UNAVAILABLE"]);

/** The declared operations of the health surface. */
export const LIVENESS_OPERATION_ID = "getLiveness";
export const READINESS_OPERATION_ID = "getReadiness";

const HEALTH_INPUT_FIELDS = Object.freeze([
  "auth",
  "claimed_overall",
  "liveness_receipt",
  "readiness_receipt",
]);
const HEALTH_RECEIPT_FIELDS = Object.freeze([
  "body",
  "body_hash",
  "operation_id",
  "outcome",
  "status",
]);
const REPORT_FIELDS = Object.freeze([
  "checks",
  "generated_at",
  "health_id",
  "host_capability_report_id",
  "overall",
  "plugin_version",
  "profile",
  "report_hash",
]);
const CHECK_FIELDS = Object.freeze(["check_id", "details", "remediation", "status"]);

const RECEIPT_OUTCOMES = Object.freeze(["SUCCESS", "PROBLEM", "TRANSPORT_FAILURE"]);

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
    fail(code, `${label} must carry exactly the declared fields`, { declared, received: keys });
  }
  return candidate;
};

const requireText = (value, field, code, maxLength = 512) => {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.length > maxLength ||
    value.normalize("NFC") !== value ||
    /\p{Cc}/u.test(value)
  ) {
    fail(code, `${field} must be a printable NFC string of 1..${maxLength} characters`, { field });
  }
  return value;
};

const validateCheck = (candidate, index) => {
  const label = `checks[${index}]`;
  requireExactFields(candidate, CHECK_FIELDS, label, "HEALTH_REPORT_INVALID");
  const status = candidate.status;
  if (typeof status !== "string" || !HEALTH_CHECK_STATUSES.includes(status)) {
    fail("HEALTH_CHECK_STATUS_UNDECLARED", `${label}.status is outside the declared vocabulary`, {
      declared: [...HEALTH_CHECK_STATUSES],
    });
  }
  const remediation = candidate.remediation;
  if (
    !isPlainArray(remediation) ||
    remediation.some((entry) => typeof entry !== "string" || entry.length === 0)
  ) {
    fail("HEALTH_REPORT_INVALID", `${label}.remediation must be an array of non-empty strings`, {
      check_index: index,
    });
  }
  return {
    check_id: requireText(candidate.check_id, `${label}.check_id`, "HEALTH_REPORT_INVALID", 128),
    details: requireText(candidate.details, `${label}.details`, "HEALTH_REPORT_INVALID"),
    remediation: [...remediation],
    status,
  };
};

/**
 * Validate a readiness body against the declared plugin health report shape.
 *
 * @param {unknown} candidate
 * @returns {Readonly<Record<string, unknown>>}
 */
export const validateHealthReport = (candidate) => {
  assertNoCredentialMaterial(candidate, "health_report");
  requireExactFields(candidate, REPORT_FIELDS, "health report", "HEALTH_REPORT_INVALID");
  const overall = candidate.overall;
  if (typeof overall !== "string" || !HEALTH_OVERALL_STATES.includes(overall)) {
    fail("HEALTH_STATE_UNDECLARED", "overall is outside the declared health state vocabulary", {
      declared: [...HEALTH_OVERALL_STATES],
    });
  }
  const profile = candidate.profile;
  if (typeof profile !== "string" || !HEALTH_PROFILES.includes(profile)) {
    fail("HEALTH_PROFILE_UNDECLARED", "profile is outside the declared profile vocabulary", {
      declared: [...HEALTH_PROFILES],
    });
  }
  if (!isPlainArray(candidate.checks) || candidate.checks.length === 0) {
    fail("HEALTH_REPORT_INVALID", "checks must be a non-empty array", { overall });
  }
  const checks = candidate.checks.map(validateCheck);
  const reportHash = candidate.report_hash;
  if (typeof reportHash !== "string" || !SHA256_PATTERN.test(reportHash)) {
    fail("HEALTH_REPORT_INVALID", "report_hash must be sha256:<64 lowercase hex>", { overall });
  }
  if (overall === "PASS") {
    const hidden = checks.filter((check) => check.status !== "PASS");
    if (hidden.length > 0) {
      fail("HEALTH_DEGRADATION_HIDDEN", "an overall PASS carries a non-passing check", {
        hidden_check_ids: hidden.map((check) => check.check_id),
        hidden_statuses: hidden.map((check) => check.status),
      });
    }
  }
  const normalized = {
    checks,
    generated_at: requireText(
      candidate.generated_at,
      "generated_at",
      "HEALTH_REPORT_INVALID",
      64,
    ),
    health_id: requireText(candidate.health_id, "health_id", "HEALTH_REPORT_INVALID", 128),
    host_capability_report_id: requireText(
      candidate.host_capability_report_id,
      "host_capability_report_id",
      "HEALTH_REPORT_INVALID",
      128,
    ),
    overall,
    plugin_version: requireText(
      candidate.plugin_version,
      "plugin_version",
      "HEALTH_REPORT_INVALID",
      64,
    ),
    profile,
  };
  const derivedReportHash = canonicalJsonSha256(normalized);
  if (reportHash !== derivedReportHash) {
    fail("HEALTH_REPORT_INVALID", "report_hash does not match the normalized health report", {
      claimed_report_hash: reportHash,
      derived_report_hash: derivedReportHash,
    });
  }
  return deepFreeze({ ...normalized, report_hash: reportHash });
};

const validateReceipt = (candidate, expectedOperationId, label) => {
  assertNoCredentialMaterial(candidate, label);
  requireExactFields(candidate, HEALTH_RECEIPT_FIELDS, label, "HEALTH_RECEIPT_INVALID");
  if (candidate.operation_id !== expectedOperationId) {
    fail("HEALTH_OPERATION_MISMATCH", `${label} must name ${expectedOperationId}`, {
      expected: expectedOperationId,
      received: candidate.operation_id ?? null,
    });
  }
  const outcome = candidate.outcome;
  if (typeof outcome !== "string" || !RECEIPT_OUTCOMES.includes(outcome)) {
    fail("HEALTH_RECEIPT_INVALID", `${label}.outcome is outside the declared vocabulary`, {
      declared: [...RECEIPT_OUTCOMES],
    });
  }
  const status = candidate.status;
  if (outcome === "TRANSPORT_FAILURE") {
    if (status !== null) {
      fail("HEALTH_RECEIPT_INVALID", `${label} records a transport failure with an HTTP status`, {
        outcome,
      });
    }
  } else if (typeof status !== "string" || !/^[1-5][0-9]{2}$/u.test(status)) {
    fail("HEALTH_RECEIPT_INVALID", `${label}.status must be a three digit HTTP status`, {
      outcome,
    });
  } else if (outcome === "SUCCESS" && status !== "200") {
    fail("HEALTH_RECEIPT_INVALID", `${label} declares success on a status other than 200`, {
      status,
    });
  }
  const bodyHash = candidate.body_hash;
  if (bodyHash !== null && (typeof bodyHash !== "string" || !SHA256_PATTERN.test(bodyHash))) {
    fail("HEALTH_RECEIPT_INVALID", `${label}.body_hash must be null or sha256:<64 hex>`, {
      outcome,
    });
  }
  if (outcome === "SUCCESS" && bodyHash === null) {
    fail("HEALTH_RECEIPT_INVALID", `${label} declares success without a response body hash`, {
      outcome,
    });
  }
  if (outcome !== "SUCCESS" && candidate.body !== null) {
    fail("HEALTH_RECEIPT_INVALID", `${label} carries a body on a non-success outcome`, { outcome });
  }
  return { body: candidate.body, body_hash: bodyHash, outcome, status };
};

const validateLivenessBody = (body) => {
  requireExactFields(body, ["status"], "liveness body", "HEALTH_LIVENESS_INVALID");
  if (body.status !== "live") {
    fail("HEALTH_LIVENESS_INVALID", "the declared liveness constant is the string live", {
      received: typeof body.status === "string" ? body.status : typeof body.status,
    });
  }
  return "LIVE";
};

const section = (id, title, state, visible, items) => ({ id, items, state, title, visible });

/**
 * Build the console health view.
 *
 * @param {{auth: unknown, claimed_overall?: string|null, liveness_receipt?: unknown,
 *   readiness_receipt?: unknown}} candidate
 * @returns {Readonly<Record<string, unknown>>}
 */
export function buildHealthView(candidate) {
  if (!isPlainDataObject(candidate)) {
    fail("HEALTH_INPUT_INVALID", "the health view input must be a plain data object", {
      received: candidate === null ? "null" : typeof candidate,
    });
  }
  assertNoCredentialMaterial(candidate, "health_view_input");
  const supplied = Object.keys(candidate).sort();
  const unsupported = supplied.filter((key) => !HEALTH_INPUT_FIELDS.includes(key));
  if (unsupported.length > 0 || !supplied.includes("auth")) {
    fail("HEALTH_INPUT_INVALID", "the health view input carries an unsupported or missing field", {
      declared: [...HEALTH_INPUT_FIELDS],
      received: supplied,
      unsupported,
    });
  }
  const input = {
    auth: candidate.auth,
    claimed_overall: candidate.claimed_overall ?? null,
    liveness_receipt: candidate.liveness_receipt ?? null,
    readiness_receipt: candidate.readiness_receipt ?? null,
  };
  const auth = validateAuthState(input.auth);

  const liveness =
    input.liveness_receipt === null
      ? { body_hash: null, outcome: null, state: "UNKNOWN", status: null }
      : (() => {
          const receipt = validateReceipt(
            input.liveness_receipt,
            LIVENESS_OPERATION_ID,
            "liveness receipt",
          );
          return {
            body_hash: receipt.body_hash,
            outcome: receipt.outcome,
            state: receipt.outcome === "SUCCESS" ? validateLivenessBody(receipt.body) : "UNAVAILABLE",
            status: receipt.status,
          };
        })();

  if (input.readiness_receipt !== null && !isAuthorized(auth)) {
    fail(
      "HEALTH_REQUIRES_AUTHENTICATION",
      `readiness requires an authenticated session and the session is ${auth.state}`,
      { auth_state: auth.state },
    );
  }
  const readiness =
    input.readiness_receipt === null
      ? { body_hash: null, outcome: null, report: null, status: null }
      : (() => {
          const receipt = validateReceipt(
            input.readiness_receipt,
            READINESS_OPERATION_ID,
            "readiness receipt",
          );
          return {
            body_hash: receipt.body_hash,
            outcome: receipt.outcome,
            report: receipt.outcome === "SUCCESS" ? validateHealthReport(receipt.body) : null,
            status: receipt.status,
          };
        })();

  const overall = readiness.report === null ? "UNKNOWN" : readiness.report.overall;
  const claimed = input.claimed_overall;
  if (claimed !== null) {
    if (typeof claimed !== "string" || !HEALTH_RENDER_STATES.includes(claimed)) {
      fail("HEALTH_STATE_UNDECLARED", "a claimed overall state must be a rendered health state", {
        declared: [...HEALTH_RENDER_STATES],
      });
    }
    if (readiness.report === null) {
      fail(
        "HEALTH_OVERCLAIMED",
        `overall ${claimed} was claimed with no successful readiness receipt`,
        {
          claimed_overall: claimed,
          liveness_state: liveness.state,
          readiness_outcome: readiness.outcome,
        },
      );
    }
    if (claimed !== overall) {
      fail(
        "HEALTH_OVERCLAIMED",
        `overall ${claimed} was claimed while the readiness receipt reports ${overall}`,
        { claimed_overall: claimed, receipt_overall: overall },
      );
    }
  }

  const checks = readiness.report === null ? [] : readiness.report.checks;
  const degradedChecks = checks.filter((check) => check.status !== "PASS");
  const dataState =
    readiness.report !== null
      ? "READY"
      : readiness.outcome === null
        ? "UNKNOWN"
        : "UNAVAILABLE";
  const body = {
    checks,
    data_state: dataState,
    degraded_checks: degradedChecks,
    heading: "Health and replay",
    kind: "EpistemicFoundryConsoleHealthView",
    liveness: {
      body_hash: liveness.body_hash,
      outcome: liveness.outcome,
      state: liveness.state,
      status: liveness.status,
    },
    overall,
    overall_is_declared_by_api: readiness.report !== null,
    profile: readiness.report === null ? null : readiness.report.profile,
    readiness: {
      body_hash: readiness.body_hash,
      operation_id: READINESS_OPERATION_ID,
      outcome: readiness.outcome,
      report_hash: readiness.report === null ? null : readiness.report.report_hash,
      status: readiness.status,
    },
    render_states: [...HEALTH_RENDER_STATES],
    sections: [
      section(
        "overall-health-state",
        "Overall health state",
        overall,
        true,
        readiness.report === null
          ? [{ label: "No readiness response has been received.", state: "UNKNOWN" }]
          : [{ label: `Reported by ${READINESS_OPERATION_ID}.`, state: overall }],
      ),
      section(
        "degraded-and-failed-checks",
        "Degraded and failed checks",
        readiness.report === null
          ? "UNKNOWN"
          : degradedChecks.length > 0
            ? "POPULATED"
            : "EMPTY_CONFIRMED",
        true,
        degradedChecks,
      ),
      section(
        "all-checks",
        "All declared checks",
        readiness.report === null
          ? "UNKNOWN"
          : checks.length > 0
            ? "POPULATED"
            : "EMPTY_CONFIRMED",
        true,
        checks,
      ),
      section(
        "process-liveness",
        "Process liveness",
        liveness.state,
        true,
        [{ label: "Liveness is not readiness.", state: liveness.state }],
      ),
    ],
    session_label: auth.session_label,
    version: HEALTH_VIEW_VERSION,
  };
  assertNoCredentialMaterial(body, "health_view");
  return deepFreeze({ ...body, record_hash: canonicalJsonSha256(body) });
}

/**
 * The health view for a console that has received nothing yet.
 *
 * @param {unknown} authState
 * @returns {Readonly<Record<string, unknown>>}
 */
export const unknownHealthView = (authState) => buildHealthView({ auth: authState });

/**
 * Re-derive the hash of a health record this module emitted.
 *
 * @param {Readonly<Record<string, unknown>>} record
 * @returns {string}
 */
export function rederiveHealthRecordHash(record) {
  const { record_hash: ignored, ...body } = record;
  return canonicalJsonSha256(body);
}
