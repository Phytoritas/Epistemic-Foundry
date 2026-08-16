import {
  sealActionIntent,
  sealEffectReceipt,
} from "./effect-coordinator.mjs";

const OBJECT_FREEZE = Object.freeze;
const ACCEPTED_REGISTRATION_STATUSES = new Set(["REGISTERED", "EXISTING"]);

const terminalOutcome = (outcome) =>
  outcome.receipt !== null && outcome.receipt.status !== "UNKNOWN";

const registerIntent = ({ effects, errors, intent, messages }) => {
  let registration;
  try {
    registration = effects.registerIntent(intent);
  } catch {
    registration = effects.registerIntent(intent);
  }
  if (!ACCEPTED_REGISTRATION_STATUSES.has(registration.status)) {
    errors.effectInvalid(messages.unknownIntentStatus);
  }
  return registration;
};

const beginAttempt = ({ effects, inspectFallback, request }) => {
  try {
    return effects.beginAttempt(request);
  } catch (firstError) {
    if (!inspectFallback) return effects.beginAttempt(request);
    try {
      return effects.beginAttempt(request);
    } catch {
      let inspected;
      try {
        inspected = effects.inspect(request.intent_id);
      } catch {
        throw firstError;
      }
      if (inspected.attempt === null) throw firstError;
      return OBJECT_FREEZE({
        attempt: inspected.attempt,
        execute_permitted: false,
        status: "EXISTING_ATTEMPT",
      });
    }
  }
};

const persistReceipt = ({ effects, attemptId, receipt, mode }) => {
  const method = mode === "RECONCILIATION" ? "reconcile" : "recordReceipt";
  try {
    return effects[method]({ attempt_id: attemptId, receipt }).outcome;
  } catch (error) {
    let inspected;
    try {
      inspected = effects.inspect(receipt.intent_id);
    } catch {
      throw error;
    }
    if (inspected.receipt?.receipt_id !== receipt.receipt_id) throw error;
    try {
      return effects[method]({ attempt_id: attemptId, receipt }).outcome;
    } catch {
      return effects.inspect(receipt.intent_id);
    }
  }
};

const republishExistingReceipt = ({ effects, outcome }) => {
  if (
    (!outcome.event_reconciliation_required && !outcome.publication_confirmation_required) ||
    outcome.receipt === null
  ) {
    return outcome;
  }
  const mode = outcome.receipt_count > 1 ? "RECONCILIATION" : "EXECUTION";
  return persistReceipt({
    effects,
    attemptId: outcome.attempt.attempt_id,
    receipt: outcome.receipt,
    mode,
  });
};

const assertTerminalReconciled = ({ errors, message, outcome }) => {
  if (terminalOutcome(outcome) && outcome.reconciliation_required) {
    errors.reconciliationRequired(message);
  }
  return outcome;
};

const completeDryRun = ({ context, effects, errors, hooks, messages, outcome, mode }) => {
  const receipt = sealEffectReceipt(hooks.dryRunReceiptInput({ context, outcome }));
  const completed = persistReceipt({
    effects,
    attemptId: context.attempt.attempt_id,
    receipt,
    mode,
  });
  if (completed.reconciliation_required) {
    errors.reconciliationRequired(messages.dryRunReconciliationRequired);
  }
  return completed;
};

const recordUnknown = ({
  context,
  effects,
  error,
  errors,
  hooks,
  messages,
  prepared,
}) => {
  let outcome = effects.inspect(context.intent.intent_id);
  if (terminalOutcome(outcome)) {
    return assertTerminalReconciled({
      errors,
      message: messages.terminalReconciliationRequired,
      outcome,
    });
  }
  if (outcome.receipt?.status === "UNKNOWN") return outcome;

  const receipt = sealEffectReceipt(
    hooks.unknownReceiptInput({ context, error, outcome, prepared }),
  );
  try {
    outcome = persistReceipt({
      effects,
      attemptId: context.attempt.attempt_id,
      receipt,
      mode: "EXECUTION",
    });
  } catch (receiptError) {
    errors.reconciliationRequired(
      messages.unknownReceiptPersistenceFailed,
      {
        causeCode: hooks.errorCode(error),
        receiptCauseCode: hooks.errorCode(receiptError),
      },
      { cause: receiptError },
    );
  }
  return outcome;
};

const recoverExistingAttempt = ({
  context,
  effects,
  errors,
  hooks,
  lease,
  messages,
  outcome,
}) => {
  try {
    if (
      outcome.intent.intent_id !== context.intent.intent_id ||
      outcome.attempt?.attempt_id !== context.attempt.attempt_id
    ) {
      errors.recoveryInvalid(messages.recoveryIdentityChanged);
    }
    const recovery = hooks.recoverEffect({ context, lease, outcome });
    if (recovery === null) return outcome;

    const receipt = sealEffectReceipt(
      hooks.successReceiptInput({
        context,
        effectResult: recovery.effectResult,
        outcome,
        prepared: recovery.prepared,
      }),
    );
    const reconciled = persistReceipt({
      effects,
      attemptId: context.attempt.attempt_id,
      receipt,
      mode: "RECONCILIATION",
    });
    if (reconciled.reconciliation_required) {
      errors.reconciliationRequired(messages.recoveredReconciliationRequired);
    }
    return reconciled;
  } catch (error) {
    if (hooks.isRecoveryEvidenceFailure(error)) return outcome;
    throw error;
  }
};

export const createDurableMutationOrchestrator = ({
  behavior,
  effects,
  errors,
  hooks,
  messages,
}) => {
  const projectResult = ({ lease, operation, outcome, terminalMessage }) => {
    assertTerminalReconciled({ errors, message: terminalMessage, outcome });
    return hooks.projectResult({ lease, operation, outcome });
  };

  const execute = (candidate) => {
    const preparedCandidate = hooks.prepareCandidate(candidate);
    let priorEffect = null;
    try {
      priorEffect = effects.inspect(preparedCandidate.intentId);
    } catch (error) {
      if (error?.code !== "EFFECT_RECORD_MISSING") throw error;
    }

    const operation = hooks.bindOperation({ preparedCandidate, priorEffect });
    const intent = sealActionIntent(operation.intentInput);
    if (priorEffect !== null && !hooks.sameRecord(priorEffect.intent, intent)) {
      errors.effectInvalid(messages.storedIntentChanged);
    }

    const hasExistingDryRunAttempt =
      priorEffect !== null &&
      priorEffect.attempt !== null &&
      (
        !behavior.existingDryRunAttemptRequiresDefined ||
        priorEffect.attempt !== undefined
      );
    if (operation.dryRun && hasExistingDryRunAttempt) {
      const storedAttempt = priorEffect.attempt;
      if (
        storedAttempt.attempt_id !== operation.attemptId ||
        storedAttempt.intent_id !== intent.intent_id ||
        storedAttempt.started_at !== operation.startedAt
      ) {
        errors.effectInvalid(messages.storedDryRunAttemptChanged);
      }

      registerIntent({ effects, errors, intent, messages });
      const attemptResult = beginAttempt({
        effects,
        inspectFallback: behavior.existingDryRunAttemptInspectFallback,
        request: {
          attempt_id: storedAttempt.attempt_id,
          intent_id: intent.intent_id,
          started_at: storedAttempt.started_at,
        },
      });
      if (
        behavior.existingDryRunAttemptRequiresBoolean &&
        typeof attemptResult.execute_permitted !== "boolean"
      ) {
        errors.effectInvalid(messages.omittedExecutePermitted);
      }
      if (
        attemptResult.execute_permitted !== false ||
        !hooks.sameRecord(attemptResult.attempt, storedAttempt)
      ) {
        errors.effectInvalid(messages.existingDryRunAttemptPermitsExecution);
      }

      const context = hooks.createContext({
        attempt: storedAttempt,
        intent,
        operation,
      });
      let outcome = republishExistingReceipt({
        effects,
        outcome: effects.inspect(intent.intent_id),
      });
      if (!terminalOutcome(outcome)) {
        outcome = completeDryRun({
          context,
          effects,
          errors,
          hooks,
          messages,
          outcome,
          mode: "RECONCILIATION",
        });
      }
      return projectResult({
        lease: null,
        operation,
        outcome,
        terminalMessage: messages.dryRunReconciliationRequired,
      });
    }

    const lease = hooks.issueLease({ intent, operation });
    registerIntent({ effects, errors, intent, messages });
    const attemptResult = beginAttempt({
      effects,
      inspectFallback: true,
      request: {
        attempt_id: operation.attemptId,
        intent_id: intent.intent_id,
        started_at: operation.startedAt,
      },
    });
    if (typeof attemptResult.execute_permitted !== "boolean") {
      errors.effectInvalid(messages.omittedExecutePermitted);
    }

    const context = hooks.createContext({
      attempt: attemptResult.attempt,
      intent,
      operation,
    });
    let outcome;
    try {
      outcome = republishExistingReceipt({
        effects,
        outcome: effects.inspect(intent.intent_id),
      });
    } catch (error) {
      outcome = recordUnknown({
        context,
        effects,
        error,
        errors,
        hooks,
        messages,
        prepared: null,
      });
      return projectResult({
        lease,
        operation,
        outcome,
        terminalMessage: messages.terminalReconciliationRequired,
      });
    }

    if (terminalOutcome(outcome)) {
      return projectResult({
        lease,
        operation,
        outcome,
        terminalMessage: messages.terminalReconciliationRequired,
      });
    }

    if (!attemptResult.execute_permitted) {
      if (operation.dryRun) {
        outcome = completeDryRun({
          context,
          effects,
          errors,
          hooks,
          messages,
          outcome,
          mode: "RECONCILIATION",
        });
        return projectResult({
          lease,
          operation,
          outcome,
          terminalMessage: messages.dryRunReconciliationRequired,
        });
      }

      outcome = recoverExistingAttempt({
        context,
        effects,
        errors,
        hooks,
        lease,
        messages,
        outcome,
      });
      if (terminalOutcome(outcome)) {
        return projectResult({
          lease,
          operation,
          outcome,
          terminalMessage: messages.terminalReconciliationRequired,
        });
      }
      if (outcome.receipt?.status !== "UNKNOWN") {
        outcome = recordUnknown({
          context,
          effects,
          error: hooks.existingAttemptReconciliationError(),
          errors,
          hooks,
          messages,
          prepared: null,
        });
      }
      return projectResult({
        lease,
        operation,
        outcome,
        terminalMessage: messages.terminalReconciliationRequired,
      });
    }

    if (operation.dryRun) {
      outcome = completeDryRun({
        context,
        effects,
        errors,
        hooks,
        messages,
        outcome,
        mode: outcome.receipt?.status === "UNKNOWN" ? "RECONCILIATION" : "EXECUTION",
      });
      return projectResult({
        lease,
        operation,
        outcome,
        terminalMessage: messages.dryRunReconciliationRequired,
      });
    }

    let prepared = null;
    try {
      const effectResult = hooks.executeEffect({
        context,
        lease,
        outcome,
        setPrepared: (value) => {
          prepared = value;
        },
      });
      outcome = effects.inspect(intent.intent_id);
      const receipt = sealEffectReceipt(
        hooks.successReceiptInput({ context, effectResult, outcome, prepared }),
      );
      outcome = persistReceipt({
        effects,
        attemptId: context.attempt.attempt_id,
        receipt,
        mode: outcome.receipt?.status === "UNKNOWN" ? "RECONCILIATION" : "EXECUTION",
      });
      if (outcome.reconciliation_required) {
        errors.reconciliationRequired(messages.successfulReconciliationRequired);
      }
    } catch (error) {
      outcome = recordUnknown({
        context,
        effects,
        error,
        errors,
        hooks,
        messages,
        prepared,
      });
    }
    return projectResult({
      lease,
      operation,
      outcome,
      terminalMessage: messages.terminalReconciliationRequired,
    });
  };

  return OBJECT_FREEZE({ execute });
};
