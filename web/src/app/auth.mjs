/**
 * U02 Foundry Console authentication state, expressed as data.
 *
 * The console cannot authenticate anybody: there is no browser, no transport
 * and no identity provider in this package.  What it owns is the *state
 * machine* a shell is allowed to be in, the transitions it is allowed to make,
 * and the rule that credential material never enters a rendered record.
 *
 * Two consequences are enforced here rather than left to a caller's care:
 *
 *   * a transition the machine does not declare is a refusal, not a silent
 *     no-op, so an "authenticated" state can never be reached by asserting it;
 *   * every record this package emits is walked for credential-shaped field
 *     names before it is returned, so a token cannot ride along inside a view
 *     model, a receipt echo, or an error context.
 *
 * The declared schemes are the two the canonical OpenAPI document declares
 * (`LocalSession`, `BearerAuth`).  Only the *name* of the scheme is state; the
 * credential itself is held by the transport layer this package does not own.
 */

import { types as utilTypes } from "node:util";

import { canonicalJsonSha256, deepFreeze } from "./record-hash.mjs";

export const AUTH_VERSION = "4.0.0-u02.1";

/** Machine codes this module refuses with, each with its standing reason. */
export const AUTH_FINDING_CODES = Object.freeze({
  AUTH_STATE_INVALID:
    "An auth state record was supplied that is not a plain data object carrying exactly the declared fields, so the shell could not tell which state it was actually being asked to render in.",
  AUTH_STATE_UNDECLARED:
    "An auth state name was supplied that is outside the declared UNAUTHENTICATED, AUTHENTICATING, AUTHENTICATED, EXPIRED vocabulary, so no transition table entry governs what may happen next.",
  AUTH_EVENT_UNDECLARED:
    "An auth event name was supplied that the transition table does not declare at all, so accepting it would mean inventing a state change the machine never described.",
  AUTH_TRANSITION_UNDECLARED:
    "The transition table declares no edge from the current auth state for the supplied event, so applying it would move the session into a state the machine never claimed was reachable.",
  AUTH_SCHEME_UNDECLARED:
    "An authentication scheme was named that the canonical OpenAPI document does not declare, so the console would be claiming a credential channel the API never offered.",
  AUTH_SESSION_LABEL_INVALID:
    "A session label was supplied that is not a short non-empty printable string, so it cannot be shown as a workspace or profile indicator without risking control characters in the rendered shell.",
  CREDENTIAL_MATERIAL_PRESENT:
    "A record carried a field whose name is credential-shaped, such as a token, password, secret or authorization field, and this console never renders, echoes, or hashes credential material.",
});

/** A refusal raised by the console auth state machine. */
export class ConsoleAuthError extends Error {
  constructor(code, detail, context = {}) {
    super(`${code}: ${detail}`);
    this.name = "ConsoleAuthError";
    this.code = code;
    this.detail = detail;
    this.reason = AUTH_FINDING_CODES[code];
    this.context = deepFreeze({ ...context });
    Object.freeze(this);
  }
}

const fail = (code, detail, context = {}) => {
  throw new ConsoleAuthError(code, detail, context);
};

/** The four states a console session may be in. */
export const AUTH_STATES = Object.freeze([
  "UNAUTHENTICATED",
  "AUTHENTICATING",
  "AUTHENTICATED",
  "EXPIRED",
]);

/** The events that may be applied to a console session. */
export const AUTH_EVENTS = Object.freeze([
  "BEGIN_AUTHENTICATION",
  "AUTHENTICATION_SUCCEEDED",
  "AUTHENTICATION_FAILED",
  "SESSION_EXPIRED",
  "SIGN_OUT",
]);

/**
 * The whole machine, as data.  Every legal move is a table entry; anything not
 * in the table is a refusal rather than an implicit stay-put.
 */
export const AUTH_TRANSITIONS = deepFreeze({
  UNAUTHENTICATED: { BEGIN_AUTHENTICATION: "AUTHENTICATING" },
  AUTHENTICATING: {
    AUTHENTICATION_SUCCEEDED: "AUTHENTICATED",
    AUTHENTICATION_FAILED: "UNAUTHENTICATED",
  },
  AUTHENTICATED: { SESSION_EXPIRED: "EXPIRED", SIGN_OUT: "UNAUTHENTICATED" },
  EXPIRED: { BEGIN_AUTHENTICATION: "AUTHENTICATING", SIGN_OUT: "UNAUTHENTICATED" },
});

/** The authentication schemes the canonical OpenAPI document declares. */
export const AUTH_SCHEMES = Object.freeze(["LocalSession", "BearerAuth"]);

/** Only this state may render a view that requires authentication. */
export const AUTHORIZED_STATE = "AUTHENTICATED";

const AUTH_STATE_FIELDS = Object.freeze([
  "scheme",
  "session_label",
  "state",
  "transition_count",
]);

/**
 * Field names that carry credential material.  A record whose key set touches
 * any of these is refused rather than redacted, because a redacted credential
 * field still tells a reader the console was willing to carry one.
 *
 * The bare name `auth` is deliberately absent: in this package it names the
 * session *state* record, whose field set is closed to `scheme`,
 * `session_label`, `state` and `transition_count` by `validateAuthState`, so it
 * has no room for material.  Anything credential-shaped nested inside it is
 * still refused by the walk below.
 */
export const CREDENTIAL_FIELD_NAMES = Object.freeze([
  "access_token",
  "api_key",
  "apikey",
  "authorization",
  "bearer",
  "client_secret",
  "cookie",
  "credential",
  "credentials",
  "id_token",
  "passphrase",
  "password",
  "private_key",
  "refresh_token",
  "secret",
  "session_token",
  "set_cookie",
  "token",
  "x_local_session",
]);

const CREDENTIAL_FIELD_SET = new Set(CREDENTIAL_FIELD_NAMES);

const normalizeFieldName = (key) => key.toLowerCase().replaceAll("-", "_");

const isPlainDataObject = (value) =>
  value !== null &&
  typeof value === "object" &&
  !Array.isArray(value) &&
  !utilTypes.isProxy(value) &&
  (Object.getPrototypeOf(value) === Object.prototype ||
    Object.getPrototypeOf(value) === null);

/**
 * Walk a record and refuse if any field name anywhere inside it is
 * credential-shaped.
 *
 * @param {unknown} record
 * @param {string} where
 * @returns {unknown} the same record, when it is clean
 */
export const assertNoCredentialMaterial = (record, where = "record") => {
  const visit = (value, path) => {
    if (Array.isArray(value)) {
      value.forEach((entry, index) => visit(entry, `${path}[${index}]`));
      return;
    }
    if (value === null || typeof value !== "object") return;
    for (const key of Object.keys(value)) {
      const normalized = normalizeFieldName(key);
      if (CREDENTIAL_FIELD_SET.has(normalized)) {
        fail(
          "CREDENTIAL_MATERIAL_PRESENT",
          `${path}.${key} is a credential-shaped field name`,
          { field: key, path, where },
        );
      }
      visit(value[key], `${path}.${key}`);
    }
  };
  visit(record, where);
  return record;
};

const requireSessionLabel = (value) => {
  if (value === null) return null;
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.length > 64 ||
    value.normalize("NFC") !== value ||
    /\p{Cc}/u.test(value)
  ) {
    fail(
      "AUTH_SESSION_LABEL_INVALID",
      "session_label must be null or a printable NFC string of 1..64 characters",
      { session_label_type: typeof value },
    );
  }
  return value;
};

const requireScheme = (value) => {
  if (value === null) return null;
  if (typeof value !== "string" || !AUTH_SCHEMES.includes(value)) {
    fail("AUTH_SCHEME_UNDECLARED", "scheme must be null or a declared security scheme", {
      declared: [...AUTH_SCHEMES],
    });
  }
  return value;
};

/**
 * The state every console session starts in.
 *
 * @returns {Readonly<{scheme: null, session_label: null, state: string, transition_count: number}>}
 */
export const initialAuthState = () =>
  deepFreeze({
    scheme: null,
    session_label: null,
    state: "UNAUTHENTICATED",
    transition_count: 0,
  });

/**
 * Validate an auth state record, whoever built it.
 *
 * @param {unknown} candidate
 * @returns {Readonly<Record<string, unknown>>}
 */
export const validateAuthState = (candidate) => {
  if (!isPlainDataObject(candidate)) {
    fail("AUTH_STATE_INVALID", "auth state must be a plain data object", {
      received: candidate === null ? "null" : typeof candidate,
    });
  }
  assertNoCredentialMaterial(candidate, "auth_state");
  const keys = Object.keys(candidate).sort();
  if (keys.length !== AUTH_STATE_FIELDS.length) {
    fail("AUTH_STATE_INVALID", "auth state carries fields outside the declared set", {
      declared: [...AUTH_STATE_FIELDS],
      received: keys,
    });
  }
  for (const field of AUTH_STATE_FIELDS) {
    if (!Object.hasOwn(candidate, field)) {
      fail("AUTH_STATE_INVALID", `auth state is missing ${field}`, { field });
    }
  }
  const state = candidate.state;
  if (typeof state !== "string" || !AUTH_STATES.includes(state)) {
    fail("AUTH_STATE_UNDECLARED", "state is outside the declared auth vocabulary", {
      declared: [...AUTH_STATES],
    });
  }
  const transitionCount = candidate.transition_count;
  if (!Number.isSafeInteger(transitionCount) || transitionCount < 0) {
    fail("AUTH_STATE_INVALID", "transition_count must be a non-negative safe integer", {
      state,
    });
  }
  const scheme = requireScheme(candidate.scheme);
  const sessionLabel = requireSessionLabel(candidate.session_label);
  if (state === "AUTHENTICATED" && scheme === null) {
    fail("AUTH_STATE_INVALID", "an authenticated session must name the scheme it used", {
      state,
    });
  }
  return deepFreeze({
    scheme,
    session_label: sessionLabel,
    state,
    transition_count: transitionCount,
  });
};

/**
 * Apply one declared event to a validated auth state.
 *
 * @param {unknown} candidate current state
 * @param {string} event declared event name
 * @param {{scheme?: string|null, session_label?: string|null}} [detail]
 * @returns {Readonly<Record<string, unknown>>} the next state
 */
export const applyAuthEvent = (candidate, event, detail = {}) => {
  const current = validateAuthState(candidate);
  if (typeof event !== "string" || !AUTH_EVENTS.includes(event)) {
    fail("AUTH_EVENT_UNDECLARED", "event is outside the declared auth event vocabulary", {
      declared: [...AUTH_EVENTS],
      state: current.state,
    });
  }
  assertNoCredentialMaterial(detail, "auth_event_detail");
  const edges = AUTH_TRANSITIONS[current.state];
  if (!Object.hasOwn(edges, event)) {
    fail(
      "AUTH_TRANSITION_UNDECLARED",
      `no declared transition leaves ${current.state} on ${event}`,
      { declared_events: Object.keys(edges), event, state: current.state },
    );
  }
  const next = edges[event];
  const scheme = Object.hasOwn(detail, "scheme")
    ? requireScheme(detail.scheme)
    : current.scheme;
  const sessionLabel = Object.hasOwn(detail, "session_label")
    ? requireSessionLabel(detail.session_label)
    : current.session_label;
  const carriesIdentity = next === "AUTHENTICATING" || next === "AUTHENTICATED" || next === "EXPIRED";
  return validateAuthState({
    scheme: carriesIdentity ? scheme : null,
    session_label: carriesIdentity ? sessionLabel : null,
    state: next,
    transition_count: current.transition_count + 1,
  });
};

/**
 * Whether a view that requires authentication may be rendered in this state.
 *
 * @param {unknown} candidate
 * @returns {boolean}
 */
export const isAuthorized = (candidate) => validateAuthState(candidate).state === AUTHORIZED_STATE;

/**
 * A hash-re-derivable projection of the auth machine itself, so a review can
 * check that the shell under test used the transition table it claims to.
 *
 * @returns {Readonly<Record<string, unknown>>}
 */
export const authMachineRecord = () => {
  const body = {
    authorized_state: AUTHORIZED_STATE,
    events: [...AUTH_EVENTS],
    kind: "EpistemicFoundryConsoleAuthMachine",
    schemes: [...AUTH_SCHEMES],
    states: [...AUTH_STATES],
    transitions: Object.fromEntries(
      AUTH_STATES.map((state) => [state, { ...AUTH_TRANSITIONS[state] }]),
    ),
    version: AUTH_VERSION,
  };
  assertNoCredentialMaterial(body, "auth_machine_record");
  return deepFreeze({ ...body, record_hash: canonicalJsonSha256(body) });
};
