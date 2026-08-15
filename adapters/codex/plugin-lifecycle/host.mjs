import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {
  FAILURE,
  LIMITS,
  STATUS,
  allowedFields,
  boundedJson,
  canonicalJson,
  fail,
  isPlainObject,
  sha256,
  strictVersion,
} from "./core.mjs";

const ENV_ALLOWLIST = new Set([
  "APPDATA",
  "CODEX_HOME",
  "HOME",
  "LANG",
  "LC_ALL",
  "LOCALAPPDATA",
  "NO_COLOR",
  "PLUGIN_DATA",
  "SYSTEMROOT",
  "TEMP",
  "TERM",
  "TMP",
  "USERPROFILE",
  "WINDIR",
]);

const ENV_PATH_KEYS = new Set([
  "APPDATA",
  "CODEX_HOME",
  "HOME",
  "LOCALAPPDATA",
  "PLUGIN_DATA",
  "SYSTEMROOT",
  "TEMP",
  "TMP",
  "USERPROFILE",
  "WINDIR",
]);

function pathKey(value) {
  const resolved = path.resolve(value).normalize("NFC");
  return process.platform === "win32" || process.platform === "darwin" ? resolved.toLowerCase() : resolved;
}

function overlap(left, right) {
  const a = pathKey(left);
  const b = pathKey(right);
  return a === b || a.startsWith(`${b}${path.sep}`) || b.startsWith(`${a}${path.sep}`);
}

function directoryIdentity(stat) {
  return `${stat.dev}:${stat.ino}`;
}

function absolute(value, label) {
  if (typeof value !== "string" || value.includes("\0") || !path.isAbsolute(value)) {
    fail(FAILURE.UNSAFE_PATH, `${label} must be an explicit absolute path`);
  }
  if (process.platform === "win32" && (/^(?:\\\\|\/\/)/u.test(value) || path.parse(value).root.startsWith("\\\\"))) {
    fail(FAILURE.UNSAFE_PATH, `${label} cannot be a UNC or network path`);
  }
  if (path.resolve(value) !== path.normalize(value)) fail(FAILURE.UNSAFE_PATH, `${label} is not canonical`);
  return path.resolve(value);
}

function ordinaryExisting(value, label, type) {
  const resolved = absolute(value, label);
  const stat = fs.lstatSync(resolved, { bigint: true });
  if (stat.isSymbolicLink() || (type === "file" ? !stat.isFile() : !stat.isDirectory())) {
    fail(FAILURE.UNSAFE_PATH, `${label} is not an ordinary ${type}`);
  }
  const real = fs.realpathSync.native(resolved);
  if (pathKey(real) !== pathKey(resolved)) fail(FAILURE.UNSAFE_PATH, `${label} resolves through an alias`);
  return { path: real, stat };
}

function projectedRoot(value, label) {
  const resolved = absolute(value, label);
  if (fs.existsSync(resolved)) return ordinaryExisting(resolved, label, "directory").path;
  let cursor = resolved;
  while (!fs.existsSync(cursor)) {
    const parent = path.dirname(cursor);
    if (parent === cursor) fail(FAILURE.UNSAFE_PATH, `${label} has no ordinary parent`);
    cursor = parent;
  }
  ordinaryExisting(cursor, `${label} parent`, "directory");
  return resolved;
}

function executableIdentity(value) {
  const ordinary = ordinaryExisting(value, "codexExecutable", "file");
  if (ordinary.stat.nlink !== 1n) fail(FAILURE.UNSAFE_PATH, "codexExecutable is hardlinked");
  if (process.platform === "win32" && path.extname(ordinary.path).toLowerCase() !== ".exe") {
    fail(FAILURE.UNSAFE_PATH, "codexExecutable must be an ordinary .exe");
  }
  if (process.platform !== "win32" && (ordinary.stat.mode & 0o111n) === 0n) {
    fail(FAILURE.UNSAFE_PATH, "codexExecutable is not executable");
  }
  if (ordinary.stat.size > BigInt(LIMITS.maxFileBytes)) {
    fail(FAILURE.RESOURCE_LIMIT, "codexExecutable exceeds the executable identity bound");
  }
  const fd = fs.openSync(ordinary.path, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
  const hash = createHash("sha256");
  let total = 0;
  try {
    const openedBefore = fs.fstatSync(fd, { bigint: true });
    if (openedBefore.dev !== ordinary.stat.dev || openedBefore.ino !== ordinary.stat.ino) {
      fail(FAILURE.UNSAFE_PATH, "codexExecutable changed before identity capture");
    }
    const buffer = Buffer.allocUnsafe(64 * 1024);
    for (;;) {
      const count = fs.readSync(fd, buffer, 0, buffer.length, null);
      if (count === 0) break;
      total += count;
      if (total > LIMITS.maxFileBytes) fail(FAILURE.RESOURCE_LIMIT, "codexExecutable exceeded its identity bound");
      hash.update(buffer.subarray(0, count));
    }
    const openedAfter = fs.fstatSync(fd, { bigint: true });
    const after = fs.lstatSync(ordinary.path, { bigint: true });
    const beforeSignature = [ordinary.stat.dev, ordinary.stat.ino, ordinary.stat.size, ordinary.stat.mtimeNs, ordinary.stat.ctimeNs].join(":");
    const afterSignature = [after.dev, after.ino, after.size, after.mtimeNs, after.ctimeNs].join(":");
    if (
      beforeSignature !== afterSignature ||
      openedAfter.dev !== ordinary.stat.dev ||
      openedAfter.ino !== ordinary.stat.ino ||
      openedAfter.size !== ordinary.stat.size
    ) fail(FAILURE.UNSAFE_PATH, "codexExecutable changed during identity capture");
  } finally {
    fs.closeSync(fd);
  }
  return {
    path: ordinary.path,
    signature: [ordinary.stat.dev, ordinary.stat.ino, ordinary.stat.size, ordinary.stat.mtimeNs, ordinary.stat.ctimeNs].join(":"),
    content_hash: `sha256:${hash.digest("hex")}`,
  };
}

function controlledEnv(value, pluginDataRoot) {
  if (!isPlainObject(value)) fail(FAILURE.INVALID_INPUT, "env must be an explicit plain object");
  const env = Object.create(null);
  const seen = new Set();
  for (const [rawKey, rawValue] of Object.entries(value)) {
    const key = rawKey.toUpperCase();
    if (
      !ENV_ALLOWLIST.has(key) ||
      seen.has(key) ||
      typeof rawValue !== "string" ||
      rawValue.includes("\0") ||
      Buffer.byteLength(rawValue, "utf8") > LIMITS.maxInjectedString
    ) {
      fail(FAILURE.INVALID_INPUT, "env contains a forbidden, aliased, or invalid entry");
    }
    seen.add(key);
    env[key] = rawValue;
  }
  if (!seen.has("CODEX_HOME") || !seen.has("PLUGIN_DATA")) {
    fail(FAILURE.INVALID_INPUT, "env requires CODEX_HOME and PLUGIN_DATA");
  }
  const pathRoots = {};
  for (const key of ENV_PATH_KEYS) {
    if (!seen.has(key)) continue;
    const ordinary = ordinaryExisting(env[key], `env.${key}`, "directory");
    env[key] = ordinary.path;
    pathRoots[key] = {
      path: ordinary.path,
      filesystem_id: directoryIdentity(ordinary.stat),
    };
  }
  const codexHome = pathRoots.CODEX_HOME.path;
  if (absolute(env.CODEX_HOME, "env.CODEX_HOME") !== codexHome) {
    fail(FAILURE.INVALID_INPUT, "env.CODEX_HOME must be canonical");
  }
  if (pathKey(env.PLUGIN_DATA) !== pathKey(pluginDataRoot) || absolute(env.PLUGIN_DATA, "env.PLUGIN_DATA") !== pluginDataRoot) {
    fail(FAILURE.INVALID_INPUT, "env.PLUGIN_DATA must be the canonical pluginDataRoot");
  }
  env.CODEX_HOME = codexHome;
  env.PLUGIN_DATA = pluginDataRoot;
  pathRoots.PLUGIN_DATA.path = pluginDataRoot;
  return {
    env: Object.freeze(env),
    codexHome,
    codexHomeIdentity: pathRoots.CODEX_HOME.filesystem_id,
    pathRoots: Object.freeze(pathRoots),
  };
}

export function resolveConfiguration(options) {
  allowedFields(
    options,
    [
      "codexExecutable",
      "lifecycleRoot",
      "pluginDataRoot",
      "cwd",
      "env",
      "commandPort",
      "probePort",
      "quiescencePort",
      "migrationPort",
      "trustPort",
      "verificationPort",
      "privateRootPort",
      "dataSnapshotPort",
      "timeoutMs",
      "maxOutputBytes",
      "maxOperationMs",
    ],
    "lifecycle options",
  );
  for (const key of ["codexExecutable", "lifecycleRoot", "pluginDataRoot", "cwd", "env"]) {
    if (!(key in options)) fail(FAILURE.INVALID_INPUT, `lifecycle options.${key} is required`);
  }
  const executable = executableIdentity(options.codexExecutable);
  const pluginData = ordinaryExisting(options.pluginDataRoot, "pluginDataRoot", "directory");
  const pluginDataRoot = pluginData.path;
  const cwdRecord = ordinaryExisting(options.cwd, "cwd", "directory");
  const cwd = cwdRecord.path;
  if (fs.readdirSync(cwd).length !== 0) fail(FAILURE.UNSAFE_PATH, "cwd must be empty");
  const lifecycleRoot = projectedRoot(options.lifecycleRoot, "lifecycleRoot");
  const environment = controlledEnv(options.env, pluginDataRoot);
  const boundaries = [
    [lifecycleRoot, pluginDataRoot],
    [lifecycleRoot, cwd],
    [lifecycleRoot, environment.codexHome],
    [pluginDataRoot, cwd],
    [pluginDataRoot, environment.codexHome],
    [cwd, environment.codexHome],
    [executable.path, lifecycleRoot],
    [executable.path, pluginDataRoot],
  ];
  if (boundaries.some(([left, right]) => overlap(left, right))) {
    fail(FAILURE.UNSAFE_PATH, "lifecycle filesystem boundaries are not disjoint");
  }
  for (const key of ["TEMP", "TMP"]) {
    const item = environment.pathRoots[key];
    if (item !== undefined && [lifecycleRoot, pluginDataRoot, cwd].some((root) => overlap(item.path, root))) {
      fail(FAILURE.UNSAFE_PATH, `env.${key} overlaps a controlled lifecycle root`);
    }
  }
  const timeoutMs = options.timeoutMs ?? 120_000;
  const maxOutputBytes = options.maxOutputBytes ?? LIMITS.maxCommandOutputBytes;
  const maxOperationMs = options.maxOperationMs ?? LIMITS.maxOperationMs;
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1000 || timeoutMs > 600_000) {
    fail(FAILURE.INVALID_INPUT, "timeoutMs is outside the supported range");
  }
  if (!Number.isSafeInteger(maxOutputBytes) || maxOutputBytes < 1024 || maxOutputBytes > LIMITS.maxCommandOutputBytes) {
    fail(FAILURE.INVALID_INPUT, "maxOutputBytes is outside the supported range");
  }
  if (!Number.isSafeInteger(maxOperationMs) || maxOperationMs < timeoutMs || maxOperationMs > LIMITS.maxOperationMs) {
    fail(FAILURE.INVALID_INPUT, "maxOperationMs is outside the supported range");
  }
  return {
    executable,
    lifecycleRoot,
    pluginDataRoot,
    cwd,
    cwdIdentity: directoryIdentity(cwdRecord.stat),
    env: environment.env,
    envRoots: environment.pathRoots,
    codexHome: environment.codexHome,
    codexHomeIdentity: environment.codexHomeIdentity,
    commandPort: options.commandPort ?? defaultCommandPort,
    commandPortInjected: options.commandPort !== undefined && options.commandPort !== null,
    probePort: options.probePort ?? null,
    quiescencePort: options.quiescencePort ?? null,
    migrationPort: options.migrationPort ?? null,
    trustPort: options.trustPort ?? null,
    verificationPort: options.verificationPort ?? null,
    privateRootPort: options.privateRootPort ?? null,
    dataSnapshotPort: options.dataSnapshotPort ?? null,
    timeoutMs,
    maxOutputBytes,
    maxOperationMs,
  };
}

function defaultCommandPort({ executable, args, cwd, env, timeoutMs, maxOutputBytes }) {
  return spawnSync(executable, args, {
    cwd,
    env,
    encoding: "utf8",
    shell: false,
    windowsHide: true,
    timeout: timeoutMs,
    maxBuffer: maxOutputBytes,
  });
}

export function parseSelector(value) {
  if (typeof value !== "string" || value.length > 257) fail(FAILURE.INVALID_INPUT, "selector is invalid");
  const split = value.split("@");
  const pattern = /^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$/u;
  if (split.length !== 2 || !pattern.test(split[0]) || !pattern.test(split[1])) {
    fail(FAILURE.INVALID_INPUT, "selector must be exact plugin@marketplace");
  }
  return { selector: value, pluginName: split[0], marketplaceName: split[1] };
}

export function parseHostVersionText(value) {
  if (typeof value !== "string" || Buffer.byteLength(value, "utf8") > 1024) {
    fail(FAILURE.HOST_OUTPUT_INVALID, "host version output is invalid");
  }
  const match = /^(?:[A-Za-z][A-Za-z0-9._-]{0,63}\s+)?((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?)$/u.exec(value.trim());
  if (match === null) fail(FAILURE.HOST_OUTPUT_INVALID, "host version is not one strict SemVer value");
  try {
    return strictVersion(match[1]);
  } catch {
    fail(FAILURE.HOST_OUTPUT_INVALID, "host version is not strict SemVer");
  }
}

function allowedArgs(args) {
  if (canonicalJson(args) === canonicalJson(["--version"])) return true;
  if (canonicalJson(args) === canonicalJson(["plugin", "list", "--json"])) return true;
  if (canonicalJson(args) === canonicalJson(["plugin", "marketplace", "list", "--json"])) return true;
  if (
    args.length === 5 &&
    args[0] === "plugin" &&
    args[1] === "marketplace" &&
    args[2] === "add" &&
    path.isAbsolute(args[3]) &&
    args[4] === "--json"
  ) return true;
  if (
    args.length === 5 &&
    args[0] === "plugin" &&
    args[1] === "marketplace" &&
    args[2] === "remove" &&
    /^[a-z0-9][a-z0-9._-]{0,127}$/u.test(args[3]) &&
    args[4] === "--json"
  ) return true;
  if (
    args.length === 4 &&
    args[0] === "plugin" &&
    ["add", "remove"].includes(args[1]) &&
    args[3] === "--json"
  ) {
    parseSelector(args[2]);
    return true;
  }
  return false;
}

function boundedDiagnosticText(text) {
  const limit = Math.floor(LIMITS.maxDiagnosticBytes / 3);
  if (Buffer.byteLength(text, "utf8") <= limit) return text;
  const prefix = Buffer.from(text, "utf8").subarray(0, limit).toString("utf8");
  return `${prefix}\n<TRUNCATED:${sha256(Buffer.from(text, "utf8"))}>`;
}

function objects(value, output = []) {
  if (Array.isArray(value)) {
    for (const item of value) objects(item, output);
  } else if (isPlainObject(value)) {
    output.push(value);
    for (const item of Object.values(value)) objects(item, output);
  }
  return output;
}

function exactMatch(entry, parsed) {
  if ([entry.selector, entry.id, entry.plugin].includes(parsed.selector)) return true;
  const name = entry.name ?? entry.plugin_name;
  const marketplace = entry.marketplace ?? entry.marketplaceName ?? entry.marketplace_name;
  return name === parsed.pluginName && marketplace === parsed.marketplaceName;
}

function roots(entry) {
  const result = new Map();
  const keys = new Set([
    "installedPath", "installed_path", "installPath", "install_path", "installRoot", "install_root",
    "pluginRoot", "plugin_root", "cachePath", "cache_path",
  ]);
  const visit = (value, depth, container = null) => {
    if (depth > 3 || !isPlainObject(value)) return;
    for (const [key, item] of Object.entries(value)) {
      if (
        typeof item === "string" &&
        path.isAbsolute(item) &&
        (keys.has(key) || ((key === "root" || key === "path") && [null, "install", "installation", "cache"].includes(container)))
      ) {
        const canonical = ordinaryExisting(item, "host reported root", "directory").path;
        result.set(pathKey(canonical), canonical);
      }
      if (isPlainObject(item)) visit(item, depth + 1, key);
    }
  };
  visit(entry, 0);
  return [...result.values()];
}

export function exactPluginEntry(payload, selector, { requireRoot = false } = {}) {
  const parsed = parseSelector(selector);
  const matches = objects(payload).filter((entry) => exactMatch(entry, parsed));
  if (matches.some((entry) => Object.hasOwn(entry, "enabled") && typeof entry.enabled !== "boolean")) {
    fail(FAILURE.HOST_OUTPUT_INVALID, "exact selector enabled state is not boolean");
  }
  const enabled = matches.filter((entry) => entry.enabled !== false);
  const disabled = matches.filter((entry) => entry.enabled === false);
  if (matches.length === 0) return null;
  if (enabled.length > 0 && disabled.length > 0) {
    fail(FAILURE.HOST_AMBIGUOUS, "exact selector has conflicting enabled states");
  }
  const selected = enabled.length > 0 ? enabled : disabled;
  const allRoots = [...new Set(selected.flatMap(roots))];
  if (selected.length > 1 && allRoots.length !== 1) fail(FAILURE.HOST_AMBIGUOUS, "multiple exact selector entries");
  if (requireRoot && allRoots.length !== 1) fail(FAILURE.HOST_AMBIGUOUS, "exact selector has no unique installed root");
  const isEnabled = enabled.length > 0;
  return {
    entry: selected[0],
    root: allRoots[0] ?? null,
    enabled: isEnabled,
    state: isEnabled ? "ENABLED" : "DISABLED",
  };
}

export function exactMarketplaceEntry(payload, name) {
  const matches = objects(payload).filter(
    (entry) => entry.name === name || entry.marketplaceName === name || entry.marketplace_name === name,
  );
  if (matches.length === 0) return null;
  const rootsFound = [...new Set(matches.flatMap(roots))];
  if (rootsFound.length > 1 || (matches.length > 1 && rootsFound.length !== 1)) {
    fail(FAILURE.HOST_AMBIGUOUS, "multiple exact marketplace entries or roots");
  }
  return { entry: matches[0], root: rootsFound[0] ?? null };
}

export function createHostClient(config, capabilityIds) {
  if (typeof config.commandPort !== "function") fail(FAILURE.INVALID_INPUT, "commandPort must be synchronous function");
  const commandCapabilityId = capabilityIds.command;
  const conditionalMutationCapabilityId = capabilityIds.conditionalMutation;
  const revalidateCommandCapability = () => {
    const observedCommand = config.commandPortInjected ? config.commandPort.capability_id : null;
    const observedConditional = config.commandPort.conditional_mutation_capability_id ?? null;
    if (observedCommand !== commandCapabilityId || observedConditional !== conditionalMutationCapabilityId) {
      fail(FAILURE.HOST_UNSUPPORTED, "command port composition identity changed", STATUS.UNSUPPORTED);
    }
  };
  const requireConditionalMutationCapability = () => {
    revalidateCommandCapability();
    if (conditionalMutationCapabilityId === null) {
      fail(
        FAILURE.HOST_UNSUPPORTED,
        "the host port cannot condition destructive mutations on exact observed identity",
        STATUS.UNSUPPORTED,
      );
    }
    return conditionalMutationCapabilityId;
  };
  const requireConditionalMutation = (value) => {
    requireConditionalMutationCapability();
    if (!isPlainObject(value) || canonicalJson(Object.keys(value).sort()) !== canonicalJson([
      "expected_root",
      "expected_tree_hash",
      "identity",
      "kind",
    ])) {
      fail(FAILURE.INVALID_INPUT, "conditional mutation guard is invalid");
    }
    if (!["PLUGIN_REMOVE", "MARKETPLACE_REMOVE"].includes(value.kind)) {
      fail(FAILURE.INVALID_INPUT, "conditional mutation kind is invalid");
    }
    if (value.kind === "PLUGIN_REMOVE") parseSelector(value.identity);
    else if (typeof value.identity !== "string" || !/^[a-z0-9][a-z0-9._-]{0,127}$/u.test(value.identity)) {
      fail(FAILURE.INVALID_INPUT, "conditional marketplace identity is invalid");
    }
    if (
      typeof value.expected_root !== "string" ||
      !path.isAbsolute(value.expected_root) ||
      typeof value.expected_tree_hash !== "string" ||
      !/^sha256:[0-9a-f]{64}$/u.test(value.expected_tree_hash)
    ) fail(FAILURE.INVALID_INPUT, "conditional mutation identity is incomplete");
    return Object.freeze({
      ...value,
      capability_id: conditionalMutationCapabilityId,
    });
  };
  const invoke = (args, mutationGuard = null) => {
    revalidateCommandCapability();
    if (!Array.isArray(args) || !args.every((item) => typeof item === "string") || !allowedArgs(args)) {
      fail(FAILURE.HOST_UNSUPPORTED, "command is outside the host allowlist", STATUS.UNSUPPORTED);
    }
    const current = executableIdentity(config.executable.path);
    if (
      current.signature !== config.executable.signature ||
      current.content_hash !== config.executable.content_hash
    ) fail(FAILURE.UNSAFE_PATH, "codexExecutable identity changed");
    const cwdBefore = ordinaryExisting(config.cwd, "cwd", "directory");
    if (directoryIdentity(cwdBefore.stat) !== config.cwdIdentity || fs.readdirSync(config.cwd).length !== 0) {
      fail(FAILURE.UNSAFE_PATH, "cwd identity or emptiness changed");
    }
    for (const [key, expected] of Object.entries(config.envRoots)) {
      if (key === "PLUGIN_DATA") continue;
      const observed = ordinaryExisting(expected.path, `env.${key}`, "directory");
      if (directoryIdentity(observed.stat) !== expected.filesystem_id) {
        fail(FAILURE.UNSAFE_PATH, `env.${key} identity changed`);
      }
    }
    const codexHomeRecord = ordinaryExisting(config.codexHome, "env.CODEX_HOME", "directory");
    const codexHome = codexHomeRecord.path;
    const lifecycleRoot = ordinaryExisting(config.lifecycleRoot, "lifecycleRoot", "directory").path;
    if (pathKey(codexHome) !== pathKey(config.codexHome) || pathKey(lifecycleRoot) !== pathKey(config.lifecycleRoot)) {
      fail(FAILURE.UNSAFE_PATH, "host configuration root identity changed");
    }
    if (fs.existsSync(config.pluginDataRoot)) {
      ordinaryExisting(config.pluginDataRoot, "pluginDataRoot", "directory");
    } else {
      ordinaryExisting(path.dirname(config.pluginDataRoot), "pluginDataRoot parent", "directory");
    }
    if (
      overlap(config.lifecycleRoot, config.pluginDataRoot) ||
      overlap(config.lifecycleRoot, config.codexHome) ||
      overlap(config.cwd, config.pluginDataRoot) ||
      config.env.PLUGIN_DATA !== config.pluginDataRoot ||
      config.env.CODEX_HOME !== config.codexHome
    ) fail(FAILURE.UNSAFE_PATH, "host configuration boundaries drifted");
    let conditionalMutation = null;
    if (mutationGuard !== null) {
      conditionalMutation = requireConditionalMutation(mutationGuard);
      const removesPlugin = args[0] === "plugin" && args[1] === "remove" && args[2] === conditionalMutation.identity;
      const removesMarketplace =
        args[0] === "plugin" &&
        args[1] === "marketplace" &&
        args[2] === "remove" &&
        args[3] === conditionalMutation.identity;
      if (
        (conditionalMutation.kind === "PLUGIN_REMOVE" && !removesPlugin) ||
        (conditionalMutation.kind === "MARKETPLACE_REMOVE" && !removesMarketplace)
      ) fail(FAILURE.INVALID_INPUT, "conditional mutation guard does not bind the command");
    }
    let raw;
    try {
      const commandInput = {
        executable: config.executable.path,
        args: [...args],
        cwd: config.cwd,
        env: config.env,
        timeoutMs: config.timeoutMs,
        maxOutputBytes: config.maxOutputBytes,
      };
      if (conditionalMutation !== null) commandInput.conditionalMutation = conditionalMutation;
      raw = config.commandPort(commandInput);
    } catch (cause) {
      raw = { status: null, signal: null, stdout: "", stderr: "", error: cause };
    }
    if (raw?.then !== undefined || raw === null || typeof raw !== "object") {
      fail(FAILURE.HOST_UNSUPPORTED, "commandPort is not synchronous", STATUS.UNSUPPORTED);
    }
    const stdout = Buffer.isBuffer(raw.stdout) ? raw.stdout.toString("utf8") : String(raw.stdout ?? "");
    const stderr = Buffer.isBuffer(raw.stderr) ? raw.stderr.toString("utf8") : String(raw.stderr ?? "");
    if (Buffer.byteLength(stdout, "utf8") > config.maxOutputBytes || Buffer.byteLength(stderr, "utf8") > config.maxOutputBytes) {
      fail(FAILURE.RESOURCE_LIMIT, "host output exceeded its bound");
    }
    const diagnostic = boundedJson(
      {
        argv: [config.executable.path, ...args],
        status: Number.isInteger(raw.status) ? raw.status : null,
        signal: typeof raw.signal === "string" ? raw.signal : null,
        error_code: typeof raw.error?.code === "string" ? raw.error.code : null,
        stdout: boundedDiagnosticText(stdout),
        stderr: boundedDiagnosticText(stderr),
      },
      "host diagnostic",
      { bytes: LIMITS.maxDiagnosticBytes, string: LIMITS.maxDiagnosticBytes },
    );
    const executableAfter = executableIdentity(config.executable.path);
    if (
      executableAfter.signature !== config.executable.signature ||
      executableAfter.content_hash !== config.executable.content_hash
    ) fail(FAILURE.UNSAFE_PATH, "codexExecutable changed during invocation");
    const cwdAfter = ordinaryExisting(config.cwd, "cwd", "directory");
    if (directoryIdentity(cwdAfter.stat) !== config.cwdIdentity || fs.readdirSync(config.cwd).length !== 0) {
      fail(FAILURE.UNSAFE_PATH, "cwd changed during invocation");
    }
    for (const [key, expected] of Object.entries(config.envRoots)) {
      if (key === "PLUGIN_DATA") continue;
      const observed = ordinaryExisting(expected.path, `env.${key}`, "directory");
      if (directoryIdentity(observed.stat) !== expected.filesystem_id) {
        fail(FAILURE.UNSAFE_PATH, `env.${key} changed during invocation`);
      }
    }
    const lifecycleAfter = ordinaryExisting(config.lifecycleRoot, "lifecycleRoot", "directory").path;
    const codexHomeAfter = ordinaryExisting(config.codexHome, "env.CODEX_HOME", "directory").path;
    if (pathKey(lifecycleAfter) !== pathKey(config.lifecycleRoot) || pathKey(codexHomeAfter) !== pathKey(config.codexHome)) {
      fail(FAILURE.UNSAFE_PATH, "host configuration root changed during invocation");
    }
    if (fs.existsSync(config.pluginDataRoot)) {
      const pluginDataAfter = ordinaryExisting(config.pluginDataRoot, "pluginDataRoot", "directory").path;
      if (pathKey(pluginDataAfter) !== pathKey(config.pluginDataRoot)) {
        fail(FAILURE.UNSAFE_PATH, "pluginDataRoot changed during invocation");
      }
    } else {
      ordinaryExisting(path.dirname(config.pluginDataRoot), "pluginDataRoot parent", "directory");
    }
    if (
      overlap(config.lifecycleRoot, config.pluginDataRoot) ||
      overlap(config.lifecycleRoot, config.codexHome) ||
      overlap(config.cwd, config.pluginDataRoot)
    ) fail(FAILURE.UNSAFE_PATH, "host filesystem boundaries changed during invocation");
    return {
      ok: raw.error == null && raw.status === 0 && raw.signal == null,
      stdout,
      stderr,
      diagnostic,
    };
  };

  const json = (args, label) => {
    const result = invoke(args);
    if (!result.ok) return { ...result, payload: null };
    let parsed;
    try {
      parsed = JSON.parse(result.stdout);
    } catch {
      fail(FAILURE.HOST_OUTPUT_INVALID, `${label} did not return JSON`);
    }
    return {
      ...result,
      payload: boundedJson(parsed, label, {
        bytes: config.maxOutputBytes,
        depth: 32,
        nodes: 100_000,
        string: 256 * 1024,
      }),
    };
  };

  return Object.freeze({
    invoke,
    json,
    conditionalMutationCapabilityId,
    commandCapabilityId,
    requireConditionalMutationCapability,
    requireConditionalMutation,
  });
}
