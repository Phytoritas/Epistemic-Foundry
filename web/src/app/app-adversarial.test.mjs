/**
 * U02 console shell and auth adversarial suite.
 *
 * Every refusal path is a typed error carrying a machine code, a frozen context
 * and a standing reason.  This suite drives each declared refusal and checks
 * that the shell fails closed rather than inventing a route, presenting a write
 * as a read, rendering a backend failure as a confirmed absence, reaching an
 * undeclared auth state, or letting credential-shaped material into a record.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  applyAuthEvent,
  assertNoCredentialMaterial,
  AUTH_FINDING_CODES,
  buildShellNavigation,
  ConsoleAuthError,
  ConsoleShellError,
  DEFAULT_VIEW_SPECS,
  initialAuthState,
  renderView,
  SHELL_FINDING_CODES,
  validateAuthState,
} from "./index.mjs";
import {
  authenticatedSession,
  emptyReceipt,
  problemReceipt,
  successReceipt,
  unauthenticatedSession,
  viewSpec,
} from "./app-test-fixtures.mjs";

const shellCode = (code) => (error) =>
  error instanceof ConsoleShellError && error.code === code;
const authCode = (code) => (error) =>
  error instanceof ConsoleAuthError && error.code === code;

test("app_adversarial: a view binding an operation the client does not export refuses", () => {
  assert.throws(
    () => buildShellNavigation([viewSpec({ operation_id: "notAnOperation" })]),
    shellCode("VIEW_OPERATION_UNKNOWN"),
  );
});

test("app_adversarial: a write operation not declared as a mutation refuses", () => {
  assert.throws(
    () =>
      buildShellNavigation([
        viewSpec({
          operation_id: "pauseRun",
          declares_mutation: false,
          view_id: "run-pause",
          title: "Pause run",
        }),
      ]),
    shellCode("VIEW_MUTATION_UNDECLARED"),
  );
});

test("app_adversarial: a read operation declared as a mutation refuses", () => {
  assert.throws(
    () => buildShellNavigation([viewSpec({ operation_id: "listRuns", declares_mutation: true })]),
    shellCode("VIEW_MUTATION_OVERDECLARED"),
  );
});

test("app_adversarial: two views claiming the same id refuse", () => {
  assert.throws(
    () =>
      buildShellNavigation([
        viewSpec({ operation_id: "getLiveness", requires_auth: false }),
        viewSpec({ operation_id: "getReadiness" }),
      ]),
    shellCode("VIEW_ID_DUPLICATE"),
  );
});

test("app_adversarial: an unknown or malformed view spec refuses without invention", () => {
  assert.throws(() => buildShellNavigation([{ operation_id: "listRuns" }]), shellCode("VIEW_SPEC_INVALID"));
  assert.throws(() => buildShellNavigation([]), shellCode("VIEW_SPEC_INVALID"));
});

test("app_adversarial: a secured view refuses in every non-authenticated state", () => {
  const navigation = buildShellNavigation();
  for (const auth of [unauthenticatedSession(), applyAuthEvent(initialAuthState(), "BEGIN_AUTHENTICATION")]) {
    // node:assert `throws` returns undefined; inspect the thrown error through
    // a validator so the frozen context and standing reason are still checked.
    assert.throws(
      () => renderView(navigation, { view_id: "health", auth }),
      (error) =>
        error instanceof ConsoleShellError &&
        error.code === "VIEW_REQUIRES_AUTHENTICATION" &&
        error.context.view_id === "health" &&
        Object.isFrozen(error.context) === true &&
        typeof error.reason === "string",
    );
  }
});

test("app_adversarial: an expired session is not authorized for a secured view", () => {
  const navigation = buildShellNavigation();
  const authenticated = applyAuthEvent(
    applyAuthEvent(initialAuthState(), "BEGIN_AUTHENTICATION"),
    "AUTHENTICATION_SUCCEEDED",
    { scheme: "LocalSession", session_label: "workspace-alpha" },
  );
  const expired = applyAuthEvent(authenticated, "SESSION_EXPIRED");
  assert.throws(
    () => renderView(navigation, { view_id: "health", auth: expired }),
    shellCode("VIEW_REQUIRES_AUTHENTICATION"),
  );
});

test("app_adversarial: a rendered-empty claim on a backend failure refuses", () => {
  const navigation = buildShellNavigation();
  assert.throws(
    () =>
      renderView(navigation, {
        view_id: "forge-docket",
        auth: authenticatedSession(),
        receipt: problemReceipt(),
        claimed_state: "EMPTY_CONFIRMED",
      }),
    shellCode("BACKEND_FAILURE_AS_EMPTY"),
  );
});

test("app_adversarial: a read model state claim that outruns the receipt refuses", () => {
  const navigation = buildShellNavigation();
  assert.throws(
    () =>
      renderView(navigation, {
        view_id: "forge-docket",
        auth: authenticatedSession(),
        receipt: successReceipt(),
        claimed_state: "DEGRADED",
      }),
    shellCode("READ_MODEL_STATE_OVERCLAIMED"),
  );
});

test("app_adversarial: a receipt naming another operation refuses", () => {
  const navigation = buildShellNavigation();
  assert.throws(
    () =>
      renderView(navigation, {
        view_id: "forge-docket",
        auth: authenticatedSession(),
        receipt: emptyReceipt({ operation_id: "getReadiness" }),
      }),
    shellCode("RECEIPT_OPERATION_MISMATCH"),
  );
});

test("app_adversarial: rendering an unregistered view id refuses", () => {
  const navigation = buildShellNavigation();
  assert.throws(
    () => renderView(navigation, { view_id: "no-such-view", auth: authenticatedSession() }),
    shellCode("VIEW_UNKNOWN"),
  );
});

test("app_adversarial: an incomplete client surface refuses", () => {
  const brokenClient = { OPERATION_IDS: [], OPERATIONS: {}, SOURCE_DOCUMENT: {}, BASE_PATH: "/api/v1" };
  assert.throws(
    () => buildShellNavigation(DEFAULT_VIEW_SPECS, brokenClient),
    shellCode("CLIENT_SURFACE_INVALID"),
  );
});

test("app_adversarial: credential-shaped material in a view spec refuses", () => {
  const hostile = { ...viewSpec(), token: "should-never-be-carried" };
  assert.throws(() => buildShellNavigation([hostile]), shellCode("CREDENTIAL_MATERIAL_PRESENT"));
});

test("app_adversarial: credential-shaped field names are refused wherever they appear", () => {
  assert.throws(
    () => assertNoCredentialMaterial({ outer: { authorization: "x" } }, "probe"),
    authCode("CREDENTIAL_MATERIAL_PRESENT"),
  );
  assert.throws(
    () => assertNoCredentialMaterial({ items: [{ Set_Cookie: "x" }] }, "probe"),
    authCode("CREDENTIAL_MATERIAL_PRESENT"),
  );
  // A clean record passes through unchanged.
  const clean = { state: "AUTHENTICATED" };
  assert.equal(assertNoCredentialMaterial(clean, "probe"), clean);
});

test("app_adversarial: an undeclared auth transition refuses instead of staying put", () => {
  const start = initialAuthState();
  assert.throws(() => applyAuthEvent(start, "SESSION_EXPIRED"), authCode("AUTH_TRANSITION_UNDECLARED"));
  assert.throws(() => applyAuthEvent(start, "NOT_AN_EVENT"), authCode("AUTH_EVENT_UNDECLARED"));
});

test("app_adversarial: an undeclared auth state or scheme refuses", () => {
  assert.throws(
    () => validateAuthState({ scheme: null, session_label: null, state: "SUPERUSER", transition_count: 0 }),
    authCode("AUTH_STATE_UNDECLARED"),
  );
  assert.throws(
    () =>
      validateAuthState({
        scheme: "OAuthDevice",
        session_label: null,
        state: "AUTHENTICATED",
        transition_count: 1,
      }),
    authCode("AUTH_SCHEME_UNDECLARED"),
  );
});

test("app_adversarial: an authenticated state without a named scheme refuses", () => {
  assert.throws(
    () =>
      validateAuthState({
        scheme: null,
        session_label: "workspace-alpha",
        state: "AUTHENTICATED",
        transition_count: 2,
      }),
    authCode("AUTH_STATE_INVALID"),
  );
});

test("app_adversarial: every finding code is a short machine code with a standing reason", () => {
  for (const codes of [SHELL_FINDING_CODES, AUTH_FINDING_CODES]) {
    for (const [code, reason] of Object.entries(codes)) {
      assert.equal(code.length <= 50, true, `${code} exceeds 50 characters`);
      assert.match(code, /^[A-Z][A-Z0-9_]+$/u);
      assert.equal(typeof reason, "string");
      assert.equal(reason.length > 0, true);
    }
  }
});
