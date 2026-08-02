/**
 * Privacy-safe log and telemetry redaction (Y02).
 *
 * Secrets and PII must never reach a log line or a trace attribute. This module
 * redacts a structured record two ways, and refuses to pretend it succeeded:
 *
 *   1. by KEY — any field whose name looks like a credential/PII carrier
 *      (`password`, `api_key`, `authorization`, `ssn`, ...) has its whole value
 *      replaced, whatever the value's type; and
 *   2. by VALUE — any string leaf is scanned for secret- and PII-shaped
 *      substrings (emails, bearer/JWT tokens, provider keys, card/SSN digits)
 *      and each match is replaced in place.
 *
 * It fails closed: malformed (proxied, symbol-keyed, non-canonical) input is
 * rejected rather than logged unredacted, and any caller-declared
 * `required_redactions` path that did not actually get redacted raises
 * `REDACTION_REQUIRED_MISSING` — a redaction that could not be applied is an
 * error, never a silent pass-through. `assertNoResidualSecrets` re-scans the
 * output so the "no secret or PII leaks" property is verifiable, not asserted.
 */

import {
  cloneCanonical,
  compareText,
  deepFreeze,
  fail,
  requirePlainRecord,
  requireString,
  sha256ObservabilityJson,
} from "./observability-primitives.mjs";

export const REDACTION_PLACEHOLDER = "[REDACTED]";

/** Field names that carry credentials or PII; the whole value is dropped. */
const SENSITIVE_KEY_PATTERN =
  /(?:pass(?:word|phrase)?|secret|token|api[_-]?key|access[_-]?key|authorization|auth|credential|private[_-]?key|session|cookie|ssn|otp)/iu;

/** Secret- and PII-shaped substrings redacted anywhere they appear in a value. */
const VALUE_PATTERNS = [
  { name: "EMAIL", pattern: /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/gu },
  { name: "BEARER", pattern: /Bearer\s+[A-Za-z0-9._~+/-]+=*/giu },
  { name: "JWT", pattern: /eyJ[A-Za-z0-9._-]{10,}/gu },
  { name: "AWS_ACCESS_KEY", pattern: /AKIA[0-9A-Z]{16}/gu },
  { name: "GITHUB_TOKEN", pattern: /gh[pousr]_[A-Za-z0-9]{20,}/gu },
  { name: "PROVIDER_KEY", pattern: /\b(?:sk|pk|rk)_[A-Za-z0-9]{16,}\b/gu },
  { name: "SSN", pattern: /\b\d{3}-\d{2}-\d{4}\b/gu },
  { name: "CARD", pattern: /\b(?:\d[ -]?){13,16}\b/gu },
];

const isSensitiveKey = (key) => typeof key === "string" && SENSITIVE_KEY_PATTERN.test(key);

/** Replace every secret/PII-shaped substring; report which patterns matched. */
const redactValueString = (value) => {
  let output = value;
  const matched = [];
  for (const { name, pattern } of VALUE_PATTERNS) {
    pattern.lastIndex = 0;
    if (pattern.test(output)) {
      matched.push(name);
      pattern.lastIndex = 0;
      output = output.replace(pattern, REDACTION_PLACEHOLDER);
    }
  }
  return { output, matched };
};

/** True if any value pattern still matches — used to prove no residual leak. */
const stringHasSecret = (value) =>
  VALUE_PATTERNS.some(({ pattern }) => {
    pattern.lastIndex = 0;
    return pattern.test(value);
  });

const walk = (value, path, keyName, redactions) => {
  // A leaf living under a sensitive key is dropped whole, whatever its type.
  if (isSensitiveKey(keyName) && (value === null || typeof value !== "object")) {
    redactions.push({ path, reason: "SENSITIVE_KEY" });
    return REDACTION_PLACEHOLDER;
  }
  if (typeof value === "string") {
    const { output, matched } = redactValueString(value);
    if (matched.length > 0) {
      redactions.push({ path, reason: "SENSITIVE_VALUE", patterns: matched });
    }
    return output;
  }
  if (value === null || typeof value === "number" || typeof value === "boolean") {
    return value;
  }
  if (Array.isArray(value)) {
    // Array elements inherit the array's key for the sensitive-key test.
    return value.map((entry, index) => walk(entry, `${path}[${index}]`, keyName, redactions));
  }
  const record = requirePlainRecord(value, path, { code: "REDACTION_INPUT_INVALID" });
  const output = {};
  for (const key of Object.keys(record).sort(compareText)) {
    output[key] = walk(record[key], path === "" ? key : `${path}.${key}`, key, redactions);
  }
  return output;
};

/**
 * Redact a structured log/telemetry record.
 *
 * @param {object} record - plain data record to redact (not mutated).
 * @param {object} [options]
 * @param {string[]} [options.required_redactions] - paths that MUST end up
 *   redacted; any that did not triggers a fail-closed error.
 * @returns frozen `{ redacted, redactions, redaction_count, redaction_hash }`.
 */
export const redactRecord = (record, options = {}) => {
  requirePlainRecord(record, "record", { code: "REDACTION_INPUT_INVALID" });
  const opts = requirePlainRecord(options, "options", {
    allowedKeys: ["required_redactions"],
    code: "REDACTION_INPUT_INVALID",
  });
  const required =
    opts.required_redactions === undefined ? [] : opts.required_redactions;
  if (!Array.isArray(required)) {
    fail("REDACTION_INPUT_INVALID", "required_redactions must be an array of paths");
  }
  for (const path of required) {
    requireString(path, "required_redactions entry", { code: "REDACTION_INPUT_INVALID" });
  }

  const redactions = [];
  const redacted = walk(cloneCanonical(record), "", null, redactions);
  redactions.sort((left, right) => compareText(left.path, right.path));

  const redactedPaths = new Set(redactions.map((entry) => entry.path));
  for (const path of required) {
    if (!redactedPaths.has(path)) {
      fail(
        "REDACTION_REQUIRED_MISSING",
        `required redaction was not applied at ${path}`,
        { path },
      );
    }
  }

  const result = {
    redacted,
    redactions,
    redaction_count: redactions.length,
  };
  result.redaction_hash = sha256ObservabilityJson(result);
  return deepFreeze(result);
};

/**
 * Re-scan an already-redacted record and fail closed if any secret or PII
 * survived — either a sensitive key still holding a real value, or a value that
 * still matches a secret/PII pattern.
 */
export const assertNoResidualSecrets = (record, label = "redacted record") => {
  const check = (value, path, keyName) => {
    if (typeof value === "string") {
      if (isSensitiveKey(keyName) && value !== REDACTION_PLACEHOLDER) {
        fail("RESIDUAL_SECRET", `sensitive field ${path} was not redacted`, { path });
      }
      if (stringHasSecret(value)) {
        fail("RESIDUAL_SECRET", `secret/PII pattern survived at ${path}`, { path });
      }
      return;
    }
    if (value === null || typeof value === "number" || typeof value === "boolean") {
      if (isSensitiveKey(keyName)) {
        fail("RESIDUAL_SECRET", `sensitive field ${path} was not redacted`, { path });
      }
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((entry, index) => check(entry, `${path}[${index}]`, keyName));
      return;
    }
    const rec = requirePlainRecord(value, path, { code: "REDACTION_INPUT_INVALID" });
    for (const key of Object.keys(rec)) {
      check(rec[key], path === "" ? key : `${path}.${key}`, key);
    }
  };
  check(record, "", null);
  return record;
};
