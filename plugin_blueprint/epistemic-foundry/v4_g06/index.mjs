// Public entry point for the G06 native plugin packaging and skill-discovery
// integration gate.
//
// The gate is a declaration plus the refusals that keep it honest; nothing here
// installs a plugin, activates a skill, executes a command or holds state.

export {
  CAPABILITY_MANIFEST_SCHEMA_PATH,
  computeLockfileHash,
  deriveDiscoverableSkills,
  discoverLockfileSkills,
  FINDING_CODES,
  HOOKS_ROOT,
  integratePackage,
  INVENTORY_PATH,
  loadPackage,
  MANIFEST_PATH,
  MCP_CONFIG_PATH,
  packagingReceipt,
  PluginPackagingError,
  REPOSITORY_ROOT,
  SKILL_LOCKFILE_SCHEMA_PATH,
  SURFACE_PATH,
} from "./packaging.mjs";
