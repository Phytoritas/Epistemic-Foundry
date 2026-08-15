import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  ExecutionSecurityError,
  NETWORK_POLICY,
  PATH_OPERATION,
  createExecutionSecurityBoundary,
} from "./execution-policy.mjs";

const expectCode = (code) => (error) =>
  error instanceof ExecutionSecurityError && error.code === code;

const withResourceRoot = (callback) => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), "foundry-s02-"));
  const root = path.join(parent, "root");
  fs.mkdirSync(path.join(root, "data"), { recursive: true });
  fs.writeFileSync(path.join(root, "data", "input.txt"), "fixture", "utf8");
  try {
    return callback({ parent, root });
  } finally {
    fs.rmSync(parent, { recursive: true, force: true });
  }
};

const boundary = createExecutionSecurityBoundary();
const { issuer, guard } = boundary;

const createPolicy = (root, overrides = {}) =>
  issuer.issueExecutionPolicy({
    policyId: "policy-path-test",
    sandboxProfileId: "sandbox-path-test",
    networkPolicy: NETWORK_POLICY.ALLOWLIST,
    egressAllowlist: ["https://api.example.test", "http://localhost:8080"],
    resourceRoots: [
      {
        rootId: "workspace",
        path: root,
        operations: [
          PATH_OPERATION.READ,
          PATH_OPERATION.WRITE,
          PATH_OPERATION.CREATE,
          PATH_OPERATION.LIST,
        ],
      },
    ],
    ...overrides,
  });

test("canonical in-root paths are authorized with scoped operations", () =>
  withResourceRoot(({ root }) => {
    const policy = createPolicy(root);
    assert.equal(guard.isExecutionPolicy(policy), true);
    assert.equal(Object.isFrozen(policy), true);

    const decision = guard.authorizePathAccess(policy, {
      rootId: "workspace",
      relativePath: "data/input.txt",
      operation: PATH_OPERATION.READ,
    });
    assert.equal(decision.decision, "ALLOW");
    assert.equal(decision.canonicalPath, path.join(root, "data", "input.txt"));
    assert.equal(decision.targetExists, true);
    assert.equal(decision.noFollowChecked, true);
    assert.equal(decision.sandboxProfileId, "sandbox-path-test");
    assert.equal(guard.isAuthorizationDecision(decision), true);
    assert.equal(guard.isAuthorizationDecision({ ...decision }), false);

    const future = guard.authorizePathAccess(policy, {
      rootId: "workspace",
      relativePath: "data/future.txt",
      operation: PATH_OPERATION.CREATE,
    });
    assert.equal(future.canonicalPath, path.join(root, "data", "future.txt"));
    assert.equal(future.targetExists, false);

    assert.throws(
      () =>
        guard.authorizePathAccess(policy, {
          rootId: "workspace",
          relativePath: "data/future.txt",
          operation: PATH_OPERATION.WRITE,
        }),
      expectCode("PATH_TARGET_MISSING"),
    );
    assert.throws(
      () =>
        guard.authorizePathAccess(policy, {
          rootId: "workspace",
          relativePath: "data/input.txt",
          operation: PATH_OPERATION.CREATE,
        }),
      expectCode("PATH_TARGET_EXISTS"),
    );

    assert.throws(
      () =>
        guard.authorizePathAccess(policy, {
          rootId: "workspace",
          relativePath: "missing-parent/future.txt",
          operation: PATH_OPERATION.CREATE,
        }),
      expectCode("PATH_PARENT_MISSING"),
    );

    assert.throws(
      () =>
        guard.authorizePathAccess(policy, {
          rootId: "workspace",
          relativePath: "data/input.txt",
          operation: PATH_OPERATION.DELETE,
        }),
      expectCode("PATH_SCOPE_DENIED"),
    );
    assert.throws(
      () =>
        guard.authorizePathAccess(policy, {
          rootId: "unknown-root",
          relativePath: "data/input.txt",
          operation: PATH_OPERATION.READ,
        }),
      expectCode("PATH_SCOPE_DENIED"),
    );
  }));

test("traversal, absolute, mixed-separator, alias, and platform-ambiguous paths are denied", () =>
  withResourceRoot(({ root }) => {
    const policy = createPolicy(root);
    const attacks = [
      "../outside.txt",
      "data/../../outside.txt",
      "/absolute/path.txt",
      "C:/absolute/path.txt",
      "data\\..\\outside.txt",
      "data\\input.txt",
      "data//input.txt",
      "./data/input.txt",
      "data/./input.txt",
      "data/input.txt:alternate",
      "data/trailing.",
      "data/trailing ",
      "NUL",
      "CONIN$",
      "COM¹.txt",
      "CON .txt",
    ];

    for (const relativePath of attacks) {
      assert.throws(
        () =>
          guard.authorizePathAccess(policy, {
            rootId: "workspace",
            relativePath,
            operation: PATH_OPERATION.READ,
          }),
        expectCode("PATH_ESCAPE_DENIED"),
        relativePath,
      );
    }
  }));

test("existing symlink or junction components are denied by no-follow policy", (t) =>
  withResourceRoot(({ parent, root }) => {
    const outside = path.join(parent, "outside");
    fs.mkdirSync(outside);
    fs.writeFileSync(path.join(outside, "secret.txt"), "synthetic fixture", "utf8");
    const link = path.join(root, "linked-outside");
    try {
      fs.symlinkSync(outside, link, process.platform === "win32" ? "junction" : "dir");
    } catch (error) {
      if (error !== null && typeof error === "object" && ["EPERM", "EACCES"].includes(error.code)) {
        t.skip("host does not permit creation of a symlink/junction fixture");
        return;
      }
      throw error;
    }

    const policy = createPolicy(root);
    assert.throws(
      () =>
        guard.authorizePathAccess(policy, {
          rootId: "workspace",
          relativePath: "linked-outside/secret.txt",
          operation: PATH_OPERATION.READ,
        }),
      expectCode("PATH_LINK_DENIED"),
    );
  }));

test("hard-linked final files are denied for read and write access", (t) =>
  withResourceRoot(({ parent, root }) => {
    const outside = path.join(parent, "outside-hard-link.txt");
    fs.writeFileSync(outside, "synthetic fixture", "utf8");
    const link = path.join(root, "data", "linked-outside.txt");
    try {
      fs.linkSync(outside, link);
    } catch (error) {
      if (
        error !== null &&
        typeof error === "object" &&
        ["EPERM", "EACCES", "ENOSYS", "ENOTSUP", "EOPNOTSUPP"].includes(error.code)
      ) {
        t.skip("host does not permit creation of a hard-link fixture");
        return;
      }
      throw error;
    }

    const policy = createPolicy(root);
    for (const operation of [PATH_OPERATION.READ, PATH_OPERATION.WRITE]) {
      assert.throws(
        () =>
          guard.authorizePathAccess(policy, {
            rootId: "workspace",
            relativePath: "data/linked-outside.txt",
            operation,
          }),
        expectCode("PATH_LINK_DENIED"),
        operation,
      );
    }
  }));

test("linked resource roots and non-directory traversal are denied", (t) =>
  withResourceRoot(({ parent, root }) => {
    assert.throws(
      () =>
        guard.authorizePathAccess(createPolicy(root), {
          rootId: "workspace",
          relativePath: "data/input.txt/child",
          operation: PATH_OPERATION.READ,
        }),
      expectCode("PATH_NOT_TRAVERSABLE"),
    );

    const linkedRoot = path.join(parent, "linked-root");
    try {
      fs.symlinkSync(root, linkedRoot, process.platform === "win32" ? "junction" : "dir");
    } catch (error) {
      if (error !== null && typeof error === "object" && ["EPERM", "EACCES"].includes(error.code)) {
        t.skip("host does not permit creation of a symlink/junction fixture");
        return;
      }
      throw error;
    }
    assert.throws(() => createPolicy(linkedRoot), expectCode("RESOURCE_ROOT_UNSAFE"));
  }));

test("egress uses exact canonical origins and defaults to denial", () =>
  withResourceRoot(({ root }) => {
    const policy = createPolicy(root);
    const allowed = guard.authorizeEgress(policy, {
      url: "https://api.example.test/v1/items?query=bounded",
      payload: { query: "bounded" },
    });
    assert.equal(allowed.origin, "https://api.example.test");
    assert.equal(allowed.secretMaterialExposed, false);
    assert.equal(allowed.redirectPolicy, "REAUTHORIZE_EACH_HOP");

    assert.throws(
      () => guard.authorizeEgress(policy, { url: "https://api.example.test.evil.invalid/v1" }),
      expectCode("EGRESS_DESTINATION_DENIED"),
    );
    assert.throws(
      () => guard.authorizeEgress(policy, { url: "http://api.example.test/v1" }),
      expectCode("EGRESS_DESTINATION_DENIED"),
    );
    assert.throws(
      () => guard.authorizeEgress(policy, { url: "https://api.example.test:444/v1" }),
      expectCode("EGRESS_DESTINATION_DENIED"),
    );
    assert.throws(
      () => guard.authorizeEgress(policy, { url: "/relative/network/path" }),
      expectCode("INVALID_EGRESS_URL"),
    );
    assert.throws(
      () => guard.authorizeEgress(policy, { url: "file:///tmp/fixture" }),
      expectCode("INVALID_EGRESS_URL"),
    );

    const disabled = createPolicy(root, {
      networkPolicy: NETWORK_POLICY.DISABLED,
      egressAllowlist: [],
    });
    assert.throws(
      () => guard.authorizeEgress(disabled, { url: "https://api.example.test/v1" }),
      expectCode("EGRESS_DISABLED"),
    );
  }));

test("allowlist and sandbox contracts reject inconsistent or unsupported policy", () =>
  withResourceRoot(({ root }) => {
    assert.throws(
      () => createPolicy(root, { networkPolicy: "unrestricted_with_approval" }),
      expectCode("UNSUPPORTED_NETWORK_POLICY"),
    );
    assert.throws(
      () =>
        createPolicy(root, {
          networkPolicy: NETWORK_POLICY.DISABLED,
          egressAllowlist: ["https://api.example.test"],
        }),
      expectCode("INCONSISTENT_NETWORK_POLICY"),
    );
    assert.throws(
      () =>
        createPolicy(root, {
          networkPolicy: NETWORK_POLICY.ALLOWLIST,
          egressAllowlist: [],
        }),
      expectCode("INCONSISTENT_NETWORK_POLICY"),
    );
    assert.throws(
      () =>
        createPolicy(root, {
          egressAllowlist: ["https://api.example.test/path"],
        }),
      expectCode("INVALID_ALLOWLIST_ORIGIN"),
    );

    const policy = createPolicy(root);
    assert.equal(guard.assertSandboxProfile(policy, "sandbox-path-test").decision, "ALLOW");
    assert.throws(
      () => guard.assertSandboxProfile(policy, "different-sandbox"),
      expectCode("SANDBOX_PROFILE_MISMATCH"),
    );
  }));

test("policy and request Proxies, accessors, and serialized lookalikes fail without execution", () =>
  withResourceRoot(({ root }) => {
    const policy = createPolicy(root);
    assert.throws(
      () =>
        guard.authorizePathAccess({ ...policy }, {
          rootId: "workspace",
          relativePath: "data/input.txt",
          operation: PATH_OPERATION.READ,
        }),
      expectCode("UNRECOGNIZED_POLICY"),
    );

    let getterRan = false;
    const accessorRequest = {
      rootId: "workspace",
      operation: PATH_OPERATION.READ,
    };
    Object.defineProperty(accessorRequest, "relativePath", {
      enumerable: true,
      get() {
        getterRan = true;
        return "data/input.txt";
      },
    });
    assert.throws(
      () => guard.authorizePathAccess(policy, accessorRequest),
      expectCode("ACCESSOR_FIELD_DENIED"),
    );
    assert.equal(getterRan, false);

    let proxyTrapRan = false;
    const proxyRequest = new Proxy(
      {},
      {
        ownKeys() {
          proxyTrapRan = true;
          return [];
        },
      },
    );
    assert.throws(
      () => guard.authorizeEgress(policy, proxyRequest),
      expectCode("PROXY_INPUT_DENIED"),
    );
    assert.equal(proxyTrapRan, false);
  }));

test("resource root identity is revalidated after policy issue", () =>
  withResourceRoot(({ parent, root }) => {
    const policy = createPolicy(root);
    const originalRoot = path.join(parent, "original-root");
    fs.renameSync(root, originalRoot);
    fs.mkdirSync(path.join(root, "data"), { recursive: true });
    fs.writeFileSync(path.join(root, "data", "input.txt"), "replacement", "utf8");

    assert.throws(
      () =>
        guard.authorizePathAccess(policy, {
          rootId: "workspace",
          relativePath: "data/input.txt",
          operation: PATH_OPERATION.READ,
        }),
      expectCode("RESOURCE_ROOT_CHANGED"),
    );
  }));

test("egress rejects fragments and requires each redirect hop to be reauthorized", () =>
  withResourceRoot(({ root }) => {
    const policy = createPolicy(root);
    assert.throws(
      () =>
        guard.authorizeEgress(policy, {
          url: "https://api.example.test/v1#access_token=synthetic-fixture",
        }),
      expectCode("EGRESS_FRAGMENT_DENIED"),
    );
    assert.throws(
      () => guard.authorizeEgress(policy, { url: "https://redirected.example.test/v1" }),
      expectCode("EGRESS_DESTINATION_DENIED"),
    );
  }));
