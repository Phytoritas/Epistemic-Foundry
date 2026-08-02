import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { openContentAddressedArtifactStore } from "../artifacts/content-addressed-artifact-store.mjs";
import { openSQLiteStateStore } from "../state/sqlite/sqlite-state-store.mjs";
import { createNoeticLedger } from "./noetic-ledger.mjs";

export const fixedTimestamp = (offset = 0) =>
  `2026-07-28T01:${String(offset).padStart(2, "0")}:00Z`;

export const payloadMetadata = ({ artifactId, receiptId, timestamp = fixedTimestamp() }) => ({
  artifact: {
    artifactId,
    artifactType: "event_payload",
    confidentiality: "internal",
    createdAt: timestamp,
    createdBy: "ACT-E01-payload-writer",
    encryption: { atRest: true, inTransit: true, keyRef: "local://e01-test-key" },
    inputArtifactIds: [],
    license: null,
    lineageEventIds: [],
    mediaType: "application/json",
    provenanceManifestId: "PROV-E01-test",
    retentionClass: "project",
  },
  receipt: {
    actionIntentId: null,
    createdAt: timestamp,
    createdBy: { actorId: "ACT-E01-payload-writer", actorType: "service" },
    receiptId,
    schemaRef: null,
    validationResults: [
      { check: "event_payload_fixture", status: "PASS", details: "deterministic E01 fixture" },
    ],
  },
});

export const putJsonPayload = (
  artifactStore,
  artifactId,
  value,
  receiptId = `AR-${artifactId}`,
) => {
  const bytes = Buffer.from(JSON.stringify(value), "utf8");
  artifactStore.putArtifact(bytes, payloadMetadata({ artifactId, receiptId }));
  return bytes;
};

export const eventInput = ({
  eventId,
  runId = "RUN-E01-test",
  payloadArtifactId,
  eventType = "session.advanced",
  occurredAt = fixedTimestamp(),
} = {}) => ({
  event_id: eventId,
  run_id: runId,
  event_type: eventType,
  aggregate_type: "session",
  aggregate_id: `AGG-${runId}`,
  actor_id: "ACT-E01-test",
  payload_artifact_id: payloadArtifactId,
  occurred_at: occurredAt,
  schema_version: "4.0.0",
});

export const createLedgerFixture = (t, prefix = "ef-e01-") => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  const databasePath = path.join(root, "foundry.db");
  const artifactRoot = path.join(root, "artifacts");
  const stateStore = openSQLiteStateStore(databasePath);
  const artifactStore = openContentAddressedArtifactStore(artifactRoot);
  const ledger = createNoeticLedger({ artifactStore, stateStore });
  t.after(() => {
    stateStore.close();
    artifactStore.close();
    fs.rmSync(root, { recursive: true, force: true });
  });
  return { artifactRoot, artifactStore, databasePath, ledger, root, stateStore };
};

