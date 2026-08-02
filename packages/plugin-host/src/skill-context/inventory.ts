import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

import {
  assertCanonicalBudgetContract,
  assertInitialMetadataBudget,
  assertReferenceFileBudget,
} from "./budget.ts";
import { failSkillContext } from "./errors.ts";
import type {
  ConditionalReference,
  InvocationDisposition,
  MetadataProjectionSeal,
  PredicateKey,
  PredicateOperator,
  ReferenceInventoryEntry,
  ReferenceSelectionMode,
  SkillInventory,
  SkillInventoryEntry,
} from "./types.ts";

const HASH_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const ID_PATTERN = /^[A-Za-z0-9]+(?:[-_.][A-Za-z0-9]+)*$/u;
const ASCII_PATTERN = /^[\x20-\x7e]+$/u;
const CONTROL_PATTERN = /[\x00-\x1f\x7f]/u;
const URI_PATTERN = /^[A-Za-z][A-Za-z0-9+.-]*:/u;
const WINDOWS_DRIVE_PATTERN = /^[A-Za-z]:/u;
const TOKENIZER_SDIST_SHA256 =
  "sha256:c9435714c3a84c2319499de9a300c0e604449dd0799ff246458b3bb6a7f433c1";

const INVOCATION_DISPOSITIONS = new Set<InvocationDisposition>([
  "PARENT_ROUTER",
  "IMPLICIT_SAFE",
  "PARENT_ROUTED",
  "EXPLICIT_ONLY",
]);
const REFERENCE_MODES = new Set<ReferenceSelectionMode>([
  "REQUIRED",
  "CONDITIONAL",
  "EXPLICIT_ONLY",
  "DISABLED",
]);
const PREDICATE_KEYS = new Set<PredicateKey>([
  "work_class",
  "forge_phase",
  "request_signal",
  "artifact_kind",
  "capability",
  "backend_id",
  "candidate_origin",
  "operation",
  "status",
]);
const PREDICATE_OPERATORS = new Set<PredicateOperator>([
  "EQUALS",
  "IN",
  "ANY_OF",
  "ALL_OF",
]);

export const EXPECTED_SKILL_IDS = Object.freeze([
  "foundry",
  "foundry-admin",
  "foundry-aporia",
  "foundry-archive",
  "foundry-atlas",
  "foundry-challenge",
  "foundry-claim-forge",
  "foundry-domain-pack",
  "foundry-evaluator-audit",
  "foundry-evolution-replay",
  "foundry-evolution-stop",
  "foundry-evolve",
  "foundry-evolve-convert",
  "foundry-evolve-inspect",
  "foundry-evolve-run",
  "foundry-evolve-setup",
  "foundry-intake",
  "foundry-map",
  "foundry-observe",
  "foundry-parliament",
  "foundry-passport",
  "foundry-plugin-dev",
  "foundry-promote-evolved",
  "foundry-reason",
  "foundry-recall",
  "foundry-replay",
  "foundry-replicate",
  "foundry-shinka-adapter",
  "foundry-validation",
]);

export const EXPECTED_REFERENCE_IDS = Object.freeze([
  "EFREF-BACKEND-SHINKA-V4",
  "EFREF-CONTEXT-MEMORY-REPLAY-V4",
  "EFREF-CORE-CONSTITUTION-V4",
  "EFREF-CORE-STATUS-RECEIPTS-V4",
  "EFREF-EVIDENCE-CLAIM-SEARCH-V4",
  "EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4",
  "EFREF-EVOLUTION-ARCHIVE-REDQUEEN-V4",
  "EFREF-EVOLUTION-RUN-GENOMES-V4",
  "EFREF-EVOLUTION-VERIFIER-STATISTICS-V4",
  "EFREF-EXTENSIONS-MAP-DOMAINPACK-V4",
  "EFREF-PARLIAMENT-ASYMMETRIC-GATES-V4",
  "EFREF-PASSPORT-PROMOTION-V4",
  "EFREF-PLUGIN-DEVELOPMENT-RELEASE-V4",
  "EFREF-PLUGIN-SECURITY-ADMIN-V4",
  "EFREF-REASONING-TYPED-MODES-V4",
  "EFREF-ROUTER-E0-E5-V4",
  "EFREF-VALIDATION-REPLICATION-V4",
]);

const APPROVED_SKILL_DISPOSITIONS: Readonly<Record<string, InvocationDisposition>> =
  Object.freeze({
    foundry: "PARENT_ROUTER",
    "foundry-admin": "EXPLICIT_ONLY",
    "foundry-aporia": "IMPLICIT_SAFE",
    "foundry-archive": "PARENT_ROUTED",
    "foundry-atlas": "IMPLICIT_SAFE",
    "foundry-challenge": "PARENT_ROUTED",
    "foundry-claim-forge": "IMPLICIT_SAFE",
    "foundry-domain-pack": "EXPLICIT_ONLY",
    "foundry-evaluator-audit": "PARENT_ROUTED",
    "foundry-evolution-replay": "EXPLICIT_ONLY",
    "foundry-evolution-stop": "EXPLICIT_ONLY",
    "foundry-evolve": "PARENT_ROUTED",
    "foundry-evolve-convert": "EXPLICIT_ONLY",
    "foundry-evolve-inspect": "IMPLICIT_SAFE",
    "foundry-evolve-run": "EXPLICIT_ONLY",
    "foundry-evolve-setup": "PARENT_ROUTED",
    "foundry-intake": "IMPLICIT_SAFE",
    "foundry-map": "IMPLICIT_SAFE",
    "foundry-observe": "IMPLICIT_SAFE",
    "foundry-parliament": "PARENT_ROUTED",
    "foundry-passport": "IMPLICIT_SAFE",
    "foundry-plugin-dev": "EXPLICIT_ONLY",
    "foundry-promote-evolved": "EXPLICIT_ONLY",
    "foundry-reason": "IMPLICIT_SAFE",
    "foundry-recall": "EXPLICIT_ONLY",
    "foundry-replay": "EXPLICIT_ONLY",
    "foundry-replicate": "EXPLICIT_ONLY",
    "foundry-shinka-adapter": "EXPLICIT_ONLY",
    "foundry-validation": "EXPLICIT_ONLY",
  });

const APPROVED_DIRECT_REFERENCES: Readonly<Record<string, readonly string[]>> =
  Object.freeze({
    foundry: ["EFREF-CORE-CONSTITUTION-V4", "EFREF-ROUTER-E0-E5-V4"],
    "foundry-admin": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-CORE-STATUS-RECEIPTS-V4",
      "EFREF-PLUGIN-SECURITY-ADMIN-V4",
      "EFREF-PLUGIN-DEVELOPMENT-RELEASE-V4",
    ],
    "foundry-aporia": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4",
      "EFREF-REASONING-TYPED-MODES-V4",
    ],
    "foundry-archive": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EVOLUTION-RUN-GENOMES-V4",
      "EFREF-EVOLUTION-ARCHIVE-REDQUEEN-V4",
    ],
    "foundry-atlas": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EVIDENCE-CLAIM-SEARCH-V4",
      "EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4",
    ],
    "foundry-challenge": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EVOLUTION-VERIFIER-STATISTICS-V4",
      "EFREF-EVOLUTION-ARCHIVE-REDQUEEN-V4",
    ],
    "foundry-claim-forge": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EVIDENCE-CLAIM-SEARCH-V4",
      "EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4",
    ],
    "foundry-domain-pack": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4",
      "EFREF-EXTENSIONS-MAP-DOMAINPACK-V4",
    ],
    "foundry-evaluator-audit": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-VALIDATION-REPLICATION-V4",
      "EFREF-EVOLUTION-VERIFIER-STATISTICS-V4",
    ],
    "foundry-evolution-replay": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EVOLUTION-RUN-GENOMES-V4",
      "EFREF-CONTEXT-MEMORY-REPLAY-V4",
    ],
    "foundry-evolution-stop": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-CORE-STATUS-RECEIPTS-V4",
      "EFREF-EVOLUTION-RUN-GENOMES-V4",
    ],
    "foundry-evolve": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-ROUTER-E0-E5-V4",
      "EFREF-EVOLUTION-RUN-GENOMES-V4",
    ],
    "foundry-evolve-convert": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EVOLUTION-RUN-GENOMES-V4",
    ],
    "foundry-evolve-inspect": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EVOLUTION-RUN-GENOMES-V4",
      "EFREF-EVOLUTION-ARCHIVE-REDQUEEN-V4",
    ],
    "foundry-evolve-run": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EVOLUTION-RUN-GENOMES-V4",
      "EFREF-EVOLUTION-VERIFIER-STATISTICS-V4",
      "EFREF-EVOLUTION-ARCHIVE-REDQUEEN-V4",
    ],
    "foundry-evolve-setup": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-ROUTER-E0-E5-V4",
      "EFREF-EVOLUTION-RUN-GENOMES-V4",
      "EFREF-EVOLUTION-VERIFIER-STATISTICS-V4",
    ],
    "foundry-intake": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-ROUTER-E0-E5-V4",
      "EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4",
    ],
    "foundry-map": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EXTENSIONS-MAP-DOMAINPACK-V4",
    ],
    "foundry-observe": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EVIDENCE-CLAIM-SEARCH-V4",
      "EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4",
    ],
    "foundry-parliament": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-PARLIAMENT-ASYMMETRIC-GATES-V4",
    ],
    "foundry-passport": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-PASSPORT-PROMOTION-V4",
    ],
    "foundry-plugin-dev": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-PLUGIN-SECURITY-ADMIN-V4",
      "EFREF-PLUGIN-DEVELOPMENT-RELEASE-V4",
    ],
    "foundry-promote-evolved": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-PASSPORT-PROMOTION-V4",
      "EFREF-EVOLUTION-VERIFIER-STATISTICS-V4",
      "EFREF-EVOLUTION-ARCHIVE-REDQUEEN-V4",
    ],
    "foundry-reason": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4",
      "EFREF-REASONING-TYPED-MODES-V4",
    ],
    "foundry-recall": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-CONTEXT-MEMORY-REPLAY-V4",
    ],
    "foundry-replay": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-CORE-STATUS-RECEIPTS-V4",
      "EFREF-CONTEXT-MEMORY-REPLAY-V4",
    ],
    "foundry-replicate": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-VALIDATION-REPLICATION-V4",
      "EFREF-EVOLUTION-VERIFIER-STATISTICS-V4",
    ],
    "foundry-shinka-adapter": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-BACKEND-SHINKA-V4",
    ],
    "foundry-validation": [
      "EFREF-CORE-CONSTITUTION-V4",
      "EFREF-VALIDATION-REPLICATION-V4",
      "EFREF-EVOLUTION-VERIFIER-STATISTICS-V4",
    ],
  });

const APPROVED_CONDITIONAL_REFERENCES: Readonly<
  Record<string, readonly ConditionalReference[]>
> = Object.freeze({
  "foundry-evolve-convert": [
    {
      reference_id: "EFREF-BACKEND-SHINKA-V4",
      mode: "CONDITIONAL",
      predicate: { key: "backend_id", operator: "EQUALS", value: "shinka" },
    },
  ],
  "foundry-parliament": [
    {
      reference_id: "EFREF-EVOLUTION-VERIFIER-STATISTICS-V4",
      mode: "CONDITIONAL",
      predicate: {
        key: "candidate_origin",
        operator: "EQUALS",
        value: "EVOLUTION",
      },
    },
  ],
  "foundry-passport": [
    {
      reference_id: "EFREF-VALIDATION-REPLICATION-V4",
      mode: "CONDITIONAL",
      predicate: {
        key: "artifact_kind",
        operator: "ANY_OF",
        value: ["ValidationResult", "ReplicationResult"],
      },
    },
  ],
});

const APPROVED_REFERENCE_CONTRACT: Readonly<
  Record<string, { path: string; mode: ReferenceSelectionMode; depends_on: readonly string[] }>
> = Object.freeze({
  "EFREF-BACKEND-SHINKA-V4": {
    path: "skills/foundry/references/backends/shinka.md",
    mode: "CONDITIONAL",
    depends_on: [
      "EFREF-EVOLUTION-RUN-GENOMES-V4",
      "EFREF-PLUGIN-SECURITY-ADMIN-V4",
    ],
  },
  "EFREF-CONTEXT-MEMORY-REPLAY-V4": {
    path: "skills/foundry/references/context/memory-replay.md",
    mode: "REQUIRED",
    depends_on: ["EFREF-CORE-STATUS-RECEIPTS-V4", "EFREF-ROUTER-E0-E5-V4"],
  },
  "EFREF-CORE-CONSTITUTION-V4": {
    path: "skills/foundry/references/core/constitution.md",
    mode: "REQUIRED",
    depends_on: [],
  },
  "EFREF-CORE-STATUS-RECEIPTS-V4": {
    path: "skills/foundry/references/core/status-receipts.md",
    mode: "REQUIRED",
    depends_on: ["EFREF-CORE-CONSTITUTION-V4"],
  },
  "EFREF-EVIDENCE-CLAIM-SEARCH-V4": {
    path: "skills/foundry/references/evidence/claim-search.md",
    mode: "REQUIRED",
    depends_on: ["EFREF-CORE-CONSTITUTION-V4"],
  },
  "EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4": {
    path: "skills/foundry/references/evidence/scope-method-dependency.md",
    mode: "REQUIRED",
    depends_on: ["EFREF-EVIDENCE-CLAIM-SEARCH-V4"],
  },
  "EFREF-EVOLUTION-ARCHIVE-REDQUEEN-V4": {
    path: "skills/foundry/references/evolution/archive-red-queen.md",
    mode: "REQUIRED",
    depends_on: [
      "EFREF-EVOLUTION-RUN-GENOMES-V4",
      "EFREF-EVOLUTION-VERIFIER-STATISTICS-V4",
    ],
  },
  "EFREF-EVOLUTION-RUN-GENOMES-V4": {
    path: "skills/foundry/references/evolution/run-genomes.md",
    mode: "REQUIRED",
    depends_on: ["EFREF-CORE-STATUS-RECEIPTS-V4", "EFREF-ROUTER-E0-E5-V4"],
  },
  "EFREF-EVOLUTION-VERIFIER-STATISTICS-V4": {
    path: "skills/foundry/references/evolution/verifier-statistics.md",
    mode: "CONDITIONAL",
    depends_on: [
      "EFREF-VALIDATION-REPLICATION-V4",
      "EFREF-EVOLUTION-RUN-GENOMES-V4",
    ],
  },
  "EFREF-EXTENSIONS-MAP-DOMAINPACK-V4": {
    path: "skills/foundry/references/extensions/map-domain-pack.md",
    mode: "REQUIRED",
    depends_on: ["EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4"],
  },
  "EFREF-PARLIAMENT-ASYMMETRIC-GATES-V4": {
    path: "skills/foundry/references/parliament/asymmetric-gates.md",
    mode: "REQUIRED",
    depends_on: [
      "EFREF-CORE-STATUS-RECEIPTS-V4",
      "EFREF-EVIDENCE-CLAIM-SEARCH-V4",
      "EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4",
    ],
  },
  "EFREF-PASSPORT-PROMOTION-V4": {
    path: "skills/foundry/references/passport/promotion.md",
    mode: "REQUIRED",
    depends_on: [
      "EFREF-CORE-STATUS-RECEIPTS-V4",
      "EFREF-PARLIAMENT-ASYMMETRIC-GATES-V4",
    ],
  },
  "EFREF-PLUGIN-DEVELOPMENT-RELEASE-V4": {
    path: "skills/foundry/references/plugin/development-release.md",
    mode: "REQUIRED",
    depends_on: [
      "EFREF-CORE-STATUS-RECEIPTS-V4",
      "EFREF-PLUGIN-SECURITY-ADMIN-V4",
    ],
  },
  "EFREF-PLUGIN-SECURITY-ADMIN-V4": {
    path: "skills/foundry/references/plugin/security-administration.md",
    mode: "REQUIRED",
    depends_on: ["EFREF-CORE-CONSTITUTION-V4", "EFREF-CORE-STATUS-RECEIPTS-V4"],
  },
  "EFREF-REASONING-TYPED-MODES-V4": {
    path: "skills/foundry/references/reasoning/typed-modes.md",
    mode: "REQUIRED",
    depends_on: ["EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4"],
  },
  "EFREF-ROUTER-E0-E5-V4": {
    path: "skills/foundry/references/router/e0-e5-routing.md",
    mode: "REQUIRED",
    depends_on: ["EFREF-CORE-CONSTITUTION-V4"],
  },
  "EFREF-VALIDATION-REPLICATION-V4": {
    path: "skills/foundry/references/validation/replication.md",
    mode: "CONDITIONAL",
    depends_on: [
      "EFREF-CORE-STATUS-RECEIPTS-V4",
      "EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4",
    ],
  },
});

const APPROVED_AUTHORITY_SOURCE_PATHS = Object.freeze([
  "MASTER_SPEC.md",
  "artifacts/authority_decisions/HD-EF4-J02-SG001-20260729-001.human-decision.json",
  "docs/skill_context_contract.md",
]);

export const compareUtf8 = (left: string, right: string): number =>
  Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));

const requireRecord = (candidate: unknown, label: string): Record<string, unknown> => {
  if (
    candidate === null ||
    typeof candidate !== "object" ||
    Array.isArray(candidate) ||
    Object.getPrototypeOf(candidate) !== Object.prototype
  ) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} must be a JSON object`);
  }
  return candidate as Record<string, unknown>;
};

const requireExactKeys = (
  candidate: Record<string, unknown>,
  expected: readonly string[],
  label: string,
): void => {
  const actual = Object.keys(candidate).sort(compareUtf8);
  const wanted = [...expected].sort(compareUtf8);
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    failSkillContext(
      "INVENTORY_CONTRACT_INVALID",
      `${label} has missing or unexpected fields`,
      { actual, expected: wanted },
    );
  }
};

const requireString = (candidate: unknown, label: string): string => {
  if (typeof candidate !== "string" || candidate.length === 0) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} must be a non-empty string`);
  }
  return candidate;
};

const requireHash = (candidate: unknown, label: string): string => {
  const value = requireString(candidate, label);
  if (!HASH_PATTERN.test(value)) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} must be canonical SHA-256`);
  }
  return value;
};

const requireCount = (candidate: unknown, label: string): number => {
  if (!Number.isSafeInteger(candidate) || (candidate as number) < 0) {
    failSkillContext(
      "INVENTORY_CONTRACT_INVALID",
      `${label} must be a non-negative safe integer`,
    );
  }
  return candidate as number;
};

const requireStringArray = (candidate: unknown, label: string): string[] => {
  if (!Array.isArray(candidate)) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} must be an array`);
  }
  const values = candidate.map((entry, index) => requireString(entry, `${label}[${index}]`));
  if (new Set(values).size !== values.length) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} contains duplicate values`);
  }
  return values;
};

const assertNormalizedRelativePath = (
  candidate: unknown,
  label: string,
  prefix: string,
): string => {
  const value = requireString(candidate, label);
  let decoded: string;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    failSkillContext("REFERENCE_PATH_TRAVERSAL", `${label} contains invalid percent encoding`);
  }
  if (
    value !== decoded ||
    !ASCII_PATTERN.test(value) ||
    CONTROL_PATTERN.test(value) ||
    value.includes("\\") ||
    value.startsWith("/") ||
    value.startsWith("//") ||
    WINDOWS_DRIVE_PATTERN.test(value) ||
    URI_PATTERN.test(value) ||
    value.split("/").some((part) => part === "" || part === "." || part === "..") ||
    path.posix.normalize(value) !== value ||
    !value.startsWith(prefix)
  ) {
    failSkillContext("REFERENCE_PATH_TRAVERSAL", `${label} is not a safe canonical path`, {
      path: value,
    });
  }
  return value;
};

const parseConditional = (candidate: unknown, label: string): ConditionalReference => {
  const record = requireRecord(candidate, label);
  requireExactKeys(record, ["reference_id", "mode", "predicate"], label);
  if (record.mode !== "CONDITIONAL") {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label}.mode must be CONDITIONAL`);
  }
  const predicate = requireRecord(record.predicate, `${label}.predicate`);
  requireExactKeys(predicate, ["key", "operator", "value"], `${label}.predicate`);
  const key = requireString(predicate.key, `${label}.predicate.key`) as PredicateKey;
  const operator = requireString(
    predicate.operator,
    `${label}.predicate.operator`,
  ) as PredicateOperator;
  if (!PREDICATE_KEYS.has(key) || !PREDICATE_OPERATORS.has(operator)) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} uses a non-canonical predicate`);
  }
  const value = Array.isArray(predicate.value)
    ? requireStringArray(predicate.value, `${label}.predicate.value`)
    : requireString(predicate.value, `${label}.predicate.value`);
  if ((operator === "EQUALS" || operator === "IN") && Array.isArray(value)) {
    failSkillContext(
      "INVENTORY_CONTRACT_INVALID",
      `${label} operator ${operator} requires one string`,
    );
  }
  if ((operator === "ANY_OF" || operator === "ALL_OF") && !Array.isArray(value)) {
    failSkillContext(
      "INVENTORY_CONTRACT_INVALID",
      `${label} operator ${operator} requires a string array`,
    );
  }
  return {
    reference_id: requireString(record.reference_id, `${label}.reference_id`),
    mode: "CONDITIONAL",
    predicate: { key, operator, value },
  };
};

const parseSkill = (candidate: unknown, index: number): SkillInventoryEntry => {
  const label = `skills[${index}]`;
  const record = requireRecord(candidate, label);
  requireExactKeys(
    record,
    [
      "skill_id",
      "name",
      "description",
      "path",
      "status",
      "invocation_disposition",
      "allow_implicit_invocation",
      "sha256",
      "byte_count",
      "token_count",
      "direct_references",
      "conditional_references",
      "child_skills",
    ],
    label,
  );
  const skillId = requireString(record.skill_id, `${label}.skill_id`);
  if (!ID_PATTERN.test(skillId) || record.name !== skillId || !ASCII_PATTERN.test(skillId)) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} has an invalid skill identity`);
  }
  const description = requireString(record.description, `${label}.description`);
  if (
    description !== description.trim().replace(/[\x20\t\f\v]+/gu, " ") ||
    /[\r\n\t]/u.test(description) ||
    Buffer.byteLength(description, "utf8") > 140
  ) {
    failSkillContext(
      "INITIAL_SKILL_METADATA_BUDGET_EXCEEDED",
      `${label}.description violates the canonical metadata projection`,
    );
  }
  const disposition = requireString(
    record.invocation_disposition,
    `${label}.invocation_disposition`,
  ) as InvocationDisposition;
  if (!INVOCATION_DISPOSITIONS.has(disposition)) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} has an invalid disposition`);
  }
  if (typeof record.allow_implicit_invocation !== "boolean") {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} implicit policy must be boolean`);
  }
  const shouldAllowImplicit = disposition === "PARENT_ROUTER" || disposition === "IMPLICIT_SAFE";
  if (record.allow_implicit_invocation !== shouldAllowImplicit) {
    failSkillContext("SKILL_INVOCATION_POLICY_DRIFT", `${label} disposition and policy differ`);
  }
  if (record.status !== "ACTIVE") {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label}.status must be ACTIVE`);
  }
  if (!Array.isArray(record.conditional_references)) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label}.conditional_references must be an array`);
  }
  const skillPath = assertNormalizedRelativePath(record.path, `${label}.path`, "skills/");
  if (skillPath !== `skills/${skillId}/SKILL.md`) {
    failSkillContext(
      "INVENTORY_CONTRACT_INVALID",
      `${label}.path must be the exact canonical skill path`,
    );
  }
  return {
    skill_id: skillId,
    name: skillId,
    description,
    path: skillPath,
    status: "ACTIVE",
    invocation_disposition: disposition,
    allow_implicit_invocation: record.allow_implicit_invocation,
    sha256: requireHash(record.sha256, `${label}.sha256`),
    byte_count: requireCount(record.byte_count, `${label}.byte_count`),
    token_count: requireCount(record.token_count, `${label}.token_count`),
    direct_references: requireStringArray(
      record.direct_references,
      `${label}.direct_references`,
    ),
    conditional_references: record.conditional_references.map((entry, conditionalIndex) =>
      parseConditional(entry, `${label}.conditional_references[${conditionalIndex}]`),
    ),
    child_skills: requireStringArray(record.child_skills, `${label}.child_skills`),
  };
};

const parseReference = (candidate: unknown, index: number): ReferenceInventoryEntry => {
  const label = `references[${index}]`;
  const record = requireRecord(candidate, label);
  requireExactKeys(
    record,
    [
      "reference_id",
      "path",
      "mode",
      "depends_on",
      "sha256",
      "byte_count",
      "token_count",
      "authority_sources",
      "media_type",
      "status",
    ],
    label,
  );
  const referenceId = requireString(record.reference_id, `${label}.reference_id`);
  if (!ID_PATTERN.test(referenceId) || !ASCII_PATTERN.test(referenceId)) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} has an invalid reference ID`);
  }
  const mode = requireString(record.mode, `${label}.mode`) as ReferenceSelectionMode;
  if (!REFERENCE_MODES.has(mode)) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label}.mode is not canonical`);
  }
  if (record.media_type !== "text/markdown") {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label}.media_type must be text/markdown`);
  }
  if (record.status !== "ACTIVE" && record.status !== "DISABLED") {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label}.status is invalid`);
  }
  if ((mode === "DISABLED") !== (record.status === "DISABLED")) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} mode and status differ`);
  }
  if (!Array.isArray(record.authority_sources) || record.authority_sources.length === 0) {
    failSkillContext("REFERENCE_TARGET_MISSING", `${label} requires authority_sources`);
  }
  const authoritySources = record.authority_sources.map((entry, sourceIndex) => {
    const sourceLabel = `${label}.authority_sources[${sourceIndex}]`;
    const source = requireRecord(entry, sourceLabel);
    requireExactKeys(source, ["path", "sha256"], sourceLabel);
    return {
      path: assertNormalizedRelativePath(source.path, `${sourceLabel}.path`, ""),
      sha256: requireHash(source.sha256, `${sourceLabel}.sha256`),
    };
  });
  return {
    reference_id: referenceId,
    path: assertNormalizedRelativePath(
      record.path,
      `${label}.path`,
      "skills/foundry/references/",
    ),
    mode,
    depends_on: requireStringArray(record.depends_on, `${label}.depends_on`),
    sha256: requireHash(record.sha256, `${label}.sha256`),
    byte_count: requireCount(record.byte_count, `${label}.byte_count`),
    token_count: requireCount(record.token_count, `${label}.token_count`),
    authority_sources: authoritySources,
    media_type: "text/markdown",
    status: record.status,
  };
};

const assertExactIdSet = (
  actual: readonly string[],
  expected: readonly string[],
  label: string,
): void => {
  const observed = [...actual].sort(compareUtf8);
  const wanted = [...expected].sort(compareUtf8);
  if (observed.length !== wanted.length || observed.some((value, index) => value !== wanted[index])) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} does not match the approved set`, {
      actual: observed,
      expected: wanted,
    });
  }
};

const assertUnique = (values: readonly string[], label: string): void => {
  if (new Set(values).size !== values.length) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} contains duplicates`);
  }
  const folded = values.map((value) => value.toLocaleLowerCase("en-US"));
  if (new Set(folded).size !== folded.length) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", `${label} contains a case-only collision`);
  }
};

const arraysEqual = (left: readonly string[], right: readonly string[]): boolean =>
  left.length === right.length && left.every((value, index) => value === right[index]);

const assertReferenceGraphSafety = (
  references: readonly ReferenceInventoryEntry[],
): void => {
  const byId = new Map(references.map((entry) => [entry.reference_id, entry]));
  const visit = (referenceId: string, depth: number, stack: readonly string[]): void => {
    if (stack.includes(referenceId)) {
      failSkillContext("REFERENCE_GRAPH_CYCLE", "reference graph contains a cycle", {
        cycle: [...stack.slice(stack.indexOf(referenceId)), referenceId],
      });
    }
    if (depth > 5) {
      failSkillContext("REFERENCE_DEPTH_EXCEEDED", "reference graph exceeds depth five", {
        reference_id: referenceId,
        depth,
      });
    }
    const reference = byId.get(referenceId);
    if (reference === undefined) {
      failSkillContext("REFERENCE_TARGET_MISSING", `reference ${referenceId} is missing`);
    }
    for (const dependencyId of reference.depends_on) {
      visit(dependencyId, depth + 1, [...stack, referenceId]);
    }
  };
  for (const reference of references) visit(reference.reference_id, 0, []);
};

const assertApprovedInventoryContract = (
  skills: readonly SkillInventoryEntry[],
  references: readonly ReferenceInventoryEntry[],
): void => {
  const expectedChildren = EXPECTED_SKILL_IDS.filter((entry) => entry !== "foundry").sort(
    compareUtf8,
  );
  for (const skill of skills) {
    const expectedDisposition = APPROVED_SKILL_DISPOSITIONS[skill.skill_id];
    const expectedDirect = APPROVED_DIRECT_REFERENCES[skill.skill_id];
    const expectedConditional = APPROVED_CONDITIONAL_REFERENCES[skill.skill_id] ?? [];
    if (
      expectedDisposition === undefined ||
      expectedDirect === undefined ||
      skill.invocation_disposition !== expectedDisposition ||
      !arraysEqual(skill.direct_references, expectedDirect) ||
      canonicalizeJson(skill.conditional_references) !== canonicalizeJson(expectedConditional) ||
      (skill.skill_id === "foundry"
        ? !arraysEqual(skill.child_skills, expectedChildren)
        : skill.child_skills.length !== 0)
    ) {
      failSkillContext(
        "INVENTORY_CONTRACT_INVALID",
        `${skill.skill_id} differs from the approved J02 skill contract`,
      );
    }
  }
  for (const reference of references) {
    const expected = APPROVED_REFERENCE_CONTRACT[reference.reference_id];
    if (
      expected === undefined ||
      reference.path !== expected.path ||
      reference.mode !== expected.mode ||
      !arraysEqual(reference.depends_on, expected.depends_on) ||
      !arraysEqual(
        reference.authority_sources.map((entry) => entry.path),
        APPROVED_AUTHORITY_SOURCE_PATHS,
      )
    ) {
      failSkillContext(
        "INVENTORY_CONTRACT_INVALID",
        `${reference.reference_id} differs from the approved J02 reference contract`,
      );
    }
  }
};

const assertTokenizer = (candidate: unknown): SkillInventory["tokenizer"] => {
  const record = requireRecord(candidate, "tokenizer");
  requireExactKeys(
    record,
    ["package", "version", "encoding", "disallowed_special", "dependency_artifact"],
    "tokenizer",
  );
  if (
    record.package !== "tiktoken" ||
    record.version !== "0.13.0" ||
    record.encoding !== "o200k_base" ||
    !Array.isArray(record.disallowed_special) ||
    record.disallowed_special.length !== 0
  ) {
    failSkillContext(
      "TOKENIZER_CONTRACT_UNAVAILABLE",
      "inventory must pin tiktoken 0.13.0 with o200k_base and no disallowed specials",
    );
  }
  const artifact = requireRecord(record.dependency_artifact, "tokenizer.dependency_artifact");
  requireExactKeys(
    artifact,
    ["artifact_kind", "filename", "sha256", "source_url"],
    "tokenizer.dependency_artifact",
  );
  if (
    artifact.artifact_kind !== "sdist" ||
    artifact.filename !== "tiktoken-0.13.0.tar.gz" ||
    artifact.sha256 !== TOKENIZER_SDIST_SHA256 ||
    artifact.source_url !==
      "https://files.pythonhosted.org/packages/source/t/tiktoken/tiktoken-0.13.0.tar.gz"
  ) {
    failSkillContext(
      "TOKENIZER_CONTRACT_UNAVAILABLE",
      "tokenizer dependency artifact lock evidence is missing or drifted",
    );
  }
  return record as unknown as SkillInventory["tokenizer"];
};

export const canonicalizeJson = (candidate: unknown): string => {
  if (candidate === null) return "null";
  if (typeof candidate === "boolean" || typeof candidate === "string") {
    return JSON.stringify(candidate);
  }
  if (typeof candidate === "number") {
    if (!Number.isFinite(candidate) || Object.is(candidate, -0)) {
      failSkillContext("INVENTORY_CONTRACT_INVALID", "canonical JSON contains an invalid number");
    }
    return JSON.stringify(candidate);
  }
  if (Array.isArray(candidate)) {
    return `[${candidate.map((entry) => canonicalizeJson(entry)).join(",")}]`;
  }
  const record = requireRecord(candidate, "canonical JSON value");
  return `{${Object.keys(record)
    .sort(compareUtf8)
    .map((key) => `${JSON.stringify(key)}:${canonicalizeJson(record[key])}`)
    .join(",")}}`;
};

export const sha256Bytes = (candidate: Uint8Array): string =>
  `sha256:${createHash("sha256").update(candidate).digest("hex")}`;

export const sha256Text = (candidate: string): string =>
  sha256Bytes(Buffer.from(candidate, "utf8"));

export const computeInventoryHash = (candidate: SkillInventory | Record<string, unknown>): string => {
  const { inventory_hash: _excluded, ...preimage } = candidate as Record<string, unknown>;
  return sha256Text(canonicalizeJson(preimage));
};

export const serializeInitialMetadata = (skills: readonly SkillInventoryEntry[]): string => {
  const parent = skills.find((entry) => entry.skill_id === "foundry");
  if (parent === undefined) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", "parent foundry skill is missing");
  }
  const children = skills
    .filter((entry) => entry.skill_id !== "foundry")
    .sort((left, right) => compareUtf8(left.name, right.name));
  return [parent, ...children]
    .map((entry) => `${entry.name}\t${entry.description}\t${entry.path}\n`)
    .join("")
    .normalize("NFC");
};

const parseMetadataSeal = (candidate: unknown): MetadataProjectionSeal => {
  const record = requireRecord(candidate, "metadata_projection");
  requireExactKeys(record, ["sha256", "byte_count", "token_count"], "metadata_projection");
  return {
    sha256: requireHash(record.sha256, "metadata_projection.sha256"),
    byte_count: requireCount(record.byte_count, "metadata_projection.byte_count"),
    token_count: requireCount(record.token_count, "metadata_projection.token_count"),
  };
};

export const validateSkillInventory = (candidate: unknown): SkillInventory => {
  const record = requireRecord(candidate, "inventory");
  requireExactKeys(
    record,
    [
      "inventory_id",
      "inventory_version",
      "inventory_hash",
      "parent_skill_id",
      "tokenizer",
      "budgets",
      "metadata_projection",
      "skills",
      "references",
    ],
    "inventory",
  );
  const inventoryId = requireString(record.inventory_id, "inventory.inventory_id");
  const inventoryVersion = requireString(record.inventory_version, "inventory.inventory_version");
  if (
    inventoryId !== "EF-SKILL-INVENTORY-V4-J02-0002" ||
    inventoryVersion !== "4.0.1-j02.1"
  ) {
    failSkillContext(
      "INVENTORY_CONTRACT_INVALID",
      "inventory identity must equal the approved J02 contract identity",
    );
  }
  const assertedHash = requireHash(record.inventory_hash, "inventory.inventory_hash");
  if (record.parent_skill_id !== "foundry") {
    failSkillContext("INVENTORY_CONTRACT_INVALID", "parent_skill_id must be foundry");
  }
  if (!Array.isArray(record.skills) || !Array.isArray(record.references)) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", "skills and references must be arrays");
  }
  const skills = record.skills.map(parseSkill);
  const references = record.references.map(parseReference);
  assertExactIdSet(
    skills.map((entry) => entry.skill_id),
    EXPECTED_SKILL_IDS,
    "skill IDs",
  );
  assertExactIdSet(
    references.map((entry) => entry.reference_id),
    EXPECTED_REFERENCE_IDS,
    "reference IDs",
  );
  assertUnique(skills.map((entry) => entry.skill_id), "skill IDs");
  assertUnique(skills.map((entry) => entry.path), "skill paths");
  assertUnique(references.map((entry) => entry.reference_id), "reference IDs");
  assertUnique(references.map((entry) => entry.path), "reference paths");
  assertUnique(references.map((entry) => entry.sha256), "reference content hashes");

  const referenceIds = new Set(references.map((entry) => entry.reference_id));
  const skillIds = new Set(skills.map((entry) => entry.skill_id));
  for (const skill of skills) {
    for (const referenceId of [
      ...skill.direct_references,
      ...skill.conditional_references.map((entry) => entry.reference_id),
    ]) {
      if (!referenceIds.has(referenceId)) {
        failSkillContext("REFERENCE_TARGET_MISSING", `${skill.skill_id} references an unknown ID`);
      }
    }
    for (const childId of skill.child_skills) {
      if (!skillIds.has(childId)) {
        failSkillContext("REFERENCE_TARGET_MISSING", `${skill.skill_id} has an unknown child`);
      }
    }
  }
  for (const reference of references) {
    for (const dependencyId of reference.depends_on) {
      if (!referenceIds.has(dependencyId)) {
        failSkillContext(
          "REFERENCE_TARGET_MISSING",
          `${reference.reference_id} depends on an unknown reference`,
        );
      }
    }
  }
  assertReferenceGraphSafety(references);
  assertApprovedInventoryContract(skills, references);

  const parent = skills.find((entry) => entry.skill_id === "foundry")!;
  if (
    parent.invocation_disposition !== "PARENT_ROUTER" ||
    parent.child_skills.length !== 28 ||
    skills.filter((entry) => entry.invocation_disposition === "PARENT_ROUTER").length !== 1
  ) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", "parent and child projection is invalid");
  }
  assertExactIdSet(
    parent.child_skills,
    skills.filter((entry) => entry.skill_id !== "foundry").map((entry) => entry.skill_id),
    "parent child_skills",
  );
  if (skills.some((entry) => entry.skill_id !== "foundry" && entry.child_skills.length !== 0)) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", "only the parent may declare child skills");
  }

  const budgets = requireRecord(record.budgets, "budgets") as unknown as SkillInventory["budgets"];
  assertCanonicalBudgetContract(budgets);
  for (const skill of skills) {
    if (
      skill.byte_count > budgets.skill_body_max_utf8_bytes ||
      skill.token_count > budgets.skill_body_max_o200k_tokens
    ) {
      failSkillContext(
        "REFERENCE_CONTEXT_BUDGET_EXCEEDED",
        `${skill.skill_id} exceeds the canonical selected-skill budget`,
      );
    }
  }
  for (const reference of references) {
    assertReferenceFileBudget(reference.byte_count, reference.token_count, budgets);
  }
  const metadataProjection = parseMetadataSeal(record.metadata_projection);
  const metadataText = serializeInitialMetadata(skills);
  if (
    Buffer.byteLength(metadataText, "utf8") !== metadataProjection.byte_count ||
    sha256Text(metadataText) !== metadataProjection.sha256
  ) {
    failSkillContext(
      "INVENTORY_HASH_MISMATCH",
      "metadata projection bytes or hash do not match the inventory seal",
    );
  }
  assertInitialMetadataBudget(metadataProjection, skills.length, budgets);

  const inventory: SkillInventory = {
    inventory_id: inventoryId,
    inventory_version: inventoryVersion,
    inventory_hash: assertedHash,
    parent_skill_id: "foundry",
    tokenizer: assertTokenizer(record.tokenizer),
    budgets,
    metadata_projection: metadataProjection,
    skills,
    references,
  };
  const computedHash = computeInventoryHash(inventory);
  if (computedHash !== assertedHash) {
    failSkillContext("INVENTORY_HASH_MISMATCH", "inventory_hash does not match canonical JSON", {
      asserted: assertedHash,
      computed: computedHash,
    });
  }
  return Object.freeze(inventory);
};

export const loadSkillInventory = async (pluginRoot: string): Promise<SkillInventory> => {
  const inventoryPath = path.resolve(pluginRoot, "skills", "skill-inventory.json");
  let bytes: Buffer;
  try {
    bytes = await readFile(inventoryPath);
  } catch (error) {
    failSkillContext("REFERENCE_TARGET_MISSING", "canonical skill inventory is unavailable", {
      cause: error instanceof Error ? error.message : String(error),
    });
  }
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", "skill inventory must be BOM-less UTF-8");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch (error) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", "skill inventory is not valid UTF-8 JSON", {
      cause: error instanceof Error ? error.message : String(error),
    });
  }
  return validateSkillInventory(parsed);
};
