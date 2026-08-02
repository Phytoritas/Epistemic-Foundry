// The evolution plugin surface: which skills EVOLVE owns, what they may name on
// the CLI, and what they may disclose.
//
// This module declares nothing it can read.  The skill set, reference closure
// and budgets come from the payload skill inventory, the CLI commands from the
// sealed tool-surface projection, the proposed evolution CLI from the spec
// section that proposes it, and the mutable search space from the sealed C05
// index.  What G05 adds is the binding between them and the refusal that keeps
// the binding honest: a skill cannot name a command the tool surface does not
// project, cannot mutate a genome outside the sealed search space, cannot
// disclose past the declared context budget, and cannot name a command that
// carries promotion authority.
//
// It routes; it owns no state.  Selection is delegated to the sealed J01 policy
// function, and no skill body or reference body is ever read here — only their
// declared metadata and hashes.

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { commandSurface } from "../../../packages/plugin-host/src/cli/command-surface.mjs";
import {
  canonicalizeSkillRoutingJson,
  computeSkillRoutingDecisionHash,
  routeSkillRequest,
} from "../../../packages/plugin-host/src/skill-router/skill-router.mjs";

/** Repository root, resolved from this file rather than the process cwd. */
export const REPOSITORY_ROOT = fileURLToPath(new URL("../../../", import.meta.url));

export const SURFACE_PATH = "plugin_blueprint/epistemic-foundry/v4_g05/evolution-surface.json";
export const INVENTORY_PATH = "plugins/epistemic-foundry/skills/skill-inventory.json";
export const PAYLOAD_ROOT = "plugins/epistemic-foundry";
export const SPEC_PATH = "MASTER_SPEC.md";
export const FAMILY_INDEX_PATH = "schemas/v4_c05/family-index.json";
export const ROUTING_DECISION_SCHEMA_PATH = "schemas/skill-routing-decision.schema.json";

/** Every way this surface refuses, and why that refusal exists. */
export const FINDING_CODES = Object.freeze({
  AUTHORITY_CLAIMED:
    "an evolution skill named a command that carries promotion authority; the plugin skill layer routes requests and never owns promotion",
  AUTHORITY_PREDICATE_EMPTY:
    "the authority-bearing command predicate matched nothing, which would make the authority check vacuous rather than satisfied",
  COMMAND_CLAIMED_TWICE:
    "two skills claimed the same proposed command, so that part of the CLI surface would have no single owner",
  COMMAND_MISDECLARED:
    "a command declared as proposed is already projected by the tool surface, and understating the surface hides a command that exists",
  COMMAND_UNPROJECTED:
    "a skill declared a command as available that the sealed tool surface does not project",
  COMMAND_UNPROPOSED:
    "a declared command is absent from the CLI the specification proposes, so the surface invented it",
  DECLARATION_NONCANONICAL:
    "the declaration is not in canonical form (sorted, unique, exactly the declared fields), so two equal surfaces could hash differently",
  DISCLOSURE_BUDGET_EXCEEDED:
    "a skill's maximal reference closure exceeds a declared progressive-disclosure budget",
  INVENTORY_HASH_DRIFT:
    "the payload skill inventory no longer matches the files it describes, so its metadata is not evidence of what ships",
  MEMBERSHIP_DRIFT:
    "the declared evolution skill set differs from the set the membership rule derives from the inventory",
  PARENT_UNDECLARED: "the declared parent skill is not the parent the inventory declares",
  POLICY_DRIFT:
    "a skill's payload invocation policy disagrees with the inventory projection of that same policy",
  PROPOSED_COMMAND_UNROUTED:
    "a command the specification proposes is claimed by no skill, so part of the proposed CLI has no owner",
  REFERENCE_UNDECLARED: "a skill depends on a reference the inventory does not declare",
  SEARCH_SPACE_VIOLATION:
    "a skill declared it mutates a genome kind outside the sealed mutable search space",
  SKILL_OUT_OF_SURFACE: "the requested skill is not part of the evolution surface",
  SPEC_BLOCK_MISSING: "the specification section that proposes the evolution CLI could not be read",
  SURFACE_UNREADABLE: "the surface declaration could not be read as the object this module requires",
});

export class EvolutionSurfaceError extends Error {
  constructor(code, message, context = {}) {
    super(message);
    this.name = "EvolutionSurfaceError";
    this.code = code;
    this.context = context;
  }
}

const fail = (code, message, context = {}) => {
  throw new EvolutionSurfaceError(code, message, context);
};

const SKILL_FIELDS = Object.freeze([
  "skill_id",
  "mutable_kinds",
  "proposed_commands",
  "available_commands",
]);
const SURFACE_FIELDS = Object.freeze([
  "surface_id",
  "surface_version",
  "parent_skill_id",
  "membership",
  "authority_objects",
  "denied_authority",
  "skills",
]);
const MEMBERSHIP_FIELDS = Object.freeze(["reference_id_prefixes", "reference_ids"]);
/** The authorities the exit criteria forbid a routing layer from acquiring. */
const DENIED_AUTHORITY = Object.freeze(["evaluator_mutation", "holdout_read", "promotion"]);
/** The effect class of a command that performs an effect rather than planning one. */
const MUTATING = "MUTATING_EFFECT";

const readBytes = (root, relative) => {
  try {
    return readFileSync(join(root, relative));
  } catch (error) {
    fail("SURFACE_UNREADABLE", `cannot read ${relative}: ${error.message}`, { path: relative });
    return Buffer.alloc(0);
  }
};

const readText = (root, relative) => readBytes(root, relative).toString("utf8");

const readJson = (root, relative) => {
  const text = readText(root, relative);
  try {
    return JSON.parse(text);
  } catch (error) {
    fail("SURFACE_UNREADABLE", `${relative} is not JSON: ${error.message}`, { path: relative });
    return undefined;
  }
};

const sha256 = (bytes) => `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

const isPlainObject = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);

const requireFields = (value, fields, label) => {
  if (!isPlainObject(value)) {
    fail("SURFACE_UNREADABLE", `${label} must be an object`, { label });
  }
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail("SURFACE_UNREADABLE", `${label} must declare exactly ${expected.join(", ")}`, {
      actual,
      expected,
    });
  }
  return value;
};

const requireCanonicalStrings = (value, label) => {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) {
    fail("DECLARATION_NONCANONICAL", `${label} must be an array of strings`, { label });
  }
  const sorted = [...value].sort();
  if (value.some((entry, index) => entry !== sorted[index])) {
    fail("DECLARATION_NONCANONICAL", `${label} must be sorted`, { label, value });
  }
  if (new Set(value).size !== value.length) {
    fail("DECLARATION_NONCANONICAL", `${label} must not repeat an entry`, { label, value });
  }
  return Object.freeze([...value]);
};

/**
 * The evolution CLI the specification proposes, read from the section that
 * proposes it.  `efoundry evolve setup|convert` expands to two commands, so a
 * verb the specification never proposes cannot enter the surface.
 */
export const parseProposedCommands = (specText) => {
  const block = /\n## 35\. Proposed CLI\n+```text\n([\s\S]*?)\n```/u.exec(specText);
  if (block === null) {
    fail("SPEC_BLOCK_MISSING", "MASTER_SPEC.md does not carry the proposed CLI block");
  }
  const commands = [];
  for (const line of block[1].split("\n")) {
    const trimmed = line.trim();
    if (trimmed.length === 0) continue;
    const tokens = trimmed.split(/\s+/u);
    if (tokens[0] !== "efoundry") {
      fail("SPEC_BLOCK_MISSING", `the proposed CLI block holds a non-CLI line: ${trimmed}`, {
        line: trimmed,
      });
    }
    const rest = tokens.slice(1);
    for (const verb of rest[rest.length - 1].split("|")) {
      commands.push([...rest.slice(0, -1), verb].join(" "));
    }
  }
  if (commands.length === 0) {
    fail("SPEC_BLOCK_MISSING", "the proposed CLI block proposes no command");
  }
  return Object.freeze(commands.sort());
};

/**
 * Read a payload skill's agent card: its invocation policy and, if it declares
 * one, its activation phrase lists.
 *
 * Only the two blocks this surface uses are parsed, and any line inside them
 * that the reader does not recognise fails closed.  A permissive reader would
 * let an unreadable policy pass as an absent one, which is exactly the case
 * that must not silently succeed.
 */
export const parseAgentCard = (yamlText, label) => {
  const policy = {};
  const phrases = { should_not_trigger: [], should_trigger: [] };
  let block = null;
  let listKey = null;
  for (const rawLine of yamlText.split("\n")) {
    const line = rawLine.replace(/\r$/u, "");
    if (line.trim().length === 0) continue;
    if (!line.startsWith(" ")) {
      block = line.trim().replace(/:$/u, "");
      listKey = null;
      continue;
    }
    if (block === "policy") {
      const match = /^ {2}([a-z_]+): (.+)$/u.exec(line);
      if (match === null) {
        fail("POLICY_DRIFT", `${label} holds an unreadable policy line: ${line.trim()}`, { label });
      }
      const [, key, raw] = match;
      policy[key] = raw === "true" ? true : raw === "false" ? false : raw.replace(/^"(.*)"$/u, "$1");
      continue;
    }
    if (block === "activation") {
      const heading = /^ {2}([a-z_]+):$/u.exec(line);
      if (heading !== null) {
        listKey = heading[1];
        if (!Object.hasOwn(phrases, listKey)) {
          fail("POLICY_DRIFT", `${label} declares an unknown activation list ${listKey}`, { label });
        }
        continue;
      }
      const item = /^ {4}- "(.+)"$/u.exec(line);
      if (item === null || listKey === null) {
        fail("POLICY_DRIFT", `${label} holds an unreadable activation line: ${line.trim()}`, {
          label,
        });
      }
      phrases[listKey].push(item[1]);
    }
  }
  if (Object.keys(policy).length === 0) {
    fail("POLICY_DRIFT", `${label} declares no invocation policy`, { label });
  }
  return Object.freeze({
    exclusionPhrases: Object.freeze([...phrases.should_not_trigger]),
    policy: Object.freeze(policy),
    triggerPhrases: Object.freeze([...phrases.should_trigger]),
  });
};

const agentCard = (root, skillId) =>
  parseAgentCard(
    readText(root, `${PAYLOAD_ROOT}/skills/${skillId}/agents/openai.yaml`),
    `${skillId}/agents/openai.yaml`,
  );

const verifyInventoryIntegrity = (root, inventory) => {
  const stated = inventory.inventory_hash;
  const withoutHash = { ...inventory };
  delete withoutHash.inventory_hash;
  const recomputed = sha256(Buffer.from(canonicalizeSkillRoutingJson(withoutHash), "utf8"));
  if (recomputed !== stated) {
    fail("INVENTORY_HASH_DRIFT", "the skill inventory does not hash to its stated value", {
      recomputed,
      stated,
    });
  }
  for (const row of [...inventory.skills, ...inventory.references]) {
    const bytes = readBytes(root, `${PAYLOAD_ROOT}/${row.path}`);
    const digest = sha256(bytes);
    if (digest !== row.sha256 || bytes.length !== row.byte_count) {
      fail("INVENTORY_HASH_DRIFT", `${row.path} differs from the inventory record`, {
        actual_byte_count: bytes.length,
        actual_sha256: digest,
        declared_byte_count: row.byte_count,
        declared_sha256: row.sha256,
        path: row.path,
      });
    }
  }
};

const referenceIds = (skill) => [
  ...skill.direct_references,
  ...skill.conditional_references.map((row) => row.reference_id),
];

/** The skills the membership rule makes part of the evolution surface. */
export const deriveEvolutionSkillIds = (inventory, membership) => {
  const matches = (id) =>
    membership.reference_ids.includes(id) ||
    membership.reference_id_prefixes.some((prefix) => id.startsWith(prefix));
  return Object.freeze(
    inventory.skills
      .filter((skill) => referenceIds(skill).some(matches))
      .map((skill) => skill.skill_id)
      .sort(),
  );
};

const predicateHolds = (predicate, context) => {
  const value = context[predicate.key];
  if (predicate.operator === "EQUALS") return value === predicate.value;
  if (predicate.operator === "ANY_OF") return predicate.value.includes(value);
  fail("REFERENCE_UNDECLARED", `unsupported reference predicate ${predicate.operator}`, {
    operator: predicate.operator,
  });
  return false;
};

/**
 * Resolve what a skill may disclose in one activation.
 *
 * The closure follows the inventory's own dependency edges, so a reference a
 * skill never names still counts when a reference it does name depends on it.
 * Only declared sizes are read; no reference body is opened.
 */
export const resolveDisclosure = (loaded, skillId, context = {}) => {
  const skill = loaded.inventory.skills.find((row) => row.skill_id === skillId);
  if (skill === undefined) {
    fail("SKILL_OUT_OF_SURFACE", `${skillId} is not declared by the payload inventory`, {
      skill_id: skillId,
    });
  }
  const depth = new Map();
  const queue = [];
  for (const id of skill.direct_references) queue.push([id, 1]);
  for (const row of skill.conditional_references) {
    if (predicateHolds(row.predicate, context)) queue.push([row.reference_id, 1]);
  }
  while (queue.length > 0) {
    const [id, level] = queue.shift();
    const reference = loaded.referencesById.get(id);
    if (reference === undefined) {
      fail("REFERENCE_UNDECLARED", `${skillId} depends on undeclared reference ${id}`, {
        reference_id: id,
        skill_id: skillId,
      });
    }
    if (depth.has(id) && depth.get(id) <= level) continue;
    depth.set(id, level);
    for (const next of reference.depends_on) queue.push([next, level + 1]);
  }
  const ids = [...depth.keys()].sort();
  const closure = ids.map((id) => loaded.referencesById.get(id));
  const closureBytes = closure.reduce((total, row) => total + row.byte_count, 0);
  const closureTokens = closure.reduce((total, row) => total + row.token_count, 0);
  const projection = loaded.inventory.metadata_projection;
  return Object.freeze({
    activation_o200k_tokens: projection.token_count + skill.token_count + closureTokens,
    activation_utf8_bytes: projection.byte_count + skill.byte_count + closureBytes,
    closure_depth: ids.length === 0 ? 0 : Math.max(...depth.values()),
    closure_o200k_tokens: closureTokens,
    closure_utf8_bytes: closureBytes,
    reference_ids: Object.freeze(ids),
    skill_id: skillId,
  });
};

const BUDGET_CHECKS = Object.freeze([
  ["reference_count", "reference_closure_max_count", (plan) => plan.reference_ids.length],
  ["closure_depth", "reference_closure_max_depth", (plan) => plan.closure_depth],
  ["closure_utf8_bytes", "reference_closure_max_utf8_bytes", (plan) => plan.closure_utf8_bytes],
  [
    "closure_o200k_tokens",
    "reference_closure_max_o200k_tokens",
    (plan) => plan.closure_o200k_tokens,
  ],
  ["activation_utf8_bytes", "activation_max_utf8_bytes", (plan) => plan.activation_utf8_bytes],
  [
    "activation_o200k_tokens",
    "activation_max_o200k_tokens",
    (plan) => plan.activation_o200k_tokens,
  ],
]);

/** The context that turns on every conditional reference at once. */
export const MAXIMAL_DISCLOSURE_CONTEXT = Object.freeze({
  artifact_kind: "ValidationResult",
  backend_id: "shinka",
  candidate_origin: "EVOLUTION",
});

export const assertWithinBudget = (loaded, plan) => {
  for (const [field, budgetKey, read] of BUDGET_CHECKS) {
    const used = read(plan);
    const limit = loaded.inventory.budgets[budgetKey];
    if (typeof limit !== "number") {
      fail("DISCLOSURE_BUDGET_EXCEEDED", `the inventory declares no ${budgetKey} budget`, {
        budget: budgetKey,
      });
    }
    if (used > limit) {
      fail("DISCLOSURE_BUDGET_EXCEEDED", `${plan.skill_id} exceeds ${budgetKey}`, {
        budget: budgetKey,
        field,
        limit,
        skill_id: plan.skill_id,
        used,
      });
    }
  }
  return plan;
};

/**
 * The commands that carry promotion authority.
 *
 * The predicate is declared by this surface; the tool names and their effect
 * classes are read from the sealed catalog, so a new promotion command joins
 * this set without the surface being edited.
 */
export const deriveAuthorityBearingCommands = (projected, authorityObjects) =>
  Object.freeze(
    projected
      .filter((row) => row.mutating && authorityObjects.includes(row.tool.split(".")[1]))
      .map((row) => row.command)
      .sort(),
  );

const verifyCommands = (loaded) => {
  const proposed = new Set(loaded.proposedCommands);
  const projected = new Map(loaded.projectedCommands.map((row) => [row.command, row]));
  const claimed = new Map();
  for (const skill of loaded.surface.skills) {
    for (const command of skill.proposed_commands) {
      if (!proposed.has(command)) {
        fail("COMMAND_UNPROPOSED", `${skill.skill_id} claims unproposed command "${command}"`, {
          command,
          skill_id: skill.skill_id,
        });
      }
      if (projected.has(command)) {
        fail("COMMAND_MISDECLARED", `"${command}" is already projected by the tool surface`, {
          command,
          skill_id: skill.skill_id,
        });
      }
      if (claimed.has(command)) {
        fail("COMMAND_CLAIMED_TWICE", `"${command}" is claimed by two skills`, {
          command,
          skill_ids: [claimed.get(command), skill.skill_id],
        });
      }
      claimed.set(command, skill.skill_id);
    }
    for (const command of skill.available_commands) {
      if (!projected.has(command)) {
        fail("COMMAND_UNPROJECTED", `${skill.skill_id} names unprojected command "${command}"`, {
          command,
          skill_id: skill.skill_id,
        });
      }
      if (loaded.authorityBearingCommands.includes(command)) {
        fail("AUTHORITY_CLAIMED", `${skill.skill_id} names authority-bearing "${command}"`, {
          command,
          skill_id: skill.skill_id,
        });
      }
    }
  }
  const unrouted = [...proposed].filter((command) => !claimed.has(command)).sort();
  if (unrouted.length > 0) {
    fail("PROPOSED_COMMAND_UNROUTED", "part of the proposed evolution CLI has no owner", {
      unrouted,
    });
  }
  return claimed;
};

/** Read, cross-check and freeze the whole evolution surface. */
export const loadSurface = ({ root = REPOSITORY_ROOT } = {}) => {
  const surface = requireFields(readJson(root, SURFACE_PATH), SURFACE_FIELDS, "surface");
  requireFields(surface.membership, MEMBERSHIP_FIELDS, "surface.membership");
  requireCanonicalStrings(surface.membership.reference_ids, "membership.reference_ids");
  requireCanonicalStrings(
    surface.membership.reference_id_prefixes,
    "membership.reference_id_prefixes",
  );
  const denied = requireCanonicalStrings(surface.denied_authority, "denied_authority");
  if (denied.join("|") !== DENIED_AUTHORITY.join("|")) {
    fail("AUTHORITY_CLAIMED", "denied_authority is not the canonical denied set", {
      declared: denied,
      expected: DENIED_AUTHORITY,
    });
  }
  const authorityObjects = requireCanonicalStrings(surface.authority_objects, "authority_objects");

  const inventory = readJson(root, INVENTORY_PATH);
  verifyInventoryIntegrity(root, inventory);
  if (surface.parent_skill_id !== inventory.parent_skill_id) {
    fail("PARENT_UNDECLARED", "the surface parent is not the inventory parent", {
      declared: surface.parent_skill_id,
      inventory: inventory.parent_skill_id,
    });
  }

  const declaredIds = requireCanonicalStrings(
    surface.skills.map((skill) => skill.skill_id),
    "skills[].skill_id",
  );
  const derivedIds = deriveEvolutionSkillIds(inventory, surface.membership);
  if (declaredIds.join("|") !== derivedIds.join("|")) {
    fail("MEMBERSHIP_DRIFT", "the declared evolution skills are not the derived ones", {
      declared: declaredIds,
      derived: derivedIds,
    });
  }

  const mutableSearchSpace = readJson(root, FAMILY_INDEX_PATH).mutable_search_space;
  for (const skill of surface.skills) {
    requireFields(skill, SKILL_FIELDS, `skills[${skill.skill_id}]`);
    requireCanonicalStrings(skill.proposed_commands, `${skill.skill_id}.proposed_commands`);
    requireCanonicalStrings(skill.available_commands, `${skill.skill_id}.available_commands`);
    const kinds = requireCanonicalStrings(skill.mutable_kinds, `${skill.skill_id}.mutable_kinds`);
    for (const kind of kinds) {
      if (!mutableSearchSpace.includes(kind)) {
        fail("SEARCH_SPACE_VIOLATION", `${skill.skill_id} declares mutation of ${kind}`, {
          kind,
          mutable_search_space: mutableSearchSpace,
          skill_id: skill.skill_id,
        });
      }
    }
  }

  const projectedCommands = commandSurface();
  const authorityBearingCommands = deriveAuthorityBearingCommands(
    projectedCommands,
    authorityObjects,
  );
  if (authorityBearingCommands.length === 0) {
    fail(
      "AUTHORITY_PREDICATE_EMPTY",
      "no projected command matched the authority predicate, so the authority check would be vacuous",
      { authority_objects: authorityObjects },
    );
  }

  const loaded = {
    agentCards: new Map(
      surface.skills.map((skill) => [skill.skill_id, agentCard(root, skill.skill_id)]),
    ),
    authorityBearingCommands,
    inventory,
    mutableSearchSpace: Object.freeze([...mutableSearchSpace]),
    projectedCommands: Object.freeze(projectedCommands),
    proposedCommands: parseProposedCommands(readText(root, SPEC_PATH)),
    referencesById: new Map(inventory.references.map((row) => [row.reference_id, row])),
    root,
    surface,
  };

  for (const skill of surface.skills) {
    const card = loaded.agentCards.get(skill.skill_id);
    const projection = inventory.skills.find((row) => row.skill_id === skill.skill_id);
    if (
      card.policy.invocation_disposition !== projection.invocation_disposition ||
      card.policy.allow_implicit_invocation !== projection.allow_implicit_invocation
    ) {
      fail("POLICY_DRIFT", `${skill.skill_id} policy differs from its inventory projection`, {
        declared_disposition: card.policy.invocation_disposition,
        declared_implicit: card.policy.allow_implicit_invocation,
        projected_disposition: projection.invocation_disposition,
        projected_implicit: projection.allow_implicit_invocation,
        skill_id: skill.skill_id,
      });
    }
    assertWithinBudget(
      loaded,
      resolveDisclosure(loaded, skill.skill_id, MAXIMAL_DISCLOSURE_CONTEXT),
    );
  }
  verifyCommands(loaded);
  return Object.freeze(loaded);
};

const skillCandidate = (loaded, skillId) => {
  const projection = loaded.inventory.skills.find((row) => row.skill_id === skillId);
  const card = loaded.agentCards.get(skillId);
  return {
    skill_id: skillId,
    description: projection.description,
    content_hash: projection.sha256,
    source: "bundled",
    allow_implicit_invocation: projection.allow_implicit_invocation,
    sensitive: card.policy.sensitive === true,
    side_effecting: card.policy.side_effecting === true,
    trigger_phrases: [...card.triggerPhrases],
    exclusion_phrases: [...card.exclusionPhrases],
  };
};

/**
 * An immutable receipt for the surface: what it read, what it bound, and the
 * hash of exactly those bytes.  Every source is named with its digest, so a
 * later run can prove whether the surface it validated is the surface that
 * shipped.
 */
export const surfaceReceipt = (loaded) => {
  const sources = [
    SURFACE_PATH,
    INVENTORY_PATH,
    FAMILY_INDEX_PATH,
    SPEC_PATH,
    ROUTING_DECISION_SCHEMA_PATH,
  ]
    .sort()
    .map((path) => ({ path, sha256: sha256(readBytes(loaded.root, path)) }));
  const byCommand = new Map(loaded.projectedCommands.map((row) => [row.command, row]));
  const availableCommands = [
    ...new Set(loaded.surface.skills.flatMap((row) => row.available_commands)),
  ].sort();
  const preimage = {
    authority_bearing_commands: [...loaded.authorityBearingCommands],
    available_commands: availableCommands.map((command) => ({
      command,
      side_effect_class: byCommand.get(command).mutating ? MUTATING : "NON_MUTATING",
    })),
    denied_authority: [...loaded.surface.denied_authority],
    implicitly_reachable_skill_ids: loaded.surface.skills
      .map((row) => row.skill_id)
      .filter((skillId) => loaded.agentCards.get(skillId).triggerPhrases.length > 0)
      .sort(),
    inventory_hash: loaded.inventory.inventory_hash,
    mutable_kinds_claimed: [
      ...new Set(loaded.surface.skills.flatMap((row) => row.mutable_kinds)),
    ].sort(),
    mutable_kinds_unclaimed: loaded.mutableSearchSpace
      .filter((kind) => !loaded.surface.skills.some((row) => row.mutable_kinds.includes(kind)))
      .sort(),
    parent_skill_id: loaded.surface.parent_skill_id,
    projected_command_count: loaded.projectedCommands.length,
    proposed_command_count: loaded.proposedCommands.length,
    proposed_commands_projected: loaded.proposedCommands.filter((command) =>
      byCommand.has(command),
    ),
    skill_count: loaded.surface.skills.length,
    sources,
    surface_id: loaded.surface.surface_id,
    surface_version: loaded.surface.surface_version,
  };
  const receiptHash = computeSkillRoutingDecisionHash(preimage);
  return Object.freeze({
    receipt_id: `EFG05-SURFACE-${receiptHash.slice("sha256:".length, "sha256:".length + 16)}`,
    ...preimage,
    receipt_hash: receiptHash,
  });
};

/**
 * Route one request across the evolution surface.
 *
 * Selection is delegated to the sealed J01 policy function; this adds only what
 * the evolution surface knows: which skills are in scope, what the selected one
 * may disclose under this request's context, and which commands it may name.
 * The result is metadata.  It is not permission to run anything.
 */
export const routeEvolutionRequest = (
  loaded,
  { requestId, requestText, explicitSkillId = null, decidedAt, context = {} },
) => {
  if (
    explicitSkillId !== null &&
    !loaded.surface.skills.some((row) => row.skill_id === explicitSkillId)
  ) {
    fail("SKILL_OUT_OF_SURFACE", `${explicitSkillId} is not an evolution skill`, {
      skill_id: explicitSkillId,
    });
  }
  const decision = routeSkillRequest({
    request_id: requestId,
    request_text: requestText,
    explicit_skill_id: explicitSkillId,
    candidates: loaded.surface.skills.map((row) => skillCandidate(loaded, row.skill_id)),
    context_budget_tokens: loaded.inventory.budgets.activation_max_o200k_tokens,
    policy_hash: surfaceReceipt(loaded).receipt_hash,
    decided_at: decidedAt,
  });
  const selected = decision.selected_skill_ids[0] ?? null;
  const row =
    selected === null ? null : loaded.surface.skills.find((entry) => entry.skill_id === selected);
  return Object.freeze({
    available_commands: Object.freeze(row === null ? [] : [...row.available_commands]),
    decision,
    disclosure: selected === null ? null : resolveDisclosure(loaded, selected, context),
    proposed_commands_unavailable: Object.freeze(row === null ? [] : [...row.proposed_commands]),
    selected_skill_id: selected,
  });
};
