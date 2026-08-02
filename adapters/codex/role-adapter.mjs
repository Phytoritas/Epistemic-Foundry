// The Codex subagent adapter: canonical role -> host descriptor, and nothing else.
//
// The role vocabulary is `manifests/role_registry.yaml` (authority 6).  The
// host-side compilation choice — which built-in Codex agent type carries a
// role, and which schema its result is checked against — is already declared by
// `adapters/codex/role_mapping.yaml`.  This module binds the two and refuses
// when they disagree, so a mapping cannot quietly widen, narrow or rename the
// role set.
//
// The descriptor is metadata.  It names a role, its bounded scopes and its
// output schema; it does not launch a subagent, hold a lease, or grant an ACL.
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
} from "./codex-declarations.mjs";

const UNREADABLE = "REGISTRY_UNREADABLE";

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

/** The fields `adapters/codex/role_mapping.yaml` declares for every role. */
export const ROLE_MAPPING_FIELDS = Object.freeze([
  "agent_type",
  "prompt_source",
  "result_schema",
]);

/** The descriptor fields this adapter publishes for one Codex subagent. */
export const DESCRIPTOR_FIELDS = Object.freeze([
  "agent_type",
  "default_timeout_seconds",
  "evidence_acl",
  "forbidden",
  "independent_review_required",
  "mission",
  "model_tier",
  "name",
  "output_schema_ref",
  "prompt_source",
  "role_id",
  "tool_acl",
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
      fail(UNREADABLE, `${label} holds an unsupported top-level key "${key}"`, { key, label });
    }

    const start = /^- role_id: (.+)$/u.exec(line);
    if (start !== null) {
      if (!inRoles) fail(UNREADABLE, `${label} declares a role outside the roles block`, { label });
      role = { role_id: decodeScalar(start[1]) };
      roles.push(role);
      listKey = null;
      listAnchor = null;
      scalarKey = "role_id";
      continue;
    }

    const field = /^ {2}([a-z_]+):(?: (.+))?$/u.exec(line);
    if (field !== null) {
      if (role === null) fail(UNREADABLE, `${label} declares a field outside a role`, { label });
      const [, key, value] = field;
      listKey = null;
      listAnchor = null;
      scalarKey = null;
      if (Object.hasOwn(role, key)) {
        fail(UNREADABLE, `${label} declares "${key}" twice for ${role.role_id}`, { key, label });
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
          fail(UNREADABLE, `${label} aliases the undefined anchor "${alias[1]}"`, { label });
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
        fail(UNREADABLE, `${label} holds a sequence item under no key: ${line.trim()}`, { label });
      }
      role[listKey].push(decodeScalar(item[1]));
      if (listAnchor !== null) anchors.set(listAnchor, role[listKey]);
      continue;
    }

    const continuation = /^ {4}(\S.*)$/u.exec(line);
    if (continuation !== null) {
      if (role === null || scalarKey === null || typeof role[scalarKey] !== "string") {
        fail(UNREADABLE, `${label} continues a scalar that is not open: ${line.trim()}`, { label });
      }
      role[scalarKey] = `${role[scalarKey]} ${continuation[1]}`;
      continue;
    }

    fail(UNREADABLE, `${label} holds an unreadable line: ${line.trim()}`, {
      label,
      line: line.trim(),
    });
  }

  if (typeof version !== "string") {
    fail(UNREADABLE, `${label} declares no version`, { label });
  }
  if (roles.length === 0) fail(UNREADABLE, `${label} declares no role`, { label });
  for (const entry of roles) {
    requireFields(entry, ROLE_REGISTRY_FIELDS, `${label}#${entry.role_id}`, UNREADABLE);
  }
  return deepFreeze({ roles, version });
};

/**
 * Read `adapters/codex/role_mapping.yaml` as role_id -> host compilation record.
 *
 * The same fail-closed discipline applies: the subset is exactly what that file
 * uses, and an unrecognised line refuses rather than being skipped.
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
      fail(UNREADABLE, `${label} holds an unsupported top-level key "${key}"`, { key, label });
    }

    const constraint = /^- (.+)$/u.exec(line);
    if (constraint !== null) {
      if (section !== "constraints") {
        fail(UNREADABLE, `${label} holds a constraint outside the constraints block`, { label });
      }
      constraints.push(decodeScalar(constraint[1]));
      continue;
    }

    const roleKey = /^ {2}([a-z0-9_]+):$/u.exec(line);
    if (roleKey !== null) {
      if (section !== "roles") {
        fail(UNREADABLE, `${label} holds a role outside the roles block`, { label });
      }
      if (Object.hasOwn(roles, roleKey[1])) {
        fail(UNREADABLE, `${label} declares role "${roleKey[1]}" twice`, { label });
      }
      role = {};
      roles[roleKey[1]] = role;
      continue;
    }

    const field = /^ {4}([a-z_]+): (.+)$/u.exec(line);
    if (field !== null) {
      if (role === null) fail(UNREADABLE, `${label} declares a field outside a role`, { label });
      role[field[1]] = decodeScalar(field[2]);
      continue;
    }

    fail(UNREADABLE, `${label} holds an unreadable line: ${line.trim()}`, {
      label,
      line: line.trim(),
    });
  }

  if (typeof version !== "string" || typeof strategy !== "string") {
    fail(UNREADABLE, `${label} declares no version or no strategy`, { label });
  }
  const ids = Object.keys(roles);
  if (ids.length === 0) fail(UNREADABLE, `${label} maps no role`, { label });
  for (const id of ids) {
    requireFields(roles[id], ROLE_MAPPING_FIELDS, `${label}#${id}`, UNREADABLE);
  }
  return deepFreeze({ constraints, roles, strategy, version });
};

/** The prompt source a mapping row must name for a role, derived from the role. */
export const promptSourceFor = (roleId) => `${ROLE_REGISTRY_PATH}#${roleId}`;

/** The Codex subagent name for a role, derived from the role id and one prefix. */
export const descriptorNameFor = (prefix, roleId) => `${prefix}${roleId.replaceAll("_", "-")}`;

const descriptorFor = (prefix, spec, mapped) =>
  deepFreeze({
    agent_type: mapped.agent_type,
    default_timeout_seconds: spec.default_timeout_seconds,
    evidence_acl: [...spec.evidence_acl],
    forbidden: [...spec.forbidden],
    independent_review_required: spec.independent_review_required,
    mission: spec.mission,
    model_tier: spec.model_tier,
    name: descriptorNameFor(prefix, spec.role_id),
    output_schema_ref: spec.output_schema_ref,
    prompt_source: mapped.prompt_source,
    role_id: spec.role_id,
    tool_acl: [...spec.tool_acl],
    write_scope: [...spec.write_scope],
  });

/**
 * Build the whole role_id -> Codex descriptor table.
 *
 * Deterministic and byte-stable: the table is sorted by role id, every field is
 * copied from a declaring source, and nothing here reads a clock, an
 * environment variable or a random number.  Rebuilding it from the same two
 * files yields the same bytes and therefore the same hash.
 */
export const buildRoleDescriptorTable = ({ root = REPOSITORY_ROOT, prefix }) => {
  if (typeof prefix !== "string" || prefix.length === 0) {
    fail(UNREADABLE, "the descriptor name prefix must be a non-empty string");
  }
  const registry = parseRoleRegistry(readText(root, ROLE_REGISTRY_PATH, UNREADABLE));
  const mapping = parseRoleMapping(readText(root, ROLE_MAPPING_PATH, UNREADABLE));
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
    const drift = [
      ["agent_type", mapped.agent_type, spec.codex_agent_type],
      ["prompt_source", mapped.prompt_source, promptSourceFor(spec.role_id)],
      ["result_schema", mapped.result_schema, spec.output_schema_ref],
    ].filter(([, mappedValue, expected]) => mappedValue !== expected);
    if (drift.length > 0) {
      fail("MAPPING_DRIFT", `the Codex mapping for "${spec.role_id}" disagrees with the registry`, {
        fields: drift.map(([field, mappedValue, expected]) => ({ expected, field, mappedValue })),
        role_id: spec.role_id,
      });
    }
    const descriptor = descriptorFor(prefix, spec, mapped);
    if (byName.has(descriptor.name)) {
      fail("DESCRIPTOR_NAME_COLLISION", `two roles resolve to "${descriptor.name}"`, {
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
export const describeRole = (table, roleId) => {
  const descriptor = table.find((row) => row.role_id === roleId);
  if (descriptor === undefined) {
    fail("ROLE_UNDECLARED", `${ROLE_REGISTRY_PATH} declares no role "${String(roleId)}"`, {
      role_id: roleId,
    });
  }
  return descriptor;
};

/** The canonical bytes of the table, and the hash re-derived from exactly them. */
export const canonicalRoleTable = (table) => canonicalizeHookJson(table.map((row) => ({ ...row })));

export const roleTableHash = (table) => sha256HookJson(table.map((row) => ({ ...row })));
