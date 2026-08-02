import assert from "node:assert/strict";
import test from "node:test";

import {
  ObservabilityError,
  REDACTION_PLACEHOLDER,
  assertNoResidualSecrets,
  redactRecord,
} from "./index.mjs";

const errorCode = (code) => (error) =>
  error instanceof ObservabilityError && error.code === code;

test("log_redaction_test: sensitive keys are dropped whole and the input is not mutated", () => {
  const record = {
    password: "hunter2",
    api_key: "sk-live-abc",
    session_token: 123456,
    user: "alice",
  };
  const before = structuredClone(record);
  const result = redactRecord(record);
  assert.deepEqual(record, before);
  assert.equal(result.redacted.password, REDACTION_PLACEHOLDER);
  assert.equal(result.redacted.api_key, REDACTION_PLACEHOLDER);
  assert.equal(result.redacted.session_token, REDACTION_PLACEHOLDER);
  assert.equal(result.redacted.user, "alice");
  assert.equal(result.redaction_count, 3);
  assert.match(result.redaction_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.ok(Object.isFrozen(result));
  assert.deepEqual(assertNoResidualSecrets(result.redacted), result.redacted);
});

test("log_redaction_test: secret- and PII-shaped values are redacted in place", () => {
  const result = redactRecord({
    message: "reach me at alice@example.com",
    header: "Authorization: Bearer abc.def.ghijklmnop",
    jwt: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
    aws: "AKIAIOSFODNN7EXAMPLE",
    ssn: "078-05-1120",
  });
  assert.equal(result.redacted.message, `reach me at ${REDACTION_PLACEHOLDER}`);
  assert.ok(result.redacted.header.includes(REDACTION_PLACEHOLDER));
  assert.equal(result.redacted.jwt, REDACTION_PLACEHOLDER);
  assert.equal(result.redacted.aws, REDACTION_PLACEHOLDER);
  assert.equal(result.redacted.ssn, REDACTION_PLACEHOLDER);
  assertNoResidualSecrets(result.redacted);
});

test("log_redaction_test: nested records and arrays are redacted recursively", () => {
  const result = redactRecord({
    outer: { credentials: ["sk-1", "sk-2"], safe: "ok" },
    contacts: ["a@b.com", "plain text"],
  });
  assert.deepEqual(result.redacted.outer.credentials, [REDACTION_PLACEHOLDER, REDACTION_PLACEHOLDER]);
  assert.equal(result.redacted.outer.safe, "ok");
  assert.equal(result.redacted.contacts[0], REDACTION_PLACEHOLDER);
  assert.equal(result.redacted.contacts[1], "plain text");
  assertNoResidualSecrets(result.redacted);
});

test("log_redaction_test: a clean record produces zero redactions honestly", () => {
  const result = redactRecord({ user: "alice", count: 3, ok: true, tags: ["x", "y"] });
  assert.equal(result.redaction_count, 0);
  assert.deepEqual(result.redactions, []);
  assert.deepEqual(result.redacted, { count: 3, ok: true, tags: ["x", "y"], user: "alice" });
});

test("log_redaction_test: required redactions that were not applied fail closed", () => {
  assert.throws(
    () => redactRecord({ user: "alice" }, { required_redactions: ["password"] }),
    errorCode("REDACTION_REQUIRED_MISSING"),
  );
  const ok = redactRecord({ password: "hunter2" }, { required_redactions: ["password"] });
  assert.equal(ok.redacted.password, REDACTION_PLACEHOLDER);
});

test("log_redaction_test: malformed input and options fail closed", () => {
  assert.throws(() => redactRecord(new Proxy({}, {})), errorCode("REDACTION_INPUT_INVALID"));
  assert.throws(() => redactRecord([1, 2, 3]), errorCode("REDACTION_INPUT_INVALID"));
  assert.throws(() => redactRecord({ a: 1 }, { unknown: true }), errorCode("REDACTION_INPUT_INVALID"));
  assert.throws(
    () => redactRecord({ a: 1 }, { required_redactions: [123] }),
    errorCode("REDACTION_INPUT_INVALID"),
  );
});

test("log_redaction_test: redaction is order-independent and deterministic", () => {
  const first = redactRecord({ password: "x", email: "a@b.com", user: "u" });
  const second = redactRecord({ user: "u", email: "a@b.com", password: "x" });
  assert.equal(first.redaction_hash, second.redaction_hash);
  assert.deepEqual(second.redacted, first.redacted);
});

test("log_redaction_test: residual-secret assertion catches an unredacted leak", () => {
  assert.throws(
    () => assertNoResidualSecrets({ token: "still-here" }),
    errorCode("RESIDUAL_SECRET"),
  );
  assert.throws(
    () => assertNoResidualSecrets({ note: "mail a@b.com" }),
    errorCode("RESIDUAL_SECRET"),
  );
});
