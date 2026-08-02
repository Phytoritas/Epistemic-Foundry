// provenance_and_receipt_audit — H05 can prove what it read and what it missed.
//
// An observability surface that cannot name its inputs is an opinion, and one
// that cannot name its gaps is a liability.  The receipt binds every declaring
// source by the gateway's own canonical-JSON digest, publishes the explicit
// `not_observed` list beside the coverage it does claim, records that the
// projection is not wired into the plugin manifest, and re-derives its own hash
// from exactly the fields it publishes.  It carries no clock and no randomness,
// so the same repository always produces the same receipt and a changed input
// always produces a different one.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  HOOK_COVERAGE,
  HOOK_DECISIONS,
  HOOK_EVENT_TYPES,
  HOOK_HOSTS,
  sha256HookJson,
} from "../../../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  coverageReport,
  DECLARING_SOURCES,
  loadObservability,
  observabilityReceipt,
  observeEvolutionEvent,
  projectHookBundle,
  REPOSITORY_ROOT,
} from "./index.mjs";
import {
  byId,
  CLEAN_PAYLOAD,
  OBSERVATION_TEMPLATE,
  stageRegistrations,
} from "./observability-fixtures.mjs";

const loaded = loadObservability();
const receipt = observabilityReceipt(loaded);
const report = coverageReport(loaded);
const textHashOf = (relative) =>
  sha256HookJson(readFileSync(join(REPOSITORY_ROOT, relative), "utf8"));

test("h05_receipt: the receipt re-derives its own hash from the fields it publishes", () => {
  const preimage = { ...receipt };
  delete preimage.receipt_id;
  delete preimage.receipt_hash;

  assert.equal(sha256HookJson(preimage), receipt.receipt_hash);
});

test("h05_receipt: the receipt identifier is derived from the hash", () => {
  assert.equal(receipt.receipt_id, `EFH05-OBSERVABILITY-${receipt.receipt_hash.slice(7, 23)}`);
  assert.match(receipt.receipt_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("h05_receipt: the same repository yields the same receipt", () => {
  assert.deepEqual(observabilityReceipt(loadObservability()), receipt);
});

test("h05_receipt: every declaring source is bound by its actual digest", () => {
  assert.deepEqual(
    receipt.declaring_sources.map((row) => row.path),
    [...DECLARING_SOURCES].sort(),
  );
  for (const row of receipt.declaring_sources) {
    assert.equal(row.text_hash, textHashOf(row.path));
    assert.match(row.text_hash, /^sha256:[0-9a-f]{64}$/u);
  }
});

test("h05_receipt: a changed registration set changes the receipt", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    declaration.registration_set_version = "4.0.0-h05.2";
  });
  const changed = observabilityReceipt(loadObservability({ root }));

  assert.notEqual(changed.receipt_hash, receipt.receipt_hash);
  assert.equal(changed.registration_set_version, "4.0.0-h05.2");
});

test("h05_receipt: dropping a registration changes the receipt and widens the gap", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    declaration.registrations = declaration.registrations.filter(
      (row) => row.registration_id !== "EFH05-OBS-HOLDOUT-STOP",
    );
  });
  const changed = observabilityReceipt(loadObservability({ root }));

  assert.notEqual(changed.receipt_hash, receipt.receipt_hash);
  assert.equal(changed.coverage_by_event_type.Stop, "UNOBSERVED");
  assert.ok(changed.not_observed.includes("claude:Stop"));
  assert.equal(changed.not_observed.length, receipt.not_observed.length + 1);
});

test("h05_receipt: the gateway vocabulary is republished, not restated", () => {
  assert.deepEqual(receipt.gateway_vocabulary.coverage, [...HOOK_COVERAGE]);
  assert.deepEqual(receipt.gateway_vocabulary.decisions, [...HOOK_DECISIONS]);
  assert.deepEqual(receipt.gateway_vocabulary.event_types, [...HOOK_EVENT_TYPES]);
  assert.deepEqual(receipt.gateway_vocabulary.hosts, [...HOOK_HOSTS]);
});

test("h05_receipt: what is not observed is recorded rather than implied", () => {
  assert.deepEqual(receipt.not_observed, [...report.not_observed]);
  assert.deepEqual(receipt.hosts_never_observed, ["other"]);
  assert.equal(receipt.observed_pair_count, 5);
  assert.equal(
    receipt.not_observed.length + receipt.observed_pair_count,
    HOOK_HOSTS.length * HOOK_EVENT_TYPES.length,
  );
});

test("h05_receipt: no event type is published as fully covered", () => {
  for (const [eventType, coverage] of Object.entries(receipt.coverage_by_event_type)) {
    assert.notEqual(coverage, "OBSERVED", eventType);
    assert.ok(HOOK_COVERAGE.includes(coverage), eventType);
  }
});

test("h05_receipt: the holdout material observability never reads is named", () => {
  assert.deepEqual(receipt.holdout_denied_access_flags, [
    "backend_access",
    "candidate_access",
    "mutation_model_access",
    "prompt_access",
  ]);
  for (const flag of receipt.holdout_denied_access_flags) {
    assert.ok(receipt.holdout_isolated_fields.includes(flag), flag);
  }
  assert.ok(receipt.holdout_isolated_fields.includes("hidden_partition_handles"));
});

test("h05_receipt: the projected bundle is bound by hash and is re-derivable", () => {
  assert.equal(receipt.projected_bundle_hash, sha256HookJson(projectHookBundle(loaded)));
  assert.equal(receipt.registration_count, loaded.declaration.registrations.length);
  assert.deepEqual(receipt.registration_ids, [...loaded.registrationIds]);
});

test("h05_receipt: the receipt records that the plugin manifest does not load it", () => {
  assert.equal(receipt.plugin_manifest_wired, false);
  assert.equal(receipt.plugin_manifest_hook_count, 7);
});

test("h05_receipt: a changed projection changes the bundle hash and the receipt", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-EVOLUTION-PRE-TOOL").timeout_seconds = 11;
  });
  const changed = observabilityReceipt(loadObservability({ root }));

  assert.notEqual(changed.projected_bundle_hash, receipt.projected_bundle_hash);
  assert.notEqual(changed.receipt_hash, receipt.receipt_hash);
});

test("h05_receipt: an observation envelope re-derives its own hash", async () => {
  const envelope = await observeEvolutionEvent(loaded, {
    ...OBSERVATION_TEMPLATE,
    payload: CLEAN_PAYLOAD,
  });
  const preimage = { ...envelope };
  delete preimage.envelope_hash;

  assert.equal(sha256HookJson(preimage), envelope.envelope_hash);
  assert.equal(sha256HookJson(CLEAN_PAYLOAD), envelope.raw_payload_hash);
});

test("h05_receipt: the observability module holds no clock and no randomness", () => {
  const source = readFileSync(
    join(REPOSITORY_ROOT, "plugin_blueprint/epistemic-foundry/hooks/v4_h05/observability.mjs"),
    "utf8",
  );

  for (const forbidden of ["Date.now", "new Date", "Math.random", "process.env"]) {
    assert.ok(!source.includes(forbidden), forbidden);
  }
});

test("h05_receipt: the receipt is canonical JSON and frozen", () => {
  assert.ok(Object.isFrozen(receipt));
  assert.deepEqual(JSON.parse(JSON.stringify(receipt)), { ...receipt });
  assert.equal(sha256HookJson(JSON.parse(JSON.stringify(receipt))), sha256HookJson(receipt));
});
