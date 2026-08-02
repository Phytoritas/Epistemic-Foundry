import assert from "node:assert/strict";
import test from "node:test";

import * as uiClient from "../generated/ui-client/index.mjs";
import {
  applyAuthEvent,
  AUTH_STATES,
  ConsoleAuthError,
  initialAuthState,
  validateAuthState,
} from "./auth.mjs";
import { buildShellNavigation, ConsoleShellError, renderView } from "./shell.mjs";
import { buildHealthView, ConsoleHealthError } from "../features/health/index.mjs";
import {
  authenticatedSession,
  degradedHealthReport,
  healthCheck,
  healthReport,
  livenessReceipt,
  readinessProblemReceipt,
  readinessReceipt,
} from "../features/health/health-test-fixtures.mjs";

const shellCode = (code) => (error) =>
  error instanceof ConsoleShellError && error.code === code && error.reason.length > 50;
const authCode = (code) => (error) =>
  error instanceof ConsoleAuthError && error.code === code && error.reason.length > 50;
const healthCode = (code) => (error) =>
  error instanceof ConsoleHealthError && error.code === code && error.reason.length > 50;

const spec = (overrides = {}) => ({
  declares_mutation: false,
  operation_id: "listRuns",
  requires_auth: true,
  title: "Forge docket",
  view_id: "forge-docket",
  ...overrides,
});

const receipt = (overrides = {}) => ({
  body_hash: `sha256:${"c".repeat(64)}`,
  degraded_reasons: [],
  item_count: 1,
  operation_id: "listRuns",
  outcome: "SUCCESS",
  status: "200",
  ...overrides,
});

test("shell_adversarial: a view binding an operation the client never exported refuses", () => {
  assert.throws(
    () => buildShellNavigation([spec({ operation_id: "deleteEverything" })]),
    shellCode("VIEW_OPERATION_UNKNOWN"),
  );
  assert.throws(
    () => buildShellNavigation([spec({ operation_id: "OPERATIONS" })]),
    shellCode("VIEW_OPERATION_UNKNOWN"),
  );
  assert.throws(
    () => buildShellNavigation([spec({ operation_id: "toString" })]),
    shellCode("VIEW_OPERATION_UNKNOWN"),
  );
});

test("shell_adversarial: a write cannot be presented as a read, or a read as a write", () => {
  assert.throws(
    () =>
      buildShellNavigation([
        spec({ operation_id: "cancelRun", title: "Cancel run", view_id: "run-cancel" }),
      ]),
    shellCode("VIEW_MUTATION_UNDECLARED"),
  );
  assert.throws(
    () => buildShellNavigation([spec({ declares_mutation: true })]),
    shellCode("VIEW_MUTATION_OVERDECLARED"),
  );
});

test("shell_adversarial: duplicate view identifiers and malformed specs refuse", () => {
  assert.throws(
    () => buildShellNavigation([spec(), spec({ operation_id: "getRun" })]),
    shellCode("VIEW_ID_DUPLICATE"),
  );
  assert.throws(() => buildShellNavigation([{ ...spec(), extra: 1 }]), shellCode("VIEW_SPEC_INVALID"));
  assert.throws(() => buildShellNavigation([spec({ requires_auth: "yes" })]), shellCode("VIEW_SPEC_INVALID"));
  assert.throws(() => buildShellNavigation([]), shellCode("VIEW_SPEC_INVALID"));
  assert.throws(
    () => buildShellNavigation(new Proxy([spec()], {})),
    shellCode("VIEW_SPEC_INVALID"),
  );
});

test("shell_adversarial: a client that is not the generated surface refuses", () => {
  assert.throws(() => buildShellNavigation(undefined, {}), shellCode("CLIENT_SURFACE_INVALID"));
  assert.throws(
    () =>
      buildShellNavigation(undefined, {
        ...uiClient,
        SOURCE_DOCUMENT: { ...uiClient.SOURCE_DOCUMENT, sha256: "not-a-hash" },
      }),
    shellCode("CLIENT_SURFACE_INVALID"),
  );
  const unbound = { ...uiClient };
  delete unbound.listRuns;
  assert.throws(() => buildShellNavigation(undefined, unbound), shellCode("CLIENT_OPERATION_UNBOUND"));
  const missing = {
    BASE_PATH: "/api/v1",
    OPERATION_IDS: ["ghostOperation"],
    OPERATIONS: {},
    SOURCE_DOCUMENT: { ...uiClient.SOURCE_DOCUMENT },
  };
  assert.throws(() => buildShellNavigation(undefined, missing), shellCode("CLIENT_SURFACE_INVALID"));
});

test("shell_adversarial: an unauthenticated session refuses instead of rendering empty", () => {
  const navigation = buildShellNavigation();
  for (const state of AUTH_STATES.filter((entry) => entry !== "AUTHENTICATED")) {
    const auth = {
      scheme: state === "UNAUTHENTICATED" ? null : "LocalSession",
      session_label: null,
      state,
      transition_count: 1,
    };
    assert.throws(
      () => renderView(navigation, { auth, view_id: "forge-docket" }),
      shellCode("VIEW_REQUIRES_AUTHENTICATION"),
      `${state} must refuse`,
    );
    assert.throws(
      () => renderView(navigation, { auth, receipt: receipt({ item_count: 0 }), view_id: "forge-docket" }),
      shellCode("VIEW_REQUIRES_AUTHENTICATION"),
      `${state} must refuse even with an empty page of results`,
    );
  }
  const open = renderView(navigation, { auth: initialAuthState(), view_id: "liveness" });
  assert.equal(open.requires_auth, false);
  assert.equal(open.data_state, "UNKNOWN");
});

test("shell_adversarial: an unregistered view identifier refuses", () => {
  const navigation = buildShellNavigation();
  assert.throws(
    () => renderView(navigation, { auth: authenticatedSession(), view_id: "constructor" }),
    shellCode("VIEW_UNKNOWN"),
  );
  assert.throws(
    () => renderView(navigation, { auth: authenticatedSession(), view_id: "atlas" }),
    shellCode("VIEW_UNKNOWN"),
  );
});

test("shell_adversarial: undeclared auth transitions and events refuse", () => {
  const start = initialAuthState();
  assert.throws(() => applyAuthEvent(start, "AUTHENTICATION_SUCCEEDED"), authCode("AUTH_TRANSITION_UNDECLARED"));
  assert.throws(() => applyAuthEvent(start, "SESSION_EXPIRED"), authCode("AUTH_TRANSITION_UNDECLARED"));
  assert.throws(() => applyAuthEvent(start, "ELEVATE"), authCode("AUTH_EVENT_UNDECLARED"));
  const authenticated = authenticatedSession();
  assert.throws(
    () => applyAuthEvent(authenticated, "AUTHENTICATION_SUCCEEDED"),
    authCode("AUTH_TRANSITION_UNDECLARED"),
  );
});

test("shell_adversarial: an authenticated state cannot simply be asserted", () => {
  assert.throws(
    () =>
      validateAuthState({
        scheme: null,
        session_label: null,
        state: "AUTHENTICATED",
        transition_count: 0,
      }),
    authCode("AUTH_STATE_INVALID"),
  );
  assert.throws(
    () =>
      validateAuthState({
        scheme: "LocalSession",
        session_label: null,
        state: "SUPERUSER",
        transition_count: 1,
      }),
    authCode("AUTH_STATE_UNDECLARED"),
  );
  assert.throws(
    () =>
      validateAuthState({
        scheme: "GodMode",
        session_label: null,
        state: "AUTHENTICATED",
        transition_count: 1,
      }),
    authCode("AUTH_SCHEME_UNDECLARED"),
  );
  assert.throws(
    () => validateAuthState(new Proxy(authenticatedSession(), {})),
    authCode("AUTH_STATE_INVALID"),
  );
});

test("shell_adversarial: credential material is refused wherever it appears", () => {
  assert.throws(
    () =>
      validateAuthState({
        scheme: "BearerAuth",
        session_label: "s",
        state: "AUTHENTICATED",
        token: "abc",
        transition_count: 1,
      }),
    authCode("CREDENTIAL_MATERIAL_PRESENT"),
  );
  assert.throws(
    () => applyAuthEvent(initialAuthState(), "BEGIN_AUTHENTICATION", { password: "hunter2" }),
    authCode("CREDENTIAL_MATERIAL_PRESENT"),
  );
  const navigation = buildShellNavigation();
  assert.throws(
    () =>
      renderView(navigation, {
        auth: authenticatedSession(),
        receipt: { ...receipt(), authorization: "Bearer x" },
        view_id: "forge-docket",
      }),
    authCode("CREDENTIAL_MATERIAL_PRESENT"),
  );
  assert.throws(
    () =>
      buildHealthView({
        auth: authenticatedSession(),
        readiness_receipt: readinessReceipt(
          healthReport({ checks: [healthCheck({ status: "PASS" })], secret: "x" }),
        ),
      }),
    authCode("CREDENTIAL_MATERIAL_PRESENT"),
  );
  assert.throws(
    () =>
      buildHealthView({
        auth: authenticatedSession(),
        readiness_receipt: { ...readinessReceipt(), "X-Local-Session": "abc" },
      }),
    authCode("CREDENTIAL_MATERIAL_PRESENT"),
  );
});

test("shell_adversarial: a backend failure can never be claimed as confirmed empty", () => {
  const navigation = buildShellNavigation();
  const auth = authenticatedSession();
  assert.throws(
    () =>
      renderView(navigation, {
        auth,
        claimed_state: "EMPTY_CONFIRMED",
        receipt: receipt({ body_hash: null, item_count: null, outcome: "PROBLEM", status: "503" }),
        view_id: "forge-docket",
      }),
    shellCode("BACKEND_FAILURE_AS_EMPTY"),
  );
  assert.throws(
    () =>
      renderView(navigation, {
        auth,
        claimed_state: "EMPTY_CONFIRMED",
        view_id: "forge-docket",
      }),
    shellCode("BACKEND_FAILURE_AS_EMPTY"),
  );
  assert.throws(
    () => renderView(navigation, { auth, claimed_state: "READY", view_id: "forge-docket" }),
    shellCode("READ_MODEL_STATE_OVERCLAIMED"),
  );
});

test("shell_adversarial: receipts that do not match the bound operation refuse", () => {
  const navigation = buildShellNavigation();
  const auth = authenticatedSession();
  assert.throws(
    () =>
      renderView(navigation, {
        auth,
        receipt: receipt({ operation_id: "getRun" }),
        view_id: "forge-docket",
      }),
    shellCode("RECEIPT_OPERATION_MISMATCH"),
  );
  assert.throws(
    () => renderView(navigation, { auth, receipt: receipt({ status: "202" }), view_id: "forge-docket" }),
    shellCode("RECEIPT_STATUS_UNDECLARED"),
  );
  assert.throws(
    () => renderView(navigation, { auth, receipt: receipt({ outcome: "OK" }), view_id: "forge-docket" }),
    shellCode("RECEIPT_OUTCOME_UNDECLARED"),
  );
  assert.throws(
    () =>
      renderView(navigation, {
        auth,
        receipt: receipt({ outcome: "TRANSPORT_FAILURE" }),
        view_id: "forge-docket",
      }),
    shellCode("RECEIPT_STATUS_UNDECLARED"),
  );
  assert.throws(
    () => renderView(navigation, { auth, receipt: receipt({ body_hash: null }), view_id: "forge-docket" }),
    shellCode("RECEIPT_INVALID"),
  );
  assert.throws(
    () => renderView(navigation, { auth, receipt: receipt({ item_count: -1 }), view_id: "forge-docket" }),
    shellCode("RECEIPT_INVALID"),
  );
  assert.throws(
    () => renderView(navigation, { auth, receipt: new Proxy(receipt(), {}), view_id: "forge-docket" }),
    shellCode("RECEIPT_INVALID"),
  );
});

test("shell_adversarial: health cannot be claimed without a readiness receipt", () => {
  const auth = authenticatedSession();
  assert.throws(
    () => buildHealthView({ auth, claimed_overall: "PASS" }),
    healthCode("HEALTH_OVERCLAIMED"),
  );
  assert.throws(
    () => buildHealthView({ auth, claimed_overall: "PASS", liveness_receipt: livenessReceipt() }),
    healthCode("HEALTH_OVERCLAIMED"),
  );
  assert.throws(
    () =>
      buildHealthView({
        auth,
        claimed_overall: "PASS",
        readiness_receipt: readinessProblemReceipt(),
      }),
    healthCode("HEALTH_OVERCLAIMED"),
  );
  assert.throws(
    () =>
      buildHealthView({
        auth,
        claimed_overall: "PASS",
        readiness_receipt: readinessReceipt(degradedHealthReport()),
      }),
    healthCode("HEALTH_OVERCLAIMED"),
  );
});

test("shell_adversarial: a report cannot pass overall while carrying a non passing check", () => {
  const auth = authenticatedSession();
  for (const status of ["WARN", "FAIL", "NOT_RUN"]) {
    assert.throws(
      () =>
        buildHealthView({
          auth,
          readiness_receipt: readinessReceipt(
            healthReport({
              checks: [healthCheck(), healthCheck({ check_id: "lane.b", status })],
            }),
          ),
        }),
      healthCode("HEALTH_DEGRADATION_HIDDEN"),
      `overall PASS with a ${status} check must refuse`,
    );
  }
});

test("shell_adversarial: undeclared health vocabulary and malformed reports refuse", () => {
  const auth = authenticatedSession();
  const build = (report) => () =>
    buildHealthView({ auth, readiness_receipt: readinessReceipt(report) });
  assert.throws(build(healthReport({ overall: "HEALTHY" })), healthCode("HEALTH_STATE_UNDECLARED"));
  assert.throws(build(healthReport({ profile: "ENTERPRISE" })), healthCode("HEALTH_PROFILE_UNDECLARED"));
  assert.throws(
    build(healthReport({ checks: [healthCheck({ status: "OK" })], overall: "DEGRADED" })),
    healthCode("HEALTH_CHECK_STATUS_UNDECLARED"),
  );
  assert.throws(build(healthReport({ checks: [] })), healthCode("HEALTH_REPORT_INVALID"));
  assert.throws(build(healthReport({ report_hash: "sha256:zz" })), healthCode("HEALTH_REPORT_INVALID"));
  assert.throws(build({ ...healthReport(), extra_field: 1 }), healthCode("HEALTH_REPORT_INVALID"));
  assert.throws(
    () =>
      buildHealthView({
        auth,
        liveness_receipt: livenessReceipt({ body: { status: "probably" } }),
      }),
    healthCode("HEALTH_LIVENESS_INVALID"),
  );
  assert.throws(
    () => buildHealthView({ auth, readiness_receipt: readinessReceipt(), unknown_field: 1 }),
    healthCode("HEALTH_INPUT_INVALID"),
  );
  assert.throws(
    () =>
      buildHealthView({
        auth,
        readiness_receipt: { ...readinessReceipt(), operation_id: "getCapabilities" },
      }),
    healthCode("HEALTH_OPERATION_MISMATCH"),
  );
});

test("shell_adversarial: readiness is refused outright without an authenticated session", () => {
  assert.throws(
    () => buildHealthView({ auth: initialAuthState(), readiness_receipt: readinessReceipt() }),
    healthCode("HEALTH_REQUIRES_AUTHENTICATION"),
  );
  const liveOnly = buildHealthView({
    auth: initialAuthState(),
    liveness_receipt: livenessReceipt(),
  });
  assert.equal(liveOnly.liveness.state, "LIVE");
  assert.equal(liveOnly.overall, "UNKNOWN");
});
