import assert from "node:assert/strict";
import test from "node:test";

import {
  ExecutionSecurityError,
  NETWORK_POLICY,
  OUTBOUND_BOUNDARY,
  createExecutionSecurityBoundary,
} from "./execution-policy.mjs";

const expectCode = (code) => (error) =>
  error instanceof ExecutionSecurityError && error.code === code;

const boundary = createExecutionSecurityBoundary();
const { issuer, guard } = boundary;

const createNetworkPolicy = () =>
  issuer.issueExecutionPolicy({
    policyId: "policy-secret-test",
    sandboxProfileId: "sandbox-secret-test",
    networkPolicy: NETWORK_POLICY.ALLOWLIST,
    egressAllowlist: ["https://api.example.test"],
    resourceRoots: [],
  });

test("opaque secret handles expose no serializable identifier or secret material", () => {
  const handle = issuer.issueOpaqueSecretHandle({
    handleId: "handle-synthetic-001",
    vaultId: "vault-test",
    allowedOrigins: ["https://api.example.test"],
  });

  assert.equal(guard.isOpaqueSecretHandle(handle), true);
  assert.equal(Object.isFrozen(handle), true);
  assert.deepEqual(Reflect.ownKeys(handle), []);
  assert.equal(JSON.stringify(handle), "{}");
  assert.equal(guard.isOpaqueSecretHandle({}), false);
  assert.equal(guard.isOpaqueSecretHandle(JSON.parse(JSON.stringify(handle))), false);
});

test("secret handle construction rejects material-bearing and executable inputs", () => {
  assert.throws(
    () =>
      issuer.issueOpaqueSecretHandle({
        handleId: "handle-synthetic-002",
        vaultId: "vault-test",
        allowedOrigins: [],
        value: "synthetic-sensitive-fixture",
      }),
    expectCode("UNEXPECTED_FIELD"),
  );

  let getterRan = false;
  const accessorInput = {
    vaultId: "vault-test",
    allowedOrigins: [],
  };
  Object.defineProperty(accessorInput, "handleId", {
    enumerable: true,
    get() {
      getterRan = true;
      return "handle-synthetic-003";
    },
  });
  assert.throws(
    () => issuer.issueOpaqueSecretHandle(accessorInput),
    expectCode("ACCESSOR_FIELD_DENIED"),
  );
  assert.equal(getterRan, false);

  let proxyTrapRan = false;
  const proxyInput = new Proxy(
    {},
    {
      ownKeys() {
        proxyTrapRan = true;
        return [];
      },
    },
  );
  assert.throws(
    () => issuer.issueOpaqueSecretHandle(proxyInput),
    expectCode("PROXY_INPUT_DENIED"),
  );
  assert.equal(proxyTrapRan, false);
});

test("handles are denied at every prohibited outbound boundary", () => {
  const handle = issuer.issueOpaqueSecretHandle({
    handleId: "handle-synthetic-004",
    vaultId: "vault-test",
    allowedOrigins: [],
  });

  for (const boundary of [
    OUTBOUND_BOUNDARY.PROMPT,
    OUTBOUND_BOUNDARY.EVIDENCE_ARTIFACT,
    OUTBOUND_BOUNDARY.LOG,
    OUTBOUND_BOUNDARY.EXPORT,
    OUTBOUND_BOUNDARY.NETWORK_REQUEST,
  ]) {
    assert.throws(
      () => guard.assertSecretFreeBoundaryPayload({ nested: ["safe", handle] }, boundary),
      expectCode("SECRET_HANDLE_BOUNDARY_DENIED"),
    );
  }
});

test("raw secret-shaped fields and values fail closed", () => {
  assert.throws(
    () =>
      guard.assertSecretFreeBoundaryPayload(
        { api_key: "synthetic-sensitive-fixture" },
        OUTBOUND_BOUNDARY.PROMPT,
      ),
    expectCode("SECRET_FIELD_BOUNDARY_DENIED"),
  );
  assert.throws(
    () =>
      guard.assertSecretFreeBoundaryPayload(
        { text: "Authorization: Bearer synthetic-fixture-token" },
        OUTBOUND_BOUNDARY.LOG,
      ),
    expectCode("SECRET_PATTERN_BOUNDARY_DENIED"),
  );
  assert.throws(
    () =>
      guard.assertSecretFreeBoundaryPayload(
        { destination: "https://fixture-user:fixture-pass@example.test/path" },
        OUTBOUND_BOUNDARY.EXPORT,
      ),
    expectCode("SECRET_PATTERN_BOUNDARY_DENIED"),
  );

  const decision = guard.assertSecretFreeBoundaryPayload(
    { messages: [{ role: "user", content: "Summarize the bounded evidence." }] },
    OUTBOUND_BOUNDARY.PROMPT,
  );
  assert.equal(decision.status, "PASS");
  assert.equal(decision.secretMaterialExposed, false);
  assert.equal(decision.authorityEligible, false);
  assert.equal(guard.isAuthorizationDecision(decision), false);
});

test("payload inspection rejects accessors, Proxies, cycles, and non-JSON values without execution", () => {
  let getterRan = false;
  const accessorPayload = {};
  Object.defineProperty(accessorPayload, "content", {
    enumerable: true,
    get() {
      getterRan = true;
      return "synthetic-sensitive-fixture";
    },
  });
  assert.throws(
    () => guard.assertSecretFreeBoundaryPayload(accessorPayload, OUTBOUND_BOUNDARY.PROMPT),
    expectCode("ACCESSOR_FIELD_DENIED"),
  );
  assert.equal(getterRan, false);

  let proxyTrapRan = false;
  const proxyPayload = new Proxy(
    {},
    {
      ownKeys() {
        proxyTrapRan = true;
        return [];
      },
    },
  );
  assert.throws(
    () => guard.assertSecretFreeBoundaryPayload(proxyPayload, OUTBOUND_BOUNDARY.LOG),
    expectCode("PROXY_INPUT_DENIED"),
  );
  assert.equal(proxyTrapRan, false);

  const cyclic = {};
  cyclic.self = cyclic;
  assert.throws(
    () => guard.assertSecretFreeBoundaryPayload(cyclic, OUTBOUND_BOUNDARY.EXPORT),
    expectCode("CYCLIC_PAYLOAD_DENIED"),
  );
  assert.throws(
    () => guard.assertSecretFreeBoundaryPayload({ value: 1n }, OUTBOUND_BOUNDARY.PROMPT),
    expectCode("UNSUPPORTED_PAYLOAD_VALUE"),
  );
  assert.throws(
    () =>
      guard.assertSecretFreeBoundaryPayload(
        { ["x".repeat(1_025)]: "bounded" },
        OUTBOUND_BOUNDARY.PROMPT,
      ),
    expectCode("PAYLOAD_LIMIT_EXCEEDED"),
  );
  assert.throws(
    () =>
      guard.assertSecretFreeBoundaryPayload(
        Array.from({ length: 10_001 }, () => null),
        OUTBOUND_BOUNDARY.LOG,
      ),
    expectCode("INVALID_INPUT"),
  );
});

test("ordinary egress cannot carry handles or secret-shaped payloads", () => {
  const policy = createNetworkPolicy();
  const handle = issuer.issueOpaqueSecretHandle({
    handleId: "handle-synthetic-005",
    vaultId: "vault-test",
    allowedOrigins: ["https://api.example.test"],
  });

  assert.throws(
    () =>
      guard.authorizeEgress(policy, {
        url: "https://api.example.test/v1",
        payload: { authentication: handle },
      }),
    expectCode("SECRET_HANDLE_BOUNDARY_DENIED"),
  );
  assert.throws(
    () =>
      guard.authorizeEgress(policy, {
        url: "https://api.example.test/v1?access_token=synthetic-fixture",
      }),
    expectCode("SECRET_FIELD_BOUNDARY_DENIED"),
  );
  assert.throws(
    () =>
      guard.authorizeEgress(policy, {
        url: "https://fixture-user:fixture-pass@api.example.test/v1",
      }),
    expectCode("EGRESS_CREDENTIALS_DENIED"),
  );
});

test("last-mile secret use requires both policy and handle destination bindings", () => {
  const policy = createNetworkPolicy();
  const handle = issuer.issueOpaqueSecretHandle({
    handleId: "handle-synthetic-006",
    vaultId: "vault-test",
    allowedOrigins: ["https://api.example.test"],
  });

  const decision = guard.authorizeSecretEgress(policy, {
    handle,
    url: "https://api.example.test/v1/resource",
  });
  assert.deepEqual(decision, {
    decision: "ALLOW",
    purpose: "network_authentication",
    policyId: "policy-secret-test",
    sandboxProfileId: "sandbox-secret-test",
    origin: "https://api.example.test",
    redirectPolicy: "REAUTHORIZE_EACH_HOP",
    opaqueHandleValidated: true,
    secretMaterialExposed: false,
  });
  assert.equal(JSON.stringify(decision).includes("handle-synthetic-006"), false);
  assert.equal(JSON.stringify(decision).includes("vault-test"), false);

  const otherDestinationHandle = issuer.issueOpaqueSecretHandle({
    handleId: "handle-synthetic-007",
    vaultId: "vault-test",
    allowedOrigins: ["https://other.example.test"],
  });
  assert.throws(
    () =>
      guard.authorizeSecretEgress(policy, {
        handle: otherDestinationHandle,
        url: "https://api.example.test/v1/resource",
      }),
    expectCode("SECRET_DESTINATION_DENIED"),
  );
  assert.throws(
    () =>
      guard.authorizeSecretEgress(policy, {
        handle: {},
        url: "https://api.example.test/v1/resource",
      }),
    expectCode("UNRECOGNIZED_SECRET_HANDLE"),
  );
});

test("foreign boundaries cannot mint handles, policies, or decisions accepted here", () => {
  const foreign = createExecutionSecurityBoundary();
  const foreignPolicy = foreign.issuer.issueExecutionPolicy({
    policyId: "policy-foreign",
    sandboxProfileId: "sandbox-foreign",
    networkPolicy: NETWORK_POLICY.ALLOWLIST,
    egressAllowlist: ["https://api.example.test"],
    resourceRoots: [],
  });
  const foreignHandle = foreign.issuer.issueOpaqueSecretHandle({
    handleId: "handle-foreign",
    vaultId: "vault-foreign",
    allowedOrigins: ["https://api.example.test"],
  });
  const foreignDecision = foreign.guard.authorizeSecretEgress(foreignPolicy, {
    handle: foreignHandle,
    url: "https://api.example.test/v1",
  });

  assert.equal(guard.isOpaqueSecretHandle(foreignHandle), false);
  assert.equal(guard.isExecutionPolicy(foreignPolicy), false);
  assert.equal(guard.isAuthorizationDecision(foreignDecision), false);
  assert.throws(
    () => guard.authorizeEgress(foreignPolicy, { url: "https://api.example.test/v1" }),
    expectCode("UNRECOGNIZED_POLICY"),
  );
  assert.throws(
    () =>
      guard.authorizeSecretEgress(createNetworkPolicy(), {
        handle: foreignHandle,
        url: "https://api.example.test/v1",
      }),
    expectCode("UNRECOGNIZED_SECRET_HANDLE"),
  );
  assert.throws(
    () => guard.assertSecretFreeBoundaryPayload(foreignHandle, OUTBOUND_BOUNDARY.PROMPT),
    expectCode("SECRET_HANDLE_BOUNDARY_DENIED"),
  );
});

test("secret handles reject cleartext HTTP destination bindings", () => {
  assert.throws(
    () =>
      issuer.issueOpaqueSecretHandle({
        handleId: "handle-insecure",
        vaultId: "vault-test",
        allowedOrigins: ["http://api.example.test"],
      }),
    expectCode("INSECURE_SECRET_ORIGIN"),
  );
});
