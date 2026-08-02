// unit_and_contract_tests — what the packaging gate does when the plugin is
// intact.
//
// The happy paths are the ones a real install takes: derive the discoverable
// skills from the sealed inventory, discover an approved third-party skill from
// a signed lockfile, and integrate the declared capabilities against an observed
// host into a health report.  Discovery is a projection of what the package
// declares, so a bundled skill appears exactly because the inventory ships it.

import assert from "node:assert/strict";
import test from "node:test";

import { HOOK_EVENT_TYPES } from "../../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  deriveDiscoverableSkills,
  discoverLockfileSkills,
  integratePackage,
  loadPackage,
} from "./index.mjs";
import { healthyObservation, lockfileSkill, sealLockfile, withCapabilityState } from "./packaging-fixtures.mjs";

const loaded = loadPackage();

test("g06_load: the package loads frozen and declares exactly the manifest fields", () => {
  assert.ok(Object.isFrozen(loaded));
  assert.equal(loaded.manifest.pluginId, "epistemic-foundry");
  assert.equal(loaded.manifest.version, "4.0.0");
  assert.ok(loaded.manifest.requiredCapabilities.includes("plugin_hooks"));
});

test("g06_discovery: the discoverable skills are exactly the sealed inventory", () => {
  const discoverable = deriveDiscoverableSkills(loaded);

  assert.equal(discoverable.length, loaded.inventorySkillIds.length);
  assert.deepEqual(
    discoverable.map((row) => row.skill_id),
    [...loaded.inventorySkillIds],
  );
  for (const row of discoverable) {
    assert.equal(row.origin, "BUNDLED");
    assert.equal(row.content_hash, loaded.contentHashBySkill.get(row.skill_id));
  }
});

test("g06_discovery: the discoverable set covers every evolution skill", () => {
  const discoverable = new Set(deriveDiscoverableSkills(loaded).map((row) => row.skill_id));

  for (const skillId of loaded.evolutionSkillIds) {
    assert.ok(discoverable.has(skillId), skillId);
  }
});

test("g06_discovery: nothing is discovered that the inventory does not declare", () => {
  const inventory = new Set(loaded.inventorySkillIds);

  for (const row of deriveDiscoverableSkills(loaded)) {
    assert.ok(inventory.has(row.skill_id), row.skill_id);
  }
});

test("g06_lockfile: an approved, verified, attested third-party skill is discovered", () => {
  const result = discoverLockfileSkills(loaded, sealLockfile());

  assert.deepEqual(
    result.discoverable.map((row) => row.skill_id),
    ["vendor-analyzer"],
  );
  assert.equal(result.discoverable[0].origin, "THIRD_PARTY");
  assert.deepEqual([...result.refused], []);
});

test("g06_lockfile: discovery of the same lockfile is deterministic", () => {
  const lockfile = sealLockfile();

  assert.deepEqual(discoverLockfileSkills(loaded, lockfile), discoverLockfileSkills(loaded, lockfile));
});

test("g06_lockfile: a mixed lockfile discovers the approved and records the rest", () => {
  const result = discoverLockfileSkills(
    loaded,
    sealLockfile({
      skills: [
        lockfileSkill({ skill_id: "vendor-approved" }),
        lockfileSkill({ skill_id: "vendor-quarantined", review_status: "QUARANTINED" }),
        lockfileSkill({ skill_id: "vendor-unsigned", signature_status: "UNVERIFIED" }),
      ],
    }),
  );

  assert.deepEqual(
    result.discoverable.map((row) => row.skill_id),
    ["vendor-approved"],
  );
  assert.deepEqual([...result.refused], [
    { code: "SKILL_QUARANTINED", skill_id: "vendor-quarantined" },
    { code: "SIGNATURE_UNVERIFIED", skill_id: "vendor-unsigned" },
  ]);
});

test("g06_integration: a fully supported host resolves to FULL/PASS", () => {
  const { report, health, receipt } = integratePackage(loaded, healthyObservation(loaded));

  assert.equal(report.mode, "FULL");
  assert.equal(health.overall, "PASS");
  assert.deepEqual(receipt.blockers, []);
  assert.deepEqual(receipt.degraded_capabilities, []);
});

test("g06_integration: a missing optional capability with a degraded mode degrades", () => {
  const { report, health, receipt } = integratePackage(
    loaded,
    withCapabilityState(loaded, "plugin_hooks", "UNSUPPORTED"),
  );

  assert.equal(report.mode, "DEGRADED");
  assert.equal(health.overall, "DEGRADED");
  assert.deepEqual(receipt.degraded_capabilities, ["plugin_hooks"]);
});

test("g06_integration: a missing required capability with no degraded mode is blocked", () => {
  const { report, health, receipt } = integratePackage(
    loaded,
    withCapabilityState(loaded, "plugin_cli", "UNSUPPORTED"),
  );

  assert.equal(report.mode, "BLOCKED");
  assert.equal(health.overall, "FAIL");
  assert.ok(receipt.blockers.includes("DEGRADED_MODE_UNDECLARED:plugin_cli"));
});

test("g06_integration: the probe is bound to the declared manifest, not the caller", () => {
  const { report } = integratePackage(loaded, healthyObservation(loaded));

  assert.deepEqual(
    Object.keys(report.capabilities).sort(),
    [...loaded.manifest.declaredCapabilities],
  );
  assert.equal(report.plugin_version, loaded.manifest.version);
});

test("g06_authority: the promotion-bearing commands are recorded, never a capability", () => {
  assert.deepEqual([...loaded.authorityBearingProjected], ["claim promote", "passport publish"]);
  for (const command of loaded.authorityBearingProjected) {
    assert.ok(!loaded.manifest.declaredCapabilities.includes(command), command);
  }
  for (const denied of loaded.deniedAuthority) {
    assert.ok(!loaded.manifest.declaredCapabilities.includes(denied), denied);
  }
});

test("g06_compose: the hook-event scope is the H05 evolution surface", () => {
  assert.ok(loaded.declaredHookEvents.length > 0);
  for (const event of loaded.declaredHookEvents) {
    assert.ok(HOOK_EVENT_TYPES.includes(event), event);
  }
});

test("g06_compose: the evolution backend skill is derived from the sealed surface", () => {
  assert.equal(loaded.backendSkillId, "foundry-shinka-adapter");
  assert.ok(loaded.evolutionSkillIds.includes(loaded.backendSkillId));
});
