import { createHash } from "node:crypto";

import {
  CLASSIFIER_VERSION,
  classificationInputHash,
  evaluateEpistemicWork,
  materializeClassificationArtifact,
} from "../classifier/epistemic-work-classifier.mjs";
import { sealForgeSessionState, sealPhaseArtifactSet } from "./forge-fsm.mjs";

export const fsmHash = (label) =>
  `sha256:${createHash("sha256").update(`F02:${label}`, "utf8").digest("hex")}`;

export const classificationFixture = ({
  signal = "MECHANISM",
  missingContractFlags = [],
  requestId = `REQ-F02-${signal}`,
} = {}) => {
  const requestText = `F02 deterministic fixture for ${signal}`;
  const input = {
    run_id: `RUN-F02-${signal}`,
    request_id: requestId,
    request_text: requestText,
    request_input_hash: classificationInputHash(requestText),
    classifier_version: CLASSIFIER_VERSION,
    policy_bundle_hash: fsmHash(`policy-${signal}`),
    policy_bundle_signals: [],
    typed_request_metadata: { signals: [signal] },
    deterministic_detector_signals: [],
    llm_signal_proposals: [],
    missing_contract_flags: missingContractFlags,
  };
  const decision = evaluateEpistemicWork(input);
  const artifact = materializeClassificationArtifact(decision, "2026-07-29T01:00:00.000Z");
  return {
    classification: artifact,
    classification_identity_context: {
      request_input_hash: input.request_input_hash,
      policy_bundle_hash: input.policy_bundle_hash,
      accepted_signals: [...decision.accepted_signals],
      supersedes_classification_hash: decision.supersedes_classification_hash,
      human_decision_hash: decision.human_decision_hash,
    },
  };
};

export const phaseArtifactSetFixture = ({
  phase,
  sessionId = "FS-F02-test",
  suffix = phase,
  status = "VALID",
} = {}) =>
  sealPhaseArtifactSet({
    set_id: `PAS-F02-${suffix}`,
    session_id: sessionId,
    phase,
    required_artifacts: [
      {
        artifact_id: `ART-F02-${suffix}`,
        kind: `Fixture${phase}`,
        schema_ref: `schemas/f02-${phase.toLowerCase()}.schema.json`,
        content_hash: fsmHash(`artifact-${suffix}`),
        receipt_id: `AR-F02-${suffix}`,
        status,
      },
    ],
    optional_artifacts: [],
    complete: status === "VALID",
    missing_kinds: [],
    validated_at: "2026-07-29T01:00:00.000Z",
  });

export const sessionStateFixture = ({
  workClass = "E3",
  phase = "IDLE",
  revision = 0,
  phaseHistory = [],
  phaseSets = [],
  status = "ACTIVE",
  sessionId = "FS-F02-test",
} = {}) =>
  sealForgeSessionState({
    session_id: sessionId,
    workspace_id: "WS-F02-test",
    revision,
    phase,
    work_class: workClass,
    status,
    run_spec_id: "RS-F02-test",
    hypothesis_revision_ids: ["H-F02-R1"],
    artifact_ids: phaseSets.flatMap((set) => [
      ...set.required_artifacts.map((artifact) => artifact.artifact_id),
      ...set.optional_artifacts.map((artifact) => artifact.artifact_id),
    ]),
    open_blockers: [],
    phase_history: phaseHistory,
    policy_hash: fsmHash("policy"),
    corpus_snapshot_hash: fsmHash("corpus"),
    updated_at: "2026-07-29T01:00:00.000Z",
  });

export const transitionRequestFixture = ({
  from,
  to,
  revision,
  sessionId = "FS-F02-test",
  suffix = `${from}-${to}-${revision}`,
} = {}) => ({
  request_id: `FTR-F02-${suffix}`,
  session_id: sessionId,
  expected_revision: revision,
  from_phase: from,
  to_phase: to,
  actor: {
    actor_id: "SVC-F02-reducer-test",
    actor_type: "service",
    role: "foundry_kernel",
  },
  artifact_receipt_ids: [],
  gate_result_ids: [],
  human_decision_id: null,
  reason: `F02 fixture ${from} to ${to}`,
  idempotency_key: `f02-${suffix}-idempotency`,
  requested_at: "2026-07-29T01:01:00.000Z",
});

export const transitionEventFixture = ({ suffix, minute = 1 } = {}) => ({
  event_id: `EVT-F02-${suffix}`,
  occurred_at: `2026-07-29T01:${String(minute).padStart(2, "0")}:00.000Z`,
});

