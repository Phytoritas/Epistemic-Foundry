export type InvocationDisposition =
  | "PARENT_ROUTER"
  | "IMPLICIT_SAFE"
  | "PARENT_ROUTED"
  | "EXPLICIT_ONLY";

export type ReferenceSelectionMode =
  | "REQUIRED"
  | "CONDITIONAL"
  | "EXPLICIT_ONLY"
  | "DISABLED";

export type PredicateKey =
  | "work_class"
  | "forge_phase"
  | "request_signal"
  | "artifact_kind"
  | "capability"
  | "backend_id"
  | "candidate_origin"
  | "operation"
  | "status";

export type PredicateOperator = "EQUALS" | "IN" | "ANY_OF" | "ALL_OF";

export interface ReferencePredicate {
  key: PredicateKey;
  operator: PredicateOperator;
  value: string | string[];
}

export interface ConditionalReference {
  reference_id: string;
  mode: "CONDITIONAL";
  predicate: ReferencePredicate;
}

export interface AuthoritySource {
  path: string;
  sha256: string;
}

export interface SkillInventoryEntry {
  skill_id: string;
  name: string;
  description: string;
  path: string;
  status: "ACTIVE";
  invocation_disposition: InvocationDisposition;
  allow_implicit_invocation: boolean;
  sha256: string;
  byte_count: number;
  token_count: number;
  direct_references: string[];
  conditional_references: ConditionalReference[];
  child_skills: string[];
}

export interface ReferenceInventoryEntry {
  reference_id: string;
  path: string;
  mode: ReferenceSelectionMode;
  depends_on: string[];
  sha256: string;
  byte_count: number;
  token_count: number;
  authority_sources: AuthoritySource[];
  media_type: "text/markdown";
  status: "ACTIVE" | "DISABLED";
}

export interface TokenizerLock {
  package: "tiktoken";
  version: "0.13.0";
  encoding: "o200k_base";
  disallowed_special: [];
  dependency_artifact: {
    artifact_kind: "sdist";
    filename: "tiktoken-0.13.0.tar.gz";
    sha256: string;
    source_url: string;
  };
}

export interface SkillContextBudgets {
  initial_metadata_max_utf8_bytes: 6400;
  initial_metadata_max_o200k_tokens: 1600;
  skill_body_max_utf8_bytes: 4096;
  skill_body_max_o200k_tokens: 1024;
  reference_file_max_utf8_bytes: 4096;
  reference_file_max_o200k_tokens: 1024;
  reference_closure_max_count: 12;
  reference_closure_max_depth: 5;
  reference_closure_max_utf8_bytes: 24576;
  reference_closure_max_o200k_tokens: 6144;
  activation_max_utf8_bytes: 28672;
  activation_max_o200k_tokens: 7168;
}

export interface MetadataProjectionSeal {
  sha256: string;
  byte_count: number;
  token_count: number;
}

export interface SkillInventory {
  inventory_id: string;
  inventory_version: string;
  inventory_hash: string;
  parent_skill_id: "foundry";
  tokenizer: TokenizerLock;
  budgets: SkillContextBudgets;
  metadata_projection: MetadataProjectionSeal;
  skills: SkillInventoryEntry[];
  references: ReferenceInventoryEntry[];
}

export type ConditionValues = Partial<Record<PredicateKey, string | string[]>>;

export interface ExactInvocationAuthority {
  kind: "PARENT_PLAN" | "ACTION_INTENT" | "HUMAN_DECISION" | "POLICY";
  skill_id: string;
  exact_authorized: true;
  authority_id: string;
}

export interface ReferenceProposal {
  reference_id: string;
  reason: string;
  source_span?: string;
  typed_trigger_candidate?: ReferencePredicate;
}

export interface ReferenceSelectionReason {
  reference_id: string;
  reason:
    | "CORE_CONSTITUTION"
    | "TRANSITIVE_PREREQUISITE"
    | "DIRECT_REQUIRED"
    | "MATCHING_CONDITIONAL"
    | "EXPLICIT_ONLY";
}

export interface SelectionResult {
  selected_skill_id: string;
  ordered_reference_ids: string[];
  reference_selection_reasons: ReferenceSelectionReason[];
  transitive_depth: number;
  warnings: string[];
}

export interface HostMetadataBudget {
  byte_budget?: number;
  character_budget?: number;
  token_budget?: number;
  parent_explicitly_reachable?: boolean;
}

export interface MetadataProjectionResult {
  text: string;
  sha256: string;
  byte_count: number;
  token_count: number;
  skill_count: number;
  degraded_mode: "NONE" | "EXPLICIT_PARENT_ONLY";
  warnings: string[];
}

export interface ResolvedSkillContext {
  inventory_id: string;
  inventory_hash: string;
  routing_decision_id: string;
  selected_skill_id: string;
  skill_path: string;
  skill_sha256: string;
  skill_byte_count: number;
  skill_token_count: number;
  ordered_reference_ids: string[];
  ordered_reference_paths: string[];
  reference_hashes: Array<{ reference_id: string; sha256: string }>;
  reference_selection_reasons: ReferenceSelectionReason[];
  transitive_depth: number;
  total_reference_bytes: number;
  total_reference_tokens: number;
  total_activation_bytes: number;
  total_activation_tokens: number;
  invocation_disposition: InvocationDisposition;
  degraded_mode: "NONE" | "EXPLICIT_PARENT_ONLY";
  warnings: string[];
  errors: string[];
  context_hash: string;
}

export interface SkillRoutingDecisionLike {
  decision_id: string;
  request_id: string;
  mode: "implicit" | "explicit" | "none";
  candidates: unknown[];
  selected_skill_ids: string[];
  rejected_skill_ids: string[];
  context_budget_tokens: number;
  authority_notes: string[];
  policy_hash: string;
  decided_at: string;
  decision_hash: string;
}

export interface ResolveSkillContextOptions {
  plugin_root: string;
  repository_root?: string;
  routing_decision: SkillRoutingDecisionLike;
  conditions?: ConditionValues;
  invocation_authority?: ExactInvocationAuthority;
  explicit_reference_ids?: string[];
  explicit_reference_authority_ids?: string[];
  llm_proposals?: ReferenceProposal[];
  host_metadata_budget?: HostMetadataBudget;
}

export interface ReachabilityReport {
  parent_count: number;
  child_count: number;
  reachable_child_count: number;
  unreachable_child_ids: string[];
  orphan_skill_ids: string[];
  reference_count: number;
  reachable_reference_count: number;
  orphan_reference_ids: string[];
  maximum_closure_count: number;
  maximum_transitive_depth: number;
  graph_integrity_errors: string[];
}
