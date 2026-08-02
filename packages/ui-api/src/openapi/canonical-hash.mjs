// Canonical JSON serialisation and SHA-256 digests for ui-api receipts.
//
// `packages/plugin-host/src/skill-router/skill-router.mjs` already exports an
// equivalent pair (`canonicalizeSkillRoutingJson`,
// `computeSkillRoutingDecisionHash`).  It is deliberately NOT imported here:
//
//   * `packages/boundary-policy.json` sets `sourceImportPolicy` to
//     `public-package-api-only`, and `packages/repo-checks/check-boundaries.mjs`
//     fails any `@epistemic-foundry/<pkg>/src/...` specifier.  The plugin-host
//     package manifest declares no `exports`/`main` entry point, so there is no
//     package-level path to that module at all.
//   * ui-api and plugin-host both sit on the `adapter` layer, so an edge
//     between them would be a sibling edge rather than the inward edge the
//     layer policy is built around.
//
// The canonical form is therefore restated here rather than shared: object keys
// sorted by Unicode code point, no insignificant whitespace, `sha256:` prefix.
// That duplication is a boundary cost, and it is recorded here rather than
// hidden behind a deep import.

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

/**
 * SHA-256 of raw bytes, prefixed with its algorithm.
 *
 * @param {Uint8Array | string} bytes
 * @returns {string}
 */
export const bytesSha256 = (bytes) =>
  `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
