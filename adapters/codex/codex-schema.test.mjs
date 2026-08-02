// codex_adapter_test / schema and type check — the adapter reads its vocabulary,
// it never restates it.
//
// Every set this adapter binds has a declaring source: the hook event types,
// hosts and coverage classes come from the sealed hook gateway, the role
// vocabulary from `manifests/role_registry.yaml`, the host compilation choice
// from `adapters/codex/role_mapping.yaml`, and the registration set from the
// plugin payload itself.  A declaring source that changes must break this suite
// rather than leave an adapter describing a plugin that no longer exists.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  HOOK_COVERAGE,
  HOOK_EVENT_TYPES,
  HOOK_HOSTS,
} from "../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  ADAPTER_ROOT,
  BINDING_DECLARATION_PATH,
  buildRoleDescriptorTable,
  CodexAdapterError,
  DECLARATION_FIELDS,
  DESCRIPTOR_FIELDS,
  FINDING_CODES,
  HOOK_REQUEST_FIELDS,
  loadCodexBinding,
  parseRoleMapping,
  parseRoleRegistry,
  promptSourceFor,
  RAW_EVENT_FIELDS,
  REPOSITORY_ROOT,
  ROLE_MAPPING_FIELDS,
  ROLE_MAPPING_PATH,
  ROLE_REGISTRY_FIELDS,
  ROLE_REGISTRY_PATH,
  selectDeclared,
  toHookRequest,
} from "./index.mjs";
import { rawEventFor, refusal } from "./codex-fixtures.mjs";

/** Every module that ships as adapter product code, tests and fixtures aside. */
const PRODUCT_MODULES = Object.freeze([
  "codex-declarations.mjs",
  "hook-bridge.mjs",
  "index.mjs",
  "plugin-binding.mjs",
  "role-adapter.mjs",
]);

const binding = loadCodexBinding();
const readRepo = (relative) => readFileSync(join(REPOSITORY_ROOT, relative), "utf8");
const registry = parseRoleRegistry(readRepo(ROLE_REGISTRY_PATH));
const mapping = parseRoleMapping(readRepo(ROLE_MAPPING_PATH));

test("x01_schema: every finding code carries a code and a reason", () => {
  assert.equal(Object.keys(FINDING_CODES).length, 22);

  for (const [code, reason] of Object.entries(FINDING_CODES)) {
    assert.equal(code, code.toUpperCase());
    assert.ok(reason.length > 50, code);
  }
});

test("x01_schema: the adapter host is one the hook gateway declares", () => {
  assert.ok(HOOK_HOSTS.includes(binding.adapterHost));
  assert.equal(binding.adapterHost, binding.declaration.declared_host);
  assert.equal(
    HOOK_HOSTS.filter((entry) => entry === binding.declaration.declared_host).length,
    1,
  );
});

test("x01_schema: no product module restates the host the gateway declares", () => {
  const literal = new RegExp(`["']${binding.adapterHost}["']`, "u");

  for (const relative of PRODUCT_MODULES) {
    const source = readRepo(`${ADAPTER_ROOT}/${relative}`);
    assert.ok(!literal.test(source), relative);
  }
  assert.match(readRepo(BINDING_DECLARATION_PATH), literal);
});

test("x01_schema: an undeclared value is refused rather than defaulted", () => {
  const error = refusal(() =>
    selectDeclared(HOOK_HOSTS, "not-a-host", "declared_host", "HOOK_HOST_UNDECLARED"),
  );

  assert.ok(error instanceof CodexAdapterError);
  assert.equal(error.code, "HOOK_HOST_UNDECLARED");
  assert.deepEqual(error.context.declared, [...HOOK_HOSTS]);
  assert.equal(refusal(() => selectDeclared([], "x", "l", "HOOK_HOST_UNDECLARED")).code,
    "HOOK_HOST_UNDECLARED");
});

test("x01_schema: every registered event type is one the gateway declares", () => {
  for (const eventType of binding.registeredEventTypes) {
    assert.ok(HOOK_EVENT_TYPES.includes(eventType), eventType);
  }
  assert.deepEqual(
    [...binding.registeredEventTypes, ...binding.unregisteredEventTypes].sort(),
    [...HOOK_EVENT_TYPES].sort(),
  );
  assert.equal(binding.registeredEventTypes.length, 8);
  assert.equal(binding.unregisteredEventTypes.length, 3);
});

test("x01_schema: every published coverage class is one the gateway declares", () => {
  for (const coverage of binding.coverageByEventType.values()) {
    assert.ok(HOOK_COVERAGE.includes(coverage), coverage);
  }
  assert.equal(binding.coverageByEventType.size, HOOK_EVENT_TYPES.length);
  for (const key of ["coverage_restricted", "coverage_unregistered", "coverage_unrestricted"]) {
    assert.ok(HOOK_COVERAGE.includes(binding.declaration[key]), key);
  }
});

test("x01_schema: the binding declaration is exactly the fields the loader requires", () => {
  assert.deepEqual(Object.keys(binding.declaration).sort(), [...DECLARATION_FIELDS].sort());
  for (const key of ["entrypoints", "hook_files", "manifest_asset_fields", "unrestricted_matchers"]) {
    const value = binding.declaration[key];
    assert.deepEqual([...value], [...value].sort());
    assert.equal(new Set(value).size, value.length);
  }
});

test("x01_schema: the role registry reads as the RoleSpec records it declares", () => {
  assert.equal(registry.version, "4.0.0");
  assert.equal(registry.roles.length, 28);

  for (const role of registry.roles) {
    assert.deepEqual(Object.keys(role).sort(), [...ROLE_REGISTRY_FIELDS].sort());
    assert.equal(typeof role.mission, "string");
    assert.equal(typeof role.independent_review_required, "boolean");
    assert.equal(typeof role.default_timeout_seconds, "number");
    assert.ok(Array.isArray(role.write_scope));
  }
});

test("x01_schema: the Codex role mapping reads as the host compilation it declares", () => {
  assert.equal(mapping.version, "4.0.0");
  assert.equal(Object.keys(mapping.roles).length, 28);
  assert.equal(mapping.constraints.length, 4);

  for (const [roleId, row] of Object.entries(mapping.roles)) {
    assert.deepEqual(Object.keys(row).sort(), [...ROLE_MAPPING_FIELDS].sort());
    assert.equal(row.prompt_source, promptSourceFor(roleId));
  }
});

test("x01_schema: the descriptor table is one row per declared role", () => {
  assert.equal(binding.roleTable.length, registry.roles.length);
  assert.deepEqual(
    binding.roleTable.map((row) => row.role_id),
    registry.roles.map((row) => row.role_id).sort(),
  );
  assert.equal(new Set(binding.roleTable.map((row) => row.name)).size, binding.roleTable.length);

  for (const descriptor of binding.roleTable) {
    assert.deepEqual(Object.keys(descriptor).sort(), [...DESCRIPTOR_FIELDS].sort());
    assert.ok(descriptor.name.startsWith(binding.declaration.descriptor_name_prefix));
  }
});

test("x01_schema: every descriptor field comes from a declaring source", () => {
  for (const descriptor of binding.roleTable) {
    const spec = registry.roles.find((row) => row.role_id === descriptor.role_id);
    const mapped = mapping.roles[descriptor.role_id];
    assert.equal(descriptor.agent_type, spec.codex_agent_type);
    assert.equal(descriptor.agent_type, mapped.agent_type);
    assert.equal(descriptor.output_schema_ref, spec.output_schema_ref);
    assert.equal(descriptor.output_schema_ref, mapped.result_schema);
    assert.equal(descriptor.prompt_source, mapped.prompt_source);
    assert.deepEqual(descriptor.write_scope, spec.write_scope);
    assert.deepEqual(descriptor.tool_acl, spec.tool_acl);
    assert.deepEqual(descriptor.evidence_acl, spec.evidence_acl);
    assert.deepEqual(descriptor.forbidden, spec.forbidden);
  }
});

test("x01_schema: the table is rebuilt from files, not from a literal role list", () => {
  const rebuilt = buildRoleDescriptorTable({
    prefix: binding.declaration.descriptor_name_prefix,
  });

  assert.deepEqual(rebuilt, binding.roleTable);
  for (const relative of PRODUCT_MODULES) {
    const source = readRepo(`${ADAPTER_ROOT}/${relative}`);
    for (const roleId of registry.roles.map((row) => row.role_id)) {
      assert.ok(!source.includes(`"${roleId}"`), `${relative}: ${roleId}`);
    }
  }
});

test("x01_schema: every hook verb is derived from a registration in the payload", () => {
  assert.equal(binding.eventTypeByVerb.size, 8);

  for (const [verb, eventType] of binding.eventTypeByVerb) {
    assert.ok(binding.registeredEventTypes.includes(eventType), eventType);
    assert.ok(
      binding.registrations.some((row) => row.verb === verb && row.event_type === eventType),
      verb,
    );
  }
});

test("x01_schema: a bridged request is exactly the fields the gateway normalizes", () => {
  const request = toHookRequest(binding, rawEventFor(binding));

  assert.deepEqual(Object.keys(request).sort(), [...HOOK_REQUEST_FIELDS].sort());
  assert.equal(RAW_EVENT_FIELDS.length, 7);
  assert.deepEqual([...RAW_EVENT_FIELDS], [...RAW_EVENT_FIELDS].sort());
});
