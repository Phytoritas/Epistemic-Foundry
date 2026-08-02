import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  buildClassificationPreimage,
  classificationInputHash,
  sha256ClassificationJson,
} from "./epistemic-work-classifier.mjs";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../..",
);
const fixture = JSON.parse(
  fs.readFileSync(
    path.join(repositoryRoot, "tests/golden/forge/f01_classifier_hash_vectors.json"),
    "utf8",
  ),
);

const semanticFields = (row) => ({
  request_id: `REQ-${row.vector_id}`,
  request_input_hash: row.request_input_hash,
  classifier_version: fixture.classifier_version,
  policy_bundle_hash: row.policy_bundle_hash,
  accepted_signals: row.accepted_signals,
  reasons: row.reasons,
  risk_factors: row.risk_factors,
  work_class: row.work_class,
  required_phases: row.required_phases,
  default_role_count: row.default_role_count,
  human_gate_required: row.human_gate_required,
  supersedes_classification_hash: row.supersedes_classification_hash,
  human_decision_hash: row.human_decision_hash,
});

test("classifier_hash_vector_test: every frozen preimage has the exact SHA-256 and ID", () => {
  assert.equal(fixture.vectors.length, 4);
  for (const row of fixture.vectors) {
    assert.equal(classificationInputHash(row.request_text), row.request_input_hash, row.vector_id);
    const preimage = buildClassificationPreimage(semanticFields(row));
    assert.equal(preimage.schema_id, fixture.schema_id, row.vector_id);
    const classificationHash = sha256ClassificationJson(preimage);
    assert.equal(classificationHash, row.expected_classification_hash, row.vector_id);
    assert.equal(
      `EWC-${classificationHash.slice("sha256:".length)}`,
      row.expected_classification_id,
      row.vector_id,
    );
  }
});

test("classifier_hash_vector_test: volatile and self fields are outside the semantic preimage", () => {
  const row = fixture.vectors[1];
  const preimage = buildClassificationPreimage(semanticFields(row));
  for (const forbidden of [
    "classification_id",
    "classified_at",
    "classification_hash",
    "artifact_receipt_id",
    "ledger_sequence_number",
    "retry_attempt_number",
  ]) {
    assert.equal(Object.hasOwn(preimage, forbidden), false, forbidden);
  }
});
