// What the Claude Code adapter is allowed to say, and where every word of it
// comes from.
//
// This module declares no scientific vocabulary of its own.  The host name
// belongs to the sealed hook gateway's host list; the role vocabulary belongs to
// `manifests/role_registry.yaml`; the concrete tool grant, model and worktree
// isolation modes belong to `adapters/claude-code/claude-binding.json` and
// `adapters/claude-code/role_mapping.yaml`, which are read, never restated here.
// What lives here is the finding set, the typed error, the paths the adapter
// reads, and the small readers that keep an unreadable input from passing as an
// absent one.
//
// The one string the adapter must name to bind itself — its host — is written in
// `adapters/claude-code/claude-binding.json`, not in code, and is admitted only
// if the gateway's own host list contains it.  `selectDeclared` is that
// admission.

import { createHash } from "node:crypto";
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

/** Repository root, resolved from this file rather than the process cwd. */
export const REPOSITORY_ROOT = fileURLToPath(new URL("../../", import.meta.url));

export const ADAPTER_ROOT = "adapters/claude-code";
export const BINDING_DECLARATION_PATH = `${ADAPTER_ROOT}/claude-binding.json`;
export const ROLE_MAPPING_PATH = `${ADAPTER_ROOT}/role_mapping.yaml`;
export const ROLE_REGISTRY_PATH = "manifests/role_registry.yaml";

/**
 * The adapter's own binding vocabulary, taken from `adapters/claude-code/README.md`:
 * "write-capable roles require isolated worktrees and disjoint write scopes."
 * A role whose custom-agent file is not yet generated does not refuse the
 * binding: it is a report.  BOUND means every declared role ships an agent file
 * that matches its RoleSpec; DEGRADED means the binding is sound but some agent
 * files are not generated at this revision, and those roles are named rather
 * than implied.
 */
export const BINDING_STATUS = Object.freeze({ BOUND: "BOUND", DEGRADED: "DEGRADED" });

/** Every way this adapter refuses or reports, and why that finding exists. */
export const FINDING_CODES = Object.freeze({
  AGENT_DESCRIPTION_DRIFT:
    "a shipped custom-agent file declares a description other than the mission its RoleSpec declares, so the agent would present a role summary the registry does not authorise",
  AGENT_FILE_MISSING:
    "the registry declares a role whose custom-agent file is not generated at this revision, so that RoleSpec has no host agent yet; the gap is published, not implied",
  AGENT_FILE_UNDECLARED:
    "an agent file ships whose name maps to no role the registry declares, and the adapter may not present an agent for a role that does not exist",
  AGENT_FRONTMATTER_UNREADABLE:
    "a shipped custom-agent file is not the exact frontmatter record this adapter requires, and an unreadable agent file must never pass as an absent one",
  AGENT_MODEL_DRIFT:
    "a shipped custom-agent file declares a model other than the one the binding declaration declares, so two equal role compilations could resolve a different model",
  AGENT_NAME_COLLISION:
    "two roles resolved to the same custom-agent name, so a delegation could not name exactly one bounded role and its scopes",
  AGENT_NAME_DRIFT:
    "a shipped custom-agent file declares a name other than the claude_agent_name its RoleSpec declares, so the agent the host loads is not the role the registry names",
  AGENT_TOOLS_DRIFT:
    "a shipped custom-agent file declares a tool grant other than the one derived from its RoleSpec write scope, so the agent could hold tools the role does not authorise",
  DECLARATION_NONCANONICAL:
    "the adapter binding declaration is not in canonical form (exactly the declared fields, arrays unique), so two equal bindings could hash differently",
  HOST_UNDECLARED:
    "the declared adapter host matches no entry the hook gateway declares, so the adapter would bind roles to a host the kernel does not know",
  ISOLATION_DRIFT:
    "the role mapping declares a worktree-isolation mode that disagrees with the role's write scope, so a write-capable role could run unisolated or a read-only role could claim a worktree",
  ISOLATION_UNDECLARED:
    "the role mapping names a worktree-isolation mode this adapter does not declare, and an adapter may not invent an isolation vocabulary",
  MAPPING_DRIFT:
    "the Claude Code role mapping disagrees with the role registry about a role's output schema reference",
  MAPPING_UNREADABLE:
    "the Claude Code role mapping could not be read as the bounded YAML subset this adapter accepts, and a partly read mapping is not evidence of any binding",
  PARALLEL_REQUEST_UNREADABLE:
    "a parallel-write request is not the exact minimal record this adapter accepts, so it cannot be planned without inventing the fields it lacks",
  REGISTRY_UNREADABLE:
    "a role declaration source could not be read as the bounded YAML subset this adapter accepts, and a partly read source is not evidence of any role",
  ROLE_UNDECLARED:
    "a custom agent was requested for a role the role registry does not declare, and the adapter may not invent a role, its scopes or its schema",
  ROLE_UNMAPPED:
    "the role registry declares a role the Claude Code role mapping does not carry, so part of the canonical role vocabulary would have no host binding",
  SURFACE_UNDECLARED:
    "the role mapping names a Claude Code surface this adapter does not declare, and an adapter may not invent a host surface for a role",
  WORKTREE_ROLE_NOT_WRITABLE:
    "a parallel-write request names a role with no write scope, so the adapter would open an isolated worktree for a role that writes nothing",
  WORKTREE_SCOPE_OVERLAP:
    "two roles in one parallel-write set resolve to overlapping write scopes, so their isolated worktrees could not merge without a conflict the adapter must refuse first",
});

export class ClaudeAdapterError extends Error {
  constructor(code, message, context = {}) {
    super(message);
    this.name = "ClaudeAdapterError";
    this.code = code;
    this.context = context;
  }
}

export const fail = (code, message, context = {}) => {
  throw new ClaudeAdapterError(code, message, context);
};

export const sha256 = (bytes) => `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

export const isPlainObject = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);

export const pathExists = (root, relative) => {
  try {
    return statSync(join(root, relative)).isFile();
  } catch {
    return false;
  }
};

export const readBytes = (root, relative, code) => {
  try {
    return readFileSync(join(root, relative));
  } catch (error) {
    fail(code, `cannot read ${relative}: ${error.message}`, { path: relative });
    return Buffer.alloc(0);
  }
};

export const readText = (root, relative, code) => readBytes(root, relative, code).toString("utf8");

export const readJson = (root, relative, code) => {
  const text = readText(root, relative, code);
  try {
    return JSON.parse(text);
  } catch (error) {
    fail(code, `${relative} is not JSON: ${error.message}`, { path: relative });
    return undefined;
  }
};

/** Require an object that declares exactly `fields`, no more and no fewer. */
export const requireFields = (value, fields, label, code) => {
  if (!isPlainObject(value)) fail(code, `${label} must be an object`, { label });
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail(code, `${label} must declare exactly ${expected.join(", ")}`, { actual, expected, label });
  }
  return value;
};

/** An array of unique strings, kept in the order the source declares. */
export const requireStringArray = (value, label, code) => {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string" || entry.length === 0)) {
    fail(code, `${label} must be an array of non-empty strings`, { label });
  }
  if (new Set(value).size !== value.length) {
    fail(code, `${label} must not repeat an entry`, { label, value });
  }
  return Object.freeze([...value]);
};

/** An array of unique strings that must also be sorted, so equal sets hash equally. */
export const requireCanonicalStrings = (value, label, code) => {
  const array = requireStringArray(value, label, code);
  const sorted = [...array].sort();
  if (array.some((entry, index) => entry !== sorted[index])) {
    fail(code, `${label} must be sorted`, { label, value: [...array] });
  }
  return array;
};

/**
 * Admit one declared value by finding it in a list the kernel declares.
 *
 * The adapter holds the *name of the declaration*, never a copy of the canonical
 * vocabulary: the value is selected from `declared` by equality, and a candidate
 * that matches nothing is a refusal rather than a silent default.
 */
export const selectDeclared = (declared, candidate, label, code) => {
  const matches = declared.filter((entry) => entry === candidate);
  if (matches.length !== 1) {
    fail(code, `${label} "${String(candidate)}" is not one declared value`, {
      candidate,
      declared: [...declared],
      label,
    });
  }
  return matches[0];
};

export const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of Reflect.ownKeys(value)) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (descriptor !== undefined && Object.hasOwn(descriptor, "value")) deepFreeze(descriptor.value);
  }
  return Object.freeze(value);
};
