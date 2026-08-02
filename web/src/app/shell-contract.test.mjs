import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import * as uiClient from "../generated/ui-client/index.mjs";
import {
  applyAuthEvent,
  AUTH_SCHEMES,
  AUTH_STATES,
  initialAuthState,
  isAuthorized,
} from "./auth.mjs";
import { buildShellNavigation, DEFAULT_VIEW_SPECS, renderView } from "./shell.mjs";
import {
  buildHealthView,
  HEALTH_CHECK_STATUSES,
  HEALTH_OVERALL_STATES,
  HEALTH_PROFILES,
  LIVENESS_OPERATION_ID,
  READINESS_OPERATION_ID,
} from "../features/health/index.mjs";
import {
  authenticatedSession,
  degradedHealthReport,
  livenessReceipt,
  readinessProblemReceipt,
  readinessReceipt,
} from "../features/health/health-test-fixtures.mjs";

const APP_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(APP_DIR, "../../..");

const routeManifest = JSON.parse(
  readFileSync(resolve(APP_DIR, "../generated/ui-client/route-manifest.json"), "utf8"),
);
const routeTable = routeManifest.routeTable;
const healthReportSchema = JSON.parse(
  readFileSync(resolve(REPO_ROOT, "schemas/plugin-health-report.schema.json"), "utf8"),
);
const openapiText = readFileSync(
  resolve(REPO_ROOT, "openapi/epistemic-foundry-v1.openapi.yaml"),
  "utf8",
);

const routeById = new Map(routeTable.operations.map((operation) => [operation.operationId, operation]));
const receipt = (operationId, overrides = {}) => ({
  body_hash: `sha256:${"c".repeat(64)}`,
  degraded_reasons: [],
  item_count: null,
  operation_id: operationId,
  outcome: "SUCCESS",
  status: routeById.get(operationId).successStatus,
  ...overrides,
});

test("shell_contract: every view binds an operation the generated client exports", () => {
  const navigation = buildShellNavigation();
  assert.equal(navigation.views.length, DEFAULT_VIEW_SPECS.length);
  for (const view of navigation.views) {
    assert.ok(
      routeTable.operationIds.includes(view.operation_id),
      `${view.view_id} binds ${view.operation_id}, absent from the route manifest`,
    );
    assert.equal(typeof uiClient[view.operation_id], "function");
    const route = routeById.get(view.operation_id);
    assert.equal(view.method, route.method);
    assert.equal(view.path_template, route.path);
    assert.equal(view.success_status, route.successStatus);
    assert.deepEqual(view.path_parameters, route.pathParameters);
    assert.equal(view.response_schema_ref, route.responseSchemaRef);
  }
});

test("shell_contract: mutation is derived from the declared method, never asserted", () => {
  const navigation = buildShellNavigation();
  for (const view of navigation.views) {
    assert.equal(view.mutating, routeById.get(view.operation_id).method !== "GET");
  }
  const declaredMutating = navigation.views
    .filter((view) => routeById.get(view.operation_id).method === "POST")
    .map((view) => view.view_id);
  assert.deepEqual(navigation.mutating_view_ids, declaredMutating);
  assert.ok(navigation.mutating_view_ids.length > 0, "at least one action view must exist");
});

test("shell_contract: the navigation records the provenance of the client it composed", () => {
  const navigation = buildShellNavigation();
  assert.equal(navigation.base_path, routeTable.basePath);
  assert.equal(navigation.source_document.sha256, routeTable.documentSha256);
  assert.equal(navigation.source_document.route_table_sha256, uiClient.SOURCE_DOCUMENT.routeTableSha256);
  assert.equal(navigation.source_document.operation_count, routeTable.operationCount);
  assert.equal(navigation.source_document.operation_count, 33);
  assert.equal(navigation.source_document.path, routeTable.documentPath);
});

test("shell_contract: the shell composes the client rather than hand written paths", () => {
  const shellSource = readFileSync(resolve(APP_DIR, "shell.mjs"), "utf8");
  const healthSource = readFileSync(
    resolve(REPO_ROOT, "web/src/features/health/health-view.mjs"),
    "utf8",
  );
  for (const source of [shellSource, healthSource]) {
    assert.equal(/fetch\s*\(/u.test(source), false, "no product module performs its own I/O");
    assert.equal(/["']\/api\/v1/u.test(source), false, "no product module writes a base path");
  }
  const declaredPaths = new Set(routeTable.operations.map((operation) => operation.path));
  for (const match of shellSource.matchAll(/["'](\/[a-z0-9{}/_-]+)["']/gu)) {
    assert.equal(
      declaredPaths.has(match[1]),
      false,
      `${match[1]} looks like a hand written route literal`,
    );
  }
});

test("shell_contract: the health surface binds the two declared System health operations", () => {
  const liveness = routeById.get(LIVENESS_OPERATION_ID);
  const readiness = routeById.get(READINESS_OPERATION_ID);
  assert.equal(liveness.path, "/health/live");
  assert.equal(liveness.method, "GET");
  assert.equal(liveness.responseSchemaRef, "#/components/schemas/Liveness");
  assert.equal(readiness.path, "/health/ready");
  assert.equal(readiness.method, "GET");
  assert.equal(readiness.responseSchemaRef, "../schemas/plugin-health-report.schema.json");
  assert.ok(/Liveness:[\s\S]{0,200}?const:\s*live/u.test(openapiText));
});

test("shell_contract: rendered health states are exactly the states the schema declares", () => {
  assert.deepEqual([...HEALTH_OVERALL_STATES], healthReportSchema.properties.overall.enum);
  assert.deepEqual(
    [...HEALTH_CHECK_STATUSES],
    healthReportSchema.properties.checks.items.properties.status.enum,
  );
  assert.deepEqual([...HEALTH_PROFILES], healthReportSchema.properties.profile.enum);
  const view = buildHealthView({
    auth: authenticatedSession(),
    readiness_receipt: readinessReceipt(),
  });
  assert.deepEqual(
    Object.keys(view.checks[0]).sort(),
    [...healthReportSchema.properties.checks.items.required].sort(),
  );
});

test("shell_contract: the declared security schemes are the ones the document declares", () => {
  const block = openapiText.slice(openapiText.indexOf("securitySchemes:"));
  for (const scheme of AUTH_SCHEMES) {
    assert.ok(new RegExp(`\\n\\s{4}${scheme}:`, "u").test(block), `${scheme} is not declared`);
  }
  assert.equal(AUTH_SCHEMES.length, 2);
});

test("shell_contract: the auth machine reaches every declared state from the initial state", () => {
  const start = initialAuthState();
  assert.equal(isAuthorized(start), false);
  const authenticating = applyAuthEvent(start, "BEGIN_AUTHENTICATION", {
    scheme: "LocalSession",
    session_label: "workspace-alpha",
  });
  assert.equal(authenticating.state, "AUTHENTICATING");
  const authenticated = applyAuthEvent(authenticating, "AUTHENTICATION_SUCCEEDED");
  assert.equal(authenticated.state, "AUTHENTICATED");
  assert.equal(isAuthorized(authenticated), true);
  const expired = applyAuthEvent(authenticated, "SESSION_EXPIRED");
  assert.equal(expired.state, "EXPIRED");
  assert.equal(isAuthorized(expired), false);
  const retrying = applyAuthEvent(expired, "BEGIN_AUTHENTICATION");
  assert.equal(retrying.state, "AUTHENTICATING");
  const signedOut = applyAuthEvent(authenticated, "SIGN_OUT");
  assert.equal(signedOut.state, "UNAUTHENTICATED");
  assert.equal(signedOut.scheme, null);
  assert.equal(signedOut.session_label, null);
  const reached = new Set([
    start.state,
    authenticating.state,
    authenticated.state,
    expired.state,
    retrying.state,
    signedOut.state,
  ]);
  assert.deepEqual([...reached].sort(), [...AUTH_STATES].sort());
  assert.equal(authenticated.transition_count, 2);
});

test("shell_contract: read model state follows the receipt and never the caller", () => {
  const navigation = buildShellNavigation();
  const auth = authenticatedSession();
  const unknown = renderView(navigation, { auth, view_id: "forge-docket" });
  assert.equal(unknown.data_state, "UNKNOWN");
  assert.equal(unknown.receipt_outcome, null);
  const ready = renderView(navigation, {
    auth,
    receipt: receipt("listRuns", { item_count: 3 }),
    view_id: "forge-docket",
  });
  assert.equal(ready.data_state, "READY");
  const empty = renderView(navigation, {
    auth,
    receipt: receipt("listRuns", { item_count: 0 }),
    view_id: "forge-docket",
  });
  assert.equal(empty.data_state, "EMPTY_CONFIRMED");
  const degraded = renderView(navigation, {
    auth,
    receipt: receipt("listRuns", {
      degraded_reasons: ["one snapshot lane did not answer"],
      item_count: 2,
    }),
    view_id: "forge-docket",
  });
  assert.equal(degraded.data_state, "DEGRADED");
  assert.deepEqual(degraded.degraded_reasons, ["one snapshot lane did not answer"]);
  const unavailable = renderView(navigation, {
    auth,
    receipt: receipt("listRuns", {
      body_hash: null,
      item_count: null,
      outcome: "PROBLEM",
      status: "503",
    }),
    view_id: "forge-docket",
  });
  assert.equal(unavailable.data_state, "UNAVAILABLE");
  const offline = renderView(navigation, {
    auth,
    receipt: receipt("listRuns", {
      body_hash: null,
      item_count: null,
      outcome: "TRANSPORT_FAILURE",
      status: null,
    }),
    view_id: "forge-docket",
  });
  assert.equal(offline.data_state, "UNAVAILABLE");
});

test("shell_contract: EMPTY_CONFIRMED, UNAVAILABLE and UNKNOWN stay distinct (EF4-I23)", () => {
  const navigation = buildShellNavigation();
  const auth = authenticatedSession();
  const states = ["listRuns"].flatMap(() => [
    renderView(navigation, {
      auth,
      receipt: receipt("listRuns", { item_count: 0 }),
      view_id: "forge-docket",
    }),
    renderView(navigation, {
      auth,
      receipt: receipt("listRuns", {
        body_hash: null,
        item_count: null,
        outcome: "PROBLEM",
        status: "500",
      }),
      view_id: "forge-docket",
    }),
    renderView(navigation, { auth, view_id: "forge-docket" }),
  ]);
  assert.deepEqual(
    states.map((record) => record.data_state),
    ["EMPTY_CONFIRMED", "UNAVAILABLE", "UNKNOWN"],
  );
  assert.deepEqual(
    states.map((record) => record.state_is_confirmed_empty),
    [true, false, false],
  );
  assert.equal(new Set(states.map((record) => record.record_hash)).size, 3);
});

test("shell_contract: health is UNKNOWN until a readiness response arrives", () => {
  const auth = authenticatedSession();
  const nothing = buildHealthView({ auth });
  assert.equal(nothing.overall, "UNKNOWN");
  assert.equal(nothing.data_state, "UNKNOWN");
  assert.equal(nothing.overall_is_declared_by_api, false);
  assert.equal(nothing.liveness.state, "UNKNOWN");
  const liveOnly = buildHealthView({ auth, liveness_receipt: livenessReceipt() });
  assert.equal(liveOnly.liveness.state, "LIVE");
  assert.equal(liveOnly.overall, "UNKNOWN", "a live process is not a healthy dependency graph");
  const failed = buildHealthView({ auth, readiness_receipt: readinessProblemReceipt() });
  assert.equal(failed.overall, "UNKNOWN");
  assert.equal(failed.data_state, "UNAVAILABLE");
  assert.notEqual(failed.data_state, nothing.data_state);
});

test("shell_contract: DEGRADED is rendered as a first class state with its checks", () => {
  const view = buildHealthView({
    auth: authenticatedSession(),
    claimed_overall: "DEGRADED",
    readiness_receipt: readinessReceipt(degradedHealthReport()),
  });
  assert.equal(view.overall, "DEGRADED");
  assert.equal(view.data_state, "READY");
  assert.equal(view.degraded_checks.length, 1);
  assert.equal(view.degraded_checks[0].status, "WARN");
  const degradedSection = view.sections.find((entry) => entry.id === "degraded-and-failed-checks");
  assert.equal(degradedSection.visible, true);
  assert.equal(degradedSection.state, "POPULATED");
  assert.equal(degradedSection.items.length, 1);
  assert.ok(degradedSection.items[0].remediation.length > 0);
});

test("shell_contract: a healthy report renders an empty degraded section, not a hidden one", () => {
  const view = buildHealthView({
    auth: authenticatedSession(),
    claimed_overall: "PASS",
    readiness_receipt: readinessReceipt(),
  });
  const degradedSection = view.sections.find((entry) => entry.id === "degraded-and-failed-checks");
  assert.equal(degradedSection.visible, true);
  assert.equal(degradedSection.state, "EMPTY_CONFIRMED");
  assert.deepEqual(degradedSection.items, []);
  const unknownSection = buildHealthView({ auth: authenticatedSession() }).sections.find(
    (entry) => entry.id === "degraded-and-failed-checks",
  );
  assert.equal(unknownSection.state, "UNKNOWN");
  assert.notEqual(unknownSection.state, degradedSection.state);
});
