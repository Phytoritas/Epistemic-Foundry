// codex_adapter_test / unit and contract tests — what the adapter does with the
// payload that actually ships.
//
// The binding is read from `plugins/epistemic-foundry` as it is on disk.  This
// suite pins the three things the adapter is for: that the shipped payload binds
// to the Codex host, that the parts of it which cannot run at this revision are
// named rather than implied, and that a raw host event crosses into the canonical
// envelope carrying nothing the adapter invented.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  HOOK_COVERAGE,
  sha256HookJson,
} from "../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  ADAPTER_ROOT,
  BINDING_STATUS,
  canonicalRoleTable,
  describeRole,
  descriptorNameFor,
  deriveCoverage,
  deriveVerbIndex,
  dispatchRawCodexEvent,
  loadCodexBinding,
  PAYLOAD_ROOT,
  parseDispatcherTarget,
  REPOSITORY_ROOT,
  roleTableHash,
  toHookRequest,
  verifyBridgedEnvelope,
} from "./index.mjs";
import { rawEventFor, refusal, RUNTIME_TEMPLATE } from "./codex-fixtures.mjs";

/** Adapter product code; a launcher or a payload write in any of it is a failure. */
const PRODUCT_MODULES = Object.freeze([
  "codex-declarations.mjs",
  "hook-bridge.mjs",
  "index.mjs",
  "plugin-binding.mjs",
  "role-adapter.mjs",
]);

const binding = loadCodexBinding();
const readRepo = (relative) => readFileSync(join(REPOSITORY_ROOT, relative), "utf8");

test("x01_contract: the shipped payload binds, and what cannot run is named", () => {
  assert.equal(binding.status, BINDING_STATUS.DEGRADED);
  assert.deepEqual(
    binding.findings.map((row) => row.code),
    ["DISPATCHER_PAYLOAD_MISSING", "HOOK_COMMAND_TARGET_MISSING"],
  );
  assert.deepEqual(
    binding.findings.map((row) => row.path),
    ["dist/cli.mjs", "dist/hook-runner.mjs"],
  );
  assert.deepEqual(
    binding.findings.find((row) => row.code === "HOOK_COMMAND_TARGET_MISSING").event_types,
    [...binding.registeredEventTypes],
  );
});

test("x01_contract: every registration names a file the payload ships", () => {
  for (const relative of binding.declaration.hook_files) {
    assert.ok(binding.registrations.some((row) => row.hook_file === relative), relative);
    assert.doesNotThrow(() => readRepo(`${PAYLOAD_ROOT}/${relative}`));
  }
  assert.equal(binding.registrations.length, 8);
  for (const row of binding.registrations) {
    assert.match(row.verb, /^[a-z][a-z0-9-]*$/u);
    assert.equal(row.target, "dist/hook-runner.mjs");
  }
});

test("x01_contract: every declared entrypoint and asset exists in the payload", () => {
  assert.deepEqual(binding.entrypoints, [
    { field: "composerIcon", path: "assets/composer-icon.svg" },
    { field: "logo", path: "assets/logo.svg" },
    { field: null, path: "bin/efoundry.mjs" },
  ]);
  for (const row of binding.entrypoints) {
    assert.doesNotThrow(() => readRepo(`${PAYLOAD_ROOT}/${row.path}`));
  }
});

test("x01_contract: the dispatcher payload target is read from the dispatcher", () => {
  assert.equal(binding.dispatcherTarget, "dist/cli.mjs");
  assert.equal(
    parseDispatcherTarget(
      readRepo(`${PAYLOAD_ROOT}/${binding.declaration.dispatcher}`),
      binding.declaration.dispatcher,
    ),
    "dist/cli.mjs",
  );
  assert.equal(refusal(() => parseDispatcherTarget("no url here", "bin/x.mjs")).code,
    "DISPATCHER_UNREADABLE");
  assert.equal(
    refusal(() =>
      parseDispatcherTarget(
        'new URL("../a.mjs", import.meta.url); new URL("../b.mjs", import.meta.url)',
        "bin/x.mjs",
      ),
    ).code,
    "DISPATCHER_UNREADABLE",
  );
  assert.equal(
    refusal(() => parseDispatcherTarget('new URL("../../out.mjs", import.meta.url)', "bin/x.mjs"))
      .code,
    "DISPATCHER_UNREADABLE",
  );
});

test("x01_contract: coverage follows the matchers the registrations declare", () => {
  const coverage = binding.coverageByEventType;

  assert.equal(coverage.get("UserPromptSubmit"), binding.declaration.coverage_unrestricted);
  assert.equal(coverage.get("SubagentStart"), binding.declaration.coverage_unrestricted);
  assert.equal(coverage.get("PreToolUse"), binding.declaration.coverage_restricted);
  assert.equal(coverage.get("SessionStart"), binding.declaration.coverage_restricted);
  for (const eventType of binding.unregisteredEventTypes) {
    assert.equal(coverage.get(eventType), binding.declaration.coverage_unregistered);
  }
});

test("x01_contract: a widened matcher list widens coverage, so the rule is data", () => {
  const widened = deriveCoverage(
    { ...binding.declaration, unrestricted_matchers: ["Bash|apply_patch|Edit|Write|mcp__.*|Agent"] },
    binding.registrations,
    [...binding.coverageByEventType.keys()],
    HOOK_COVERAGE,
  );

  assert.equal(widened.get("PreToolUse"), binding.declaration.coverage_unrestricted);
  assert.equal(widened.get("SessionStart"), binding.declaration.coverage_restricted);
});

test("x01_contract: two event types cannot share one hook verb", () => {
  const error = refusal(() =>
    deriveVerbIndex([
      { event_type: "PreToolUse", hook_file: "hooks/a.json", matcher: null, target: "t", verb: "v" },
      { event_type: "PostToolUse", hook_file: "hooks/b.json", matcher: null, target: "t", verb: "v" },
    ]),
  );

  assert.equal(error.code, "HOOK_VERB_AMBIGUOUS");
  assert.deepEqual(error.context.event_types, ["PostToolUse", "PreToolUse"]);
});

test("x01_contract: translation copies the raw event and adds only what it read", () => {
  const raw = rawEventFor(binding);
  const request = toHookRequest(binding, raw);

  assert.equal(request.event_id, raw.event_id);
  assert.equal(request.host, raw.host);
  assert.equal(request.received_at, raw.received_at);
  assert.equal(request.session_id, raw.session_id);
  assert.equal(request.tool_name, raw.tool_name);
  assert.deepEqual(request.raw_payload, raw.payload);
  assert.equal(request.event_type, binding.eventTypeByVerb.get(raw.hook));
  assert.equal(request.coverage, binding.coverageByEventType.get(request.event_type));
});

test("x01_contract: the bridged envelope is the gateway's, and it re-validates", async () => {
  const raw = rawEventFor(binding);
  const envelope = await dispatchRawCodexEvent(binding, raw, RUNTIME_TEMPLATE);

  assert.equal(envelope.host, binding.adapterHost);
  assert.equal(envelope.event_type, "PreToolUse");
  assert.equal(envelope.event_id, raw.event_id);
  assert.equal(envelope.received_at, raw.received_at);
  assert.equal(envelope.raw_payload_hash, sha256HookJson(raw.payload));
  assert.deepEqual(envelope.normalized_payload, raw.payload);
  assert.equal(envelope.decision, "ADVISORY");
  assert.deepEqual(verifyBridgedEnvelope(envelope), envelope);
});

test("x01_contract: the same raw event always bridges to the same envelope", async () => {
  const raw = rawEventFor(binding);
  const first = await dispatchRawCodexEvent(binding, raw, RUNTIME_TEMPLATE);
  const second = await dispatchRawCodexEvent(binding, raw, RUNTIME_TEMPLATE);

  assert.equal(first.envelope_hash, second.envelope_hash);
});

test("x01_contract: a descriptor carries the bounded scopes its RoleSpec declares", () => {
  const descriptor = describeRole(binding.roleTable, "validation_executor");

  assert.equal(
    descriptor.name,
    descriptorNameFor(binding.declaration.descriptor_name_prefix, "validation_executor"),
  );
  assert.equal(descriptor.agent_type, "worker");
  assert.deepEqual(descriptor.write_scope, ["artifacts/validation/**"]);
  assert.deepEqual(descriptor.tool_acl, ["sandbox.execute", "artifact.read", "artifact.write"]);
  assert.equal(descriptor.output_schema_ref, "schemas/result-envelope.schema.json");
  assert.equal(descriptor.independent_review_required, false);
  assert.equal(descriptor.default_timeout_seconds, 1200);
  assert.ok(Object.isFrozen(descriptor));
});

test("x01_contract: a role the registry does not declare has no descriptor", () => {
  const error = refusal(() => describeRole(binding.roleTable, "shadow_promoter"));

  assert.equal(error.code, "ROLE_UNDECLARED");
  assert.equal(error.context.role_id, "shadow_promoter");
});

test("x01_contract: regenerating the descriptor table is byte-stable", () => {
  const rebuilt = loadCodexBinding().roleTable;

  assert.equal(canonicalRoleTable(rebuilt), canonicalRoleTable(binding.roleTable));
  assert.equal(roleTableHash(rebuilt), roleTableHash(binding.roleTable));
  assert.match(roleTableHash(binding.roleTable), /^sha256:[0-9a-f]{64}$/u);
});

test("x01_contract: the adapter launches nothing and writes nothing", () => {
  for (const relative of PRODUCT_MODULES) {
    const source = readRepo(`${ADAPTER_ROOT}/${relative}`);
    for (const forbidden of [
      "node:child_process",
      "spawnSync",
      "execSync",
      "writeFileSync",
      "rmSync",
      "mkdirSync",
    ]) {
      assert.ok(!source.includes(forbidden), `${relative}: ${forbidden}`);
    }
  }
});
