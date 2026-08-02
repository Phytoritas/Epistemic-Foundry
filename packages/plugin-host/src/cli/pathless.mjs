// PATH-less process surfaces.
//
// The CLI never resolves an executable by name.  Every child process is the
// running Node binary at `process.execPath` running an absolute script path,
// with `shell: false` and an environment built from a declared allowlist rather
// than inherited wholesale.  That removes the whole class of failures where the
// tool a command runs depends on what happens to be first on PATH.

import { isAbsolute } from "node:path";

import { CliContractError } from "./error-codes.mjs";

/** Environment variables a child may inherit. PATH is deliberately absent. */
export const INHERITABLE_ENV_KEYS = Object.freeze([
  "EFOUNDRY_WORKSPACE_ID",
  "HOME",
  "LANG",
  "LC_ALL",
  "TMPDIR",
  "USERPROFILE",
]);
/** Variables that would reintroduce ambient lookup and are always stripped. */
export const STRIPPED_ENV_KEYS = Object.freeze([
  "NODE_OPTIONS",
  "NODE_PATH",
  "PATH",
  "PATHEXT",
  "PYTHONPATH",
  "Path",
]);

/** Source patterns that would reintroduce a PATH lookup. */
const FORBIDDEN_SOURCE_PATTERNS = Object.freeze([
  { name: "shell_true", pattern: /shell\s*:\s*true/u },
  { name: "exec_by_string", pattern: /\bexec(?:Sync)?\s*\(/u },
  { name: "env_path_read", pattern: /process\.env\.(?:PATH|Path|PATHEXT)\b/u },
  { name: "env_path_index", pattern: /process\.env\[\s*["'](?:PATH|Path|PATHEXT)["']/u },
  { name: "bare_interpreter", pattern: /["'](?:node|python3?|sh|bash|pwsh|cmd)["']/u },
]);

/** The only executable this CLI ever launches. */
export function resolveExecutable() {
  return process.execPath;
}

/**
 * Build a child environment from the allowlist.
 *
 * Anything not named is dropped, so a variable added to the parent environment
 * later cannot silently change a child's behaviour.
 */
export function childEnvironment(parentEnv = process.env, overrides = {}) {
  const child = {};
  for (const key of INHERITABLE_ENV_KEYS) {
    const value = parentEnv?.[key];
    if (typeof value === "string") {
      child[key] = value;
    }
  }
  for (const [key, value] of Object.entries(overrides)) {
    if (STRIPPED_ENV_KEYS.includes(key)) {
      throw new CliContractError(
        "ENV_KEY_FORBIDDEN",
        `${key} would reintroduce ambient executable lookup`,
        { key },
      );
    }
    if (typeof value !== "string") {
      throw new CliContractError(
        "ENV_VALUE_INVALID",
        `${key} must be a string`,
        { key },
      );
    }
    child[key] = value;
  }
  return child;
}

/**
 * Spawn options for one PATH-less child run.
 *
 * The script must already be an absolute path: accepting a relative one would
 * make the result depend on the caller's working directory, which is the same
 * ambient-resolution problem PATH creates.
 */
export function spawnPlan(scriptPath, args = [], { cwd, env } = {}) {
  if (typeof scriptPath !== "string" || !isAbsolute(scriptPath)) {
    throw new CliContractError(
      "SCRIPT_PATH_NOT_ABSOLUTE",
      "a child script must be named by an absolute path",
      { script_path: scriptPath ?? null },
    );
  }
  if (!Array.isArray(args) || args.some((entry) => typeof entry !== "string")) {
    throw new CliContractError(
      "ARGUMENTS_INVALID",
      "child arguments must be an array of strings",
    );
  }
  if (cwd !== undefined && (typeof cwd !== "string" || !isAbsolute(cwd))) {
    throw new CliContractError(
      "CWD_NOT_ABSOLUTE",
      "a child working directory must be an absolute path",
    );
  }
  return Object.freeze({
    args: Object.freeze([scriptPath, ...args]),
    executable: resolveExecutable(),
    options: Object.freeze({
      cwd: cwd ?? process.cwd(),
      env: childEnvironment(process.env, env ?? {}),
      shell: false,
      windowsHide: true,
    }),
  });
}

/**
 * Every way a source file would reintroduce ambient lookup.
 *
 * Returned rather than thrown so a caller can report all of them at once; the
 * assertion helper turns a non-empty result into a failure.
 */
export function pathlessViolations(source) {
  if (typeof source !== "string") {
    throw new CliContractError("INPUT_INVALID", "source must be a string");
  }
  return FORBIDDEN_SOURCE_PATTERNS.filter(({ pattern }) => pattern.test(source))
    .map(({ name }) => name)
    .sort();
}

/** Refuse a source file that could resolve an executable from the environment. */
export function assertPathless(source, label = "source") {
  const violations = pathlessViolations(source);
  if (violations.length > 0) {
    throw new CliContractError(
      "PATH_LOOKUP_PRESENT",
      `${label} would resolve an executable from the environment`,
      { violations },
    );
  }
}
