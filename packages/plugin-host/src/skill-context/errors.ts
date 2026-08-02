export const SKILL_CONTEXT_ERROR_CODES = Object.freeze([
  "TOKENIZER_CONTRACT_UNAVAILABLE",
  "INITIAL_SKILL_METADATA_BUDGET_EXCEEDED",
  "HOST_SKILL_METADATA_BUDGET_INSUFFICIENT",
  "REFERENCE_CONTEXT_BUDGET_EXCEEDED",
  "REFERENCE_DEPTH_EXCEEDED",
  "REFERENCE_TARGET_MISSING",
  "REFERENCE_GRAPH_CYCLE",
  "REFERENCE_PATH_TRAVERSAL",
  "REFERENCE_SYMLINK_DENIED",
  "REFERENCE_HARDLINK_DENIED",
  "REFERENCE_CONTENT_DRIFT",
  "REFERENCE_AUTHORITY_STALE",
  "REFERENCE_DISABLED",
  "UNKNOWN_REFERENCE_PROPOSAL",
  "REFERENCE_EXPLICIT_AUTHORITY_REQUIRED",
  "SKILL_INVOCATION_POLICY_DRIFT",
  "INVENTORY_HASH_MISMATCH",
  "INVENTORY_CONTRACT_INVALID",
  "INVALID_SKILL_CONTEXT_INPUT",
  "INVALID_ROUTING_DECISION",
  "UNKNOWN_SKILL",
  "INVOCATION_DISPOSITION_DENIED",
] as const);

export type SkillContextErrorCode = (typeof SKILL_CONTEXT_ERROR_CODES)[number];

export class SkillContextError extends Error {
  readonly code: SkillContextErrorCode;
  readonly details: Readonly<Record<string, unknown>>;

  constructor(
    code: SkillContextErrorCode,
    message: string,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "SkillContextError";
    this.code = code;
    this.details = Object.freeze({ ...details });
  }
}

export const failSkillContext = (
  code: SkillContextErrorCode,
  message: string,
  details: Record<string, unknown> = {},
): never => {
  throw new SkillContextError(code, message, details);
};

export const errorCodeOf = (candidate: unknown): string | null =>
  candidate instanceof SkillContextError ? candidate.code : null;
