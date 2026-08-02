/**
 * U03 Evidence Parliament read model.
 *
 * An adjudication is not a vote.  The verdict this view displays is the one the
 * adjudication carries, derived from its gate decisions; a presentation that
 * declares a brief-majority or vote-tally basis is refused rather than rendered,
 * and a minority report the adjudication references is a first-class element of
 * the rendering.  Dropping it fails with `MINORITY_REPORT_HIDDEN` instead of
 * producing a cleaner-looking panel.
 *
 * Declaring sources:
 *   - `schemas/adjudication.schema.json` (verdict and promotion vocabularies)
 *   - `schemas/council-brief.schema.json` (role and verdict-candidate vocabulary)
 *   - `schemas/minority-report.schema.json` (preservation-status vocabulary)
 *   - `web/src/generated/ui-client/index.mjs` (the only route binding allowed)
 *
 * The module reads no clock, no random source, no environment and no file.
 */

import { types as utilTypes } from "node:util";

import {
  OPERATIONS,
  createDeliberationRun,
  getAdjudication,
} from "../../generated/ui-client/index.mjs";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;

export const PARLIAMENT_VIEW_VERSION = "4.0.0-u03.1";

/** `schemas/adjudication.schema.json` `verdict`. */
export const PARLIAMENT_VERDICTS = OBJECT_FREEZE([
  "ENTAILED",
  "SUPPORTED",
  "CONDITIONAL",
  "MIXED",
  "CONTRADICTED",
  "UNDERDETERMINED",
  "UNTESTABLE",
]);

/** `schemas/adjudication.schema.json` `promotion_recommendation`. */
export const PROMOTION_RECOMMENDATIONS = OBJECT_FREEZE([
  "BLOCK",
  "INBOX",
  "CANDIDATE",
  "LITERATURE_GROUNDED",
  "VALIDATION_SCREENED",
  "EMPIRICALLY_TESTED",
  "REPLICATED",
]);

/** `schemas/council-brief.schema.json` `role`. */
export const BRIEF_ROLES = OBJECT_FREEZE([
  "defender",
  "prosecutor",
  "method_auditor",
  "scope_auditor",
  "inductivist",
  "deductivist",
  "causal_auditor",
  "novelty_examiner",
  "abductive_mediator",
  "bias_auditor",
  "other",
]);

/** `schemas/minority-report.schema.json` `preservation_status`. */
export const MINORITY_PRESERVATION_STATUSES = OBJECT_FREEZE([
  "required",
  "preserved",
  "superseded_by_new_evidence",
]);

/** The only verdict basis a Parliament rendering may declare. */
export const VERDICT_BASIS = "ADJUDICATION_GATE_DECISIONS";

/** Presentation bases that would restate a gate decision as a vote. */
export const REFUSED_VERDICT_BASES = OBJECT_FREEZE([
  "BRIEF_MAJORITY",
  "ROLE_MAJORITY",
  "VOTE_TALLY",
  "WEIGHTED_VOTE",
  "CONSENSUS_SCORE",
]);

/** Operation ids from the generated client this view is permitted to bind. */
export const PARLIAMENT_OPERATION_IDS = OBJECT_FREEZE([
  "getAdjudication",
  "createDeliberationRun",
]);

export const PARLIAMENT_FINDING_CODES = OBJECT_FREEZE({
  PARLIAMENT_INPUT_INVALID:
    "The adjudication, brief, or minority-report payload is not a plain data object carrying exactly the field set its canonical schema declares, so no element could be read without guessing what the caller meant.",
  UNKNOWN_VERDICT:
    "The adjudication or a brief declares a verdict outside the canonical seven-value vocabulary, and displaying it would present a state the Parliament contract does not define.",
  UNKNOWN_PROMOTION_RECOMMENDATION:
    "The adjudication declares a promotion recommendation outside the canonical vocabulary, so the rendered recommendation could not be traced to a declared promotion level.",
  UNKNOWN_BRIEF_ROLE:
    "A council brief declares a role outside the canonical role vocabulary, so the rendering could not show which adversarial position the brief actually represents.",
  UNKNOWN_PRESERVATION_STATUS:
    "A minority report declares a preservation status outside the canonical vocabulary, so the view cannot state whether the dissent is still required to be preserved.",
  MINORITY_REPORT_HIDDEN:
    "The adjudication references a minority report that the rendering does not present, and a Parliament panel that drops recorded dissent misrepresents the deliberation it claims to show.",
  MINORITY_REPORT_UNKNOWN:
    "The rendering presents a minority report identifier the adjudication does not reference, so the panel would attribute dissent to a deliberation that never recorded it.",
  MINORITY_REPORT_RECORD_MISSING:
    "A referenced minority report has no supplied record, so the rendering could only show an identifier while the dissent itself, its unresolved test and its evidence stay invisible.",
  MAJORITY_VOTE_PRESENTATION:
    "The rendering declares a vote, tally, or majority basis for the verdict, but a gate decision is not a poll of briefs and presenting it as one would invent an adjudication procedure.",
  BRIEF_SET_MISMATCH:
    "The supplied briefs are not exactly the briefs the adjudication references, so the panel would show a deliberation record that is not the one the verdict was drawn from.",
  GATE_OVERRIDE_HIDDEN:
    "The adjudication records that a deterministic gate override was attempted, and a rendering that suppresses that fact would hide the most decision-relevant integrity signal it carries.",
  OPERATION_NOT_DECLARED:
    "The Parliament view may only bind operations the generated OpenAPI client exports, and the requested operation id is not one of them, so the request would target an undeclared route.",
});

export class ParliamentViewError extends Error {
  constructor(code, detail, context = {}) {
    super(`${code}: ${detail}`);
    this.name = "ParliamentViewError";
    this.code = code;
    this.detail = detail;
    this.reason = PARLIAMENT_FINDING_CODES[code];
    this.context = OBJECT_FREEZE({ ...context });
  }
}

const fail = (code, detail, context = {}) => {
  if (!OBJECT_HAS_OWN(PARLIAMENT_FINDING_CODES, code)) {
    throw new Error(`undeclared Parliament finding code ${code}`);
  }
  throw new ParliamentViewError(code, detail, context);
};

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

const CODE = "PARLIAMENT_INPUT_INVALID";

const isPlainDataObject = (value) =>
  value !== null &&
  typeof value === "object" &&
  !ARRAY_IS_ARRAY(value) &&
  !IS_PROXY(value) &&
  (OBJECT_GET_PROTOTYPE_OF(value) === PLAIN_OBJECT_PROTOTYPE ||
    OBJECT_GET_PROTOTYPE_OF(value) === null);

const requireFields = (value, label, fields, code = CODE) => {
  if (!isPlainDataObject(value)) fail(code, `${label} must be a plain data object`);
  const allowed = new Set(fields);
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (typeof key !== "string" || !allowed.has(key)) {
      fail(code, `${label} carries the unsupported field ${String(key)}`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor === undefined || !descriptor.enumerable || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail(code, `${label}.${String(key)} must be an enumerable data property`);
    }
  }
  for (const field of fields) {
    if (!OBJECT_HAS_OWN(value, field)) fail(code, `${label}.${field} is required`);
  }
  return value;
};

const readValue = (object, key) => OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(object, key).value;

const requireArray = (value, label, code = CODE) => {
  if (
    !ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== Array.prototype
  ) {
    fail(code, `${label} must be a plain dense array`);
  }
  const result = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (descriptor === undefined || !descriptor.enumerable || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail(code, `${label} contains a sparse or accessor-backed element`);
    }
    result.push(descriptor.value);
  }
  return result;
};

const requireString = (value, label, code = CODE) => {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.normalize("NFC") !== value ||
    /\p{Cc}/u.test(value)
  ) {
    fail(code, `${label} must be a non-empty NFC string without control characters`);
  }
  return value;
};

const requireStringArray = (value, label, code = CODE) => {
  const values = requireArray(value, label, code).map((entry, index) =>
    requireString(entry, `${label}[${index}]`, code),
  );
  if (new Set(values).size !== values.length) fail(code, `${label} contains duplicate entries`);
  return values;
};

/** Order-independent comparison of two identifier sets. */
const canonical = (values) => JSON.stringify([...values].sort());

const requireNullableString = (value, label) =>
  value === null ? null : requireString(value, label);

const requireHash = (value, label) => {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    fail(CODE, `${label} must match sha256:<64 lowercase hex characters>`);
  }
  return value;
};

const requireMember = (value, label, vocabulary, code) => {
  const text = requireString(value, label);
  if (!vocabulary.includes(text)) {
    fail(code, `${label} is outside the canonical vocabulary`, { value: text });
  }
  return text;
};

const ADJUDICATION_FIELDS = OBJECT_FREEZE([
  "adjudication_id",
  "run_id",
  "hypothesis_id",
  "gate_decision_ids",
  "brief_ids",
  "cross_examination_ids",
  "minority_report_ids",
  "verdict",
  "scope_narrowing",
  "strongest_support_id",
  "strongest_counterevidence_id",
  "unresolved_issue_ids",
  "promotion_recommendation",
  "rationale",
  "deterministic_gate_override_attempted",
  "created_at",
  "adjudication_hash",
]);
const BRIEF_FIELDS = OBJECT_FREEZE([
  "brief_id",
  "run_id",
  "round",
  "role",
  "blind",
  "context_manifest_id",
  "verdict_candidate",
  "assertions",
  "strongest_counterargument",
  "conditions_that_change_verdict",
  "missing_evidence",
  "schema_version",
  "brief_hash",
  "created_at",
]);
const ASSERTION_FIELDS = OBJECT_FREEZE([
  "assertion_id",
  "text",
  "evidence_ids",
  "argument_node_ids",
  "scope_limitations",
  "confidence",
]);
const MINORITY_FIELDS = OBJECT_FREEZE([
  "minority_report_id",
  "run_id",
  "author_role",
  "minority_claim",
  "evidence_ids",
  "why_majority_may_be_wrong",
  "unresolved_test",
  "expected_information_gain",
  "preservation_status",
  "created_at",
  "report_hash",
]);
const PRESENTATION_FIELDS = OBJECT_FREEZE([
  "verdict_basis",
  "brief_ids",
  "minority_report_ids",
]);
const INPUT_FIELDS = OBJECT_FREEZE([
  "adjudication",
  "briefs",
  "minority_reports",
  "presentation",
]);

const normalizeAdjudication = (candidate) => {
  const adjudication = requireFields(candidate, "Adjudication", ADJUDICATION_FIELDS);
  const briefIds = requireStringArray(readValue(adjudication, "brief_ids"), "brief_ids");
  if (briefIds.length === 0) fail(CODE, "brief_ids must reference at least one council brief");
  const gateIds = requireStringArray(
    readValue(adjudication, "gate_decision_ids"),
    "gate_decision_ids",
  );
  if (gateIds.length === 0) fail(CODE, "gate_decision_ids must reference at least one decision");
  const override = readValue(adjudication, "deterministic_gate_override_attempted");
  if (typeof override !== "boolean") {
    fail(CODE, "deterministic_gate_override_attempted must be a boolean");
  }
  return {
    adjudication_id: requireString(readValue(adjudication, "adjudication_id"), "adjudication_id"),
    run_id: requireString(readValue(adjudication, "run_id"), "run_id"),
    hypothesis_id: requireString(readValue(adjudication, "hypothesis_id"), "hypothesis_id"),
    gate_decision_ids: gateIds,
    brief_ids: briefIds,
    cross_examination_ids: requireStringArray(
      readValue(adjudication, "cross_examination_ids"),
      "cross_examination_ids",
    ),
    minority_report_ids: requireStringArray(
      readValue(adjudication, "minority_report_ids"),
      "minority_report_ids",
    ),
    verdict: requireMember(
      readValue(adjudication, "verdict"),
      "verdict",
      PARLIAMENT_VERDICTS,
      "UNKNOWN_VERDICT",
    ),
    scope_narrowing: requireStringArray(
      readValue(adjudication, "scope_narrowing"),
      "scope_narrowing",
    ),
    strongest_support_id: requireNullableString(
      readValue(adjudication, "strongest_support_id"),
      "strongest_support_id",
    ),
    strongest_counterevidence_id: requireNullableString(
      readValue(adjudication, "strongest_counterevidence_id"),
      "strongest_counterevidence_id",
    ),
    unresolved_issue_ids: requireStringArray(
      readValue(adjudication, "unresolved_issue_ids"),
      "unresolved_issue_ids",
    ),
    promotion_recommendation: requireMember(
      readValue(adjudication, "promotion_recommendation"),
      "promotion_recommendation",
      PROMOTION_RECOMMENDATIONS,
      "UNKNOWN_PROMOTION_RECOMMENDATION",
    ),
    rationale: requireString(readValue(adjudication, "rationale"), "rationale"),
    deterministic_gate_override_attempted: override,
    created_at: requireString(readValue(adjudication, "created_at"), "created_at"),
    adjudication_hash: requireHash(
      readValue(adjudication, "adjudication_hash"),
      "adjudication_hash",
    ),
  };
};

const normalizeAssertion = (candidate, briefLabel, index) => {
  const label = `${briefLabel}.assertions[${index}]`;
  const assertion = requireFields(candidate, label, ASSERTION_FIELDS);
  const confidence = readValue(assertion, "confidence");
  if (typeof confidence !== "number" || !Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    fail(CODE, `${label}.confidence must be a finite number within the closed unit interval`);
  }
  return {
    assertion_id: requireString(readValue(assertion, "assertion_id"), `${label}.assertion_id`),
    text: requireString(readValue(assertion, "text"), `${label}.text`),
    evidence_ids: requireStringArray(readValue(assertion, "evidence_ids"), `${label}.evidence_ids`),
    argument_node_ids: requireStringArray(
      readValue(assertion, "argument_node_ids"),
      `${label}.argument_node_ids`,
    ),
    scope_limitations: requireStringArray(
      readValue(assertion, "scope_limitations"),
      `${label}.scope_limitations`,
    ),
    confidence,
  };
};

const normalizeBrief = (candidate, index) => {
  const label = `briefs[${index}]`;
  const brief = requireFields(candidate, label, BRIEF_FIELDS);
  const round = readValue(brief, "round");
  if (!Number.isSafeInteger(round) || round < 1) {
    fail(CODE, `${label}.round must be a safe integer of at least one`);
  }
  const blind = readValue(brief, "blind");
  if (typeof blind !== "boolean") fail(CODE, `${label}.blind must be a boolean`);
  const assertions = requireArray(readValue(brief, "assertions"), `${label}.assertions`).map(
    (assertion, position) => normalizeAssertion(assertion, label, position),
  );
  if (assertions.length === 0) fail(CODE, `${label}.assertions must carry at least one assertion`);
  const conditions = requireStringArray(
    readValue(brief, "conditions_that_change_verdict"),
    `${label}.conditions_that_change_verdict`,
  );
  if (conditions.length === 0) {
    fail(CODE, `${label}.conditions_that_change_verdict must carry at least one condition`);
  }
  return {
    brief_id: requireString(readValue(brief, "brief_id"), `${label}.brief_id`),
    run_id: requireString(readValue(brief, "run_id"), `${label}.run_id`),
    round,
    role: requireMember(readValue(brief, "role"), `${label}.role`, BRIEF_ROLES, "UNKNOWN_BRIEF_ROLE"),
    blind,
    context_manifest_id: requireString(
      readValue(brief, "context_manifest_id"),
      `${label}.context_manifest_id`,
    ),
    verdict_candidate: requireMember(
      readValue(brief, "verdict_candidate"),
      `${label}.verdict_candidate`,
      PARLIAMENT_VERDICTS,
      "UNKNOWN_VERDICT",
    ),
    assertions,
    strongest_counterargument: requireString(
      readValue(brief, "strongest_counterargument"),
      `${label}.strongest_counterargument`,
    ),
    conditions_that_change_verdict: conditions,
    missing_evidence: requireStringArray(
      readValue(brief, "missing_evidence"),
      `${label}.missing_evidence`,
    ),
    schema_version: requireString(readValue(brief, "schema_version"), `${label}.schema_version`),
    brief_hash: requireHash(readValue(brief, "brief_hash"), `${label}.brief_hash`),
    created_at: requireString(readValue(brief, "created_at"), `${label}.created_at`),
  };
};

const normalizeMinorityReport = (candidate, index) => {
  const label = `minority_reports[${index}]`;
  const report = requireFields(candidate, label, MINORITY_FIELDS);
  const evidenceIds = requireStringArray(
    readValue(report, "evidence_ids"),
    `${label}.evidence_ids`,
  );
  if (evidenceIds.length === 0) {
    fail(CODE, `${label}.evidence_ids must carry at least one evidence identifier`);
  }
  const gain = readValue(report, "expected_information_gain");
  if (typeof gain !== "number" || !Number.isFinite(gain) || gain < 0) {
    fail(CODE, `${label}.expected_information_gain must be a finite non-negative number`);
  }
  return {
    minority_report_id: requireString(
      readValue(report, "minority_report_id"),
      `${label}.minority_report_id`,
    ),
    run_id: requireString(readValue(report, "run_id"), `${label}.run_id`),
    author_role: requireString(readValue(report, "author_role"), `${label}.author_role`),
    minority_claim: requireString(readValue(report, "minority_claim"), `${label}.minority_claim`),
    evidence_ids: evidenceIds,
    why_majority_may_be_wrong: requireString(
      readValue(report, "why_majority_may_be_wrong"),
      `${label}.why_majority_may_be_wrong`,
    ),
    unresolved_test: requireString(readValue(report, "unresolved_test"), `${label}.unresolved_test`),
    expected_information_gain: gain,
    preservation_status: requireMember(
      readValue(report, "preservation_status"),
      `${label}.preservation_status`,
      MINORITY_PRESERVATION_STATUSES,
      "UNKNOWN_PRESERVATION_STATUS",
    ),
    created_at: requireString(readValue(report, "created_at"), `${label}.created_at`),
    report_hash: requireHash(readValue(report, "report_hash"), `${label}.report_hash`),
  };
};

const normalizePresentation = (candidate) => {
  const presentation = requireFields(candidate, "presentation", PRESENTATION_FIELDS);
  const basis = requireString(readValue(presentation, "verdict_basis"), "presentation.verdict_basis");
  if (REFUSED_VERDICT_BASES.includes(basis)) {
    fail("MAJORITY_VOTE_PRESENTATION", "a gate decision may not be presented as a vote", {
      verdict_basis: basis,
    });
  }
  if (basis !== VERDICT_BASIS) {
    fail("MAJORITY_VOTE_PRESENTATION", "the verdict basis is not the declared adjudication basis", {
      verdict_basis: basis,
      expected: VERDICT_BASIS,
    });
  }
  return {
    verdict_basis: basis,
    brief_ids: requireStringArray(readValue(presentation, "brief_ids"), "presentation.brief_ids"),
    minority_report_ids: requireStringArray(
      readValue(presentation, "minority_report_ids"),
      "presentation.minority_report_ids",
    ),
  };
};

/** Validate the deliberation record and the rendering the caller proposes. */
export function validateParliamentInput(candidate) {
  const input = requireFields(candidate, "ParliamentViewInput", INPUT_FIELDS);
  const adjudication = normalizeAdjudication(readValue(input, "adjudication"));
  const briefs = requireArray(readValue(input, "briefs"), "briefs").map(normalizeBrief);
  const reports = requireArray(readValue(input, "minority_reports"), "minority_reports").map(
    normalizeMinorityReport,
  );
  const presentation = normalizePresentation(readValue(input, "presentation"));

  const briefIds = briefs.map((brief) => brief.brief_id);
  if (new Set(briefIds).size !== briefIds.length) fail(CODE, "briefs contains duplicate identifiers");
  const referenced = [...adjudication.brief_ids].sort();
  if (canonical(briefIds) !== canonical(referenced)) {
    fail("BRIEF_SET_MISMATCH", "the supplied briefs are not the briefs the adjudication cites", {
      expected: referenced,
      observed: [...briefIds].sort(),
    });
  }
  if (canonical(presentation.brief_ids) !== canonical(referenced)) {
    fail("BRIEF_SET_MISMATCH", "the rendering does not present every cited council brief", {
      expected: referenced,
      observed: [...presentation.brief_ids].sort(),
    });
  }

  const reportIds = reports.map((report) => report.minority_report_id);
  if (new Set(reportIds).size !== reportIds.length) {
    fail(CODE, "minority_reports contains duplicate identifiers");
  }
  for (const id of adjudication.minority_report_ids) {
    if (!reportIds.includes(id)) {
      fail("MINORITY_REPORT_RECORD_MISSING", "a cited minority report carries no record", {
        minority_report_id: id,
      });
    }
    if (!presentation.minority_report_ids.includes(id)) {
      fail("MINORITY_REPORT_HIDDEN", "a cited minority report is absent from the rendering", {
        minority_report_id: id,
      });
    }
  }
  for (const id of presentation.minority_report_ids) {
    if (!adjudication.minority_report_ids.includes(id)) {
      fail("MINORITY_REPORT_UNKNOWN", "the rendering presents an uncited minority report", {
        minority_report_id: id,
      });
    }
  }
  for (const report of reports) {
    if (!adjudication.minority_report_ids.includes(report.minority_report_id)) {
      fail("MINORITY_REPORT_UNKNOWN", "a supplied minority report is not cited by the adjudication", {
        minority_report_id: report.minority_report_id,
      });
    }
    if (report.run_id !== adjudication.run_id) {
      fail(CODE, "a minority report belongs to a different run than the adjudication");
    }
  }
  for (const brief of briefs) {
    if (brief.run_id !== adjudication.run_id) {
      fail(CODE, "a council brief belongs to a different run than the adjudication");
    }
  }
  return deepFreeze({ adjudication, briefs, minority_reports: reports, presentation });
}

const minoritySection = (input) => {
  const cited = input.adjudication.minority_report_ids;
  const byId = new Map(input.minority_reports.map((report) => [report.minority_report_id, report]));
  return {
    id: "minority-report",
    title: "Minority report",
    state: cited.length ? "PRESERVED" : "NONE_RECORDED",
    visible: true,
    items: cited.map((id) => {
      const report = byId.get(id);
      return {
        minority_report_id: report.minority_report_id,
        author_role: report.author_role,
        minority_claim: report.minority_claim,
        why_majority_may_be_wrong: report.why_majority_may_be_wrong,
        unresolved_test: report.unresolved_test,
        evidence_ids: [...report.evidence_ids],
        expected_information_gain: report.expected_information_gain,
        preservation_status: report.preservation_status,
        report_hash: report.report_hash,
      };
    }),
  };
};

/** Build the Parliament read model with dissent as a first-class element. */
export function buildParliamentView(candidate) {
  const input = validateParliamentInput(candidate);
  const adjudication = input.adjudication;
  const minority = minoritySection(input);
  const briefs = input.briefs.map((brief) => ({
    brief_id: brief.brief_id,
    round: brief.round,
    role: brief.role,
    blind: brief.blind,
    verdict_candidate: brief.verdict_candidate,
    assertion_count: brief.assertions.length,
    assertions: brief.assertions,
    strongest_counterargument: brief.strongest_counterargument,
    conditions_that_change_verdict: [...brief.conditions_that_change_verdict],
    missing_evidence: [...brief.missing_evidence],
    brief_hash: brief.brief_hash,
  }));
  return deepFreeze({
    kind: "EpistemicFoundryParliamentView",
    version: PARLIAMENT_VIEW_VERSION,
    heading: "Evidence Parliament",
    parliament_identity: {
      adjudication_id: adjudication.adjudication_id,
      run_id: adjudication.run_id,
      hypothesis_id: adjudication.hypothesis_id,
      created_at: adjudication.created_at,
    },
    source_receipt: {
      adjudication_hash: adjudication.adjudication_hash,
      brief_hashes: briefs.map((brief) => brief.brief_hash),
      minority_report_hashes: minority.items.map((item) => item.report_hash),
      gate_decision_ids: [...adjudication.gate_decision_ids],
      operation_ids: [...PARLIAMENT_OPERATION_IDS],
    },
    verdict: {
      value: adjudication.verdict,
      basis: VERDICT_BASIS,
      gate_decision_ids: [...adjudication.gate_decision_ids],
      rationale: adjudication.rationale,
      scope_narrowing: [...adjudication.scope_narrowing],
      is_vote: false,
    },
    promotion: {
      recommendation: adjudication.promotion_recommendation,
      status: "RECOMMENDATION_NOT_DECISION",
    },
    counter_evidence: {
      strongest_support_id: adjudication.strongest_support_id,
      strongest_counterevidence_id: adjudication.strongest_counterevidence_id,
      unresolved_issue_ids: [...adjudication.unresolved_issue_ids],
      cross_examination_ids: [...adjudication.cross_examination_ids],
    },
    gate_integrity: {
      deterministic_gate_override_attempted:
        adjudication.deterministic_gate_override_attempted,
      state: adjudication.deterministic_gate_override_attempted
        ? "OVERRIDE_ATTEMPT_RECORDED"
        : "NO_OVERRIDE_ATTEMPT",
    },
    briefs,
    minority_report: minority,
    sections: [
      {
        id: "verdict-and-basis",
        title: "Verdict and its basis",
        state: "VERIFIED",
        visible: true,
      },
      minority,
      {
        id: "counter-evidence-and-unresolved",
        title: "Counter-evidence and unresolved issues",
        state:
          adjudication.strongest_counterevidence_id !== null ||
          adjudication.unresolved_issue_ids.length
            ? "POPULATED"
            : "NONE_RECORDED",
        visible: true,
      },
      {
        id: "council-briefs",
        title: "Council briefs",
        state: briefs.length ? "POPULATED" : "EMPTY_CONFIRMED",
        visible: true,
      },
      {
        id: "gate-integrity",
        title: "Gate integrity",
        state: adjudication.deterministic_gate_override_attempted
          ? "OVERRIDE_ATTEMPT_RECORDED"
          : "NO_OVERRIDE_ATTEMPT",
        visible: true,
      },
    ],
  });
}

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const displayNullable = (value) => (value === null ? "not recorded" : String(value));

const renderList = (items, emptyText, renderItem) =>
  items.length
    ? `<ol>${items.map((item) => `<li>${renderItem(item)}</li>`).join("")}</ol>`
    : `<p class="parliament-empty">${escapeHtml(emptyText)}</p>`;

/** Render the Parliament panel; the minority section always precedes the briefs. */
export function renderParliamentPanel(candidate) {
  const view = buildParliamentView(candidate);
  return [
    `<main class="parliament" data-parliament-version="${escapeHtml(view.version)}">`,
    `<header><h1>${escapeHtml(view.heading)}</h1><p>${escapeHtml(
      view.parliament_identity.hypothesis_id,
    )}</p></header>`,
    '<section class="parliament-verdict" data-section="verdict-and-basis">',
    `<h2>Verdict and its basis</h2><p data-verdict="${escapeHtml(
      view.verdict.value,
    )}">${escapeHtml(view.verdict.value)}</p>`,
    `<p data-verdict-basis="${escapeHtml(view.verdict.basis)}">Basis: ${escapeHtml(
      view.verdict.basis,
    )}; this is a gate decision, not a vote.</p>`,
    `<p>${escapeHtml(view.verdict.rationale)}</p>`,
    `<p>Promotion recommendation ${escapeHtml(
      view.promotion.recommendation,
    )} (${escapeHtml(view.promotion.status)})</p></section>`,
    `<section class="parliament-minority" data-section="minority-report" data-state="${escapeHtml(
      view.minority_report.state,
    )}"><h2>Minority report</h2>`,
    renderList(
      view.minority_report.items,
      "No minority report was recorded for this adjudication.",
      (item) =>
        [
          `<strong>${escapeHtml(item.minority_claim)}</strong>`,
          ` <span>${escapeHtml(item.author_role)}</span>`,
          ` <p>${escapeHtml(item.why_majority_may_be_wrong)}</p>`,
          `<p>Unresolved test: ${escapeHtml(item.unresolved_test)}</p>`,
          `<p>${escapeHtml(item.preservation_status)}</p>`,
        ].join(""),
    ),
    "</section>",
    '<section class="parliament-counter" data-section="counter-evidence-and-unresolved">',
    "<h2>Counter-evidence and unresolved issues</h2>",
    `<dl><dt>Strongest counter-evidence</dt><dd>${escapeHtml(
      displayNullable(view.counter_evidence.strongest_counterevidence_id),
    )}</dd>`,
    `<dt>Strongest support</dt><dd>${escapeHtml(
      displayNullable(view.counter_evidence.strongest_support_id),
    )}</dd></dl>`,
    renderList(view.counter_evidence.unresolved_issue_ids, "No unresolved issue was recorded.", (id) =>
      escapeHtml(id),
    ),
    "</section>",
    '<section class="parliament-briefs" data-section="council-briefs"><h2>Council briefs</h2>',
    renderList(
      view.briefs,
      "No council brief is displayable.",
      (brief) =>
        `<strong>${escapeHtml(brief.role)}</strong> <span>${escapeHtml(
          brief.verdict_candidate,
        )}</span> <p>${escapeHtml(brief.strongest_counterargument)}</p>`,
    ),
    "</section>",
    `<section class="parliament-integrity" data-section="gate-integrity" data-state="${escapeHtml(
      view.gate_integrity.state,
    )}"><h2>Gate integrity</h2><p>${escapeHtml(view.gate_integrity.state)}</p></section></main>`,
  ].join("");
}

const requireDeclaredOperation = (operationId) => {
  if (!PARLIAMENT_OPERATION_IDS.includes(operationId) || !OBJECT_HAS_OWN(OPERATIONS, operationId)) {
    fail("OPERATION_NOT_DECLARED", `${operationId} is not a Parliament-bindable operation`, {
      operation_id: operationId,
    });
  }
};

/** Bind `GET /adjudications/{id}` through the generated client only. */
export function parliamentAdjudicationRequest({ adjudication_id: adjudicationId }, transport) {
  requireDeclaredOperation("getAdjudication");
  requireString(adjudicationId, "adjudication_id");
  return getAdjudication({ path: { adjudication_id: adjudicationId } }, transport);
}

/** Bind `POST /deliberation-runs` (plan and execute) through the client. */
export function parliamentDeliberationRequest({ run_spec: runSpec }, transport) {
  requireDeclaredOperation("createDeliberationRun");
  if (!isPlainDataObject(runSpec)) fail(CODE, "run_spec must be a plain data object");
  return createDeliberationRun({ body: runSpec }, transport);
}
