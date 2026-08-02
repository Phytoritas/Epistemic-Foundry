// codex_hook_coverage_test / provenance and receipt audit — the adapter can
// prove what it read and what it could not observe.
//
// A host binding that cannot name its inputs is an opinion.  The receipt binds
// every declaring source by digest, re-derives its own hash from exactly the
// fields it publishes, publishes the coverage of every canonical event type
// including the ones this payload registers for none, and carries no clock and
// no randomness — so the same repository always produces the same receipt and a
// changed input always produces a different one.

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  HOOK_COVERAGE,
  HOOK_EVENT_TYPES,
  sha256HookJson,
} from "../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  ADAPTER_ROOT,
  BINDING_SOURCE_PATHS,
  codexBindingReceipt,
  loadCodexBinding,
  PAYLOAD_ROOT,
  REPOSITORY_ROOT,
  roleTableHash,
} from "./index.mjs";
import { stageDeclaration } from "./codex-fixtures.mjs";

/** Adapter product code; a clock or a random number in any of it is a failure. */
const PRODUCT_MODULES = Object.freeze([
  "codex-declarations.mjs",
  "hook-bridge.mjs",
  "index.mjs",
  "plugin-binding.mjs",
  "role-adapter.mjs",
]);

const binding = loadCodexBinding();
const receipt = codexBindingReceipt(binding);
const digestOf = (relative) =>
  `sha256:${createHash("sha256").update(readFileSync(join(REPOSITORY_ROOT, relative))).digest("hex")}`;

test("x01_receipt: the receipt re-derives its own hash from the fields it publishes", () => {
  const preimage = { ...receipt };
  delete preimage.receipt_id;
  delete preimage.receipt_hash;

  assert.equal(sha256HookJson(preimage), receipt.receipt_hash);
});

test("x01_receipt: the receipt identifier is derived from the hash", () => {
  assert.equal(receipt.receipt_id, `EFX01-CODEX-${receipt.receipt_hash.slice(7, 23)}`);
  assert.match(receipt.receipt_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("x01_receipt: the same repository yields the same receipt", () => {
  assert.deepEqual(codexBindingReceipt(loadCodexBinding()), receipt);
});

test("x01_receipt: every declaring source is bound by its actual digest", () => {
  const expected = [
    ...BINDING_SOURCE_PATHS,
    ...binding.declaration.hook_files.map((relative) => `${PAYLOAD_ROOT}/${relative}`),
    `${PAYLOAD_ROOT}/${binding.declaration.dispatcher}`,
  ].sort();

  assert.deepEqual(
    receipt.sources.map((row) => row.path),
    expected,
  );
  assert.equal(receipt.sources.length, 9);
  for (const row of receipt.sources) assert.equal(row.sha256, digestOf(row.path));
});

test("x01_receipt: a changed declaration changes the receipt", (t) => {
  const root = stageDeclaration(t, (declaration) => {
    declaration.adapter_version = "4.0.0-x01.2";
  });
  const changed = codexBindingReceipt(loadCodexBinding({ root }));

  assert.notEqual(changed.receipt_hash, receipt.receipt_hash);
  assert.equal(changed.adapter_version, "4.0.0-x01.2");
});

test("x01_receipt: coverage is published for every canonical event type", () => {
  assert.deepEqual(
    receipt.coverage_by_event_type.map((row) => row.event_type),
    [...HOOK_EVENT_TYPES].sort(),
  );
  for (const row of receipt.coverage_by_event_type) {
    assert.ok(HOOK_COVERAGE.includes(row.coverage), row.event_type);
  }
});

test("x01_receipt: the event types this payload observes for nothing are named", () => {
  assert.deepEqual(receipt.unregistered_event_types, ["PreCompact", "SessionEnd", "Stop"]);
  for (const eventType of receipt.unregistered_event_types) {
    const row = receipt.coverage_by_event_type.find((entry) => entry.event_type === eventType);
    assert.equal(row.coverage, binding.declaration.coverage_unregistered);
  }
  assert.deepEqual(receipt.registered_event_types, [
    "PermissionRequest",
    "PostCompact",
    "PostToolUse",
    "PreToolUse",
    "SessionStart",
    "SubagentStart",
    "SubagentStop",
    "UserPromptSubmit",
  ]);
});

test("x01_receipt: the runtime the payload has not built is recorded, not implied", () => {
  assert.equal(receipt.binding_status, "DEGRADED");
  assert.deepEqual(receipt.findings, [
    { code: "DISPATCHER_PAYLOAD_MISSING", event_types: [], path: "dist/cli.mjs" },
    {
      code: "HOOK_COMMAND_TARGET_MISSING",
      event_types: [...receipt.registered_event_types],
      path: "dist/hook-runner.mjs",
    },
  ]);
  assert.equal(receipt.dispatcher_target, "dist/cli.mjs");
});

test("x01_receipt: the receipt binds the payload identity and the role table", () => {
  assert.equal(receipt.plugin_name, binding.declaration.plugin_name);
  assert.equal(receipt.plugin_version, "4.0.0");
  assert.equal(receipt.adapter_host, binding.adapterHost);
  assert.equal(receipt.role_count, 28);
  assert.equal(receipt.role_table_hash, roleTableHash(binding.roleTable));
});

test("x01_receipt: every hook verb the receipt publishes maps to a registered type", () => {
  assert.equal(receipt.hook_verbs.length, 8);
  assert.equal(receipt.registration_count, 8);
  for (const row of receipt.hook_verbs) {
    assert.ok(receipt.registered_event_types.includes(row.event_type), row.verb);
  }
});

test("x01_receipt: the adapter holds no clock and no randomness", () => {
  for (const relative of PRODUCT_MODULES) {
    const source = readFileSync(join(REPOSITORY_ROOT, ADAPTER_ROOT, relative), "utf8");
    for (const forbidden of ["Date.now", "new Date", "Math.random", "process.env", "process.argv"]) {
      assert.ok(!source.includes(forbidden), `${relative}: ${forbidden}`);
    }
  }
});

test("x01_receipt: the receipt is canonical JSON and frozen", () => {
  assert.deepEqual(JSON.parse(JSON.stringify(receipt)), { ...receipt });
  assert.ok(Object.isFrozen(receipt));
  assert.equal(sha256HookJson(receipt), sha256HookJson(JSON.parse(JSON.stringify(receipt))));
});
