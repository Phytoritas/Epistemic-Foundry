import assert from "node:assert/strict";
import test from "node:test";

import {
  assembleIntakeFrame,
  buildIntakeView,
  IntakeContractError,
  renderIntakePanel,
} from "./index.mjs";
import {
  measurementCompatibility,
  ontologyResolution,
  readyInput,
  sampleConsent,
} from "./intake-test-fixtures.mjs";

const clone = (value) => structuredClone(value);

test("intake_ui_test: Inbox and blockers are the first visible intake section", () => {
  const input = readyInput();
  input.insight_card.registration_status = "inbox";
  input.insight_card.scope.population = null;
  input.council_ready = false;
  input.council_blockers = [
    "COUNCIL_REGISTRATION_STATUS_NOT_ELIGIBLE",
    "COUNCIL_SCOPE_POPULATION_UNKNOWN",
  ];
  input.unknown_scope = [
    ...input.unknown_scope,
    { path: "scope.population", source: "EXPLICIT_NULL" },
  ];

  const view = buildIntakeView(input);

  assert.equal(view.heading, "Inbox");
  assert.equal(view.inbox.visible, true);
  assert.equal(view.sections[0].id, "blockers");
  assert.equal(view.sections[0].visible, true);
  assert.equal(view.sections[0].state, "BLOCKED");
  assert.deepEqual(
    view.sections[0].items.map(({ code }) => code).sort(),
    ["COUNCIL_REGISTRATION_STATUS_NOT_ELIGIBLE", "COUNCIL_SCOPE_POPULATION_UNKNOWN"],
  );
  assert.equal(view.export_control.enabled, false);
});

test("intake_ui_test: a complete eligible frame exposes a truthful ready export control", () => {
  const view = buildIntakeView(readyInput());

  assert.equal(view.heading, "Eligible frame");
  assert.equal(view.sections[0].state, "CLEAR");
  assert.equal(view.export_control.status, "READY");
  assert.equal(view.export_control.enabled, true);
  assert.deepEqual(view.export_control.reason_codes, []);
});

test("intake_ui_test: confidence and verdict are not invented anywhere in the projection", () => {
  const serialized = JSON.stringify(buildIntakeView(readyInput()));

  assert.equal(/confidence/i.test(serialized), false);
  assert.equal(/verdict/i.test(serialized), false);
});

test("intake_ui_test: untrusted statement and blocker text are HTML-escaped", () => {
  const input = readyInput();
  input.insight_card.statement = '<img src=x onerror="alert(1)"> remains untrusted evidence text.';
  input.insight_card.registration_status = "inbox";
  input.council_ready = false;
  input.council_blockers = ["COUNCIL_REGISTRATION_STATUS_NOT_ELIGIBLE"];

  const html = renderIntakePanel(input);

  assert.equal(html.includes("<img src=x"), false);
  assert.equal(html.includes("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"), true);
  assert.equal(html.includes("<h2>Blockers</h2>"), true);
  assert.equal(html.includes("disabled aria-disabled=\"true\""), true);
});

test("intake_ui_test: pending ontology approval remains a visible blocker and review item", () => {
  const input = readyInput();
  input.ontology_resolutions = [
    ontologyResolution({
      abstention_reasons: ["HUMAN_APPROVAL_REQUIRED"],
      review_queue_items: [
        {
          candidate_construct_ids: ["construct-engagement"],
          mapping_key_hash: `sha256:${"1".repeat(64)}`,
          policy_version: "POLICY-1",
          proposed_construct_id: "construct-engagement",
          reasons: ["HIGH_IMPACT", "MAPPING_REVIEW"],
          required_authority_artifact: "HumanDecision",
          review_item_id: "ORQ-review-1",
        },
      ],
      selected_construct_id: null,
      status: "PENDING_APPROVAL",
    }),
  ];

  const view = buildIntakeView(input);

  assert.equal(view.export_control.enabled, false);
  assert.equal(view.sections[0].items[0].code, "ONTOLOGY_HUMAN_APPROVAL_REQUIRED");
  assert.equal(view.sections[2].state, "AUTHORITY_REQUIRED");
  assert.equal(view.sections[2].items[0].review_item_id, "ORQ-review-1");
  assert.equal(view.sections[2].items[0].authority, "HumanDecision");
});

test("intake_ui_test: unresolved measurement identity blocks export", () => {
  const input = readyInput();
  input.measurement_compatibilities = [
    measurementCompatibility({
      aggregation_allowed: false,
      compatibility_status: "UNKNOWN",
      construct_equivalence: "UNKNOWN",
      method_threats: ["MISSING_UNIT"],
      promotion_ceiling: "BLOCK_AGGREGATION",
    }),
  ];

  const view = buildIntakeView(input);

  assert.equal(view.export_control.enabled, false);
  assert.deepEqual(view.export_control.reason_codes, ["MEASUREMENT_RESOLUTION_REQUIRED"]);
});

test("intake_ui_test: a method boundary remains visible without being relabelled a blocker", () => {
  const input = readyInput();
  input.measurement_compatibilities = [
    measurementCompatibility({
      aggregation_allowed: false,
      compatibility_status: "WITHIN_METHOD_ONLY",
      method_threats: ["METHOD_MISMATCH"],
      promotion_ceiling: "METHOD_BOUNDARY_ONLY",
    }),
  ];

  const view = buildIntakeView(input);

  assert.equal(view.export_control.enabled, true);
  assert.equal(view.sections[3].state, "VISIBLE_LIMITATIONS");
  assert.equal(
    view.sections[3].items.some(({ code }) => code === "MEASUREMENT_BOUNDARY_VISIBLE"),
    true,
  );
  assert.equal(
    view.sections[0].items.some(({ code }) => code === "MEASUREMENT_BOUNDARY_VISIBLE"),
    false,
  );
});

test("intake_ui_test: required consent fails closed until one active record covers the contract", () => {
  const input = readyInput();
  input.consent_requirement = {
    evaluated_at: "2026-08-01T00:00:00Z",
    records: [],
    required: true,
    required_data_classes: ["research decisions"],
    required_purposes: ["workspace recall"],
    required_scopes: ["WORKSPACE"],
  };

  assert.deepEqual(buildIntakeView(input).export_control.reason_codes, ["CONSENT_REQUIRED"]);

  input.consent_requirement.records = [sampleConsent()];
  assert.equal(buildIntakeView(input).export_control.enabled, true);
});

test("intake_ui_test: expiring consent without an evaluation time cannot be treated as valid", () => {
  const input = readyInput();
  input.consent_requirement = {
    evaluated_at: null,
    records: [sampleConsent()],
    required: true,
    required_data_classes: ["research decisions"],
    required_purposes: ["workspace recall"],
    required_scopes: ["WORKSPACE"],
  };

  assert.deepEqual(buildIntakeView(input).export_control.reason_codes, [
    "CONSENT_EVALUATION_TIME_REQUIRED",
  ]);
});

test("intake_ui_test: assembling the UI does not mutate caller-owned authority inputs", () => {
  const input = readyInput();
  input.ontology_resolutions = [ontologyResolution()];
  input.measurement_compatibilities = [measurementCompatibility()];
  const before = clone(input);

  assembleIntakeFrame(input);
  buildIntakeView(input);
  renderIntakePanel(input);

  assert.deepEqual(input, before);
});

test("intake_ui_test: missing upstream blocker evidence is rejected instead of hidden", () => {
  const input = readyInput();
  input.insight_card.registration_status = "inbox";
  input.council_ready = false;

  assert.throws(
    () => assembleIntakeFrame(input),
    (error) =>
      error instanceof IntakeContractError && error.code === "INTAKE_COUNCIL_STATE_CONFLICT",
  );
});

test("intake_ui_test: a blocker outside the exact I02 vocabulary is rejected", () => {
  const input = readyInput();
  input.council_ready = false;
  input.council_blockers = ["MODEL_LOW_CONFIDENCE"];

  assert.throws(
    () => assembleIntakeFrame(input),
    (error) =>
      error instanceof IntakeContractError && error.code === "INTAKE_COUNCIL_STATE_CONFLICT",
  );
});

test("intake_ui_test: I02 blocker order remains canonical", () => {
  const input = readyInput();
  input.insight_card.registration_status = "inbox";
  input.insight_card.scope.population = null;
  input.council_ready = false;
  input.council_blockers = [
    "COUNCIL_SCOPE_POPULATION_UNKNOWN",
    "COUNCIL_REGISTRATION_STATUS_NOT_ELIGIBLE",
  ];
  input.unknown_scope = [
    ...input.unknown_scope,
    { path: "scope.population", source: "EXPLICIT_NULL" },
  ];

  assert.throws(
    () => assembleIntakeFrame(input),
    (error) =>
      error instanceof IntakeContractError && error.code === "INTAKE_COUNCIL_STATE_CONFLICT",
  );
});

test("intake_ui_test: I03 aggregation decisions are checked in both directions", () => {
  const input = readyInput();
  input.measurement_compatibilities = [
    measurementCompatibility({ aggregation_allowed: false }),
  ];

  assert.throws(
    () => assembleIntakeFrame(input),
    (error) =>
      error instanceof IntakeContractError &&
      error.code === "INTAKE_MEASUREMENT_STATE_CONFLICT",
  );
});

test("intake_ui_test: unrestricted measurement output cannot contradict equivalence", () => {
  const input = readyInput();
  input.measurement_compatibilities = [
    measurementCompatibility({
      aggregation_allowed: false,
      construct_equivalence: "DIFFERENT",
    }),
  ];

  assert.throws(
    () => assembleIntakeFrame(input),
    (error) =>
      error instanceof IntakeContractError &&
      error.code === "INTAKE_MEASUREMENT_STATE_CONFLICT",
  );
});

test("intake_ui_test: resolved ontology selection must name the unique complete candidate", () => {
  const input = readyInput();
  input.ontology_resolutions = [
    ontologyResolution({
      proposed_construct_id: "construct-forged",
      selected_construct_id: "construct-forged",
    }),
  ];

  assert.throws(
    () => assembleIntakeFrame(input),
    (error) =>
      error instanceof IntakeContractError && error.code === "INTAKE_ONTOLOGY_STATE_CONFLICT",
  );
});

test("intake_ui_test: a normalized null scope value cannot lose its I02 sidecar", () => {
  const input = readyInput();
  input.unknown_scope = input.unknown_scope.filter(
    ({ path }) => path !== "scope.geography",
  );

  assert.throws(
    () => assembleIntakeFrame(input),
    (error) =>
      error instanceof IntakeContractError && error.code === "INTAKE_UNKNOWN_SCOPE_CONFLICT",
  );
});

test("intake_ui_test: malformed ScopeVector values fail closed", () => {
  const input = readyInput();
  input.insight_card.scope.conditions = { invalid_nested_value: { confidence: 1 } };

  assert.throws(
    () => assembleIntakeFrame(input),
    (error) => error instanceof IntakeContractError && error.code === "INTAKE_INPUT_INVALID",
  );
});

test("intake_ui_test: a forged assembled frame cannot hide a derived blocker", () => {
  const input = readyInput();
  input.insight_card.registration_status = "inbox";
  input.council_ready = false;
  input.council_blockers = ["COUNCIL_REGISTRATION_STATUS_NOT_ELIGIBLE"];
  const frame = clone(assembleIntakeFrame(input));
  frame.blockers = [];
  frame.exportable = true;

  assert.throws(
    () => buildIntakeView(frame),
    (error) =>
      error instanceof IntakeContractError &&
      error.code === "INTAKE_FRAME_DERIVATION_MISMATCH",
  );
});

test("intake_ui_test: unknown input fields fail closed", () => {
  const input = readyInput();
  input.model_confidence = 0.99;

  assert.throws(
    () => assembleIntakeFrame(input),
    (error) => error instanceof IntakeContractError && error.code === "INTAKE_FIELD_SET_INVALID",
  );
});
