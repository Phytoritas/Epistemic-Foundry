// G06 — native plugin packaging and skill-discovery integration gate.
//
// This module declares no vocabulary of its own.  The capability names, host
// surfaces, degraded-mode dispositions and capability states come from the
// canonical PluginCapabilityManifest schema and the sealed capability probe; the
// skills that may be discovered come from the payload skill inventory that G05
// already verifies; the CLI commands come from the sealed tool-surface
// projection; the commands that carry promotion authority and the authority the
// package denies come from the sealed G05 evolution surface; and the hook-event
// coverage scope comes from the sealed H05 observability surface.  What G06 adds
// is the binding between them and the refusals that keep the binding honest.
//
// Three honesty rules drive every refusal here.
//
//   1. Packaging is a projection, never an invention.  The manifest may declare
//      only skills the inventory ships, only commands the tool surface projects,
//      only hook bundles that exist and only MCP servers the package configures;
//      understating any of those surfaces is refused as loudly as overstating.
//   2. Discovery derives from declared manifests.  A bundled skill is discovered
//      from the sealed inventory; a third-party skill is discovered from a
//      signed, approved lockfile row whose permissions the package actually
//      declares.  A skill that is unsigned, quarantined, unattested or that
//      claims a capability the package does not have is refused, not activated.
//   3. Packaging carries no authority.  No declared capability may name the
//      evaluator, holdout or promotion authority the G05 surface denies, and the
//      promotion-bearing commands the CLI projects are recorded as such rather
//      than laundered into a freely discoverable capability.
//
// The module owns no state and holds no clock: every timestamp is supplied by
// the caller, and every hash is re-derivable from the values published beside it
// with the sealed gateway's canonical-JSON digest.

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { basename, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildPluginHealthReport,
  probeHostCapabilities,
} from "../../../packages/plugin-host/src/capability-probe/capability-probe.mjs";
import { commandSurface } from "../../../packages/plugin-host/src/cli/command-surface.mjs";
import {
  canonicalizeHookJson,
  sha256HookJson,
} from "../../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  EVOLUTION_BUNDLE_PATH as H05_EVOLUTION_BUNDLE_PATH,
  HOLDOUT_BUNDLE_PATH as H05_HOLDOUT_BUNDLE_PATH,
  coverageReport,
  loadObservability,
} from "../hooks/v4_h05/index.mjs";
import {
  INVENTORY_PATH as G05_INVENTORY_PATH,
  SURFACE_PATH as G05_SURFACE_PATH,
  loadSurface,
} from "../v4_g05/index.mjs";

/** Repository root, resolved from this file rather than the process cwd. */
export const REPOSITORY_ROOT = fileURLToPath(new URL("../../../", import.meta.url));

export const MANIFEST_PATH =
  "plugin_blueprint/epistemic-foundry/v4_g06/capability-manifest.json";
export const CAPABILITY_MANIFEST_SCHEMA_PATH =
  "schemas/plugin-capability-manifest.schema.json";
export const SKILL_LOCKFILE_SCHEMA_PATH = "schemas/skill-lockfile.schema.json";
export const MCP_CONFIG_PATH = "plugin_blueprint/epistemic-foundry/.mcp.json";
export const HOOKS_ROOT = "plugin_blueprint/epistemic-foundry/hooks";
export const INVENTORY_PATH = G05_INVENTORY_PATH;
export const SURFACE_PATH = G05_SURFACE_PATH;

/** Every way this packaging surface refuses, and why that refusal exists. */
export const FINDING_CODES = Object.freeze({
  APPROVAL_UNATTESTED:
    "a lockfile skill is marked approved but names no approver, so its approval is a claim nobody signed and cannot enter the discoverable set",
  AUTHORITY_CAPABILITY_DECLARED:
    "a declared capability names the evaluator, holdout or promotion authority the G05 surface denies, which would let packaging acquire an authority routing never grants",
  CLI_COMMAND_OMITTED:
    "a command the sealed tool surface projects is absent from the manifest, and understating the CLI hides a command that the package actually exposes",
  CLI_COMMAND_UNPROJECTED:
    "the manifest declares a CLI command the sealed tool surface does not project, so packaging invented a command the host cannot dispatch",
  DEGRADED_MODE_INVALID:
    "a degraded-mode entry names an undeclared capability, repeats a capability, or uses a disposition the capability-manifest schema does not declare",
  HOOK_BUNDLE_DISCOVERY_DRIFT:
    "the manifest omits an evolution or holdout hook bundle the sealed H05 observability surface declares, so packaging hides a hook bundle that ships",
  HOOK_BUNDLE_UNDECLARED:
    "the manifest declares a hook bundle whose definition file does not exist in the plugin, so packaging advertises hooks that cannot be loaded",
  LOCKFILE_HASH_MISMATCH:
    "a skill lockfile does not hash to its own stated lock hash, so its rows are not evidence of the supply chain the workspace approved",
  LOCKFILE_UNREADABLE:
    "the skill lockfile could not be read as the object this module requires, so no third-party discovery decision can be derived from it",
  MANIFEST_FIELD_INVALID:
    "a capability-manifest field is missing, mistyped, non-canonical, or outside the vocabulary the manifest schema declares for it",
  MANIFEST_UNREADABLE:
    "the capability manifest could not be read as the exact object this module requires, so packaging has no declaration to gate",
  MCP_SERVER_UNDECLARED:
    "the manifest declares an MCP server the plugin's own MCP configuration does not define, so packaging advertises a transport that does not exist",
  PERMISSION_UNDECLARED:
    "a lockfile skill requests a permission the package does not declare as a capability, so it claims a capability the package does not actually have",
  PLUGIN_HOOKS_UNDECLARED:
    "the manifest declares no plugin_hooks capability, so the sealed capability probe that binds hook trust to the health report cannot be satisfied",
  SIGNATURE_UNVERIFIED:
    "a lockfile skill's signature is unverified, failed or not provided, so it cannot be trusted into the discoverable set without a fresh approval",
  SKILL_DISCOVERY_DRIFT:
    "the manifest omits a skill the sealed inventory ships, so the discoverable set understates the skills the package actually contains",
  SKILL_ID_COLLISION:
    "a third-party lockfile skill reuses the identifier of a bundled skill, so approving it would let an outside skill impersonate a first-party one",
  SKILL_QUARANTINED:
    "a lockfile skill is quarantined, rejected or disabled, so the supply-chain gate keeps it out of the discoverable set until it is approved",
  SKILL_UNDECLARED:
    "the manifest declares a skill the sealed inventory does not ship, so discovery would surface a skill that has no verified body",
});

export class PluginPackagingError extends Error {
  constructor(code, message, context = {}) {
    super(message);
    this.name = "PluginPackagingError";
    this.code = code;
    this.context = context;
  }
}

const fail = (code, message, context = {}) => {
  throw new PluginPackagingError(code, message, context);
};

const MANIFEST_FIELDS = Object.freeze([
  "plugin_id",
  "version",
  "schema_version",
  "host_surfaces",
  "required_capabilities",
  "optional_capabilities",
  "degraded_modes",
  "skills",
  "hook_bundles",
  "mcp_servers",
  "cli_commands",
]);
const DEGRADED_MODE_FIELDS = Object.freeze(["missing_capability", "mode", "behavior"]);
const LOCKFILE_FIELDS = Object.freeze([
  "lock_version",
  "workspace_id",
  "skills",
  "generated_at",
  "policy_hash",
  "lock_hash",
]);
const LOCKFILE_SKILL_FIELDS = Object.freeze([
  "skill_id",
  "source",
  "revision",
  "content_hash",
  "signature_status",
  "license",
  "permissions",
  "review_status",
  "approved_by_ids",
]);

const PLUGIN_ID_PATTERN = /^[a-z][a-z0-9-]+$/u;
const VERSION_PATTERN = /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/u;
const CAPABILITY_NAME_PATTERN = /^[a-z][a-z0-9_]*$/u;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;

/** The one capability the sealed probe requires the manifest to declare. */
const REQUIRED_PROBE_CAPABILITY = "plugin_hooks";

const isPlainObject = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);

const readBytes = (root, relative, code = "MANIFEST_UNREADABLE") => {
  try {
    return readFileSync(join(root, relative));
  } catch (error) {
    fail(code, `cannot read ${relative}: ${error.message}`, { path: relative });
    return Buffer.alloc(0);
  }
};

const readJson = (root, relative, code = "MANIFEST_UNREADABLE") => {
  const text = readBytes(root, relative, code).toString("utf8");
  try {
    return JSON.parse(text);
  } catch (error) {
    fail(code, `${relative} is not JSON: ${error.message}`, { path: relative });
    return undefined;
  }
};

const sha256Bytes = (bytes) => `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

const requireExactFields = (value, fields, label, code) => {
  if (!isPlainObject(value)) fail(code, `${label} must be an object`, { label });
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail(code, `${label} must declare exactly ${expected.join(", ")}`, { actual, expected });
  }
  return value;
};

const requireCanonicalStringArray = (
  value,
  label,
  { allowEmpty = true, pattern = undefined, code = "MANIFEST_FIELD_INVALID" } = {},
) => {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) {
    fail(code, `${label} must be an array of strings`, { label });
  }
  if (!allowEmpty && value.length === 0) fail(code, `${label} must not be empty`, { label });
  const sorted = [...value].sort();
  if (value.some((entry, index) => entry !== sorted[index])) {
    fail(code, `${label} must be sorted`, { label, value });
  }
  if (new Set(value).size !== value.length) {
    fail(code, `${label} must not repeat an entry`, { label, value });
  }
  if (pattern !== undefined) {
    for (const entry of value) {
      if (!pattern.test(entry)) fail(code, `${label} holds a non-canonical entry "${entry}"`, { entry, label });
    }
  }
  return Object.freeze([...value]);
};

const requireString = (value, label, { pattern = undefined, code = "MANIFEST_FIELD_INVALID" } = {}) => {
  if (typeof value !== "string" || value.length === 0) {
    fail(code, `${label} must be a non-empty string`, { label });
  }
  if (pattern !== undefined && !pattern.test(value)) {
    fail(code, `${label} does not match its declared form`, { label, value });
  }
  return value;
};

/**
 * Read the vocabulary the capability-manifest schema declares, so this module
 * gates against the schema's own host-surface and degraded-mode literals rather
 * than restating them (EF4-I22).
 */
const readManifestVocabulary = (root) => {
  const schema = readJson(root, CAPABILITY_MANIFEST_SCHEMA_PATH);
  const hostSurfaces = schema?.properties?.host_surfaces?.items?.enum;
  const degradedModes = schema?.properties?.degraded_modes?.items?.properties?.mode?.enum;
  if (!Array.isArray(hostSurfaces) || !Array.isArray(degradedModes)) {
    fail("MANIFEST_UNREADABLE", "the capability-manifest schema declares no host-surface or degraded-mode vocabulary");
  }
  return {
    degradedModeSet: new Set(degradedModes),
    hostSurfaceSet: new Set(hostSurfaces),
  };
};

const validateManifest = (root, vocabulary) => {
  const manifest = requireExactFields(
    readJson(root, MANIFEST_PATH),
    MANIFEST_FIELDS,
    "capability manifest",
    "MANIFEST_UNREADABLE",
  );

  const pluginId = requireString(manifest.plugin_id, "plugin_id", { pattern: PLUGIN_ID_PATTERN });
  const version = requireString(manifest.version, "version", { pattern: VERSION_PATTERN });
  const schemaVersion = requireString(manifest.schema_version, "schema_version");

  const hostSurfaces = requireCanonicalStringArray(manifest.host_surfaces, "host_surfaces", {
    allowEmpty: false,
  });
  for (const surface of hostSurfaces) {
    if (!vocabulary.hostSurfaceSet.has(surface)) {
      fail("MANIFEST_FIELD_INVALID", `host_surfaces names undeclared surface "${surface}"`, {
        surface,
      });
    }
  }

  const requiredCapabilities = requireCanonicalStringArray(
    manifest.required_capabilities,
    "required_capabilities",
    { allowEmpty: false, pattern: CAPABILITY_NAME_PATTERN },
  );
  const optionalCapabilities = requireCanonicalStringArray(
    manifest.optional_capabilities,
    "optional_capabilities",
    { pattern: CAPABILITY_NAME_PATTERN },
  );
  const declaredCapabilities = new Set([...requiredCapabilities, ...optionalCapabilities]);
  if (declaredCapabilities.size !== requiredCapabilities.length + optionalCapabilities.length) {
    fail("MANIFEST_FIELD_INVALID", "required_capabilities and optional_capabilities must be disjoint");
  }
  if (!declaredCapabilities.has(REQUIRED_PROBE_CAPABILITY)) {
    fail("PLUGIN_HOOKS_UNDECLARED", `the manifest must declare the ${REQUIRED_PROBE_CAPABILITY} capability`, {
      declared: [...declaredCapabilities].sort(),
    });
  }

  if (!Array.isArray(manifest.degraded_modes)) {
    fail("DEGRADED_MODE_INVALID", "degraded_modes must be an array");
  }
  const degradedByCapability = new Map();
  let previousCapability = "";
  for (const entry of manifest.degraded_modes) {
    requireExactFields(entry, DEGRADED_MODE_FIELDS, "degraded_modes[]", "DEGRADED_MODE_INVALID");
    const missing = requireString(entry.missing_capability, "degraded_modes[].missing_capability", {
      code: "DEGRADED_MODE_INVALID",
    });
    if (missing < previousCapability) {
      fail("DEGRADED_MODE_INVALID", "degraded_modes must be sorted by missing_capability", { missing });
    }
    previousCapability = missing;
    if (!declaredCapabilities.has(missing)) {
      fail("DEGRADED_MODE_INVALID", `degraded_modes names undeclared capability "${missing}"`, { missing });
    }
    if (degradedByCapability.has(missing)) {
      fail("DEGRADED_MODE_INVALID", `degraded_modes maps "${missing}" more than once`, { missing });
    }
    if (!vocabulary.degradedModeSet.has(entry.mode)) {
      fail("DEGRADED_MODE_INVALID", `degraded_modes uses undeclared mode "${entry.mode}"`, {
        mode: entry.mode,
      });
    }
    requireString(entry.behavior, "degraded_modes[].behavior", { code: "DEGRADED_MODE_INVALID" });
    degradedByCapability.set(missing, { behavior: entry.behavior, mode: entry.mode });
  }

  const skills = requireCanonicalStringArray(manifest.skills, "skills", { allowEmpty: false });
  const hookBundles = requireCanonicalStringArray(manifest.hook_bundles, "hook_bundles");
  const mcpServers = requireCanonicalStringArray(manifest.mcp_servers, "mcp_servers");
  const cliCommands = requireCanonicalStringArray(manifest.cli_commands, "cli_commands", {
    allowEmpty: false,
  });

  return Object.freeze({
    cliCommands,
    declaredCapabilities: Object.freeze([...declaredCapabilities].sort()),
    degradedByCapability,
    hookBundles,
    hostSurfaces,
    mcpServers,
    optionalCapabilities,
    pluginId,
    requiredCapabilities,
    schemaVersion,
    skills,
    version,
  });
};

/** The evolution skill whose commands drive the T05 backend adapter, or null. */
const deriveBackendSkill = (evolution) => {
  const row = evolution.surface.skills.find((skill) =>
    skill.proposed_commands.some((command) => command.startsWith("backend shinka")),
  );
  return row === undefined ? null : row.skill_id;
};

/**
 * Read, cross-check and freeze the whole packaging surface.
 *
 * G05 is composed for the verified inventory, the authority-bearing commands and
 * the denied authority; H05 for the evolution hook-event coverage scope; the
 * sealed tool surface for the projected CLI.  Nothing here is restated.
 */
export const loadPackage = ({ root = REPOSITORY_ROOT } = {}) => {
  const vocabulary = readManifestVocabulary(root);
  const manifest = validateManifest(root, vocabulary);

  // Compose G05: a verified inventory, the authority it denies and the commands
  // that carry it.  loadSurface fails closed on inventory drift for us.
  const evolution = loadSurface({ root });
  const inventorySkillIds = evolution.inventory.skills.map((row) => row.skill_id).sort();
  const inventorySet = new Set(inventorySkillIds);
  const contentHashBySkill = new Map(
    evolution.inventory.skills.map((row) => [row.skill_id, row.sha256]),
  );

  // Skill discovery derives from the declared inventory manifest: every declared
  // skill must ship, and every shipped skill must be declared.
  for (const skillId of manifest.skills) {
    if (!inventorySet.has(skillId)) {
      fail("SKILL_UNDECLARED", `the manifest declares skill "${skillId}" the inventory does not ship`, {
        skill_id: skillId,
      });
    }
  }
  const declaredSet = new Set(manifest.skills);
  for (const skillId of inventorySkillIds) {
    if (!declaredSet.has(skillId)) {
      fail("SKILL_DISCOVERY_DRIFT", `the manifest omits inventory skill "${skillId}"`, {
        skill_id: skillId,
      });
    }
  }

  // The CLI is the sealed tool-surface projection, faithfully and completely.
  const projectedCommands = commandSurface();
  const projectedNames = projectedCommands.map((row) => row.command).sort();
  const projectedSet = new Set(projectedNames);
  const declaredCommandSet = new Set(manifest.cliCommands);
  for (const command of manifest.cliCommands) {
    if (!projectedSet.has(command)) {
      fail("CLI_COMMAND_UNPROJECTED", `the manifest declares unprojected command "${command}"`, {
        command,
      });
    }
  }
  for (const command of projectedNames) {
    if (!declaredCommandSet.has(command)) {
      fail("CLI_COMMAND_OMITTED", `the manifest omits projected command "${command}"`, { command });
    }
  }

  // Packaging carries no authority: no declared capability may name a denied one.
  const deniedAuthority = [...evolution.surface.denied_authority];
  const deniedSet = new Set(deniedAuthority);
  for (const capability of manifest.declaredCapabilities) {
    if (deniedSet.has(capability)) {
      fail("AUTHORITY_CAPABILITY_DECLARED", `capability "${capability}" names denied authority`, {
        capability,
        denied_authority: deniedAuthority,
      });
    }
  }
  const authorityBearingCommands = [...evolution.authorityBearingCommands];
  const authorityBearingProjected = authorityBearingCommands
    .filter((command) => declaredCommandSet.has(command))
    .sort();

  // Hook bundles must exist, and the H05 evolution/holdout bundles must appear.
  for (const bundle of manifest.hookBundles) {
    readJson(root, `${HOOKS_ROOT}/${bundle}.json`, "HOOK_BUNDLE_UNDECLARED");
  }
  const hookBundleSet = new Set(manifest.hookBundles);
  for (const bundlePath of [H05_EVOLUTION_BUNDLE_PATH, H05_HOLDOUT_BUNDLE_PATH]) {
    const name = basename(bundlePath, ".json");
    if (!hookBundleSet.has(name)) {
      fail("HOOK_BUNDLE_DISCOVERY_DRIFT", `the manifest omits H05 hook bundle "${name}"`, {
        bundle: name,
      });
    }
  }

  // MCP servers must be defined by the plugin's own MCP configuration.
  const mcpConfig = readJson(root, MCP_CONFIG_PATH);
  const configuredServers = isPlainObject(mcpConfig?.mcpServers)
    ? new Set(Object.keys(mcpConfig.mcpServers))
    : new Set();
  for (const server of manifest.mcpServers) {
    if (!configuredServers.has(server)) {
      fail("MCP_SERVER_UNDECLARED", `the manifest declares undefined MCP server "${server}"`, {
        server,
      });
    }
  }

  // Compose H05: the evolution hook-event coverage scope, derived not invented.
  const observability = loadObservability({ root });
  const declaredHookEvents = [...coverageReport(observability).evolution_event_types].sort();

  return Object.freeze({
    authorityBearingCommands: Object.freeze(authorityBearingCommands),
    authorityBearingProjected: Object.freeze(authorityBearingProjected),
    backendSkillId: deriveBackendSkill(evolution),
    contentHashBySkill,
    declaredHookEvents: Object.freeze(declaredHookEvents),
    deniedAuthority: Object.freeze(deniedAuthority),
    evolution,
    evolutionSkillIds: Object.freeze(evolution.surface.skills.map((row) => row.skill_id).sort()),
    inventoryHash: evolution.inventory.inventory_hash,
    inventorySkillIds: Object.freeze(inventorySkillIds),
    manifest,
    mcpServers: Object.freeze([...manifest.mcpServers]),
    projectedCommands: Object.freeze(projectedCommands),
    root,
    vocabulary: Object.freeze({
      degradedModes: Object.freeze([...vocabulary.degradedModeSet].sort()),
      hostSurfaces: Object.freeze([...vocabulary.hostSurfaceSet].sort()),
    }),
  });
};

/**
 * The skills a host may discover from the sealed inventory manifest.
 *
 * Each carries the sealed content hash of its body, so a later run can prove the
 * skill it discovered is the skill that shipped.  Nothing is invented: the set
 * is exactly the inventory the package declares.
 */
export const deriveDiscoverableSkills = (loaded) =>
  Object.freeze(
    loaded.inventorySkillIds.map((skillId) =>
      Object.freeze({
        content_hash: loaded.contentHashBySkill.get(skillId),
        origin: "BUNDLED",
        skill_id: skillId,
      }),
    ),
  );

const LOCK_ITEM_ORDER = (left, right) => (left.skill_id < right.skill_id ? -1 : 1);

/**
 * The canonical lock hash of a skill lockfile: the digest of every field except
 * the hash itself.  Published beside the lockfile so a workspace can prove the
 * rows it approved are the rows it is discovering against.
 */
export const computeLockfileHash = (lockfile) => {
  if (!isPlainObject(lockfile)) {
    fail("LOCKFILE_UNREADABLE", "the skill lockfile must be an object");
  }
  const withoutHash = { ...lockfile };
  delete withoutHash.lock_hash;
  return sha256HookJson(withoutHash);
};

/**
 * Discover third-party skills from a signed, approved lockfile.
 *
 * A row enters the discoverable set only when its identifier does not collide
 * with a bundled skill, its permissions are all capabilities the package
 * declares, its signature is verified, its review is approved and its approval
 * is attested.  Every excluded row is named with the code that excluded it, so
 * a refused skill is recorded rather than silently dropped.
 */
export const discoverLockfileSkills = (loaded, lockfileCandidate) => {
  const lockfile = requireExactFields(
    lockfileCandidate,
    LOCKFILE_FIELDS,
    "skill lockfile",
    "LOCKFILE_UNREADABLE",
  );
  if (!Number.isInteger(lockfile.lock_version) || lockfile.lock_version < 1) {
    fail("LOCKFILE_UNREADABLE", "lock_version must be a positive integer");
  }
  requireString(lockfile.workspace_id, "workspace_id", { code: "LOCKFILE_UNREADABLE" });
  requireString(lockfile.generated_at, "generated_at", { code: "LOCKFILE_UNREADABLE" });
  requireString(lockfile.policy_hash, "policy_hash", {
    code: "LOCKFILE_UNREADABLE",
    pattern: SHA256_PATTERN,
  });
  const statedHash = requireString(lockfile.lock_hash, "lock_hash", {
    code: "LOCKFILE_UNREADABLE",
    pattern: SHA256_PATTERN,
  });
  if (!Array.isArray(lockfile.skills)) {
    fail("LOCKFILE_UNREADABLE", "lockfile skills must be an array");
  }
  const recomputed = computeLockfileHash(lockfile);
  if (recomputed !== statedHash) {
    fail("LOCKFILE_HASH_MISMATCH", "the lockfile does not hash to its stated lock hash", {
      recomputed,
      stated: statedHash,
    });
  }

  const declaredCapabilities = new Set(loaded.manifest.declaredCapabilities);
  const bundled = new Set(loaded.inventorySkillIds);
  const discoverable = [];
  const refused = [];
  for (const row of lockfile.skills) {
    requireExactFields(row, LOCKFILE_SKILL_FIELDS, "lockfile skill", "LOCKFILE_UNREADABLE");
    const skillId = requireString(row.skill_id, "lockfile skill.skill_id", {
      code: "LOCKFILE_UNREADABLE",
    });
    if (bundled.has(skillId)) {
      refused.push({ code: "SKILL_ID_COLLISION", skill_id: skillId });
      continue;
    }
    if (!Array.isArray(row.permissions) || row.permissions.some((p) => typeof p !== "string")) {
      fail("LOCKFILE_UNREADABLE", `lockfile skill "${skillId}" has invalid permissions`, { skillId });
    }
    const undeclared = row.permissions.find((permission) => !declaredCapabilities.has(permission));
    if (undeclared !== undefined) {
      refused.push({ code: "PERMISSION_UNDECLARED", permission: undeclared, skill_id: skillId });
      continue;
    }
    if (row.signature_status !== "VERIFIED") {
      refused.push({ code: "SIGNATURE_UNVERIFIED", skill_id: skillId });
      continue;
    }
    if (row.review_status !== "APPROVED") {
      refused.push({ code: "SKILL_QUARANTINED", skill_id: skillId });
      continue;
    }
    if (!Array.isArray(row.approved_by_ids) || row.approved_by_ids.length === 0) {
      refused.push({ code: "APPROVAL_UNATTESTED", skill_id: skillId });
      continue;
    }
    discoverable.push({
      content_hash: row.content_hash,
      origin: "THIRD_PARTY",
      skill_id: skillId,
    });
  }
  discoverable.sort(LOCK_ITEM_ORDER);
  refused.sort((left, right) =>
    left.skill_id === right.skill_id
      ? left.code < right.code
        ? -1
        : 1
      : left.skill_id < right.skill_id
        ? -1
        : 1,
  );
  return Object.freeze({
    discoverable: Object.freeze(discoverable),
    lock_hash: statedHash,
    refused: Object.freeze(refused),
    workspace_id: lockfile.workspace_id,
  });
};

/**
 * Integrate the declared package against an observed host.
 *
 * The capability names, degraded modes and hook-event scope come from the
 * manifest and the sealed H05 surface; only the observations come from the
 * caller.  The sealed capability probe turns them into a HostCapabilityReport,
 * and the sealed health builder into a PluginHealthReport.  A missing required
 * capability with no degraded mode resolves to a BLOCKED report — a refusal
 * recorded as an immutable receipt, not an exception.
 */
export const integratePackage = (loaded, observation) => {
  if (!isPlainObject(observation)) {
    fail("MANIFEST_FIELD_INVALID", "integration observation must be an object");
  }
  const degradedModes = [...loaded.manifest.degradedByCapability.entries()].map(
    ([missingCapability, { behavior, mode }]) => ({ behavior, missingCapability, mode }),
  );
  const report = probeHostCapabilities({
    degradedModes,
    detectedAt: observation.detectedAt,
    host: observation.host,
    hostVersion: observation.hostVersion,
    pluginVersion: loaded.manifest.version,
    reportId: observation.reportId,
    requiredCapabilities: [...loaded.manifest.requiredCapabilities],
    optionalCapabilities: [...loaded.manifest.optionalCapabilities],
    observations: observation.observations,
    hookTrust: observation.hookTrust,
    declaredHookEvents: [...loaded.declaredHookEvents],
    observedHookEvents: observation.observedHookEvents,
    knownToolPaths: observation.knownToolPaths,
    observedToolPaths: observation.observedToolPaths,
  });
  const health = buildPluginHealthReport({
    capabilityReport: report,
    generatedAt: observation.generatedAt,
    healthId: observation.healthId,
    profile: observation.profile,
  });
  const degradedCapabilities = Object.keys(report.capabilities)
    .filter((name) => report.capabilities[name].state !== "SUPPORTED")
    .sort();
  const preimage = {
    blockers: [...report.blockers],
    capability_report_hash: report.report_hash,
    degraded_capabilities: degradedCapabilities,
    denied_authority: [...loaded.deniedAuthority],
    health_report_hash: health.report_hash,
    host: report.host,
    mode: report.mode,
    overall: health.overall,
    plugin_id: loaded.manifest.pluginId,
    profile: health.profile,
    required_capabilities: [...loaded.manifest.requiredCapabilities],
    version: loaded.manifest.version,
  };
  const receiptHash = sha256HookJson(preimage);
  return Object.freeze({
    health,
    receipt: Object.freeze({
      integration_id: `EFG06-INTEGRATION-${receiptHash.slice("sha256:".length, "sha256:".length + 16)}`,
      ...preimage,
      receipt_hash: receiptHash,
    }),
    report,
  });
};

/**
 * An immutable receipt for the package: what it read, what it bound and the hash
 * of exactly those bytes.  Every declaring source is named with its digest, so a
 * later run can prove whether the package it validated is the package that
 * shipped.  It carries no clock and no randomness.
 */
export const packagingReceipt = (loaded) => {
  const sourcePaths = [
    MANIFEST_PATH,
    CAPABILITY_MANIFEST_SCHEMA_PATH,
    SKILL_LOCKFILE_SCHEMA_PATH,
    INVENTORY_PATH,
    SURFACE_PATH,
    MCP_CONFIG_PATH,
    ...loaded.manifest.hookBundles.map((bundle) => `${HOOKS_ROOT}/${bundle}.json`),
  ].sort();
  const sources = sourcePaths.map((path) => ({
    path,
    sha256: sha256Bytes(readBytes(loaded.root, path)),
  }));
  const preimage = {
    authority_bearing_commands: [...loaded.authorityBearingCommands],
    authority_bearing_commands_projected: [...loaded.authorityBearingProjected],
    cli_command_count: loaded.manifest.cliCommands.length,
    declared_hook_events: [...loaded.declaredHookEvents],
    denied_authority: [...loaded.deniedAuthority],
    discoverable_skill_count: loaded.inventorySkillIds.length,
    discoverable_skills: [...loaded.inventorySkillIds],
    evolution_backend_skill: loaded.backendSkillId,
    evolution_skill_ids: [...loaded.evolutionSkillIds],
    host_surfaces: [...loaded.manifest.hostSurfaces],
    hook_bundles: [...loaded.manifest.hookBundles],
    inventory_hash: loaded.inventoryHash,
    mcp_servers: [...loaded.manifest.mcpServers],
    optional_capabilities: [...loaded.manifest.optionalCapabilities],
    plugin_id: loaded.manifest.pluginId,
    required_capabilities: [...loaded.manifest.requiredCapabilities],
    schema_version: loaded.manifest.schemaVersion,
    sources,
    version: loaded.manifest.version,
  };
  const receiptHash = sha256HookJson(preimage);
  return Object.freeze({
    receipt_id: `EFG06-PACKAGE-${receiptHash.slice("sha256:".length, "sha256:".length + 16)}`,
    ...preimage,
    receipt_hash: receiptHash,
  });
};
