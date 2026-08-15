// pathless_cli_test — the CLI never resolves an executable from the environment.
//
// Exit criterion under test: PATH-less surfaces.  Every child is the running
// Node binary at an absolute script path with `shell: false`, the child
// environment is built from an allowlist that excludes PATH, and the CLI's own
// sources are scanned so a future edit cannot quietly reintroduce a lookup.

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, isAbsolute, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  INHERITABLE_ENV_KEYS,
  STRIPPED_ENV_KEYS,
  assertPathless,
  childEnvironment,
  pathlessViolations,
  resolveExecutable,
  spawnPlan,
} from "./pathless.mjs";
import { CliContractError } from "./error-codes.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPOSITORY_ROOT = join(HERE, "..", "..", "..", "..");
const CLI_SOURCES = readdirSync(HERE)
  .filter((name) => name.endsWith(".mjs") && !name.endsWith(".test.mjs"))
  .sort();

test("pathless_cli_test: the only executable is the running Node binary", () => {
  assert.equal(resolveExecutable(), process.execPath);
  assert.equal(isAbsolute(resolveExecutable()), true);
});

test("pathless_cli_test: PATH is not on the inheritable allowlist", () => {
  for (const key of ["PATH", "Path", "PATHEXT", "NODE_OPTIONS", "NODE_PATH"]) {
    assert.equal(INHERITABLE_ENV_KEYS.includes(key), false, key);
    assert.equal(STRIPPED_ENV_KEYS.includes(key), true, key);
  }
});

test("pathless_cli_test: the child environment carries only allowlisted keys", () => {
  const parent = {
    EFOUNDRY_WORKSPACE_ID: "ws-1",
    HOME: "/home/user",
    NODE_OPTIONS: "--inspect",
    PATH: "/usr/local/bin:/usr/bin",
    SECRET_TOKEN: "hunter2",
  };

  const child = childEnvironment(parent);

  assert.deepEqual(Object.keys(child).sort(), ["EFOUNDRY_WORKSPACE_ID", "HOME"]);
  assert.equal("PATH" in child, false);
  assert.equal("SECRET_TOKEN" in child, false);
});

test("pathless_cli_test: an unset allowlisted key is simply absent", () => {
  const child = childEnvironment({ HOME: "/home/user" });

  assert.deepEqual(Object.keys(child), ["HOME"]);
});

test("pathless_cli_test: an override cannot smuggle PATH back in", () => {
  for (const key of STRIPPED_ENV_KEYS) {
    assert.throws(
      () => childEnvironment({}, { [key]: "/tmp/evil" }),
      (error) => error instanceof CliContractError && error.code === "ENV_KEY_FORBIDDEN",
      key,
    );
  }
});

test("pathless_cli_test: Windows-style case variants cannot smuggle lookup variables back in", () => {
  for (const key of ["path", "pAtHeXt", "node_options", "Node_Path", "pythonpath"]) {
    assert.throws(
      () => childEnvironment({}, { [key]: "/tmp/evil" }),
      (error) => error instanceof CliContractError && error.code === "ENV_KEY_FORBIDDEN",
      key,
    );
  }
});

test("pathless_cli_test: an override must be a string", () => {
  assert.throws(
    () => childEnvironment({}, { EFOUNDRY_RUN: 7 }),
    (error) => error instanceof CliContractError && error.code === "ENV_VALUE_INVALID",
  );
});

test("pathless_cli_test: a spawn plan names an absolute script and disables the shell", () => {
  const script = join(REPOSITORY_ROOT, "packages", "plugin-host", "src", "cli", "x.mjs");

  const plan = spawnPlan(script, ["status", "--json"], { cwd: REPOSITORY_ROOT });

  assert.equal(plan.executable, process.execPath);
  assert.deepEqual([...plan.args], [script, "status", "--json"]);
  assert.equal(plan.options.shell, false);
  assert.equal(plan.options.windowsHide, true);
  assert.equal(plan.options.cwd, REPOSITORY_ROOT);
  assert.equal("PATH" in plan.options.env, false);
});

test("pathless_cli_test: a relative script path is refused", () => {
  assert.throws(
    () => spawnPlan("./cli.mjs"),
    (error) =>
      error instanceof CliContractError && error.code === "SCRIPT_PATH_NOT_ABSOLUTE",
  );
  assert.throws(
    () => spawnPlan("cli.mjs"),
    (error) =>
      error instanceof CliContractError && error.code === "SCRIPT_PATH_NOT_ABSOLUTE",
  );
});

test("pathless_cli_test: a relative working directory is refused", () => {
  const script = join(REPOSITORY_ROOT, "cli.mjs");

  assert.throws(
    () => spawnPlan(script, [], { cwd: "subdir" }),
    (error) => error instanceof CliContractError && error.code === "CWD_NOT_ABSOLUTE",
  );
});

test("pathless_cli_test: non-string arguments are refused", () => {
  const script = join(REPOSITORY_ROOT, "cli.mjs");

  assert.throws(
    () => spawnPlan(script, ["ok", 7]),
    (error) => error instanceof CliContractError && error.code === "ARGUMENTS_INVALID",
  );
});

test("pathless_cli_test: the plan is frozen so a caller cannot re-enable the shell", () => {
  const plan = spawnPlan(join(REPOSITORY_ROOT, "cli.mjs"));

  assert.throws(() => {
    "use strict";
    plan.options.shell = true;
  }, TypeError);
  assert.equal(plan.options.shell, false);

  assert.throws(() => {
    "use strict";
    plan.options.env.PATH = "/tmp/evil";
  }, TypeError);
  assert.equal("PATH" in plan.options.env, false);
});

test("pathless_cli_test: the source scanner names every lookup it finds", () => {
  assert.deepEqual(pathlessViolations("spawn(cmd, args, { shell: true })"), [
    "shell_true",
  ]);
  assert.deepEqual(pathlessViolations('const p = process.env.PATH;'), [
    "env_path_read",
  ]);
  assert.deepEqual(pathlessViolations('process.env["PATH"]'), ["env_path_index"]);
  assert.deepEqual(pathlessViolations('spawn("node", [script])'), ["bare_interpreter"]);
  assert.deepEqual(pathlessViolations("exec(`ls ${dir}`)"), ["exec_by_string"]);
  assert.deepEqual(pathlessViolations("spawn(process.execPath, [script])"), []);
});

test("pathless_cli_test: several violations are reported together", () => {
  const source = 'exec("ls"); spawn("bash", [], { shell: true });';

  assert.deepEqual(pathlessViolations(source), [
    "bare_interpreter",
    "exec_by_string",
    "shell_true",
  ]);
});

test("pathless_cli_test: assertPathless refuses a source that would look up an executable", () => {
  assert.throws(
    () => assertPathless('spawn("python", [])', "candidate"),
    (error) =>
      error instanceof CliContractError &&
      error.code === "PATH_LOOKUP_PRESENT" &&
      error.context.violations.includes("bare_interpreter"),
  );
});

test("pathless_cli_test: every CLI source is itself PATH-less", () => {
  assert.equal(CLI_SOURCES.length >= 4, true, "the CLI surface lost its modules");

  for (const name of CLI_SOURCES) {
    const source = readFileSync(join(HERE, name), "utf8");
    assert.deepEqual(pathlessViolations(source), [], name);
  }
});

test("pathless_cli_test: the shipped dispatcher is PATH-less too", () => {
  const dispatcher = join(
    REPOSITORY_ROOT,
    "plugins",
    "epistemic-foundry",
    "bin",
    "efoundry.mjs",
  );

  const source = readFileSync(dispatcher, "utf8");

  assert.deepEqual(pathlessViolations(source), []);
  assert.match(source, /new URL\(["']\.\.\/dist\/cli\.mjs["'], import\.meta\.url\)/u);
  assert.match(source, /await import\(payloadCli\.href\)/u);
  assert.doesNotMatch(source, /\b(?:spawn|exec|execFile|fork)\s*\(/u);
});
