/**
 * Deterministic fixtures for the U03 Evidence Parliament view suite.
 *
 * Every value is a literal.  No clock, no random source and no environment read,
 * so two runs of the same suite build byte-identical views.  Each factory takes a
 * shallow override object so a single adversarial field can be perturbed without
 * restating the whole record.
 */

export const ADJUDICATION_HASH =
  "sha256:7096b1ae7f753ee108ebef9d9d7a12de307ddc42705aba14b48499d314c774be";
export const BRIEF_ONE_HASH =
  "sha256:321c2c43dfd4bbe168196e0869e90ce737ba85707d4d7f1f8c66091e26ac9193";
export const BRIEF_TWO_HASH =
  "sha256:53a4d91768c4437c69d01b8981d3c59823940357aeb82a5ea1857754a1287e8d";
export const MINORITY_HASH =
  "sha256:ca70ae01ef56f40e4ef19a6ec6a064a0f8ab296a863b4b82d93a8a3a9e70db7c";

export const RUN_ID = "RUN-0001";

/** One brief assertion, overridable field by field. */
export const assertion = (overrides = {}) => ({
  assertion_id: "AS-0001",
  text: "The greenhouse trials report a consistent positive yield response.",
  evidence_ids: ["EV-0001", "EV-0002"],
  argument_node_ids: ["AN-0001"],
  scope_limitations: ["greenhouse only"],
  confidence: 0.6,
  ...overrides,
});

/** The defender brief the adjudication references. */
export const defenderBrief = (overrides = {}) => ({
  brief_id: "CB-0001",
  run_id: RUN_ID,
  round: 1,
  role: "defender",
  blind: true,
  context_manifest_id: "CM-0001",
  verdict_candidate: "SUPPORTED",
  assertions: [assertion()],
  strongest_counterargument: "No independent replication has been run outside the source lab.",
  conditions_that_change_verdict: ["a field trial contradicts the greenhouse effect"],
  missing_evidence: ["a pre-registered field replication"],
  schema_version: "4.0.0",
  brief_hash: BRIEF_ONE_HASH,
  created_at: "2026-01-02T00:00:00Z",
  ...overrides,
});

/** The prosecutor brief the adjudication references. */
export const prosecutorBrief = (overrides = {}) => ({
  brief_id: "CB-0002",
  run_id: RUN_ID,
  round: 1,
  role: "prosecutor",
  blind: true,
  context_manifest_id: "CM-0001",
  verdict_candidate: "UNDERDETERMINED",
  assertions: [
    assertion({
      assertion_id: "AS-0002",
      text: "The observed effect is confounded with irrigation scheduling.",
      confidence: 0.4,
    }),
  ],
  strongest_counterargument: "The effect survives the one irrigation-matched subgroup.",
  conditions_that_change_verdict: ["an irrigation-controlled trial removes the effect"],
  missing_evidence: ["an irrigation-matched design"],
  schema_version: "4.0.0",
  brief_hash: BRIEF_TWO_HASH,
  created_at: "2026-01-02T00:05:00Z",
  ...overrides,
});

/** The minority report the adjudication cites and the presentation must show. */
export const minorityReport = (overrides = {}) => ({
  minority_report_id: "MR-0001",
  run_id: RUN_ID,
  author_role: "method_auditor",
  minority_claim: "The confound is not ruled out and the verdict overstates support.",
  evidence_ids: ["EV-0003"],
  why_majority_may_be_wrong: "The irrigation covariate was never balanced across arms.",
  unresolved_test: "An irrigation-matched replication would discriminate the accounts.",
  expected_information_gain: 0.7,
  preservation_status: "required",
  created_at: "2026-01-02T00:10:00Z",
  report_hash: MINORITY_HASH,
  ...overrides,
});

/** The adjudication whose gate decisions carry the verdict. */
export const adjudication = (overrides = {}) => ({
  adjudication_id: "ADJ-0001",
  run_id: RUN_ID,
  hypothesis_id: "HYP-0001",
  gate_decision_ids: ["GD-0001", "GD-0002"],
  brief_ids: ["CB-0001", "CB-0002"],
  cross_examination_ids: ["CX-0001"],
  minority_report_ids: ["MR-0001"],
  verdict: "CONDITIONAL",
  scope_narrowing: ["holds for the greenhouse regime only"],
  strongest_support_id: "EV-0001",
  strongest_counterevidence_id: "EV-0003",
  unresolved_issue_ids: ["UI-0001"],
  promotion_recommendation: "CANDIDATE",
  rationale: "The gate decisions support a conditional verdict pending an irrigation control.",
  deterministic_gate_override_attempted: false,
  created_at: "2026-01-02T00:15:00Z",
  adjudication_hash: ADJUDICATION_HASH,
  ...overrides,
});

/** The rendering the caller proposes: gate basis, every brief, every citation. */
export const presentation = (overrides = {}) => ({
  verdict_basis: "ADJUDICATION_GATE_DECISIONS",
  brief_ids: ["CB-0001", "CB-0002"],
  minority_report_ids: ["MR-0001"],
  ...overrides,
});

/** A complete, well-formed Parliament view input. */
export const parliamentInput = (overrides = {}) => ({
  adjudication: adjudication(),
  briefs: [defenderBrief(), prosecutorBrief()],
  minority_reports: [minorityReport()],
  presentation: presentation(),
  ...overrides,
});
