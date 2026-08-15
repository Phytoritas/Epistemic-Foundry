/**
 * Deterministic fixtures for the U03 Aporia Engine view suite.
 *
 * Every value is a literal.  No clock, no random source and no environment read,
 * so two runs of the same suite build byte-identical views.  Each factory takes a
 * shallow override object so a single adversarial field can be perturbed.
 */

export const GRAPH_HASH =
  "sha256:753e780e02eb9e32c3b3f0738daa4b998b4c1f62eeadd45bc9e903632d5f3b9f";
export const RUN_ID = "RUN-0001";

const scopeVector = () => ({
  domain: null,
  population: null,
  entity_type: null,
  entity_subtype: null,
  unit_of_analysis: null,
  setting: "greenhouse",
  geography: null,
  jurisdiction: null,
  language: null,
  lifecycle_stage: null,
  spatial_scale: null,
  temporal_scale: null,
  time_period: null,
  measurement_time: null,
  intervention_or_exposure: null,
  comparator: null,
  inclusion_criteria: [],
  exclusion_criteria: [],
  conditions: {},
  domain_extensions: {},
});

/** One argument node, overridable field by field. */
export const node = (overrides = {}) => ({
  argument_node_id: "AN-0001",
  node_type: "premise",
  statement: "The greenhouse trials report a positive yield response.",
  evidence_ids: ["EV-0001"],
  scope: scopeVector(),
  status: "accepted",
  ...overrides,
});

/** One argument edge, overridable field by field. */
export const edge = (overrides = {}) => ({
  edge_id: "AE-0001",
  from_id: "AN-0001",
  to_id: "AN-0003",
  edge_type: "deductively_implies",
  rule_ref: "modus_ponens",
  confidence: null,
  ...overrides,
});

/**
 * A graph carrying every edge class the engine partitions:
 *   - AN-0001 accepted premise -> AN-0003 conclusion by a sound strict inference,
 *   - AN-0002 accepted assumption declared through a depends_on_assumption edge,
 *   - AN-0004 unresolved objection rebutting the conclusion (a contradiction),
 *   - one hidden assumption (AN-0002) and one unresolved objection (AN-0004).
 */
export const argumentGraph = (overrides = {}) => ({
  argument_graph_id: "AG-0001",
  run_id: RUN_ID,
  hypothesis_id: "HYP-0001",
  nodes: [
    node(),
    node({
      argument_node_id: "AN-0002",
      node_type: "assumption",
      statement: "Irrigation was held constant across the arms.",
      status: "accepted",
    }),
    node({
      argument_node_id: "AN-0003",
      node_type: "conclusion",
      statement: "Elevated CO2 raises tomato yield in this regime.",
      status: "asserted",
    }),
    node({
      argument_node_id: "AN-0004",
      node_type: "objection",
      statement: "The effect may be confounded with irrigation scheduling.",
      status: "unresolved",
    }),
  ],
  edges: [
    edge(),
    edge({
      edge_id: "AE-0002",
      from_id: "AN-0002",
      to_id: "AN-0003",
      edge_type: "depends_on_assumption",
      rule_ref: null,
    }),
    edge({
      edge_id: "AE-0003",
      from_id: "AN-0004",
      to_id: "AN-0003",
      edge_type: "rebuts",
      rule_ref: null,
      confidence: 0.4,
    }),
  ],
  hidden_assumption_ids: ["AN-0002"],
  unresolved_objection_ids: ["AN-0004"],
  proof_trace_artifact_id: "PT-0001",
  graph_hash: GRAPH_HASH,
  created_at: "2026-01-02T00:00:00Z",
  ...overrides,
});

/** The rendering the caller proposes: open questions shown, classes declared. */
export const presentation = (overrides = {}) => ({
  resolution_claim: "OPEN_QUESTIONS_REMAIN",
  open_question_ids: ["AN-0002", "AN-0004"],
  contradiction_classes: ["attacks", "competes_with", "falsified_by", "rebuts", "undercuts"],
  ...overrides,
});

/** A complete, well-formed Aporia view input. */
export const aporiaInput = (overrides = {}) => ({
  graph: argumentGraph(),
  presentation: presentation(),
  ...overrides,
});
