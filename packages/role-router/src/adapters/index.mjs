export {
  ADAPTER_CONTRACT_VERSION,
  ADAPTER_HOSTS,
  EXECUTION_ENVELOPE_SCHEMA_REF,
  HOST_EXECUTION_CAPABILITIES,
  SPAWN_DESCRIPTOR_REQUIRED_FIELDS,
  AdapterContractError,
  compileRoleSpawnDescriptor,
  sha256AdapterJson,
  verifyAdapterHostCapabilityReport,
  verifySpawnDescriptorIntegrity,
} from "./adapter-contract.mjs";
export { compileClaudeSpawnDescriptor } from "./claude-adapter.mjs";
export { compileCodexSpawnDescriptor } from "./codex-adapter.mjs";
