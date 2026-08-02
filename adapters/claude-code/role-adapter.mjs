// The Claude Code custom-agent adapter: canonical role -> agent descriptor.
//
// The role vocabulary is `manifests/role_registry.yaml` (authority 6).  The
// host-side compilation choice — which Claude Code surface carries a role, which
// schema its result is checked against, and whether its writes run in an
// isolated worktree — is declared by `adapters/claude-code/role_mapping.yaml`.
// This module binds the two and refuses when they disagree, so a mapping cannot
// quietly widen, narrow or rename the role set, nor drop a write-capable role's
// isolation.
//
// The descriptor is metadata.  It names a role, the concrete Claude Code tool
// grant its write scope earns, its output schema and its isolation mode; it does
// not launch an agent, create a worktree, hold a lease or grant an ACL.  The
// concrete tool names and the model come from the binding declaration, never
// from a literal here.
//
// The repository ships no YAML parser for Node, so both sources are read by a
// bounded line reader that accepts exactly the constructs these two files use
// and refuses every other line.  A permissive reader would let an unreadable
// role pass as an absent one, which is the case that must not silently succeed.

import { canonicalizeHookJson, sha256HookJson } from "../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  deepFreeze,
  fail,
  isPlainObject,
  readText,
  REPOSITORY_ROOT,
  requireFields,
  ROLE_MAPPING_PATH,
  ROLE_REGISTRY_PATH,
  selectDeclared,
} from "./claude-declarations.mjs";

const REGISTRY_UNREADABLE = "REGISTRY_UNREADABLE";
const MAPPING_UNREADABLE = "MAPPING_UNREADABLE";

/** The Claude Code role-capable surfaces this adapter knows how to target. */
export const AGENT_SURFACES = Object.freeze(["custom_agent", "skill", "slash_command"]);

/** The worktree-isolation modes this adapter declares for a role's write scope. */
export const ISOLATION_MODES = Object.freeze(["shared", "worktree"]);

/** The RoleSpec fields `manifests/role_registry.yaml` declares for every role. */
export const ROLE_REGISTRY_FIELDS = Object.freeze([
  "claude_agent_name",
  "codex_agent_type",
  "default_timeout_seconds",
  "evidence_acl",
  "forbidden",
  "independent_review_required",
  "mission",
  "model_tier",
  "output_schema_ref",
  "role_id",
  "tool_acl",
  "write_scope",
]);

/** The fields `adapters/claude-code/role_mapping.yaml` declares for every role. */
export const ROLE_MAPPING_FIELDS = Object.freeze(["isolation", "result_schema", "surface"]);

/** The descriptor fields this adapter publishes for one Claude Code custom agent. */
export const DESCRIPTOR_FIELDS = Object.freeze([
  "default_timeout_seconds",
  "description",
  "evidence_acl",
  "forbidden",
  "independent_review_required",
  "isolation",
  "model",
  "model_tier",
  "name",
  "output_schema_ref",
  "role_id",
  "surface",
  "tool_acl",
  "tools",
  "write_scope",
]);

const decodeScalar = (raw) => {
  if (raw === "true") return true;
  if (raw === "false") return false;
  if (/^-?[0-9]+$/u.test(raw)) return Number(raw);
  const quoted = /^'(.*)'$/u.exec(raw);
  return quoted === null ? raw : quoted[1];
};

const lines = (text) =>
  text
    .split("\n")
    .map((line) => line.replace(/\r$/u, ""))
    .filter((line) => line.trim().length > 0);

/**
 * Read `manifests/role_registry.yaml` as a list of RoleSpec records.
 *
 * The subset covered is exactly what that file uses: two top-level keys, a
 * sequence of role mappings, block sequences, folded plain scalars, and the one
 * anchor/alias pair the shared `forbidden` list uses.  Anything else refuses.
 */
export const parseRoleRegistry = (text, label = ROLE_REGISTRY_PATH) => {
  const roles = [];
  const anchors = new Map();
  let version = null;
  let inRoles = false;
  let role = null;
  let listKey = null;
  let listAnchor = null;
  let scalarKey = null;

  for (const line of lines(text)) {
    const top = /^([a-z_]+):(?: (.+))?$/u.exec(line);
    if (top !== null) {
      const [, key, value] = top;
      listKey = null;
      listAnchor = null;
      scalarKey = null;
      if (key === "version" && value !== undefined) {
        version = decodeScalar(value);
        inRoles = false;
        continue;
      }
      if (key === "roles" && value === undefined) {
        inRoles = true;
        continue;
      }
      fail(REGISTRY_UNREADABLE, `${label} holds an unsupported top-level key "${key}"`, { key, label });
    }

    const start = /^- role_id: (.+)$/u.exec(line);
    if (start !== null) {
      if (!inRoles) fail(REGISTRY_UNREADABLE, `${label} declares a role outside the roles block`, { label });
      role = { role_id: decodeScalar(start[1]) };
      roles.push(role);
      listKey = null;
      listAnchor = null;
      scalarKey = "role_id";
      continue;
    }

    const field = /^ {2}([a-z_]+):(?: (.+))?$/u.exec(line);
    if (field !== null) {
      if (role === null) fail(REGISTRY_UNREADABLE, `${label} declares a field outside a role`, { label });
      const [, key, value] = field;
      listKey = null;
      listAnchor = null;
      scalarKey = null;
      if (Object.hasOwn(role, key)) {
        fail(REGISTRY_UNREADABLE, `${label} declares "${key}" twice for ${role.role_id}`, { key, label });
      }
      if (value === undefined || value === "[]") {
        role[key] = [];
        if (value === undefined) listKey = key;
        continue;
      }
      const anchor = /^&([A-Za-z0-9_]+)$/u.exec(value);
      if (anchor !== null) {
        role[key] = [];
        listKey = key;
        listAnchor = anchor[1];
        continue;
      }
      const alias = /^\*([A-Za-z0-9_]+)$/u.exec(value);
      if (alias !== null) {
        if (!anchors.has(alias[1])) {
          fail(REGISTRY_UNREADABLE, `${label} aliases the undefined anchor "${alias[1]}"`, { label });
        }
        role[key] = [...anchors.get(alias[1])];
        continue;
      }
      role[key] = decodeScalar(value);
      scalarKey = key;
      continue;
    }

    const item = /^ {2}- (.+)$/u.exec(line);
    if (item !== null) {
      if (role === null || listKey === null) {
        fail(REGISTRY_UNREADABLE, `${label} holds a sequence item under no key: ${line.trim()}`, { label });
      }
      role[listKey].push(decodeScalar(item[1]));
      if (listAnchor !== null) anchors.set(listAnchor, role[listKey]);
      continue;
    }

    const continuation = /^ {4}(\S.*)$/u.exec(line);
    if (continuation !== null) {
      if (role === null || scalarKey === null || typeof role[scalarKey] !== "string") {
        fail(REGISTRY_UNREADABLE, `${label} continues a scalar that is not open: ${line.trim()}`, { label });
      }
      role[scalarKey] = `${role[scalarKey]} ${continuation[1]}`;
      continue;
    }

    fail(REGISTRY_UNREADABLE, `${label} holds an unreadable line: ${line.trim()}`, {
      label,
      line: line.trim(),
    });
  }

  if (typeof version !== "string") {
    fail(REGISTRY_UNREADABLE, `${label} declares no version`, { label });
  }
  if (roles.length === 0) fail(REGISTRY_UNREADABLE, `${label} declares no role`, { label });
  for (const entry of roles) {
    requireFields(entry, ROLE_REGISTRY_FIELDS, `${label}#${entry.role_id}`, REGISTRY_UNREADABLE);
  }
  return deepFreeze({ roles, version });
};

/**
 * Read `adapters/claude-code/role_mapping.yaml` as role_id -> host compilation
 * record.  The same fail-closed discipline applies: the subset is exactly what
 * that file uses, and an unrecognised line refuses rather than being skipped.
 */
export const parseRoleMapping = (text, label = ROLE_MAPPING_PATH) => {
  const roles = {};
  const constraints = [];
  let version = null;
  let strategy = null;
  let section = null;
  let role = null;

  for (const line of lines(text)) {
    const top = /^([a-z_]+):(?: (.+))?$/u.exec(line);
    if (top !== null) {
      const [, key, value] = top;
      role = null;
      if (key === "version" && value !== undefined) {
        version = decodeScalar(value);
        section = null;
        continue;
      }
      if (key === "strategy" && value !== undefined) {
        strategy = decodeScalar(value);
        section = null;
        continue;
      }
      if ((key === "roles" || key === "constraints") && value === undefined) {
        section = key;
        continue;
      }
      fail(MAPPING_UNREADABLE, `${label} holds an unsupported top-level key "${key}"`, { key, label });
    }

    const constraint = /^- (.+)$/u.exec(line);
    if (constraint !== null) {
      if (section !== "constraints") {
        fail(MAPPING_UNREADABLE, `${label} holds a constraint outside the constraints block`, { label });
      }
      constraints.push(decodeScalar(constraint[1]));
      continue;
    }

    const roleKey = /^ {2}([a-z0-9_]+):$/u.exec(line);
    if (roleKey !== null) {
      if (section !== "roles") {
        fail(MAPPING_UNREADABLE, `${label} holds a role outside the roles block`, { label });
      }
      if (Object.hasOwn(roles, roleKey[1])) {
        fail(MAPPING_UNREADABLE, `${label} declares role "${roleKey[1]}" twice`, { label });
      }
      role = {};
      roles[roleKey[1]] = role;
      continue;
    }

    const field = /^ {4}([a-z_]+): (.+)$/u.exec(line);
    if (field !== null) {
      if (role === null) fail(MAPPING_UNREADABLE, `${label} declares a field outside a role`, { label });
      role[field[1]] = decodeScalar(field[2]);
      continue;
    }

    fail(MAPPING_UNREADABLE, `${label} holds an unreadable line: ${line.trim()}`, {
      label,
      line: line.trim(),
    });
  }

  if (typeof version !== "string" || typeof strategy !== "string") {
    fail(MAPPING_UNREADABLE, `${label} declares no version or no strategy`, { label });
  }
  const ids = Object.keys(roles);
  if (ids.length === 0) fail(MAPPING_UNREADABLE, `${label} maps no role`, { label });
  for (const id of ids) {
    requireFields(roles[id], ROLE_MAPPING_FIELDS, `${label}#${id}`, MAPPING_UNREADABLE);
  }
  return deepFreeze({ constraints, roles, strategy, version });
};

/** Whether a RoleSpec write scope makes the role a writer at all. */
export const isWriteCapable = (spec) => Array.isArray(spec.write_scope) && spec.write_scope.length > 0;

/** The isolation mode a role's write scope earns: a writer is isolated, a reader is shared. */
export const isolationFor = (spec) => (isWriteCapable(spec) ? "worktree" : "shared");

/**
 * The concrete Claude Code tool grant a role earns.
 *
 * Every agent holds the read tools the binding declares; a write-capable role
 * additionally holds the write tool.  Order follows the declaration so the grant
 * is byte-stable and matches the frontmatter a generated agent file would carry.
 */
export const deriveTools = (spec, { baseTools, writeTool }) =>
  Object.freeze(isWriteCapable(spec) ? [...baseTools, writeTool] : [...baseTools]);

const descriptorFor = (spec, mapped, options) =>
  deepFreeze({
    default_timeout_seconds: spec.default_timeout_seconds,
    description: spec.mission,
    evidence_acl: [...spec.evidence_acl],
    forbidden: [...spec.forbidden],
    independent_review_required: spec.independent_review_required,
    isolation: mapped.isolation,
    model: options.model,
    model_tier: spec.model_tier,
    name: spec.claude_agent_name,
    output_schema_ref: spec.output_schema_ref,
    role_id: spec.role_id,
    surface: mapped.surface,
    tool_acl: [...spec.tool_acl],
    tools: deriveTools(spec, options),
    write_scope: [...spec.write_scope],
  });

/**
 * Build the whole role_id -> Claude Code agent descriptor table.
 *
 * Deterministic and byte-stable: the table is sorted by role id, every field is
 * copied from or derived from a declaring source, and nothing here reads a clock,
 * an environment variable or a random number.  Rebuilding it from the same two
 * files and the same declaration yields the same bytes and therefore the same
 * hash.
 */
export const buildAgentDescriptorTable = ({ root = REPOSITORY_ROOT, baseTools, model, writeTool }) => {
  if (!Array.isArray(baseTools) || baseTools.length === 0) {
    fail(REGISTRY_UNREADABLE, "the base tool grant must be a non-empty array");
  }
  if (typeof writeTool !== "string" || writeTool.length === 0) {
    fail(REGISTRY_UNREADABLE, "the write tool must be a non-empty string");
  }
  if (typeof model !== "string" || model.length === 0) {
    fail(REGISTRY_UNREADABLE, "the agent model must be a non-empty string");
  }
  const options = { baseTools: [...baseTools], model, writeTool };
  const registry = parseRoleRegistry(readText(root, ROLE_REGISTRY_PATH, REGISTRY_UNREADABLE));
  const mapping = parseRoleMapping(readText(root, ROLE_MAPPING_PATH, MAPPING_UNREADABLE));
  const specById = new Map(registry.roles.map((row) => [row.role_id, row]));

  for (const roleId of Object.keys(mapping.roles)) {
    if (!specById.has(roleId)) {
      fail("ROLE_UNDECLARED", `${ROLE_MAPPING_PATH} maps undeclared role "${roleId}"`, {
        role_id: roleId,
      });
    }
  }

  const byName = new Map();
  const descriptors = [];
  for (const spec of registry.roles) {
    const mapped = mapping.roles[spec.role_id];
    if (mapped === undefined || !isPlainObject(mapped)) {
      fail("ROLE_UNMAPPED", `${ROLE_MAPPING_PATH} carries no row for "${spec.role_id}"`, {
        role_id: spec.role_id,
      });
    }
    selectDeclared(AGENT_SURFACES, mapped.surface, `${spec.role_id} surface`, "SURFACE_UNDECLARED");
    selectDeclared(ISOLATION_MODES, mapped.isolation, `${spec.role_id} isolation`, "ISOLATION_UNDECLARED");
    if (mapped.result_schema !== spec.output_schema_ref) {
      fail("MAPPING_DRIFT", `the Claude Code mapping for "${spec.role_id}" disagrees with the registry`, {
        expected: spec.output_schema_ref,
        mapped: mapped.result_schema,
        role_id: spec.role_id,
      });
    }
    if (mapped.isolation !== isolationFor(spec)) {
      fail("ISOLATION_DRIFT", `the isolation of "${spec.role_id}" disagrees with its write scope`, {
        expected: isolationFor(spec),
        mapped: mapped.isolation,
        role_id: spec.role_id,
        write_scope: [...spec.write_scope],
      });
    }
    const descriptor = descriptorFor(spec, mapped, options);
    if (byName.has(descriptor.name)) {
      fail("AGENT_NAME_COLLISION", `two roles resolve to "${descriptor.name}"`, {
        name: descriptor.name,
        role_ids: [byName.get(descriptor.name), spec.role_id],
      });
    }
    byName.set(descriptor.name, spec.role_id);
    descriptors.push(descriptor);
  }

  descriptors.sort((left, right) => (left.role_id < right.role_id ? -1 : 1));
  return deepFreeze(descriptors);
};

/** The descriptor for one role, or a refusal naming the role the registry lacks. */
export const describeAgent = (table, roleId) => {
  const descriptor = table.find((row) => row.role_id === roleId);
  if (descriptor === undefined) {
    fail("ROLE_UNDECLARED", `${ROLE_REGISTRY_PATH} declares no role "${String(roleId)}"`, {
      role_id: roleId,
    });
  }
  return descriptor;
};

/** The canonical bytes of the table, and the hash re-derived from exactly them. */
export const canonicalAgentTable = (table) => canonicalizeHookJson(table.map((row) => ({ ...row })));

export const agentTableHash = (table) => sha256HookJson(table.map((row) => ({ ...row })));
