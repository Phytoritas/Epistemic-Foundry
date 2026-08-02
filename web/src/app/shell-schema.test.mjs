import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  AUTH_EVENTS,
  AUTH_FINDING_CODES,
  AUTH_SCHEMES,
  AUTH_STATES,
  AUTH_TRANSITIONS,
  AUTHORIZED_STATE,
  authMachineRecord,
  CREDENTIAL_FIELD_NAMES,
  initialAuthState,
} from "./auth.mjs";
import {
  buildShellNavigation,
  DEFAULT_VIEW_SPECS,
  READ_MODEL_STATES,
  RECEIPT_OUTCOMES,
  renderView,
  SHELL_FINDING_CODES,
  SHELL_SECURITY_POLICY,
} from "./shell.mjs";
import {
  buildHealthView,
  HEALTH_CHECK_STATUSES,
  HEALTH_FINDING_CODES,
  HEALTH_OVERALL_STATES,
  HEALTH_PROFILES,
  HEALTH_RENDER_STATES,
  unknownHealthView,
} from "../features/health/index.mjs";
import {
  authenticatedSession,
  livenessReceipt,
  readinessReceipt,
} from "../features/health/health-test-fixtures.mjs";

const APP_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(APP_DIR, "../../..");

const PRODUCT_MODULES = [
  "web/src/app/auth.mjs",
  "web/src/app/index.mjs",
  "web/src/app/record-hash.mjs",
  "web/src/app/shell.mjs",
  "web/src/features/health/health-view.mjs",
  "web/src/features/health/index.mjs",
];

const authenticated = () => authenticatedSession();

test("shell_schema: every finding code states a reason long enough to stand alone", () => {
  const tables = [
    ["shell", SHELL_FINDING_CODES],
    ["auth", AUTH_FINDING_CODES],
    ["health", HEALTH_FINDING_CODES],
  ];
  const seen = new Set();
  for (const [table, codes] of tables) {
    assert.equal(Object.isFrozen(codes), true, `${table} finding codes must be frozen`);
    for (const [code, reason] of Object.entries(codes)) {
      assert.equal(/^[A-Z][A-Z0-9_]*$/u.test(code), true, `${table}.${code} must be a machine code`);
      assert.ok(reason.length > 50, `${table}.${code} reason is ${reason.length} characters`);
      assert.equal(seen.has(code), false, `${code} is declared in two tables`);
      seen.add(code);
    }
  }
  assert.ok(seen.size >= 25);
});

test("shell_schema: the read model vocabulary is frozen, complete and distinct", () => {
  assert.equal(Object.isFrozen(READ_MODEL_STATES), true);
  assert.deepEqual([...READ_MODEL_STATES], [
    "READY",
    "EMPTY_CONFIRMED",
    "DEGRADED",
    "UNAVAILABLE",
    "UNKNOWN",
  ]);
  assert.equal(new Set(READ_MODEL_STATES).size, READ_MODEL_STATES.length);
  assert.equal(Object.isFrozen(RECEIPT_OUTCOMES), true);
  assert.deepEqual([...RECEIPT_OUTCOMES], ["SUCCESS", "PROBLEM", "TRANSPORT_FAILURE"]);
});

test("shell_schema: the auth machine is data and references only declared names", () => {
  assert.equal(Object.isFrozen(AUTH_STATES), true);
  assert.equal(Object.isFrozen(AUTH_EVENTS), true);
  assert.equal(Object.isFrozen(AUTH_TRANSITIONS), true);
  assert.deepEqual(Object.keys(AUTH_TRANSITIONS).sort(), [...AUTH_STATES].sort());
  for (const [state, edges] of Object.entries(AUTH_TRANSITIONS)) {
    assert.equal(Object.isFrozen(edges), true, `${state} edges must be frozen`);
    for (const [event, next] of Object.entries(edges)) {
      assert.ok(AUTH_EVENTS.includes(event), `${state} declares undeclared event ${event}`);
      assert.ok(AUTH_STATES.includes(next), `${state} moves to undeclared state ${next}`);
    }
  }
  assert.equal(AUTHORIZED_STATE, "AUTHENTICATED");
  assert.deepEqual(initialAuthState(), {
    scheme: null,
    session_label: null,
    state: "UNAUTHENTICATED",
    transition_count: 0,
  });
});

test("shell_schema: the credential field vocabulary is frozen, sorted and lowercase", () => {
  assert.equal(Object.isFrozen(CREDENTIAL_FIELD_NAMES), true);
  assert.deepEqual([...CREDENTIAL_FIELD_NAMES], [...CREDENTIAL_FIELD_NAMES].sort());
  for (const name of CREDENTIAL_FIELD_NAMES) {
    assert.equal(name, name.toLowerCase());
  }
  for (const required of ["token", "password", "secret", "authorization", "api_key"]) {
    assert.ok(CREDENTIAL_FIELD_NAMES.includes(required), `${required} must be refused`);
  }
});

test("shell_schema: default view specifications carry exactly the declared fields", () => {
  assert.equal(Object.isFrozen(DEFAULT_VIEW_SPECS), true);
  const ids = DEFAULT_VIEW_SPECS.map((spec) => spec.view_id);
  assert.equal(new Set(ids).size, ids.length);
  for (const spec of DEFAULT_VIEW_SPECS) {
    assert.deepEqual(Object.keys(spec).sort(), [
      "declares_mutation",
      "operation_id",
      "requires_auth",
      "title",
      "view_id",
    ]);
    assert.equal(typeof spec.declares_mutation, "boolean");
    assert.equal(typeof spec.requires_auth, "boolean");
  }
});

test("shell_schema: the navigation record is deep frozen and shaped as declared", () => {
  const navigation = buildShellNavigation();
  assert.equal(Object.isFrozen(navigation), true);
  assert.equal(Object.isFrozen(navigation.views), true);
  assert.equal(Object.isFrozen(navigation.views[0]), true);
  assert.deepEqual(Object.keys(navigation).sort(), [
    "base_path",
    "kind",
    "mutating_view_ids",
    "read_model_states",
    "record_hash",
    "security_policy",
    "source_document",
    "version",
    "view_ids",
    "views",
  ]);
  assert.deepEqual(Object.keys(navigation.views[0]).sort(), [
    "method",
    "mutating",
    "operation_id",
    "path_parameters",
    "path_template",
    "requires_auth",
    "response_schema_ref",
    "success_status",
    "title",
    "view_id",
  ]);
  assert.throws(() => {
    navigation.views.push({});
  }, TypeError);
});

test("shell_schema: a rendered view record is deep frozen and shaped as declared", () => {
  const navigation = buildShellNavigation();
  const record = renderView(navigation, { auth: authenticated(), view_id: "forge-docket" });
  assert.equal(Object.isFrozen(record), true);
  assert.deepEqual(Object.keys(record).sort(), [
    "auth_state",
    "data_state",
    "degraded_reasons",
    "item_count",
    "kind",
    "method",
    "mutating",
    "navigation_hash",
    "operation_id",
    "path_template",
    "receipt_body_hash",
    "receipt_outcome",
    "receipt_status",
    "record_hash",
    "requires_auth",
    "scheme",
    "session_label",
    "state_is_confirmed_empty",
    "title",
    "version",
    "view_id",
  ]);
  assert.ok(READ_MODEL_STATES.includes(record.data_state));
});

test("shell_schema: the health vocabularies are frozen and the unknown state is local", () => {
  assert.equal(Object.isFrozen(HEALTH_OVERALL_STATES), true);
  assert.deepEqual([...HEALTH_OVERALL_STATES], ["PASS", "DEGRADED", "FAIL", "SAFE_MODE"]);
  assert.deepEqual([...HEALTH_CHECK_STATUSES], ["PASS", "WARN", "FAIL", "NOT_RUN"]);
  assert.deepEqual([...HEALTH_PROFILES], ["LITE", "RESEARCH", "TEAM", "REGULATED"]);
  assert.deepEqual([...HEALTH_RENDER_STATES], ["UNKNOWN", ...HEALTH_OVERALL_STATES]);
  assert.equal(HEALTH_OVERALL_STATES.includes("UNKNOWN"), false);
});

test("shell_schema: the health view is deep frozen with stable, always visible sections", () => {
  const view = buildHealthView({
    auth: authenticated(),
    liveness_receipt: livenessReceipt(),
    readiness_receipt: readinessReceipt(),
  });
  assert.equal(Object.isFrozen(view), true);
  assert.equal(Object.isFrozen(view.sections), true);
  assert.deepEqual(view.sections.map((entry) => entry.id), [
    "overall-health-state",
    "degraded-and-failed-checks",
    "all-checks",
    "process-liveness",
  ]);
  for (const entry of view.sections) {
    assert.equal(entry.visible, true, `${entry.id} must remain visible`);
    assert.deepEqual(Object.keys(entry).sort(), ["id", "items", "state", "title", "visible"]);
  }
  assert.deepEqual(unknownHealthView(authenticated()).sections.map((entry) => entry.id), [
    "overall-health-state",
    "degraded-and-failed-checks",
    "all-checks",
    "process-liveness",
  ]);
});

test("shell_schema: the declared local security posture is frozen data", () => {
  assert.equal(Object.isFrozen(SHELL_SECURITY_POLICY), true);
  assert.equal(SHELL_SECURITY_POLICY.network_binding, "LOOPBACK_ONLY");
  assert.equal(
    SHELL_SECURITY_POLICY.credential_storage,
    "NO_BROWSER_STORAGE_OF_CREDENTIAL_MATERIAL",
  );
  assert.equal(SHELL_SECURITY_POLICY.evidence_rendering, "ESCAPED_TEXT_ONLY_NO_RAW_HTML");
  for (const directive of ["default-src 'self'", "frame-ancestors 'none'", "object-src 'none'"]) {
    assert.ok(SHELL_SECURITY_POLICY.content_security_policy.includes(directive));
  }
  assert.ok(SHELL_SECURITY_POLICY.write_methods_requiring_origin_check.includes("POST"));
});

test("shell_schema: product modules read no clock, no random source and no environment", () => {
  for (const relative of PRODUCT_MODULES) {
    const text = readFileSync(resolve(REPO_ROOT, relative), "utf8");
    for (const forbidden of [
      /Date\s*\.\s*now/u,
      /new\s+Date\s*\(/u,
      /Math\s*\.\s*random/u,
      /process\s*\.\s*env/u,
      /performance\s*\.\s*now/u,
    ]) {
      assert.equal(forbidden.test(text), false, `${relative} matches ${forbidden}`);
    }
  }
});

test("shell_schema: the auth machine record restates the table it was built from", () => {
  const record = authMachineRecord();
  assert.equal(Object.isFrozen(record), true);
  assert.deepEqual(record.states, [...AUTH_STATES]);
  assert.deepEqual(record.events, [...AUTH_EVENTS]);
  assert.deepEqual(record.schemes, [...AUTH_SCHEMES]);
  assert.deepEqual(Object.keys(record.transitions).sort(), [...AUTH_STATES].sort());
});
