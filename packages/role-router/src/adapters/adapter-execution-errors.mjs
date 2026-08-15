const DEFAULT_STAGE = "preflight";
const EFFECT_STATE_SET = new Set(["CONFIRMED", "NOT_STARTED", "UNKNOWN"]);

export const EXECUTION_EFFECT_STATES = Object.freeze([
  "NOT_STARTED",
  "UNKNOWN",
  "CONFIRMED",
]);

const freezeDetails = (details) => {
  if (details === undefined) return undefined;
  if (details === null || typeof details !== "object") {
    return Object.freeze({ value: details });
  }
  return Object.freeze({ ...details });
};

/**
 * Typed failure raised by the bounded adapter execution boundary.
 *
 * The state flags describe how far the local orchestration advanced. They do
 * not certify an EffectReceipt and do not authorize retry or reconciliation.
 */
export class AdapterExecutionError extends Error {
  constructor(
    code,
    message,
    {
      stage = DEFAULT_STAGE,
      adapterInvoked = false,
      intentState = "NOT_STARTED",
      attemptState = "NOT_STARTED",
      artifactState = "NOT_STARTED",
      receiptState = "NOT_STARTED",
      details = undefined,
    } = {},
  ) {
    super(message);
    this.name = "AdapterExecutionError";
    this.code = code;
    this.stage = stage;
    this.adapterInvoked = adapterInvoked;
    for (const [label, value] of Object.entries({
      intentState,
      attemptState,
      artifactState,
      receiptState,
    })) {
      if (!EFFECT_STATE_SET.has(value)) {
        throw new TypeError(label + " is outside the execution effect-state vocabulary");
      }
    }
    this.intentState = intentState;
    this.attemptState = attemptState;
    this.artifactState = artifactState;
    this.receiptState = receiptState;
    this.intentRegistered = intentState === "CONFIRMED";
    this.attemptStarted = attemptState === "CONFIRMED";
    this.artifactWritten = artifactState === "CONFIRMED";
    this.receiptRecorded = receiptState === "CONFIRMED";
    this.reconciliationRequired =
      [intentState, attemptState, artifactState, receiptState].includes(
        "UNKNOWN",
      ) ||
      (attemptState === "CONFIRMED" && receiptState !== "CONFIRMED");
    if (details !== undefined) this.details = freezeDetails(details);
  }
}

export const failAdapterExecution = (code, message, options = undefined) => {
  throw new AdapterExecutionError(code, message, options);
};

export const wrapAdapterExecutionError = (
  error,
  code,
  message,
  options = undefined,
) => {
  // The wrapped value may come from an injected provider/kernel/storage port.
  // It is deliberately ignored: foreign code, message, stage, effect states,
  // details, stack and cause never cross this public boundary. The caller's
  // locally observed state is the only error projection that is published.
  void error;
  return new AdapterExecutionError(code, message, options);
};
