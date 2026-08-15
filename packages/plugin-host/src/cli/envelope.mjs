// Canonical JSON rendering and round-trip checking for the CLI surface.
//
// `--json` is the machine surface and the human surface is separate, so the
// bytes the CLI writes must survive a parse and a re-render unchanged.  A
// command that cannot round-trip its own output is not emitting a contract, it
// is emitting a description of one.

import { CliContractError } from "./error-codes.mjs";

/** The single machine-readable output flag. Human text is never parsed. */
export const JSON_FLAG = "--json";

function canonicalize(value, seen) {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new CliContractError(
        "ENVELOPE_NOT_CANONICAL",
        "a non-finite number cannot be rendered as canonical JSON",
      );
    }
    return value;
  }
  if (Array.isArray(value)) {
    if (seen.has(value)) {
      throw new CliContractError(
        "ENVELOPE_NOT_CANONICAL",
        "a cyclic value cannot be rendered as canonical JSON",
      );
    }
    seen.add(value);
    const ownNames = Object.getOwnPropertyNames(value);
    if (
      Object.getOwnPropertySymbols(value).length > 0 ||
      ownNames.length !== value.length + 1
    ) {
      throw new CliContractError(
        "ENVELOPE_NOT_CANONICAL",
        "an array must contain only its indexed JSON values",
      );
    }
    const rendered = [];
    for (let index = 0; index < value.length; index += 1) {
      const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
      if (descriptor === undefined || !descriptor.enumerable || !("value" in descriptor)) {
        throw new CliContractError(
          "ENVELOPE_NOT_CANONICAL",
          "a sparse or accessor-backed array cannot be rendered as canonical JSON",
        );
      }
      rendered.push(canonicalize(descriptor.value, seen));
    }
    seen.delete(value);
    return rendered;
  }
  if (typeof value === "object") {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new CliContractError(
        "ENVELOPE_NOT_CANONICAL",
        "a CLI envelope may contain only plain JSON objects",
      );
    }
    if (seen.has(value)) {
      throw new CliContractError(
        "ENVELOPE_NOT_CANONICAL",
        "a cyclic value cannot be rendered as canonical JSON",
      );
    }
    seen.add(value);
    const keys = Object.keys(value).sort();
    if (
      Object.getOwnPropertySymbols(value).length > 0 ||
      Object.getOwnPropertyNames(value).length !== keys.length
    ) {
      throw new CliContractError(
        "ENVELOPE_NOT_CANONICAL",
        "a CLI envelope object must contain only enumerable string fields",
      );
    }
    const rendered = Object.create(null);
    for (const key of keys) {
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (descriptor === undefined || !("value" in descriptor)) {
        throw new CliContractError(
          "ENVELOPE_NOT_CANONICAL",
          `${key} must be a data field, not an accessor`,
        );
      }
      const entry = descriptor.value;
      if (entry === undefined) {
        throw new CliContractError(
          "ENVELOPE_NOT_CANONICAL",
          `${key} is undefined; an absent field must be null, not missing`,
        );
      }
      rendered[key] = canonicalize(entry, seen);
    }
    seen.delete(value);
    return rendered;
  }
  throw new CliContractError(
    "ENVELOPE_NOT_CANONICAL",
    `a ${typeof value} value cannot appear in a CLI envelope`,
  );
}

/** Render one envelope as canonical JSON with a trailing newline. */
export function renderJson(envelope) {
  if (envelope === null || typeof envelope !== "object" || Array.isArray(envelope)) {
    throw new CliContractError(
      "ENVELOPE_NOT_CANONICAL",
      "a CLI envelope must be a JSON object",
    );
  }
  return `${JSON.stringify(canonicalize(envelope, new Set()))}\n`;
}

/** Parse one rendered envelope back into an object. */
export function parseJson(text) {
  if (typeof text !== "string") {
    throw new CliContractError("ENVELOPE_UNPARSEABLE", "CLI output must be a string");
  }
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new CliContractError(
      "ENVELOPE_UNPARSEABLE",
      `CLI output is not valid JSON: ${error.message}`,
    );
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new CliContractError(
      "ENVELOPE_UNPARSEABLE",
      "CLI output must parse to a JSON object",
    );
  }
  return parsed;
}

/**
 * Whether an envelope survives render → parse → render unchanged.
 *
 * Byte identity is the test, not structural equality: a rendering that reorders
 * keys or drops a null still parses, and would quietly break any consumer that
 * hashes or diffs the output.
 */
export function roundTrips(envelope) {
  const first = renderJson(envelope);
  const second = renderJson(parseJson(first));
  return first === second;
}

/**
 * Render an envelope after proving it round-trips.
 *
 * The check runs before the bytes are emitted, so a non-round-tripping envelope
 * never reaches a consumer.
 */
export function emitJson(envelope) {
  const rendered = renderJson(envelope);
  if (renderJson(parseJson(rendered)) !== rendered) {
    throw new CliContractError(
      "ENVELOPE_NOT_ROUND_TRIPPING",
      "the rendered envelope does not survive a parse and re-render",
    );
  }
  return rendered;
}
