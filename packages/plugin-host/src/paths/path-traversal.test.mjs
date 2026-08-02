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

const withBoundary = (t) => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), "foundry G03 traversal "));
  const pluginRoot = path.join(parent, "plugin root");
  const pluginData = path.join(parent, "plugin data");
  const workspaceRoot = path.join(parent, "작업 공간");
  const workspaceState = path.join(workspaceRoot, ".epistemic-foundry");
  fs.mkdirSync(path.join(pluginRoot, "dist"), { recursive: true });
  fs.mkdirSync(path.join(pluginData, "cache"), { recursive: true });
  fs.mkdirSync(path.join(workspaceState, "artifacts", "한글 자료"), { recursive: true });
  fs.writeFileSync(path.join(pluginRoot, "dist", "cli.mjs"), "export {};\n", "utf8");
  fs.writeFileSync(
    path.join(workspaceState, "artifacts", "한글 자료", "receipt.json"),
    "{}\n",
    "utf8",
  );
  t.after(() => fs.rmSync(parent, { recursive: true, force: true }));
  return {
    parent,
    pluginRoot,
    pluginData,
    workspaceRoot,
    resolution: resolvePluginPaths({ pluginRoot, pluginData, workspaceRoot }),
  };
};

test("path_traversal_test: valid portable children remain inside their selected boundary", (t) => {
  const { pluginData, workspaceRoot, resolution } = withBoundary(t);

  const existing = resolveBoundaryPath(resolution, {
    boundary: PATH_BOUNDARY.WORKSPACE_STATE,
    relativePath: "artifacts/한글 자료/receipt.json",
    targetMode: PATH_TARGET_MODE.EXISTING,
  });
  assert.equal(
    existing.canonicalPath,
    path.join(workspaceRoot, ".epistemic-foundry", "artifacts", "한글 자료", "receipt.json"),
  );
  assert.equal(existing.targetExists, true);
  assert.equal(existing.noFollowChecked, true);

  const create = resolveBoundaryPath(resolution, {
    boundary: PATH_BOUNDARY.PLUGIN_DATA,
    relativePath: "cache/new artifact.json",
    targetMode: PATH_TARGET_MODE.CREATE,
  });
  assert.equal(create.canonicalPath, path.join(pluginData, "cache", "new artifact.json"));
  assert.equal(create.targetExists, false);
});

test("path_traversal_test: traversal, absolute, mixed-separator, NUL, and alias paths fail closed", (t) => {
  const { resolution } = withBoundary(t);
  const attacks = [
    "../outside.txt",
    "artifacts/../../outside.txt",
    "/absolute/path.txt",
    "C:/absolute/path.txt",
    "artifacts\\..\\outside.txt",
    "artifacts\\receipt.json",
    "artifacts//receipt.json",
    "./artifacts/receipt.json",
    "artifacts/./receipt.json",
    "artifacts/receipt.json:alternate",
    "artifacts/<receipt>.json",
    "artifacts/receipt?.json",
    "artifacts/*.json",
    'artifacts/receipt"quote.json',
    "artifacts/receipt|pipe.json",
    "artifacts/trailing.",
    "artifacts/trailing ",
    "NUL",
    "CONIN$",
    "COM¹.txt",
    "bad\u0000name",
  ];

  for (const relativePath of attacks) {
    assert.throws(
      () =>
        resolveBoundaryPath(resolution, {
          boundary: PATH_BOUNDARY.WORKSPACE_STATE,
          relativePath,
          targetMode: PATH_TARGET_MODE.EXISTING,
        }),
      (error) =>
        error instanceof PluginPathResolutionError &&
        ["INVALID_PATH", "PATH_ESCAPE_DENIED"].includes(error.code),
      relativePath,
    );
  }
});

test("path_traversal_test: links, junctions, and linked roots are denied", (t) => {
  const fixture = withBoundary(t);
  const outside = path.join(fixture.parent, "outside");
  fs.mkdirSync(outside);
  fs.writeFileSync(path.join(outside, "secret.txt"), "synthetic fixture", "utf8");
  const link = path.join(fixture.workspaceRoot, ".epistemic-foundry", "linked-outside");
  fs.symlinkSync(outside, link, process.platform === "win32" ? "junction" : "dir");

  assert.throws(
    () =>
      resolveBoundaryPath(fixture.resolution, {
        boundary: PATH_BOUNDARY.WORKSPACE_STATE,
        relativePath: "linked-outside/secret.txt",
        targetMode: PATH_TARGET_MODE.EXISTING,
      }),
    expectCode("PATH_LINK_DENIED"),
  );

  const linkedPluginData = path.join(fixture.parent, "linked plugin data");
  fs.symlinkSync(
    fixture.pluginData,
    linkedPluginData,
    process.platform === "win32" ? "junction" : "dir",
  );
  assert.throws(
    () =>
      resolvePluginPaths({
        pluginRoot: fixture.pluginRoot,
        pluginData: linkedPluginData,
        workspaceRoot: fixture.workspaceRoot,
      }),
    expectCode("ROOT_UNSAFE"),
  );
});

test("path_traversal_test: missing parents and mismatched target modes are rejected", (t) => {
  const { resolution } = withBoundary(t);
  assert.throws(
    () =>
      resolveBoundaryPath(resolution, {
        boundary: PATH_BOUNDARY.PLUGIN_DATA,
        relativePath: "missing-parent/new.txt",
        targetMode: PATH_TARGET_MODE.CREATE,
      }),
    expectCode("PATH_PARENT_MISSING"),
  );
  assert.throws(
    () =>
      resolveBoundaryPath(resolution, {
        boundary: PATH_BOUNDARY.PLUGIN_DATA,
        relativePath: "cache/missing.txt",
        targetMode: PATH_TARGET_MODE.EXISTING,
      }),
    expectCode("PATH_TARGET_MISSING"),
  );
  assert.throws(
    () =>
      resolveBoundaryPath(resolution, {
        boundary: PATH_BOUNDARY.PLUGIN_DATA,
        relativePath: "cache",
        targetMode: PATH_TARGET_MODE.CREATE,
      }),
    expectCode("PATH_TARGET_EXISTS"),
  );
  assert.throws(
    () =>
      resolveBoundaryPath(resolution, {
        boundary: PATH_BOUNDARY.PLUGIN_ROOT,
        relativePath: "dist/new.mjs",
        targetMode: PATH_TARGET_MODE.CREATE,
      }),
    expectCode("BOUNDARY_WRITE_DENIED"),
  );
});

test("path_traversal_test: copied resolutions and replaced roots cannot retain authority", (t) => {
  const fixture = withBoundary(t);
  assert.throws(
    () =>
      resolveBoundaryPath({ ...fixture.resolution }, {
        boundary: PATH_BOUNDARY.PLUGIN_ROOT,
        relativePath: "dist/cli.mjs",
        targetMode: PATH_TARGET_MODE.EXISTING,
      }),
    expectCode("UNRECOGNIZED_PATH_RESOLUTION"),
  );

  const original = path.join(fixture.parent, "original plugin data");
  fs.renameSync(fixture.pluginData, original);
  fs.mkdirSync(path.join(fixture.pluginData, "cache"), { recursive: true });
  assert.throws(
    () =>
      resolveBoundaryPath(fixture.resolution, {
        boundary: PATH_BOUNDARY.PLUGIN_DATA,
        relativePath: "cache",
        targetMode: PATH_TARGET_MODE.EXISTING,
      }),
    expectCode("BOUNDARY_ROOT_CHANGED"),
  );
});
