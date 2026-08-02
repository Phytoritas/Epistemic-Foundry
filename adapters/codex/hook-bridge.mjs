// Translate one raw Codex-host event into the canonical hook-event envelope.
//
// The bridge is a translator, not a source.  It adds exactly two things the raw
// event does not carry, and both are read rather than invented: the canonical
// event type, resolved from the verb the payload's own registration passes, and
// the coverage class for that event type, derived from the matchers that
// registration declares.  Everything else is copied through unchanged.
//
// Validation is not re-implemented here.  The request goes to the sealed hook
// gateway, which normalizes it, hashes the raw payload, seals the envelope and
// checks it with `validateHookEventEnvelope`; a refusal there propagates to the
// caller as the gateway's own typed error.  The bridge refuses first only for
// what the gateway cannot know: whether this event belongs to the Codex host
// this adapter binds, and whether its verb is one the payload registers.
//
// The raw shape below is this adapter's declared expectation of what a Codex
// hook process receives, pinned by tests.  It is not transcribed from a host
// specification, because the repository ships none; a host that delivers other
// field names needs this shape re-declared, not the gateway widened.

import {
  dispatchHookEvent,
  validateHookEventEnvelope,
} from "../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import { fail, requireFields } from "./codex-declarations.mjs";

/** The exact minimal record this adapter accepts from the Codex host. */
export const RAW_EVENT_FIELDS = Object.freeze([
  "event_id",
  "hook",
  "host",
  "payload",
  "received_at",
  "session_id",
  "tool_name",
]);

/** The request fields the hook gateway normalizes. */
export const HOOK_REQUEST_FIELDS = Object.freeze([
  "coverage",
  "event_id",
  "event_type",
  "host",
  "raw_payload",
  "received_at",
  "session_id",
  "tool_name",
]);

/**
 * Translate a raw host event into the gateway's request shape.
 *
 * Pure and clock-free: `received_at` is the host's, not this module's.  Field
 * values are passed through untouched, so a value the gateway would refuse is
 * refused by the gateway rather than repaired here.
 */
export const toHookRequest = (binding, rawEvent) => {
  requireFields(rawEvent, RAW_EVENT_FIELDS, "raw event", "RAW_EVENT_UNREADABLE");
  if (rawEvent.host !== binding.adapterHost) {
    fail("RAW_EVENT_HOST_FOREIGN", `the raw event declares a host this adapter does not bind`, {
      adapter_host: binding.adapterHost,
      raw_host: rawEvent.host,
    });
  }
  const eventType = binding.eventTypeByVerb.get(rawEvent.hook);
  if (eventType === undefined) {
    fail("HOOK_VERB_UNREGISTERED", `no registration in the payload passes the verb given`, {
      registered_verbs: [...binding.eventTypeByVerb.keys()].sort(),
      verb: rawEvent.hook,
    });
  }
  return {
    coverage: binding.coverageByEventType.get(eventType),
    event_id: rawEvent.event_id,
    event_type: eventType,
    host: rawEvent.host,
    raw_payload: rawEvent.payload,
    received_at: rawEvent.received_at,
    session_id: rawEvent.session_id,
    tool_name: rawEvent.tool_name,
  };
};

/**
 * Bridge one raw host event through the gateway.
 *
 * The decision function and its timeout belong to the caller; this adapter never
 * decides, never converts a refusal into an allow, and never seals an envelope
 * of its own.  The returned envelope is whatever the gateway sealed.
 */
export const dispatchRawCodexEvent = async (binding, rawEvent, runtime) =>
  dispatchHookEvent(toHookRequest(binding, rawEvent), runtime);

/**
 * Re-check a bridged envelope with the gateway's own validator.
 *
 * Composed, not re-implemented: the refusal a caller sees for a tampered
 * envelope is the gateway's, with the gateway's code.
 */
export const verifyBridgedEnvelope = (envelope) => validateHookEventEnvelope(envelope);
