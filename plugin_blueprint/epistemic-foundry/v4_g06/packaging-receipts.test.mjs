// provenance_and_receipt_audit — the package can prove what it read, and every
// degradation resolves to an immutable receipt.
//
// A packaging gate that cannot name its inputs is an opinion.  The receipt binds
// every declaring source by digest, re-derives its own hash from exactly the
// fields it publishes, and carries no clock and no randomness, so the same
// repository always produces the same receipt and a changed input always
// produces a different one.  An integration that blocks is recorded, not thrown.

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import { sha256HookJson } from "../../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  CAPABILITY_MANIFEST_SCHEMA_PATH,
  integratePackage,
  INVENTORY_PATH,
  loadPackage,
  MANIFEST_PATH,
  MCP_CONFIG_PATH,
  packagingReceipt,
  REPOSITORY_ROOT,
  SKILL_LOCKFILE_SCHEMA_PATH,
  SURFACE_PATH,
} from "./index.mjs";
import { healthyObservation, stageManifest, withCapabilityState } from "./packaging-fixtures.mjs";

const loaded = loadPackage();
const receipt = packagingReceipt(loaded);
const digestOf = (relative) =>
  `sha256:${createHash("sha256").update(readFileSync(join(REPOSITORY_ROOT, relative))).digest("hex")}`;

test("g06_receipt: the receipt re-derives its own hash from the fields it publishes", () => {
  const preimage = { ...receipt };
  delete preimage.receipt_id;
  delete preimage.receipt_hash;

  assert.equal(sha256HookJson(preimage), receipt.receipt_hash);
});

test("g06_receipt: the receipt identifier is derived from the hash", () => {
  assert.equal(receipt.receipt_id, `EFG06-PACKAGE-${receipt.receipt_hash.slice(7, 23)}`);
  assert.match(receipt.receipt_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("g06_receipt: the same repository yields the same receipt", () => {
  assert.deepEqual(packagingReceipt(loadPackage()), receipt);
});

test("g06_receipt: every declaring source is bound by its actual digest", () => {
  const expected = [
    MANIFEST_PATH,
    CAPABILITY_MANIFEST_SCHEMA_PATH,
    SKILL_LOCKFILE_SCHEMA_PATH,
    INVENTORY_PATH,
    SURFACE_PATH,
    MCP_CONFIG_PATH,
    ...loaded.manifest.hookBundles.map(
      (bundle) => `plugin_blueprint/epistemic-foundry/hooks/${bundle}.json`,
    ),
  ].sort();

  assert.deepEqual(
    receipt.sources.map((row) => row.path),
    expected,
  );
  for (const row of receipt.sources) assert.equal(row.sha256, digestOf(row.path));
});

test("g06_receipt: a changed manifest changes the receipt", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.schema_version = "5";
  });
  const changed = packagingReceipt(loadPackage({ root }));

  assert.notEqual(changed.receipt_hash, receipt.receipt_hash);
  assert.equal(changed.schema_version, "5");
});

test("g06_receipt: the authority the package denies and the commands that carry it are named", () => {
  assert.deepEqual(receipt.denied_authority, ["evaluator_mutation", "holdout_read", "promotion"]);
  assert.deepEqual(receipt.authority_bearing_commands, ["claim promote", "passport publish"]);
  assert.deepEqual(receipt.authority_bearing_commands_projected, [
    "claim promote",
    "passport publish",
  ]);
  for (const command of receipt.authority_bearing_commands) {
    assert.ok(!receipt.required_capabilities.includes(command));
    assert.ok(!receipt.optional_capabilities.includes(command));
  }
});

test("g06_receipt: the receipt records the discovery reality it found", () => {
  assert.equal(receipt.discoverable_skill_count, 29);
  assert.equal(receipt.discoverable_skills.length, 29);
  assert.equal(receipt.cli_command_count, 22);
  assert.equal(receipt.evolution_backend_skill, "foundry-shinka-adapter");
  assert.equal(receipt.inventory_hash, loaded.inventoryHash);
});

test("g06_receipt: the hook-event scope is published, derived from H05", () => {
  assert.deepEqual(receipt.declared_hook_events, [...loaded.declaredHookEvents]);
  assert.ok(receipt.declared_hook_events.length > 0);
});

test("g06_integration: a FULL integration receipt re-derives its own hash", () => {
  const { receipt: integration } = integratePackage(loaded, healthyObservation(loaded));
  const preimage = { ...integration };
  delete preimage.integration_id;
  delete preimage.receipt_hash;

  assert.equal(sha256HookJson(preimage), integration.receipt_hash);
  assert.equal(integration.mode, "FULL");
  assert.equal(integration.overall, "PASS");
});

test("g06_integration: a blocked integration is recorded as an immutable receipt", () => {
  const { receipt: integration, report, health } = integratePackage(
    loaded,
    withCapabilityState(loaded, "plugin_cli", "UNSUPPORTED"),
  );

  assert.equal(integration.mode, "BLOCKED");
  assert.equal(integration.overall, "FAIL");
  assert.ok(integration.blockers.length > 0);
  assert.equal(integration.capability_report_hash, report.report_hash);
  assert.equal(integration.health_report_hash, health.report_hash);

  const preimage = { ...integration };
  delete preimage.integration_id;
  delete preimage.receipt_hash;
  assert.equal(sha256HookJson(preimage), integration.receipt_hash);
});

test("g06_integration: the same observation yields the same integration receipt", () => {
  const first = integratePackage(loaded, healthyObservation(loaded));
  const second = integratePackage(loaded, healthyObservation(loaded));

  assert.deepEqual(first.receipt, second.receipt);
});

test("g06_receipt: the packaging surface holds no clock and no randomness", () => {
  const source = readFileSync(
    join(REPOSITORY_ROOT, "plugin_blueprint/epistemic-foundry/v4_g06/packaging.mjs"),
    "utf8",
  );

  for (const forbidden of ["Date.now", "new Date", "Math.random", "process.env"]) {
    assert.ok(!source.includes(forbidden), forbidden);
  }
});

test("g06_receipt: the receipt is canonical JSON", () => {
  assert.deepEqual(JSON.parse(JSON.stringify(receipt)), { ...receipt });
});
