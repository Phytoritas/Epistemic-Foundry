// Frozen CLI exit-code table for the sealed MCP error vocabulary.
//
// The error vocabulary is not restated here: it is read from the sealed
// contract at contracts/mcp/t01/foundry-mcp-tool-error.schema.json, and the
// table must cover it exactly.  A new error code with no exit code, or an exit
// code for a name the contract does not define, fails at load rather than
// silently mapping to a generic failure.
//
// Exit codes stay inside 1..125.  126 and 127 belong to the shell ("found but
// not executable", "not found") and 128+N to signals; reusing them would make a
// tool failure indistinguishable from a launch failure.

import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const HERE = dirname(fileURLToPath(import.meta.url));
// packages/plugin-host/src/cli -> repository root
const REPOSITORY_ROOT = join(HERE, "..", "..", "..", "..");
const ERROR_SCHEMA_PATH = join(
  REPOSITORY_ROOT,
  "contracts",
  "mcp",
  "t01",
  "foundry-mcp-tool-error.schema.json",
);

/** Success. Reserved and never assigned to an error code. */
export const EXIT_SUCCESS = 0;
/** The lowest and highest exit codes this CLI may ever return for an error. */
export const EXIT_CODE_FLOOR = 1;
export const EXIT_CODE_CEILING = 125;
/** Reserved by the shell; a tool failure must never collide with these. */
export const RESERVED_EXIT_CODES = Object.freeze([126, 127]);

// One stable code per sealed error name. These numbers are a wire contract:
// scripts branch on them, so they may be added to but never reassigned.
const EXIT_CODES = Object.freeze({
  INVALID_REQUEST: 10,
  UNKNOWN_TOOL: 11,
  INVALID_INPUT: 12,
  UNAUTHENTICATED: 20,
  WORKSPACE_DENIED: 21,
  UNAUTHORIZED: 22,
  NOT_FOUND: 30,
  IDEMPOTENCY_CONFLICT: 40,
  PLAN_COMPILATION_REJECTED: 41,
  INTERNAL: 70,
});

/** Raised when the table and the sealed contract disagree. */
export class CliContractError extends Error {
  constructor(code, message, context = null) {
    super(message);
    this.name = "CliContractError";
    this.code = code;
    this.context = context;
  }
}

function sealedErrorCodes() {
  const schema = require(ERROR_SCHEMA_PATH);
  const declared = schema?.properties?.error_code?.enum;
  if (!Array.isArray(declared) || declared.length === 0) {
    throw new CliContractError(
      "ERROR_VOCABULARY_UNREADABLE",
      "the sealed error envelope declares no error_code enum",
    );
  }
  return declared.map(String);
}

function verifyTable() {
  const declared = sealedErrorCodes();
  const mapped = Object.keys(EXIT_CODES);
  const missing = declared.filter((name) => !(name in EXIT_CODES)).sort();
  const unknown = mapped.filter((name) => !declared.includes(name)).sort();
  if (missing.length > 0 || unknown.length > 0) {
    throw new CliContractError(
      "EXIT_CODE_TABLE_INCOMPLETE",
      "the exit-code table must cover the sealed error vocabulary exactly",
      { missing, unknown },
    );
  }
  const seen = new Map();
  for (const [name, code] of Object.entries(EXIT_CODES)) {
    if (!Number.isInteger(code)) {
      throw new CliContractError(
        "EXIT_CODE_INVALID",
        `${name} must map to an integer exit code`,
      );
    }
    if (code < EXIT_CODE_FLOOR || code > EXIT_CODE_CEILING) {
      throw new CliContractError(
        "EXIT_CODE_OUT_OF_RANGE",
        `${name} maps to ${code}, outside ${EXIT_CODE_FLOOR}..${EXIT_CODE_CEILING}`,
      );
    }
    if (RESERVED_EXIT_CODES.includes(code)) {
      throw new CliContractError(
        "EXIT_CODE_RESERVED",
        `${name} maps to ${code}, which the shell reserves`,
      );
    }
    if (seen.has(code)) {
      throw new CliContractError(
        "EXIT_CODE_COLLISION",
        `${name} and ${seen.get(code)} both map to ${code}`,
      );
    }
    seen.set(code, name);
  }
  return declared;
}

const SEALED_ERROR_CODES = Object.freeze(verifyTable().slice().sort());

/** The sealed error vocabulary this table is bound to, sorted. */
export function sealedErrorVocabulary() {
  return SEALED_ERROR_CODES.slice();
}

/** The frozen name -> exit code table. */
export function exitCodeTable() {
  return { ...EXIT_CODES };
}

/**
 * The stable exit code for one sealed error name.
 *
 * An unknown name is refused rather than folded into INTERNAL: a caller that
 * cannot be told which failure occurred is worse off than one that is told the
 * CLI and the contract have diverged.
 */
export function exitCodeFor(errorCode) {
  if (typeof errorCode !== "string" || !(errorCode in EXIT_CODES)) {
    throw new CliContractError(
      "UNKNOWN_ERROR_CODE",
      `no stable exit code is defined for ${String(errorCode)}`,
      { error_code: errorCode ?? null },
    );
  }
  return EXIT_CODES[errorCode];
}

/** Reverse lookup, for tests and for diagnosing a captured exit status. */
export function errorCodeForExit(exitCode) {
  for (const [name, code] of Object.entries(EXIT_CODES)) {
    if (code === exitCode) {
      return name;
    }
  }
  return null;
}
