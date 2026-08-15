// worktree_isolation_test / provenance and receipt audit — the adapter can prove
// what it read, which roles it could compile and how their writers are isolated.
//
// A role binding that cannot name its inputs is an opinion.  The receipt binds
// every declaring source by digest, re-derives its own hash from exactly the
// fields it publishes, names the roles whose agent file is not generated yet,
// publishes the disjoint worktree of every writer, and carries no clock and no
// randomness — so the same repository always produces the same receipt and a
// changed input always produces a different one.

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import { sha256HookJson } from "../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  ADAPTER_ROOT,
  agentTableHash,
  BINDING_SOURCE_PATHS,
  claudeBindingReceipt,
  loadClaudeBinding,
  REPOSITORY_ROOT,
} from "./index.mjs";
import { stageDeclaration } from "./claude-fixtures.mjs";

/** Adapter product code; a clock or a random number in any of it is a failure. */
const PRODUCT_MODULES = Object.freeze([
  "agent-binding.mjs",
  "claude-declarations.mjs",
  "index.mjs",
  "role-adapter.mjs",
  "worktree-plan.mjs",
]);

const binding = loadClaudeBinding();
const receipt = claudeBindingReceipt(binding);
const digestOf = (relative) =>
  `sha256:${createHash("sha256").update(readFileSync(join(REPOSITORY_ROOT, relative))).digest("hex")}`;

test("x02_receipt: the receipt re-derives its own hash from the fields it publishes", () => {
  const preimage = { ...receipt };
  delete preimage.receipt_id;
  delete preimage.receipt_hash;

  assert.equal(sha256HookJson(preimage), receipt.receipt_hash);
});

test("x02_receipt: the receipt identifier is derived from the hash", () => {
  assert.equal(receipt.receipt_id, `EFX02-CLAUDE-${receipt.receipt_hash.slice(7, 23)}`);
  assert.match(receipt.receipt_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("x02_receipt: the same repository yields the same receipt", () => {
  assert.deepEqual(claudeBindingReceipt(loadClaudeBinding()), receipt);
});

test("x02_receipt: every declaring source is bound by its actual digest", () => {
  const expected = [
    ...BINDING_SOURCE_PATHS,
    ...binding.presentRoleIds.map((roleId) => {
      const descriptor = binding.agentTable.find((row) => row.role_id === roleId);
      return `${binding.agentRoot}/${descriptor.name}.md`;
    }),
  ].sort();

  assert.deepEqual(receipt.sources.map((row) => row.path), expected);
  assert.equal(receipt.sources.length, 31);
  for (const row of receipt.sources) assert.equal(row.sha256, digestOf(row.path));
});

test("x02_receipt: a changed declaration changes the receipt", (t) => {
  const root = stageDeclaration(t, (declaration) => {
    declaration.adapter_version = "4.0.0-x02.2";
  });
  const changed = claudeBindingReceipt(loadClaudeBinding({ root }));

  assert.notEqual(changed.receipt_hash, receipt.receipt_hash);
  assert.equal(changed.adapter_version, "4.0.0-x02.2");
});

test("x02_receipt: every live Claude agent is named", () => {
  assert.equal(receipt.binding_status, "BOUND");
  assert.equal(receipt.agent_root, ".claude/agents");
  assert.equal(receipt.agent_count, 28);
  assert.deepEqual(receipt.missing_agents, []);
  assert.equal(receipt.present_agents.length, 28);
  assert.deepEqual(receipt.findings, []);
});

test("x02_receipt: the receipt binds the adapter identity and the agent table", () => {
  assert.equal(receipt.adapter_id, binding.declaration.adapter_id);
  assert.equal(receipt.adapter_version, "4.0.0");
  assert.equal(receipt.adapter_host, binding.adapterHost);
  assert.equal(receipt.agent_table_hash, agentTableHash(binding.agentTable));
});

test("x02_receipt: every writer has a disjoint worktree and only the reader has none", () => {
  assert.equal(receipt.worktrees.length, 27);
  assert.deepEqual(receipt.read_only_agents, ["evidence_scout"]);
  const roleIds = receipt.worktrees.map((row) => row.role_id);
  assert.equal(new Set(roleIds).size, roleIds.length);
  for (const row of receipt.worktrees) {
    assert.equal(row.isolation, "worktree");
    assert.ok(row.write_scope.length > 0);
  }
});

test("x02_receipt: the adapter holds no clock and no randomness", () => {
  for (const relative of PRODUCT_MODULES) {
    const source = readFileSync(join(REPOSITORY_ROOT, ADAPTER_ROOT, relative), "utf8");
    for (const forbidden of ["Date.now", "new Date", "Math.random", "process.env", "process.argv"]) {
      assert.ok(!source.includes(forbidden), `${relative}: ${forbidden}`);
    }
  }
});

test("x02_receipt: the receipt is canonical JSON and frozen", () => {
  assert.deepEqual(JSON.parse(JSON.stringify(receipt)), { ...receipt });
  assert.ok(Object.isFrozen(receipt));
  assert.equal(sha256HookJson(receipt), sha256HookJson(JSON.parse(JSON.stringify(receipt))));
});
