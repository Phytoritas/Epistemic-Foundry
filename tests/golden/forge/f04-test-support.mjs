import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { openContentAddressedArtifactStore } from "../../../packages/foundry-kernel/src/artifacts/content-addressed-artifact-store.mjs";
import {
  CLASSIFIER_VERSION,
  classificationInputHash,
  evaluateEpistemicWork,
  materializeClassificationArtifact,
} from "../../../packages/foundry-kernel/src/forge/classifier/index.mjs";
import {
  compileForgePlan,
  reduceForgeTransition,
  replayForgeTransitionEvents,
  sealForgeSessionState,
  sealPhaseArtifactSet,
  sha256ForgeJson,
} from "../../../packages/foundry-kernel/src/forge/fsm/index.mjs";
import { admitForgeTransition } from "../../../packages/foundry-kernel/src/forge/gates/index.mjs";

const GOLDEN_FIXTURE_URL = new URL("./f04_forge_golden_flows.json", import.meta.url);
const ADJUDICATION_SCHEMA_URL = new URL(
  "../../../schemas/adjudication.schema.json",
  import.meta.url,
);

const CLASSIFICATION_SCHEMA_REF = "schemas/epistemic-work-classification.schema.json";
const PHASE_SET_SCHEMA_REF = "schemas/phase-artifact-set.schema.json";
const RESULT_SCHEMA_REF = "schemas/result-envelope.schema.json";
const ADJUDICATION_SCHEMA_REF = "schemas/adjudication.schema.json";

const FIXED_CLASSIFIED_AT = "2026-07-29T03:00:00.000Z";
const FIXED_ARTIFACT_AT = "2026-07-29T03:01:00.000Z";
const REPOSITORY_ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const VALIDATED_CASES = new Set();

const readJson = (url) => JSON.parse(readFileSync(url, "utf8"));

export const GOLDEN_FLOW_DEFINITIONS = Object.freeze(
  readJson(GOLDEN_FIXTURE_URL).cases.map((row) => Object.freeze(structuredClone(row))),
);

const ADJUDICATION_SCHEMA = readJson(ADJUDICATION_SCHEMA_URL);

const artifactMetadata = ({
  artifactId,
  artifactType,
  receiptId,
  schemaRef,
  createdAt = FIXED_ARTIFACT_AT,
  validationResults = [],
}) => ({
  artifact: {
    artifactId,
    artifactType,
    confidentiality: "internal",
    createdAt,
    createdBy: "SVC-F04-golden-flow",
    encryption: { atRest: true, inTransit: true, keyRef: "local://f04-golden" },
    inputArtifactIds: [],
    license: null,
    lineageEventIds: ["EVT-F04-golden-fixture"],
    mediaType: "application/json",
    provenanceManifestId: "PROV-F04-golden-fixture",
    retentionClass: "project",
  },
  receipt: {
    actionIntentId: null,
    createdAt,
    createdBy: { actorId: "SVC-F04-golden-flow", actorType: "service" },
    receiptId,
    schemaRef,
    validationResults,
  },
});

const putJsonArtifact = (
  store,
  document,
  { artifactId, artifactType, receiptId, schemaRef, validationResults = [] },
) =>
  store.putArtifact(Buffer.from(`${JSON.stringify(document)}\n`, "utf8"),
    artifactMetadata({
      artifactId,
      artifactType,
      receiptId,
      schemaRef,
      validationResults,
    }));

const canonicalSchemaValidation = (schemaRef) => [
  { check: "canonical_schema_validation", status: "PASS", details: schemaRef },
];

const validateCanonicalDocuments = (caseId, documents) => {
  if (VALIDATED_CASES.has(caseId)) return;
  const validationRoot = mkdtempSync(path.join(tmpdir(), "ef-f04-schema-"));
  try {
    const bundlePath = path.join(validationRoot, "validation-bundle.json");
    writeFileSync(bundlePath, `${JSON.stringify(documents)}\n`, "utf8");
    const script = `
import json
import pathlib
import sys
from jsonschema import Draft202012Validator, FormatChecker

repository_root = pathlib.Path(sys.argv[1])
bundle = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
validated = 0
for row in bundle:
    schema = json.loads((repository_root / row["schema_ref"]).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(row["document"]),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        location = "/".join(str(part) for part in errors[0].absolute_path)
        raise SystemExit(f'{row["label"]}:{location}: {errors[0].message}')
    validated += 1
print(f"{validated} canonical F04 documents validated")
`;
    const validation = spawnSync(
      "uv",
      ["run", "--locked", "python", "-", REPOSITORY_ROOT, bundlePath],
      { cwd: REPOSITORY_ROOT, encoding: "utf8", input: script },
    );
    assert.equal(
      validation.status,
      0,
      `F04 canonical schema validation failed\nstdout: ${validation.stdout}\nstderr: ${validation.stderr}`,
    );
    assert.equal(
      validation.stdout.trim(),
      `${documents.length} canonical F04 documents validated`,
    );
    VALIDATED_CASES.add(caseId);
  } finally {
    rmSync(validationRoot, { recursive: true, force: true });
  }
};

const phaseResultEnvelope = ({ caseId, phase, runId, index }) => ({
  run_id: runId,
  node_id: `NODE-F04-${caseId}-${phase}`,
  attempt: 1,
  status: "success",
  output_artifact_ids: [],
  evidence_ids: [],
  errors: [],
  metrics: { fixture: "F04", phase },
  input_hash: sha256ForgeJson({ case_id: caseId, phase, direction: "input" }),
  output_hash: sha256ForgeJson({ case_id: caseId, phase, direction: "output" }),
  started_at: `2026-07-29T03:${String(index + 1).padStart(2, "0")}:00.000Z`,
  finished_at: `2026-07-29T03:${String(index + 1).padStart(2, "0")}:30.000Z`,
  completeness: {
    expected_count: 1,
    terminal_count: 1,
    missing_node_ids: [],
    partial_allowed: false,
  },
  effect_receipt_ids: [],
  policy_decision_ids: [],
  schema_validation_report_id: `SVR-F04-${caseId}-${phase}`,
  terminal_reason: `PHASE_${phase}_COMPLETED`,
});

const underdeterminedAdjudication = ({ caseId, runId, gateId }) => {
  const semantic = {
    adjudication_id: `ADJ-F04-${caseId}`,
    run_id: runId,
    hypothesis_id: `HYP-F04-${caseId}`,
    gate_decision_ids: [gateId],
    brief_ids: [`BRIEF-F04-${caseId}`],
    cross_examination_ids: [],
    minority_report_ids: [],
    verdict: "UNDERDETERMINED",
    scope_narrowing: [],
    strongest_support_id: null,
    strongest_counterevidence_id: null,
    unresolved_issue_ids: [`ISSUE-F04-${caseId}-INSUFFICIENT-EVIDENCE`],
    promotion_recommendation: "BLOCK",
    rationale:
      "The bounded evidence does not determine the claim; this truthful outcome is not a system failure.",
    deterministic_gate_override_attempted: false,
    created_at: "2026-07-29T03:08:00.000Z",
  };
  return Object.freeze({ ...semantic, adjudication_hash: sha256ForgeJson(semantic) });
};

export const assertUnderdeterminedAdjudication = (document) => {
  assert.equal(ADJUDICATION_SCHEMA.additionalProperties, false);
  assert.equal(
    ADJUDICATION_SCHEMA.properties.verdict.enum.includes("UNDERDETERMINED"),
    true,
  );
  assert.deepEqual(
    Object.keys(document).sort(),
    [...ADJUDICATION_SCHEMA.required].sort(),
  );
  assert.equal(document.verdict, "UNDERDETERMINED");
  assert.equal(document.promotion_recommendation, "BLOCK");
  assert.equal(document.deterministic_gate_override_attempted, false);
  assert.equal(document.unresolved_issue_ids.length > 0, true);
  assert.equal(document.rationale.length > 0, true);
  const { adjudication_hash: actualHash, ...semantic } = document;
  assert.equal(actualHash, sha256ForgeJson(semantic));
  return true;
};

const makeClassification = (store, definition) => {
  const requestText = `F04 golden flow ${definition.case_id}`;
  const policyBundleHash = sha256ForgeJson({
    fixture: "F04",
    case_id: definition.case_id,
    authority: "policy_bundle",
  });
  const input = {
    run_id: `RUN-F04-${definition.case_id}`,
    request_id: `REQ-F04-${definition.case_id}`,
    request_text: requestText,
    request_input_hash: classificationInputHash(requestText),
    classifier_version: CLASSIFIER_VERSION,
    policy_bundle_hash: policyBundleHash,
    policy_bundle_signals: [],
    typed_request_metadata: { signals: [definition.signal] },
    deterministic_detector_signals: [],
    llm_signal_proposals: [],
    missing_contract_flags: [...definition.missing_contract_flags],
  };
  const decision = evaluateEpistemicWork(input);
  const artifact = materializeClassificationArtifact(decision, FIXED_CLASSIFIED_AT);
  const registration = putJsonArtifact(store, artifact, {
    artifactId: artifact.classification_id,
    artifactType: "epistemic_work_classification",
    receiptId: `AR-F04-${definition.case_id}-CLASSIFICATION`,
    schemaRef: CLASSIFICATION_SCHEMA_REF,
    validationResults: canonicalSchemaValidation(CLASSIFICATION_SCHEMA_REF),
  });
  return {
    artifact,
    decision,
    input,
    registration,
    identityContext: {
      request_input_hash: input.request_input_hash,
      policy_bundle_hash: input.policy_bundle_hash,
      accepted_signals: [...decision.accepted_signals],
      supersedes_classification_hash: decision.supersedes_classification_hash,
      human_decision_hash: decision.human_decision_hash,
    },
  };
};

const makeGateDecision = ({ caseId, runId, evidenceId, policyBundleHash }) => {
  const inputArtifactIds = [evidenceId];
  const evaluatedAt = "2026-07-29T03:09:00.000Z";
  const semantic = {
    gate_id: `GD-F04-${caseId}-ENTER-E`,
    gate_version: "4.0.0",
    run_id: runId,
    name: "f04_golden_e_entry",
    status: "PASS",
    reasons: ["The bounded golden-flow evidence resolves and is receipt-bound."],
    evidence_ids: [evidenceId],
    input_artifact_ids: inputArtifactIds,
    policy_bundle_hash: policyBundleHash,
    decision: "PASS",
    blocker_ids: [],
    waiver_authority: null,
    waiver_reason: null,
    evaluated_at: evaluatedAt,
    created_at: evaluatedAt,
    policy_version: "4.0.0",
    non_waivable: true,
    evaluator_type: "deterministic",
    input_hash: sha256ForgeJson({
      case_id: caseId,
      gate: "ENTER_E",
      input_artifact_ids: inputArtifactIds,
      policy_bundle_hash: policyBundleHash,
    }),
  };
  return Object.freeze({ ...semantic, decision_hash: sha256ForgeJson(semantic) });
};

const transitionEdges = (phases) => {
  const edges = [{ from: "IDLE", to: phases[0] }];
  for (let index = 0; index < phases.length - 1; index += 1) {
    edges.push({ from: phases[index], to: phases[index + 1] });
  }
  edges.push({ from: "E", to: "IDLE" });
  return edges;
};

const transitionRequest = ({ caseId, edge, index, receiptIds, gateIds }) => ({
  request_id: `FTR-F04-${caseId}-${String(index + 1).padStart(2, "0")}`,
  session_id: `FS-F04-${caseId}`,
  expected_revision: index,
  from_phase: edge.from,
  to_phase: edge.to,
  actor: {
    actor_id: "SVC-F04-foundry-kernel",
    actor_type: "service",
    role: "foundry_kernel",
  },
  artifact_receipt_ids: receiptIds,
  gate_result_ids: gateIds,
  human_decision_id: null,
  reason: `F04 golden flow ${edge.from} to ${edge.to}`,
  idempotency_key: `f04-${caseId}-${index}-${edge.from}-${edge.to}`,
  requested_at: `2026-07-29T03:${String(index + 10).padStart(2, "0")}:00.000Z`,
});

const transitionEvent = ({ caseId, index }) => ({
  event_id: `EVT-F04-${caseId}-${String(index + 1).padStart(2, "0")}`,
  occurred_at: `2026-07-29T04:${String(index + 1).padStart(2, "0")}:00.000Z`,
});

const persistTransitionRecord = (store, caseId, index, transition) => {
  const artifactId = `FTE-F04-${caseId}-${String(index + 1).padStart(2, "0")}`;
  const registration = putJsonArtifact(store, transition, {
    artifactId,
    artifactType: "forge_transition_record",
    receiptId: `AR-${artifactId}`,
    schemaRef: null,
    validationResults: [
      {
        check: "transition_hash_validation",
        status: "PASS",
        details: transition.transition_hash,
      },
    ],
  });
  return {
    artifact_id: artifactId,
    receipt_id: registration.receipt.receipt_id,
    record: JSON.parse(store.readArtifact(artifactId).toString("utf8")),
  };
};

const prepareFlow = (t, definition) => {
  const storeRoot = mkdtempSync(path.join(tmpdir(), "ef-f04-"));
  t.after(() => rmSync(storeRoot, { recursive: true, force: true }));
  const store = openContentAddressedArtifactStore(storeRoot);
  const classification = makeClassification(store, definition);
  const runId = classification.input.run_id;
  const sessionId = `FS-F04-${definition.case_id}`;
  const gateId = `GD-F04-${definition.case_id}-ENTER-E`;
  const phaseRecords = new Map();

  definition.expected_required_phases.forEach((phase, index) => {
    const artifactId =
      phase === "E"
        ? `ADJ-F04-${definition.case_id}`
        : `ART-F04-${definition.case_id}-${phase}`;
    const schemaRef = phase === "E" ? ADJUDICATION_SCHEMA_REF : RESULT_SCHEMA_REF;
    const document =
      phase === "E"
        ? underdeterminedAdjudication({ caseId: definition.case_id, runId, gateId })
        : phaseResultEnvelope({ caseId: definition.case_id, phase, runId, index });
    if (phase === "E") assertUnderdeterminedAdjudication(document);
    const evidenceRegistration = putJsonArtifact(store, document, {
      artifactId,
      artifactType: phase === "E" ? "adjudication" : "phase_result_envelope",
      receiptId: `AR-F04-${definition.case_id}-${phase}`,
      schemaRef,
      validationResults: canonicalSchemaValidation(schemaRef),
    });
    const entry = {
      artifact_id: artifactId,
      kind: phase === "E" ? "Adjudication" : `Phase${phase}ResultEnvelope`,
      schema_ref: schemaRef,
      content_hash: evidenceRegistration.manifest.content_hash,
      receipt_id: evidenceRegistration.receipt.receipt_id,
      status: "VALID",
    };
    const phaseSet = sealPhaseArtifactSet({
      set_id: `PAS-F04-${definition.case_id}-${phase}`,
      session_id: sessionId,
      phase,
      required_artifacts: [entry],
      optional_artifacts: [],
      complete: true,
      missing_kinds: [],
      validated_at: "2026-07-29T03:07:00.000Z",
    });
    const phaseSetRegistration = putJsonArtifact(store, phaseSet, {
      artifactId: phaseSet.set_id,
      artifactType: "phase_artifact_set",
      receiptId: `AR-${phaseSet.set_id}`,
      schemaRef: PHASE_SET_SCHEMA_REF,
      validationResults: canonicalSchemaValidation(PHASE_SET_SCHEMA_REF),
    });
    phaseRecords.set(phase, {
      document,
      entry,
      evidenceRegistration,
      phaseSet,
      phaseSetRegistration,
    });
  });

  const preEPhase = definition.expected_required_phases.at(-2);
  const preERecord = phaseRecords.get(preEPhase);
  const gateDecision = makeGateDecision({
    caseId: definition.case_id,
    runId,
    evidenceId: preERecord.entry.artifact_id,
    policyBundleHash: classification.input.policy_bundle_hash,
  });
  const gateRegistration = putJsonArtifact(store, gateDecision, {
    artifactId: gateDecision.gate_id,
    artifactType: "gate_decision",
    receiptId: `AR-${gateDecision.gate_id}`,
    schemaRef: "schemas/gate-decision.schema.json",
    validationResults: canonicalSchemaValidation("schemas/gate-decision.schema.json"),
  });

  validateCanonicalDocuments(definition.case_id, [
    {
      label: "EpistemicWorkClassification",
      schema_ref: CLASSIFICATION_SCHEMA_REF,
      document: classification.artifact,
    },
    ...[...phaseRecords.entries()].flatMap(([phase, record]) => [
      {
        label: `${phase} phase artifact`,
        schema_ref: record.entry.schema_ref,
        document: record.document,
      },
      {
        label: `${phase} PhaseArtifactSet`,
        schema_ref: PHASE_SET_SCHEMA_REF,
        document: record.phaseSet,
      },
    ]),
    {
      label: "GateDecision",
      schema_ref: "schemas/gate-decision.schema.json",
      document: gateDecision,
    },
  ]);

  const initialState = sealForgeSessionState({
    session_id: sessionId,
    workspace_id: "WS-F04-golden",
    revision: 0,
    phase: "IDLE",
    work_class: definition.expected_work_class,
    status: "ACTIVE",
    run_spec_id: runId,
    hypothesis_revision_ids: [`HYP-F04-${definition.case_id}-R1`],
    artifact_ids: [...phaseRecords.values()].map((record) => record.entry.artifact_id),
    open_blockers: [],
    phase_history: [],
    policy_hash: classification.input.policy_bundle_hash,
    corpus_snapshot_hash: sha256ForgeJson({
      fixture: "F04",
      case_id: definition.case_id,
      snapshot: "corpus",
    }),
    updated_at: FIXED_CLASSIFIED_AT,
  });
  const phaseSets = [...phaseRecords.values()].map((record) => record.phaseSet);
  const edges = transitionEdges(definition.expected_required_phases);
  const transitionEntries = edges.map((edge, index) => {
    let receiptIds;
    const gateIds = [];
    if (edge.from === "IDLE") {
      receiptIds = [classification.registration.receipt.receipt_id];
    } else {
      const phase = phaseRecords.get(edge.from);
      receiptIds = [
        phase.entry.receipt_id,
        phase.phaseSetRegistration.receipt.receipt_id,
      ];
      if (edge.to === "E") {
        receiptIds.push(gateRegistration.receipt.receipt_id);
        gateIds.push(gateDecision.gate_id);
      }
    }
    return {
      transition_request: transitionRequest({
        caseId: definition.case_id,
        edge,
        index,
        receiptIds,
        gateIds,
      }),
      event: transitionEvent({ caseId: definition.case_id, index }),
    };
  });

  return {
    store,
    classification,
    definition,
    initialState,
    phaseRecords,
    phaseSets,
    gateDecision,
    transitionEntries,
  };
};

export const executeGoldenFlow = (t, definition) => {
  const fixture = prepareFlow(t, definition);
  const plan = compileForgePlan({
    classification: fixture.classification.artifact,
    classification_identity_context: fixture.classification.identityContext,
  });
  let state = fixture.initialState;
  let phaseSets = fixture.phaseSets;
  const admissions = [];
  const directTransitions = [];
  const persistedTransitions = [];

  for (let index = 0; index < fixture.transitionEntries.length; index += 1) {
    const entry = fixture.transitionEntries[index];
    const admitted = admitForgeTransition({
      current_state: state,
      transition_request: entry.transition_request,
      artifact_store: fixture.store,
    });
    const reduced = reduceForgeTransition({
      current_state: state,
      transition_request: entry.transition_request,
      classification: fixture.classification.artifact,
      classification_identity_context: fixture.classification.identityContext,
      phase_artifact_sets: phaseSets,
      event: entry.event,
    });
    assert.equal(admitted.admission.request_hash, reduced.transition.request_hash);
    admissions.push(admitted);
    directTransitions.push(reduced.transition);
    persistedTransitions.push(
      persistTransitionRecord(fixture.store, definition.case_id, index, reduced.transition),
    );
    state = reduced.state;
    phaseSets = reduced.phase_artifact_sets;
  }

  const replay = replayForgeTransitionEvents({
    initial_state: fixture.initialState,
    transitions: fixture.transitionEntries,
    classification: fixture.classification.artifact,
    classification_identity_context: fixture.classification.identityContext,
    phase_artifact_sets: fixture.phaseSets,
  });
  const storeIntegrity = fixture.store.checkIntegrity();
  return Object.freeze({
    ...fixture,
    admissions: Object.freeze(admissions),
    directTransitions: Object.freeze(directTransitions),
    persistedTransitions: Object.freeze(persistedTransitions),
    finalState: state,
    finalPhaseSets: phaseSets,
    plan,
    replay,
    storeIntegrity,
    expectedTransitionIds: Object.freeze(
      fixture.transitionEntries.map((entry) => entry.transition_request.request_id),
    ),
  });
};

const duplicateIds = (ids) => {
  const seen = new Set();
  const duplicates = new Set();
  for (const id of ids) {
    if (seen.has(id)) duplicates.add(id);
    seen.add(id);
  }
  return [...duplicates].sort();
};

const missingIds = (expected, actual) => {
  const observed = new Set(actual);
  return expected.filter((id) => !observed.has(id));
};

export const reconcileGoldenFlows = (results) => {
  const expected = results.flatMap((result) => result.expectedTransitionIds);
  const generated = results.flatMap((result) =>
    result.transitionEntries.map((entry) => entry.transition_request.request_id));
  const admitted = results.flatMap((result) =>
    result.admissions.map((entry) => entry.admission.request_id));
  const reduced = results.flatMap((result) =>
    result.directTransitions.map((entry) => entry.request_id));
  const replayed = results.flatMap((result) =>
    result.replay.transitions.map((entry) => entry.request_id));
  const persisted = results.flatMap((result) =>
    result.persistedTransitions.map((entry) => entry.record.request_id));
  const stages = { generated, admitted, reduced, replayed, persisted };
  const missingByStage = Object.fromEntries(
    Object.entries(stages).map(([stage, ids]) => [stage, missingIds(expected, ids)]),
  );
  const duplicateByStage = Object.fromEntries(
    Object.entries(stages).map(([stage, ids]) => [stage, duplicateIds(ids)]),
  );
  const expectedPhaseSets = results.flatMap((result) =>
    result.definition.expected_required_phases.map(
      (phase) => `PAS-F04-${result.definition.case_id}-${phase}`,
    ));
  const generatedPhaseSets = results.flatMap((result) =>
    result.phaseSets.map((phaseSet) => phaseSet.set_id));
  const admittedPhaseSets = results.flatMap((result) =>
    result.admissions
      .map((entry) => entry.admission.phase_artifact_set_id)
      .filter((value) => value !== null));
  const missingPhaseSetIds = [
    ...new Set([
      ...missingIds(expectedPhaseSets, generatedPhaseSets),
      ...missingIds(expectedPhaseSets, admittedPhaseSets),
    ]),
  ].sort();
  const missingTransitionIds = [
    ...new Set(Object.values(missingByStage).flat()),
  ].sort();
  const duplicateTransitionIds = [
    ...new Set(Object.values(duplicateByStage).flat()),
  ].sort();
  const failedCount = results.filter((result) => result.finalState.status !== "COMPLETED").length;
  const status =
    missingTransitionIds.length === 0 &&
    duplicateTransitionIds.length === 0 &&
    missingPhaseSetIds.length === 0 &&
    failedCount === 0
      ? "PASS"
      : "FAIL";
  return Object.freeze({
    status,
    flow_count: results.length,
    expected_transition_count: expected.length,
    generated_transition_count: generated.length,
    admitted_transition_count: admitted.length,
    reduced_transition_count: reduced.length,
    replayed_transition_count: replayed.length,
    persisted_transition_count: persisted.length,
    expected_phase_artifact_set_count: expectedPhaseSets.length,
    generated_phase_artifact_set_count: generatedPhaseSets.length,
    admitted_phase_artifact_set_count: admittedPhaseSets.length,
    underdetermined_terminal_outcome_count: results.filter(
      (result) => result.phaseRecords.get("E").document.verdict === "UNDERDETERMINED",
    ).length,
    failed_count: failedCount,
    cancelled_count: 0,
    missing_transition_ids: missingTransitionIds,
    duplicate_transition_ids: duplicateTransitionIds,
    missing_phase_artifact_set_ids: missingPhaseSetIds,
  });
};
