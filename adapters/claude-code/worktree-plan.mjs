// Translate one parallel-write request into an isolated-worktree plan.
//
// This is the worktree surface of the adapter, and it is a planner, not an
// actor: it opens no worktree, moves no file and holds no lease.  Given a set of
// write-capable roles a caller intends to run at the same time, it derives the
// disjoint write scopes their isolated worktrees would own and refuses the set
// the moment two of them could collide.  "Parallel writes isolated" is therefore
// a property the adapter can prove before any write happens, not a hope.
//
// The request is external, adapter-supplied input and is treated as inert data:
// its fields are validated to the exact minimal record, every role it names is
// resolved against the role registry rather than trusted, and a role the
// registry does not declare or that owns no write scope is refused rather than
// given a worktree it should not have.

import { fail, isPlainObject, requireFields } from "./claude-declarations.mjs";

/** The exact minimal record this adapter accepts as a parallel-write request. */
export const PARALLEL_REQUEST_FIELDS = Object.freeze(["requested_at", "roles", "session_id"]);

/** The fields one worktree assignment carries in a derived plan. */
export const WORKTREE_ASSIGNMENT_FIELDS = Object.freeze(["isolation", "role_id", "write_scope"]);

/**
 * The literal directory prefix a write-scope glob owns.
 *
 * The scope is read up to its first wildcard segment, so `artifacts/x/**` owns
 * `artifacts/x`.  Two scopes collide when one prefix is the other or an ancestor
 * of it, which is exactly when their isolated worktrees could not merge cleanly.
 */
export const scopePrefix = (glob) => {
  const segments = String(glob).split("/");
  const kept = [];
  for (const segment of segments) {
    if (segment.includes("*")) break;
    kept.push(segment);
  }
  return kept.join("/");
};

const prefixesConflict = (left, right) =>
  left === right || left.startsWith(`${right}/`) || right.startsWith(`${left}/`);

/** Whether any scope in `left` overlaps any scope in `right`. */
export const scopesConflict = (left, right) => {
  for (const a of left) {
    for (const b of right) {
      if (prefixesConflict(scopePrefix(a), scopePrefix(b))) return true;
    }
  }
  return false;
};

const assignmentFor = (descriptor) =>
  Object.freeze({
    isolation: descriptor.isolation,
    role_id: descriptor.role_id,
    write_scope: [...descriptor.write_scope],
  });

/**
 * Verify a set of worktree assignments is pairwise scope-disjoint.
 *
 * Pure and order-independent: it compares every pair once and refuses the first
 * overlap it finds, naming both roles.  A caller that has already built a plan
 * re-checks it here rather than trusting that it was built disjoint.
 */
export const verifyDisjoint = (assignments) => {
  const sorted = [...assignments].sort((left, right) => (left.role_id < right.role_id ? -1 : 1));
  for (let i = 0; i < sorted.length; i += 1) {
    for (let j = i + 1; j < sorted.length; j += 1) {
      if (scopesConflict(sorted[i].write_scope, sorted[j].write_scope)) {
        fail("WORKTREE_SCOPE_OVERLAP", `roles "${sorted[i].role_id}" and "${sorted[j].role_id}" overlap`, {
          role_ids: [sorted[i].role_id, sorted[j].role_id],
          write_scopes: [[...sorted[i].write_scope], [...sorted[j].write_scope]],
        });
      }
    }
  }
  return sorted;
};

/**
 * The isolation plan for every write-capable role the table declares.
 *
 * Read-only roles carry no worktree because they write nothing; every writer is
 * assigned its own isolated worktree, and the whole set is proved disjoint.  A
 * registry that ever gave two writers overlapping scopes would refuse here rather
 * than let the collision reach a real parallel run.
 */
export const deriveWorktreePlan = (table) => {
  const assignments = table
    .filter((descriptor) => descriptor.isolation === "worktree")
    .map((descriptor) => assignmentFor(descriptor));
  return Object.freeze(verifyDisjoint(assignments));
};

/**
 * Translate a raw parallel-write request into a disjoint worktree plan.
 *
 * Pure and clock-free: `requested_at` is the caller's, not this module's.  Every
 * named role is resolved against the binding's descriptor table; an undeclared
 * role or a read-only one is refused rather than isolated, and the resolved set
 * is proved disjoint before the plan is returned.
 */
export const toWorktreePlan = (binding, request) => {
  requireFields(request, PARALLEL_REQUEST_FIELDS, "parallel-write request", "PARALLEL_REQUEST_UNREADABLE");
  if (typeof request.session_id !== "string" || request.session_id.length === 0) {
    fail("PARALLEL_REQUEST_UNREADABLE", "the request session_id must be a non-empty string");
  }
  if (typeof request.requested_at !== "string" || request.requested_at.length === 0) {
    fail("PARALLEL_REQUEST_UNREADABLE", "the request requested_at must be a non-empty string");
  }
  if (!Array.isArray(request.roles) || request.roles.length === 0) {
    fail("PARALLEL_REQUEST_UNREADABLE", "the request must name at least one role", {
      roles: request.roles,
    });
  }
  if (new Set(request.roles).size !== request.roles.length) {
    fail("PARALLEL_REQUEST_UNREADABLE", "the request names a role twice", { roles: [...request.roles] });
  }

  const assignments = [];
  for (const roleId of request.roles) {
    const descriptor = binding.agentTable.find((row) => row.role_id === roleId);
    if (descriptor === undefined || !isPlainObject(descriptor)) {
      fail("ROLE_UNDECLARED", `the request names undeclared role "${String(roleId)}"`, {
        role_id: roleId,
      });
    }
    if (descriptor.isolation !== "worktree" || descriptor.write_scope.length === 0) {
      fail("WORKTREE_ROLE_NOT_WRITABLE", `role "${roleId}" writes nothing, so it earns no worktree`, {
        isolation: descriptor.isolation,
        role_id: roleId,
      });
    }
    assignments.push(assignmentFor(descriptor));
  }

  return Object.freeze({
    disjoint: true,
    requested_at: request.requested_at,
    session_id: request.session_id,
    worktrees: verifyDisjoint(assignments),
  });
};
