import path from "node:path";

import { routeSkillRequest } from "../../../../../packages/plugin-host/src/skill-router/skill-router.mjs";
import {
  canonicalizeJson,
  loadSkillInventory,
  selectReferences,
  sha256Text,
} from "../../../../../packages/plugin-host/src/skill-context/index.ts";

const repositoryRoot = path.resolve(import.meta.dirname, "../../../../..");
const pluginRoot = path.join(repositoryRoot, "plugins", "epistemic-foundry");
const inventory = await loadSkillInventory(pluginRoot);
const POLICY_HASH = `sha256:${"a".repeat(64)}`;
const DECIDED_AT = "2026-07-29T12:00:00.000Z";

const decisionFor = (skill, caseId) =>
  routeSkillRequest({
    request_id: `REQ-J02-${caseId}`,
    request_text: `Explicit J02 fixture route for ${skill.skill_id}.`,
    explicit_skill_id: skill.skill_id,
    candidates: [
      {
        skill_id: skill.skill_id,
        description: skill.description,
        content_hash: skill.sha256,
        source: "bundled",
        allow_implicit_invocation: skill.allow_implicit_invocation,
        sensitive: false,
        side_effecting: false,
        trigger_phrases: [],
        exclusion_phrases: [],
      },
    ],
    context_budget_tokens: 7168,
    policy_hash: POLICY_HASH,
    decided_at: DECIDED_AT,
  });

const materialize = (caseId, category, skillId, conditions) => {
  const skill = inventory.skills.find((entry) => entry.skill_id === skillId);
  const selection = selectReferences({
    inventory,
    routingDecision: decisionFor(skill, caseId),
    conditions,
    invocationAuthority:
      skill.invocation_disposition === "PARENT_ROUTED"
        ? {
            kind: "PARENT_PLAN",
            skill_id: skillId,
            exact_authorized: true,
            authority_id: `PLAN-J02-${caseId}`,
          }
        : undefined,
  });
  const references = new Map(
    inventory.references.map((entry) => [entry.reference_id, entry]),
  );
  const selectionPreimage = {
    ordered_reference_ids: selection.ordered_reference_ids,
    reference_selection_reasons: selection.reference_selection_reasons,
    transitive_depth: selection.transitive_depth,
    total_reference_bytes: selection.ordered_reference_ids.reduce(
      (total, referenceId) => total + references.get(referenceId).byte_count,
      0,
    ),
    total_reference_tokens: selection.ordered_reference_ids.reduce(
      (total, referenceId) => total + references.get(referenceId).token_count,
      0,
    ),
    warnings: selection.warnings,
  };
  return {
    case_id: caseId,
    category,
    skill_id: skillId,
    conditions,
    inventory_hash: inventory.inventory_hash,
    selection_hash: sha256Text(canonicalizeJson(selectionPreimage)),
    ...selectionPreimage,
  };
};

const cases = inventory.skills.map((skill) =>
  materialize(`DEFAULT-${skill.skill_id}`, "DEFAULT", skill.skill_id, {}),
);
for (const [skillId, positive, negative] of [
  ["foundry-evolve-convert", { backend_id: "shinka" }, { backend_id: "native" }],
  [
    "foundry-parliament",
    { candidate_origin: "EVOLUTION" },
    { candidate_origin: "LITERATURE" },
  ],
  [
    "foundry-passport",
    { artifact_kind: ["ValidationResult"] },
    { artifact_kind: ["EvidencePack"] },
  ],
]) {
  cases.push(materialize(`CONDITIONAL-POSITIVE-${skillId}`, "CONDITIONAL_POSITIVE", skillId, positive));
  cases.push(materialize(`CONDITIONAL-NEGATIVE-${skillId}`, "CONDITIONAL_NEGATIVE", skillId, negative));
}

console.log(
  JSON.stringify(
    {
      fixture_version: "J02-0002",
      inventory_id: inventory.inventory_id,
      inventory_hash: inventory.inventory_hash,
      case_count: cases.length,
      cases,
    },
    null,
    2,
  ),
);
