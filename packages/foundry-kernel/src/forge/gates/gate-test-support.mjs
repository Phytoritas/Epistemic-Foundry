import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { openContentAddressedArtifactStore } from "../../artifacts/content-addressed-artifact-store.mjs";
import {
  CLASSIFIER_VERSION,
  classificationInputHash,
  evaluateEpistemicWork,
  materializeClassificationArtifact,
} from "../classifier/epistemic-work-classifier.mjs";
import { sha256TransitionJson } from "./transition-admission-gate.mjs";

export const gateHash = (label) => sha256TransitionJson({ fixture: `F03:${label}` });

export const activeArtifactStore = (t) => {
  const root = mkdtempSync(path.join(tmpdir(), "ef-f03-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return openContentAddressedArtifactStore(root);
};

export const putJsonArtifact = (
  store,
  document,
  {
    artifactId,
    receiptId,
    schemaRef,
    artifactType,
    actorId = "SVC-F03-fixture",
    actorType = "service",
    createdAt = "2026-07-29T02:00:00.000Z",
  },
) => {
  const bytes = Buffer.from(`${JSON.stringify(document)}\n`, "utf8");
  return store.putArtifact(bytes, {
    artifact: {
      artifactId,
      artifactType,
      confidentiality: "internal",
      createdAt,
      createdBy: actorId,
      encryption: { atRest: true, inTransit: true, keyRef: "local://f03-test" },
      inputArtifactIds: [],
      license: null,
      lineageEventIds: ["EVT-F03-fixture"],
      mediaType: "application/json",
      provenanceManifestId: "PROV-F03-fixture",
      retentionClass: "project",
    },
    receipt: {
      actionIntentId: null,
      createdAt,
      createdBy: { actorId, actorType },
      receiptId,
      schemaRef,
      validationResults: [
        { check: "canonical_schema_validation", status: "PASS", details: schemaRef },
      ],
    },
  });
};

export const registerPhaseEvidence = (
  store,
  { suffix = "frame", schemaRef = "schemas/insight-card.schema.json" } = {},
) => {
  const artifactId = `ART-F03-${suffix}`;
  const receiptId = `AR-F03-${suffix}`;
  const registration = putJsonArtifact(
    store,
    { artifact_id: artifactId, fixture: suffix },
    {
      artifactId,
      receiptId,
      schemaRef,
      artifactType: "phase_evidence",
    },
  );
  return {
    artifact_id: artifactId,
    kind: `Fixture${suffix}`,
    schema_ref: schemaRef,
    content_hash: registration.manifest.content_hash,
    receipt_id: receiptId,
    status: "VALID",
  };
};

export const registerClassification = (
  store,
  { signal = "MECHANISM", suffix = signal.toLowerCase() } = {},
) => {
  const requestText = `F03 deterministic classification fixture for ${signal}`;
  const input = {
    run_id: `RUN-F03-${suffix}`,
    request_id: `REQ-F03-${suffix}`,
    request_text: requestText,
    request_input_hash: classificationInputHash(requestText),
    classifier_version: CLASSIFIER_VERSION,
    policy_bundle_hash: gateHash(`classification-policy-${suffix}`),
    policy_bundle_signals: [],
    typed_request_metadata: { signals: [signal] },
    deterministic_detector_signals: [],
    llm_signal_proposals: [],
    missing_contract_flags: [],
  };
  const decision = evaluateEpistemicWork(input);
  const artifact = materializeClassificationArtifact(
    decision,
    "2026-07-29T02:00:00.000Z",
  );
  const registration = putJsonArtifact(store, artifact, {
    artifactId: artifact.classification_id,
    receiptId: `AR-F03-classification-${suffix}`,
    schemaRef: "schemas/epistemic-work-classification.schema.json",
    artifactType: "epistemic_work_classification",
  });
  return { artifact, registration };
};

export const sealPhaseArtifactSet = ({
  sessionId = "FS-F03-test",
  phase = "F",
  requiredArtifacts,
  optionalArtifacts = [],
  complete = true,
  missingKinds = [],
  suffix = phase,
} = {}) => {
  const semantic = {
    set_id: `PAS-F03-${suffix}`,
    session_id: sessionId,
    phase,
    required_artifacts: requiredArtifacts,
    optional_artifacts: optionalArtifacts,
    complete,
    missing_kinds: missingKinds,
    validated_at: "2026-07-29T02:01:00.000Z",
  };
  return { ...semantic, set_hash: sha256TransitionJson(semantic) };
};

export const registerPhaseArtifactSet = (store, phaseSet) =>
  putJsonArtifact(store, phaseSet, {
    artifactId: phaseSet.set_id,
    receiptId: `AR-${phaseSet.set_id}`,
    schemaRef: "schemas/phase-artifact-set.schema.json",
    artifactType: "phase_artifact_set",
  });

export const sealState = ({
  sessionId = "FS-F03-test",
  phase = "F",
  revision = 1,
  artifactIds = [],
  runSpecId = "RUN-F03-test",
} = {}) => {
  const semantic = {
    session_id: sessionId,
    workspace_id: "WS-F03-test",
    revision,
    phase,
    work_class: "E3",
    status: "ACTIVE",
    run_spec_id: runSpecId,
    hypothesis_revision_ids: ["HYP-F03-R1"],
    artifact_ids: artifactIds,
    open_blockers: [],
    phase_history: [],
    policy_hash: gateHash("policy"),
    corpus_snapshot_hash: gateHash("corpus"),
    updated_at: "2026-07-29T02:02:00.000Z",
  };
  return { ...semantic, state_hash: sha256TransitionJson(semantic) };
};

export const transitionRequest = ({
  state,
  to = "O",
  receiptIds = [],
  gateResultIds = [],
  humanDecisionId = null,
  reason = `advance ${state.phase} to ${to}`,
} = {}) => ({
  request_id: `FTR-F03-${state.phase}-${to}-${state.revision}`,
  session_id: state.session_id,
  expected_revision: state.revision,
  from_phase: state.phase,
  to_phase: to,
  actor: {
    actor_id: "SVC-F03-kernel",
    actor_type: "service",
    role: "foundry_kernel",
  },
  artifact_receipt_ids: receiptIds,
  gate_result_ids: gateResultIds,
  human_decision_id: humanDecisionId,
  reason,
  idempotency_key: `f03-${state.session_id}-${state.revision}-${to}`,
  requested_at: "2026-07-29T02:03:00.000Z",
});

export const sealGateDecision = ({
  gateId = "GD-F03-grounding",
  gateVersion,
  runId = "RUN-F03-test",
  status = "PASS",
  decision = status,
  nonWaivable = true,
  waiverAuthority = null,
  waiverReason = null,
  evidenceIds = [],
  inputArtifactIds,
  policyBundleHash,
  blockerIds = [],
} = {}) => {
  if (typeof gateVersion !== "string" || gateVersion.length === 0) {
    throw new TypeError("sealGateDecision requires an explicit gateVersion");
  }
  if (!Array.isArray(inputArtifactIds) || inputArtifactIds.length === 0) {
    throw new TypeError("sealGateDecision requires explicit inputArtifactIds");
  }
  if (typeof policyBundleHash !== "string" || policyBundleHash.length === 0) {
    throw new TypeError("sealGateDecision requires an explicit policyBundleHash");
  }
  const evaluatedAt = "2026-07-29T02:04:00.000Z";
  const semantic = {
    gate_id: gateId,
    gate_version: gateVersion,
    run_id: runId,
    name: "evidence_grounding",
    status,
    reasons: [status === "PASS" ? "all evidence resolves" : `fixture ${status}`],
    evidence_ids: evidenceIds,
    input_artifact_ids: inputArtifactIds,
    policy_bundle_hash: policyBundleHash,
    decision,
    blocker_ids: blockerIds,
    waiver_authority: waiverAuthority,
    waiver_reason: waiverReason,
    evaluated_at: evaluatedAt,
    created_at: evaluatedAt,
    policy_version: "4.0.0",
    non_waivable: nonWaivable,
    evaluator_type: "deterministic",
    input_hash: sha256TransitionJson({
      gate_id: gateId,
      input_artifact_ids: inputArtifactIds,
      policy_bundle_hash: policyBundleHash,
    }),
  };
  return { ...semantic, decision_hash: sha256TransitionJson(semantic) };
};

export const registerGateDecision = (store, decision) =>
  putJsonArtifact(store, decision, {
    artifactId: decision.gate_id,
    receiptId: `AR-${decision.gate_id}`,
    schemaRef: "schemas/gate-decision.schema.json",
    artifactType: "gate_decision",
  });

export const sealHumanDecision = ({
  decisionId = "HD-F03-waiver",
  runId = "RUN-F03-test",
  gateId = "GD-F03-style",
  authorityId = "HUMAN-F03-owner",
  decisionType = "override_waivable_gate",
  affectedArtifactIds = [gateId],
} = {}) => {
  const semantic = {
    decision_id: decisionId,
    run_id: runId,
    subject_id: gateId,
    decision_type: decisionType,
    decision: "Override the bounded waivable gate for this transition only.",
    authority_id: authorityId,
    authority_role: "product_owner",
    rationale: "The declared limitation is accepted without changing immutable evidence.",
    evidence_artifact_ids: [gateId],
    affected_artifact_ids: affectedArtifactIds,
    supersedes_decision_id: null,
    non_mutation_acknowledgement: true,
    created_at: "2026-07-29T02:05:00.000Z",
  };
  return { ...semantic, decision_hash: sha256TransitionJson(semantic) };
};

export const registerHumanDecision = (
  store,
  decision,
  { actorId = decision.authority_id, actorType = "human" } = {},
) =>
  putJsonArtifact(store, decision, {
    artifactId: decision.decision_id,
    receiptId: `AR-${decision.decision_id}`,
    schemaRef: "schemas/human-decision.schema.json",
    artifactType: "human_decision",
    actorId,
    actorType,
    createdAt: decision.created_at,
  });

export const phaseTransitionFixture = (t, { phase = "F", to = "O", suffix = "frame" } = {}) => {
  const store = activeArtifactStore(t);
  const evidence = registerPhaseEvidence(store, { suffix });
  const phaseSet = sealPhaseArtifactSet({ phase, requiredArtifacts: [evidence], suffix });
  const phaseSetRegistration = registerPhaseArtifactSet(store, phaseSet);
  const state = sealState({ phase, artifactIds: [evidence.artifact_id] });
  const receiptIds = [evidence.receipt_id, phaseSetRegistration.receipt.receipt_id];
  const request = transitionRequest({ state, to, receiptIds });
  return { store, evidence, phaseSet, phaseSetRegistration, state, request, receiptIds };
};
