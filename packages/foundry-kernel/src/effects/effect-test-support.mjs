import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { openContentAddressedArtifactStore } from "../artifacts/content-addressed-artifact-store.mjs";
import { createNoeticLedger } from "../ledger/noetic-ledger.mjs";
import { openSQLiteStateStore } from "../state/sqlite/sqlite-state-store.mjs";
import {
  createEffectCoordinator,
  sealActionIntent,
  sealEffectReceipt,
} from "./effect-coordinator.mjs";

export const fixedEffectTimestamp = (offset = 0) =>
  `2026-07-28T03:${String(offset).padStart(2, "0")}:00Z`;

export const digestBytes = (bytes) =>
  `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

const artifactMetadata = ({
  artifactId,
  receiptId,
  timestamp = fixedEffectTimestamp(),
  artifactType = "effect_fixture",
  actionIntentId = null,
}) => ({
  artifact: {
    artifactId,
    artifactType,
    confidentiality: "internal",
    createdAt: timestamp,
    createdBy: "ACT-E02-test",
    encryption: { atRest: true, inTransit: true, keyRef: "local://e02-test-key" },
    inputArtifactIds: [],
    license: null,
    lineageEventIds: [],
    mediaType: "application/json",
    provenanceManifestId: "PROV-E02-test",
    retentionClass: "project",
  },
  receipt: {
    actionIntentId,
    createdAt: timestamp,
    createdBy: { actorId: "ACT-E02-test", actorType: "service" },
    receiptId,
    schemaRef: null,
    validationResults: [
      { check: "effect_fixture", status: "PASS", details: "deterministic E02 fixture" },
    ],
  },
});

export const putEffectArtifact = (
  artifactStore,
  {
    artifactId,
    bytes = Buffer.from(JSON.stringify({ artifactId }), "utf8"),
    receiptId = `AR-${artifactId}`,
    timestamp = fixedEffectTimestamp(),
    artifactType = "effect_fixture",
    actionIntentId = null,
  },
) => {
  const stableBytes = Buffer.from(bytes);
  artifactStore.putArtifact(
    stableBytes,
    artifactMetadata({
      actionIntentId,
      artifactId,
      artifactType,
      receiptId,
      timestamp,
    }),
  );
  return stableBytes;
};

export const createIntentFixture = (
  artifactStore,
  {
    intentId = "INTENT-E02-0001",
    runId = "RUN-E02-0001",
    nodeId = "execute_effect",
    idempotencyKey = "RUN-E02-0001:execute_effect:1",
    targetRef = "TARGET-E02-0001",
    actionType = "run_bounded_effect",
    argumentsArtifactId = `ART-ARGS-${intentId}`,
    argumentsValue = { operation: "deterministic-fixture" },
    createdAt = fixedEffectTimestamp(),
  } = {},
) => {
  const bytes = putEffectArtifact(artifactStore, {
    artifactId: argumentsArtifactId,
    artifactType: "action_arguments",
    bytes: Buffer.from(JSON.stringify(argumentsValue), "utf8"),
    receiptId: `AR-${argumentsArtifactId}`,
    timestamp: createdAt,
  });
  return sealActionIntent({
    intent_id: intentId,
    run_id: runId,
    node_id: nodeId,
    action_type: actionType,
    target_ref: targetRef,
    arguments_artifact_id: argumentsArtifactId,
    arguments_hash: digestBytes(bytes),
    idempotency_key: idempotencyKey,
    required_capabilities: ["sandbox_execute"],
    approval_record_ids: [],
    risk_class: "bounded_compute",
    created_at: createdAt,
  });
};

export const createReceiptFixture = ({
  receiptId,
  intent,
  attempt,
  status,
  finishedAt,
  resultArtifactIds = [],
  errorArtifactIds = [],
  observedStateHash = null,
  externalOperationId = null,
}) =>
  sealEffectReceipt({
    receipt_id: receiptId,
    intent_id: intent.intent_id,
    run_id: intent.run_id,
    external_operation_id: externalOperationId,
    status,
    result_artifact_ids: resultArtifactIds,
    error_artifact_ids: errorArtifactIds,
    observed_state_hash: observedStateHash,
    idempotency_key: intent.idempotency_key,
    started_at: attempt.started_at,
    finished_at: finishedAt,
    reconciliation_required: status === "UNKNOWN",
  });

export const createEffectFixture = (t, prefix = "ef-e02-") => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  const databasePath = path.join(root, "foundry.db");
  const artifactRoot = path.join(root, "artifacts");
  const stateStore = openSQLiteStateStore(databasePath);
  const artifactStore = openContentAddressedArtifactStore(artifactRoot);
  const ledger = createNoeticLedger({ artifactStore, stateStore });
  const coordinator = createEffectCoordinator({ artifactStore, ledger, stateStore });
  t.after(() => {
    stateStore.close();
    artifactStore.close();
    fs.rmSync(root, { recursive: true, force: true });
  });
  return {
    artifactRoot,
    artifactStore,
    coordinator,
    databasePath,
    ledger,
    root,
    stateStore,
  };
};
