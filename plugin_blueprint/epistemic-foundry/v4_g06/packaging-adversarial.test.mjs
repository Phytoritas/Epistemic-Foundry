// negative_and_adversarial_tests — every way the package can lie, refused.
//
// A packaging gate fails quietly: it advertises a skill that does not ship, a
// command the host cannot dispatch, or a hook bundle that is not there, and a
// user is told a capability exists that does not.  So each hostile input is
// staged as a copy of the declaring sources that is wrong in exactly one way,
// and each must be refused by its own code.  The CLI projection is imported
// code, so it is the real sealed projection in every case below.

import assert from "node:assert/strict";
import test from "node:test";

import {
  discoverLockfileSkills,
  loadPackage,
  PluginPackagingError,
} from "./index.mjs";
import {
  lockfileSkill,
  refusal,
  sealLockfile,
  stageManifest,
} from "./packaging-fixtures.mjs";

const loaded = loadPackage();
const refused = (root) => {
  const error = refusal(() => loadPackage({ root }));
  assert.ok(error instanceof PluginPackagingError, error.message);
  return error;
};

test("g06_refuse: an unexpected manifest field is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.experimental = true;
  });

  assert.equal(refused(root).code, "MANIFEST_UNREADABLE");
});

test("g06_refuse: a non-canonical plugin id is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.plugin_id = "Epistemic_Foundry";
  });

  assert.equal(refused(root).code, "MANIFEST_FIELD_INVALID");
});

test("g06_refuse: a non-semver version is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.version = "4.0";
  });

  assert.equal(refused(root).code, "MANIFEST_FIELD_INVALID");
});

test("g06_refuse: a host surface outside the schema vocabulary is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.host_surfaces = [...manifest.host_surfaces, "vscode"].sort();
  });

  const error = refused(root);
  assert.equal(error.code, "MANIFEST_FIELD_INVALID");
  assert.equal(error.context.surface, "vscode");
});

test("g06_refuse: an unsorted skill list is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.skills = [...manifest.skills].reverse();
  });

  assert.equal(refused(root).code, "MANIFEST_FIELD_INVALID");
});

test("g06_refuse: dropping the plugin_hooks capability is refused as unsatisfiable", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.required_capabilities = manifest.required_capabilities.filter(
      (capability) => capability !== "plugin_hooks",
    );
  });

  assert.equal(refused(root).code, "PLUGIN_HOOKS_UNDECLARED");
});

test("g06_refuse: a degraded mode for an undeclared capability is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    const last = manifest.degraded_modes[manifest.degraded_modes.length - 1];
    last.missing_capability = "plugin_zzz_unknown";
  });

  const error = refused(root);
  assert.equal(error.code, "DEGRADED_MODE_INVALID");
  assert.equal(error.context.missing, "plugin_zzz_unknown");
});

test("g06_refuse: a degraded mode with an undeclared disposition is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.degraded_modes[0].mode = "OFFLINE";
  });

  const error = refused(root);
  assert.equal(error.code, "DEGRADED_MODE_INVALID");
  assert.equal(error.context.mode, "OFFLINE");
});

test("g06_refuse: declaring a skill the inventory does not ship is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.skills = [...manifest.skills, "foundry-ghost"].sort();
  });

  const error = refused(root);
  assert.equal(error.code, "SKILL_UNDECLARED");
  assert.equal(error.context.skill_id, "foundry-ghost");
});

test("g06_refuse: omitting a skill the inventory ships is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.skills = manifest.skills.filter((skill) => skill !== "foundry-recall");
  });

  const error = refused(root);
  assert.equal(error.code, "SKILL_DISCOVERY_DRIFT");
  assert.equal(error.context.skill_id, "foundry-recall");
});

test("g06_refuse: declaring a command the tool surface does not project is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.cli_commands = [...manifest.cli_commands, "evolve teleport"].sort();
  });

  const error = refused(root);
  assert.equal(error.code, "CLI_COMMAND_UNPROJECTED");
  assert.equal(error.context.command, "evolve teleport");
});

test("g06_refuse: omitting a command the tool surface projects is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.cli_commands = manifest.cli_commands.filter((command) => command !== "status");
  });

  const error = refused(root);
  assert.equal(error.code, "CLI_COMMAND_OMITTED");
  assert.equal(error.context.command, "status");
});

test("g06_refuse: a capability that names denied authority is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.optional_capabilities = [...manifest.optional_capabilities, "promotion"].sort();
  });

  const error = refused(root);
  assert.equal(error.code, "AUTHORITY_CAPABILITY_DECLARED");
  assert.equal(error.context.capability, "promotion");
});

test("g06_refuse: a hook bundle whose file does not exist is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.hook_bundles = [...manifest.hook_bundles, "ghostbundle"].sort();
  });

  assert.equal(refused(root).code, "HOOK_BUNDLE_UNDECLARED");
});

test("g06_refuse: omitting an H05 evolution hook bundle is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.hook_bundles = manifest.hook_bundles.filter((bundle) => bundle !== "evolution");
  });

  const error = refused(root);
  assert.equal(error.code, "HOOK_BUNDLE_DISCOVERY_DRIFT");
  assert.equal(error.context.bundle, "evolution");
});

test("g06_refuse: declaring an MCP server the configuration lacks is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.mcp_servers = ["ghost-server"];
  });

  const error = refused(root);
  assert.equal(error.code, "MCP_SERVER_UNDECLARED");
  assert.equal(error.context.server, "ghost-server");
});

test("g06_lockfile: a lockfile missing a field is refused", () => {
  const lockfile = sealLockfile();
  delete lockfile.policy_hash;

  assert.equal(refusal(() => discoverLockfileSkills(loaded, lockfile)).code, "LOCKFILE_UNREADABLE");
});

test("g06_lockfile: a tampered lockfile whose hash no longer matches is refused", () => {
  const lockfile = sealLockfile();
  lockfile.workspace_id = "ws-tampered";

  assert.equal(refusal(() => discoverLockfileSkills(loaded, lockfile)).code, "LOCKFILE_HASH_MISMATCH");
});

test("g06_lockfile: a third-party skill impersonating a bundled one is refused", () => {
  const result = discoverLockfileSkills(
    loaded,
    sealLockfile({ skills: [lockfileSkill({ skill_id: "foundry" })] }),
  );

  assert.deepEqual([...result.discoverable], []);
  assert.deepEqual([...result.refused], [{ code: "SKILL_ID_COLLISION", skill_id: "foundry" }]);
});

test("g06_lockfile: a skill claiming an undeclared capability is refused", () => {
  const result = discoverLockfileSkills(
    loaded,
    sealLockfile({ skills: [lockfileSkill({ permissions: ["nonexistent_cap"] })] }),
  );

  assert.deepEqual([...result.discoverable], []);
  assert.deepEqual([...result.refused], [
    { code: "PERMISSION_UNDECLARED", permission: "nonexistent_cap", skill_id: "vendor-analyzer" },
  ]);
});

test("g06_lockfile: an approved skill with no attested approver is refused", () => {
  const result = discoverLockfileSkills(
    loaded,
    sealLockfile({ skills: [lockfileSkill({ approved_by_ids: [] })] }),
  );

  assert.deepEqual([...result.discoverable], []);
  assert.deepEqual([...result.refused], [{ code: "APPROVAL_UNATTESTED", skill_id: "vendor-analyzer" }]);
});
