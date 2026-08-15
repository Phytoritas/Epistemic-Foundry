import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);
const pluginName = "epistemic-foundry";
const repositoryPluginPrefix = `plugins/${pluginName}`;
const marketplaceName = "installed-dist-local-marketplace";
const selector = `${pluginName}@${marketplaceName}`;
const processTimeoutMs = 60_000;
const processMaxBuffer = 64 * 1024 * 1024;
const qualifiedPermissionRuntime = "26.4.0";
const qualifiedNodeExecutable = fs.realpathSync.native(process.execPath);
const qualifiedNodeDirectory = fs.realpathSync.native(path.dirname(qualifiedNodeExecutable));
const requiredHeadPaths = Object.freeze([
  ".codex-plugin/plugin.json",
  ".mcp.json",
  "bin/efoundry.mjs",
  "dist/cli.mjs",
  "hooks/session.json",
]);
const installedChildEnvironmentBaseKeys = Object.freeze([
  "APPDATA",
  "CLAUDE_PLUGIN_ROOT",
  "CODEX_HOME",
  "HOME",
  "LOCALAPPDATA",
  "PATH",
  "PLUGIN_DATA",
  "PLUGIN_ROOT",
  "TEMP",
  "TMP",
  "TMPDIR",
  "USERPROFILE",
]);
export const installedChildEnvironmentAllowlist = Object.freeze([
  ...installedChildEnvironmentBaseKeys,
  ...(process.platform === "win32" ? ["HOMEDRIVE", "HOMEPATH"] : []),
].sort());
const mcpDriverArgsEnvironmentKey = "EFOUNDRY_INSTALLED_DIST_MCP_ARGS";
const mcpDriverChildEnvironmentKey = "EFOUNDRY_INSTALLED_DIST_MCP_ENVIRONMENT";
const mcpDriverExecutableEnvironmentKey = "EFOUNDRY_INSTALLED_DIST_MCP_EXECUTABLE";
const mcpDriverEnvironmentAllowlist = Object.freeze([
  mcpDriverArgsEnvironmentKey,
  mcpDriverChildEnvironmentKey,
  mcpDriverExecutableEnvironmentKey,
  "PATH",
]);

function sha256(bytes) {
  return `sha256:${crypto.createHash("sha256").update(bytes).digest("hex")}`;
}

function fileState(filePath) {
  if (!fs.existsSync(filePath)) {
    return { exists: false, byte_size: null, sha256: null };
  }
  const bytes = fs.readFileSync(filePath);
  return { exists: true, byte_size: bytes.length, sha256: sha256(bytes) };
}

function parseJson(text, label) {
  try {
    return JSON.parse(text);
  } catch (cause) {
    throw new Error(`${label} did not return JSON: ${cause.message}\n${text}`);
  }
}

function objects(value, output = []) {
  if (Array.isArray(value)) {
    for (const item of value) objects(item, output);
  } else if (value !== null && typeof value === "object") {
    output.push(value);
    for (const item of Object.values(value)) objects(item, output);
  }
  return output;
}

function pluginEntry(payload) {
  const candidates = objects(payload).filter((entry) => {
    const identities = [
      entry.name,
      entry.plugin_name,
      entry.id,
      entry.selector,
      entry.plugin,
    ];
    return identities.includes(pluginName) || identities.includes(selector);
  });
  const entry = candidates.find((candidate) => typeof candidate.enabled === "boolean");
  assert.ok(entry, `plugin state missing for ${selector}: ${JSON.stringify(payload)}`);
  return entry;
}

function containsPersonalMarketplace(payload) {
  return objects(payload).some(
    (entry) =>
      entry.marketplaceName === "personal" ||
      entry.marketplace_name === "personal" ||
      (entry.name === "personal" && typeof entry.root === "string"),
  );
}

function isWithin(root, candidate, { allowRoot = false } = {}) {
  const relative = path.relative(root, candidate);
  if (relative === "") return allowRoot;
  return relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

function assertNoRepositoryPath(value, label) {
  const normalize = (candidate) => candidate
    .replaceAll("\\", "/")
    .replace(/\/{2,}/gu, "/")
    .toLowerCase();
  const normalizedValue = normalize(String(value));
  const repositoryVariants = new Set([
    normalize(repositoryRoot),
    normalize(fs.realpathSync.native(repositoryRoot)),
  ]);
  for (const normalizedRepository of repositoryVariants) {
    assert.equal(
      normalizedValue.includes(normalizedRepository),
      false,
      `${label} referenced the repository checkout`,
    );
  }
}

export function assertRepositoryFreeChildEnvironment(
  environment,
  label,
  allowlist = installedChildEnvironmentAllowlist,
) {
  assert.equal(
    environment !== null && typeof environment === "object" && !Array.isArray(environment),
    true,
    `${label} must be an environment object`,
  );
  const allowedKeys = new Set(allowlist);
  assert.deepEqual(
    Object.keys(environment).sort(),
    [...allowlist].sort(),
    `${label} must contain the exact allowlisted key set`,
  );
  const pathEntries = [];
  for (const [key, value] of Object.entries(environment)) {
    assert.equal(allowedKeys.has(key), true, `${label} contains non-allowlisted key ${key}`);
    assert.equal(typeof value, "string", `${label} ${key} must be a string`);
    assertNoRepositoryPath(value, `${label} ${key}`);
    if (key.toUpperCase() === "PATH") pathEntries.push([key, value]);
  }
  assert.equal(pathEntries.length, 1, `${label} must declare exactly one PATH`);
  const declaredPath = pathEntries[0][1];
  assert.deepEqual(
    declaredPath.split(path.delimiter),
    [qualifiedNodeDirectory],
    `${label} PATH must contain exactly the qualified Node directory`,
  );
  const resolvedPath = fs.realpathSync.native(declaredPath);
  assert.equal(
    resolvedPath,
    qualifiedNodeDirectory,
    `${label} PATH must resolve to the qualified Node directory`,
  );
  assert.equal(fs.statSync(resolvedPath).isDirectory(), true, `${label} PATH is not a directory`);
  assert.equal(
    isWithin(fs.realpathSync.native(repositoryRoot), resolvedPath, { allowRoot: true }),
    false,
    `${label} PATH resolves inside the repository checkout`,
  );
  assertNoRepositoryPath(resolvedPath, `${label} resolved PATH`);
}

export function buildInstalledChildEnvironment({
  appData,
  codexHome,
  home,
  localAppData,
  pluginData,
  pluginRoot,
  temp,
}) {
  const environment = {
    APPDATA: appData,
    CLAUDE_PLUGIN_ROOT: pluginRoot,
    CODEX_HOME: codexHome,
    HOME: home,
    LOCALAPPDATA: localAppData,
    PATH: qualifiedNodeDirectory,
    PLUGIN_DATA: pluginData,
    PLUGIN_ROOT: pluginRoot,
    TEMP: temp,
    TMP: temp,
    TMPDIR: temp,
    USERPROFILE: home,
  };
  if (process.platform === "win32") {
    const homeRoot = path.parse(home).root;
    environment.HOMEDRIVE = homeRoot.slice(0, -1);
    environment.HOMEPATH = `${path.sep}${path.relative(homeRoot, home)}`;
  }
  assertRepositoryFreeChildEnvironment(environment, "installed child environment");
  return Object.freeze(environment);
}

function removeOwnedTempRoot(tempRoot) {
  const expectedParent = fs.realpathSync.native(os.tmpdir());
  const observedParent = fs.realpathSync.native(path.dirname(tempRoot));
  assert.equal(observedParent, expectedParent, `cleanup target escaped OS temp: ${tempRoot}`);
  assert.match(
    path.basename(tempRoot),
    /^efoundry installed dist [A-Za-z0-9_-]+$/u,
    `cleanup target lacks the owned installed-dist prefix: ${tempRoot}`,
  );
  const stat = fs.lstatSync(tempRoot);
  assert.equal(stat.isDirectory(), true, `cleanup target is not a directory: ${tempRoot}`);
  assert.equal(stat.isSymbolicLink(), false, `cleanup target is a link: ${tempRoot}`);
  fs.rmSync(tempRoot, { recursive: true, force: true });
}

function assertClosedOrdinaryTree(root, label) {
  const rootStat = fs.lstatSync(root);
  assert.equal(rootStat.isSymbolicLink(), false, `${label} root is a link`);
  assert.equal(rootStat.isDirectory(), true, `${label} root is not a directory`);
  const pending = [root];
  while (pending.length > 0) {
    const directory = pending.pop();
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const candidate = path.join(directory, entry.name);
      const stat = fs.lstatSync(candidate);
      assert.equal(stat.isSymbolicLink(), false, `${label} contains a link: ${candidate}`);
      if (stat.isDirectory()) {
        pending.push(candidate);
        continue;
      }
      assert.equal(stat.isFile(), true, `${label} contains a special entry: ${candidate}`);
    }
  }
}

function permissionGuardRecords(tracePath) {
  if (!fs.existsSync(tracePath)) return [];
  return fs.readFileSync(tracePath, "utf8")
    .split(/\r?\n/u)
    .filter(Boolean)
    .map((line, index) => parseJson(line, `permission guard record ${index + 1}`));
}

function createPermissionContext({ guardRoot, installedRoot, repositoryCanary }) {
  assert.equal(
    process.versions.node,
    qualifiedPermissionRuntime,
    `installed-dist permission boundary requires Node ${qualifiedPermissionRuntime}`,
  );
  const canonicalInstalledRoot = fs.realpathSync.native(installedRoot);
  const canonicalRepositoryCanary = fs.realpathSync.native(repositoryCanary);
  const canonicalRepositoryRoot = fs.realpathSync.native(repositoryRoot);
  assert.equal(
    isWithin(canonicalRepositoryRoot, canonicalInstalledRoot, { allowRoot: true }),
    false,
    "installed root is inside the repository checkout",
  );
  assert.equal(
    isWithin(canonicalInstalledRoot, canonicalRepositoryCanary, { allowRoot: true }),
    false,
    "repository canary is inside the installed root",
  );

  fs.mkdirSync(guardRoot, { recursive: false });
  const canonicalGuardRoot = fs.realpathSync.native(guardRoot);
  assert.equal(
    isWithin(canonicalRepositoryRoot, canonicalGuardRoot, { allowRoot: true }),
    false,
    "permission guard is inside the repository checkout",
  );
  assert.equal(
    isWithin(canonicalInstalledRoot, canonicalGuardRoot, { allowRoot: true }) ||
      isWithin(canonicalGuardRoot, canonicalInstalledRoot, { allowRoot: true }),
    false,
    "permission guard and installed payload roots overlap",
  );
  const guardPath = path.join(guardRoot, "permission-guard.mjs");
  const tracePath = path.join(guardRoot, "permission-guard.jsonl");
  const source = `
import { appendFileSync, readFileSync, realpathSync } from "node:fs";

const qualifiedNodeExecutable = ${JSON.stringify(qualifiedNodeExecutable)};
const repositoryCanary = ${JSON.stringify(canonicalRepositoryCanary)};
const tracePath = ${JSON.stringify(tracePath)};
if (process.execPath !== qualifiedNodeExecutable) {
  throw new Error("process.execPath is not the exact qualified host Node executable");
}
if (process.permission?.has("fs.read", repositoryCanary) !== false) {
  throw new Error("repository read permission was not denied");
}
if (process.permission?.has("child") !== false) {
  throw new Error("child-process permission was not denied");
}
let denied = false;
try {
  readFileSync(repositoryCanary);
} catch (error) {
  denied = error?.code === "ERR_ACCESS_DENIED" && error?.permission === "FileSystemRead";
}
if (!denied) throw new Error("repository read canary was not denied");
appendFileSync(tracePath, JSON.stringify({
  child_process: "DENIED",
  entrypoint: realpathSync(process.argv[1]),
  process_exec_path: process.execPath,
  repository_read: "DENIED",
}) + "\\n", "utf8");
`;
  fs.writeFileSync(guardPath, source, { encoding: "utf8", flag: "wx" });
  assertClosedOrdinaryTree(canonicalInstalledRoot, "installed payload");
  assertClosedOrdinaryTree(guardRoot, "permission guard");
  return Object.freeze({
    guardPath: fs.realpathSync.native(guardPath),
    guardRoot: canonicalGuardRoot,
    installedRoot: canonicalInstalledRoot,
    tracePath,
  });
}

function permissionArguments(context) {
  assertClosedOrdinaryTree(context.installedRoot, "installed payload before launch");
  assertClosedOrdinaryTree(context.guardRoot, "permission guard before launch");
  return Object.freeze([
    "--permission",
    `--allow-fs-read=${context.installedRoot}`,
    `--allow-fs-read=${context.guardRoot}`,
    `--allow-fs-write=${context.guardRoot}`,
    `--import=${pathToFileURL(context.guardPath).href}`,
  ]);
}

function assertPermissionGuardInvocation(context, beforeCount, expectedEntrypoint, label) {
  const records = permissionGuardRecords(context.tracePath);
  assert.equal(
    records.length,
    beforeCount + 1,
    `${label} did not execute exactly one permission guard`,
  );
  const record = records.at(-1);
  assert.deepEqual(
    { child_process: record.child_process, repository_read: record.repository_read },
    { child_process: "DENIED", repository_read: "DENIED" },
    `${label} permission guard did not deny repository/child access`,
  );
  assert.equal(
    record.process_exec_path,
    qualifiedNodeExecutable,
    `${label} did not use the exact qualified host Node executable`,
  );
  assert.equal(
    record.entrypoint,
    fs.realpathSync.native(expectedEntrypoint),
    `${label} executed a different entrypoint`,
  );
  assertNoRepositoryPath(record.entrypoint, `${label} permission-guard entrypoint`);
  return record;
}

function locateExecutable(name, explicitEnvironmentKey) {
  const explicit = process.env[explicitEnvironmentKey];
  if (explicit !== undefined) {
    assert.equal(path.isAbsolute(explicit), true, `${explicitEnvironmentKey} must be absolute`);
    assert.equal(fs.existsSync(explicit), true, `${explicitEnvironmentKey} does not exist`);
    return fs.realpathSync.native(explicit);
  }

  const locator = process.platform === "win32" ? "where.exe" : "which";
  const located = spawnSync(locator, [name], {
    encoding: "utf8",
    maxBuffer: 1024 * 1024,
    shell: false,
    timeout: 10_000,
    windowsHide: true,
  });
  assert.equal(located.error, undefined, `unable to start ${locator}: ${located.error}`);
  assert.equal(located.status, 0, `unable to locate ${name}: ${located.stderr}`);
  const candidates = located.stdout
    .split(/\r?\n/u)
    .map((value) => value.trim())
    .filter(Boolean);
  const preferred =
    candidates.find((value) => process.platform !== "win32" || value.endsWith(".exe")) ??
    candidates[0];
  assert.ok(preferred, `${locator} returned no ${name} executable`);
  return fs.realpathSync.native(preferred);
}

function spawnBounded(executable, args, {
  cwd,
  env,
  expectStatus = 0,
  input,
  label,
  maxBuffer = processMaxBuffer,
  repositoryFreeEnvironmentAllowlist,
  timeout = processTimeoutMs,
} = {}) {
  if (repositoryFreeEnvironmentAllowlist !== undefined) {
    assertRepositoryFreeChildEnvironment(
      env,
      `${label} child environment`,
      repositoryFreeEnvironmentAllowlist,
    );
  }
  const result = spawnSync(executable, args, {
    cwd,
    encoding: "utf8",
    env,
    input,
    maxBuffer,
    shell: false,
    timeout,
    windowsHide: true,
  });
  assert.equal(result.error, undefined, `${label} failed to run: ${result.error}`);
  assert.equal(
    result.status,
    expectStatus,
    `${label} exited ${result.status}\nstdout=${result.stdout ?? ""}\nstderr=${result.stderr ?? ""}`,
  );
  return result;
}

function spawnInstalledPayload(executable, args, options) {
  const { permissionContext, ...spawnOptions } = options;
  assert.ok(permissionContext, `${options.label} requires a permission context`);
  assertRepositoryFreeChildEnvironment(
    spawnOptions.env,
    `${spawnOptions.label} child environment`,
    installedChildEnvironmentAllowlist,
  );
  assert.equal(
    resolveNodeExecutable(executable, `${spawnOptions.label} executable`),
    executable,
    `${spawnOptions.label} executable token was translated`,
  );
  assert.equal(args.length > 0, true, `${spawnOptions.label} has no installed entrypoint`);
  const expectedEntrypoint = args[0];
  const beforeCount = permissionGuardRecords(permissionContext.tracePath).length;
  const result = spawnBounded(
    executable,
    [...permissionArguments(permissionContext), ...args],
    spawnOptions,
  );
  const permissionRecord = assertPermissionGuardInvocation(
    permissionContext,
    beforeCount,
    expectedEntrypoint,
    spawnOptions.label,
  );
  return Object.assign(result, { permissionRecord });
}

function gitText(gitExecutable, args, label) {
  return spawnBounded(gitExecutable, ["-C", repositoryRoot, ...args], {
    cwd: repositoryRoot,
    env: process.env,
    label,
    maxBuffer: 16 * 1024 * 1024,
    timeout: 30_000,
  }).stdout;
}

function gitBytes(gitExecutable, args, label) {
  const result = spawnSync(gitExecutable, ["-C", repositoryRoot, ...args], {
    cwd: repositoryRoot,
    encoding: null,
    env: process.env,
    maxBuffer: processMaxBuffer,
    shell: false,
    timeout: 30_000,
    windowsHide: true,
  });
  assert.equal(result.error, undefined, `${label} failed to run: ${result.error}`);
  assert.equal(
    result.status,
    0,
    `${label} exited ${result.status}: ${Buffer.from(result.stderr ?? []).toString("utf8")}`,
  );
  return Buffer.from(result.stdout);
}

function readHeadEntries(gitExecutable, headCommit) {
  assert.match(headCommit, /^[0-9a-f]{40,64}$/u, "pinned HEAD must be a commit hash");
  const output = gitBytes(
    gitExecutable,
    ["ls-tree", "-r", "-z", headCommit, "--", repositoryPluginPrefix],
    "git ls-tree pinned HEAD plugin payload",
  );
  const entries = new Map();
  for (const record of output.toString("utf8").split("\0")) {
    if (record === "") continue;
    const tab = record.indexOf("\t");
    assert.notEqual(tab, -1, `malformed git ls-tree record: ${record}`);
    const [mode, type, objectId] = record.slice(0, tab).split(" ");
    const repositoryPath = record.slice(tab + 1);
    assert.equal(type, "blob", `non-blob plugin payload entry at HEAD: ${repositoryPath}`);
    assert.ok(
      mode === "100644" || mode === "100755",
      `unsupported plugin payload mode ${mode}: ${repositoryPath}`,
    );
    assert.equal(
      repositoryPath.startsWith(`${repositoryPluginPrefix}/`),
      true,
      `HEAD plugin path escaped its prefix: ${repositoryPath}`,
    );
    const relativePath = repositoryPath.slice(repositoryPluginPrefix.length + 1);
    const segments = relativePath.split("/");
    assert.equal(
      relativePath.length > 0 && !segments.includes("") && !segments.includes(".."),
      true,
      `unsafe HEAD plugin path: ${repositoryPath}`,
    );
    assert.equal(entries.has(relativePath), false, `duplicate HEAD plugin path: ${relativePath}`);
    entries.set(relativePath, { mode, objectId });
  }
  assert.equal(entries.size > 0, true, `no payload is tracked at HEAD:${repositoryPluginPrefix}`);
  return entries;
}

function materializeHeadPlugin(gitExecutable, headCommit, destination) {
  const entries = readHeadEntries(gitExecutable, headCommit);
  for (const required of requiredHeadPaths) {
    assert.equal(
      entries.has(required),
      true,
      `required installed payload path is absent from HEAD: ${repositoryPluginPrefix}/${required}`,
    );
  }

  let totalBytes = 0;
  const inventory = [];
  for (const [relativePath, entry] of [...entries].sort(([left], [right]) =>
    left.localeCompare(right, "en"))) {
    const bytes = gitBytes(
      gitExecutable,
      ["cat-file", "blob", entry.objectId],
      `git cat-file ${relativePath}`,
    );
    totalBytes += bytes.length;
    assert.equal(totalBytes <= 512 * 1024 * 1024, true, "HEAD plugin payload exceeds 512 MiB");
    const destinationPath = path.join(destination, ...relativePath.split("/"));
    assert.equal(
      isWithin(path.resolve(destination), path.resolve(destinationPath)),
      true,
      `materialized path escaped marketplace plugin root: ${relativePath}`,
    );
    fs.mkdirSync(path.dirname(destinationPath), { recursive: true });
    fs.writeFileSync(destinationPath, bytes);
    if (entry.mode === "100755" && process.platform !== "win32") {
      fs.chmodSync(destinationPath, 0o755);
    }
    inventory.push({ path: relativePath, byte_size: bytes.length, sha256: sha256(bytes) });
  }
  return inventory;
}

function inventory(root) {
  const entries = [];
  const visit = (directory) => {
    for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
      const absolutePath = path.join(directory, item.name);
      if (item.isDirectory()) {
        visit(absolutePath);
        continue;
      }
      assert.equal(item.isFile(), true, `unsupported plugin entry: ${absolutePath}`);
      const bytes = fs.readFileSync(absolutePath);
      entries.push({
        path: path.relative(root, absolutePath).split(path.sep).join("/"),
        byte_size: bytes.length,
        sha256: sha256(bytes),
      });
    }
  };
  visit(root);
  return entries.sort((left, right) => left.path.localeCompare(right.path, "en"));
}

function compareInventories(source, installed) {
  const sourceByPath = new Map(source.map((entry) => [entry.path, entry]));
  const installedByPath = new Map(installed.map((entry) => [entry.path, entry]));
  return {
    missing_paths: [...sourceByPath.keys()].filter((key) => !installedByPath.has(key)),
    extra_paths: [...installedByPath.keys()].filter((key) => !sourceByPath.has(key)),
    hash_mismatches: [...sourceByPath.keys()]
      .filter((key) => installedByPath.has(key))
      .filter((key) => sourceByPath.get(key).sha256 !== installedByPath.get(key).sha256),
  };
}

function inventoryDigest(entries) {
  const canonical = [...entries]
    .map((entry) => ({
      byte_size: entry.byte_size,
      path: entry.path,
      sha256: entry.sha256,
    }))
    .sort((left, right) => left.path.localeCompare(right.path, "en"));
  return sha256(Buffer.from(JSON.stringify(canonical), "utf8"));
}

function relativeInstalledPath(installedRoot, candidate, label) {
  const canonicalRoot = fs.realpathSync.native(installedRoot);
  const canonicalCandidate = fs.realpathSync.native(candidate);
  assert.equal(
    isWithin(canonicalRoot, canonicalCandidate),
    true,
    `${label} escaped the installed payload`,
  );
  return path.relative(canonicalRoot, canonicalCandidate).split(path.sep).join("/");
}

function listRelativeTree(root) {
  if (!fs.existsSync(root)) return [];
  const entries = [];
  const visit = (directory) => {
    for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
      const absolutePath = path.join(directory, item.name);
      entries.push(path.relative(root, absolutePath).split(path.sep).join("/"));
      if (item.isDirectory()) visit(absolutePath);
    }
  };
  visit(root);
  return entries.sort((left, right) => left.localeCompare(right, "en"));
}

function findInstalledRoot(codexHome, installResult) {
  const expectedParent = path.join(
    codexHome,
    "plugins",
    "cache",
    marketplaceName,
    pluginName,
  );
  assert.equal(
    typeof installResult.installedPath,
    "string",
    `install result has no installedPath: ${JSON.stringify(installResult)}`,
  );
  assert.equal(path.isAbsolute(installResult.installedPath), true);
  const installedPath = path.resolve(installResult.installedPath);
  assert.equal(
    path.dirname(installedPath),
    path.resolve(expectedParent),
    `installed path escaped isolated plugin cache: ${installedPath}`,
  );
  assert.equal(
    fs.existsSync(installedPath),
    true,
    `installed root missing: ${installedPath}; cache=${JSON.stringify(
      listRelativeTree(path.join(codexHome, "plugins", "cache")),
    )}`,
  );
  return fs.realpathSync.native(installedPath);
}

function buildRepositorySetupEnvironment(overrides) {
  const child = { ...process.env };
  const exactKeys = new Set([
    "CLAUDE_PLUGIN_ROOT",
    "INIT_CWD",
    "NODE_OPTIONS",
    "NODE_PATH",
    "OLDPWD",
    "PLUGIN_DATA",
    "PLUGIN_ROOT",
    "PWD",
    "PYTHONPATH",
  ]);
  const sourceKey = /(?:^|_)(?:REPO|REPOSITORY|SOURCE|WORKSPACE)(?:_ROOT|_DIR|_PATH)?$/iu;
  for (const key of Object.keys(child)) {
    if (exactKeys.has(key.toUpperCase()) || sourceKey.test(key)) delete child[key];
  }
  return { ...child, ...overrides };
}

function assertNoTraversal(rawPath, label) {
  const withoutVariables = rawPath.replace(/\$\{(?:CLAUDE_PLUGIN_ROOT|PLUGIN_ROOT|PLUGIN_DATA)\}/gu, "ROOT");
  assert.equal(
    withoutVariables.replaceAll("\\", "/").split("/").includes(".."),
    false,
    `${label} contains relative traversal: ${rawPath}`,
  );
}

function substituteRoots(value, pluginRoot, pluginData) {
  const substituted = value
    .replaceAll("${CLAUDE_PLUGIN_ROOT}", pluginRoot)
    .replaceAll("${PLUGIN_ROOT}", pluginRoot)
    .replaceAll("${PLUGIN_DATA}", pluginData);
  assert.doesNotMatch(substituted, /\$\{[^}]+\}/u, `unresolved command variable: ${value}`);
  return substituted;
}

function resolvePayloadPath(rawPath, {
  base,
  label,
  mustBeFile = true,
  pluginData,
  pluginRoot,
}) {
  assert.equal(typeof rawPath, "string", `${label} must be a string`);
  assertNoTraversal(rawPath, label);
  const substituted = substituteRoots(rawPath, pluginRoot, pluginData);
  const candidate = path.isAbsolute(substituted)
    ? path.resolve(substituted)
    : path.resolve(base, substituted);
  const resolvedRoot = fs.realpathSync.native(pluginRoot);
  assert.equal(
    isWithin(resolvedRoot, candidate, { allowRoot: !mustBeFile }),
    true,
    `${label} escaped the plugin root: ${candidate}`,
  );
  assert.equal(fs.existsSync(candidate), true, `${label} does not exist: ${candidate}`);
  const realCandidate = fs.realpathSync.native(candidate);
  assert.equal(
    isWithin(resolvedRoot, realCandidate, { allowRoot: !mustBeFile }),
    true,
    `${label} resolves outside the plugin root: ${realCandidate}`,
  );
  assert.equal(
    isWithin(fs.realpathSync.native(repositoryRoot), realCandidate, { allowRoot: true }),
    false,
    `${label} resolves into the repository checkout: ${realCandidate}`,
  );
  if (mustBeFile) {
    assert.equal(fs.statSync(realCandidate).isFile(), true, `${label} is not a file`);
  } else {
    assert.equal(fs.statSync(realCandidate).isDirectory(), true, `${label} is not a directory`);
  }
  return realCandidate;
}

function resolveNodeExecutable(configured, label) {
  assert.equal(typeof configured, "string", `${label} command must be a string`);
  const normalized = configured.toLowerCase();
  if (normalized === "node" || normalized === "node.exe") return configured;
  assert.equal(path.isAbsolute(configured), true, `${label} may only use the host Node executable`);
  assert.equal(fs.existsSync(configured), true, `${label} Node executable does not exist`);
  assert.equal(
    fs.realpathSync.native(configured),
    qualifiedNodeExecutable,
    `${label} may only use the running host Node executable`,
  );
  return configured;
}

function resolveMcpPlan(pluginRoot, pluginData) {
  const document = parseJson(
    fs.readFileSync(path.join(pluginRoot, ".mcp.json"), "utf8"),
    "installed .mcp.json",
  );
  const server = document.mcpServers?.[pluginName];
  assert.ok(server && typeof server === "object", `installed .mcp.json lacks ${pluginName}`);
  assert.equal(Array.isArray(server.args), true, "installed MCP args must be an array");
  assert.equal(server.args.every((entry) => typeof entry === "string"), true);
  const executable = resolveNodeExecutable(server.command, "installed MCP");
  const cwd = resolvePayloadPath(server.cwd ?? ".", {
    base: pluginRoot,
    label: "installed MCP cwd",
    mustBeFile: false,
    pluginData,
    pluginRoot,
  });
  assert.equal(server.args.length > 0, true, "installed MCP has no Node script argument");
  const script = resolvePayloadPath(server.args[0], {
    base: cwd,
    label: "installed MCP script",
    pluginData,
    pluginRoot,
  });
  const args = [
    script,
    ...server.args.slice(1).map((value) => substituteRoots(value, pluginRoot, pluginData)),
  ];
  for (const value of args) assertNoRepositoryPath(value, "installed MCP argument");
  return { args, cwd, executable, script };
}

function tokenizeCommand(command) {
  assert.equal(typeof command, "string", "hook command must be a string");
  assert.doesNotMatch(command, /[;&|<>`\r\n]/u, `hook command contains shell syntax: ${command}`);
  const tokens = [];
  let token = "";
  let quote = null;
  for (const character of command) {
    if (quote !== null) {
      if (character === quote) quote = null;
      else token += character;
      continue;
    }
    if (character === '"' || character === "'") {
      quote = character;
    } else if (/\s/u.test(character)) {
      if (token !== "") {
        tokens.push(token);
        token = "";
      }
    } else {
      token += character;
    }
  }
  assert.equal(quote, null, `hook command has an unterminated quote: ${command}`);
  if (token !== "") tokens.push(token);
  assert.equal(tokens.length > 0, true, "hook command is empty");
  return tokens;
}

function resolveHookPlans(pluginRoot, pluginData) {
  const hookDirectory = path.join(pluginRoot, "hooks");
  assert.equal(fs.existsSync(hookDirectory), true, "installed hook directory is missing");
  const manifestNames = fs.readdirSync(hookDirectory)
    .filter((name) => name.endsWith(".json"))
    .sort((left, right) => left.localeCompare(right, "en"));
  assert.equal(manifestNames.length > 0, true, "installed payload has no hook manifest");
  const plans = [];
  for (const manifestName of manifestNames) {
    const document = parseJson(
      fs.readFileSync(path.join(hookDirectory, manifestName), "utf8"),
      `installed hook manifest ${manifestName}`,
    );
    for (const entry of objects(document)) {
      if (entry.type !== "command" || typeof entry.command !== "string") continue;
      if (!/dist[\\/]/u.test(entry.command)) continue;
      const tokens = tokenizeCommand(entry.command);
      const executable = resolveNodeExecutable(tokens[0], `hook ${manifestName}`);
      assert.equal(tokens.length > 1, true, `hook ${manifestName} has no Node script`);
      const rawScript = tokens[1];
      const script = resolvePayloadPath(rawScript, {
        base: pluginRoot,
        label: `hook ${manifestName} script`,
        pluginData,
        pluginRoot,
      });
      const args = [
        script,
        ...tokens.slice(2).map((value) => substituteRoots(value, pluginRoot, pluginData)),
      ];
      const declaredTimeout = entry.timeout === undefined ? 15 : Number(entry.timeout);
      assert.equal(
        Number.isFinite(declaredTimeout) && declaredTimeout > 0 && declaredTimeout <= 30,
        true,
        `hook ${manifestName} timeout must be within 1..30 seconds`,
      );
      for (const value of args) assertNoRepositoryPath(value, `hook ${manifestName} argument`);
      plans.push({
        args,
        executable,
        manifestName,
        script,
        timeout: declaredTimeout * 1000,
      });
    }
  }
  assert.equal(plans.length > 0, true, "no installed hook command loads dist/");
  return plans;
}

const mcpStdioDriverSource = String.raw`
const { spawn } = require("node:child_process");
const { realpathSync } = require("node:fs");
const path = require("node:path");
const { createInterface } = require("node:readline");

const argsKey = "EFOUNDRY_INSTALLED_DIST_MCP_ARGS";
const environmentKey = "EFOUNDRY_INSTALLED_DIST_MCP_ENVIRONMENT";
const executableKey = "EFOUNDRY_INSTALLED_DIST_MCP_EXECUTABLE";
const args = JSON.parse(process.env[argsKey]);
const childEnvironment = JSON.parse(process.env[environmentKey]);
const executable = process.env[executableKey];
delete process.env[argsKey];
delete process.env[environmentKey];
delete process.env[executableKey];

if (typeof executable !== "string" || executable.length === 0) {
  throw new Error("MCP driver received no declared executable token");
}
const actualNodeExecutable = realpathSync.native(process.execPath);
const normalizedExecutable = executable.toLowerCase();
if (normalizedExecutable !== "node" && normalizedExecutable !== "node.exe") {
  if (!path.isAbsolute(executable) || realpathSync.native(executable) !== actualNodeExecutable) {
    throw new Error("MCP driver executable is not the declared qualified Node executable");
  }
}

const allowedChildEnvironmentKeys = new Set([
  "APPDATA",
  "CLAUDE_PLUGIN_ROOT",
  "CODEX_HOME",
  "HOME",
  "LOCALAPPDATA",
  "PATH",
  "PLUGIN_DATA",
  "PLUGIN_ROOT",
  "TEMP",
  "TMP",
  "TMPDIR",
  "USERPROFILE",
]);
if (process.platform === "win32") {
  allowedChildEnvironmentKeys.add("HOMEDRIVE");
  allowedChildEnvironmentKeys.add("HOMEPATH");
}
const observedChildEnvironmentKeys = Object.keys(childEnvironment).sort();
const expectedChildEnvironmentKeys = [...allowedChildEnvironmentKeys].sort();
if (JSON.stringify(observedChildEnvironmentKeys) !== JSON.stringify(expectedChildEnvironmentKeys)) {
  throw new Error("MCP child environment does not match the exact allowlist");
}
for (const [key, value] of Object.entries(childEnvironment)) {
  if (!allowedChildEnvironmentKeys.has(key)) {
    throw new Error("MCP child environment contains non-allowlisted key " + key);
  }
  if (typeof value !== "string") {
    throw new Error("MCP child environment value must be a string: " + key);
  }
}
const qualifiedNodeDirectory = realpathSync.native(path.dirname(actualNodeExecutable));
const childPathEntries = childEnvironment.PATH.split(path.delimiter);
if (
  childPathEntries.length !== 1 ||
  childPathEntries[0] !== qualifiedNodeDirectory
) {
  throw new Error("MCP child environment PATH must contain exactly the qualified Node directory");
}

const child = spawn(executable, args, {
  cwd: process.cwd(),
  env: childEnvironment,
  shell: false,
  stdio: ["pipe", "pipe", "pipe"],
  windowsHide: true,
});
child.stdout.setEncoding("utf8");
child.stderr.setEncoding("utf8");

let stderr = "";
let fatal = null;
let stderrBytes = 0;
let stdoutBytes = 0;
const maxOutputBytes = 16 * 1024 * 1024;
const pending = new Map();
const lines = createInterface({ input: child.stdout, crlfDelay: Infinity });
const closed = new Promise((resolve) => {
  child.once("close", (code, signal) => resolve({ code, signal }));
});

function fail(error) {
  if (fatal === null) fatal = error;
  for (const waiter of pending.values()) waiter.reject(fatal);
  pending.clear();
}

child.stdout.on("data", (chunk) => {
  stdoutBytes += Buffer.byteLength(chunk, "utf8");
  if (stdoutBytes > maxOutputBytes) {
    fail(new Error("MCP stdout exceeded 16 MiB"));
    child.kill("SIGKILL");
  }
});
child.stderr.on("data", (chunk) => {
  stderrBytes += Buffer.byteLength(chunk, "utf8");
  if (stderrBytes <= maxOutputBytes) stderr += chunk;
  if (stderrBytes > maxOutputBytes) {
    fail(new Error("MCP stderr exceeded 16 MiB"));
    child.kill("SIGKILL");
  }
});

child.once("error", fail);
child.once("close", (code, signal) => {
  if (pending.size > 0) {
    fail(new Error("MCP child closed before its response: code=" + code + " signal=" + signal));
  }
});

lines.on("line", (line) => {
  if (fatal !== null) return;
  if (line.trim() === "") return;
  let payload;
  try {
    payload = JSON.parse(line);
  } catch (cause) {
    fail(new Error("MCP emitted non-JSON output: " + cause.message));
    return;
  }
  if (!Object.hasOwn(payload, "id")) {
    fail(new Error("MCP emitted an unexpected response to a notification"));
    return;
  }
  const key = JSON.stringify(payload.id);
  const waiter = pending.get(key);
  if (waiter === undefined) {
    fail(new Error("MCP emitted an unmatched response id: " + key));
    return;
  }
  pending.delete(key);
  waiter.resolve(payload);
});

function writeMessage(payload) {
  if (fatal !== null) return Promise.reject(fatal);
  return new Promise((resolve, reject) => {
    child.stdin.write(JSON.stringify(payload) + "\n", (error) => {
      if (error) reject(error);
      else resolve();
    });
  });
}

function request(payload, timeoutMilliseconds) {
  if (fatal !== null) return Promise.reject(fatal);
  const key = JSON.stringify(payload.id);
  if (pending.has(key)) return Promise.reject(new Error("duplicate MCP request id: " + key));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(key);
      reject(new Error("timed out awaiting MCP response id: " + key));
    }, timeoutMilliseconds);
    pending.set(key, {
      reject(error) {
        clearTimeout(timer);
        reject(error);
      },
      resolve(response) {
        clearTimeout(timer);
        resolve(response);
      },
    });
    child.stdin.write(JSON.stringify(payload) + "\n", (error) => {
      if (error) {
        const waiter = pending.get(key);
        pending.delete(key);
        waiter?.reject(error);
      }
    });
  });
}

const wait = (milliseconds, value) => new Promise((resolve) => {
  setTimeout(() => resolve(value), milliseconds);
});

async function main() {
  let responses = null;
  let failure = null;
  let exit = null;
  try {
    const initialize = await request({
      jsonrpc: "2.0",
      id: "initialize",
      method: "initialize",
      params: {
        protocolVersion: "2025-06-18",
        capabilities: {},
        clientInfo: { name: "installed-dist-automation", version: "1" },
      },
    }, 10_000);
    await writeMessage({
      jsonrpc: "2.0",
      method: "notifications/initialized",
      params: {},
    });
    const toolsList = await request({
      jsonrpc: "2.0",
      id: "tools-list",
      method: "tools/list",
      params: {},
    }, 10_000);
    const foundryStatus = await request({
      jsonrpc: "2.0",
      id: "foundry-status",
      method: "tools/call",
      params: {
        name: "foundry.status",
        arguments: { workspace_id: "installed-dist-automation" },
      },
    }, 30_000);
    responses = [initialize, toolsList, foundryStatus];
  } catch (cause) {
    failure = cause;
  } finally {
    if (!child.stdin.destroyed) child.stdin.end();
    exit = await Promise.race([closed, wait(5_000, null)]);
    if (exit === null) {
      child.kill("SIGKILL");
      exit = await Promise.race([closed, wait(2_000, null)]);
    }
    if (exit === null) {
      child.stdin.destroy();
      child.stdout.destroy();
      child.stderr.destroy();
      child.unref();
    }
    lines.close();
  }

  if (failure === null && fatal !== null) failure = fatal;
  if (failure === null && exit === null) failure = new Error("MCP child did not close after kill");
  if (failure === null && exit.code !== 0) {
    failure = new Error("MCP child exited " + exit.code + " signal=" + exit.signal);
  }
  if (failure !== null) throw failure;
  process.stdout.write(JSON.stringify({ exit, responses, stderr }) + "\n");
}

main().catch((cause) => {
  process.stderr.write((cause.stack || cause.message) + "\n" + stderr);
  process.exitCode = 1;
});
`;

function runMcpStdioLifecycle(plan, environment, permissionContext) {
  assertRepositoryFreeChildEnvironment(environment, "installed MCP child environment");
  const beforeCount = permissionGuardRecords(permissionContext.tracePath).length;
  const driverEnvironment = {
    [mcpDriverArgsEnvironmentKey]: JSON.stringify([
      ...permissionArguments(permissionContext),
      ...plan.args,
    ]),
    [mcpDriverChildEnvironmentKey]: JSON.stringify(environment),
    [mcpDriverExecutableEnvironmentKey]: plan.executable,
    PATH: qualifiedNodeDirectory,
  };
  const result = spawnBounded(
    plan.executable,
    ["--input-type=commonjs", "--eval", mcpStdioDriverSource],
    {
      cwd: plan.cwd,
      env: driverEnvironment,
      label: "installed MCP strict stdio lifecycle",
      repositoryFreeEnvironmentAllowlist: mcpDriverEnvironmentAllowlist,
      timeout: processTimeoutMs,
    },
  );
  const payload = parseJson(result.stdout, "installed MCP strict stdio lifecycle");
  assert.equal(Array.isArray(payload.responses), true, "MCP driver returned no responses");
  assert.equal(typeof payload.stderr, "string", "MCP driver returned no stderr capture");
  assert.deepEqual(payload.exit, { code: 0, signal: null }, "MCP child did not exit cleanly");
  return {
    ...payload,
    permissionRecord: assertPermissionGuardInvocation(
      permissionContext,
      beforeCount,
      plan.args[0],
      "installed MCP child",
    ),
  };
}

function configText(configPath) {
  return fs.existsSync(configPath) ? fs.readFileSync(configPath, "utf8") : "";
}

export function runInstalledDistExecutionAutomation() {
  const codexExecutable = locateExecutable("codex", "EFOUNDRY_CODEX_EXECUTABLE");
  const gitExecutable = locateExecutable("git", "EFOUNDRY_GIT_EXECUTABLE");
  const headCommit = gitText(gitExecutable, ["rev-parse", "HEAD"], "git rev-parse HEAD").trim();
  assert.match(headCommit, /^[0-9a-f]{40,64}$/u, "HEAD did not resolve to a commit hash");

  const realCodexHome = path.resolve(process.env.CODEX_HOME ?? path.join(os.homedir(), ".codex"));
  const realConfigPath = path.join(realCodexHome, "config.toml");
  const realConfigBefore = fileState(realConfigPath);
  const realSelectorCache = path.join(
    realCodexHome,
    "plugins",
    "cache",
    marketplaceName,
    pluginName,
  );
  assert.equal(
    fs.existsSync(realSelectorCache),
    false,
    `refusing to run over a real-user selector cache: ${realSelectorCache}`,
  );

  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "efoundry installed dist "));
  const codexHome = path.join(tempRoot, "isolated CODEX_HOME");
  const isolatedUserHome = path.join(tempRoot, "isolated user profile");
  const isolatedAppData = path.join(isolatedUserHome, "AppData", "Roaming");
  const isolatedLocalAppData = path.join(isolatedUserHome, "AppData", "Local");
  const isolatedTemp = path.join(tempRoot, "isolated temp");
  const marketplaceRoot = path.join(tempRoot, "local marketplace");
  const marketplacePluginRoot = path.join(marketplaceRoot, "plugins", pluginName);
  const detachedSourceRoot = path.join(tempRoot, "detached marketplace source", pluginName);
  const emptyCwd = path.join(tempRoot, "empty cwd");
  const pluginData = path.join(tempRoot, "persistent plugin data", pluginName);
  const permissionGuardRoot = path.join(tempRoot, "permission guard");
  const sentinelPath = path.join(pluginData, "installed-dist-sentinel.txt");
  const sentinelBytes = Buffer.from("installed-dist-plugin-data-must-survive-removal\n", "utf8");

  try {
    fs.mkdirSync(codexHome, { recursive: true });
    fs.mkdirSync(isolatedAppData, { recursive: true });
    fs.mkdirSync(isolatedLocalAppData, { recursive: true });
    fs.mkdirSync(isolatedTemp, { recursive: true });
    fs.mkdirSync(marketplacePluginRoot, { recursive: true });
    fs.mkdirSync(emptyCwd, { recursive: true });
    fs.mkdirSync(pluginData, { recursive: true });
    fs.writeFileSync(sentinelPath, sentinelBytes);

    const sourceInventory = materializeHeadPlugin(
      gitExecutable,
      headCommit,
      marketplacePluginRoot,
    );
    const sourceManifest = parseJson(
      fs.readFileSync(path.join(marketplacePluginRoot, ".codex-plugin", "plugin.json"), "utf8"),
      "HEAD plugin manifest",
    );
    assert.equal(sourceManifest.name, pluginName, "HEAD plugin manifest has the wrong name");

    // Resolve every declared payload entry before touching Codex configuration. This turns a
    // missing tracked dist file into an immediate HEAD-content failure, not a partial install.
    const sourceMcpPlan = resolveMcpPlan(marketplacePluginRoot, pluginData);
    const sourceHookPlans = resolveHookPlans(marketplacePluginRoot, pluginData);
    resolvePayloadPath("dist/cli.mjs", {
      base: marketplacePluginRoot,
      label: "HEAD dispatcher target",
      pluginData,
      pluginRoot: marketplacePluginRoot,
    });
    assert.equal(sourceMcpPlan.script.length > 0, true);
    assert.equal(sourceHookPlans.length > 0, true);

    fs.mkdirSync(path.join(marketplaceRoot, ".agents", "plugins"), { recursive: true });
    fs.writeFileSync(
      path.join(marketplaceRoot, ".agents", "plugins", "marketplace.json"),
      `${JSON.stringify(
        {
          name: marketplaceName,
          interface: { displayName: "Installed Distribution Local Marketplace" },
          plugins: [
            {
              name: pluginName,
              source: { source: "local", path: `./plugins/${pluginName}` },
              policy: { installation: "AVAILABLE", authentication: "ON_INSTALL" },
              category: "Research",
            },
          ],
        },
        null,
        2,
      )}\n`,
      "utf8",
    );

    const baseEnvironment = buildRepositorySetupEnvironment({
      APPDATA: isolatedAppData,
      CODEX_HOME: codexHome,
      HOME: isolatedUserHome,
      LOCALAPPDATA: isolatedLocalAppData,
      USERPROFILE: isolatedUserHome,
    });
    if (process.platform === "win32") {
      const homeRoot = path.parse(isolatedUserHome).root;
      baseEnvironment.HOMEDRIVE = homeRoot.slice(0, -1);
      baseEnvironment.HOMEPATH = `${path.sep}${path.relative(homeRoot, isolatedUserHome)}`;
    }
    const runCodex = (args, label, env = baseEnvironment) => spawnBounded(codexExecutable, args, {
      cwd: emptyCwd,
      env,
      label,
    });

    const marketplaceAdd = parseJson(
      runCodex(["plugin", "marketplace", "add", marketplaceRoot, "--json"], "marketplace add").stdout,
      "marketplace add",
    );
    assert.match(JSON.stringify(marketplaceAdd), new RegExp(marketplaceName, "u"));

    const available = parseJson(
      runCodex(["plugin", "list", "--available", "--json"], "available plugin list").stdout,
      "available plugin list",
    );
    assert.match(JSON.stringify(available), new RegExp(pluginName, "u"));
    assert.equal(containsPersonalMarketplace(available), false);

    const installResult = parseJson(
      runCodex(["plugin", "add", selector, "--json"], "plugin add").stdout,
      "plugin add",
    );
    const installedRoot = findInstalledRoot(codexHome, installResult);
    const installedInventory = inventory(installedRoot);
    const parity = compareInventories(sourceInventory, installedInventory);
    assert.deepEqual(parity, { missing_paths: [], extra_paths: [], hash_mismatches: [] });

    const enabledState = pluginEntry(
      parseJson(runCodex(["plugin", "list", "--json"], "installed plugin list").stdout, "installed plugin list"),
    );
    assert.equal(enabledState.enabled, true, "plugin add did not enable the installed plugin");

    fs.mkdirSync(path.dirname(detachedSourceRoot), { recursive: true });
    fs.renameSync(marketplacePluginRoot, detachedSourceRoot);
    assert.equal(fs.existsSync(marketplacePluginRoot), false);
    assert.deepEqual(inventory(installedRoot), installedInventory);

    const permissionContext = createPermissionContext({
      guardRoot: permissionGuardRoot,
      installedRoot,
      repositoryCanary: path.join(repositoryRoot, "MASTER_SPEC.md"),
    });

    const installedEnvironment = buildInstalledChildEnvironment({
      appData: isolatedAppData,
      codexHome,
      home: isolatedUserHome,
      localAppData: isolatedLocalAppData,
      pluginData,
      pluginRoot: installedRoot,
      temp: isolatedTemp,
    });
    const dispatcher = resolvePayloadPath("bin/efoundry.mjs", {
      base: installedRoot,
      label: "installed dispatcher",
      pluginData,
      pluginRoot: installedRoot,
    });
    const dispatcherTarget = resolvePayloadPath("dist/cli.mjs", {
      base: installedRoot,
      label: "installed dispatcher target",
      pluginData,
      pluginRoot: installedRoot,
    });
    const dispatcherTargetRelative = relativeInstalledPath(
      installedRoot,
      dispatcherTarget,
      "installed dispatcher target",
    );
    const cliResult = spawnInstalledPayload(process.execPath, [dispatcher, "status", "--json"], {
      cwd: emptyCwd,
      env: installedEnvironment,
      label: "installed dispatcher status --json",
      permissionContext,
    });
    assert.equal(cliResult.stderr.trim(), "", "installed status wrote to stderr");
    const cliPayload = parseJson(cliResult.stdout, "installed dispatcher status --json");
    assert.equal(cliPayload !== null && typeof cliPayload === "object", true);
    assertNoRepositoryPath(cliResult.stdout, "installed CLI stdout");
    assertNoRepositoryPath(cliResult.stderr, "installed CLI stderr");

    const mcpPlan = resolveMcpPlan(installedRoot, pluginData);
    const mcpScriptRelative = relativeInstalledPath(
      installedRoot,
      mcpPlan.script,
      "installed MCP script",
    );
    const mcpLifecycle = runMcpStdioLifecycle(
      mcpPlan,
      installedEnvironment,
      permissionContext,
    );
    assert.equal(mcpLifecycle.stderr.trim(), "", "installed MCP wrote to stderr");
    assertNoRepositoryPath(JSON.stringify(mcpLifecycle.responses), "installed MCP responses");
    assertNoRepositoryPath(mcpLifecycle.stderr, "installed MCP stderr");
    const mcpResponses = mcpLifecycle.responses;
    assert.equal(mcpResponses.length, 3, "installed MCP did not answer all three requests");
    const initializeResponse = mcpResponses.find((response) => response.id === "initialize");
    const toolsResponse = mcpResponses.find((response) => response.id === "tools-list");
    const statusResponse = mcpResponses.find((response) => response.id === "foundry-status");
    assert.equal(initializeResponse?.result?.serverInfo?.name, pluginName);
    assert.equal(Array.isArray(toolsResponse?.result?.tools), true);
    assert.equal(
      toolsResponse.result.tools.some((tool) => tool?.name === "foundry.status"),
      true,
      "installed MCP tools/list omitted foundry.status",
    );
    assert.equal(statusResponse?.error, undefined, "installed MCP foundry.status returned JSON-RPC error");
    assert.equal(statusResponse?.result?.isError, false, "installed MCP foundry.status returned a tool error");
    assert.equal(statusResponse?.result?.structuredContent?.tool, "foundry.status");
    assert.equal(
      statusResponse?.result?.structuredContent?.workspace_id,
      "installed-dist-automation",
    );

    const hookPlans = resolveHookPlans(installedRoot, pluginData);
    const hookInput = `${JSON.stringify({ hook_event_name: "SessionStart", source: "startup" })}\n`;
    const hookExecutions = [];
    const hookPermissionRecords = [];
    for (const [index, plan] of hookPlans.entries()) {
      const hookResult = spawnInstalledPayload(plan.executable, plan.args, {
        cwd: emptyCwd,
        env: installedEnvironment,
        input: hookInput,
        label: `installed hook ${plan.manifestName} #${index + 1}`,
        permissionContext,
        timeout: plan.timeout,
      });
      hookPermissionRecords.push(hookResult.permissionRecord);
      hookExecutions.push({
        command: [
          plan.executable,
          relativeInstalledPath(installedRoot, plan.script, "installed hook script"),
          ...plan.args.slice(1),
        ],
        entrypoint: relativeInstalledPath(
          installedRoot,
          plan.script,
          "installed hook entrypoint",
        ),
        exit: { code: hookResult.status, signal: hookResult.signal },
        manifest: plan.manifestName,
        process_exec_path: hookResult.permissionRecord.process_exec_path,
      });
      assert.equal(hookResult.stderr.trim(), "", `installed hook ${plan.manifestName} wrote stderr`);
      assertNoRepositoryPath(hookResult.stdout, `installed hook ${plan.manifestName} stdout`);
      assertNoRepositoryPath(hookResult.stderr, `installed hook ${plan.manifestName} stderr`);
      const hookPayload = parseJson(hookResult.stdout, `installed hook ${plan.manifestName}`);
      assert.equal(hookPayload?.hookSpecificOutput?.hookEventName, "SessionStart");
      assert.equal(
        typeof hookPayload?.hookSpecificOutput?.additionalContext === "string" &&
          hookPayload.hookSpecificOutput.additionalContext.length > 0,
        true,
        `installed hook ${plan.manifestName} returned no SessionStart context`,
      );
    }

    const guardedEntrypoints = [
      cliResult.permissionRecord,
      mcpLifecycle.permissionRecord,
      ...hookPermissionRecords,
    ].map((record, index) => relativeInstalledPath(
      installedRoot,
      record.entrypoint,
      `permission-guard entrypoint ${index + 1}`,
    ));

    const removeResult = parseJson(
      runCodex(
        ["plugin", "remove", selector, "--json"],
        "plugin remove",
        baseEnvironment,
      ).stdout,
      "plugin remove",
    );
    assert.match(JSON.stringify(removeResult), new RegExp(pluginName, "u"));
    assert.equal(fs.existsSync(installedRoot), false, "installed cache root survived plugin removal");
    assert.equal(
      listRelativeTree(path.join(codexHome, "plugins", "cache", marketplaceName, pluginName)).length,
      0,
      "installed selector cache contains residue",
    );
    const configPath = path.join(codexHome, "config.toml");
    assert.doesNotMatch(configText(configPath), new RegExp(selector, "u"));

    const marketplaceRemove = parseJson(
      runCodex(["plugin", "marketplace", "remove", marketplaceName, "--json"], "marketplace remove").stdout,
      "marketplace remove",
    );
    assert.match(JSON.stringify(marketplaceRemove), new RegExp(marketplaceName, "u"));
    const remainingMarketplaces = parseJson(
      runCodex(["plugin", "marketplace", "list", "--json"], "marketplace list after removal").stdout,
      "marketplace list after removal",
    );
    assert.doesNotMatch(JSON.stringify(remainingMarketplaces), new RegExp(marketplaceName, "u"));
    assert.equal(containsPersonalMarketplace(remainingMarketplaces), false);
    assert.doesNotMatch(configText(configPath), new RegExp(marketplaceName, "u"));

    assert.equal(fs.existsSync(sentinelPath), true, "plugin removal deleted PLUGIN_DATA");
    assert.deepEqual(fs.readFileSync(sentinelPath), sentinelBytes, "PLUGIN_DATA sentinel changed");
    assert.equal(fs.existsSync(realSelectorCache), false, "real-user plugin cache was modified");

    const installedDistInventory = installedInventory.filter((entry) =>
      entry.path.startsWith("dist/"),
    );
    const harnessSha256 = sha256(fs.readFileSync(fileURLToPath(import.meta.url)));
    return {
      schema_version: "installed-dist-execution-automation/v1",
      gate: "installed_dist_execution_automation",
      head_commit: headCommit,
      harness_sha256: harnessSha256,
      tracked_payload_files: sourceInventory.length,
      installed_payload_sha256: inventoryDigest(installedInventory),
      installed_dist_sha256: inventoryDigest(installedDistInventory),
      installed_byte_parity: "PASS",
      plugin_enabled: true,
      detached_cwd: true,
      repository_access_enforcement: {
        child_process: "DENIED",
        permission_model: `NODE_${qualifiedPermissionRuntime}`,
        repository_read: "DENIED",
        guarded_entrypoints: guardedEntrypoints,
      },
      invoked_entrypoints: [
        {
          command: [process.execPath, "bin/efoundry.mjs", "status", "--json"],
          entrypoint: "bin/efoundry.mjs",
          implementation: dispatcherTargetRelative,
          exit: { code: cliResult.status, signal: cliResult.signal },
          process_exec_path: cliResult.permissionRecord.process_exec_path,
        },
        {
          command: [
            mcpPlan.executable,
            mcpScriptRelative,
          ],
          entrypoint: mcpScriptRelative,
          exit: mcpLifecycle.exit,
          process_exec_path: mcpLifecycle.permissionRecord.process_exec_path,
        },
        ...hookExecutions,
      ],
      cli_status_json: "PASS",
      mcp: { initialize: "PASS", tools_list: "PASS", foundry_status: "PASS" },
      hooks: { dist_commands_executed: hookPlans.length, session_start: "PASS" },
      removal: {
        plugin_cache: "REMOVED",
        plugin_config: "REMOVED",
        marketplace_config: "REMOVED",
        plugin_data_sentinel: "PRESERVED",
      },
      final_status: "PASS",
    };
  } finally {
    const realConfigAfter = fileState(realConfigPath);
    const realSelectorCacheExistsAfter = fs.existsSync(realSelectorCache);
    removeOwnedTempRoot(tempRoot);
    assert.equal(realSelectorCacheExistsAfter, false, "real-user plugin cache was modified");
    assert.deepEqual(realConfigAfter, realConfigBefore, "real-user Codex config was modified");
  }
}

const directInvocation =
  process.argv[1] !== undefined && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;

if (directInvocation) {
  try {
    process.stdout.write(`${JSON.stringify(runInstalledDistExecutionAutomation())}\n`);
  } catch (cause) {
    process.stderr.write(`${cause.stack ?? cause.message}\n`);
    process.exitCode = 1;
  }
}
