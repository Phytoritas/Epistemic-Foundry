// unit_and_contract_tests — what H05 observes, and what it deliberately does not.
//
// The contract has two halves that must both hold.  The registrations observe
// the evolution and holdout event surface the plugin already declares, emitting
// envelopes the sealed gateway seals and stamps with the registration's own
// coverage disposition.  And the coverage report states, without softening, the
// hosts and event types nobody watches — including a host the gateway declares
// that no registration observes at all.

import assert from "node:assert/strict";
import test from "node:test";

import {
  HOOK_COVERAGE,
  HOOK_EVENT_TYPES,
  HOOK_HOSTS,
} from "../../../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  assertCoverageClaim,
  coverageReport,
  holdoutFlaggedPaths,
  loadObservability,
  observabilityReceipt,
  observeEvolutionEvent,
  pluginManifestWiring,
  projectHookBundle,
} from "./index.mjs";
import { CLEAN_PAYLOAD, OBSERVATION_TEMPLATE } from "./observability-fixtures.mjs";

const loaded = loadObservability();
const report = coverageReport(loaded);
const honestClaim = () => ({
  coverage_by_event_type: { ...report.coverage_by_event_type },
  not_observed: [...report.not_observed],
});

test("h05_contract: the registration set observes the evolution and holdout surface", () => {
  assert.deepEqual([...loaded.registrationIds], [
    "EFH05-OBS-EVOLUTION-POST-TOOL",
    "EFH05-OBS-EVOLUTION-PRE-TOOL",
    "EFH05-OBS-HOLDOUT-STOP",
  ]);
  assert.deepEqual([...loaded.evolutionEventTypes], ["PostToolUse", "PreToolUse", "Stop"]);
});

test("h05_contract: each host and event pair has exactly one owning registration", () => {
  assert.equal(loaded.observedPairs.size, 5);
  assert.deepEqual([...loaded.observedPairs.keys()].sort(), [
    "claude:PostToolUse",
    "claude:PreToolUse",
    "claude:Stop",
    "codex:PostToolUse",
    "codex:PreToolUse",
  ]);
});

test("h05_contract: an observation carries the registration's declared coverage", async () => {
  const envelope = await observeEvolutionEvent(loaded, {
    ...OBSERVATION_TEMPLATE,
    payload: CLEAN_PAYLOAD,
  });

  assert.equal(envelope.coverage, "OBSERVED");
  assert.equal(envelope.host, "codex");
  assert.equal(envelope.event_type, "PreToolUse");
  assert.ok(HOOK_COVERAGE.includes(envelope.coverage));
});

test("h05_contract: a partially covered registration stamps its envelopes PARTIAL", async () => {
  const envelope = await observeEvolutionEvent(loaded, {
    eventId: "EFH05-EVENT-0002",
    eventType: "Stop",
    host: "claude",
    observedAt: "2026-08-02T07:05:00Z",
    payload: { reason: "session stop" },
    registrationId: "EFH05-OBS-HOLDOUT-STOP",
  });

  assert.equal(envelope.coverage, "PARTIAL");
  assert.equal(envelope.decision, "ADVISORY");
});

test("h05_contract: an observation never allows, blocks or rewrites the host action", async () => {
  const envelope = await observeEvolutionEvent(loaded, {
    ...OBSERVATION_TEMPLATE,
    payload: CLEAN_PAYLOAD,
  });

  assert.equal(loaded.decisions.control.has(envelope.decision), false);
  assert.equal(envelope.action_intent_id, null);
  assert.equal(envelope.effect_receipt_id, null);
  assert.ok(envelope.reasons.includes("H05_OBSERVATION_ONLY:EFH05-OBS-EVOLUTION-PRE-TOOL"));
  assert.ok(envelope.reasons.includes("H05_DECLARED_COVERAGE:OBSERVED"));
});

test("h05_contract: an emitted envelope is frozen and re-derives its own hash", async () => {
  const envelope = await observeEvolutionEvent(loaded, {
    ...OBSERVATION_TEMPLATE,
    payload: CLEAN_PAYLOAD,
  });

  assert.ok(Object.isFrozen(envelope));
  assert.ok(Object.isFrozen(envelope.normalized_payload));
  assert.match(envelope.envelope_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("h05_contract: the caller's timestamp is the only clock", async () => {
  const first = await observeEvolutionEvent(loaded, {
    ...OBSERVATION_TEMPLATE,
    payload: CLEAN_PAYLOAD,
  });
  const second = await observeEvolutionEvent(loaded, {
    ...OBSERVATION_TEMPLATE,
    payload: CLEAN_PAYLOAD,
  });

  assert.equal(first.received_at, OBSERVATION_TEMPLATE.observedAt);
  assert.deepEqual({ ...first }, { ...second });
});

test("h05_contract: the observed payload is not mutated by observing it", async () => {
  const payload = { candidate_id: "CAND-0002", nested: { run: 3 } };
  const before = JSON.parse(JSON.stringify(payload));
  await observeEvolutionEvent(loaded, { ...OBSERVATION_TEMPLATE, payload });

  assert.deepEqual(payload, before);
});

test("h05_contract: the coverage report names an unobserved disposition, never a silence", () => {
  assert.equal(report.coverage_by_event_type.PreToolUse, "PARTIAL");
  assert.equal(report.coverage_by_event_type.PostToolUse, "PARTIAL");
  assert.equal(report.coverage_by_event_type.Stop, "PARTIAL");
  assert.equal(report.coverage_by_event_type.SessionStart, "UNOBSERVED");
  for (const eventType of HOOK_EVENT_TYPES) {
    assert.ok(HOOK_COVERAGE.includes(report.coverage_by_event_type[eventType]), eventType);
  }
});

test("h05_contract: every unobserved host and event pair is listed explicitly", () => {
  const expected = HOOK_HOSTS.flatMap((host) =>
    HOOK_EVENT_TYPES.map((eventType) => `${host}:${eventType}`),
  ).filter((pair) => !loaded.observedPairs.has(pair));

  assert.deepEqual([...report.not_observed], expected.sort());
  assert.equal(report.not_observed.length, HOOK_HOSTS.length * HOOK_EVENT_TYPES.length - 5);
});

test("h05_contract: a host the gateway declares but nobody observes is named", () => {
  assert.deepEqual([...report.hosts_never_observed], ["other"]);
  for (const eventType of HOOK_EVENT_TYPES) {
    assert.ok(report.not_observed.includes(`other:${eventType}`), eventType);
  }
});

test("h05_contract: registration coverage is scoped, report coverage is absolute", () => {
  const preTool = loaded.registrationsById.get("EFH05-OBS-EVOLUTION-PRE-TOOL");

  assert.equal(preTool.coverage, "OBSERVED");
  assert.deepEqual([...preTool.hosts], [...loaded.observedHosts]);
  assert.equal(report.coverage_by_event_type.PreToolUse, "PARTIAL");
});

test("h05_contract: an honest coverage claim is accepted", () => {
  assert.deepEqual(assertCoverageClaim(loaded, honestClaim()), report);
});

test("h05_contract: the projected bundle mirrors the plugin's own hook bundle shape", () => {
  const bundle = projectHookBundle(loaded);

  assert.deepEqual(Object.keys(bundle.hooks).sort(), ["PostToolUse", "PreToolUse", "Stop"]);
  for (const [eventType, rows] of Object.entries(bundle.hooks)) {
    for (const row of rows) {
      assert.equal(row.hooks.length, 1);
      assert.equal(row.hooks[0].type, "command");
      assert.ok(row.hooks[0].command.startsWith(loaded.commandPrefix), eventType);
      assert.equal(typeof row.hooks[0].timeout, "number");
      assert.ok(row.hooks[0].statusMessage.startsWith("(Epistemic Foundry)"));
    }
  }
  assert.equal(Object.hasOwn(bundle.hooks.Stop[0], "matcher"), false);
  assert.equal(bundle.hooks.PreToolUse[0].matcher, "Bash|mcp__efoundry__evolve.*|Agent");
});

test("h05_contract: the projection is not wired into the plugin manifest, and says so", () => {
  const wiring = pluginManifestWiring(loaded);

  assert.equal(wiring.manifest_wired, false);
  assert.deepEqual([...wiring.wired_paths], []);
  assert.equal(wiring.manifest_hook_count, 7);
  assert.equal(observabilityReceipt(loaded).plugin_manifest_wired, false);
});

test("h05_contract: a payload naming no holdout-flagged field yields no flagged path", () => {
  assert.deepEqual([...holdoutFlaggedPaths(loaded, CLEAN_PAYLOAD)], []);
  assert.deepEqual([...holdoutFlaggedPaths(loaded, { public_partition_refs: ["ref"] })], []);
});

test("h05_contract: holdout-flagged material is found however deeply it is nested", () => {
  const paths = holdoutFlaggedPaths(loaded, {
    outer: { inner: [{ hidden_partition_handles: ["H1"] }] },
    prompt_access: true,
  });

  assert.deepEqual(
    [...paths],
    ["payload.outer.inner[0].hidden_partition_handles", "payload.prompt_access"],
  );
});

test("h05_contract: the loaded surface is frozen and holds no writable state", () => {
  assert.ok(Object.isFrozen(loaded));
  assert.ok(Object.isFrozen(loaded.registrationIds));
  assert.ok(Object.isFrozen(loaded.evolutionEventTypes));
  assert.ok(Object.isFrozen(loaded.holdout));
  assert.ok(Object.isFrozen(report));
});
