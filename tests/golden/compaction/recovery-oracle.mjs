import { types as utilTypes } from "node:util";

import {
  requireFreshContextCapsule,
  verifyContextCapsuleIntegrity,
} from "../../../packages/context-capsule/src/index.mjs";

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const REQUEST_FIELDS = new Set([
  "capsule",
  "sealed_receipt",
  "freshness_state",
  "prose_summary",
]);
const RECEIPT_FIELDS = new Set(["receipt_id", "capsule_id", "capsule_hash"]);
const IS_PROXY = utilTypes.isProxy;
const GET_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const GET_PROTOTYPE = Object.getPrototypeOf;
const HAS_OWN = Object.hasOwn;

export class CompactionRecoveryError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "CompactionRecoveryError";
    this.code = code;
  }
}

const fail = (code, message) => {
  throw new CompactionRecoveryError(code, message);
};

const requirePlainDataRecord = (candidate, label, allowedFields, requiredFields) => {
  if (
    candidate === null ||
    typeof candidate !== "object" ||
    Array.isArray(candidate) ||
    IS_PROXY(candidate)
  ) {
    fail("INVALID_RECOVERY_INPUT", `${label} must be a non-proxy plain data object`);
  }
  const prototype = GET_PROTOTYPE(candidate);
  if (prototype !== Object.prototype && prototype !== null) {
    fail("INVALID_RECOVERY_INPUT", `${label} must not have a custom prototype`);
  }
  for (const key of Reflect.ownKeys(candidate)) {
    const descriptor = typeof key === "string" ? GET_DESCRIPTOR(candidate, key) : undefined;
    if (
      typeof key !== "string" ||
      !allowedFields.has(key) ||
      descriptor === undefined ||
      !descriptor.enumerable ||
      !HAS_OWN(descriptor, "value")
    ) {
      fail("INVALID_RECOVERY_INPUT", `${label} contains a non-data or unsupported field`);
    }
  }
  for (const key of requiredFields) {
    if (!HAS_OWN(candidate, key)) {
      fail(
        key === "capsule"
          ? "CANONICAL_CAPSULE_REQUIRED"
          : key === "sealed_receipt"
            ? "SEALED_CAPSULE_RECEIPT_REQUIRED"
            : "INVALID_RECOVERY_INPUT",
        `${label}.${key} is required`,
      );
    }
  }
  return candidate;
};

const readData = (record, key) => GET_DESCRIPTOR(record, key).value;

const validateReceipt = (candidate) => {
  const receipt = requirePlainDataRecord(
    candidate,
    "sealedReceipt",
    RECEIPT_FIELDS,
    RECEIPT_FIELDS,
  );
  const receiptId = readData(receipt, "receipt_id");
  const capsuleId = readData(receipt, "capsule_id");
  const capsuleHash = readData(receipt, "capsule_hash");
  if (
    typeof receiptId !== "string" ||
    receiptId.length === 0 ||
    typeof capsuleId !== "string" ||
    capsuleId.length === 0 ||
    typeof capsuleHash !== "string" ||
    !SHA256_PATTERN.test(capsuleHash)
  ) {
    fail("INVALID_SEALED_CAPSULE_RECEIPT", "sealed receipt fields are not canonical");
  }
  return { receiptId, capsuleId, capsuleHash };
};

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const entry of Object.values(value)) deepFreeze(entry);
  return Object.freeze(value);
};

/**
 * Test-only J04 recovery oracle. Narrative prose is deliberately never read:
 * only the integrity-verified, externally receipt-bound and fresh capsule may
 * project a phase cursor, blockers or governing hashes into resumed state.
 */
export const recoverPostCompaction = (candidate) => {
  const request = requirePlainDataRecord(candidate, "recoveryRequest", REQUEST_FIELDS, [
    "capsule",
    "sealed_receipt",
    "freshness_state",
  ]);

  const capsule = verifyContextCapsuleIntegrity(readData(request, "capsule"));
  const receipt = validateReceipt(readData(request, "sealed_receipt"));
  if (
    receipt.capsuleId !== capsule.capsule_id ||
    receipt.capsuleHash !== capsule.capsule_hash
  ) {
    fail(
      "SEALED_CAPSULE_RECEIPT_MISMATCH",
      "the observed capsule does not match the externally sealed receipt",
    );
  }

  const freshness = requireFreshContextCapsule(
    capsule,
    readData(request, "freshness_state"),
  );

  return deepFreeze({
    status: "RESUMABLE",
    authority_source: "SEALED_CONTEXT_CAPSULE",
    capsule_id: capsule.capsule_id,
    capsule_hash: capsule.capsule_hash,
    sealed_receipt_id: receipt.receiptId,
    phase: capsule.phase,
    open_blockers: [...capsule.open_blockers],
    run_spec_hash: capsule.run_spec_hash,
    policy_hash: capsule.policy_hash,
    authoritative_artifact_ids: [...capsule.artifact_ids],
    excluded_artifact_ids: [...capsule.excluded_artifact_ids],
    freshness,
  });
};
