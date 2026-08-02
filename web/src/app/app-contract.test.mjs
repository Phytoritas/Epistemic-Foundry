/**
 * U02 console shell and auth contract suite.
 *
 * These are the happy-path claims: the shell binds views to declared operations
 * of the generated client, derives mutation from the route table, maps receipts
 * to explicit read model states, gates secured views on the auth state machine,
 * and emits deeply frozen, hash-re-derivable records.  There is no DOM, HTTP or
 * identity provider here; this suite exercises the view-model logic and state
 * only.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  applyAuthEvent,
  authMachineRecord,
  AUTH_SCHEMES,
  AUTH_STATES,
  AUTHORIZED_STATE,
  buildShellNavigation,
  DEFAULT_VIEW_SPECS,
  initialAuthState,
  isAuthorized,
  READ_MODEL_STATES,
  RECEIPT_OUTCOMES,
  rederiveRecordHash,
  renderView,
  SHA256_PATTERN,
  validateAuthState,
} from "./index.mjs";
import * as generatedClient from "../generated/ui-client/index.mjs";
import {
  authenticatedSession,
  degradedReceipt,
  emptyReceipt,
  problemReceipt,
  successReceipt,
  transportFailureReceipt,
  unauthenticatedSession,
} from "./app-test-fixtures.mjs";

const authenticate = () =>
  applyAuthEvent(
    applyAuthEvent(initialAuthState(), "BEGIN_AUTHENTICATION"),
    "AUTHENTICATION_SUCCEEDED",
    { scheme: "LocalSession", session_label: "workspace-alpha" },
  );

test("app_contract: every default view binds a declared operation of the generated client", () => {
  const navigation = buildShellNavigation();
  assert.equal(navigation.views.length, DEFAULT_VIEW_SPECS.length);
  for (const view of navigation.views) {
    assert.equal(generatedClient.OPERATION_IDS.includes(view.operation_id), true);
    assert.equal(typeof generatedClient[view.operation_id], "function");
    assert.equal(view.method, generatedClient.OPERATIONS[view.operation_id].method);
    assert.equal(view.path_template, generatedClient.OPERATIONS[view.operation_id].path);
  }
});

test("app_contract: mutation is derived from the route table, not from the view's claim", () => {
  const navigation = buildShellNavigation();
  for (const view of navigation.views) {
    const method = generatedClient.OPERATIONS[view.operation_id].method;
    assert.equal(view.mutating, method !== "GET");
  }
  const mutating = navigation.mutating_view_ids.sort();
  assert.deepEqual(mutating, ["promotion-request", "run-pause"]);
});

test("app_contract: the navigation record is deeply frozen and hash re-derivable", () => {
  const navigation = buildShellNavigation();
  assert.equal(Object.isFrozen(navigation), true);
  assert.equal(Object.isFrozen(navigation.views), true);
  assert.equal(Object.isFrozen(navigation.views[0]), true);
  assert.match(navigation.record_hash, SHA256_PATTERN);
  assert.equal(navigation.record_hash, rederiveRecordHash(navigation));
});

test("app_contract: building navigation twice is deterministic to the byte", () => {
  const first = buildShellNavigation();
  const second = buildShellNavigation();
  assert.equal(first.record_hash, second.record_hash);
  assert.deepEqual(first, second);
});

test("app_contract: a public view renders without authentication", () => {
  const navigation = buildShellNavigation();
  const record = renderView(navigation, { view_id: "liveness", auth: unauthenticatedSession() });
  assert.equal(record.requires_auth, false);
  assert.equal(record.auth_state, "UNAUTHENTICATED");
  assert.equal(record.data_state, "UNKNOWN");
  assert.equal(record.record_hash, rederiveRecordHash(record));
});

test("app_contract: unauthenticated exposes only the declared public operations", () => {
  const navigation = buildShellNavigation();
  const unauth = unauthenticatedSession();
  const publicIds = [];
  const securedIds = [];
  for (const view of navigation.views) {
    if (view.requires_auth) {
      assert.throws(
        () => renderView(navigation, { view_id: view.view_id, auth: unauth }),
        (error) => error.code === "VIEW_REQUIRES_AUTHENTICATION",
      );
      securedIds.push(view.view_id);
    } else {
      const record = renderView(navigation, { view_id: view.view_id, auth: unauth });
      assert.equal(record.auth_state, "UNAUTHENTICATED");
      publicIds.push(view.view_id);
    }
  }
  // Exactly one public view is declared: unauthenticated liveness.
  assert.deepEqual(publicIds, ["liveness"]);
  assert.equal(securedIds.length, navigation.views.length - 1);
});

test("app_contract: a secured view renders once the session is authenticated", () => {
  const navigation = buildShellNavigation();
  const record = renderView(navigation, {
    view_id: "forge-docket",
    auth: authenticatedSession(),
    receipt: successReceipt(),
  });
  assert.equal(record.requires_auth, true);
  assert.equal(record.auth_state, "AUTHENTICATED");
  assert.equal(record.scheme, "LocalSession");
  assert.equal(record.data_state, "READY");
});

test("app_contract: receipts map to the five distinct read model states", () => {
  const navigation = buildShellNavigation();
  const auth = authenticatedSession();
  const stateOf = (receipt) =>
    renderView(navigation, { view_id: "forge-docket", auth, receipt }).data_state;
  assert.equal(stateOf(successReceipt()), "READY");
  assert.equal(stateOf(emptyReceipt()), "EMPTY_CONFIRMED");
  assert.equal(stateOf(degradedReceipt()), "DEGRADED");
  assert.equal(stateOf(problemReceipt()), "UNAVAILABLE");
  assert.equal(stateOf(transportFailureReceipt()), "UNAVAILABLE");
  const unknown = renderView(navigation, { view_id: "forge-docket", auth });
  assert.equal(unknown.data_state, "UNKNOWN");
});

test("app_contract: EMPTY_CONFIRMED is distinct from UNAVAILABLE", () => {
  const navigation = buildShellNavigation();
  const auth = authenticatedSession();
  const empty = renderView(navigation, { view_id: "forge-docket", auth, receipt: emptyReceipt() });
  const unavailable = renderView(navigation, {
    view_id: "forge-docket",
    auth,
    receipt: problemReceipt(),
  });
  assert.equal(empty.data_state, "EMPTY_CONFIRMED");
  assert.equal(empty.state_is_confirmed_empty, true);
  assert.equal(unavailable.data_state, "UNAVAILABLE");
  assert.equal(unavailable.state_is_confirmed_empty, false);
  assert.notEqual(empty.data_state, unavailable.data_state);
});

test("app_contract: a claimed read model state that matches the receipt is accepted", () => {
  const navigation = buildShellNavigation();
  const record = renderView(navigation, {
    view_id: "forge-docket",
    auth: authenticatedSession(),
    receipt: emptyReceipt(),
    claimed_state: "EMPTY_CONFIRMED",
  });
  assert.equal(record.data_state, "EMPTY_CONFIRMED");
});

test("app_contract: the auth machine advances only along declared transitions", () => {
  const start = initialAuthState();
  assert.equal(start.state, "UNAUTHENTICATED");
  assert.equal(isAuthorized(start), false);
  const authenticating = applyAuthEvent(start, "BEGIN_AUTHENTICATION");
  assert.equal(authenticating.state, "AUTHENTICATING");
  const authenticated = applyAuthEvent(authenticating, "AUTHENTICATION_SUCCEEDED", {
    scheme: "BearerAuth",
    session_label: "workspace-alpha",
  });
  assert.equal(authenticated.state, AUTHORIZED_STATE);
  assert.equal(isAuthorized(authenticated), true);
  assert.equal(authenticated.transition_count, 2);
  const expired = applyAuthEvent(authenticated, "SESSION_EXPIRED");
  assert.equal(expired.state, "EXPIRED");
  assert.equal(isAuthorized(expired), false);
  const signedOut = applyAuthEvent(expired, "SIGN_OUT");
  assert.equal(signedOut.state, "UNAUTHENTICATED");
  assert.equal(signedOut.scheme, null);
});

test("app_contract: the auth machine record enumerates the declared vocabulary and re-derives", () => {
  const record = authMachineRecord();
  assert.deepEqual(record.states, [...AUTH_STATES]);
  assert.deepEqual(record.schemes, [...AUTH_SCHEMES]);
  assert.equal(record.authorized_state, AUTHORIZED_STATE);
  assert.equal(Object.isFrozen(record), true);
  assert.match(record.record_hash, SHA256_PATTERN);
  assert.equal(record.record_hash, rederiveRecordHash(record));
});

test("app_contract: declared read model states and receipt outcomes are the closed vocabularies", () => {
  assert.deepEqual(READ_MODEL_STATES, [
    "READY",
    "EMPTY_CONFIRMED",
    "DEGRADED",
    "UNAVAILABLE",
    "UNKNOWN",
  ]);
  assert.deepEqual(RECEIPT_OUTCOMES, ["SUCCESS", "PROBLEM", "TRANSPORT_FAILURE"]);
});

test("app_contract: validateAuthState freezes and preserves a well-formed state", () => {
  const validated = validateAuthState(authenticatedSession());
  assert.equal(Object.isFrozen(validated), true);
  assert.equal(validated.state, "AUTHENTICATED");
  assert.equal(validated.scheme, "LocalSession");
});
