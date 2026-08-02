/**
 * Canonical JSON and SHA-256 for Foundry Console records.
 *
 * `packages/ui-api/src/openapi/canonical-hash.mjs` already exports an
 * equivalent pair, and it is deliberately NOT imported here:
 *
 *   * `packages/boundary-policy.json` sets `sourceImportPolicy` to
 *     `public-package-api-only`, and `packages/repo-checks/check-boundaries.mjs`
 *     fails any `@epistemic-foundry/<pkg>/src/...` specifier.  The ui-api
 *     package manifest publishes no entry point for that module, so there is no
 *     package-level path to it.
 *   * The console consumes the ui-api surface through exactly one artifact,
 *     the generated client under `web/src/generated/ui-client`.  Reaching past
 *     that artifact into the adapter's private source would make the console
 *     depend on an internal shape no contract test covers.
 *
 * The canonical form is therefore restated here rather than shared: object keys
 * sorted by Unicode code point, no insignificant whitespace, `sha256:` prefix.
 * That duplication is a boundary cost and is recorded here rather than hidden
 * behind a deep import.
 */

import { createHash } from "node:crypto";

const compareCodePoints = (left, right) => {
  const leftPoints = [...left];
  const rightPoints = [...right];
  const shared = Math.min(leftPoints.length, rightPoints.length);
  for (let index = 0; index < shared; index += 1) {
    const difference = leftPoints[index].codePointAt(0) - rightPoints[index].codePointAt(0);
    if (difference !== 0) return difference < 0 ? -1 : 1;
  }
  if (leftPoints.length === rightPoints.length) return 0;
  return leftPoints.length < rightPoints.length ? -1 : 1;
};

/**
 * Serialise a plain JSON value into its canonical string form.
 *
 * @param {unknown} value
 * @returns {string}
 */
export const canonicalJson = (value) => {
  if (value === null) return "null";
  const kind = typeof value;
  if (kind === "string" || kind === "boolean") return JSON.stringify(value);
  if (kind === "number") {
    if (!Number.isFinite(value)) {
      throw new TypeError("canonical JSON cannot encode a non-finite number");
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((entry) => canonicalJson(entry)).join(",")}]`;
  }
  if (kind !== "object") {
    throw new TypeError(`canonical JSON cannot encode a ${kind} value`);
  }
  return `{${Object.keys(value)
    .sort(compareCodePoints)
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
    .join(",")}}`;
};

/**
 * SHA-256 of a canonical JSON value, prefixed with its algorithm.
 *
 * @param {unknown} value
 * @returns {string}
 */
export const canonicalJsonSha256 = (value) =>
  `sha256:${createHash("sha256").update(canonicalJson(value), "utf8").digest("hex")}`;

/** The shape every hash this console emits is checked against. */
export const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;

/**
 * Freeze a value and everything reachable from it through data properties.
 *
 * @template T
 * @param {T} value
 * @returns {T}
 */
export const deepFreeze = (value) => {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const entry of Object.values(value)) deepFreeze(entry);
  return Object.freeze(value);
};
