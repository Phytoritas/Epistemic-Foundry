// Planning-envelope receipt projection for the plugin host.
//
// The canonical hashing authority for plan artifacts is the Python
// application layer; the adapter treats `sha256` values as opaque identifiers
// and only enforces the structural receipt contract of the shared result
// envelope.  DURABLE_PLAN_ARTIFACT envelopes carry exactly one receipt;
// PURE_READ envelopes carry none.

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/;

export class ReceiptContractError extends Error {
  constructor(message) {
    super(message);
    this.name = "ReceiptContractError";
  }
}

function assertReceiptShape(receipt, index) {
  if (typeof receipt !== "object" || receipt === null || Array.isArray(receipt)) {
    throw new ReceiptContractError(`receipts[${index}] must be an object`);
  }
  const keys = Object.keys(receipt).sort();
  if (keys.join(",") !== "artifact_id,receipt_id,sha256") {
    throw new ReceiptContractError(`receipts[${index}] field set is not canonical`);
  }
  for (const field of ["artifact_id", "receipt_id"]) {
    if (typeof receipt[field] !== "string" || receipt[field].length === 0) {
      throw new ReceiptContractError(`receipts[${index}].${field} must be non-empty`);
    }
  }
  if (typeof receipt.sha256 !== "string" || !SHA256_PATTERN.test(receipt.sha256)) {
    throw new ReceiptContractError(`receipts[${index}].sha256 is not a sha256 id`);
  }
}

/**
 * Extract the receipts of a shared result envelope, enforcing the frozen
 * side-effect contract: planning envelopes bind exactly one receipt, read
 * envelopes bind none, and error envelopes have no receipts at all.
 */
export function extractReceipts(envelope, sideEffectClass) {
  if (typeof envelope !== "object" || envelope === null) {
    throw new ReceiptContractError("envelope must be an object");
  }
  if (Object.hasOwn(envelope, "error_code")) {
    throw new ReceiptContractError("error envelopes carry no receipts");
  }
  const receipts = envelope.receipts;
  if (!Array.isArray(receipts)) {
    throw new ReceiptContractError("envelope.receipts must be an array");
  }
  receipts.forEach(assertReceiptShape);
  if (sideEffectClass === "PURE_READ" && receipts.length !== 0) {
    throw new ReceiptContractError("a PURE_READ envelope cannot carry receipts");
  }
  if (sideEffectClass === "DURABLE_PLAN_ARTIFACT" && receipts.length !== 1) {
    throw new ReceiptContractError(
      "a DURABLE_PLAN_ARTIFACT envelope must carry exactly one receipt",
    );
  }
  return receipts.map((receipt) => ({ ...receipt }));
}
