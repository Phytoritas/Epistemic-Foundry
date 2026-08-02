import { failSkillContext } from "./errors.ts";
import { compareUtf8 } from "./inventory.ts";
import type { ReachabilityReport, ReferenceInventoryEntry, SkillInventory } from "./types.ts";

interface ClosureResult {
  ids: Set<string>;
  maximumDepth: number;
}

const closureForRoots = (
  roots: readonly string[],
  references: ReadonlyMap<string, ReferenceInventoryEntry>,
): ClosureResult => {
  const ids = new Set<string>();
  let maximumDepth = 0;
  const visit = (referenceId: string, depth: number, stack: readonly string[]): void => {
    const reference = references.get(referenceId);
    if (reference === undefined) {
      failSkillContext("REFERENCE_TARGET_MISSING", `reference ${referenceId} is missing`);
    }
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
    ids.add(referenceId);
    maximumDepth = Math.max(maximumDepth, depth);
    for (const dependencyId of reference.depends_on) {
      visit(dependencyId, depth + 1, [...stack, referenceId]);
    }
  };
  for (const root of roots) visit(root, 0, []);
  return { ids, maximumDepth };
};

export const analyzeReachability = (inventory: SkillInventory): ReachabilityReport => {
  const referenceById = new Map(
    inventory.references.map((entry) => [entry.reference_id, entry]),
  );
  const parentSkills = inventory.skills.filter(
    (entry) => entry.invocation_disposition === "PARENT_ROUTER",
  );
  const parent = parentSkills[0];
  const reachableChildren = new Set<string>();
  const queue = parent === undefined ? [] : [...parent.child_skills].sort(compareUtf8);
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (reachableChildren.has(current)) continue;
    const skill = inventory.skills.find((entry) => entry.skill_id === current);
    if (skill === undefined) {
      failSkillContext("REFERENCE_TARGET_MISSING", `child skill ${current} is missing`);
    }
    reachableChildren.add(current);
    queue.push(...skill.child_skills);
  }
  const childIds = inventory.skills
    .filter((entry) => entry.skill_id !== inventory.parent_skill_id)
    .map((entry) => entry.skill_id);
  const unreachableChildren = childIds
    .filter((entry) => !reachableChildren.has(entry))
    .sort(compareUtf8);
  const orphanSkills = inventory.skills
    .map((entry) => entry.skill_id)
    .filter(
      (entry) => entry !== inventory.parent_skill_id && !reachableChildren.has(entry),
    )
    .sort(compareUtf8);

  const reachableReferences = new Set<string>();
  let maximumClosureCount = 0;
  let maximumDepth = 0;
  for (const skill of inventory.skills) {
    const roots = [
      ...skill.direct_references,
      ...skill.conditional_references.map((entry) => entry.reference_id),
    ];
    const closure = closureForRoots(roots, referenceById);
    maximumClosureCount = Math.max(maximumClosureCount, closure.ids.size);
    maximumDepth = Math.max(maximumDepth, closure.maximumDepth);
    for (const referenceId of closure.ids) reachableReferences.add(referenceId);
  }
  const orphanReferences = inventory.references
    .map((entry) => entry.reference_id)
    .filter((entry) => !reachableReferences.has(entry))
    .sort(compareUtf8);
  const errors: string[] = [];
  if (parentSkills.length !== 1) errors.push("PARENT_COUNT");
  if (unreachableChildren.length > 0) errors.push("UNREACHABLE_CHILD");
  if (orphanSkills.length > 0) errors.push("ORPHAN_SKILL");
  if (orphanReferences.length > 0) errors.push("ORPHAN_REFERENCE");
  if (maximumClosureCount > inventory.budgets.reference_closure_max_count) {
    errors.push("REFERENCE_CLOSURE_COUNT");
  }
  if (maximumDepth > inventory.budgets.reference_closure_max_depth) {
    errors.push("REFERENCE_DEPTH");
  }
  return Object.freeze({
    parent_count: parentSkills.length,
    child_count: childIds.length,
    reachable_child_count: reachableChildren.size,
    unreachable_child_ids: Object.freeze(unreachableChildren) as unknown as string[],
    orphan_skill_ids: Object.freeze(orphanSkills) as unknown as string[],
    reference_count: inventory.references.length,
    reachable_reference_count: reachableReferences.size,
    orphan_reference_ids: Object.freeze(orphanReferences) as unknown as string[],
    maximum_closure_count: maximumClosureCount,
    maximum_transitive_depth: maximumDepth,
    graph_integrity_errors: Object.freeze(errors) as unknown as string[],
  });
};

export const assertReachability = (inventory: SkillInventory): ReachabilityReport => {
  const report = analyzeReachability(inventory);
  if (
    report.parent_count !== 1 ||
    report.child_count !== 28 ||
    report.reachable_child_count !== 28 ||
    report.reference_count !== 17 ||
    report.reachable_reference_count !== 17 ||
    report.graph_integrity_errors.length !== 0
  ) {
    failSkillContext("INVENTORY_CONTRACT_INVALID", "skill/reference graph is not fully reachable", {
      report,
    });
  }
  return report;
};
