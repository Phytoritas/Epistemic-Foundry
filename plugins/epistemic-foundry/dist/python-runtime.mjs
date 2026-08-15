// Locating and running the plugin-resident Python runtime.
//
// The plugin ships its own copy of the application package and needs only an
// interpreter from the host.  Nothing here resolves `efoundry` from PATH: a
// globally installed executable would be a different, unversioned copy of the
// application, and the whole point of the bundled runtime is that the bytes
// which run are the bytes this release recorded.
//
// Every failure is a named code plus a human sentence.  A caller that cannot
// distinguish "no interpreter" from "interpreter too old" cannot tell the user
// what to do about it.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** Where the payload lives, derived from this file rather than the cwd. */
export function pluginRoot(fromUrl = import.meta.url) {
  // <plugin-root>/{src,dist}/python-runtime.mjs -> <plugin-root>
  return dirname(dirname(fileURLToPath(fromUrl)));
}

/** Interpreters to try, in order, when EFOUNDRY_PYTHON is unset. */
const CANDIDATES = Object.freeze(
  process.platform === "win32"
    ? [
        { args: ["-3"], command: "py" },
        { args: [], command: "python" },
        { args: [], command: "python3" },
      ]
    : [
        { args: [], command: "python3" },
        { args: [], command: "python" },
      ],
);

/** Named failures a caller can branch on. */
export const RUNTIME_ERRORS = Object.freeze({
  BUNDLED_IMPORT_FAILED: "BUNDLED_IMPORT_FAILED",
  PYTHON_INTERPRETER_NOT_FOUND: "PYTHON_INTERPRETER_NOT_FOUND",
  PYTHON_VERSION_UNSUPPORTED: "PYTHON_VERSION_UNSUPPORTED",
  RUNTIME_INTEGRITY_FAILED: "RUNTIME_INTEGRITY_FAILED",
});

/**
 * Verify the staged runtime against the hashes its manifest recorded.
 *
 * Recording hashes and never checking them proves nothing: the payload would
 * report a closure it is not necessarily running.  This walks the recorded
 * file list, so a replaced, truncated, or missing file is caught before the
 * interpreter is handed any of it.
 *
 * The manifest itself is not self-authenticating; it detects accident and
 * partial installation, not a determined attacker who rewrites both.
 */
export function verifyRuntimeIntegrity(root = pluginRoot()) {
  const read = readRuntimeManifest(root);
  if (!read.ok) return read;
  const files = read.manifest.files;
  if (!Array.isArray(files) || files.length === 0) {
    return {
      error_code: RUNTIME_ERRORS.RUNTIME_INTEGRITY_FAILED,
      message: "the runtime manifest records no files",
      ok: false,
    };
  }
  const { root: runtimeRoot } = runtimePaths(root);
  const closure = createHash("sha256");
  const damaged = [];
  for (const entry of files) {
    const relative = String(entry?.path ?? "");
    const expected = String(entry?.sha256 ?? "");
    if (relative === "" || expected === "") {
      return {
        error_code: RUNTIME_ERRORS.RUNTIME_INTEGRITY_FAILED,
        message: "the runtime manifest contains a malformed file entry",
        ok: false,
      };
    }
    let actual;
    try {
      actual = createHash("sha256")
        .update(readFileSync(join(runtimeRoot, relative)))
        .digest("hex");
    } catch {
      damaged.push(`${relative}: missing`);
      if (damaged.length >= 5) break;
      continue;
    }
    if (actual !== expected) {
      damaged.push(`${relative}: content differs`);
      if (damaged.length >= 5) break;
    }
    closure.update(relative).update("\0").update(expected).update("\0");
  }
  if (damaged.length > 0) {
    return {
      error_code: RUNTIME_ERRORS.RUNTIME_INTEGRITY_FAILED,
      message: `the bundled runtime does not match its manifest: ${damaged.join("; ")}`,
      ok: false,
    };
  }
  const recorded = String(read.manifest.closure_sha256 ?? "");
  const computed = closure.digest("hex");
  if (recorded !== computed) {
    return {
      error_code: RUNTIME_ERRORS.RUNTIME_INTEGRITY_FAILED,
      message: "the runtime manifest closure hash does not match its own file list",
      ok: false,
    };
  }
  return { file_count: files.length, ok: true };
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
 * manifest is how a user finds out which bytes they are running.
 */
export function readRuntimeManifest(root = pluginRoot()) {
  const { manifest } = runtimePaths(root);
  if (!existsSync(manifest)) {
    return {
      error_code: RUNTIME_ERRORS.RUNTIME_INTEGRITY_FAILED,
      message: `the runtime manifest is missing at ${manifest}`,
      ok: false,
    };
  }
  try {
    return { manifest: JSON.parse(readFileSync(manifest, "utf8")), ok: true };
  } catch (cause) {
    return {
      error_code: RUNTIME_ERRORS.RUNTIME_INTEGRITY_FAILED,
      message: `the runtime manifest is unreadable: ${cause.message}`,
      ok: false,
    };
  }
}

function probeInterpreter(command, baseArgs, bootstrap) {
  let result;
  try {
    result = spawnSync(command, [...baseArgs, "-I", bootstrap, "--json", "status"], {
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
      timeout: 60_000,
      windowsHide: true,
    });
  } catch (cause) {
    return { ok: false, reason: cause.message };
  }
  if (result.error) {
    return { ok: false, reason: result.error.code ?? result.error.message };
  }
  if (result.status === 0) {
    return { ok: true };
  }
  // The bootstrap reports its own typed failures as JSON on stderr, so a
  // version or import problem is distinguishable from "this name is not an
  // interpreter at all".
  const stderr = String(result.stderr ?? "");
  for (const line of stderr.split(/\r?\n/)) {
    if (!line.trim().startsWith("{")) continue;
    try {
      const payload = JSON.parse(line);
      if (typeof payload.error_code === "string") {
        return {
          errorCode: payload.error_code,
          ok: false,
          reason: String(payload.message ?? payload.error_code),
        };
      }
    } catch {
      // Not the bootstrap's structured line; keep looking.
    }
  }
  return { ok: false, reason: `exited with status ${result.status}` };
}

/**
 * Find an interpreter that can actually run this payload.
 *
 * Candidates are probed by running the bootstrap, not by checking that a name
 * exists.  On Windows especially, `python` is frequently a store stub that
 * resolves and then refuses to run, so existence proves nothing.
 */
export function resolveInterpreter(root = pluginRoot()) {
  const { bootstrap, packageRoot } = runtimePaths(root);
  if (!existsSync(bootstrap) || !existsSync(packageRoot)) {
    return {
      error_code: RUNTIME_ERRORS.RUNTIME_INTEGRITY_FAILED,
      message:
        "the bundled Python runtime is missing; this payload was not built " +
        `(expected ${bootstrap})`,
      ok: false,
    };
  }

  // Integrity is checked before any of these bytes are executed, not after.
  const integrity = verifyRuntimeIntegrity(root);
  if (!integrity.ok) return integrity;

  const override = process.env.EFOUNDRY_PYTHON;
  const candidates =
    typeof override === "string" && override.length > 0
      ? [{ args: [], command: override }]
      : CANDIDATES;

  const attempts = [];
  const explicitOverride = typeof override === "string" && override.length > 0;
  for (const candidate of candidates) {
    const probe = probeInterpreter(candidate.command, candidate.args, bootstrap);
    if (probe.ok) {
      return { args: candidate.args, command: candidate.command, ok: true };
    }
    attempts.push(`${candidate.command}: ${probe.reason}`);
    // An interpreter the user named explicitly is a terminal answer: silently
    // running a different one would defeat the point of naming it.  A probed
    // candidate is not, because a machine can easily have an old `py` launcher
    // and a current `python`; stopping at the first would strand that user.
    if (explicitOverride) {
      return {
        error_code: probe.errorCode ?? RUNTIME_ERRORS.PYTHON_INTERPRETER_NOT_FOUND,
        message: `${candidate.command} cannot run the bundled runtime: ${probe.reason}`,
        ok: false,
      };
    }
  }
  return {
    error_code: RUNTIME_ERRORS.PYTHON_INTERPRETER_NOT_FOUND,
    message:
      "no usable Python interpreter was found. Install Python 3.11+ with " +
      "jsonschema and PyYAML, or set EFOUNDRY_PYTHON to its full path. " +
      `Tried: ${attempts.join("; ")}`,
    ok: false,
  };
}

/**
 * Run the bundled CLI once and capture its output.
 *
 * `-I` keeps the child from picking up ambient `PYTHONPATH`, user site
 * packages, or a different installed copy of the application.
 */
export function runBundledCli(args, { cwd, root = pluginRoot(), interpreter } = {}) {
  const resolved = interpreter ?? resolveInterpreter(root);
  if (!resolved.ok) return resolved;
  const { bootstrap } = runtimePaths(root);
  const result = spawnSync(
    resolved.command,
    [...resolved.args, "-I", bootstrap, ...args],
    {
      cwd: cwd ?? process.cwd(),
      encoding: "utf8",
      maxBuffer: 64 * 1024 * 1024,
      timeout: 30 * 60_000,
      windowsHide: true,
    },
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

/** Run the bundled CLI and parse its `--json` output. */
export function runBundledJson(args, options = {}) {
  const run = runBundledCli(["--json", ...args], options);
  if (!run.ok) return run;
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
