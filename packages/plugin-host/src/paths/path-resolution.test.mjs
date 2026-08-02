import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  PATH_BOUNDARY,
  PATH_TARGET_MODE,
  PluginPathResolutionError,
  resolveBoundaryPath,
  resolvePluginPaths,
} from "./path-resolution.mjs";

const expectCode = (code) => (error) =>
  error instanceof PluginPathResolutionError && error.code === code;

const withRoots = (t, { createWorkspaceState = true } = {}) => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), "foundry G03 한글 "));
  const pluginRoot = path.join(parent, "installed plugin", "배포 코드");
  const pluginData = path.join(parent, "plugin data", "쓰기 상태");
  const workspaceRoot = path.join(parent, "workspace with spaces", "연구 프로젝트");
  fs.mkdirSync(pluginRoot, { recursive: true });
  fs.mkdirSync(pluginData, { recursive: true });
  fs.mkdirSync(workspaceRoot, { recursive: true });
  if (createWorkspaceState) {
    fs.mkdirSync(path.join(workspaceRoot, ".epistemic-foundry"));
  }
  t.after(() => fs.rmSync(parent, { recursive: true, force: true }));
  return { pluginRoot, pluginData, workspaceRoot };
};

test("path_resolution_test: explicit roots preserve spaces and non-ASCII names", (t) => {
  const roots = withRoots(t);
  const resolution = resolvePluginPaths(roots);

  assert.equal(resolution.pluginRoot, fs.realpathSync.native(roots.pluginRoot));
  assert.equal(resolution.pluginData, fs.realpathSync.native(roots.pluginData));
  assert.equal(resolution.workspaceRoot, fs.realpathSync.native(roots.workspaceRoot));
  assert.equal(
    resolution.workspaceStateRoot,
    path.join(fs.realpathSync.native(roots.workspaceRoot), ".epistemic-foundry"),
  );
  assert.equal(resolution.workspaceStateExists, true);
  assert.equal(resolution.explicitInputs, true);
  assert.equal(resolution.noFollowChecked, true);
  assert.equal(Object.isFrozen(resolution), true);
});

test("path_resolution_test: a fresh explicit workspace has one deterministic state location", (t) => {
  const roots = withRoots(t, { createWorkspaceState: false });
  const resolution = resolvePluginPaths(roots);

  assert.equal(
    resolution.workspaceStateRoot,
    path.join(fs.realpathSync.native(roots.workspaceRoot), ".epistemic-foundry"),
  );
  assert.equal(resolution.workspaceStateExists, false);

  assert.throws(
    () =>
      resolveBoundaryPath(resolution, {
        boundary: PATH_BOUNDARY.WORKSPACE_STATE,
        relativePath: "foundry.db",
        targetMode: PATH_TARGET_MODE.CREATE,
      }),
    expectCode("BOUNDARY_ROOT_UNAVAILABLE"),
  );

  fs.mkdirSync(resolution.workspaceStateRoot);
  const refreshed = resolvePluginPaths(roots);
  const target = resolveBoundaryPath(refreshed, {
    boundary: PATH_BOUNDARY.WORKSPACE_STATE,
    relativePath: "foundry.db",
    targetMode: PATH_TARGET_MODE.CREATE,
  });
  assert.equal(target.canonicalPath, path.join(refreshed.workspaceStateRoot, "foundry.db"));
  assert.equal(target.targetExists, false);
});

test("path_resolution_test: root traversal and linked workspace state fail closed", (t) => {
  const roots = withRoots(t, { createWorkspaceState: false });
  assert.throws(
    () =>
      resolvePluginPaths({
        ...roots,
        pluginRoot: `${roots.pluginRoot}${path.sep}..${path.sep}${path.basename(roots.pluginRoot)}`,
      }),
    expectCode("ROOT_TRAVERSAL_DENIED"),
  );

  const outside = path.join(path.dirname(roots.workspaceRoot), "outside state");
  fs.mkdirSync(outside);
  fs.symlinkSync(
    outside,
    path.join(roots.workspaceRoot, ".epistemic-foundry"),
    process.platform === "win32" ? "junction" : "dir",
  );
  assert.throws(() => resolvePluginPaths(roots), expectCode("ROOT_UNSAFE"));
});

test("path_resolution_test: missing or relative roots never fall back to cwd or environment", (t) => {
  const roots = withRoots(t);
  const previousRoot = process.env.PLUGIN_ROOT;
  const previousData = process.env.PLUGIN_DATA;
  process.env.PLUGIN_ROOT = roots.pluginRoot;
  process.env.PLUGIN_DATA = roots.pluginData;
  try {
    assert.throws(
      () => resolvePluginPaths({ pluginData: roots.pluginData, workspaceRoot: roots.workspaceRoot }),
      expectCode("MISSING_FIELD"),
    );
    assert.throws(
      () =>
        resolvePluginPaths({
          pluginRoot: ".",
          pluginData: roots.pluginData,
          workspaceRoot: roots.workspaceRoot,
        }),
      expectCode("ROOT_NOT_ABSOLUTE"),
    );
  } finally {
    if (previousRoot === undefined) delete process.env.PLUGIN_ROOT;
    else process.env.PLUGIN_ROOT = previousRoot;
    if (previousData === undefined) delete process.env.PLUGIN_DATA;
    else process.env.PLUGIN_DATA = previousData;
  }
});

test("path_resolution_test: installed code and writable data cannot overlap", (t) => {
  const roots = withRoots(t);
  const nestedData = path.join(roots.pluginRoot, "data");
  fs.mkdirSync(nestedData);

  assert.throws(
    () => resolvePluginPaths({ ...roots, pluginData: nestedData }),
    expectCode("PATH_BOUNDARY_OVERLAP"),
  );
  assert.throws(
    () => resolvePluginPaths({ ...roots, pluginData: roots.pluginRoot }),
    expectCode("PATH_BOUNDARY_OVERLAP"),
  );
});

test("path_resolution_test: workspace state cannot be placed under installed code", (t) => {
  const roots = withRoots(t);
  const workspaceRoot = path.join(roots.pluginRoot, "workspace");
  fs.mkdirSync(path.join(workspaceRoot, ".epistemic-foundry"), { recursive: true });

  assert.throws(
    () => resolvePluginPaths({ ...roots, workspaceRoot }),
    expectCode("PATH_BOUNDARY_OVERLAP"),
  );
});

test("path_resolution_test: plugin data and workspace boundaries cannot overlap", (t) => {
  const roots = withRoots(t);
  const nestedData = path.join(roots.workspaceRoot, "host data");
  fs.mkdirSync(nestedData);

  assert.throws(
    () => resolvePluginPaths({ ...roots, pluginData: nestedData }),
    expectCode("PATH_BOUNDARY_OVERLAP"),
  );
  assert.throws(
    () => resolvePluginPaths({ ...roots, pluginData: roots.workspaceRoot }),
    expectCode("PATH_BOUNDARY_OVERLAP"),
  );
});

test("path_resolution_test: strict inputs reject unknown fields, accessors, and Proxies", (t) => {
  const roots = withRoots(t);
  assert.throws(
    () => resolvePluginPaths({ ...roots, cwdFallback: process.cwd() }),
    expectCode("UNEXPECTED_FIELD"),
  );

  let getterRan = false;
  const accessorInput = { pluginData: roots.pluginData, workspaceRoot: roots.workspaceRoot };
  Object.defineProperty(accessorInput, "pluginRoot", {
    enumerable: true,
    get() {
      getterRan = true;
      return roots.pluginRoot;
    },
  });
  assert.throws(() => resolvePluginPaths(accessorInput), expectCode("ACCESSOR_FIELD_DENIED"));
  assert.equal(getterRan, false);

  let proxyTrapRan = false;
  const proxy = new Proxy(
    {},
    {
      ownKeys() {
        proxyTrapRan = true;
        return [];
      },
    },
  );
  assert.throws(() => resolvePluginPaths(proxy), expectCode("PROXY_INPUT_DENIED"));
  assert.equal(proxyTrapRan, false);
});
