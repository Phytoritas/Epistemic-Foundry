/**
 * U02 one-shot composition from a liveness observation to an honest health view.
 *
 * The runtime probes liveness once and deliberately supplies no readiness
 * receipt, so process reachability can never become a readiness claim.
 */

import { types as utilTypes } from "node:util";

import { buildHealthView } from "./health-view.mjs";
import {
  ConsoleHealthRuntimeError,
  createHealthRuntimeAdapter,
} from "./health-runtime-adapter.mjs";

const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;

class HealthViewCompositionIntegrityError extends Error {
  constructor(detail) {
    super(`health view runtime composition integrity failure: ${detail}`);
    this.name = "HealthViewCompositionIntegrityError";
  }
}

const failInput = (detail, context = {}) => {
  throw new ConsoleHealthRuntimeError(
    "HEALTH_RUNTIME_INPUT_INVALID",
    detail,
    context,
  );
};

const requireObservationInput = (candidate) => {
  let plain = false;
  try {
    plain =
      candidate !== null &&
      typeof candidate === "object" &&
      !Array.isArray(candidate) &&
      !utilTypes.isProxy(candidate) &&
      (OBJECT_GET_PROTOTYPE_OF(candidate) === Object.prototype ||
        OBJECT_GET_PROTOTYPE_OF(candidate) === null);
  } catch {
    plain = false;
  }
  if (!plain) {
    failInput("liveness view observation input must be a plain data object");
  }

  const keys = Reflect.ownKeys(candidate);
  if (keys.some((key) => typeof key !== "string")) {
    failInput("liveness view observation input may not contain symbol fields");
  }
  const allowed = ["auth", "signal"];
  const unknown = keys.filter((key) => !allowed.includes(key));
  const missing = OBJECT_HAS_OWN(candidate, "auth") ? [] : ["auth"];
  const accessors = keys.filter((key) => {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(candidate, key);
    return descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value");
  });
  if (unknown.length > 0 || missing.length > 0 || accessors.length > 0) {
    failInput("liveness view observation input does not match its closed field set", {
      accessors,
      allowed,
      missing,
      unknown,
    });
  }
  return candidate;
};

const readDataField = (candidate, key) => {
  const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(candidate, key);
  if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
    failInput(`liveness view observation input.${key} must be an own data field`);
  }
  return descriptor.value;
};

const requireComposition = (condition, detail) => {
  if (!condition) {
    throw new HealthViewCompositionIntegrityError(detail);
  }
};

const requireLivenessViewPostconditions = (view, livenessReceipt) => {
  requireComposition(
    view !== null && typeof view === "object" && !Array.isArray(view),
    "the view owner returned a non-record",
  );

  const expectedState =
    livenessReceipt.outcome === "SUCCESS" ? "LIVE" : "UNAVAILABLE";
  const processLiveness = Array.isArray(view.sections)
    ? view.sections.find((candidate) => candidate?.id === "process-liveness")
    : undefined;

  requireComposition(
    view.kind === "EpistemicFoundryConsoleHealthView",
    "the view kind is not the canonical health view kind",
  );
  requireComposition(
    view.liveness?.body_hash === livenessReceipt.body_hash &&
      view.liveness?.outcome === livenessReceipt.outcome &&
      view.liveness?.status === livenessReceipt.status,
    "the liveness projection is not bound to the observed receipt",
  );
  requireComposition(
    view.liveness?.state === expectedState,
    "the rendered liveness state does not match the receipt outcome",
  );
  requireComposition(
    view.overall === "UNKNOWN" &&
      view.data_state === "UNKNOWN" &&
      view.overall_is_declared_by_api === false,
    "liveness was promoted into a readiness or overall claim",
  );
  requireComposition(
    view.readiness?.body_hash === null &&
      view.readiness?.outcome === null &&
      view.readiness?.report_hash === null &&
      view.readiness?.status === null,
    "the liveness-only view contains a readiness observation",
  );
  requireComposition(
    view.profile === null &&
      Array.isArray(view.checks) &&
      view.checks.length === 0 &&
      Array.isArray(view.degraded_checks) &&
      view.degraded_checks.length === 0,
    "the liveness-only view contains readiness-derived data",
  );
  requireComposition(
    processLiveness?.state === view.liveness.state,
    "the process-liveness section disagrees with the liveness projection",
  );
};

export const createHealthViewRuntime = (options = {}) => {
  const adapter = createHealthRuntimeAdapter(options);

  const observeLivenessView = async (input = {}) => {
    const candidate = requireObservationInput(input);
    const auth = readDataField(candidate, "auth");
    const signal = OBJECT_HAS_OWN(candidate, "signal")
      ? readDataField(candidate, "signal")
      : undefined;
    const livenessReceipt = await adapter.probeLiveness({ signal });
    const view = buildHealthView({
      auth,
      liveness_receipt: livenessReceipt,
    });
    requireLivenessViewPostconditions(view, livenessReceipt);
    return view;
  };

  return OBJECT_FREEZE({ observeLivenessView });
};
