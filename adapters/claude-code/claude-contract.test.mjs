// claude_adapter_test / unit and contract tests — what the adapter does with the
// role registry and the agent files that actually ship.
//
// The binding is derived from the adapter declaration, canonical role registry,
// and the host-visible `.claude/agents` surface.  This suite pins the three things
// the adapter is for: every canonical RoleSpec compiles to one custom-agent
// descriptor, every live EF agent's bound frontmatter matches it, and a parallel-write request
// crosses into an isolated worktree plan carrying nothing the adapter invented.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  ADAPTER_ROOT,
  agentTableHash,
  BINDING_STATUS,
  buildAgentDescriptorTable,
  canonicalAgentTable,
  describeAgent,
  deriveWorktreePlan,
  isWriteCapable,
  loadClaudeBinding,
  REPOSITORY_ROOT,
  toWorktreePlan,
} from "./index.mjs";
import { parallelRequest, refusal } from "./claude-fixtures.mjs";

/** Adapter product code; a generator or a filesystem write in any of it is a failure. */
const PRODUCT_MODULES = Object.freeze([
  "agent-binding.mjs",
  "claude-declarations.mjs",
  "index.mjs",
  "role-adapter.mjs",
  "worktree-plan.mjs",
]);

const binding = loadClaudeBinding();
const readRepo = (relative) => readFileSync(join(REPOSITORY_ROOT, relative), "utf8");

test("x02_contract: every RoleSpec compiles to a live Claude agent", () => {
  assert.equal(binding.status, BINDING_STATUS.BOUND);
  assert.equal(binding.agentRoot, ".claude/agents");
  assert.equal(binding.agentTable.length, 28);
  assert.deepEqual(binding.findings, []);
  assert.deepEqual(binding.missingRoleIds, []);
  assert.equal(binding.presentRoleIds.length, 28);
});

test("x02_contract: every present agent file exists and belongs to a declared role", () => {
  for (const roleId of binding.presentRoleIds) {
    const descriptor = describeAgent(binding.agentTable, roleId);
    assert.doesNotThrow(() => readRepo(`${binding.agentRoot}/${descriptor.name}.md`));
    assert.ok(descriptor.name.startsWith("ef-"));
  }
  assert.ok(binding.presentRoleIds.includes("judge"));
  assert.ok(binding.presentRoleIds.includes("evidence_scout"));
});

test("x02_contract: the tool grant follows the write scope the RoleSpec declares", () => {
  const scout = describeAgent(binding.agentTable, "evidence_scout");
  assert.equal(isWriteCapable(scout), false);
  assert.deepEqual(scout.tools, ["Read", "Grep", "Glob"]);
  assert.equal(scout.isolation, "shared");
  assert.deepEqual(scout.write_scope, []);

  const extractor = describeAgent(binding.agentTable, "claim_extractor");
  assert.equal(isWriteCapable(extractor), true);
  assert.deepEqual(extractor.tools, ["Read", "Grep", "Glob", "Bash"]);
  assert.equal(extractor.isolation, "worktree");
  assert.deepEqual(extractor.write_scope, ["artifacts/claims/**"]);
});

test("x02_contract: a descriptor carries the bounded scopes and schema its RoleSpec declares", () => {
  const descriptor = describeAgent(binding.agentTable, "validation_executor");

  assert.equal(descriptor.name, "ef-validation-executor");
  assert.equal(descriptor.description, "Execute only a preregistered plan under a capability lease and emit effect receipts.");
  assert.deepEqual(descriptor.write_scope, ["artifacts/validation/**"]);
  assert.deepEqual(descriptor.tool_acl, ["sandbox.execute", "artifact.read", "artifact.write"]);
  assert.equal(descriptor.output_schema_ref, "schemas/result-envelope.schema.json");
  assert.equal(descriptor.model, "inherit");
  assert.equal(descriptor.surface, "custom_agent");
  assert.equal(descriptor.default_timeout_seconds, 1200);
  assert.ok(Object.isFrozen(descriptor));
});

test("x02_contract: a role the registry does not declare has no descriptor", () => {
  const error = refusal(() => describeAgent(binding.agentTable, "shadow_promoter"));

  assert.equal(error.code, "ROLE_UNDECLARED");
  assert.equal(error.context.role_id, "shadow_promoter");
});

test("x02_contract: regenerating the descriptor table is byte-stable", () => {
  const rebuilt = loadClaudeBinding().agentTable;

  assert.equal(canonicalAgentTable(rebuilt), canonicalAgentTable(binding.agentTable));
  assert.equal(agentTableHash(rebuilt), agentTableHash(binding.agentTable));
  assert.match(agentTableHash(binding.agentTable), /^sha256:[0-9a-f]{64}$/u);
});

test("x02_contract: every writer earns an isolated worktree and readers earn none", () => {
  const writers = binding.agentTable.filter((row) => isWriteCapable(row));
  assert.equal(binding.worktreePlan.length, writers.length);
  assert.equal(binding.worktreePlan.length, 27);
  assert.ok(!binding.worktreePlan.some((row) => row.role_id === "evidence_scout"));
  for (const row of binding.worktreePlan) {
    assert.equal(row.isolation, "worktree");
    assert.ok(row.write_scope.length > 0);
  }
  assert.deepEqual(deriveWorktreePlan(binding.agentTable), binding.worktreePlan);
});

test("x02_contract: a parallel-write request becomes a plan of only the scopes it named", () => {
  const request = parallelRequest({ roles: ["defender", "prosecutor", "judge"] });
  const plan = toWorktreePlan(binding, request);

  assert.equal(plan.disjoint, true);
  assert.equal(plan.session_id, request.session_id);
  assert.equal(plan.requested_at, request.requested_at);
  assert.deepEqual(
    plan.worktrees.map((row) => row.role_id),
    ["defender", "judge", "prosecutor"],
  );
  for (const row of plan.worktrees) {
    const descriptor = describeAgent(binding.agentTable, row.role_id);
    assert.deepEqual(row.write_scope, descriptor.write_scope);
    assert.equal(row.isolation, "worktree");
  }
});

test("x02_contract: the same request always plans to the same worktrees", () => {
  const request = parallelRequest();
  assert.deepEqual(toWorktreePlan(binding, request), toWorktreePlan(binding, request));
});

test("x02_contract: the adapter generates nothing and writes nothing", () => {
  for (const relative of PRODUCT_MODULES) {
    const source = readRepo(`${ADAPTER_ROOT}/${relative}`);
    for (const forbidden of [
      "node:child_process",
      "spawnSync",
      "execSync",
      "writeFileSync",
      "rmSync",
      "mkdirSync",
      "cpSync",
    ]) {
      assert.ok(!source.includes(forbidden), `${relative}: ${forbidden}`);
    }
  }
});
