import assert from "node:assert/strict";
import test from "node:test";

import {
  auditRankingClaims,
  buildRankingClaims,
  RANKING_CLAIM_TYPES,
  WorkspaceMapViewError,
} from "./index.mjs";
import { workspaceMapFixture } from "./map-test-fixtures.mjs";

const errorCode = (code) => (error) =>
  error instanceof WorkspaceMapViewError && error.code === code;

const auditInput = (fixture = workspaceMapFixture()) => ({
  ...fixture,
  claims: structuredClone(buildRankingClaims(fixture)),
});

test("ranking_claim_audit: exact closed claim set passes", () => {
  const result = auditRankingClaims(auditInput());
  assert.equal(result.status, "PASS");
  assert.equal(result.claim_count, 4);
  assert.deepEqual(result.claim_types, RANKING_CLAIM_TYPES);
  assert.equal(new Set(result.artifact_hashes).size, 3);
});

test("ranking_claim_audit: generic RANKED or importance claims have no authority", () => {
  const input = auditInput();
  input.claims[0].claim_type = "RANKED";
  input.claims[0].label = "Overall importance";
  assert.throws(() => auditRankingClaims(input), errorCode("UNKNOWN_RANKING_CLAIM_TYPE"));
});

test("ranking_claim_audit: algorithm label cannot be changed to importance", () => {
  const input = auditInput();
  input.claims[0].label = "Importance ranking";
  assert.throws(() => auditRankingClaims(input), errorCode("RANKING_CLAIM_MISMATCH"));
});

test("ranking_claim_audit: algorithm name and version must match the sealed artifact", () => {
  for (const mutate of [
    (claim) => {
      claim.algorithm_name = "SYMBOL_LIST";
    },
    (claim) => {
      claim.algorithm_version = "latest";
    },
  ]) {
    const input = auditInput();
    mutate(input.claims[0]);
    assert.throws(() => auditRankingClaims(input), errorCode("RANKING_CLAIM_MISMATCH"));
  }
});

test("ranking_claim_audit: artifact hash tampering is rejected", () => {
  const input = auditInput();
  input.claims[1].artifact_hash = `sha256:${"f".repeat(64)}`;
  assert.throws(() => auditRankingClaims(input), errorCode("RANKING_CLAIM_MISMATCH"));
});

test("ranking_claim_audit: ranking order tampering is rejected", () => {
  const input = auditInput();
  input.claims[0].order.reverse();
  assert.throws(() => auditRankingClaims(input), errorCode("RANKING_CLAIM_MISMATCH"));
});

test("ranking_claim_audit: unresolved-edge exclusions cannot be hidden", () => {
  const input = auditInput();
  input.claims[2].excluded_unresolved_edge_ids = [];
  assert.throws(() => auditRankingClaims(input), errorCode("RANKING_CLAIM_MISMATCH"));
});

test("ranking_claim_audit: risk and blast-radius score semantics cannot be conflated", () => {
  const input = auditInput();
  input.claims[2].score_field = null;
  input.claims[3].score_field = "risk_score";
  assert.throws(() => auditRankingClaims(input), errorCode("RANKING_CLAIM_MISMATCH"));
});

test("ranking_claim_audit: absent query cannot be advertised as ranked", () => {
  const input = auditInput(workspaceMapFixture({ query: null }));
  assert.equal(input.claims[1].status, "NOT_PERSONALIZED");
  assert.deepEqual(input.claims[1].order, []);
  input.claims[1].status = "RANKED";
  assert.throws(() => auditRankingClaims(input), errorCode("RANKING_CLAIM_MISMATCH"));
});

test("ranking_claim_audit: missing, duplicate, and reordered claims fail closed", () => {
  const missing = auditInput();
  missing.claims.pop();
  assert.throws(() => auditRankingClaims(missing), errorCode("RANKING_CLAIM_SET_MISMATCH"));

  const duplicate = auditInput();
  duplicate.claims[3] = structuredClone(duplicate.claims[2]);
  assert.throws(() => auditRankingClaims(duplicate), errorCode("RANKING_CLAIM_SET_MISMATCH"));

  const reordered = auditInput();
  [reordered.claims[0], reordered.claims[1]] = [reordered.claims[1], reordered.claims[0]];
  assert.throws(() => auditRankingClaims(reordered), errorCode("RANKING_CLAIM_MISMATCH"));
});

test("ranking_claim_audit: unknown fields are rejected rather than ignored", () => {
  const input = auditInput();
  input.claims[0].confidence = 0.99;
  assert.throws(() => auditRankingClaims(input), errorCode("INVALID_RANKING_CLAIM"));
});

test("ranking_claim_audit: proxy, accessor, and sparse claim arrays fail without execution", () => {
  const proxyInput = auditInput();
  proxyInput.claims = new Proxy(proxyInput.claims, {});
  assert.throws(() => auditRankingClaims(proxyInput), errorCode("INVALID_RANKING_CLAIMS"));

  const accessorInput = auditInput();
  let invoked = false;
  Object.defineProperty(accessorInput.claims[0], "label", {
    enumerable: true,
    get() {
      invoked = true;
      return "forged";
    },
  });
  assert.throws(() => auditRankingClaims(accessorInput), errorCode("INVALID_RANKING_CLAIM"));
  assert.equal(invoked, false);

  const sparseInput = auditInput();
  const sparse = new Array(4);
  sparse[3] = sparseInput.claims[3];
  sparseInput.claims = sparse;
  assert.throws(() => auditRankingClaims(sparseInput), errorCode("INVALID_RANKING_CLAIMS"));
});

test("ranking_claim_audit: upstream artifact tampering cannot be laundered by matching prose", () => {
  const input = structuredClone(auditInput());
  input.risk_change_impact.risk_results[0].risk_score = 0.123;
  input.claims[2].label = "Intrinsic risk";
  assert.throws(() => auditRankingClaims(input));
});

test("ranking_claim_audit: claim derivation is deterministic across input permutation", () => {
  const first = workspaceMapFixture();
  const second = workspaceMapFixture({ reverse: true });
  assert.deepEqual(buildRankingClaims(first), buildRankingClaims(second));
  assert.deepEqual(auditRankingClaims(auditInput(first)), auditRankingClaims(auditInput(second)));
});
