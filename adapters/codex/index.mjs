// Public entry point for the Codex plugin, hook and subagent adapter.
//
// The adapter validates and translates.  It does not install the plugin, run a
// hook, launch a subagent, or grant any authority; every export here returns
// metadata or a typed refusal.

export {
  ADAPTER_ROOT,
  BINDING_DECLARATION_PATH,
  BINDING_STATUS,
  CodexAdapterError,
  FINDING_CODES,
  PAYLOAD_ROOT,
  PLUGIN_MANIFEST_PATH,
  REPOSITORY_ROOT,
  ROLE_MAPPING_PATH,
  ROLE_REGISTRY_PATH,
  selectDeclared,
} from "./codex-declarations.mjs";

export {
  BINDING_SOURCE_PATHS,
  codexBindingReceipt,
  DECLARATION_FIELDS,
  deriveCoverage,
  deriveVerbIndex,
  loadCodexBinding,
  parseDispatcherTarget,
} from "./plugin-binding.mjs";

export {
  buildRoleDescriptorTable,
  canonicalRoleTable,
  describeRole,
  descriptorNameFor,
  DESCRIPTOR_FIELDS,
  parseRoleMapping,
  parseRoleRegistry,
  promptSourceFor,
  ROLE_MAPPING_FIELDS,
  ROLE_REGISTRY_FIELDS,
  roleTableHash,
} from "./role-adapter.mjs";

export {
  dispatchRawCodexEvent,
  HOOK_REQUEST_FIELDS,
  RAW_EVENT_FIELDS,
  toHookRequest,
  verifyBridgedEnvelope,
} from "./hook-bridge.mjs";
