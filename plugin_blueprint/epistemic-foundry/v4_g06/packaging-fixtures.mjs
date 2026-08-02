// Test scaffolding: a staged repository root the adversarial suite may damage,
// plus builders for the lockfiles and host observations the gate consumes.
//
// Every hostile case needs an input that is wrong in exactly one way, so the
// declaring inputs are copied into a temporary root and mutated there.  The real
// repository is never written to by a test.

import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

import { verifyHookTrust } from "../../../packages/plugin-host/src/capability-probe/capability-probe.mjs";
import { computeLockfileHash, MANIFEST_PATH, REPOSITORY_ROOT } from "./index.mjs";

/**
 * The inputs `loadPackage` reads by path: the manifest itself, the schemas, the
 * G05 surface and its payload inventory, MASTER_SPEC, the hook bundles and the
 * H05 registrations, the plugin manifest and the MCP configuration.  The CLI
 * projection is imported code, so it is the real sealed projection in every case.
 */
const STAGED_PATHS = Object.freeze([
  MANIFEST_PATH,
  "schemas",
  "MASTER_SPEC.md",
  "plugins/epistemic-foundry/skills",
  "plugin_blueprint/epistemic-foundry/v4_g05/evolution-surface.json",
  "plugin_blueprint/epistemic-foundry/hooks",
  "plugin_blueprint/epistemic-foundry/.codex-plugin/plugin.json",
  "plugin_blueprint/epistemic-foundry/.mcp.json",
]);

export const stageRoot = (t) => {
  const root = mkdtempSync(join(tmpdir(), "ef-g06-"));
  t.after(() => rmSync(root, { force: true, recursive: true }));
  for (const relative of STAGED_PATHS) {
    const target = join(root, relative);
    mkdirSync(dirname(target), { recursive: true });
    cpSync(join(REPOSITORY_ROOT, relative), target, { recursive: true });
  }
  return root;
};

export const readStaged = (root, relative) => readFileSync(join(root, relative), "utf8");

export const writeStaged = (root, relative, text) =>
  writeFileSync(join(root, relative), text, "utf8");

export const readStagedJson = (root, relative) => JSON.parse(readStaged(root, relative));

export const writeStagedJson = (root, relative, value) =>
  writeStaged(root, relative, `${JSON.stringify(value, null, 2)}\n`);

/** Stage a root whose capability manifest has been mutated in one way. */
export const stageManifest = (t, mutate) => {
  const root = stageRoot(t);
  const manifest = readStagedJson(root, MANIFEST_PATH);
  mutate(manifest, root);
  writeStagedJson(root, MANIFEST_PATH, manifest);
  return root;
};

/** Run `run` and return the refusal it raises, or fail loudly if it does not. */
export const refusal = (run) => {
  try {
    run();
  } catch (error) {
    return error;
  }
  throw new Error("expected a refusal, but the call succeeded");
};

const LOCKFILE_HASH_PLACEHOLDER = `sha256:${"0".repeat(64)}`;

/** A well-formed lockfile skill row; override any field to make it hostile. */
export const lockfileSkill = (overrides = {}) => ({
  skill_id: "vendor-analyzer",
  source: "https://skills.example.com/vendor-analyzer",
  revision: "1.4.2",
  content_hash: `sha256:${"1".repeat(64)}`,
  signature_status: "VERIFIED",
  license: "Apache-2.0",
  permissions: ["plugin_cli"],
  review_status: "APPROVED",
  approved_by_ids: ["approver-001"],
  ...overrides,
});

/** Seal a lockfile by computing the lock hash the gate re-derives. */
export const sealLockfile = ({ skills = [lockfileSkill()], overrides = {} } = {}) => {
  const lockfile = {
    lock_version: 1,
    workspace_id: "ws-g06-fixture",
    skills,
    generated_at: "2026-08-02T07:00:00.000Z",
    policy_hash: `sha256:${"2".repeat(64)}`,
    lock_hash: LOCKFILE_HASH_PLACEHOLDER,
    ...overrides,
  };
  return { ...lockfile, lock_hash: computeLockfileHash(lockfile) };
};

const HOOK_HASH = `sha256:${"a".repeat(64)}`;

/**
 * A host observation under which every declared capability is SUPPORTED, hook
 * trust is verified, and every declared hook event and tool path is observed:
 * the FULL/PASS path.  Override `observations` to make a capability degrade.
 */
export const healthyObservation = (loaded, overrides = {}) => {
  const trust = verifyHookTrust({
    hookDefinitions: [{ hookId: "efoundry-session", observedHash: HOOK_HASH }],
    trustedHookHashes: [HOOK_HASH],
    hooksEnabled: true,
  });
  const observations = Object.fromEntries(
    loaded.manifest.declaredCapabilities.map((capability) => [
      capability,
      { state: "SUPPORTED", evidence: `${capability} observed` },
    ]),
  );
  return {
    detectedAt: "2026-08-02T07:00:00.000Z",
    generatedAt: "2026-08-02T07:00:00.000Z",
    healthId: "EF-G06-HEALTH-0001",
    host: "claude_code",
    hostVersion: "1.0.0",
    hookTrust: trust,
    knownToolPaths: ["Agent", "Bash"],
    observations,
    observedHookEvents: [...loaded.declaredHookEvents],
    observedToolPaths: ["Agent", "Bash"],
    profile: "RESEARCH",
    reportId: "EF-G06-REPORT-0001",
    ...overrides,
  };
};

/** Replace one capability observation in an otherwise healthy observation. */
export const withCapabilityState = (loaded, capability, state, overrides = {}) => {
  const base = healthyObservation(loaded, overrides);
  return {
    ...base,
    observations: {
      ...base.observations,
      [capability]: { state, evidence: `${capability} ${state}` },
    },
  };
};
