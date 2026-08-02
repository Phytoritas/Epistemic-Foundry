/**
 * U03 Evidence Parliament view suite.
 *
 * The named tests below cover the five required checks the development manifest
 * declares for U03, without duplicating a single canonical vocabulary:
 *
 *   - schema_and_type_check         -> "vocabularies are the ones the schemas declare"
 *   - unit_and_contract_tests       -> "renders the verdict, promotion and briefs";
 *                                       "dissent is a first-class element";
 *                                       "projection is deterministic, frozen and preserving"
 *   - negative_and_adversarial      -> "a vote basis refuses"; "hidden or invented dissent
 *                                       refuses"; "a mismatched brief set refuses";
 *                                       "undeclared vocabulary refuses"; "proxies and
 *                                       accessors fail without execution"; "hostile text is escaped"
 *   - provenance_and_receipt_audit  -> "the view carries its source receipt and binds only
 *                                       declared operations"
 *   - independent_review            -> "every finding code stands alone"
 *
 * There is no HTTP client, no DOM and no clock here.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  BRIEF_ROLES,
  MINORITY_PRESERVATION_STATUSES,
  PARLIAMENT_FINDING_CODES,
  PARLIAMENT_OPERATION_IDS,
  PARLIAMENT_VERDICTS,
  PARLIAMENT_VIEW_VERSION,
  ParliamentViewError,
  PROMOTION_RECOMMENDATIONS,
  REFUSED_VERDICT_BASES,
  VERDICT_BASIS,
  buildParliamentView,
  parliamentAdjudicationRequest,
  parliamentDeliberationRequest,
  renderParliamentPanel,
  validateParliamentInput,
} from "./index.mjs";
import {
  ADJUDICATION_HASH,
  BRIEF_ONE_HASH,
  BRIEF_TWO_HASH,
  MINORITY_HASH,
  adjudication,
  defenderBrief,
  minorityReport,
  parliamentInput,
  presentation,
  prosecutorBrief,
} from "./parliament-test-fixtures.mjs";

const REPO = new URL("../../../../", import.meta.url);
const readJson = (relative) => JSON.parse(readFileSync(new URL(relative, REPO), "utf8"));
const MODULE_SOURCE = readFileSync(
  fileURLToPath(new URL("./parliament-view.mjs", import.meta.url)),
  "utf8",
);

const errorCode = (code) => (error) =>
  error instanceof ParliamentViewError && error.code === code;

const collectEnums = (schema, out = []) => {
  if (schema && typeof schema === "object") {
    if (Array.isArray(schema.enum)) out.push(schema.enum);
    for (const key of Object.keys(schema)) collectEnums(schema[key], out);
  }
  return out;
};

// --- schema_and_type_check ---------------------------------------------------

test("parliament_view: the vocabularies are the ones the canonical schemas declare", () => {
  const adjudicationSchema = readJson("schemas/adjudication.schema.json");
  const enums = collectEnums(adjudicationSchema).map((values) => new Set(values));
  const hasSet = (candidate) =>
    enums.some(
      (set) => set.size === candidate.length && candidate.every((value) => set.has(value)),
    );
  assert.ok(hasSet([...PARLIAMENT_VERDICTS]), "verdict vocabulary matches the adjudication schema");
  assert.ok(
    hasSet([...PROMOTION_RECOMMENDATIONS]),
    "promotion vocabulary matches the adjudication schema",
  );

  const briefSchema = readJson("schemas/council-brief.schema.json");
  const briefEnums = collectEnums(briefSchema).map((values) => [...values].sort().join(","));
  assert.ok(briefEnums.includes([...BRIEF_ROLES].sort().join(",")));

  const minoritySchema = readJson("schemas/minority-report.schema.json");
  const minorityEnums = collectEnums(minoritySchema).map((values) => [...values].sort().join(","));
  assert.ok(minorityEnums.includes([...MINORITY_PRESERVATION_STATUSES].sort().join(",")));

  for (const frozen of [PARLIAMENT_VERDICTS, PROMOTION_RECOMMENDATIONS, BRIEF_ROLES]) {
    assert.equal(Object.isFrozen(frozen), true);
  }
});

// --- unit_and_contract_tests -------------------------------------------------

test("parliament_view: the verdict is a gate decision and never a vote", () => {
  const view = buildParliamentView(parliamentInput());
  assert.equal(view.verdict.value, "CONDITIONAL");
  assert.equal(view.verdict.basis, VERDICT_BASIS);
  assert.equal(view.verdict.is_vote, false);
  assert.deepEqual(view.verdict.gate_decision_ids, ["GD-0001", "GD-0002"]);
  assert.equal(view.promotion.recommendation, "CANDIDATE");
  assert.equal(view.promotion.status, "RECOMMENDATION_NOT_DECISION");
  assert.equal(PARLIAMENT_VERDICTS.includes(view.verdict.value), true);
});

test("parliament_view: dissent is a first-class element beside the verdict", () => {
  const view = buildParliamentView(parliamentInput());
  assert.equal(view.minority_report.state, "PRESERVED");
  assert.equal(view.minority_report.items.length, 1);
  const item = view.minority_report.items[0];
  assert.equal(item.minority_report_id, "MR-0001");
  assert.equal(item.preservation_status, "required");
  assert.equal(item.report_hash, MINORITY_HASH);
  // The minority section precedes the council briefs in the section order.
  const sectionIds = view.sections.map((section) => section.id);
  assert.ok(sectionIds.indexOf("minority-report") < sectionIds.indexOf("council-briefs"));
  assert.equal(view.counter_evidence.strongest_counterevidence_id, "EV-0003");
  assert.deepEqual(view.counter_evidence.unresolved_issue_ids, ["UI-0001"]);
});

test("parliament_view: a recorded gate override surfaces instead of being hidden", () => {
  const view = buildParliamentView(
    parliamentInput({
      adjudication: adjudication({ deterministic_gate_override_attempted: true }),
    }),
  );
  assert.equal(view.gate_integrity.deterministic_gate_override_attempted, true);
  assert.equal(view.gate_integrity.state, "OVERRIDE_ATTEMPT_RECORDED");
  const section = view.sections.find((entry) => entry.id === "gate-integrity");
  assert.equal(section.state, "OVERRIDE_ATTEMPT_RECORDED");
});

test("parliament_view: projection is deterministic, frozen and input preserving", () => {
  const input = parliamentInput();
  const before = structuredClone(input);
  const first = buildParliamentView(input);
  const second = buildParliamentView(parliamentInput());
  assert.deepEqual(first, second);
  assert.deepEqual(input, before);
  assert.equal(Object.isFrozen(first), true);
  assert.equal(Object.isFrozen(first.sections), true);
  assert.equal(Object.isFrozen(first.minority_report.items), true);
  assert.equal(Object.isFrozen(first.briefs), true);
  assert.equal(first.version, PARLIAMENT_VIEW_VERSION);
  assert.equal(/Date\.now|Math\.random|process\.env|new Date\(/u.test(MODULE_SOURCE), false);
});

// --- negative_and_adversarial_tests -----------------------------------------

test("parliament_view: a vote, tally or majority basis refuses", () => {
  for (const basis of REFUSED_VERDICT_BASES) {
    assert.throws(
      () => buildParliamentView(parliamentInput({ presentation: presentation({ verdict_basis: basis }) })),
      errorCode("MAJORITY_VOTE_PRESENTATION"),
    );
  }
  assert.throws(
    () =>
      buildParliamentView(
        parliamentInput({ presentation: presentation({ verdict_basis: "SHOW_OF_HANDS" }) }),
      ),
    errorCode("MAJORITY_VOTE_PRESENTATION"),
  );
});

test("parliament_view: hidden, unrecorded or invented dissent refuses", () => {
  assert.throws(
    () =>
      buildParliamentView(
        parliamentInput({ presentation: presentation({ minority_report_ids: [] }) }),
      ),
    errorCode("MINORITY_REPORT_HIDDEN"),
  );

  assert.throws(
    () =>
      buildParliamentView(
        parliamentInput({
          adjudication: adjudication({ minority_report_ids: ["MR-0001", "MR-0002"] }),
          presentation: presentation({ minority_report_ids: ["MR-0001", "MR-0002"] }),
        }),
      ),
    errorCode("MINORITY_REPORT_RECORD_MISSING"),
  );

  assert.throws(
    () =>
      buildParliamentView(
        parliamentInput({
          presentation: presentation({ minority_report_ids: ["MR-0001", "MR-9999"] }),
        }),
      ),
    errorCode("MINORITY_REPORT_UNKNOWN"),
  );
});

test("parliament_view: a brief set that is not the one the adjudication cites refuses", () => {
  assert.throws(
    () => buildParliamentView(parliamentInput({ briefs: [defenderBrief()] })),
    errorCode("BRIEF_SET_MISMATCH"),
  );
  assert.throws(
    () =>
      buildParliamentView(
        parliamentInput({ presentation: presentation({ brief_ids: ["CB-0001"] }) }),
      ),
    errorCode("BRIEF_SET_MISMATCH"),
  );
});

test("parliament_view: values outside a canonical vocabulary refuse rather than render", () => {
  assert.throws(
    () => buildParliamentView(parliamentInput({ adjudication: adjudication({ verdict: "PROBABLY" }) })),
    errorCode("UNKNOWN_VERDICT"),
  );
  assert.throws(
    () =>
      buildParliamentView(
        parliamentInput({ adjudication: adjudication({ promotion_recommendation: "SHIP_IT" }) }),
      ),
    errorCode("UNKNOWN_PROMOTION_RECOMMENDATION"),
  );
  assert.throws(
    () => buildParliamentView(parliamentInput({ briefs: [defenderBrief({ role: "cheerleader" }), prosecutorBrief()] })),
    errorCode("UNKNOWN_BRIEF_ROLE"),
  );
  assert.throws(
    () =>
      buildParliamentView(
        parliamentInput({ minority_reports: [minorityReport({ preservation_status: "forgotten" })] }),
      ),
    errorCode("UNKNOWN_PRESERVATION_STATUS"),
  );
});

test("parliament_view: proxies, accessors and unknown fields fail without execution", () => {
  const input = parliamentInput();
  assert.throws(
    () => buildParliamentView(new Proxy(input, {})),
    errorCode("PARLIAMENT_INPUT_INVALID"),
  );

  let invoked = false;
  const accessor = { ...input };
  Object.defineProperty(accessor, "briefs", {
    enumerable: true,
    get() {
      invoked = true;
      return input.briefs;
    },
  });
  assert.throws(() => buildParliamentView(accessor), errorCode("PARLIAMENT_INPUT_INVALID"));
  assert.equal(invoked, false);

  assert.throws(
    () => buildParliamentView(parliamentInput({ adjudication: adjudication({ verdict_basis: "x" }) })),
    errorCode("PARLIAMENT_INPUT_INVALID"),
  );
});

test("parliament_view: hostile brief and minority text is HTML escaped, dissent renders first", () => {
  const html = renderParliamentPanel(
    parliamentInput({
      minority_reports: [
        minorityReport({
          minority_claim: '<img src=x onerror="boom"> claim',
        }),
      ],
    }),
  );
  assert.equal(html.includes("<img src=x"), false);
  assert.equal(html.includes("&lt;img src=x onerror=&quot;boom&quot;&gt; claim"), true);
  const minority = html.indexOf('data-section="minority-report"');
  const briefs = html.indexOf('data-section="council-briefs"');
  assert.ok(minority > 0 && minority < briefs);
  assert.equal(html.includes('data-verdict-basis="ADJUDICATION_GATE_DECISIONS"'), true);
});

// --- provenance_and_receipt_audit -------------------------------------------

test("parliament_view: the view carries its source receipt and binds only declared operations", () => {
  const view = buildParliamentView(parliamentInput());
  assert.deepEqual(view.source_receipt, {
    adjudication_hash: ADJUDICATION_HASH,
    brief_hashes: [BRIEF_ONE_HASH, BRIEF_TWO_HASH],
    minority_report_hashes: [MINORITY_HASH],
    gate_decision_ids: ["GD-0001", "GD-0002"],
    operation_ids: [...PARLIAMENT_OPERATION_IDS],
  });

  const manifest = readJson("web/src/generated/ui-client/route-manifest.json");
  const declared = new Map(
    manifest.routeTable.operations.map((operation) => [operation.operationId, operation]),
  );
  for (const operationId of PARLIAMENT_OPERATION_IDS) assert.ok(declared.has(operationId));

  const request = parliamentAdjudicationRequest({ adjudication_id: "ADJ-0001" });
  assert.equal(request.operationId, "getAdjudication");
  assert.equal(request.method, declared.get("getAdjudication").method);
  assert.equal(request.pathTemplate, declared.get("getAdjudication").path);
  assert.equal(request.url, "/api/v1/adjudications/ADJ-0001");
  assert.equal(Object.isFrozen(request), true);

  const sent = [];
  parliamentAdjudicationRequest({ adjudication_id: "ADJ-0002" }, (descriptor) => sent.push(descriptor));
  assert.equal(sent.length, 1);
  assert.equal(sent[0].url, "/api/v1/adjudications/ADJ-0002");

  const deliberation = parliamentDeliberationRequest({ run_spec: { run_spec_id: "RS-0001" } });
  assert.equal(deliberation.operationId, "createDeliberationRun");
  assert.equal(deliberation.method, "POST");
  assert.equal(deliberation.url, "/api/v1/deliberation-runs");

  assert.throws(
    () => parliamentAdjudicationRequest({ adjudication_id: "" }),
    errorCode("PARLIAMENT_INPUT_INVALID"),
  );
});

// --- independent_review ------------------------------------------------------

test("parliament_view: every finding code stands alone with a distinct reason", () => {
  const codes = Object.keys(PARLIAMENT_FINDING_CODES);
  assert.ok(codes.length >= 10);
  const reasons = new Set();
  for (const code of codes) {
    assert.match(code, /^[A-Z][A-Z0-9_]+$/u);
    assert.ok(PARLIAMENT_FINDING_CODES[code].length > 50, code);
    assert.ok(MODULE_SOURCE.includes(code), code);
    reasons.add(PARLIAMENT_FINDING_CODES[code]);
  }
  assert.equal(reasons.size, codes.length);

  const raised = (() => {
    try {
      validateParliamentInput({});
      return null;
    } catch (error) {
      return error;
    }
  })();
  assert.ok(raised instanceof ParliamentViewError);
  assert.equal(raised.reason, PARLIAMENT_FINDING_CODES.PARLIAMENT_INPUT_INVALID);
  assert.equal(Object.isFrozen(raised.context), true);
});
