// Locating and running the plugin-resident Python runtime.
//
// The plugin ships its own copy of the application package. Python-dependent
// commands require EFOUNDRY_PYTHON to name an absolute Python 3.12+ executable
// with the required dependencies; this module never discovers Python through
// PATH. Nothing here resolves `efoundry` from PATH either: a globally installed
// executable would be a different, unversioned copy of the application, and
// the whole point of the bundled runtime is to run only bytes this release
// recorded. The integrity pass detects installation damage and drift; it is
// not a privilege boundary against the same local user who selected both the
// plugin payload and EFOUNDRY_PYTHON.
//
// Every failure is a named code plus a human sentence. Python version and
// dependency failures are bootstrap contracts. A requested operation creates
// one Python child, so there is no probe-child/CLI-child replacement window.

import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  closeSync,
  constants,
  fstatSync,
  lstatSync,
  openSync,
  readFileSync,
  readdirSync,
  realpathSync,
  statSync,
} from "node:fs";
import { dirname, isAbsolute, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

/** Where the payload lives, derived from this file rather than the cwd. */
export function pluginRoot(fromUrl = import.meta.url) {
  // <plugin-root>/{src,dist}/python-runtime.mjs -> <plugin-root>
  return dirname(dirname(fileURLToPath(fromUrl)));
}

/** Named failures a caller can branch on. */
export const RUNTIME_ERRORS = Object.freeze({
  ARTIFACT_INPUT_INVALID: "ARTIFACT_INPUT_INVALID",
  ARTIFACT_INPUT_TOO_LARGE: "ARTIFACT_INPUT_TOO_LARGE",
  ARTIFACT_SCHEMA_UNAVAILABLE: "ARTIFACT_SCHEMA_UNAVAILABLE",
  ARTIFACT_VALIDATION_FAILED: "ARTIFACT_VALIDATION_FAILED",
  BUNDLED_IMPORT_FAILED: "BUNDLED_IMPORT_FAILED",
  BUNDLED_VALIDATION_FAILED: "BUNDLED_VALIDATION_FAILED",
  DOMAIN_ARTIFACT_VALIDATION_FAILED: "DOMAIN_ARTIFACT_VALIDATION_FAILED",
  PYTHON_INTERPRETER_NOT_FOUND: "PYTHON_INTERPRETER_NOT_FOUND",
  PYTHON_VERSION_UNSUPPORTED: "PYTHON_VERSION_UNSUPPORTED",
  RUNTIME_INTEGRITY_FAILED: "RUNTIME_INTEGRITY_FAILED",
});

const PYTHON_CONFIGURATION_REQUIREMENT =
  "Python-dependent commands require EFOUNDRY_PYTHON to be set to an " +
  "absolute path to a Python 3.12+ executable with the required dependencies " +
  "(jsonschema and PyYAML).";

const RUNTIME_MANIFEST_SCHEMA = "epistemic-foundry/mvp-runtime-manifest/v1";
const RUNTIME_INTEGRITY_MESSAGE =
  "the bundled runtime failed integrity validation";
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const QUALIFIED_SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/;
const CONTROL_CHARACTER_PATTERN = /[\u0000-\u001f\u007f-\u009f]/u;
const PACKAGE_PATH_PREFIX = "python/epistemic_foundry/";
const HAS_OPEN_NOFOLLOW =
  process.platform !== "win32" &&
  typeof constants.O_NOFOLLOW === "number" &&
  constants.O_NOFOLLOW !== 0;
const OPEN_NOFOLLOW = HAS_OPEN_NOFOLLOW ? constants.O_NOFOLLOW : 0;
const MAX_VALIDATION_INPUT_BYTES = 8 * 1024 * 1024;
const MAX_VALIDATION_OUTPUT_BYTES = 8 * MAX_VALIDATION_INPUT_BYTES;
const MAX_VALIDATION_TIMEOUT_MS = 30_000;
const CANONICAL_SCHEMA_REF_PATTERN =
  /^https:\/\/epistemic-foundry\.local\/schemas\/([a-z0-9]+(?:-[a-z0-9]+)*)\.schema\.json$/u;
const DOMAIN_ARTIFACT_VALIDATION_MESSAGE =
  "bundled domain artifact validation failed";
const VALIDATION_FAILURE_MESSAGES = Object.freeze({
  [RUNTIME_ERRORS.ARTIFACT_INPUT_INVALID]:
    "artifact validation input is invalid",
  [RUNTIME_ERRORS.ARTIFACT_INPUT_TOO_LARGE]:
    "artifact validation input exceeds the 8 MiB limit",
  [RUNTIME_ERRORS.ARTIFACT_SCHEMA_UNAVAILABLE]:
    "the requested artifact schema is unavailable",
  [RUNTIME_ERRORS.ARTIFACT_VALIDATION_FAILED]:
    "the artifact does not satisfy the requested schema",
  [RUNTIME_ERRORS.BUNDLED_IMPORT_FAILED]:
    "the bundled Python runtime could not be loaded",
  [RUNTIME_ERRORS.BUNDLED_VALIDATION_FAILED]:
    "bundled artifact validation could not be completed",
  [RUNTIME_ERRORS.PYTHON_INTERPRETER_NOT_FOUND]:
    "the configured Python runtime is unavailable",
  [RUNTIME_ERRORS.PYTHON_VERSION_UNSUPPORTED]:
    "the configured Python version is unsupported",
  [RUNTIME_ERRORS.RUNTIME_INTEGRITY_FAILED]: RUNTIME_INTEGRITY_MESSAGE,
});
const PYTHON_VALIDATION_FAILURE_CODES = Object.freeze({
  INPUT_TOO_LARGE: RUNTIME_ERRORS.ARTIFACT_INPUT_TOO_LARGE,
  INVALID_UTF8: RUNTIME_ERRORS.ARTIFACT_INPUT_INVALID,
  INVALID_JSON: RUNTIME_ERRORS.ARTIFACT_INPUT_INVALID,
  ROOT_NOT_OBJECT: RUNTIME_ERRORS.ARTIFACT_INPUT_INVALID,
  SCHEMA_NOT_FOUND: RUNTIME_ERRORS.ARTIFACT_SCHEMA_UNAVAILABLE,
  SCHEMA_VALIDATION_FAILED: RUNTIME_ERRORS.ARTIFACT_VALIDATION_FAILED,
  VALIDATION_INTERNAL_ERROR: RUNTIME_ERRORS.BUNDLED_VALIDATION_FAILED,
});

function validationFailure(errorCode) {
  const selected = Object.hasOwn(VALIDATION_FAILURE_MESSAGES, errorCode)
    ? errorCode
    : RUNTIME_ERRORS.BUNDLED_VALIDATION_FAILED;
  return {
    ok: false,
    error_code: selected,
    message: VALIDATION_FAILURE_MESSAGES[selected],
  };
}

function domainArtifactValidationFailure() {
  const error = new Error(DOMAIN_ARTIFACT_VALIDATION_MESSAGE);
  error.name = "BundledDomainArtifactValidationError";
  error.code = RUNTIME_ERRORS.DOMAIN_ARTIFACT_VALIDATION_FAILED;
  error.stack = `${error.name}: ${error.message}`;
  return error;
}

function runtimeIntegrityFailure() {
  return {
    error_code: RUNTIME_ERRORS.RUNTIME_INTEGRITY_FAILED,
    message: RUNTIME_INTEGRITY_MESSAGE,
    ok: false,
  };
}

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function isCanonicalRuntimePath(value) {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.startsWith("/") ||
    isAbsolute(value) ||
    value.includes("\\") ||
    value.includes(":") ||
    CONTROL_CHARACTER_PATTERN.test(value)
  ) {
    return false;
  }
  const segments = value.split("/");
  return !segments.some(
    (segment) => segment === "" || segment === "." || segment === "..",
  );
}

function isConfinedWithin(root, candidate) {
  const fromRoot = relative(root, candidate);
  return (
    fromRoot !== "" &&
    fromRoot !== ".." &&
    !fromRoot.startsWith(`..${sep}`) &&
    !isAbsolute(fromRoot)
  );
}

function sameStringSet(left, right) {
  if (left.size !== right.size) return false;
  for (const value of left) {
    if (!right.has(value)) return false;
  }
  return true;
}

function isRegularFileSnapshot(snapshot) {
  return !snapshot.isSymbolicLink() && snapshot.isFile();
}

function isDirectorySnapshot(snapshot) {
  return !snapshot.isSymbolicLink() && snapshot.isDirectory();
}

function sameIdentity(left, right) {
  return left.dev === right.dev && left.ino === right.ino;
}

/**
 * Read one manifest-selected regular file through a descriptor.
 *
 * O_NOFOLLOW closes the final-component symlink race on platforms that expose
 * it. The lstat/fstat identity comparison prevents a final-component link from
 * silently selecting a different inode during this observation. This remains
 * a point-in-time installation-drift check, not a same-user immutability claim.
 */
function readStableRegularFile(path) {
  const pathBefore = lstatSync(path, { bigint: true });
  if (!isRegularFileSnapshot(pathBefore)) throw new Error("unsafe runtime file");

  let descriptor;
  try {
    descriptor = openSync(path, constants.O_RDONLY | OPEN_NOFOLLOW);
    const descriptorBefore = fstatSync(descriptor, { bigint: true });
    if (
      !isRegularFileSnapshot(descriptorBefore) ||
      !sameIdentity(pathBefore, descriptorBefore)
    ) {
      throw new Error("runtime file changed before reading");
    }

    const bytes = readFileSync(descriptor);
    if (descriptorBefore.size !== BigInt(bytes.byteLength)) {
      throw new Error("runtime file changed while reading");
    }
    return bytes;
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
  }
}

function enumerateRuntimeTree(runtimeRoot) {
  const directories = new Set();
  const files = new Set();
  const pending = [{ absolute: runtimeRoot, relative: "" }];
  while (pending.length > 0) {
    const current = pending.pop();
    if (!isDirectorySnapshot(lstatSync(current.absolute, { bigint: true }))) {
      return null;
    }
    for (const name of readdirSync(current.absolute)) {
      const childAbsolute = join(current.absolute, name);
      const childRelative =
        current.relative === "" ? name : `${current.relative}/${name}`;
      const childStat = lstatSync(childAbsolute, { bigint: true });
      if (childStat.isSymbolicLink()) return null;
      if (childStat.isDirectory()) {
        directories.add(childRelative);
        pending.push({ absolute: childAbsolute, relative: childRelative });
        continue;
      }
      if (isRegularFileSnapshot(childStat)) {
        files.add(childRelative);
        continue;
      }
      return null;
    }
  }
  return { directories, files };
}

function lstatManifestEntry(runtimeRoot, manifestPath) {
  const segments = manifestPath.split("/");
  let absolute = runtimeRoot;
  for (let index = 0; index < segments.length; index += 1) {
    absolute = join(absolute, segments[index]);
    const entryStat = lstatSync(absolute, { bigint: true });
    if (entryStat.isSymbolicLink()) return null;
    const isFile = index === segments.length - 1;
    if (
      isFile
        ? !isRegularFileSnapshot(entryStat)
        : !isDirectorySnapshot(entryStat)
    ) {
      return null;
    }
  }
  return absolute;
}

function inspectRuntimeManifest(manifest) {
  if (!isPlainObject(manifest)) return null;
  const files = manifest.files;
  if (
    manifest.schema !== RUNTIME_MANIFEST_SCHEMA ||
    manifest.python_requirement !== ">=3.12" ||
    !Array.isArray(files) ||
    !Number.isSafeInteger(manifest.file_count) ||
    manifest.file_count !== files.length ||
    typeof manifest.closure_sha256 !== "string" ||
    !SHA256_PATTERN.test(manifest.closure_sha256)
  ) {
    return null;
  }

  const expectedDirectories = new Set();
  const expectedFiles = new Set(["runtime-manifest.json"]);
  let bootstrapCount = 0;
  let previousPath = null;
  for (const entry of files) {
    if (
      !isPlainObject(entry) ||
      !isCanonicalRuntimePath(entry.path) ||
      typeof entry.sha256 !== "string" ||
      !SHA256_PATTERN.test(entry.sha256) ||
      expectedFiles.has(entry.path) ||
      (previousPath !== null && previousPath >= entry.path)
    ) {
      return null;
    }
    if (entry.path === "bootstrap.py") {
      bootstrapCount += 1;
    } else if (!entry.path.startsWith(PACKAGE_PATH_PREFIX)) {
      return null;
    }

    const segments = entry.path.split("/");
    let directory = "";
    for (const segment of segments.slice(0, -1)) {
      directory = directory === "" ? segment : `${directory}/${segment}`;
      expectedDirectories.add(directory);
    }
    expectedFiles.add(entry.path);
    previousPath = entry.path;
  }
  if (bootstrapCount !== 1) return null;
  return { expectedDirectories, expectedFiles, files };
}

/**
 * Verify the staged runtime against the hashes its manifest recorded.
 *
 * Recording hashes and never checking them proves nothing. This validates the
 * manifest contract, rejects unsafe filesystem entries, reconciles the complete
 * runtime tree, and hashes every recorded regular file through a stable open
 * descriptor. It is a point-in-time integrity observation, not a claim that a
 * later pathname-based Python import is bound to the same bytes.
 *
 * The manifest itself is not self-authenticating; it detects accident and
 * partial installation, not a determined attacker who rewrites both.
 */
export function verifyRuntimeIntegrity(root = pluginRoot()) {
  try {
    const { root: runtimeRoot } = runtimePaths(root);
    const runtimeStat = lstatSync(runtimeRoot, { bigint: true });
    if (!isDirectorySnapshot(runtimeStat)) {
      return runtimeIntegrityFailure();
    }
    const canonicalRuntimeRoot = realpathSync(runtimeRoot);

    const read = readRuntimeManifest(root);
    if (!read.ok) return read;
    const manifest = read.manifest;
    const inspection = inspectRuntimeManifest(manifest);
    if (inspection === null) return runtimeIntegrityFailure();
    const { expectedDirectories, expectedFiles, files } = inspection;

    const actualTree = enumerateRuntimeTree(runtimeRoot);
    if (
      actualTree === null ||
      !sameStringSet(actualTree.files, expectedFiles) ||
      !sameStringSet(actualTree.directories, expectedDirectories)
    ) {
      return runtimeIntegrityFailure();
    }

    const closure = createHash("sha256");
    for (const entry of files) {
      const absolute = lstatManifestEntry(runtimeRoot, entry.path);
      if (absolute === null) return runtimeIntegrityFailure();
      const canonicalEntry = realpathSync(absolute);
      if (!isConfinedWithin(canonicalRuntimeRoot, canonicalEntry)) {
        return runtimeIntegrityFailure();
      }
      const actualHash = createHash("sha256")
        .update(readStableRegularFile(absolute))
        .digest("hex");
      if (realpathSync(absolute) !== canonicalEntry) {
        return runtimeIntegrityFailure();
      }
      if (actualHash !== entry.sha256) return runtimeIntegrityFailure();
      closure.update(entry.path).update("\0").update(entry.sha256).update("\0");
    }
    if (closure.digest("hex") !== manifest.closure_sha256) {
      return runtimeIntegrityFailure();
    }

    return { file_count: files.length, ok: true };
  } catch {
    return runtimeIntegrityFailure();
  }
}

/** Paths that make up the bundled runtime. */
export function runtimePaths(root = pluginRoot()) {
  const runtime = join(root, "runtime");
  return Object.freeze({
    bootstrap: join(runtime, "bootstrap.py"),
    manifest: join(runtime, "runtime-manifest.json"),
    packageRoot: join(runtime, "python"),
    root: runtime,
  });
}

/**
 * Read the recorded manifest for this payload.
 *
 * A missing or unreadable manifest is reported rather than defaulted: the
 * manifest is how a user finds out which bytes the payload records.
 */
export function readRuntimeManifest(root = pluginRoot()) {
  const { manifest, root: runtimeRoot } = runtimePaths(root);
  const payloadRoot = join(root, "dist");
  const payloadManifest = join(payloadRoot, "payload-manifest.json");
  try {
    const runtimeStat = lstatSync(runtimeRoot, { bigint: true });
    const manifestStat = lstatSync(manifest, { bigint: true });
    const payloadRootStat = lstatSync(payloadRoot, { bigint: true });
    const payloadManifestStat = lstatSync(payloadManifest, { bigint: true });
    if (
      !isDirectorySnapshot(runtimeStat) ||
      !isRegularFileSnapshot(manifestStat) ||
      !isDirectorySnapshot(payloadRootStat) ||
      !isRegularFileSnapshot(payloadManifestStat)
    ) {
      return runtimeIntegrityFailure();
    }
    const canonicalRuntimeRoot = realpathSync(runtimeRoot);
    const canonicalManifest = realpathSync(manifest);
    const canonicalPayloadRoot = realpathSync(payloadRoot);
    const canonicalPayloadManifest = realpathSync(payloadManifest);
    if (
      !isConfinedWithin(canonicalRuntimeRoot, canonicalManifest) ||
      !isConfinedWithin(canonicalPayloadRoot, canonicalPayloadManifest)
    ) {
      return runtimeIntegrityFailure();
    }
    const runtimeManifestBytes = readStableRegularFile(manifest);
    const payloadManifestBytes = readStableRegularFile(payloadManifest);
    const parsed = JSON.parse(runtimeManifestBytes.toString("utf8"));
    const parsedPayload = JSON.parse(payloadManifestBytes.toString("utf8"));
    if (
      realpathSync(manifest) !== canonicalManifest ||
      realpathSync(payloadManifest) !== canonicalPayloadManifest
    ) {
      return runtimeIntegrityFailure();
    }
    const expectedRuntimeManifestSha256 = parsedPayload?.runtime_manifest_sha256;
    const actualRuntimeManifestSha256 = `sha256:${createHash("sha256")
      .update(runtimeManifestBytes)
      .digest("hex")}`;
    if (
      !isPlainObject(parsedPayload) ||
      typeof expectedRuntimeManifestSha256 !== "string" ||
      !QUALIFIED_SHA256_PATTERN.test(expectedRuntimeManifestSha256) ||
      expectedRuntimeManifestSha256 !== actualRuntimeManifestSha256 ||
      inspectRuntimeManifest(parsed) === null
    ) {
      return runtimeIntegrityFailure();
    }
    return { manifest: parsed, ok: true };
  } catch {
    return runtimeIntegrityFailure();
  }
}

/**
 * Resolve the sole explicitly configured interpreter for this payload.
 *
 * Python-dependent commands require EFOUNDRY_PYTHON to be an absolute path to
 * a Python 3.12+ executable with the required dependencies. Bare interpreter
 * names are never considered, so resolution cannot search PATH. Interpreter
 * execution is deliberately not used as a separate probe: a requested CLI
 * operation may have at most one Python child. If descriptor-bound execution
 * is issued, the same child lets the bootstrap enforce the Python 3.12+ and
 * dependency contracts before dispatching the requested operation.
 */
export function resolveInterpreter(root = pluginRoot()) {
  const override = process.env.EFOUNDRY_PYTHON;
  if (typeof override !== "string" || override.length === 0) {
    return {
      error_code: RUNTIME_ERRORS.PYTHON_INTERPRETER_NOT_FOUND,
      message: `EFOUNDRY_PYTHON is not set. ${PYTHON_CONFIGURATION_REQUIREMENT}`,
      ok: false,
    };
  }
  if (!isAbsolute(override)) {
    return {
      error_code: RUNTIME_ERRORS.PYTHON_INTERPRETER_NOT_FOUND,
      message:
        `EFOUNDRY_PYTHON is not an absolute path: ${override}. ` +
        PYTHON_CONFIGURATION_REQUIREMENT,
      ok: false,
    };
  }
  let overrideStat;
  try {
    overrideStat = statSync(override);
  } catch {
    return {
      error_code: RUNTIME_ERRORS.PYTHON_INTERPRETER_NOT_FOUND,
      message:
        `EFOUNDRY_PYTHON does not identify an existing regular file: ${override}. ` +
        PYTHON_CONFIGURATION_REQUIREMENT,
      ok: false,
    };
  }
  if (!overrideStat.isFile()) {
    return {
      error_code: RUNTIME_ERRORS.PYTHON_INTERPRETER_NOT_FOUND,
      message:
        `EFOUNDRY_PYTHON does not identify an existing regular file: ${override}. ` +
        PYTHON_CONFIGURATION_REQUIREMENT,
      ok: false,
    };
  }

  // This is the final closed-tree check before the execution decision.
  const integrity = verifyRuntimeIntegrity(root);
  if (!integrity.ok) return integrity;

  // The configured interpreter and installed payload run with the same local
  // user's authority. The manifest check detects damage or drift; it does not
  // claim to defend against that same user rewriting the payload after this
  // point. The Python bootstrap independently confines imports to runtime/python.
  return { args: [], command: override, ok: true };
}

/**
 * Run one requested CLI operation through the plugin-resident bootstrap.
 *
 * Every invocation resolves the configured interpreter and rechecks the
 * staged runtime; callers cannot inject a pre-resolved interpreter object.
 * There is no separate readiness probe. `-I` isolates ambient Python paths,
 * while the bootstrap performs the version/import checks and operation in the
 * same child.
 */
export function runBundledCli(
  args,
  {
    cwd,
    input,
    maxBufferBytes = 64 * 1024 * 1024,
    root = pluginRoot(),
    timeoutMs = 30 * 60_000,
  } = {},
) {
  const { bootstrap } = runtimePaths(root);
  const resolved = resolveInterpreter(root);
  if (!resolved.ok) return resolved;
  const spawnOptions = {
    cwd: cwd ?? process.cwd(),
    encoding: "utf8",
    maxBuffer: maxBufferBytes,
    timeout: timeoutMs,
    windowsHide: true,
  };
  if (input !== undefined) spawnOptions.input = input;
  const result = spawnSync(
    resolved.command,
    [...resolved.args, "-I", "-B", bootstrap, ...args],
    spawnOptions,
  );
  if (result.error) {
    return {
      error_code: RUNTIME_ERRORS.PYTHON_INTERPRETER_NOT_FOUND,
      message: `the runtime could not be started: ${result.error.message}`,
      ok: false,
    };
  }
  return {
    ok: true,
    status: result.status ?? 1,
    stderr: String(result.stderr ?? ""),
    stdout: String(result.stdout ?? ""),
  };
}

/** Request bundled CLI JSON output, preserving any fail-closed runtime error. */
export function runBundledJson(args, options = {}) {
  const run = runBundledCli(["--json", ...args], options);
  if (!run.ok) return run;
  if (run.status === 71) {
    try {
      const failure = JSON.parse(run.stderr.trim());
      const allowedCodes = new Set([
        RUNTIME_ERRORS.BUNDLED_IMPORT_FAILED,
        RUNTIME_ERRORS.PYTHON_VERSION_UNSUPPORTED,
        RUNTIME_ERRORS.RUNTIME_INTEGRITY_FAILED,
      ]);
      if (
        isPlainObject(failure) &&
        failure.status === "BOOTSTRAP_FAILED" &&
        allowedCodes.has(failure.error_code) &&
        typeof failure.message === "string" &&
        failure.message.length > 0
      ) {
        return {
          error_code: failure.error_code,
          exit_status: run.status,
          message: failure.message,
          ok: false,
        };
      }
    } catch {
      // Fall through to the stable malformed-output error below.
    }
  }
  let data;
  try {
    data = JSON.parse(run.stdout);
  } catch {
    return {
      exit_status: run.status,
      error_code: RUNTIME_ERRORS.BUNDLED_IMPORT_FAILED,
      message:
        run.stderr.trim() ||
        "the runtime produced output that is not valid JSON",
      ok: false,
    };
  }
  return { data, ok: true, status: run.status, stderr: run.stderr };
}

/**
 * Validate one bounded artifact through the bundled canonical Python registry.
 *
 * The child command and stdin are fixed here: callers can choose only the
 * schema name, bytes, root/cwd, and a timeout no longer than 30 seconds. Schema
 * semantics remain exclusively in Python's canonical registry.
 */
export function validateBundledArtifact(schemaName, bytes, options = {}) {
  if (
    typeof schemaName !== "string" ||
    schemaName.length === 0 ||
    schemaName.includes("\0") ||
    !Buffer.isBuffer(bytes) ||
    !isPlainObject(options)
  ) {
    return validationFailure(RUNTIME_ERRORS.ARTIFACT_INPUT_INVALID);
  }
  if (bytes.byteLength > MAX_VALIDATION_INPUT_BYTES) {
    return validationFailure(RUNTIME_ERRORS.ARTIFACT_INPUT_TOO_LARGE);
  }

  let cwd;
  let requestedTimeout;
  let root;
  try {
    cwd = options.cwd;
    requestedTimeout = options.timeoutMs ?? MAX_VALIDATION_TIMEOUT_MS;
    root = options.root;
  } catch {
    return validationFailure(RUNTIME_ERRORS.ARTIFACT_INPUT_INVALID);
  }
  if (
    (cwd !== undefined && (typeof cwd !== "string" || cwd.length === 0)) ||
    (root !== undefined && (typeof root !== "string" || root.length === 0))
  ) {
    return validationFailure(RUNTIME_ERRORS.ARTIFACT_INPUT_INVALID);
  }
  if (!Number.isSafeInteger(requestedTimeout) || requestedTimeout <= 0) {
    return validationFailure(RUNTIME_ERRORS.ARTIFACT_INPUT_INVALID);
  }
  const timeoutMs = Math.min(requestedTimeout, MAX_VALIDATION_TIMEOUT_MS);
  let run;
  try {
    run = runBundledCli(["_validate-json-stdin", "--", schemaName], {
      cwd,
      input: Buffer.from(bytes),
      maxBufferBytes: MAX_VALIDATION_OUTPUT_BYTES,
      root: root ?? pluginRoot(),
      timeoutMs,
    });
  } catch {
    return validationFailure(RUNTIME_ERRORS.BUNDLED_VALIDATION_FAILED);
  }
  if (!run.ok) return validationFailure(run.error_code);

  if (run.status === 0) {
    try {
      const data = JSON.parse(run.stdout);
      if (isPlainObject(data)) return { ok: true, data };
    } catch {
      // Fall through to the fixed malformed-output failure below.
    }
    return validationFailure(RUNTIME_ERRORS.BUNDLED_VALIDATION_FAILED);
  }

  if (run.status === 71) {
    try {
      const bootstrapFailure = JSON.parse(run.stderr.trim());
      if (
        isPlainObject(bootstrapFailure) &&
        typeof bootstrapFailure.error_code === "string"
      ) {
        return validationFailure(bootstrapFailure.error_code);
      }
    } catch {
      // Fall through to the fixed redacted failure below.
    }
    return validationFailure(RUNTIME_ERRORS.BUNDLED_VALIDATION_FAILED);
  }

  try {
    const failure = JSON.parse(run.stdout);
    if (
      isPlainObject(failure) &&
      failure.ok === false &&
      typeof failure.error_code === "string" &&
      Object.hasOwn(PYTHON_VALIDATION_FAILURE_CODES, failure.error_code)
    ) {
      return validationFailure(
        PYTHON_VALIDATION_FAILURE_CODES[failure.error_code],
      );
    }
  } catch {
    // Fall through to the fixed redacted failure below.
  }
  return validationFailure(RUNTIME_ERRORS.BUNDLED_VALIDATION_FAILED);
}

/**
 * Validate one store-read-model artifact identified by its canonical schema URL.
 *
 * This adapter intentionally exposes neither the wrapper result nor child/runtime
 * diagnostics. Its error surface is one stable local code and redacted message.
 */
export function validateBundledDomainArtifact(schemaRef, bytes, options = {}) {
  const match =
    typeof schemaRef === "string"
      ? CANONICAL_SCHEMA_REF_PATTERN.exec(schemaRef)
      : null;
  if (match === null || match[0] !== schemaRef) {
    throw domainArtifactValidationFailure();
  }

  let result;
  try {
    result = validateBundledArtifact(match[1], bytes, options);
  } catch {
    throw domainArtifactValidationFailure();
  }
  if (result.ok === true) return result.data;
  throw domainArtifactValidationFailure();
}
