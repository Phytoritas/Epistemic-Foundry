import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  CapabilityAuthorityError,
  createCapabilityAuthority,
  sealCapabilityPolicy,
} from "./capability-authority.mjs";
import {
  E03_IDS,
  createCapabilityFixture,
  defaultLeaseCommand,
  defaultPolicyInput,
  defaultUseCommand,
  issueCapabilityApproval,
  issueDefaultLease,
  leaseSubject,
} from "./capability-test-support.mjs";

const expectCode = (code) => (error) =>
  error instanceof CapabilityAuthorityError && error.code === code;

test("fencing_test: newer overlapping lease makes the old fencing token stale", (t) => {
  const { authority, setTime, stateStore } = createCapabilityFixture(t, {
    policy: defaultPolicyInput({
      subjects: [
        leaseSubject({ subjectId: E03_IDS.LEASE }),
        leaseSubject({ subjectId: "LEASE-E03-newer" }),
      ],
    }),
  });
  const oldLease = issueDefaultLease(authority);
  setTime("2026-07-28T05:01:00Z");
  const newer = authority.issueLease(
    E03_IDS.AUTHORITY,
    defaultLeaseCommand({ lease_id: "LEASE-E03-newer", expires_at: "2026-07-28T06:01:00Z" }),
  );
  assert.equal(newer.fencing_token, oldLease.fencing_token + 1);

  assert.throws(
    () =>
      authority.commitWithLease(defaultUseCommand(oldLease, { operation_id: "OP-E03-stale" }), (store) => {
        store.createRevisionedRecord({ recordType: "e03.test.result", recordId: "STALE", value: {} });
        return null;
      }),
    expectCode("STALE_FENCING_TOKEN"),
  );
  assert.equal(stateStore.readRevisionedRecord("e03.test.result", "STALE"), null);
  const accepted = authority.commitWithLease(
    defaultUseCommand(newer, { operation_id: "OP-E03-current" }),
    () => ({ accepted: true }),
  );
  assert.equal(accepted.fencing_token, 2);
});

test("fencing_test: replacing one scope invalidates the whole multi-scope lease", (t) => {
  const { authority, setTime } = createCapabilityFixture(t, {
    policy: defaultPolicyInput({
      subjects: [
        leaseSubject({ subjectId: E03_IDS.LEASE }),
        leaseSubject({
          subjectId: "LEASE-E03-overlap",
          capabilities: ["sandbox:execute"],
          resourceScopes: ["workspace/e03"],
        }),
      ],
    }),
  });
  const oldLease = issueDefaultLease(authority);
  setTime("2026-07-28T05:02:00Z");
  authority.issueLease(
    E03_IDS.AUTHORITY,
    defaultLeaseCommand({
      lease_id: "LEASE-E03-overlap",
      capabilities: ["sandbox:execute"],
      resource_scopes: ["workspace/e03"],
      expires_at: "2026-07-28T06:02:00Z",
    }),
  );
  assert.throws(
    () =>
      authority.commitWithLease(
        defaultUseCommand(oldLease, {
          operation_id: "OP-E03-old-unreplaced-scope",
          resource_scopes: ["artifact/e03"],
        }),
        () => null,
      ),
    expectCode("STALE_FENCING_TOKEN"),
  );
});

test("fencing_test: failed callback rolls back result, lease-use, and event outbox", (t) => {
  const { authority, ledger, stateStore } = createCapabilityFixture(t);
  const lease = issueDefaultLease(authority);
  const beforeEvents = ledger.readEvents(E03_IDS.RUN).length;
  assert.throws(
    () =>
      authority.commitWithLease(defaultUseCommand(lease, { operation_id: "OP-E03-rollback" }), (store) => {
        store.createRevisionedRecord({
          recordType: "e03.test.result",
          recordId: "ROLLBACK",
          value: { should_not_persist: true },
        });
        throw new Error("synthetic failure");
      }),
    expectCode("LEASE_COMMIT_CALLBACK_FAILED"),
  );
  assert.equal(stateStore.readRevisionedRecord("e03.test.result", "ROLLBACK"), null);
  assert.equal(ledger.readEvents(E03_IDS.RUN).length, beforeEvents);
  const retry = authority.commitWithLease(
    defaultUseCommand(lease, { operation_id: "OP-E03-rollback" }),
    () => ({ retry_committed: true }),
  );
  assert.equal(retry.status, "COMMITTED");
  assert.deepEqual(retry.result, { retry_committed: true });
});

test("fencing_test: operation retry is idempotent and does not rerun callback", (t) => {
  const { authority, setTime } = createCapabilityFixture(t);
  const lease = issueDefaultLease(authority);
  let calls = 0;
  const command = defaultUseCommand(lease, { operation_id: "OP-E03-idempotent" });
  const first = authority.commitWithLease(command, () => ({ call: ++calls }));
  setTime("2026-07-28T06:30:00Z");
  const retry = authority.commitWithLease(command, () => ({ call: ++calls }));
  assert.equal(first.status, "COMMITTED");
  assert.equal(retry.status, "EXISTING");
  assert.deepEqual(retry.result, first.result);
  assert.equal(calls, 1);
});

test("fencing_test: approval role is server-derived and client assertion is rejected", (t) => {
  const { authority, root } = createCapabilityFixture(t);
  assert.throws(
    () =>
      authority.issueApproval(E03_IDS.APPROVER, {
        approval_id: "APR-E03-forged-role",
        run_id: E03_IDS.RUN,
        subject_id: E03_IDS.LEASE,
        approval_type: "capability",
        decision: "APPROVE",
        reason: "attempted client role assertion",
        evidence_artifact_ids: ["ART-E03-evidence"],
        conditions: [],
        expires_at: "2026-07-28T06:00:00Z",
        authority_role: "system_owner",
      }),
    expectCode("INVALID_INPUT"),
  );
  const approval = authority.issueApproval(E03_IDS.APPROVER, {
    approval_id: "APR-E03-derived-role",
    run_id: E03_IDS.RUN,
    subject_id: E03_IDS.LEASE,
    approval_type: "capability",
    decision: "APPROVE",
    reason: "bounded lease evidence reviewed",
    evidence_artifact_ids: ["ART-E03-evidence"],
    conditions: [],
    expires_at: "2026-07-28T06:00:00Z",
  });
  assert.equal(approval.authority_id, E03_IDS.APPROVER);
  assert.equal(approval.authority_role, "product_owner");
  assert.match(approval.record_hash, /^sha256:[0-9a-f]{64}$/u);
  const instancePath = path.join(root, "approval.json");
  fs.writeFileSync(instancePath, JSON.stringify(approval), "utf8");
  const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
  const script = `
import json, pathlib, sys
from jsonschema import Draft202012Validator, FormatChecker
schema = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
instance = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
Draft202012Validator.check_schema(schema)
errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance))
if errors: raise SystemExit("; ".join(error.message for error in errors))
print("ApprovalRecord valid")
`;
  const result = spawnSync(
    "uv",
    [
      "run",
      "--locked",
      "python",
      "-",
      path.join(repositoryRoot, "schemas", "approval-record.schema.json"),
      instancePath,
    ],
    { cwd: repositoryRoot, encoding: "utf8", input: script },
  );
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  assert.equal(result.stdout.trim(), "ApprovalRecord valid");
});

test("fencing_test: exact approval retry returns its immutable result after expiry", (t) => {
  const { authority, setTime } = createCapabilityFixture(t);
  const first = issueCapabilityApproval(authority);
  setTime("2026-07-28T06:30:00Z");

  const retry = issueCapabilityApproval(authority);
  assert.deepEqual(retry, first);
  assert.equal(retry.issued_at, "2026-07-28T05:00:00Z");
  assert.equal(retry.expires_at, "2026-07-28T06:00:00Z");
});

test("fencing_test: self-approval is a non-waivable denial", (t) => {
  const { authority } = createCapabilityFixture(t);
  assert.throws(
    () =>
      authority.issueApproval(E03_IDS.APPROVER, {
        approval_id: "APR-E03-self",
        run_id: E03_IDS.RUN,
        subject_id: "WORK-E03-self",
        approval_type: "capability",
        decision: "APPROVE",
        reason: "self approval attempt",
        evidence_artifact_ids: ["ART-E03-self"],
        conditions: [],
        expires_at: "2026-07-28T06:00:00Z",
      }),
    expectCode("SELF_APPROVAL_DENIED"),
  );
});

test("fencing_test: promotion commit lease fails without approval and passes with exact approval", (t) => {
  const { authority } = createCapabilityFixture(t);
  const command = defaultLeaseCommand({
    lease_id: "LEASE-E03-approved",
    capabilities: ["promotion:commit"],
    resource_scopes: ["passport/e03"],
    approval_ids: [],
  });
  assert.throws(
    () => authority.issueLease(E03_IDS.AUTHORITY, command),
    expectCode("REQUIRED_APPROVAL_MISSING"),
  );
  const approval = issueCapabilityApproval(authority);
  const lease = authority.issueLease(E03_IDS.AUTHORITY, {
    ...command,
    approval_ids: [approval.approval_id],
  });
  assert.deepEqual(lease.approval_ids, [approval.approval_id]);
  const committed = authority.commitWithLease(
    defaultUseCommand(lease, {
      operation_id: "OP-E03-promotion",
      capability: "promotion:commit",
      resource_scopes: ["passport/e03"],
    }),
    () => ({ passport_revision: 8 }),
  );
  assert.equal(committed.status, "COMMITTED");
});

test("fencing_test: candidate/model/backend policy cannot grant privileged authority", () => {
  const policy = defaultPolicyInput();
  const candidate = policy.principals.find((entry) => entry.principal_id === E03_IDS.CANDIDATE);
  candidate.capabilities.push("promotion:commit");
  assert.throws(
    () => sealCapabilityPolicy(policy),
    expectCode("UNTRUSTED_AUTHORITY_GRANT_DENIED"),
  );
});

test("fencing_test: forged lease fields or hash cannot reach the mutation callback", (t) => {
  const { authority } = createCapabilityFixture(t);
  const lease = issueDefaultLease(authority);
  let invoked = false;
  assert.throws(
    () =>
      authority.commitWithLease(
        defaultUseCommand({ ...lease, fencing_token: lease.fencing_token + 100 }),
        () => {
          invoked = true;
          return null;
        },
      ),
    expectCode("LEASE_HASH_MISMATCH"),
  );
  assert.equal(invoked, false);
});

test("fencing_test: callback cannot access authority-private scope-head state", (t) => {
  const { authority, stateStore } = createCapabilityFixture(t);
  const lease = issueDefaultLease(authority);

  assert.throws(
    () =>
      authority.commitWithLease(
        defaultUseCommand(lease, { operation_id: "OP-E03-scope-head-tamper" }),
        (store) => {
          store.readRevisionedRecord("foundry.capabilities.scope-head.v1", "forged-scope-id");
          return { forged: true };
        },
      ),
    expectCode("CAPABILITY_STATE_ACCESS_DENIED"),
  );
  const valid = authority.commitWithLease(
    defaultUseCommand(lease, { operation_id: "OP-E03-after-scope-head-tamper" }),
    () => ({ valid: true }),
  );
  assert.equal(valid.status, "COMMITTED");
  assert.equal(stateStore.readRevisionedRecord("e03.test.result", "forged-scope-id"), null);
});

test("fencing_test: async callback is denied and its pre-await mutation rolls back", async (t) => {
  const { authority, stateStore } = createCapabilityFixture(t);
  const lease = issueDefaultLease(authority);
  assert.throws(
    () =>
      authority.commitWithLease(
        defaultUseCommand(lease, { operation_id: "OP-E03-async" }),
        async (store) => {
          store.createRevisionedRecord({
            recordType: "e03.test.result",
            recordId: "ASYNC",
            value: { should_not_persist: true },
          });
          await Promise.resolve();
          return null;
        },
      ),
    expectCode("ASYNC_LEASE_COMMIT_DENIED"),
  );
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(stateStore.readRevisionedRecord("e03.test.result", "ASYNC"), null);
});

test("fencing_test: lease use and revocation are bound to the sealed run", (t) => {
  const { authority } = createCapabilityFixture(t);
  const lease = issueDefaultLease(authority);
  let invoked = false;

  assert.throws(
    () =>
      authority.commitWithLease(
        defaultUseCommand(lease, {
          operation_id: "OP-E03-cross-run",
          run_id: "RUN-E03-other",
        }),
        () => {
          invoked = true;
          return null;
        },
      ),
    expectCode("LEASE_RUN_SCOPE_MISMATCH"),
  );
  assert.equal(invoked, false);
  assert.throws(
    () =>
      authority.revokeLease(E03_IDS.AUTHORITY, {
        lease_id: lease.lease_id,
        run_id: "RUN-E03-other",
        reason: "cross-run revocation attempt",
      }),
    expectCode("LEASE_RUN_SCOPE_MISMATCH"),
  );
  assert.equal(authority.readLease(lease.lease_id).revoked, false);
});

test("fencing_test: approval authority role without approval:issue capability is denied", (t) => {
  const policyInput = defaultPolicyInput();
  const approver = policyInput.principals.find(
    (entry) => entry.principal_id === E03_IDS.APPROVER,
  );
  approver.capabilities = [];
  const { authority } = createCapabilityFixture(t, { policy: policyInput });

  assert.throws(
    () =>
      authority.issueApproval(E03_IDS.APPROVER, {
        approval_id: "APR-E03-role-only",
        run_id: E03_IDS.RUN,
        subject_id: E03_IDS.LEASE,
        approval_type: "capability",
        decision: "APPROVE",
        reason: "role alone must not mint approval authority",
        evidence_artifact_ids: ["ART-E03-role-only"],
        conditions: [],
        expires_at: "2026-07-28T06:00:00Z",
      }),
    expectCode("CAPABILITY_NOT_AUTHORIZED"),
  );
});

test("fencing_test: later REVOKE head invalidates an earlier APPROVE-bound lease", (t) => {
  const { authority, setTime } = createCapabilityFixture(t);
  const approval = issueCapabilityApproval(authority);
  const lease = authority.issueLease(
    E03_IDS.AUTHORITY,
    defaultLeaseCommand({
      lease_id: "LEASE-E03-approved",
      capabilities: ["promotion:commit"],
      resource_scopes: ["passport/e03"],
      approval_ids: [approval.approval_id],
    }),
  );
  const before = authority.commitWithLease(
    defaultUseCommand(lease, {
      operation_id: "OP-E03-before-approval-revoke",
      capability: "promotion:commit",
      resource_scopes: ["passport/e03"],
    }),
    () => ({ passport_revision: 2 }),
  );
  assert.equal(before.status, "COMMITTED");

  setTime("2026-07-28T05:10:00Z");
  const revocation = authority.issueApproval(E03_IDS.APPROVER, {
    approval_id: "APR-E03-capability-revoke",
    run_id: E03_IDS.RUN,
    subject_id: "LEASE-E03-approved",
    approval_type: "capability",
    decision: "REVOKE",
    reason: "promotion pack authority was withdrawn",
    evidence_artifact_ids: ["ART-E03-revocation"],
    conditions: [],
    expires_at: null,
  });
  assert.equal(revocation.decision, "REVOKE");
  assert.equal(authority.readApproval(approval.approval_id).decision, "APPROVE");

  assert.throws(
    () =>
      authority.commitWithLease(
        defaultUseCommand(lease, {
          operation_id: "OP-E03-after-approval-revoke",
          capability: "promotion:commit",
          resource_scopes: ["passport/e03"],
        }),
        () => ({ passport_revision: 3 }),
      ),
    expectCode("REQUIRED_APPROVAL_MISSING"),
  );
});

test("fencing_test: approval head rejects clock regression and rolls back the proposed record", (t) => {
  const { authority, setTime } = createCapabilityFixture(t);
  issueCapabilityApproval(authority);
  setTime("2026-07-28T04:59:59Z");

  assert.throws(
    () =>
      authority.issueApproval(E03_IDS.APPROVER, {
        approval_id: "APR-E03-regressed-revoke",
        run_id: E03_IDS.RUN,
        subject_id: "LEASE-E03-approved",
        approval_type: "capability",
        decision: "REVOKE",
        reason: "regressed authority time must not replace a newer approval head",
        evidence_artifact_ids: ["ART-E03-regressed-revoke"],
        conditions: [],
        expires_at: null,
      }),
    expectCode("APPROVAL_CLOCK_REGRESSION"),
  );
  assert.throws(
    () => authority.readApproval("APR-E03-regressed-revoke"),
    expectCode("CAPABILITY_STATE_MISSING"),
  );
});

test("fencing_test: approval head rejects distinct decisions at the same instant", (t) => {
  const { authority } = createCapabilityFixture(t);
  issueCapabilityApproval(authority);

  assert.throws(
    () =>
      authority.issueApproval(E03_IDS.APPROVER, {
        approval_id: "APR-E03-same-time-revoke",
        run_id: E03_IDS.RUN,
        subject_id: "LEASE-E03-approved",
        approval_type: "capability",
        decision: "REVOKE",
        reason: "same-instant decisions must not receive an ambiguous head ordering",
        evidence_artifact_ids: ["ART-E03-same-time-revoke"],
        conditions: [],
        expires_at: null,
      }),
    expectCode("APPROVAL_TIMESTAMP_CONFLICT"),
  );
  assert.throws(
    () => authority.readApproval("APR-E03-same-time-revoke"),
    expectCode("CAPABILITY_STATE_MISSING"),
  );
});

test("fencing_test: committed state survives E01 outage and reconciles exactly once", (t) => {
  const fixture = createCapabilityFixture(t);
  let failNextAppend = true;
  const flakyLedger = {
    append(input) {
      if (failNextAppend) {
        failNextAppend = false;
        const error = new Error("synthetic E01 outage");
        error.code = "E01_UNAVAILABLE";
        throw error;
      }
      return fixture.ledger.append(input);
    },
  };
  const authority = createCapabilityAuthority({
    artifactStore: fixture.artifactStore,
    ledger: flakyLedger,
    stateStore: fixture.stateStore,
    policy: fixture.policy,
    clock: () => "2026-07-28T05:00:00Z",
  });

  assert.throws(
    () => authority.issueLease(E03_IDS.AUTHORITY, defaultLeaseCommand()),
    expectCode("CAPABILITY_EVENT_RECONCILIATION_REQUIRED"),
  );
  const committedLease = authority.readLease(E03_IDS.LEASE);
  assert.equal(committedLease.fencing_token, 1);
  assert.deepEqual(fixture.ledger.readEvents(E03_IDS.RUN), []);

  assert.deepEqual(authority.reconcileEvents(), { existing: 0, published: 1, total: 1 });
  assert.equal(fixture.ledger.readEvents(E03_IDS.RUN).length, 1);
  assert.deepEqual(authority.reconcileEvents(), { existing: 1, published: 0, total: 1 });
  assert.equal(fixture.ledger.readEvents(E03_IDS.RUN).length, 1);
});

test("fencing_test: same PolicyBundle hash with a different capability projection is rejected", (t) => {
  const fixture = createCapabilityFixture(t);
  const lease = issueDefaultLease(fixture.authority);
  const changedInput = defaultPolicyInput({ hash: fixture.policy.policy_hash });
  changedInput.subjects.push(
    leaseSubject({
      subjectId: "LEASE-E03-unrelated-projection-change",
      capabilities: ["sandbox:execute"],
      resourceScopes: ["workspace/e03"],
    }),
  );
  const changedPolicy = sealCapabilityPolicy(changedInput);
  assert.equal(changedPolicy.policy_hash, fixture.policy.policy_hash);
  assert.notEqual(changedPolicy.projection_hash, fixture.policy.projection_hash);
  const changedAuthority = createCapabilityAuthority({
    artifactStore: fixture.artifactStore,
    ledger: fixture.ledger,
    stateStore: fixture.stateStore,
    policy: changedPolicy,
    clock: () => "2026-07-28T05:05:00Z",
  });
  assert.throws(
    () =>
      changedAuthority.commitWithLease(
        defaultUseCommand(lease, { operation_id: "OP-E03-projection-change" }),
        () => ({ forbidden: true }),
      ),
    expectCode("LEASE_POLICY_PROJECTION_MISMATCH"),
  );
});
