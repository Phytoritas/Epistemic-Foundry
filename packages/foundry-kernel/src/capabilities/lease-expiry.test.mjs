import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { CAPABILITY_RECORD_TYPES, CapabilityAuthorityError, createCapabilityAuthority, sealCapabilityPolicy } from "./capability-authority.mjs";
import {
  E03_IDS,
  createCapabilityFixture,
  defaultLeaseCommand,
  defaultPolicyInput,
  defaultUseCommand,
  issueDefaultLease,
  policyHash,
} from "./capability-test-support.mjs";

const expectCode = (code) => (error) =>
  error instanceof CapabilityAuthorityError && error.code === code;

test("lease_expiry_test: issued leases are canonical, scoped, expiring, and schema-valid", (t) => {
  const fixture = createCapabilityFixture(t);
  const lease = issueDefaultLease(fixture.authority);

  assert.equal(lease.principal_type, "agent");
  assert.deepEqual(lease.capabilities, ["artifact:write", "sandbox:execute"]);
  assert.deepEqual(lease.resource_scopes, ["artifact/e03", "workspace/e03"]);
  assert.equal(lease.issued_at, "2026-07-28T05:00:00Z");
  assert.equal(lease.expires_at, "2026-07-28T06:00:00Z");
  assert.equal(lease.policy_hash, fixture.policy.policy_hash);
  assert.equal(lease.fencing_token, 1);
  assert.equal(lease.revoked, false);
  assert.equal(lease.revocation_reason, null);
  assert.match(lease.lease_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.ok(Object.isFrozen(lease));
  assert.deepEqual(fixture.authority.readLease(lease.lease_id), lease);

  const instancePath = path.join(fixture.root, "lease.json");
  fs.writeFileSync(instancePath, JSON.stringify(lease), "utf8");
  const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
  const script = `
import json, pathlib, sys
from jsonschema import Draft202012Validator, FormatChecker
schema = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
instance = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
Draft202012Validator.check_schema(schema)
errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance))
if errors: raise SystemExit("; ".join(error.message for error in errors))
print("CapabilityLease valid")
`;
  const result = spawnSync(
    "uv",
    ["run", "--locked", "python", "-", path.join(repositoryRoot, "schemas", "capability-lease.schema.json"), instancePath],
    { cwd: repositoryRoot, encoding: "utf8", input: script },
  );
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  assert.equal(result.stdout.trim(), "CapabilityLease valid");
  assert.equal(fixture.ledger.readEvents(E03_IDS.RUN).at(-1).event_type, "capability.lease.issued");
});

test("lease_expiry_test: active lease checks and result persistence share one transaction", (t) => {
  const { authority, stateStore } = createCapabilityFixture(t);
  const lease = issueDefaultLease(authority);
  const committed = authority.commitWithLease(defaultUseCommand(lease), (store) => {
    store.createRevisionedRecord({
      recordType: "e03.test.result",
      recordId: "RESULT-E03-active",
      value: { accepted: true, fencing_token: lease.fencing_token },
    });
    return { result_id: "RESULT-E03-active" };
  });

  assert.equal(committed.status, "COMMITTED");
  assert.deepEqual(committed.result, { result_id: "RESULT-E03-active" });
  assert.deepEqual(stateStore.readRevisionedRecord("e03.test.result", "RESULT-E03-active").value, {
    accepted: true,
    fencing_token: 1,
  });
});

test("lease_expiry_test: expiry boundary rejects commit without invoking or persisting callback", (t) => {
  const { authority, setTime, stateStore } = createCapabilityFixture(t);
  const lease = issueDefaultLease(authority);
  setTime(lease.expires_at);
  let invoked = false;

  assert.throws(
    () =>
      authority.commitWithLease(defaultUseCommand(lease), (store) => {
        invoked = true;
        store.createRevisionedRecord({ recordType: "e03.test.result", recordId: "EXPIRED", value: {} });
        return null;
      }),
    expectCode("LEASE_EXPIRED"),
  );
  assert.equal(invoked, false);
  assert.equal(stateStore.readRevisionedRecord("e03.test.result", "EXPIRED"), null);
  setTime("2026-07-28T05:30:00Z");
  const recovered = authority.commitWithLease(defaultUseCommand(lease), () => {
    invoked = true;
    return { recovered: true };
  });
  assert.equal(invoked, true);
  assert.equal(recovered.status, "COMMITTED");
});

test("lease_expiry_test: a clock before issued_at rejects a not-yet-valid lease", (t) => {
  const { authority, setTime } = createCapabilityFixture(t);
  const lease = issueDefaultLease(authority);
  setTime("2026-07-28T04:59:59Z");
  assert.throws(
    () => authority.commitWithLease(defaultUseCommand(lease), () => ({ impossible: true })),
    expectCode("LEASE_NOT_YET_VALID"),
  );
});

test("lease_expiry_test: issue rejects zero or negative lifetime before state mutation", (t) => {
  const { authority, stateStore } = createCapabilityFixture(t);
  assert.throws(
    () => authority.issueLease(E03_IDS.AUTHORITY, defaultLeaseCommand({ expires_at: "2026-07-28T05:00:00Z" })),
    expectCode("LEASE_ALREADY_EXPIRED"),
  );
  assert.equal(stateStore.readRevisionedRecord(CAPABILITY_RECORD_TYPES.FENCING_COUNTER, "global"), null);
});

test("lease_expiry_test: policy changes invalidate an otherwise unexpired lease", (t) => {
  const fixture = createCapabilityFixture(t);
  const lease = issueDefaultLease(fixture.authority);
  const changedPolicy = sealCapabilityPolicy(defaultPolicyInput({ hash: policyHash("changed") }));
  const changedAuthority = createCapabilityAuthority({
    artifactStore: fixture.artifactStore,
    ledger: fixture.ledger,
    stateStore: fixture.stateStore,
    policy: changedPolicy,
    clock: () => "2026-07-28T05:10:00Z",
  });

  assert.throws(
    () => changedAuthority.commitWithLease(defaultUseCommand(lease), () => null),
    expectCode("LEASE_POLICY_MISMATCH"),
  );
});

test("lease_expiry_test: revocation is explicit and prevents later commits", (t) => {
  const { authority } = createCapabilityFixture(t);
  const lease = issueDefaultLease(authority);
  const revoked = authority.revokeLease(E03_IDS.AUTHORITY, {
    lease_id: lease.lease_id,
    run_id: E03_IDS.RUN,
    reason: "operator revoked bounded authority",
  });
  assert.equal(revoked.revoked, true);
  assert.equal(revoked.revocation_reason, "operator revoked bounded authority");
  assert.notEqual(revoked.lease_hash, lease.lease_hash);
  assert.throws(
    () => authority.commitWithLease(defaultUseCommand(revoked), () => null),
    expectCode("LEASE_REVOKED"),
  );
  const retry = authority.issueLease(E03_IDS.AUTHORITY, defaultLeaseCommand());
  assert.deepEqual(retry, revoked);
  assert.equal(retry.fencing_token, lease.fencing_token);
});

test("lease_expiry_test: exact lease issuance retry returns the first logical lease", (t) => {
  const { authority, setTime } = createCapabilityFixture(t);
  const first = issueDefaultLease(authority);
  setTime("2026-07-28T06:30:00Z");
  const retry = authority.issueLease(E03_IDS.AUTHORITY, defaultLeaseCommand());
  assert.deepEqual(retry, first);
  assert.equal(retry.fencing_token, 1);
});

test("lease_expiry_test: expiry after callback rolls back the protected mutation", (t) => {
  const { authority, setTime, stateStore } = createCapabilityFixture(t);
  const lease = issueDefaultLease(authority);

  assert.throws(
    () =>
      authority.commitWithLease(
        defaultUseCommand(lease, { operation_id: "OP-E03-expire-during-commit" }),
        (store) => {
          store.createRevisionedRecord({
            recordType: "e03.test.result",
            recordId: "EXPIRED-DURING-COMMIT",
            value: { should_not_persist: true },
          });
          setTime(lease.expires_at);
          return { should_not_commit: true };
        },
      ),
    expectCode("LEASE_EXPIRED"),
  );
  assert.equal(
    stateStore.readRevisionedRecord("e03.test.result", "EXPIRED-DURING-COMMIT"),
    null,
  );
});

test("lease_expiry_test: authority clock regression during commit fails closed", (t) => {
  const { authority, setTime, stateStore } = createCapabilityFixture(t);
  const lease = issueDefaultLease(authority);

  assert.throws(
    () =>
      authority.commitWithLease(
        defaultUseCommand(lease, { operation_id: "OP-E03-clock-regression" }),
        (store) => {
          store.createRevisionedRecord({
            recordType: "e03.test.result",
            recordId: "CLOCK-REGRESSION",
            value: { should_not_persist: true },
          });
          setTime("2026-07-28T04:59:59Z");
          return null;
        },
      ),
    expectCode("CLOCK_REGRESSION"),
  );
  assert.equal(stateStore.readRevisionedRecord("e03.test.result", "CLOCK-REGRESSION"), null);
});

test("lease_expiry_test: lease issuance is bound to declared subject run and scope", (t) => {
  const { authority, stateStore } = createCapabilityFixture(t);
  assert.throws(
    () =>
      authority.issueLease(
        E03_IDS.AUTHORITY,
        defaultLeaseCommand({ run_id: "RUN-E03-other" }),
      ),
    expectCode("LEASE_RUN_SCOPE_MISMATCH"),
  );
  assert.throws(
    () =>
      authority.issueLease(
        E03_IDS.AUTHORITY,
        defaultLeaseCommand({ resource_scopes: ["workspace/e03"] }),
      ),
    expectCode("LEASE_SUBJECT_SCOPE_MISMATCH"),
  );
  assert.equal(stateStore.readRevisionedRecord(CAPABILITY_RECORD_TYPES.FENCING_COUNTER, "global"), null);
});
