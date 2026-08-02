// Public entry point for the Claude Code skills, agents and worktree adapter.
//
// The adapter validates and translates.  It does not create an agent file,
// launch a custom agent, open a worktree or grant any authority; every export
// here returns metadata or a typed refusal.

export {
  ADAPTER_ROOT,
  BINDING_DECLARATION_PATH,
  BINDING_STATUS,
  ClaudeAdapterError,
  FINDING_CODES,
  REPOSITORY_ROOT,
  ROLE_MAPPING_PATH,
  ROLE_REGISTRY_PATH,
  selectDeclared,
} from "./claude-declarations.mjs";

export {
  AGENT_SURFACES,
  agentTableHash,
  buildAgentDescriptorTable,
  canonicalAgentTable,
  describeAgent,
  deriveTools,
  DESCRIPTOR_FIELDS,
  isolationFor,
  ISOLATION_MODES,
  isWriteCapable,
  parseRoleMapping,
  parseRoleRegistry,
  ROLE_MAPPING_FIELDS,
  ROLE_REGISTRY_FIELDS,
} from "./role-adapter.mjs";

export {
  BINDING_SOURCE_PATHS,
  claudeBindingReceipt,
  DECLARATION_FIELDS,
  loadClaudeBinding,
  parseAgentFrontmatter,
} from "./agent-binding.mjs";

export {
  deriveWorktreePlan,
  PARALLEL_REQUEST_FIELDS,
  scopePrefix,
  scopesConflict,
  toWorktreePlan,
  verifyDisjoint,
  WORKTREE_ASSIGNMENT_FIELDS,
} from "./worktree-plan.mjs";
