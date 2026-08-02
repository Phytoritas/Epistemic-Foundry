// schema_and_type_check — H05 reads its vocabulary, it never restates it.
//
// Every set this surface binds has a declaring source: hosts, event types,
// decisions and coverage dispositions come from the sealed hook gateway, the
// evolution event surface from the plugin's own evolution and holdout hook
// bundles, and the holdout material an observer may never touch from the sealed
// holdout-manifest schema.  A declaring source that changes must break this
// suite rather than leave a registration describing hooks that cannot exist.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  HOOK_COVERAGE,
  HOOK_DECISIONS,
  HOOK_EVENT_TYPES,
  HOOK_HOSTS,
} from "../../../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  coverageReport,
  DECLARING_SOURCES,
  deriveEvolutionEventTypes,
  deriveHoldoutIsolation,
  deriveRunnerCommandPrefix,
  EVOLUTION_BUNDLE_PATH,
  FINDING_CODES,
  HOLDOUT_BUNDLE_PATH,
  HOLDOUT_MANIFEST_SCHEMA_PATH,
  HOOK_EVENT_ENVELOPE_SCHEMA_PATH,
  loadObservability,
  observeEvolutionEvent,
  REGISTRATIONS_PATH,
  REPOSITORY_ROOT,
} from "./index.mjs";
import { CLEAN_PAYLOAD, OBSERVATION_TEMPLATE } from "./observability-fixtures.mjs";

const loaded = loadObservability();
const readRepo = (relative) => readFileSync(join(REPOSITORY_ROOT, relative), "utf8");
const readRepoJson = (relative) => JSON.parse(readRepo(relative));

test("h05_schema: every declared host is one the sealed gateway declares", () => {
  assert.deepEqual([...loaded.observedHosts], ["claude", "codex"]);
  for (const host of loaded.observedHosts) assert.ok(HOOK_HOSTS.includes(host), host);
  for (const registration of loaded.declaration.registrations) {
    for (const host of registration.hosts) assert.ok(HOOK_HOSTS.includes(host), host);
  }
});

test("h05_schema: every declared event type is one the sealed gateway declares", () => {
  for (const registration of loaded.declaration.registrations) {
    for (const eventType of registration.event_types) {
      assert.ok(HOOK_EVENT_TYPES.includes(eventType), eventType);
    }
  }
});

test("h05_schema: the evolution event surface is derived from the plugin's own bundles", () => {
  const derived = deriveEvolutionEventTypes([
    [EVOLUTION_BUNDLE_PATH, readRepoJson(EVOLUTION_BUNDLE_PATH)],
    [HOLDOUT_BUNDLE_PATH, readRepoJson(HOLDOUT_BUNDLE_PATH)],
  ]);

  assert.deepEqual([...loaded.evolutionEventTypes], [...derived]);
  assert.deepEqual([...derived], ["PostToolUse", "PreToolUse", "Stop"]);
});

test("h05_schema: no registration observes an event type outside that surface", () => {
  for (const registration of loaded.declaration.registrations) {
    for (const eventType of registration.event_types) {
      assert.ok(loaded.evolutionEventTypes.includes(eventType), eventType);
    }
  }
});

test("h05_schema: every declared coverage disposition is gateway vocabulary", () => {
  for (const registration of loaded.declaration.registrations) {
    assert.ok(HOOK_COVERAGE.includes(registration.coverage), registration.registration_id);
  }
  assert.deepEqual(Object.keys(loaded.declaration.coverage_rank).sort(), [...HOOK_COVERAGE].sort());
});

test("h05_schema: the decision sets partition the gateway decision vocabulary", () => {
  const observer = [...loaded.decisions.observer];
  const control = [...loaded.decisions.control];

  assert.deepEqual([...observer, ...control].sort(), [...HOOK_DECISIONS].sort());
  assert.equal(observer.some((entry) => control.includes(entry)), false);
  assert.deepEqual(control.sort(), ["ALLOW", "BLOCK", "REWRITE"]);
});

test("h05_schema: no registration emits a control-bearing decision", () => {
  for (const registration of loaded.declaration.registrations) {
    assert.ok(loaded.decisions.observer.has(registration.emits_decision));
    assert.equal(loaded.decisions.control.has(registration.emits_decision), false);
  }
});

test("h05_schema: the holdout isolation set is derived from the sealed schema", () => {
  const derived = deriveHoldoutIsolation(readRepoJson(HOLDOUT_MANIFEST_SCHEMA_PATH));

  assert.deepEqual(
    [...derived.deniedAccessFlags],
    ["backend_access", "candidate_access", "mutation_model_access", "prompt_access"],
  );
  assert.deepEqual(
    [...derived.isolatedPartitions],
    ["adversarial_partition_handles", "hidden_partition_handles", "ood_partition_handles"],
  );
  assert.equal(derived.isolatedFields.includes("public_partition_refs"), false);
  assert.deepEqual([...loaded.holdout.isolatedFields], [...derived.isolatedFields]);
});

test("h05_schema: every declared access flag is pinned closed by the sealed schema", () => {
  const properties = readRepoJson(HOLDOUT_MANIFEST_SCHEMA_PATH).properties;

  for (const flag of loaded.holdout.deniedAccessFlags) {
    assert.equal(properties[flag].const, false, flag);
  }
});

test("h05_schema: every requested payload field is declared and none is holdout-flagged", () => {
  for (const registration of loaded.declaration.registrations) {
    for (const field of registration.payload_access) {
      assert.ok(loaded.holdout.declaredFields.includes(field), field);
      assert.equal(loaded.holdout.isolatedFields.includes(field), false, field);
    }
  }
});

test("h05_schema: the registration set declares exactly the fields the loader requires", () => {
  assert.deepEqual(Object.keys(loaded.declaration).sort(), [
    "control_decisions",
    "coverage_rank",
    "observed_hosts",
    "observer_decisions",
    "registration_set_id",
    "registration_set_version",
    "registrations",
  ]);
  for (const registration of loaded.declaration.registrations) {
    assert.deepEqual(Object.keys(registration).sort(), [
      "coverage",
      "emits_decision",
      "event_types",
      "hosts",
      "matcher",
      "payload_access",
      "registration_id",
      "runner_argument",
      "status_message",
      "timeout_seconds",
    ]);
  }
});

test("h05_schema: the runner command prefix is derived from the bundle that uses it", () => {
  const prefix = deriveRunnerCommandPrefix(
    readRepoJson(EVOLUTION_BUNDLE_PATH),
    EVOLUTION_BUNDLE_PATH,
  );

  assert.equal(loaded.commandPrefix, prefix);
  assert.ok(prefix.includes("hook-runner.mjs"), prefix);
});

test("h05_schema: every finding code carries a code and a reason", () => {
  assert.equal(Object.keys(FINDING_CODES).length, 19);
  for (const [code, reason] of Object.entries(FINDING_CODES)) {
    assert.equal(code, code.toUpperCase());
    assert.ok(reason.length > 50, code);
  }
});

test("h05_schema: the declaring sources are exactly the files this module reads", () => {
  assert.deepEqual(
    [...DECLARING_SOURCES].sort(),
    [
      EVOLUTION_BUNDLE_PATH,
      HOLDOUT_BUNDLE_PATH,
      HOLDOUT_MANIFEST_SCHEMA_PATH,
      HOOK_EVENT_ENVELOPE_SCHEMA_PATH,
      REGISTRATIONS_PATH,
    ].sort(),
  );
  for (const path of DECLARING_SOURCES) assert.ok(readRepo(path).length > 0, path);
});

test("h05_schema: the coverage report names every gateway host and event type", () => {
  const report = coverageReport(loaded);

  assert.equal(report.declared_host_count, HOOK_HOSTS.length);
  assert.equal(report.declared_event_type_count, HOOK_EVENT_TYPES.length);
  assert.deepEqual(
    report.event_types.map((row) => row.event_type).sort(),
    [...HOOK_EVENT_TYPES].sort(),
  );
  for (const row of report.event_types) {
    assert.ok(HOOK_COVERAGE.includes(row.coverage), row.event_type);
    assert.equal(row.hosts_observed.length + row.hosts_unobserved.length, HOOK_HOSTS.length);
  }
});

test("h05_schema: an emitted observation validates against the canonical envelope schema", async (t) => {
  const envelope = await observeEvolutionEvent(loaded, {
    ...OBSERVATION_TEMPLATE,
    payload: CLEAN_PAYLOAD,
  });
  const temporaryRoot = mkdtempSync(join(tmpdir(), "ef-h05-schema-"));
  t.after(() => rmSync(temporaryRoot, { force: true, recursive: true }));
  const instancePath = join(temporaryRoot, "hook-event-envelope.json");
  writeFileSync(instancePath, JSON.stringify(envelope), "utf8");
  const script = `
import json
import pathlib
import sys
from jsonschema import Draft202012Validator, FormatChecker

schema = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
instance = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
Draft202012Validator.check_schema(schema)
errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance))
if errors:
    raise SystemExit("; ".join(error.message for error in errors))
print("HookEventEnvelope valid")
`;
  const result = spawnSync(
    "uv",
    [
      "run",
      "--locked",
      "python",
      "-",
      join(REPOSITORY_ROOT, HOOK_EVENT_ENVELOPE_SCHEMA_PATH),
      instancePath,
    ],
    { cwd: REPOSITORY_ROOT, encoding: "utf8", input: script },
  );

  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  assert.equal(result.stdout.trim(), "HookEventEnvelope valid");
});
