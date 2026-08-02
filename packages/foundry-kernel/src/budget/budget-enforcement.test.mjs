// budget_enforcement_test — typed budgets are ENFORCED, not truncated (EF4-I28,
// Y01). Over-budget reservations are refused; under-budget reservations are
// admitted; hard/soft/unmetered enforcement states stay truthful; malformed and
// undeclared budget input is refused; receipts are deterministic and
// re-derivable. The budget vocabulary is composed from the sealed contract
// registry, never restated.

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { contractByTitle } from "@epistemic-foundry/contracts";

import {
  BudgetControlError,
  budgetVocabulary,
  createBudgetMeter,
  deriveBudgetVocabulary,
  enforcementBoundsSpend,
  sealBudgetEnvelope,
  spendIsBounded,
} from "./index.mjs";
import { budgetEnvelopeFixture, reservationFixture } from "./budget-test-support.mjs";

const ROOT = fileURLToPath(new URL("../../../../", import.meta.url));
const SCHEMA_PATH = join(ROOT, "schemas", "budget-envelope.schema.json");

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

test("budget_enforcement_test: vocabulary is composed from the sealed registry", () => {
  const vocab = budgetVocabulary();
  assert.deepEqual(vocab.enforcement_labels, [
    "HARD_METERED",
    "HARD_PREALLOCATED",
    "SOFT_ESTIMATE",
    "UNMETERED",
  ]);
  assert.deepEqual(vocab.bounding_enforcement, ["HARD_METERED", "HARD_PREALLOCATED"]);
  assert.deepEqual(vocab.advisory_enforcement, ["SOFT_ESTIMATE", "UNMETERED"]);
  assert.deepEqual(vocab.limit_dimensions, [
    "tokens",
    "calls",
    "wall_seconds",
    "concurrency",
    "storage_bytes",
    "network_bytes",
  ]);
  // concurrency is a fleet gauge, not a cumulative meter dimension.
  assert.ok(!vocab.reservation_dimensions.includes("concurrency"));
});

test("budget_enforcement_test: composed vocabulary tracks the canonical schema bytes", () => {
  const entry = contractByTitle.get("BudgetEnvelope");
  const digest = createHash("sha256").update(readFileSync(SCHEMA_PATH)).digest("hex");
  assert.equal(entry.source_sha256, `sha256:${digest}`);
  assert.equal(budgetVocabulary().source_sha256, `sha256:${digest}`);
});

test("budget_enforcement_test: a tampered budget contract is refused", () => {
  const base = contractByTitle.get("BudgetEnvelope");
  const wrongTitle = structuredClone(base);
  wrongTitle.title = "NotBudget";
  assertCode(() => deriveBudgetVocabulary(wrongTitle), "BUDGET_VOCABULARY_INVALID");

  const noEnum = structuredClone(base);
  noEnum.properties = noEnum.properties.filter((p) => p.name !== "enforcement");
  assertCode(() => deriveBudgetVocabulary(noEnum), "BUDGET_VOCABULARY_INVALID");
});

test("budget_enforcement_test: an under-budget reservation is admitted", () => {
  const meter = createBudgetMeter({ envelope: budgetEnvelopeFixture() });
  assert.equal(meter.spendIsBounded(), true);
  const receipt = meter.charge(reservationFixture({ tokens: 500, calls: 1 }));
  assert.equal(receipt.usage_after.tokens, 500);
  assert.equal(receipt.usage_after.calls, 1);
  assert.equal(meter.remaining("calls"), 19);
});

test("budget_enforcement_test: an over-budget reservation is refused, not truncated", () => {
  const meter = createBudgetMeter({
    envelope: budgetEnvelopeFixture({ hardLimits: { tokens: 1000 } }),
  });
  meter.charge(reservationFixture({ tokens: 800 }));

  const error = assertCode(
    () => meter.charge(reservationFixture({ tokens: 300 })),
    "BUDGET_LIMIT_EXCEEDED",
  );
  assert.equal(error.details.dimension, "tokens");
  assert.equal(error.details.limit, 1000);
  // Refusal must not partially apply: usage is unchanged after the refusal.
  assert.equal(meter.usage().tokens, 800);
  assert.equal(meter.remaining("tokens"), 200);
});

test("budget_enforcement_test: the call-count (compute) dimension is enforced", () => {
  const meter = createBudgetMeter({
    envelope: budgetEnvelopeFixture({ hardLimits: { calls: 2 } }),
  });
  meter.charge(reservationFixture({ calls: 1 }));
  meter.charge(reservationFixture({ calls: 1 }));
  assertCode(() => meter.charge(reservationFixture({ calls: 1 })), "BUDGET_LIMIT_EXCEEDED");
});

test("budget_enforcement_test: the wall-time dimension is enforced", () => {
  const meter = createBudgetMeter({
    envelope: budgetEnvelopeFixture({ hardLimits: { wall_seconds: 90 } }),
  });
  meter.charge(reservationFixture({ wall_seconds: 60 }));
  assertCode(() => meter.charge(reservationFixture({ wall_seconds: 60 })), "BUDGET_LIMIT_EXCEEDED");
});

test("budget_enforcement_test: soft and unmetered states are truthful and never refuse", () => {
  const soft = createBudgetMeter({ envelope: budgetEnvelopeFixture({ enforcement: "SOFT_ESTIMATE" }) });
  assert.equal(soft.spendIsBounded(), false);
  assert.equal(enforcementBoundsSpend("SOFT_ESTIMATE"), false);
  // A forecast is recorded but never bounds spend.
  const softReceipt = soft.charge(reservationFixture({ tokens: 10 ** 9 }));
  assert.equal(softReceipt.spend_bounded, false);
  assert.equal(soft.remaining("tokens"), null);

  const unmetered = createBudgetMeter({ envelope: budgetEnvelopeFixture({ enforcement: "UNMETERED" }) });
  assert.equal(unmetered.spendIsBounded(), false);
  assert.doesNotThrow(() => unmetered.charge(reservationFixture({ calls: 10 ** 6 })));
});

test("budget_enforcement_test: mislabeled envelopes are refused at seal time", () => {
  const dims = budgetVocabulary().limit_dimensions;
  const nulls = Object.fromEntries(dims.map((k) => [k, null]));

  // HARD enforcement with no hard limit claims a bound nothing enforces.
  assertCode(
    () =>
      sealBudgetEnvelope({
        budget_id: "BUD-Y01-bad",
        enforcement: "HARD_METERED",
        hard_limits: nulls,
        soft_cost_currency: null,
        soft_cost_amount: null,
        metering_authority: "METER",
        breach_policy: "CANCEL",
        created_at: "2026-07-31T00:00:00.000Z",
      }),
    "BUDGET_ENVELOPE_INVALID",
  );

  // UNMETERED cannot carry a CANCEL breach policy: there is no meter to breach.
  assertCode(
    () =>
      sealBudgetEnvelope({
        budget_id: "BUD-Y01-bad2",
        enforcement: "UNMETERED",
        hard_limits: nulls,
        soft_cost_currency: null,
        soft_cost_amount: null,
        metering_authority: null,
        breach_policy: "CANCEL",
        created_at: "2026-07-31T00:00:00.000Z",
      }),
    "BUDGET_ENVELOPE_INVALID",
  );
});

test("budget_enforcement_test: malformed reservations and envelopes are refused", () => {
  const meter = createBudgetMeter({ envelope: budgetEnvelopeFixture() });
  assertCode(() => meter.charge({ tokens: 1 }), "BUDGET_RESERVATION_INVALID");
  assertCode(() => meter.charge(reservationFixture({ tokens: -1 })), "BUDGET_RESERVATION_INVALID");
  assertCode(() => meter.charge(reservationFixture({ tokens: 1.5 })), "BUDGET_RESERVATION_INVALID");
  assertCode(
    () => meter.charge({ ...reservationFixture(), surprise: 1 }),
    "BUDGET_RESERVATION_INVALID",
  );

  // An undeclared / unsealed envelope cannot create a meter.
  assertCode(() => createBudgetMeter({ envelope: { enforcement: "HARD_METERED" } }), "BUDGET_ENVELOPE_INVALID");
});

test("budget_enforcement_test: a tampered budget_hash is rejected", () => {
  const sealed = budgetEnvelopeFixture();
  const tampered = { ...sealed, budget_id: "BUD-Y01-tampered" };
  assertCode(() => createBudgetMeter({ envelope: tampered }), "BUDGET_HASH_MISMATCH");
});

test("budget_enforcement_test: receipts are deterministic and re-derivable", () => {
  const build = () => {
    const meter = createBudgetMeter({ envelope: budgetEnvelopeFixture() });
    return [
      meter.charge(reservationFixture({ tokens: 100 })),
      meter.charge(reservationFixture({ tokens: 200 })),
    ];
  };
  const first = build();
  const second = build();
  assert.deepEqual(first, second);
  assert.equal(first[0].receipt_hash, second[0].receipt_hash);
  assert.notEqual(first[0].receipt_hash, first[1].receipt_hash);
  assert.equal(first[1].usage_after.tokens, 300);
  assert.equal(spendIsBounded(budgetEnvelopeFixture()), true);
});
