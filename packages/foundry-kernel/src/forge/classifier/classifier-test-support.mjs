import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { openContentAddressedArtifactStore } from "../../artifacts/content-addressed-artifact-store.mjs";
import { createNoeticLedger } from "../../ledger/noetic-ledger.mjs";
import { openSQLiteStateStore } from "../../state/sqlite/sqlite-state-store.mjs";
import { createClassificationCommitter } from "./classification-committer.mjs";
import { classificationInputHash } from "./epistemic-work-classifier.mjs";

export const testHash = (label) =>
  `sha256:${createHash("sha256").update(label, "utf8").digest("hex")}`;

export const classificationInput = ({
  runId = "RUN-F01-test",
  requestId = "REQ-F01-test",
  requestText = "Explain the specified mechanism.",
  classifierVersion = "4.0.1-f01.1",
  policyBundleHash = testHash("F01-policy-default"),
  policySignals = [],
  requestSignals = ["MECHANISM"],
  detectorSignals = [],
  proposals = [],
  missingContractFlags = [],
} = {}) => ({
  run_id: runId,
  request_id: requestId,
  request_text: requestText,
  request_input_hash: classificationInputHash(requestText),
  classifier_version: classifierVersion,
  policy_bundle_hash: policyBundleHash,
  policy_bundle_signals: policySignals,
  typed_request_metadata: { signals: requestSignals },
  deterministic_detector_signals: detectorSignals,
  llm_signal_proposals: proposals,
  missing_contract_flags: missingContractFlags,
});

export const createClassifierFixture = (t, options = {}) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "ef-f01-"));
  const stateStore = openSQLiteStateStore(path.join(root, "foundry.db"));
  const artifactStore = openContentAddressedArtifactStore(path.join(root, "artifacts"));
  const ledger = createNoeticLedger({ artifactStore, stateStore });
  let currentTime = options.now ?? "2026-07-29T00:00:00.000Z";
  const clock = () => currentTime;
  const committer = createClassificationCommitter({ artifactStore, ledger, stateStore, clock });
  const setTime = (timestamp) => {
    currentTime = timestamp;
  };
  t.after(() => {
    stateStore.close();
    artifactStore.close();
    fs.rmSync(root, { recursive: true, force: true });
  });
  return { artifactStore, committer, ledger, root, setTime, stateStore };
};

