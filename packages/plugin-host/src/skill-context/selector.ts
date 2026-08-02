import { computeSkillRoutingDecisionHash } from "../skill-router/skill-router.mjs";
import { types as utilTypes } from "node:util";

import { failSkillContext } from "./errors.ts";
import { compareUtf8 } from "./inventory.ts";
import type {
  ConditionValues,
  ExactInvocationAuthority,
  ReferenceInventoryEntry,
  ReferencePredicate,
  ReferenceProposal,
  ReferenceSelectionReason,
  SelectionResult,
  SkillInventory,
  SkillInventoryEntry,
  SkillRoutingDecisionLike,
} from "./types.ts";

const ROUTING_DECISION_KEYS = Object.freeze([
  "decision_id",
  "request_id",
  "mode",
  "candidates",
  "selected_skill_ids",
  "rejected_skill_ids",
  "context_budget_tokens",
  "authority_notes",
  "policy_hash",
  "decided_at",
  "decision_hash",
]);

const PREDICATE_KEYS = Object.freeze([
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
const PREDICATE_OPERATORS = Object.freeze(["EQUALS", "IN", "ANY_OF", "ALL_OF"]);
const AUTHORITY_KINDS = Object.freeze([
  "PARENT_PLAN",
  "ACTION_INTENT",
  "HUMAN_DECISION",
  "POLICY",
]);

const requirePlainDataRecord = (
  candidate: unknown,
  label: string,
  code: "INVALID_ROUTING_DECISION" | "INVALID_SKILL_CONTEXT_INPUT" =
    "INVALID_SKILL_CONTEXT_INPUT",
): Record<string, unknown> => {
  if (
    candidate === null ||
    typeof candidate !== "object" ||
    Array.isArray(candidate) ||
    utilTypes.isProxy(candidate) ||
    Object.getPrototypeOf(candidate) !== Object.prototype
  ) {
    failSkillContext(code, `${label} must be a plain data object`);
  }
  const keys = Reflect.ownKeys(candidate);
  const descriptors = Object.getOwnPropertyDescriptors(candidate);
  if (
    keys.some((key) => typeof key !== "string") ||
    Object.values(descriptors).some(
      (descriptor) => !descriptor.enumerable || !("value" in descriptor),
    )
  ) {
    failSkillContext(code, `${label} must contain enumerable data fields only`);
  }
  return candidate as Record<string, unknown>;
};

const requireExactInputKeys = (
  record: Record<string, unknown>,
  required: readonly string[],
  optional: readonly string[],
  label: string,
): void => {
  const allowed = new Set([...required, ...optional]);
  const actual = Object.keys(record);
  if (
    required.some((key) => !Object.hasOwn(record, key)) ||
    actual.some((key) => !allowed.has(key))
  ) {
    failSkillContext(
      "INVALID_SKILL_CONTEXT_INPUT",
      `${label} has missing or unexpected fields`,
      { actual: actual.sort(compareUtf8), required: [...required], optional: [...optional] },
    );
  }
};

const requireInputString = (candidate: unknown, label: string): string => {
  if (typeof candidate !== "string" || candidate.length === 0) {
    failSkillContext("INVALID_SKILL_CONTEXT_INPUT", `${label} must be a non-empty string`);
  }
  return candidate;
};

const requireInputStringArray = (candidate: unknown, label: string): string[] => {
  if (
    !Array.isArray(candidate) ||
    utilTypes.isProxy(candidate) ||
    Object.keys(candidate).length !== candidate.length
  ) {
    failSkillContext("INVALID_SKILL_CONTEXT_INPUT", `${label} must be a dense array`);
  }
  const values = candidate.map((entry, index) =>
    requireInputString(entry, `${label}[${index}]`),
  );
  if (values.length === 0 || new Set(values).size !== values.length) {
    failSkillContext(
      "INVALID_SKILL_CONTEXT_INPUT",
      `${label} must contain unique values and cannot be empty`,
    );
  }
  return values;
};

export const validateReferencePredicate = (
  candidate: unknown,
  label = "reference predicate",
): ReferencePredicate => {
  const record = requirePlainDataRecord(candidate, label);
  requireExactInputKeys(record, ["key", "operator", "value"], [], label);
  const key = requireInputString(record.key, `${label}.key`);
  const operator = requireInputString(record.operator, `${label}.operator`);
  if (!PREDICATE_KEYS.includes(key) || !PREDICATE_OPERATORS.includes(operator)) {
    failSkillContext(
      "INVALID_SKILL_CONTEXT_INPUT",
      `${label} uses a non-canonical key or operator`,
    );
  }
  const expectsArray = operator === "ANY_OF" || operator === "ALL_OF";
  const value = expectsArray
    ? requireInputStringArray(record.value, `${label}.value`)
    : requireInputString(record.value, `${label}.value`);
  if (!expectsArray && Array.isArray(record.value)) {
    failSkillContext(
      "INVALID_SKILL_CONTEXT_INPUT",
      `${label}.${operator} requires one string`,
    );
  }
  return Object.freeze({
    key: key as ReferencePredicate["key"],
    operator: operator as ReferencePredicate["operator"],
    value: Array.isArray(value) ? Object.freeze([...value]) as unknown as string[] : value,
  });
};

export const validateConditionValues = (
  candidate: ConditionValues | undefined,
): ConditionValues => {
  if (candidate === undefined) return Object.freeze({});
  const record = requirePlainDataRecord(candidate, "conditions");
  const normalized: ConditionValues = {};
  for (const [key, value] of Object.entries(record)) {
    if (!PREDICATE_KEYS.includes(key)) {
      failSkillContext("INVALID_SKILL_CONTEXT_INPUT", `conditions.${key} is not canonical`);
    }
    normalized[key as keyof ConditionValues] = Array.isArray(value)
      ? Object.freeze(requireInputStringArray(value, `conditions.${key}`)) as unknown as string[]
      : requireInputString(value, `conditions.${key}`);
  }
  return Object.freeze(normalized);
};

export const validateInvocationAuthority = (
  candidate: ExactInvocationAuthority | undefined,
): ExactInvocationAuthority | undefined => {
  if (candidate === undefined) return undefined;
  const record = requirePlainDataRecord(candidate, "invocation_authority");
  requireExactInputKeys(
    record,
    ["kind", "skill_id", "exact_authorized", "authority_id"],
    [],
    "invocation_authority",
  );
  const kind = requireInputString(record.kind, "invocation_authority.kind");
  if (!AUTHORITY_KINDS.includes(kind) || record.exact_authorized !== true) {
    failSkillContext(
      "INVOCATION_DISPOSITION_DENIED",
      "invocation authority kind or exact authorization is invalid",
    );
  }
  return Object.freeze({
    kind: kind as ExactInvocationAuthority["kind"],
    skill_id: requireInputString(record.skill_id, "invocation_authority.skill_id"),
    exact_authorized: true,
    authority_id: requireInputString(record.authority_id, "invocation_authority.authority_id"),
  });
};

export const validateReferenceProposals = (
  candidate: ReferenceProposal[] | undefined,
): ReferenceProposal[] => {
  if (candidate === undefined) return Object.freeze([]) as unknown as ReferenceProposal[];
  if (
    !Array.isArray(candidate) ||
    utilTypes.isProxy(candidate) ||
    Object.keys(candidate).length !== candidate.length
  ) {
    failSkillContext("INVALID_SKILL_CONTEXT_INPUT", "llm_proposals must be a dense array");
  }
  return Object.freeze(
    candidate.map((entry, index) => {
      const label = `llm_proposals[${index}]`;
      const record = requirePlainDataRecord(entry, label);
      requireExactInputKeys(
        record,
        ["reference_id", "reason"],
        ["source_span", "typed_trigger_candidate"],
        label,
      );
      const proposal: ReferenceProposal = {
        reference_id: requireInputString(record.reference_id, `${label}.reference_id`),
        reason: requireInputString(record.reason, `${label}.reason`),
      };
      if (Object.hasOwn(record, "source_span")) {
        proposal.source_span = requireInputString(record.source_span, `${label}.source_span`);
      }
      if (Object.hasOwn(record, "typed_trigger_candidate")) {
        proposal.typed_trigger_candidate = validateReferencePredicate(
          record.typed_trigger_candidate,
          `${label}.typed_trigger_candidate`,
        );
      }
      return Object.freeze(proposal);
    }),
  ) as unknown as ReferenceProposal[];
};

const requireDenseStringArray = (candidate: unknown, label: string): string[] => {
  if (
    !Array.isArray(candidate) ||
    utilTypes.isProxy(candidate) ||
    Object.keys(candidate).length !== candidate.length
  ) {
    failSkillContext("INVALID_ROUTING_DECISION", `${label} must be a dense array`);
  }
  const values = candidate.map((entry) => {
    if (typeof entry !== "string" || entry.length === 0) {
      failSkillContext("INVALID_ROUTING_DECISION", `${label} must contain strings`);
    }
    return entry;
  });
  if (new Set(values).size !== values.length) {
    failSkillContext("INVALID_ROUTING_DECISION", `${label} contains duplicate values`);
  }
  return values;
};

const requireRoutingCandidates = (candidate: unknown): string[] => {
  if (
    !Array.isArray(candidate) ||
    utilTypes.isProxy(candidate) ||
    Object.keys(candidate).length !== candidate.length
  ) {
    failSkillContext("INVALID_ROUTING_DECISION", "candidates must be a dense array");
  }
  const ids = candidate.map((entry, index) => {
    const record = requirePlainDataRecord(
      entry,
      `candidates[${index}]`,
      "INVALID_ROUTING_DECISION",
    );
    const actualKeys = Object.keys(record).sort(compareUtf8);
    const expectedKeys = ["skill_id", "score", "reason", "implicit_allowed"].sort(
      compareUtf8,
    );
    if (
      actualKeys.length !== expectedKeys.length ||
      actualKeys.some((key, keyIndex) => key !== expectedKeys[keyIndex]) ||
      typeof record.skill_id !== "string" ||
      record.skill_id.length === 0 ||
      typeof record.score !== "number" ||
      !Number.isFinite(record.score) ||
      record.score < 0 ||
      record.score > 1 ||
      typeof record.reason !== "string" ||
      record.reason.length === 0 ||
      typeof record.implicit_allowed !== "boolean"
    ) {
      failSkillContext(
        "INVALID_ROUTING_DECISION",
        `candidates[${index}] violates the J01 output contract`,
      );
    }
    return record.skill_id;
  });
  if (new Set(ids).size !== ids.length) {
    failSkillContext("INVALID_ROUTING_DECISION", "candidates contains duplicate skill IDs");
  }
  return ids;
};

export const validateRoutingDecision = (
  candidate: SkillRoutingDecisionLike,
): SkillRoutingDecisionLike => {
  requirePlainDataRecord(candidate, "routing decision", "INVALID_ROUTING_DECISION");
  const actualKeys = Object.keys(candidate).sort(compareUtf8);
  const expectedKeys = [...ROUTING_DECISION_KEYS].sort(compareUtf8);
  if (
    actualKeys.length !== expectedKeys.length ||
    actualKeys.some((key, index) => key !== expectedKeys[index])
  ) {
    failSkillContext(
      "INVALID_ROUTING_DECISION",
      "routing decision fields are missing or unexpected",
    );
  }
  if (!/^SRD-[0-9a-f]{64}$/u.test(candidate.decision_id)) {
    failSkillContext("INVALID_ROUTING_DECISION", "routing decision ID is invalid");
  }
  if (!/^sha256:[0-9a-f]{64}$/u.test(candidate.decision_hash)) {
    failSkillContext("INVALID_ROUTING_DECISION", "routing decision hash is invalid");
  }
  if (!new Set(["implicit", "explicit", "none"]).has(candidate.mode)) {
    failSkillContext("INVALID_ROUTING_DECISION", "routing decision mode is invalid");
  }
  const selected = requireDenseStringArray(
    candidate.selected_skill_ids,
    "selected_skill_ids",
  );
  const rejected = requireDenseStringArray(candidate.rejected_skill_ids, "rejected_skill_ids");
  requireDenseStringArray(candidate.authority_notes, "authority_notes");
  if (candidate.mode === "none" || selected.length !== 1) {
    failSkillContext(
      "INVALID_ROUTING_DECISION",
      "J02 requires one exactly selected skill from a non-none J01 decision",
    );
  }
  const candidateIds = requireRoutingCandidates(candidate.candidates);
  const selectedSet = new Set(selected);
  const rejectedSet = new Set(rejected);
  if (
    !selected.every((entry) => candidateIds.includes(entry)) ||
    selected.some((entry) => rejectedSet.has(entry)) ||
    candidateIds.some((entry) => !selectedSet.has(entry) && !rejectedSet.has(entry)) ||
    rejected.some((entry) => !candidateIds.includes(entry)) ||
    !Number.isSafeInteger(candidate.context_budget_tokens) ||
    candidate.context_budget_tokens < 0 ||
    typeof candidate.request_id !== "string" ||
    candidate.request_id.length === 0 ||
    !/^sha256:[0-9a-f]{64}$/u.test(candidate.policy_hash) ||
    typeof candidate.decided_at !== "string" ||
    candidate.decided_at.length === 0
  ) {
    failSkillContext(
      "INVALID_ROUTING_DECISION",
      "routing decision candidates, partition, or scalar fields are inconsistent",
    );
  }
  const { decision_id: _id, decision_hash: _hash, ...preimage } = candidate;
  const computed = computeSkillRoutingDecisionHash(preimage);
  if (
    computed !== candidate.decision_hash ||
    candidate.decision_id !== `SRD-${computed.slice("sha256:".length)}`
  ) {
    failSkillContext(
      "INVALID_ROUTING_DECISION",
      "routing decision hash or ID does not bind its canonical preimage",
    );
  }
  return candidate;
};

const assertInvocationDisposition = (
  skill: SkillInventoryEntry,
  decision: SkillRoutingDecisionLike,
  authority: ExactInvocationAuthority | undefined,
): void => {
  if (decision.mode === "implicit") {
    if (
      skill.invocation_disposition !== "PARENT_ROUTER" &&
      skill.invocation_disposition !== "IMPLICIT_SAFE"
    ) {
      failSkillContext(
        "INVOCATION_DISPOSITION_DENIED",
        `${skill.skill_id} cannot be invoked implicitly`,
      );
    }
    return;
  }
  if (skill.invocation_disposition === "PARENT_ROUTED") {
    if (
      authority?.kind !== "PARENT_PLAN" ||
      authority.skill_id !== skill.skill_id ||
      authority.exact_authorized !== true ||
      authority.authority_id.length === 0
    ) {
      failSkillContext(
        "INVOCATION_DISPOSITION_DENIED",
        `${skill.skill_id} requires an exact parent routing plan`,
      );
    }
  }
  if (
    skill.invocation_disposition === "EXPLICIT_ONLY" &&
    decision.mode !== "explicit" &&
    !(
      authority?.skill_id === skill.skill_id &&
      authority.exact_authorized === true &&
      authority.authority_id.length > 0
    )
  ) {
    failSkillContext(
      "INVOCATION_DISPOSITION_DENIED",
      `${skill.skill_id} requires exact explicit authorization`,
    );
  }
};

const asValues = (candidate: string | string[] | undefined): string[] => {
  if (candidate === undefined) return [];
  return Array.isArray(candidate) ? candidate : [candidate];
};

const predicatesEqual = (
  left: ReferencePredicate,
  right: ReferencePredicate,
): boolean => {
  if (left.key !== right.key || left.operator !== right.operator) return false;
  const leftValues = asValues(left.value);
  const rightValues = asValues(right.value);
  return (
    leftValues.length === rightValues.length &&
    leftValues.every((value, index) => value === rightValues[index])
  );
};

export const predicateMatches = (
  predicate: ReferencePredicate,
  conditions: ConditionValues,
): boolean => {
  const observed = asValues(conditions[predicate.key]);
  const expected = asValues(predicate.value);
  switch (predicate.operator) {
    case "EQUALS":
      return observed.length === 1 && expected.length === 1 && observed[0] === expected[0];
    case "IN":
      return observed.includes(expected[0]);
    case "ANY_OF":
      return expected.some((entry) => observed.includes(entry));
    case "ALL_OF":
      return expected.every((entry) => observed.includes(entry));
  }
};

interface RootReason {
  reference_id: string;
  reason: "DIRECT_REQUIRED" | "MATCHING_CONDITIONAL" | "EXPLICIT_ONLY";
}

interface ExpandedGraph {
  closure: Set<string>;
  maximumDepth: number;
  dependencyOnly: Set<string>;
}

const expandDependencies = (
  roots: readonly RootReason[],
  referenceById: ReadonlyMap<string, ReferenceInventoryEntry>,
): ExpandedGraph => {
  const closure = new Set<string>();
  const rootIds = new Set(roots.map((entry) => entry.reference_id));
  const dependencyOnly = new Set<string>();
  let maximumDepth = 0;

  const visit = (referenceId: string, depth: number, stack: readonly string[]): void => {
    const reference = referenceById.get(referenceId);
    if (reference === undefined) {
      failSkillContext("REFERENCE_TARGET_MISSING", `reference target ${referenceId} is missing`);
    }
    if (stack.includes(referenceId)) {
      failSkillContext("REFERENCE_GRAPH_CYCLE", "reference dependency graph contains a cycle", {
        cycle: [...stack.slice(stack.indexOf(referenceId)), referenceId],
      });
    }
    if (depth > 5) {
      failSkillContext("REFERENCE_DEPTH_EXCEEDED", "reference dependency depth exceeds five", {
        reference_id: referenceId,
        depth,
      });
    }
    maximumDepth = Math.max(maximumDepth, depth);
    closure.add(referenceId);
    if (!rootIds.has(referenceId)) dependencyOnly.add(referenceId);
    for (const dependencyId of reference.depends_on) {
      visit(dependencyId, depth + 1, [...stack, referenceId]);
    }
  };

  for (const root of roots) visit(root.reference_id, 0, []);
  return { closure, maximumDepth, dependencyOnly };
};

const reasonPriority = (reason: ReferenceSelectionReason["reason"]): number => {
  switch (reason) {
    case "CORE_CONSTITUTION":
      return 0;
    case "TRANSITIVE_PREREQUISITE":
      return 1;
    case "DIRECT_REQUIRED":
      return 2;
    case "MATCHING_CONDITIONAL":
      return 3;
    case "EXPLICIT_ONLY":
      return 4;
  }
};

const topologicalOrder = (
  closure: ReadonlySet<string>,
  references: ReadonlyMap<string, ReferenceInventoryEntry>,
  reasons: ReadonlyMap<string, ReferenceSelectionReason["reason"]>,
): string[] => {
  const indegree = new Map<string, number>();
  const dependents = new Map<string, string[]>();
  for (const referenceId of closure) {
    const reference = references.get(referenceId)!;
    const dependencies = reference.depends_on.filter((entry) => closure.has(entry));
    indegree.set(referenceId, dependencies.length);
    for (const dependencyId of dependencies) {
      const entries = dependents.get(dependencyId) ?? [];
      entries.push(referenceId);
      dependents.set(dependencyId, entries);
    }
  }
  const compareReady = (left: string, right: string): number =>
    reasonPriority(reasons.get(left)!) - reasonPriority(reasons.get(right)!) ||
    compareUtf8(left, right);
  const ready = [...closure].filter((entry) => indegree.get(entry) === 0).sort(compareReady);
  const ordered: string[] = [];
  while (ready.length > 0) {
    const current = ready.shift()!;
    ordered.push(current);
    for (const dependent of (dependents.get(current) ?? []).sort(compareUtf8)) {
      const next = indegree.get(dependent)! - 1;
      indegree.set(dependent, next);
      if (next === 0) {
        ready.push(dependent);
        ready.sort(compareReady);
      }
    }
  }
  if (ordered.length !== closure.size) {
    failSkillContext("REFERENCE_GRAPH_CYCLE", "reference graph cannot be topologically ordered");
  }
  return ordered;
};

export interface SelectReferencesOptions {
  inventory: SkillInventory;
  routingDecision: SkillRoutingDecisionLike;
  conditions?: ConditionValues;
  invocationAuthority?: ExactInvocationAuthority;
  explicitReferenceIds?: string[];
  explicitReferenceAuthorityIds?: string[];
  llmProposals?: ReferenceProposal[];
}

export const selectReferences = (options: SelectReferencesOptions): SelectionResult => {
  const decision = validateRoutingDecision(options.routingDecision);
  const conditions = validateConditionValues(options.conditions);
  const invocationAuthority = validateInvocationAuthority(options.invocationAuthority);
  const llmProposals = validateReferenceProposals(options.llmProposals);
  const selectedSkillId = decision.selected_skill_ids[0];
  const skill = options.inventory.skills.find((entry) => entry.skill_id === selectedSkillId);
  if (skill === undefined) {
    failSkillContext(
      "REFERENCE_TARGET_MISSING",
      `selected skill ${selectedSkillId} is not in the inventory`,
    );
  }
  assertInvocationDisposition(skill, decision, invocationAuthority);
  const referenceById = new Map(
    options.inventory.references.map((entry) => [entry.reference_id, entry]),
  );
  const roots: RootReason[] = skill.direct_references.map((referenceId) => ({
    reference_id: referenceId,
    reason: "DIRECT_REQUIRED",
  }));
  for (const conditional of skill.conditional_references) {
    if (predicateMatches(conditional.predicate, conditions)) {
      roots.push({
        reference_id: conditional.reference_id,
        reason: "MATCHING_CONDITIONAL",
      });
    }
  }

  const explicitIds = requireDenseStringArray(
    options.explicitReferenceIds ?? [],
    "explicit_reference_ids",
  );
  const explicitAuthorities = new Set(
    requireDenseStringArray(
      options.explicitReferenceAuthorityIds ?? [],
      "explicit_reference_authority_ids",
    ),
  );
  for (const referenceId of explicitIds) {
    const reference = referenceById.get(referenceId);
    if (reference === undefined) {
      failSkillContext("UNKNOWN_REFERENCE_PROPOSAL", `explicit reference ${referenceId} is unknown`);
    }
    if (reference.mode === "DISABLED" || reference.status === "DISABLED") {
      failSkillContext("REFERENCE_DISABLED", `${referenceId} is disabled`);
    }
    if (reference.mode !== "EXPLICIT_ONLY" || !explicitAuthorities.has(referenceId)) {
      failSkillContext(
        "REFERENCE_EXPLICIT_AUTHORITY_REQUIRED",
        `${referenceId} lacks exact explicit authority`,
      );
    }
    roots.push({ reference_id: referenceId, reason: "EXPLICIT_ONLY" });
  }

  const warnings: string[] = [];
  for (const proposal of llmProposals) {
    const proposedReference = referenceById.get(proposal.reference_id);
    if (proposedReference === undefined) {
      failSkillContext(
        "UNKNOWN_REFERENCE_PROPOSAL",
        `LLM-proposed reference ${proposal.reference_id} is unknown`,
      );
    }
    if (proposedReference.mode === "DISABLED" || proposedReference.status === "DISABLED") {
      failSkillContext("REFERENCE_DISABLED", `${proposal.reference_id} is disabled`);
    }
    if (proposal.typed_trigger_candidate !== undefined) {
      const declared = skill.conditional_references.some(
        (conditional) =>
          conditional.reference_id === proposal.reference_id &&
          predicatesEqual(conditional.predicate, proposal.typed_trigger_candidate!),
      );
      if (!declared || !predicateMatches(proposal.typed_trigger_candidate, conditions)) {
        warnings.push(`LLM_TYPED_TRIGGER_REJECTED:${proposal.reference_id}`);
      }
    }
  }

  const rootById = new Map<string, RootReason>();
  for (const root of roots) {
    const existing = rootById.get(root.reference_id);
    if (
      existing === undefined ||
      reasonPriority(root.reason) < reasonPriority(existing.reason)
    ) {
      rootById.set(root.reference_id, root);
    }
  }
  for (const root of rootById.values()) {
    const reference = referenceById.get(root.reference_id);
    if (reference === undefined) {
      failSkillContext("REFERENCE_TARGET_MISSING", `${root.reference_id} is absent from inventory`);
    }
    if (reference.mode === "DISABLED" || reference.status === "DISABLED") {
      failSkillContext("REFERENCE_DISABLED", `${root.reference_id} is disabled`);
    }
  }

  const expanded = expandDependencies([...rootById.values()], referenceById);
  for (const proposal of llmProposals) {
    if (!expanded.closure.has(proposal.reference_id)) {
      warnings.push(`LLM_PROPOSAL_NOT_AUTHORIZED:${proposal.reference_id}`);
    }
  }
  if (expanded.closure.size > options.inventory.budgets.reference_closure_max_count) {
    failSkillContext(
      "REFERENCE_CONTEXT_BUDGET_EXCEEDED",
      "selected reference closure exceeds the maximum count",
      { observed: expanded.closure.size },
    );
  }
  const reasonById = new Map<string, ReferenceSelectionReason["reason"]>();
  for (const referenceId of expanded.closure) {
    if (referenceId === "EFREF-CORE-CONSTITUTION-V4") {
      reasonById.set(referenceId, "CORE_CONSTITUTION");
    } else if (expanded.dependencyOnly.has(referenceId)) {
      reasonById.set(referenceId, "TRANSITIVE_PREREQUISITE");
    } else {
      reasonById.set(referenceId, rootById.get(referenceId)!.reason);
    }
  }
  const orderedReferenceIds = topologicalOrder(expanded.closure, referenceById, reasonById);
  return Object.freeze({
    selected_skill_id: selectedSkillId,
    ordered_reference_ids: Object.freeze([...orderedReferenceIds]) as unknown as string[],
    reference_selection_reasons: Object.freeze(
      orderedReferenceIds.map((referenceId) =>
        Object.freeze({ reference_id: referenceId, reason: reasonById.get(referenceId)! }),
      ),
    ) as unknown as ReferenceSelectionReason[],
    transitive_depth: expanded.maximumDepth,
    warnings: Object.freeze(warnings.sort(compareUtf8)) as unknown as string[],
  });
};
