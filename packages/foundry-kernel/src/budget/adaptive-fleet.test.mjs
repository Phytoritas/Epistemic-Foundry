// adaptive_fleet_test — the fleet scales worker fan-out deterministically within
// declared bounds, capped by the budget concurrency limit; fan-out is bounded;
// undeclared / out-of-bounds scaling is refused; the fleet acquires no
// authority; receipts are deterministic and re-derivable (Y01).

import assert from "node:assert/strict";
import test from "node:test";

import { BudgetControlError, createAdaptiveFleet } from "./index.mjs";
import { budgetEnvelopeFixture } from "./budget-test-support.mjs";

function assertCode(fn, code) {
  try {
    fn();
  } catch (error) {
    assert.ok(error instanceof BudgetControlError, String(error));
    assert.equal(error.code, code, error.message);
    return error;
  }
  assert.fail(`expected ${code}`);
}

test("adaptive_fleet_test: scaling is a deterministic clamp on backlog", () => {
  const fleet = createAdaptiveFleet({
    envelope: budgetEnvelopeFixture({ hardLimits: { concurrency: 8 } }),
    min_workers: 1,
    max_workers: 6,
  });
  assert.equal(fleet.effectiveMaxWorkers, 6);
  assert.equal(fleet.plan(0).target_workers, 1); // floored at min_workers
  assert.equal(fleet.plan(3).target_workers, 3);
  assert.equal(fleet.plan(6).target_workers, 6);
  assert.equal(fleet.plan(1000).target_workers, 6); // fan-out stays bounded
});

test("adaptive_fleet_test: the budget concurrency limit caps the effective maximum", () => {
  const fleet = createAdaptiveFleet({
    envelope: budgetEnvelopeFixture({ hardLimits: { concurrency: 3 } }),
    min_workers: 0,
    max_workers: 3,
  });
  assert.equal(fleet.effectiveMaxWorkers, 3);
  assert.equal(fleet.plan(100).target_workers, 3);
});

test("adaptive_fleet_test: a declared maximum above the budget concurrency is refused", () => {
  assertCode(
    () =>
      createAdaptiveFleet({
        envelope: budgetEnvelopeFixture({ hardLimits: { concurrency: 4 } }),
        min_workers: 1,
        max_workers: 10,
      }),
    "FLEET_BOUND_EXCEEDS_BUDGET",
  );
});

test("adaptive_fleet_test: an advisory budget imposes no concurrency cap", () => {
  const fleet = createAdaptiveFleet({
    envelope: budgetEnvelopeFixture({ enforcement: "SOFT_ESTIMATE" }),
    min_workers: 2,
    max_workers: 12,
  });
  assert.equal(fleet.effectiveMaxWorkers, 12);
  assert.equal(fleet.plan(100).target_workers, 12);
});

test("adaptive_fleet_test: out-of-bounds and undeclared requests are refused", () => {
  const fleet = createAdaptiveFleet({
    envelope: budgetEnvelopeFixture({ hardLimits: { concurrency: 5 } }),
    min_workers: 2,
    max_workers: 5,
  });
  assert.equal(fleet.assertRequest(3).admitted, true);
  assertCode(() => fleet.assertRequest(6), "FLEET_BOUND_EXCEEDED");
  assertCode(() => fleet.assertRequest(1), "FLEET_BOUND_EXCEEDED");
  assertCode(() => fleet.plan(-1), "FLEET_CONTRACT_INVALID");
  assertCode(() => fleet.plan(2.5), "FLEET_CONTRACT_INVALID");
});

test("adaptive_fleet_test: malformed fleet specs are refused", () => {
  const envelope = budgetEnvelopeFixture();
  assertCode(
    () => createAdaptiveFleet({ envelope, min_workers: 5, max_workers: 3 }),
    "FLEET_CONTRACT_INVALID",
  );
  assertCode(
    () => createAdaptiveFleet({ envelope, min_workers: -1, max_workers: 3 }),
    "FLEET_CONTRACT_INVALID",
  );
  assertCode(
    () => createAdaptiveFleet({ envelope, min_workers: 0, max_workers: 0 }),
    "FLEET_CONTRACT_INVALID",
  );
  assertCode(
    () => createAdaptiveFleet({ envelope, min_workers: 1, max_workers: 3, extra: 1 }),
    "FLEET_CONTRACT_INVALID",
  );
  assertCode(
    () => createAdaptiveFleet({ envelope: { enforcement: "HARD_METERED" }, min_workers: 1, max_workers: 2 }),
    "BUDGET_ENVELOPE_INVALID",
  );
});

test("adaptive_fleet_test: plan receipts are deterministic and re-derivable", () => {
  const make = () =>
    createAdaptiveFleet({
      envelope: budgetEnvelopeFixture({ hardLimits: { concurrency: 8 } }),
      min_workers: 1,
      max_workers: 6,
    });
  const a = make().plan(4);
  const b = make().plan(4);
  assert.deepEqual(a, b);
  assert.equal(a.receipt_hash, b.receipt_hash);
  // Different backlog yields a different receipt.
  assert.notEqual(a.receipt_hash, make().plan(5).receipt_hash);
});

test("adaptive_fleet_test: the fleet acquires no authority", () => {
  const fleet = createAdaptiveFleet({
    envelope: budgetEnvelopeFixture({ hardLimits: { concurrency: 8 } }),
    min_workers: 1,
    max_workers: 4,
  });
  const receipt = fleet.plan(3);
  // A decision receipt is plain data: counts and hashes only, no leases or
  // capability grants.
  const keys = Object.keys(receipt).sort();
  assert.deepEqual(keys, [
    "backlog",
    "budget_hash",
    "concurrency_limit",
    "effective_max_workers",
    "enforcement",
    "max_workers",
    "min_workers",
    "receipt_hash",
    "target_workers",
  ]);
  assert.ok(Object.isFrozen(receipt));
});
