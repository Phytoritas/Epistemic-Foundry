// worktree_isolation_test / the worktree surface — parallel writes are proved
// isolated before any write happens.
//
// The registry's real scopes are all disjoint, so a plan over the whole table
// always succeeds; the overlap refusal is exercised with synthetic assignments
// so the guard is shown to fire rather than assumed to.  The request is external,
// adapter-supplied input and is treated as inert data: a malformed record, an
// undeclared role, or a read-only role is refused rather than isolated.

import assert from "node:assert/strict";
import test from "node:test";

import {
  deriveWorktreePlan,
  loadClaudeBinding,
  scopePrefix,
  scopesConflict,
  toWorktreePlan,
  verifyDisjoint,
} from "./index.mjs";
import { parallelRequest, refusal } from "./claude-fixtures.mjs";

const binding = loadClaudeBinding();

test("x02_worktree: a scope prefix is read up to its first wildcard segment", () => {
  assert.equal(scopePrefix("artifacts/parliament/judge/**"), "artifacts/parliament/judge");
  assert.equal(scopePrefix("artifacts/claims/**"), "artifacts/claims");
  assert.equal(scopePrefix("artifacts/exact/file.json"), "artifacts/exact/file.json");
});

test("x02_worktree: overlapping and nested scopes conflict, sibling scopes do not", () => {
  assert.equal(scopesConflict(["artifacts/x/**"], ["artifacts/x/**"]), true);
  assert.equal(scopesConflict(["artifacts/x/**"], ["artifacts/x/y/**"]), true);
  assert.equal(scopesConflict(["artifacts/parliament/defender/**"], ["artifacts/parliament/prosecutor/**"]), false);
  assert.equal(scopesConflict(["artifacts/reason/inductive/**"], ["artifacts/reason/deductive/**"]), false);
});

test("x02_worktree: verifyDisjoint refuses the first overlapping pair it finds", () => {
  const error = refusal(() =>
    verifyDisjoint([
      { role_id: "beta", write_scope: ["artifacts/x/y/**"] },
      { role_id: "alpha", write_scope: ["artifacts/x/**"] },
    ]),
  );

  assert.equal(error.code, "WORKTREE_SCOPE_OVERLAP");
  assert.deepEqual(error.context.role_ids, ["alpha", "beta"]);
});

test("x02_worktree: the whole registry compiles to a disjoint set of writer worktrees", () => {
  const plan = deriveWorktreePlan(binding.agentTable);

  assert.equal(plan.length, 27);
  assert.ok(!plan.some((row) => row.role_id === "evidence_scout"));
  assert.deepEqual(plan, binding.worktreePlan);
  for (let i = 0; i < plan.length; i += 1) {
    for (let j = i + 1; j < plan.length; j += 1) {
      assert.equal(scopesConflict(plan[i].write_scope, plan[j].write_scope), false, `${plan[i].role_id} ${plan[j].role_id}`);
    }
  }
});

test("x02_worktree: a valid request plans exactly the writers it named, disjoint", () => {
  const plan = toWorktreePlan(binding, parallelRequest({ roles: ["archive_curator", "claim_extractor", "defender"] }));

  assert.equal(plan.disjoint, true);
  assert.deepEqual(plan.worktrees.map((row) => row.role_id), ["archive_curator", "claim_extractor", "defender"]);
});

test("x02_worktree: a request that names a read-only role earns no worktree", () => {
  const error = refusal(() => toWorktreePlan(binding, parallelRequest({ roles: ["defender", "evidence_scout"] })));

  assert.equal(error.code, "WORKTREE_ROLE_NOT_WRITABLE");
  assert.equal(error.context.role_id, "evidence_scout");
});

test("x02_worktree: a request that names an undeclared role is refused", () => {
  const error = refusal(() => toWorktreePlan(binding, parallelRequest({ roles: ["defender", "../etc/passwd"] })));

  assert.equal(error.code, "ROLE_UNDECLARED");
  assert.equal(error.context.role_id, "../etc/passwd");
});

test("x02_worktree: a request that is not the exact minimal record is refused", () => {
  assert.equal(refusal(() => toWorktreePlan(binding, { ...parallelRequest(), extra: true })).code, "PARALLEL_REQUEST_UNREADABLE");
  const { session_id: _dropped, ...missing } = parallelRequest();
  assert.equal(refusal(() => toWorktreePlan(binding, missing)).code, "PARALLEL_REQUEST_UNREADABLE");
  assert.equal(refusal(() => toWorktreePlan(binding, parallelRequest({ roles: [] }))).code, "PARALLEL_REQUEST_UNREADABLE");
  assert.equal(
    refusal(() => toWorktreePlan(binding, parallelRequest({ roles: ["defender", "defender"] }))).code,
    "PARALLEL_REQUEST_UNREADABLE",
  );
  assert.equal(refusal(() => toWorktreePlan(binding, null)).code, "PARALLEL_REQUEST_UNREADABLE");
});

test("x02_worktree: the plan is deterministic and frozen", () => {
  const request = parallelRequest({ roles: ["defender", "prosecutor", "judge"] });
  const plan = toWorktreePlan(binding, request);

  assert.ok(Object.isFrozen(plan));
  assert.deepEqual(plan, toWorktreePlan(binding, request));
});
