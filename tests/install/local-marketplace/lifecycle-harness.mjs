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
const sourcePluginRoot = path.join(repositoryRoot, "plugins", "epistemic-foundry");
const pluginName = "epistemic-foundry";
const marketplaceName = "g04-local-marketplace";
const selector = `${pluginName}@${marketplaceName}`;

function sha256(bytes) {
  return `sha256:${crypto.createHash("sha256").update(bytes).digest("hex")}`;
}

function fileState(filePath) {
  if (!fs.existsSync(filePath)) return { exists: false, byte_size: null, sha256: null };
  const bytes = fs.readFileSync(filePath);
  return { exists: true, byte_size: bytes.length, sha256: sha256(bytes) };
}

function removeOwnedTempRoot(tempRoot) {
  const expectedParent = fs.realpathSync.native(os.tmpdir());
  const observedParent = fs.realpathSync.native(path.dirname(tempRoot));
  assert.equal(observedParent, expectedParent, `cleanup target escaped OS temp: ${tempRoot}`);
  assert.match(
    path.basename(tempRoot),
    /^efoundry G04 한글 [A-Za-z0-9_-]+$/u,
    `cleanup target does not have the owned G04 prefix: ${tempRoot}`,
  );
  const stat = fs.lstatSync(tempRoot);
  assert.equal(stat.isDirectory(), true, `cleanup target is not a directory: ${tempRoot}`);
  assert.equal(stat.isSymbolicLink(), false, `cleanup target is a link: ${tempRoot}`);
  fs.rmSync(tempRoot, { recursive: true, force: true });
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

function resolveCodexExecutable() {
  const explicit = process.env.EFOUNDRY_CODEX_EXECUTABLE;
  if (explicit !== undefined) {
    assert.equal(path.isAbsolute(explicit), true, "EFOUNDRY_CODEX_EXECUTABLE must be absolute");
    assert.equal(fs.existsSync(explicit), true, "EFOUNDRY_CODEX_EXECUTABLE does not exist");
    return fs.realpathSync.native(explicit);
  }

  const locator = process.platform === "win32" ? "where.exe" : "which";
  const located = spawnSync(locator, ["codex"], {
    encoding: "utf8",
    shell: false,
    windowsHide: true,
  });
  assert.equal(located.status, 0, `unable to locate codex: ${located.stderr}`);
  const candidates = located.stdout
    .split(/\r?\n/u)
    .map((value) => value.trim())
    .filter(Boolean);
  const preferred =
    candidates.find((value) => process.platform !== "win32" || value.endsWith(".exe")) ??
    candidates[0];
  assert.ok(preferred, "codex locator returned no executable");
  return fs.realpathSync.native(preferred);
}

function parseJson(stdout, label) {
  try {
    return JSON.parse(stdout);
  } catch (error) {
    throw new Error(`${label} did not return JSON: ${error.message}\n${stdout}`);
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
    const identityValues = [
      entry.name,
      entry.plugin_name,
      entry.id,
      entry.selector,
      entry.plugin,
    ];
    return identityValues.includes(pluginName) || identityValues.includes(selector);
  });
  const entry = candidates.find((candidate) => typeof candidate.enabled === "boolean");
  assert.ok(entry, `plugin state missing for ${selector}: ${JSON.stringify(payload)}`);
  return entry;
}

function setEnabled(configPath, enabled) {
  const header = `[plugins.${JSON.stringify(selector)}]`;
  let config = fs.readFileSync(configPath, "utf8");
  const start = config.indexOf(header);
  assert.notEqual(start, -1, `installed plugin config block missing: ${header}`);
  const nextHeader = config.indexOf("\n[", start + header.length);
  const end = nextHeader === -1 ? config.length : nextHeader + 1;
  const block = config.slice(start, end);
  assert.match(block, /(^|\n)enabled\s*=\s*(?:true|false)(?:\r?\n|$)/u);
  const replacement = block.replace(
    /(^|\n)(enabled\s*=\s*)(?:true|false)(?=\r?\n|$)/u,
    `$1$2${enabled}`,
  );
  config = `${config.slice(0, start)}${replacement}${config.slice(end)}`;
  fs.writeFileSync(configPath, config, "utf8");
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
  const cacheRoot = path.join(codexHome, "plugins", "cache");
  assert.equal(
    fs.existsSync(installedPath),
    true,
    `installed cache root missing: ${installedPath}\ninstall result: ${JSON.stringify(
      installResult,
    )}\ncache tree: ${JSON.stringify(listRelativeTree(cacheRoot))}`,
  );
  return fs.realpathSync.native(installedPath);
}

function compareInventories(source, installed) {
  const sourceByPath = new Map(source.map((entry) => [entry.path, entry]));
  const installedByPath = new Map(installed.map((entry) => [entry.path, entry]));
  const missingPaths = [...sourceByPath.keys()].filter((key) => !installedByPath.has(key));
  const extraPaths = [...installedByPath.keys()].filter((key) => !sourceByPath.has(key));
  const hashMismatches = [...sourceByPath.keys()]
    .filter((key) => installedByPath.has(key))
    .filter((key) => sourceByPath.get(key).sha256 !== installedByPath.get(key).sha256);
  return { missingPaths, extraPaths, hashMismatches };
}

function pathVariants(literal) {
  const variants = new Set([literal, literal.split(path.sep).join("/")]);
  if (process.platform === "win32" && /^[A-Za-z]:[\\/]/u.test(literal)) {
    const native = literal.replaceAll("/", "\\");
    variants.add(`\\\\?\\${native}`);
  }
  for (const value of [...variants]) {
    variants.add(JSON.stringify(value).slice(1, -1));
  }
  return [...variants].sort((left, right) => right.length - left.length);
}

function normalizeOutput(value, replacements) {
  let normalized = value;
  for (const [literal, replacement] of replacements) {
    for (const variant of pathVariants(literal)) {
      normalized = normalized.split(variant).join(replacement);
    }
  }
  return normalized;
}

function containsPersonalMarketplace(payload) {
  return objects(payload).some(
    (entry) =>
      entry.marketplaceName === "personal" ||
      entry.marketplace_name === "personal" ||
      (entry.name === "personal" && typeof entry.root === "string"),
  );
}

function assertPortableEvidence(value) {
  const visit = (candidate) => {
    if (typeof candidate === "string") {
      assert.equal(
        path.isAbsolute(candidate),
        false,
        `evidence contains a machine-local absolute path: ${candidate}`,
      );
      return;
    }
    if (Array.isArray(candidate)) {
      for (const item of candidate) visit(item);
      return;
    }
    if (candidate !== null && typeof candidate === "object") {
      for (const item of Object.values(candidate)) visit(item);
    }
  };
  visit(value);
}

function assertNoRepositoryPath(value, label) {
  const normalize = (candidate) =>
    String(candidate).replaceAll("\\", "/").replace(/\/{2,}/gu, "/").toLowerCase();
  const normalizedValue = normalize(value);
  for (const candidate of [repositoryRoot, fs.realpathSync.native(repositoryRoot)]) {
    assert.equal(
      normalizedValue.includes(normalize(candidate)),
      false,
      `${label} referenced the repository checkout`,
    );
  }
}

export function runLocalMarketplaceLifecycle() {
  assert.equal(fs.existsSync(sourcePluginRoot), true, "source plugin package is missing");
  const codexExecutable = resolveCodexExecutable();
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "efoundry G04 한글 "));
  const codexHome = path.join(tempRoot, "isolated CODEX_HOME", "상태");
  const isolatedUserHome = path.join(tempRoot, "isolated user profile", "사용자");
  const isolatedAppData = path.join(isolatedUserHome, "AppData", "Roaming");
  const isolatedLocalAppData = path.join(isolatedUserHome, "AppData", "Local");
  const marketplaceRoot = path.join(tempRoot, "local marketplace", "마켓");
  const marketplacePluginRoot = path.join(marketplaceRoot, "plugins", pluginName);
  const detachedPluginRoot = path.join(tempRoot, "detached plugin source", pluginName);
  const emptyCwd = path.join(tempRoot, "empty cwd", "작업 공간");
  const pluginData = path.join(tempRoot, "persistent plugin data", pluginName);
  const pluginDataSentinel = path.join(pluginData, "g04-plugin-data-sentinel.txt");
  const pluginDataSentinelBytes = Buffer.from("G04 PLUGIN_DATA must survive uninstall\n", "utf8");
  const realCodexHome = path.resolve(process.env.CODEX_HOME ?? path.join(os.homedir(), ".codex"));
  const realConfigPath = path.join(realCodexHome, "config.toml");
  const realConfigStateBefore = fileState(realConfigPath);
  const realSelectorCache = path.join(
    realCodexHome,
    "plugins",
    "cache",
    marketplaceName,
    pluginName,
  );
  const realSelectorExistedBefore = fs.existsSync(realSelectorCache);
  assert.equal(
    realSelectorExistedBefore,
    false,
    `refusing to test over an existing real-user selector cache: ${realSelectorCache}`,
  );

  fs.mkdirSync(codexHome, { recursive: true });
  fs.mkdirSync(isolatedAppData, { recursive: true });
  fs.mkdirSync(isolatedLocalAppData, { recursive: true });
  fs.mkdirSync(path.dirname(marketplacePluginRoot), { recursive: true });
  fs.mkdirSync(emptyCwd, { recursive: true });
  fs.mkdirSync(pluginData, { recursive: true });
  fs.writeFileSync(pluginDataSentinel, pluginDataSentinelBytes);
  fs.cpSync(sourcePluginRoot, marketplacePluginRoot, { recursive: true, errorOnExist: true });
  fs.mkdirSync(path.join(marketplaceRoot, ".agents", "plugins"), { recursive: true });
  fs.writeFileSync(
    path.join(marketplaceRoot, ".agents", "plugins", "marketplace.json"),
    `${JSON.stringify(
      {
        name: marketplaceName,
        interface: { displayName: "G04 Local Marketplace" },
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

  const replacements = [
    [tempRoot, "<G04_TEMP_ROOT>"],
    [repositoryRoot, "<REPOSITORY_ROOT>"],
    [os.homedir(), "<REAL_USER_HOME>"],
    [realCodexHome, "<REAL_CODEX_HOME>"],
    [codexExecutable, "<CODEX_EXECUTABLE>"],
  ];
  const commands = [];
  const childEnv = {
    ...process.env,
    APPDATA: isolatedAppData,
    CODEX_HOME: codexHome,
    HOME: isolatedUserHome,
    LOCALAPPDATA: isolatedLocalAppData,
    PLUGIN_DATA: pluginData,
    USERPROFILE: isolatedUserHome,
  };
  if (process.platform === "win32") {
    const homeRoot = path.parse(isolatedUserHome).root;
    childEnv.HOMEDRIVE = homeRoot.slice(0, -1);
    childEnv.HOMEPATH = `${path.sep}${path.relative(homeRoot, isolatedUserHome)}`;
  }
  const run = (args, { expectStatus = 0, env = childEnv, cwd = emptyCwd } = {}) => {
    const result = spawnSync(codexExecutable, args, {
      cwd,
      encoding: "utf8",
      env,
      shell: false,
      windowsHide: true,
    });
    const normalizedStdout = normalizeOutput(result.stdout ?? "", replacements);
    const normalizedStderr = normalizeOutput(result.stderr ?? "", replacements);
    const command = {
      argv: [
        "<CODEX_EXECUTABLE>",
        ...args.map((argument) => normalizeOutput(argument, replacements)),
      ],
      status: result.status,
      signal: result.signal,
      expected_status: expectStatus,
      semantic_result: result.status === expectStatus ? "PASS" : "FAIL",
      stdout_byte_size: Buffer.byteLength(normalizedStdout, "utf8"),
      stdout_sha256: sha256(Buffer.from(normalizedStdout, "utf8")),
      stderr_byte_size: Buffer.byteLength(normalizedStderr, "utf8"),
      stderr_sha256: sha256(Buffer.from(normalizedStderr, "utf8")),
    };
    commands.push(command);
    assert.equal(result.error, undefined, `${args.join(" ")} failed to spawn: ${result.error}`);
    assert.equal(
      result.status,
      expectStatus,
      `${args.join(" ")} exited ${result.status}\nstdout=${normalizedStdout}\nstderr=${normalizedStderr}`,
    );
    return result;
  };

  try {
    const versionResult = run(["--version"]);
    const codexVersion = versionResult.stdout.trim();
    const sourceInventory = inventory(marketplacePluginRoot);

    const marketplaceAdd = parseJson(
      run(["plugin", "marketplace", "add", marketplaceRoot, "--json"]).stdout,
      "marketplace add",
    );
    assert.match(JSON.stringify(marketplaceAdd), new RegExp(marketplaceName, "u"));

    const available = parseJson(
      run(["plugin", "list", "--available", "--json"]).stdout,
      "available plugin list",
    );
    assert.match(JSON.stringify(available), new RegExp(pluginName, "u"));
    assert.equal(containsPersonalMarketplace(available), false);

    const installResult = parseJson(
      run(["plugin", "add", selector, "--json"]).stdout,
      "plugin add",
    );
    assert.match(JSON.stringify(installResult), new RegExp(pluginName, "u"));

    const installedRoot = findInstalledRoot(codexHome, installResult);
    const installedInventory = inventory(installedRoot);
    const parity = compareInventories(sourceInventory, installedInventory);
    assert.deepEqual(parity, { missingPaths: [], extraPaths: [], hashMismatches: [] });

    const installedManifest = JSON.parse(
      fs.readFileSync(path.join(installedRoot, ".codex-plugin", "plugin.json"), "utf8"),
    );
    assert.equal(installedManifest.name, pluginName);
    assert.deepEqual(installedManifest.interface.capabilities, []);

    const initialState = pluginEntry(
      parseJson(run(["plugin", "list", "--json"]).stdout, "installed plugin list"),
    );
    assert.equal(initialState.enabled, true);

    const configPath = path.join(codexHome, "config.toml");
    setEnabled(configPath, false);
    const disabledState = pluginEntry(
      parseJson(run(["plugin", "list", "--json"]).stdout, "disabled plugin list"),
    );
    assert.equal(disabledState.enabled, false);

    setEnabled(configPath, true);
    const reenabledState = pluginEntry(
      parseJson(run(["plugin", "list", "--json"]).stdout, "re-enabled plugin list"),
    );
    assert.equal(reenabledState.enabled, true);

    fs.mkdirSync(path.dirname(detachedPluginRoot), { recursive: true });
    fs.renameSync(marketplacePluginRoot, detachedPluginRoot);
    assert.equal(fs.existsSync(marketplacePluginRoot), false);
    assert.deepEqual(inventory(installedRoot), installedInventory);
    const detachedSourceState = pluginEntry(
      parseJson(
        run(["plugin", "list", "--json"]).stdout,
        "installed plugin list after marketplace source detachment",
      ),
    );
    assert.equal(detachedSourceState.enabled, true);

    const dispatcher = path.join(installedRoot, "bin", "efoundry.mjs");
    const dispatcherSource = fs.readFileSync(dispatcher, "utf8");
    assert.match(
      dispatcherSource,
      /new URL\(["']\.\.\/dist\/cli\.mjs["'], import\.meta\.url\)/u,
    );
    assert.match(dispatcherSource, /await import\(payloadCli\.href\)/u);
    const dispatcherTarget = fileURLToPath(
      new URL("../dist/cli.mjs", pathToFileURL(dispatcher)),
    );
    const installedDistTarget = path.join(installedRoot, "dist", "cli.mjs");
    assert.equal(path.resolve(dispatcherTarget), path.resolve(installedDistTarget));
    assert.equal(fs.existsSync(dispatcherTarget), true, "installed dispatcher target is missing");
    const dispatcherTargetIdentity = path
      .relative(installedRoot, dispatcherTarget)
      .split(path.sep)
      .join("/");
    assert.equal(dispatcherTargetIdentity, "dist/cli.mjs");

    const dispatcherResult = spawnSync(process.execPath, [dispatcher, "status", "--json"], {
      cwd: emptyCwd,
      encoding: "utf8",
      env: {
        ...childEnv,
        CLAUDE_PLUGIN_ROOT: installedRoot,
        PATH: "",
        PLUGIN_ROOT: installedRoot,
      },
      shell: false,
      windowsHide: true,
    });
    assert.equal(dispatcherResult.error, undefined);
    assert.equal(
      dispatcherResult.status,
      0,
      `installed status exited ${dispatcherResult.status}\nstdout=${dispatcherResult.stdout}\nstderr=${dispatcherResult.stderr}`,
    );
    assert.equal(dispatcherResult.signal, null);
    assert.equal(dispatcherResult.stderr.trim(), "", "installed status wrote to stderr");
    const dispatcherStatus = parseJson(dispatcherResult.stdout, "installed dispatcher status --json");
    assert.equal(dispatcherStatus !== null && typeof dispatcherStatus === "object", true);
    assertNoRepositoryPath(dispatcherSource, "installed dispatcher source");
    assertNoRepositoryPath(dispatcherResult.stdout, "installed status stdout");
    assertNoRepositoryPath(dispatcherResult.stderr, "installed status stderr");

    const removeResult = parseJson(
      run(["plugin", "remove", selector, "--json"]).stdout,
      "plugin remove",
    );
    assert.match(JSON.stringify(removeResult), new RegExp(pluginName, "u"));
    assert.equal(fs.existsSync(installedRoot), false);
    assert.doesNotMatch(fs.readFileSync(configPath, "utf8"), new RegExp(selector, "u"));
    assert.equal(fs.existsSync(pluginDataSentinel), true, "plugin removal deleted PLUGIN_DATA");
    assert.deepEqual(
      fs.readFileSync(pluginDataSentinel),
      pluginDataSentinelBytes,
      "PLUGIN_DATA sentinel changed",
    );

    const marketplaceRemove = parseJson(
      run(["plugin", "marketplace", "remove", marketplaceName, "--json"]).stdout,
      "marketplace remove",
    );
    assert.match(JSON.stringify(marketplaceRemove), new RegExp(marketplaceName, "u"));
    const remainingMarketplaces = parseJson(
      run(["plugin", "marketplace", "list", "--json"]).stdout,
      "marketplace list after removal",
    );
    assert.doesNotMatch(JSON.stringify(remainingMarketplaces), new RegExp(marketplaceName, "u"));
    assert.equal(containsPersonalMarketplace(remainingMarketplaces), false);
    assert.equal(fs.existsSync(realSelectorCache), false);

    const verification = {
      schema_version: "g04-local-marketplace-verification/v1",
      work_package_id: "G04",
      host: {
        platform: process.platform,
        arch: process.arch,
        codex_version: codexVersion,
      },
      isolation: {
        isolated_codex_home: true,
        isolated_user_profile: true,
        personal_marketplace_visible: false,
        empty_cwd: true,
        spaces_and_non_ascii_paths: true,
        real_user_selector_cache_created: false,
        real_user_config_unchanged: true,
      },
      fresh_install_test: {
        marketplace_add: "PASS",
        available_listing: "PASS",
        plugin_install: "PASS",
        installed_cache_copy: "PASS",
        source_file_count: sourceInventory.length,
        installed_file_count: installedInventory.length,
        missing_paths: parity.missingPaths,
        extra_paths: parity.extraPaths,
        hash_mismatches: parity.hashMismatches,
        initial_enabled_state: true,
        disable_state_observed: disabledState.enabled === false,
        reenable_state_observed: reenabledState.enabled === true,
        marketplace_source_detached: true,
        installed_cache_survived_source_detachment: true,
        installed_plugin_listed_after_source_detachment: true,
      },
      path_less_boundary: {
        invocation_used_absolute_installed_dispatcher: true,
        path_environment_empty: true,
        dispatcher_target_root: "INSTALLED_PLUGIN_ROOT",
        dispatcher_target_identity: dispatcherTargetIdentity,
        repository_checkout_fallback_count: 0,
        installed_status_execution: "PASS",
        observed_exit_code: dispatcherResult.status,
        observed_signal: dispatcherResult.signal,
      },
      clean_uninstall_test: {
        plugin_remove: "PASS",
        installed_cache_residue_count: 0,
        installed_config_residue_count: 0,
        marketplace_remove: "PASS",
        marketplace_config_residue_count: 0,
        plugin_data_sentinel: "PRESERVED",
      },
      commands,
      limitations: [
        "The current G01 shell declares no runtime capabilities.",
        "The headless enable/disable check edits only the isolated config state that the supported UI owns.",
      ],
      final_status: "PASS",
    };
    assertPortableEvidence(verification);
    return verification;
  } finally {
    const realSelectorCacheExistsAfter = fs.existsSync(realSelectorCache);
    const realConfigStateAfter = fileState(realConfigPath);
    removeOwnedTempRoot(tempRoot);
    assert.equal(realSelectorCacheExistsAfter, false, "real user plugin cache was modified");
    assert.deepEqual(realConfigStateAfter, realConfigStateBefore, "real user config was modified");
  }
}

const directInvocation =
  process.argv[1] !== undefined && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;

if (directInvocation) {
  try {
    process.stdout.write(`${JSON.stringify(runLocalMarketplaceLifecycle(), null, 2)}\n`);
  } catch (error) {
    process.stderr.write(`${error.stack ?? error.message}\n`);
    process.exitCode = 1;
  }
}
