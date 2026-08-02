import assert from "node:assert/strict";
import test from "node:test";

import { authorizeRoleAccess, createRoleSpec } from "./index.mjs";
import {
  assertRoleSpecError,
  makeRoleSpec,
  makeRoleSpecInput,
} from "./role-spec-test-support.mjs";

const decision = (roleSpec, acl, resource) =>
  authorizeRoleAccess(roleSpec, { acl, resource });

test("acl_test: explicit tool, path, network, and evidence grants allow access", () => {
  const roleSpec = makeRoleSpec();
  for (const [acl, resource] of [
    ["tool", "artifact_read"],
    ["tool", "fulltext_search"],
    ["read", "policy/current.json"],
    ["read", "artifacts/evidence/pack.json"],
    ["write", "artifacts/retrieval/evidence_scout/result.json"],
    ["network", "https://search.example"],
    ["evidence", "counter"],
  ]) {
    const result = decision(roleSpec, acl, resource);
    assert.equal(result.decision, "ALLOW");
    assert.equal(result.reason, "EXPLICIT_ROLE_SPEC_GRANT");
    assert.ok(Object.isFrozen(result));
  }
});

test("acl_test: every known but undeclared access is denied by default", () => {
  const roleSpec = makeRoleSpec({
    tool_acl: [],
    read_scope: [],
    write_scope: [],
    network_acl: [],
    evidence_acl: [],
  });
  for (const [acl, resource] of [
    ["tool", "artifact_read"],
    ["read", "artifacts/evidence/pack.json"],
    ["write", "artifacts/retrieval/result.json"],
    ["network", "https://search.example"],
    ["evidence", "support"],
  ]) {
    const result = decision(roleSpec, acl, resource);
    assert.equal(result.decision, "DENY");
    assert.equal(result.reason, "DENY_BY_DEFAULT");
  }
});

test("acl_test: evidence ACLs preserve asymmetric defender and prosecutor views", () => {
  const defender = makeRoleSpec({
    role_id: "defender",
    evidence_acl: ["mechanism", "support"],
    independence_group: "parliament_defense",
  });
  const prosecutor = makeRoleSpec({
    role_id: "prosecutor",
    evidence_acl: ["boundary", "counter", "method", "null"],
    independence_group: "parliament_prosecution",
  });

  assert.equal(decision(defender, "evidence", "support").decision, "ALLOW");
  assert.equal(decision(defender, "evidence", "counter").decision, "DENY");
  assert.equal(decision(prosecutor, "evidence", "counter").decision, "ALLOW");
  assert.equal(decision(prosecutor, "evidence", "support").decision, "DENY");
  assert.notEqual(defender.role_spec_hash, prosecutor.role_spec_hash);
});

test("acl_test: all_permitted is an explicit privileged grant but never a request class", () => {
  const minorityReporter = makeRoleSpec({
    role_id: "minority_reporter",
    evidence_acl: ["all_permitted"],
  });
  for (const evidenceClass of ["support", "counter", "holdout_metadata"]) {
    assert.equal(decision(minorityReporter, "evidence", evidenceClass).decision, "ALLOW");
  }
  assertRoleSpecError(assert, "INVALID_EVIDENCE_REQUEST", () =>
    decision(minorityReporter, "evidence", "all_permitted"),
  );
});

test("acl_test: tool grants do not imply network, evidence, read, or write authority", () => {
  const roleSpec = makeRoleSpec({
    tool_acl: ["artifact_read", "network_fetch"],
    read_scope: [],
    write_scope: [],
    network_acl: [],
    evidence_acl: [],
  });
  assert.equal(decision(roleSpec, "tool", "network_fetch").decision, "ALLOW");
  assert.equal(decision(roleSpec, "network", "https://search.example").decision, "DENY");
  assert.equal(decision(roleSpec, "read", "artifacts/evidence/pack.json").decision, "DENY");
  assert.equal(decision(roleSpec, "write", "artifacts/evidence/pack.json").decision, "DENY");
  assert.equal(decision(roleSpec, "evidence", "support").decision, "DENY");
});

test("acl_test: read and write scopes remain independent", () => {
  const roleSpec = makeRoleSpec({
    read_scope: ["artifacts/public/**"],
    write_scope: ["artifacts/private/output.json"],
  });
  assert.equal(decision(roleSpec, "read", "artifacts/public/input.json").decision, "ALLOW");
  assert.equal(decision(roleSpec, "write", "artifacts/public/input.json").decision, "DENY");
  assert.equal(decision(roleSpec, "write", "artifacts/private/output.json").decision, "ALLOW");
  assert.equal(decision(roleSpec, "read", "artifacts/private/output.json").decision, "DENY");
  assert.equal(decision(roleSpec, "write", "artifacts/private/output.json/child").decision, "DENY");
});

test("acl_test: dotted and colon-delimited capability aliases fail closed", () => {
  for (const alias of ["artifact.read", "artifact:read", "llm.inference", "search.read"] ) {
    assertRoleSpecError(assert, "CAPABILITY_VOCABULARY_MISMATCH", () =>
      createRoleSpec(makeRoleSpecInput({ tool_acl: [alias] })),
    );
  }
  assertRoleSpecError(assert, "CAPABILITY_VOCABULARY_MISMATCH", () =>
    decision(makeRoleSpec(), "tool", "artifact.read"),
  );
});

test("acl_test: unknown tool, evidence, and ACL vocabularies are never treated as denial aliases", () => {
  assertRoleSpecError(assert, "UNKNOWN_TOOL_CAPABILITY", () =>
    createRoleSpec(makeRoleSpecInput({ tool_acl: ["provider_magic"] })),
  );
  assertRoleSpecError(assert, "UNKNOWN_EVIDENCE_CLASS", () =>
    createRoleSpec(makeRoleSpecInput({ evidence_acl: ["secret_holdout"] })),
  );
  assertRoleSpecError(assert, "UNKNOWN_ACL_KIND", () =>
    authorizeRoleAccess(makeRoleSpec(), { acl: "capability", resource: "artifact_read" }),
  );
});

test("acl_test: network ACLs bind exact canonical HTTPS origins", () => {
  const roleSpec = makeRoleSpec({ network_acl: ["https://search.example"] });
  assert.equal(decision(roleSpec, "network", "https://search.example").decision, "ALLOW");
  assert.equal(decision(roleSpec, "network", "https://api.search.example").decision, "DENY");
  for (const invalid of [
    "http://search.example",
    "https://search.example/path",
    "https://user:pass@search.example",
    "https://*.example",
    "https://SEARCH.example",
  ]) {
    assertRoleSpecError(assert, "INVALID_NETWORK_ORIGIN", () =>
      decision(roleSpec, "network", invalid),
    );
  }
});

test("acl_test: access requests reject traversal and accessor or proxy wrappers without execution", () => {
  const roleSpec = makeRoleSpec();
  for (const invalid of ["../secret", "artifacts/../secret", "C:/secret", "artifacts\\secret"] ) {
    assertRoleSpecError(assert, "INVALID_SCOPE", () => decision(roleSpec, "read", invalid));
  }

  let getterCount = 0;
  const accessor = { acl: "tool" };
  Object.defineProperty(accessor, "resource", {
    enumerable: true,
    get() {
      getterCount += 1;
      throw new Error("must not execute");
    },
  });
  assertRoleSpecError(assert, "ACCESSOR_FIELD_DENIED", () =>
    authorizeRoleAccess(roleSpec, accessor),
  );
  assert.equal(getterCount, 0);

  let trapCount = 0;
  const proxy = new Proxy({ acl: "tool", resource: "artifact_read" }, {
    get() {
      trapCount += 1;
      throw new Error("must not execute");
    },
  });
  assertRoleSpecError(assert, "INVALID_INPUT", () => authorizeRoleAccess(roleSpec, proxy));
  assert.equal(trapCount, 0);
});

test("acl_test: a tampered RoleSpec cannot authorize any access", () => {
  const tampered = structuredClone(makeRoleSpec());
  tampered.tool_acl.push("database_write");
  assertRoleSpecError(assert, "NON_CANONICAL_ORDER", () =>
    decision(tampered, "tool", "database_write"),
  );
});
