// claude_adapter_test / schema and type check — the adapter reads its vocabulary,
// it never restates it.
//
// Every set this adapter binds has a declaring source: the host comes from the
// sealed hook gateway, the role vocabulary from `manifests/role_registry.yaml`,
// the host compilation choice from `adapters/claude-code/role_mapping.yaml`, and
// the concrete tool grant and model from the binding declaration.  A declaring
// source that changes must break this suite rather than leave an adapter
// describing agents that no longer match their roles.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import { HOOK_HOSTS } from "../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  ADAPTER_ROOT,
  AGENT_SURFACES,
  BINDING_DECLARATION_PATH,
  buildAgentDescriptorTable,
  ClaudeAdapterError,
  DECLARATION_FIELDS,
  DESCRIPTOR_FIELDS,
  deriveTools,
  FINDING_CODES,
  isolationFor,
  ISOLATION_MODES,
  loadClaudeBinding,
  PARALLEL_REQUEST_FIELDS,
  parseRoleMapping,
  parseRoleRegistry,
  REPOSITORY_ROOT,
  ROLE_MAPPING_FIELDS,
  ROLE_MAPPING_PATH,
  ROLE_REGISTRY_FIELDS,
  ROLE_REGISTRY_PATH,
  selectDeclared,
  WORKTREE_ASSIGNMENT_FIELDS,
} from "./index.mjs";
import { refusal } from "./claude-fixtures.mjs";

/** Every module that ships as adapter product code, tests and fixtures aside. */
const PRODUCT_MODULES = Object.freeze([
  "agent-binding.mjs",
  "claude-declarations.mjs",
  "index.mjs",
  "role-adapter.mjs",
  "worktree-plan.mjs",
]);

const binding = loadClaudeBinding();
const readRepo = (relative) => readFileSync(join(REPOSITORY_ROOT, relative), "utf8");
const registry = parseRoleRegistry(readRepo(ROLE_REGISTRY_PATH));
const mapping = parseRoleMapping(readRepo(ROLE_MAPPING_PATH));

test("x02_schema: every finding code carries a code and a reason", () => {
  assert.equal(Object.keys(FINDING_CODES).length, 21);
  for (const [code, reason] of Object.entries(FINDING_CODES)) {
    assert.equal(code, code.toUpperCase());
    assert.ok(reason.length > 50, code);
  }
});

test("x02_schema: the adapter host is one the hook gateway declares", () => {
  assert.ok(HOOK_HOSTS.includes(binding.adapterHost));
  assert.equal(binding.adapterHost, binding.declaration.declared_host);
  assert.equal(HOOK_HOSTS.filter((entry) => entry === binding.declaration.declared_host).length, 1);
});

test("x02_schema: no product module restates the host the gateway declares", () => {
  const literal = new RegExp(`["']${binding.adapterHost}["']`, "u");
  for (const relative of PRODUCT_MODULES) {
    assert.ok(!literal.test(readRepo(`${ADAPTER_ROOT}/${relative}`)), relative);
  }
  assert.match(readRepo(BINDING_DECLARATION_PATH), literal);
});

test("x02_schema: an undeclared value is refused rather than defaulted", () => {
  const error = refusal(() => selectDeclared(HOOK_HOSTS, "not-a-host", "declared_host", "HOST_UNDECLARED"));

  assert.ok(error instanceof ClaudeAdapterError);
  assert.equal(error.code, "HOST_UNDECLARED");
  assert.deepEqual(error.context.declared, [...HOOK_HOSTS]);
  assert.equal(refusal(() => selectDeclared([], "x", "l", "HOST_UNDECLARED")).code, "HOST_UNDECLARED");
});

test("x02_schema: the surface and isolation vocabularies are the ones the mapping selects from", () => {
  assert.deepEqual([...AGENT_SURFACES], ["custom_agent", "skill", "slash_command"]);
  assert.deepEqual([...ISOLATION_MODES], ["shared", "worktree"]);
  for (const row of Object.values(mapping.roles)) {
    assert.ok(AGENT_SURFACES.includes(row.surface), row.surface);
    assert.ok(ISOLATION_MODES.includes(row.isolation), row.isolation);
  }
});

test("x02_schema: the binding declaration is exactly the fields the loader requires", () => {
  assert.deepEqual(Object.keys(binding.declaration).sort(), [...DECLARATION_FIELDS].sort());
  assert.deepEqual([...binding.declaration.frontmatter_fields], [...binding.declaration.frontmatter_fields].sort());
  assert.equal(binding.declaration.agent_root, ".claude/agents");
  assert.deepEqual(binding.declaration.optional_frontmatter, {
    maxTurns: "40",
    permissionMode: "plan",
  });
  assert.equal(new Set(binding.declaration.base_tools).size, binding.declaration.base_tools.length);
  assert.ok(!binding.declaration.base_tools.includes(binding.declaration.write_tool));
});

test("x02_schema: the role registry reads as the RoleSpec records it declares", () => {
  assert.equal(registry.version, "4.0.0");
  assert.equal(registry.roles.length, 28);
  for (const role of registry.roles) {
    assert.deepEqual(Object.keys(role).sort(), [...ROLE_REGISTRY_FIELDS].sort());
    assert.equal(typeof role.mission, "string");
    assert.equal(typeof role.claude_agent_name, "string");
    assert.ok(Array.isArray(role.write_scope));
  }
});

test("x02_schema: the Claude Code role mapping reads as the host compilation it declares", () => {
  assert.equal(mapping.version, "4.0.0");
  assert.equal(Object.keys(mapping.roles).length, 28);
  assert.equal(mapping.constraints.length, 4);
  const byId = new Map(registry.roles.map((row) => [row.role_id, row]));
  for (const [roleId, row] of Object.entries(mapping.roles)) {
    assert.deepEqual(Object.keys(row).sort(), [...ROLE_MAPPING_FIELDS].sort());
    assert.equal(row.result_schema, byId.get(roleId).output_schema_ref);
    assert.equal(row.isolation, isolationFor(byId.get(roleId)));
  }
});

test("x02_schema: the descriptor table is one row per declared role", () => {
  assert.equal(binding.agentTable.length, registry.roles.length);
  assert.deepEqual(
    binding.agentTable.map((row) => row.role_id),
    registry.roles.map((row) => row.role_id).sort(),
  );
  assert.equal(new Set(binding.agentTable.map((row) => row.name)).size, binding.agentTable.length);
  for (const descriptor of binding.agentTable) {
    assert.deepEqual(Object.keys(descriptor).sort(), [...DESCRIPTOR_FIELDS].sort());
    assert.ok(descriptor.name.startsWith("ef-"));
  }
});

test("x02_schema: every descriptor field comes from a declaring source", () => {
  for (const descriptor of binding.agentTable) {
    const spec = registry.roles.find((row) => row.role_id === descriptor.role_id);
    const mapped = mapping.roles[descriptor.role_id];
    assert.equal(descriptor.name, spec.claude_agent_name);
    assert.equal(descriptor.description, spec.mission);
    assert.equal(descriptor.output_schema_ref, spec.output_schema_ref);
    assert.equal(descriptor.output_schema_ref, mapped.result_schema);
    assert.equal(descriptor.surface, mapped.surface);
    assert.equal(descriptor.isolation, mapped.isolation);
    assert.equal(descriptor.model, binding.declaration.model);
    assert.deepEqual(
      descriptor.tools,
      deriveTools(spec, { baseTools: binding.declaration.base_tools, writeTool: binding.declaration.write_tool }),
    );
    assert.deepEqual(descriptor.write_scope, spec.write_scope);
    assert.deepEqual(descriptor.tool_acl, spec.tool_acl);
    assert.deepEqual(descriptor.evidence_acl, spec.evidence_acl);
    assert.deepEqual(descriptor.forbidden, spec.forbidden);
  }
});

test("x02_schema: the table is rebuilt from files, not from a literal role list", () => {
  const rebuilt = buildAgentDescriptorTable({
    baseTools: binding.declaration.base_tools,
    model: binding.declaration.model,
    writeTool: binding.declaration.write_tool,
  });

  assert.deepEqual(rebuilt, binding.agentTable);
  for (const relative of PRODUCT_MODULES) {
    const source = readRepo(`${ADAPTER_ROOT}/${relative}`);
    for (const roleId of registry.roles.map((row) => row.role_id)) {
      assert.ok(!source.includes(`"${roleId}"`), `${relative}: ${roleId}`);
    }
  }
});

test("x02_schema: the request and assignment shapes are the exact fields they declare", () => {
  assert.deepEqual([...PARALLEL_REQUEST_FIELDS], ["requested_at", "roles", "session_id"]);
  assert.deepEqual([...PARALLEL_REQUEST_FIELDS], [...PARALLEL_REQUEST_FIELDS].sort());
  assert.deepEqual([...WORKTREE_ASSIGNMENT_FIELDS], ["isolation", "role_id", "write_scope"]);
  for (const row of binding.worktreePlan) {
    assert.deepEqual(Object.keys(row).sort(), [...WORKTREE_ASSIGNMENT_FIELDS].sort());
  }
});
