import { failSkillContext } from "./errors.ts";
import { types as utilTypes } from "node:util";
import type {
  HostMetadataBudget,
  MetadataProjectionSeal,
  SkillContextBudgets,
} from "./types.ts";

export const CANONICAL_SKILL_CONTEXT_BUDGETS: Readonly<SkillContextBudgets> =
  Object.freeze({
    initial_metadata_max_utf8_bytes: 6400,
    initial_metadata_max_o200k_tokens: 1600,
    skill_body_max_utf8_bytes: 4096,
    skill_body_max_o200k_tokens: 1024,
    reference_file_max_utf8_bytes: 4096,
    reference_file_max_o200k_tokens: 1024,
    reference_closure_max_count: 12,
    reference_closure_max_depth: 5,
    reference_closure_max_utf8_bytes: 24576,
    reference_closure_max_o200k_tokens: 6144,
    activation_max_utf8_bytes: 28672,
    activation_max_o200k_tokens: 7168,
  });

const requireNonNegativeSafeInteger = (value: unknown, label: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) {
    failSkillContext(
      "INVENTORY_CONTRACT_INVALID",
      `${label} must be a non-negative safe integer`,
    );
  }
  return value as number;
};

const HOST_METADATA_BUDGET_KEYS = Object.freeze([
  "byte_budget",
  "character_budget",
  "token_budget",
  "parent_explicitly_reachable",
]);

export const validateHostMetadataBudget = (
  candidate: HostMetadataBudget | undefined,
): HostMetadataBudget | undefined => {
  if (candidate === undefined) return undefined;
  if (
    candidate === null ||
    typeof candidate !== "object" ||
    Array.isArray(candidate) ||
    utilTypes.isProxy(candidate) ||
    Object.getPrototypeOf(candidate) !== Object.prototype
  ) {
    failSkillContext(
      "INVALID_SKILL_CONTEXT_INPUT",
      "host_metadata_budget must be a plain data object",
    );
  }
  const descriptors = Object.getOwnPropertyDescriptors(candidate);
  const actualKeys = Reflect.ownKeys(candidate);
  if (
    actualKeys.some((key) => typeof key !== "string") ||
    actualKeys.some((key) => !HOST_METADATA_BUDGET_KEYS.includes(key as string)) ||
    Object.values(descriptors).some(
      (descriptor) => !descriptor.enumerable || !("value" in descriptor),
    )
  ) {
    failSkillContext(
      "INVALID_SKILL_CONTEXT_INPUT",
      "host_metadata_budget has unexpected or non-data fields",
    );
  }
  const record = candidate as Record<string, unknown>;
  for (const key of ["byte_budget", "character_budget", "token_budget"] as const) {
    if (Object.hasOwn(record, key)) requireNonNegativeSafeInteger(record[key], `host ${key}`);
  }
  if (
    Object.hasOwn(record, "parent_explicitly_reachable") &&
    typeof record.parent_explicitly_reachable !== "boolean"
  ) {
    failSkillContext(
      "INVALID_SKILL_CONTEXT_INPUT",
      "host parent_explicitly_reachable must be boolean",
    );
  }
  return Object.freeze({ ...candidate });
};

export const assertCanonicalBudgetContract = (candidate: SkillContextBudgets): void => {
  const actualKeys = Object.keys(candidate).sort();
  const expectedKeys = Object.keys(CANONICAL_SKILL_CONTEXT_BUDGETS).sort();
  if (
    actualKeys.length !== expectedKeys.length ||
    actualKeys.some((key, index) => key !== expectedKeys[index])
  ) {
    failSkillContext(
      "INVENTORY_CONTRACT_INVALID",
      "inventory budgets have missing or unexpected fields",
      { actual: actualKeys, expected: expectedKeys },
    );
  }
  for (const [key, expected] of Object.entries(CANONICAL_SKILL_CONTEXT_BUDGETS)) {
    const observed = candidate[key as keyof SkillContextBudgets];
    if (observed !== expected) {
      failSkillContext(
        "INVENTORY_CONTRACT_INVALID",
        `inventory budget ${key} must equal the canonical J02 limit`,
        { expected, observed },
      );
    }
  }
};

export const assertReferenceFileBudget = (
  byteCount: number,
  tokenCount: number,
  budgets: SkillContextBudgets = CANONICAL_SKILL_CONTEXT_BUDGETS,
): void => {
  requireNonNegativeSafeInteger(byteCount, "reference byte_count");
  requireNonNegativeSafeInteger(tokenCount, "reference token_count");
  if (
    byteCount > budgets.reference_file_max_utf8_bytes ||
    tokenCount > budgets.reference_file_max_o200k_tokens
  ) {
    failSkillContext(
      "REFERENCE_CONTEXT_BUDGET_EXCEEDED",
      "one atomic reference exceeds a canonical file budget",
      { byte_count: byteCount, token_count: tokenCount },
    );
  }
};

export const assertInitialMetadataBudget = (
  seal: MetadataProjectionSeal,
  skillCount: number,
  budgets: SkillContextBudgets = CANONICAL_SKILL_CONTEXT_BUDGETS,
): void => {
  const bytes = requireNonNegativeSafeInteger(seal.byte_count, "metadata byte_count");
  const tokens = requireNonNegativeSafeInteger(seal.token_count, "metadata token_count");
  if (
    skillCount !== 29 ||
    bytes > budgets.initial_metadata_max_utf8_bytes ||
    tokens > budgets.initial_metadata_max_o200k_tokens
  ) {
    failSkillContext(
      "INITIAL_SKILL_METADATA_BUDGET_EXCEEDED",
      "all 29 canonical skill metadata entries must fit both initial budgets",
      { bytes, tokens, skill_count: skillCount },
    );
  }
};

export const effectiveHostMetadataBudgets = (
  host: HostMetadataBudget | undefined,
  budgets: SkillContextBudgets = CANONICAL_SKILL_CONTEXT_BUDGETS,
): { bytes: number; tokens: number } => {
  host = validateHostMetadataBudget(host);
  let bytes = budgets.initial_metadata_max_utf8_bytes;
  let tokens = budgets.initial_metadata_max_o200k_tokens;
  if (host?.byte_budget !== undefined) {
    bytes = Math.min(bytes, requireNonNegativeSafeInteger(host.byte_budget, "host byte_budget"));
  }
  if (host?.character_budget !== undefined) {
    // A one-byte-per-character projection is deliberately conservative for UTF-8.
    bytes = Math.min(
      bytes,
      requireNonNegativeSafeInteger(host.character_budget, "host character_budget"),
    );
  }
  if (host?.token_budget !== undefined) {
    tokens = Math.min(
      tokens,
      requireNonNegativeSafeInteger(host.token_budget, "host token_budget"),
    );
  }
  return { bytes, tokens };
};

export const metadataFitsHost = (
  seal: MetadataProjectionSeal,
  host: HostMetadataBudget | undefined,
  budgets: SkillContextBudgets = CANONICAL_SKILL_CONTEXT_BUDGETS,
): boolean => {
  const effective = effectiveHostMetadataBudgets(host, budgets);
  return seal.byte_count <= effective.bytes && seal.token_count <= effective.tokens;
};

export interface ActivationBudgetCandidate {
  skill_bytes: number;
  skill_tokens: number;
  reference_count: number;
  reference_depth: number;
  reference_bytes: number;
  reference_tokens: number;
}

export const assertActivationBudget = (
  candidate: ActivationBudgetCandidate,
  budgets: SkillContextBudgets = CANONICAL_SKILL_CONTEXT_BUDGETS,
): void => {
  for (const [key, value] of Object.entries(candidate)) {
    requireNonNegativeSafeInteger(value, key);
  }
  if (candidate.reference_depth > budgets.reference_closure_max_depth) {
    failSkillContext(
      "REFERENCE_DEPTH_EXCEEDED",
      "reference dependency depth exceeds the canonical maximum",
      { observed: candidate.reference_depth, maximum: budgets.reference_closure_max_depth },
    );
  }

  const totalBytes = candidate.skill_bytes + candidate.reference_bytes;
  const totalTokens = candidate.skill_tokens + candidate.reference_tokens;
  if (
    candidate.skill_bytes > budgets.skill_body_max_utf8_bytes ||
    candidate.skill_tokens > budgets.skill_body_max_o200k_tokens ||
    candidate.reference_count > budgets.reference_closure_max_count ||
    candidate.reference_bytes > budgets.reference_closure_max_utf8_bytes ||
    candidate.reference_tokens > budgets.reference_closure_max_o200k_tokens ||
    totalBytes > budgets.activation_max_utf8_bytes ||
    totalTokens > budgets.activation_max_o200k_tokens
  ) {
    failSkillContext(
      "REFERENCE_CONTEXT_BUDGET_EXCEEDED",
      "the mandatory skill and reference closure exceeds a canonical activation budget",
      {
        ...candidate,
        total_activation_bytes: totalBytes,
        total_activation_tokens: totalTokens,
      },
    );
  }
};
