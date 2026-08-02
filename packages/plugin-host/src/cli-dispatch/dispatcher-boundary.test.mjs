import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../..",
);
const dispatcherPath = path.join(
  repositoryRoot,
  "plugins",
  "epistemic-foundry",
  "bin",
  "efoundry.mjs",
);

test("dispatcher_boundary_test: dispatcher is a fixed process adapter without domain logic", () => {
  const source = fs.readFileSync(dispatcherPath, "utf8");
  const imports = [...source.matchAll(/from\s+["']([^"']+)["']/gu)].map(
    (match) => match[1],
  );

  assert.deepEqual(imports, ["node:child_process", "node:url"]);
  assert.match(
    source,
    /fileURLToPath\(new URL\(["']\.\.\/dist\/cli\.mjs["'], import\.meta\.url\)\)/u,
  );
  assert.match(
    source,
    /spawn\(process\.execPath, \[payloadCli, \.\.\.process\.argv\.slice\(2\)\]/u,
  );
  assert.match(source, /cwd: process\.cwd\(\)/u);
  assert.match(source, /env: process\.env/u);
  assert.match(source, /shell: false/u);
  assert.match(source, /stdio: ["']inherit["']/u);

  for (const forbidden of [
    "PLUGIN_ROOT",
    "PLUGIN_DATA",
    "epistemic_foundry",
    "node:fs",
    "node:http",
    "node:https",
    "schemas/",
    "openapi/",
    "Noetic",
    "PolicyBundle",
    "PromotionDecision",
  ]) {
    assert.equal(
      source.includes(forbidden),
      false,
      `dispatcher contains forbidden policy/domain/path token: ${forbidden}`,
    );
  }

  assert.equal(source.length < 1_500, true, "dispatcher stopped being a thin adapter");
});

test("dispatcher_boundary_test: no alternate executable, target, or shell fallback exists", () => {
  const source = fs.readFileSync(dispatcherPath, "utf8");

  assert.equal((source.match(/spawn\(/gu) ?? []).length, 1);
  assert.equal((source.match(/\.\.\/dist\/cli\.mjs/gu) ?? []).length, 1);
  assert.doesNotMatch(source, /process\.env\.[A-Z0-9_]*(?:CLI|PYTHON|ROOT|PATH)/u);
  assert.doesNotMatch(source, /\b(?:exec|execFile|fork|spawnSync)\s*\(/u);
  assert.doesNotMatch(source, /\b(?:cmd(?:\.exe)?|powershell|pwsh|bash|sh|python)\b/iu);
});
