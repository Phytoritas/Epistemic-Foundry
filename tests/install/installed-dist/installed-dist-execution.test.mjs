import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  buildInstalledChildEnvironment,
  installedChildEnvironmentAllowlist,
  runInstalledDistExecutionAutomation,
} from "./installed-dist-harness.mjs";

test("installed child environment source is explicit and repository-free by contract", () => {
  const builderSource = buildInstalledChildEnvironment.toString();
  const harnessSource = fs.readFileSync(
    new URL("./installed-dist-harness.mjs", import.meta.url),
    "utf8",
  );
  const expectedAllowlist = [
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
    ...(process.platform === "win32" ? ["HOMEDRIVE", "HOMEPATH"] : []),
  ].sort();
  assert.doesNotMatch(builderSource, /process\.env/u);
  assert.doesNotMatch(builderSource, /\.\.\./u);
  assert.match(builderSource, /PATH:\s*qualifiedNodeDirectory/u);
  assert.doesNotMatch(builderSource, /PATH:\s*["']["']/u);
  assert.deepEqual([...installedChildEnvironmentAllowlist].sort(), expectedAllowlist);
  for (const forbiddenKey of [
    "GIT_DIR",
    "GIT_WORK_TREE",
    "INIT_CWD",
    "NODE_OPTIONS",
    "NODE_PATH",
    "OLDPWD",
    "PATHEXT",
    "PWD",
    "PYTHON",
    "PYTHONHOME",
    "PYTHONPATH",
    "VIRTUAL_ENV",
  ]) {
    assert.equal(installedChildEnvironmentAllowlist.includes(forbiddenKey), false);
  }
  assert.equal(
    installedChildEnvironmentAllowlist.some((key) => /^npm_/iu.test(key)),
    false,
  );
  assert.equal(
    installedChildEnvironmentAllowlist.some((key) =>
      /(?:^|_)(?:REPO|REPOSITORY|SOURCE|WORKSPACE)(?:_ROOT|_DIR|_PATH)?$/iu.test(key)),
    false,
  );
  assert.match(harnessSource, /const installedEnvironment = buildInstalledChildEnvironment\(/u);
  assert.match(
    harnessSource,
    /function spawnInstalledPayload[\s\S]*?assertRepositoryFreeChildEnvironment\([\s\S]*?permissionArguments\(permissionContext\)[\s\S]*?assertPermissionGuardInvocation\(/u,
  );
  assert.match(harnessSource, /"--permission"/u);
  assert.match(harnessSource, /--allow-fs-read=/u);
  assert.match(harnessSource, /--allow-fs-write=/u);
  assert.doesNotMatch(harnessSource, /--allow-child-process/u);
  assert.match(harnessSource, /repository read canary was not denied/u);
  assert.match(
    harnessSource,
    /const cliResult = spawnInstalledPayload\(process\.execPath/u,
  );
  assert.match(
    harnessSource,
    /const hookResult = spawnInstalledPayload\(plan\.executable/u,
  );
  assert.match(
    harnessSource,
    /function resolveNodeExecutable\(configured, label\)[\s\S]*?normalized === "node"[\s\S]*?normalized === "node\.exe"\) return configured;[\s\S]*?path\.isAbsolute\(configured\)[\s\S]*?fs\.realpathSync\.native\(configured\),\s*qualifiedNodeExecutable,[\s\S]*?return configured;/u,
  );
  assert.doesNotMatch(
    harnessSource,
    /const installedEnvironment\s*=\s*\{\s*\.\.\.(?:process\.env|baseEnvironment|runtimeEnvironment)/u,
  );
  assert.match(
    harnessSource,
    /const executableKey = "EFOUNDRY_INSTALLED_DIST_MCP_EXECUTABLE";[\s\S]*?const executable = process\.env\[executableKey\];/u,
  );
  assert.match(
    harnessSource,
    /\[mcpDriverExecutableEnvironmentKey\]: plan\.executable/u,
  );
  assert.match(
    harnessSource,
    /function runMcpStdioLifecycle[\s\S]*?spawnBounded\(\s*plan\.executable,/u,
  );
  assert.doesNotMatch(
    harnessSource,
    /function runMcpStdioLifecycle[\s\S]*?spawnBounded\(\s*process\.execPath,/u,
  );
  assert.match(
    harnessSource,
    /const child = spawn\(executable, args, \{\s*cwd: process\.cwd\(\),\s*env: childEnvironment,/u,
  );
  assert.doesNotMatch(
    harnessSource,
    /const child = spawn\(process\.execPath, args,/u,
  );
  assert.match(
    harnessSource,
    /if \(process\.execPath !== qualifiedNodeExecutable\)[\s\S]*?process_exec_path: process\.execPath,/u,
  );
  assert.match(
    harnessSource,
    /record\.process_exec_path,\s*qualifiedNodeExecutable,/u,
  );
  assert.match(
    harnessSource,
    /MCP child environment does not match the exact allowlist/u,
  );
  assert.match(
    harnessSource,
    /function runMcpStdioLifecycle[\s\S]*?assertRepositoryFreeChildEnvironment\(environment,[\s\S]*?repositoryFreeEnvironmentAllowlist: mcpDriverEnvironmentAllowlist/u,
  );
});

test(
  "installed_dist_execution_automation: installed bytes run CLI, MCP, and hooks without repository fallback",
  { timeout: 180_000 },
  () => {
    const result = runInstalledDistExecutionAutomation();

    assert.equal(result.gate, "installed_dist_execution_automation");
    assert.match(result.harness_sha256, /^sha256:[0-9a-f]{64}$/u);
    assert.match(result.installed_payload_sha256, /^sha256:[0-9a-f]{64}$/u);
    assert.match(result.installed_dist_sha256, /^sha256:[0-9a-f]{64}$/u);
    assert.equal(result.cli_status_json, "PASS");
    assert.deepEqual(result.mcp, {
      initialize: "PASS",
      tools_list: "PASS",
      foundry_status: "PASS",
    });
    assert.equal(result.hooks.dist_commands_executed > 0, true);
    assert.deepEqual(
      {
        child_process: result.repository_access_enforcement.child_process,
        repository_read: result.repository_access_enforcement.repository_read,
      },
      { child_process: "DENIED", repository_read: "DENIED" },
    );
    assert.equal(result.repository_access_enforcement.guarded_entrypoints.length >= 3, true);
    assert.equal(
      result.invoked_entrypoints.every(
        (entry) => entry.exit?.code === 0 && entry.exit?.signal === null,
      ),
      true,
    );
    assert.equal(result.removal.plugin_data_sentinel, "PRESERVED");
    assert.equal(result.final_status, "PASS");
  },
);
