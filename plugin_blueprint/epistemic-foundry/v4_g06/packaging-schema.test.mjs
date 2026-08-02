// schema_and_type_check — the package reads its vocabulary, it never restates it.
//
// Every set this gate binds has a declaring source: the capability manifest and
// its host-surface and degraded-mode vocabulary come from the canonical manifest
// schema, the discoverable skills from the payload inventory, the CLI commands
// from the sealed tool-surface projection, the authority from the sealed G05
// surface and the hook-event scope from the sealed H05 surface.  A declaring
// source that changes must break this suite rather than leave a manifest
// describing a plugin that no longer exists.  Every artifact the gate emits is
// revalidated against its canonical JSON Schema by an external validator.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { commandSurface } from "../../../packages/plugin-host/src/cli/command-surface.mjs";
import {
  CAPABILITY_MANIFEST_SCHEMA_PATH,
  deriveDiscoverableSkills,
  FINDING_CODES,
  integratePackage,
  loadPackage,
  MANIFEST_PATH,
  REPOSITORY_ROOT,
  SKILL_LOCKFILE_SCHEMA_PATH,
} from "./index.mjs";
import { healthyObservation, sealLockfile } from "./packaging-fixtures.mjs";

const loaded = loadPackage();

test("g06_schema: the discoverable skills are exactly the inventory projection", () => {
  const discoverable = deriveDiscoverableSkills(loaded).map((row) => row.skill_id);

  assert.deepEqual(discoverable, [...loaded.inventorySkillIds]);
});

test("g06_schema: the declared CLI is exactly the sealed tool-surface projection", () => {
  const projected = commandSurface()
    .map((row) => row.command)
    .sort();

  assert.deepEqual([...loaded.manifest.cliCommands], projected);
});

test("g06_schema: the host surfaces are within the manifest schema vocabulary", () => {
  for (const surface of loaded.manifest.hostSurfaces) {
    assert.ok(loaded.vocabulary.hostSurfaces.includes(surface), surface);
  }
});

test("g06_schema: every declared capability is snake_case and disjoint by role", () => {
  const required = new Set(loaded.manifest.requiredCapabilities);
  for (const capability of loaded.manifest.optionalCapabilities) {
    assert.ok(!required.has(capability), capability);
    assert.match(capability, /^[a-z][a-z0-9_]*$/u);
  }
  for (const capability of loaded.manifest.requiredCapabilities) {
    assert.match(capability, /^[a-z][a-z0-9_]*$/u);
  }
});

test("g06_schema: every finding code carries a code and a reason", () => {
  assert.equal(Object.keys(FINDING_CODES).length, 19);
  for (const [code, reason] of Object.entries(FINDING_CODES)) {
    assert.equal(code, code.toUpperCase());
    assert.ok(reason.length > 50, code);
  }
});

test("g06_schema: the emitted artifacts validate against their canonical schemas", (t) => {
  const { report, health } = integratePackage(loaded, healthyObservation(loaded));
  const lockfile = sealLockfile();

  const temporaryRoot = mkdtempSync(join(tmpdir(), "ef-g06-schema-"));
  t.after(() => rmSync(temporaryRoot, { force: true, recursive: true }));
  const write = (name, value) => {
    const path = join(temporaryRoot, name);
    writeFileSync(path, JSON.stringify(value), "utf8");
    return path;
  };
  const reportPath = write("host-capability-report.json", report);
  const healthPath = write("plugin-health-report.json", health);
  const lockfilePath = write("skill-lockfile.json", lockfile);

  const pairs = [
    [join(REPOSITORY_ROOT, CAPABILITY_MANIFEST_SCHEMA_PATH), join(REPOSITORY_ROOT, MANIFEST_PATH)],
    [join(REPOSITORY_ROOT, SKILL_LOCKFILE_SCHEMA_PATH), lockfilePath],
    [join(REPOSITORY_ROOT, "schemas/host-capability-report.schema.json"), reportPath],
    [join(REPOSITORY_ROOT, "schemas/plugin-health-report.schema.json"), healthPath],
  ];

  const script = `
import json
import pathlib
import sys
from jsonschema import Draft202012Validator, FormatChecker

args = sys.argv[1:]
pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]
for schema_path, instance_path in pairs:
    schema = json.loads(pathlib.Path(schema_path).read_text(encoding="utf-8"))
    instance = json.loads(pathlib.Path(instance_path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance))
    if errors:
        raise SystemExit(f"{pathlib.Path(instance_path).name}: " + "; ".join(e.message for e in errors))
print("all instances valid")
`;
  const result = spawnSync("uv", ["run", "--locked", "python", "-", ...pairs.flat()], {
    cwd: REPOSITORY_ROOT,
    encoding: "utf8",
    input: script,
  });

  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  assert.equal(result.stdout.trim(), "all instances valid");
});
