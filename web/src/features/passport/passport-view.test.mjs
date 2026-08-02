/**
 * U03 Hypothesis Passport view suite.
 *
 * The named tests below cover the five required checks the development manifest
 * declares for U03, without duplicating a single canonical vocabulary:
 *
 *   - schema_and_type_check         -> "the status vocabularies are the ones the
 *                                       passport schema declares"
 *   - unit_and_contract_tests       -> "the verdict, stability, falsifiers and next test
 *                                       render together"; "the seven confidence dimensions
 *                                       stay seven"; "projection is deterministic, frozen
 *                                       and preserving"
 *   - negative_and_adversarial      -> "a hidden counter-evidence or required field refuses";
 *                                       "an aggregate or undeclared display field refuses";
 *                                       "an edit affordance on an immutable revision refuses";
 *                                       "a revision mismatch refuses";
 *                                       "an undeclared status refuses";
 *                                       "proxies and accessors fail without execution";
 *                                       "hostile text is escaped"
 *   - provenance_and_receipt_audit  -> "the view carries its source receipt and binds only
 *                                       the declared read operation"
 *   - independent_review            -> "every finding code stands alone"
 *
 * There is no HTTP client, no DOM and no clock here.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  CALIBRATION_STATUSES,
  CAUSAL_STATUSES,
  CONFIDENCE_DIMENSIONS,
  COUNTER_EVIDENCE_FIELDS,
  EPISTEMIC_STATUSES,
  LIFECYCLE_STATUSES,
  NOVELTY_STATUSES,
  PASSPORT_FINDING_CODES,
  PASSPORT_OPERATION_IDS,
  PASSPORT_VIEW_VERSION,
  PROMOTION_LEVELS,
  PassportViewError,
  REQUIRED_VISIBLE_FIELDS,
  SEARCH_COMPLETENESS_STATES,
  buildPassportView,
  passportOperationRequest,
  passportRevisionRequest,
  renderPassportPanel,
  validatePassportInput,
} from "./index.mjs";
import { passport, passportInput, presentation } from "./passport-test-fixtures.mjs";

const REPO = new URL("../../../../", import.meta.url);
const readJson = (relative) => JSON.parse(readFileSync(new URL(relative, REPO), "utf8"));
const MODULE_SOURCE = readFileSync(
  fileURLToPath(new URL("./passport-view.mjs", import.meta.url)),
  "utf8",
);

const errorCode = (code) => (error) =>
  error instanceof PassportViewError && error.code === code;

const withoutField = (field) =>
  presentation({ visible_fields: [...REQUIRED_VISIBLE_FIELDS].filter((entry) => entry !== field) });

// --- schema_and_type_check ---------------------------------------------------

test("passport_view: the status vocabularies are the ones the passport schema declares", () => {
  const schema = readJson("schemas/hypothesis-passport.schema.json").properties;
  assert.deepEqual([...EPISTEMIC_STATUSES], schema.epistemic_status.enum);
  assert.deepEqual([...CAUSAL_STATUSES], schema.causal_status.enum);
  assert.deepEqual([...NOVELTY_STATUSES], schema.novelty_status.enum);
  assert.deepEqual([...PROMOTION_LEVELS], schema.promotion_level.enum);
  assert.deepEqual([...SEARCH_COMPLETENESS_STATES], schema.search_completeness.enum);
  assert.deepEqual([...LIFECYCLE_STATUSES], schema.lifecycle_status.enum);
  assert.deepEqual(
    [...CALIBRATION_STATUSES],
    schema.epistemic_assessment.properties.calibration_status.enum,
  );
  assert.equal(CONFIDENCE_DIMENSIONS.length, 7);
  assert.equal(Object.isFrozen(CONFIDENCE_DIMENSIONS), true);
});

// --- unit_and_contract_tests -------------------------------------------------

test("passport_view: verdict, stability, falsifiers and next test render together", () => {
  const view = buildPassportView(passportInput());
  assert.equal(view.passport_identity.immutability, "IMMUTABLE_REVISION");
  assert.equal(view.verdict.epistemic_status, "SUPPORTED");
  assert.equal(view.verdict.causal_status, "ASSUMPTION_DEPENDENT");
  assert.equal(view.verdict.promotion_level, "CANDIDATE");
  assert.equal(view.stability.lifecycle_status, "active");
  assert.equal(view.stability.state, "NO_STALENESS_RECORDED");
  assert.deepEqual(view.falsifiers.falsifier_ids, ["FL-0001"]);
  assert.equal(view.next_test.state, "SCHEDULED");
  // Counter-evidence is a first-class element beside the verdict.
  assert.equal(view.counter_evidence.strongest_counterevidence_id, "EV-9001");
  assert.equal(view.counter_evidence.minority_report_state, "PRESERVED");
  const sectionIds = view.sections.map((section) => section.id);
  assert.ok(sectionIds.indexOf("verdict") < sectionIds.indexOf("counter-evidence"));
});

test("passport_view: the seven confidence dimensions stay seven separate dimensions", () => {
  const view = buildPassportView(passportInput());
  assert.deepEqual(Object.keys(view.confidence_vector).sort(), [...CONFIDENCE_DIMENSIONS].sort());
  const confidenceSection = view.sections.find((section) => section.id === "confidence-dimensions");
  assert.equal(confidenceSection.state, "SEPARATE_DIMENSIONS");
});

test("passport_view: a stale revision surfaces its staleness reasons", () => {
  const view = buildPassportView(
    passportInput({
      passport: passport({ lifecycle_status: "stale", stale_reasons: ["a superseding revision exists"] }),
    }),
  );
  assert.equal(view.stability.state, "STALENESS_RECORDED");
  assert.deepEqual(view.counter_evidence.stale_reasons, ["a superseding revision exists"]);
});

test("passport_view: projection is deterministic, frozen and input preserving", () => {
  const input = passportInput();
  const before = structuredClone(input);
  const first = buildPassportView(input);
  const second = buildPassportView(passportInput());
  assert.deepEqual(first, second);
  assert.deepEqual(input, before);
  assert.equal(Object.isFrozen(first), true);
  assert.equal(Object.isFrozen(first.confidence_vector), true);
  assert.equal(Object.isFrozen(first.sections), true);
  assert.equal(first.version, PASSPORT_VIEW_VERSION);
  assert.equal(/Date\.now|Math\.random|process\.env|new Date\(/u.test(MODULE_SOURCE), false);
});

// --- negative_and_adversarial_tests -----------------------------------------

test("passport_view: hiding a counter-evidence or a required field refuses", () => {
  for (const field of COUNTER_EVIDENCE_FIELDS) {
    assert.throws(
      () => buildPassportView(passportInput({ presentation: withoutField(field) })),
      errorCode("COUNTER_EVIDENCE_HIDDEN"),
    );
  }
  assert.throws(
    () => buildPassportView(passportInput({ presentation: withoutField("promotion_level") })),
    errorCode("REQUIRED_FIELD_HIDDEN"),
  );
});

test("passport_view: an aggregate or undeclared display field refuses", () => {
  assert.throws(
    () =>
      buildPassportView(
        passportInput({
          presentation: presentation({
            visible_fields: [...REQUIRED_VISIBLE_FIELDS, "overall_confidence"],
          }),
        }),
      ),
    errorCode("CONFIDENCE_AGGREGATED"),
  );
  assert.throws(
    () =>
      buildPassportView(
        passportInput({
          presentation: presentation({
            visible_fields: [...REQUIRED_VISIBLE_FIELDS, "invented_field"],
          }),
        }),
      ),
    errorCode("UNKNOWN_DISPLAY_FIELD"),
  );
});

test("passport_view: an edit affordance on an immutable revision refuses", () => {
  assert.throws(
    () =>
      buildPassportView(
        passportInput({ presentation: presentation({ affordances: ["READ_REVISION", "EDIT_VERDICT"] }) }),
      ),
    errorCode("IMMUTABLE_REVISION_EDIT_AFFORDANCE"),
  );
  assert.throws(
    () =>
      buildPassportView(
        passportInput({ presentation: presentation({ affordances: ["DO_A_BACKFLIP"] }) }),
      ),
    errorCode("UNKNOWN_AFFORDANCE"),
  );
});

test("passport_view: a revision mismatch and an undeclared status refuse", () => {
  assert.throws(
    () => buildPassportView(passportInput({ presentation: presentation({ revision: 99 }) })),
    errorCode("REVISION_MISMATCH"),
  );
  assert.throws(
    () => buildPassportView(passportInput({ passport: passport({ epistemic_status: "PROBABLY" }) })),
    errorCode("UNKNOWN_PASSPORT_VOCABULARY"),
  );
  assert.throws(
    () => buildPassportView(passportInput({ passport: passport({ lifecycle_status: "zombie" }) })),
    errorCode("UNKNOWN_PASSPORT_VOCABULARY"),
  );
});

test("passport_view: proxies, accessors and unknown fields fail without execution", () => {
  const input = passportInput();
  assert.throws(() => buildPassportView(new Proxy(input, {})), errorCode("PASSPORT_INPUT_INVALID"));

  let invoked = false;
  const accessor = { ...input };
  Object.defineProperty(accessor, "passport", {
    enumerable: true,
    get() {
      invoked = true;
      return input.passport;
    },
  });
  assert.throws(() => buildPassportView(accessor), errorCode("PASSPORT_INPUT_INVALID"));
  assert.equal(invoked, false);

  assert.throws(
    () => buildPassportView(passportInput({ passport: passport({ overall_score: 0.9 }) })),
    errorCode("PASSPORT_INPUT_INVALID"),
  );
});

test("passport_view: hostile statement text is HTML escaped, immutability is declared", () => {
  const html = renderPassportPanel(
    passportInput({
      passport: passport({
        canonical_statement: '<img src=x onerror="boom"> statement of the hypothesis',
      }),
    }),
  );
  assert.equal(html.includes("<img src=x"), false);
  assert.equal(
    html.includes("&lt;img src=x onerror=&quot;boom&quot;&gt; statement of the hypothesis"),
    true,
  );
  assert.equal(html.includes('data-immutability="IMMUTABLE_REVISION"'), true);
  const verdict = html.indexOf('data-section="verdict"');
  const counter = html.indexOf('data-section="counter-evidence"');
  assert.ok(verdict > 0 && verdict < counter);
});

// --- provenance_and_receipt_audit -------------------------------------------

test("passport_view: the view carries its source receipt and binds only the read operation", () => {
  const view = buildPassportView(passportInput());
  assert.deepEqual(view.source_receipt, {
    attestation_id: "AT-0001",
    provenance_manifest_id: "PM-0001",
    evidence_pack_id: "EP-0001",
    bias_risk_register_id: "BRR-0001",
    decision_stability_report_id: "DSR-0001",
    operation_ids: [...PASSPORT_OPERATION_IDS],
  });

  const manifest = readJson("web/src/generated/ui-client/route-manifest.json");
  const declared = new Map(
    manifest.routeTable.operations.map((operation) => [operation.operationId, operation]),
  );
  for (const operationId of PASSPORT_OPERATION_IDS) assert.ok(declared.has(operationId));

  const request = passportRevisionRequest({ passport_id: "PASS-0001" });
  assert.equal(request.operationId, "getPassport");
  assert.equal(request.method, declared.get("getPassport").method);
  assert.equal(request.pathTemplate, declared.get("getPassport").path);
  assert.equal(request.url, "/api/v1/passports/PASS-0001");
  assert.equal(Object.isFrozen(request), true);

  const sent = [];
  passportRevisionRequest({ passport_id: "PASS-0002" }, (descriptor) => sent.push(descriptor));
  assert.equal(sent.length, 1);
  assert.equal(sent[0].url, "/api/v1/passports/PASS-0002");

  // The canonical document declares no passport write route, so a write refuses.
  assert.throws(
    () => passportOperationRequest("deletePassport", { path: { passport_id: "PASS-0001" } }),
    errorCode("OPERATION_NOT_DECLARED"),
  );
  assert.throws(
    () => passportRevisionRequest({ passport_id: "" }),
    errorCode("PASSPORT_INPUT_INVALID"),
  );
});

// --- independent_review ------------------------------------------------------

test("passport_view: every finding code stands alone with a distinct reason", () => {
  const codes = Object.keys(PASSPORT_FINDING_CODES);
  assert.ok(codes.length >= 9);
  const reasons = new Set();
  for (const code of codes) {
    assert.match(code, /^[A-Z][A-Z0-9_]+$/u);
    assert.ok(PASSPORT_FINDING_CODES[code].length > 50, code);
    assert.ok(MODULE_SOURCE.includes(code), code);
    reasons.add(PASSPORT_FINDING_CODES[code]);
  }
  assert.equal(reasons.size, codes.length);

  const raised = (() => {
    try {
      validatePassportInput({});
      return null;
    } catch (error) {
      return error;
    }
  })();
  assert.ok(raised instanceof PassportViewError);
  assert.equal(raised.reason, PASSPORT_FINDING_CODES.PASSPORT_INPUT_INVALID);
  assert.equal(Object.isFrozen(raised.context), true);
});
