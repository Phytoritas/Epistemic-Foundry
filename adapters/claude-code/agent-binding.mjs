// Read-and-verify: do the shipped custom-agent files actually bind to the
// canonical roles, and are their writers isolated?
//
// Nothing here rewrites an agent file.  `adapters/claude-code` is read as it
// ships — its binding declaration, its role mapping, and the custom-agent files
// it has generated so far — and every claim each file makes is checked against a
// source entitled to make it: the hook gateway declares the host, the role
// registry declares the roles and their scopes, and the binding declaration
// declares the concrete tool grant and model a generated file must carry.
//
// Two kinds of outcome are kept apart on purpose.  An agent file that
// contradicts its RoleSpec — a wrong name, description, tool grant or model — is
// a refusal: the binding is wrong and must not be reported as anything else.  A
// declared role whose agent file is not generated at this revision is a finding,
// and the binding is DEGRADED — the role is real, and the part of the surface
// that does not ship yet is named rather than implied.

import { readdirSync } from "node:fs";
import { posix } from "node:path";

import { HOOK_HOSTS, sha256HookJson } from "../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  ADAPTER_ROOT,
  BINDING_DECLARATION_PATH,
  BINDING_STATUS,
  deepFreeze,
  fail,
  isPlainObject,
  pathExists,
  readBytes,
  readJson,
  readText,
  REPOSITORY_ROOT,
  requireCanonicalStrings,
  requireFields,
  requireStringArray,
  ROLE_MAPPING_PATH,
  ROLE_REGISTRY_PATH,
  selectDeclared,
  sha256,
} from "./claude-declarations.mjs";
import { agentTableHash, buildAgentDescriptorTable } from "./role-adapter.mjs";
import { deriveWorktreePlan } from "./worktree-plan.mjs";

/** The fields `adapters/claude-code/claude-binding.json` must declare, exactly. */
export const DECLARATION_FIELDS = Object.freeze([
  "adapter_id",
  "adapter_version",
  "agent_file_suffix",
  "base_tools",
  "declared_host",
  "frontmatter_fields",
  "model",
  "write_tool",
]);

const readDeclaration = (root) => {
  const declaration = requireFields(
    readJson(root, BINDING_DECLARATION_PATH, "DECLARATION_NONCANONICAL"),
    DECLARATION_FIELDS,
    "binding declaration",
    "DECLARATION_NONCANONICAL",
  );
  requireStringArray(declaration.base_tools, "declaration.base_tools", "DECLARATION_NONCANONICAL");
  requireCanonicalStrings(
    declaration.frontmatter_fields,
    "declaration.frontmatter_fields",
    "DECLARATION_NONCANONICAL",
  );
  for (const key of ["adapter_id", "adapter_version", "agent_file_suffix", "declared_host", "model", "write_tool"]) {
    if (typeof declaration[key] !== "string" || declaration[key].length === 0) {
      fail("DECLARATION_NONCANONICAL", `declaration.${key} must be a non-empty string`, { key });
    }
  }
  if (!declaration.agent_file_suffix.startsWith(".")) {
    fail("DECLARATION_NONCANONICAL", "declaration.agent_file_suffix must start with a dot", {
      agent_file_suffix: declaration.agent_file_suffix,
    });
  }
  if (declaration.base_tools.includes(declaration.write_tool)) {
    fail("DECLARATION_NONCANONICAL", "declaration.write_tool must not already be a base tool", {
      base_tools: [...declaration.base_tools],
      write_tool: declaration.write_tool,
    });
  }
  return deepFreeze(declaration);
};

/** The four-key frontmatter block a generated custom-agent file must carry. */
export const parseAgentFrontmatter = (text, declaration, relative) => {
  const normalized = text.replace(/\r\n/gu, "\n");
  const match = /^---\n([\s\S]*?)\n---\n/u.exec(normalized);
  if (match === null) {
    fail("AGENT_FRONTMATTER_UNREADABLE", `${relative} has no frontmatter block`, { path: relative });
  }
  const frontmatter = {};
  for (const line of match[1].split("\n")) {
    if (line.trim().length === 0) continue;
    const field = /^([a-z_]+): (.+)$/u.exec(line);
    if (field === null) {
      fail("AGENT_FRONTMATTER_UNREADABLE", `${relative} holds an unreadable frontmatter line`, {
        line: line.trim(),
        path: relative,
      });
    }
    const [, key, rawValue] = field;
    if (Object.hasOwn(frontmatter, key)) {
      fail("AGENT_FRONTMATTER_UNREADABLE", `${relative} declares "${key}" twice`, { key, path: relative });
    }
    if (key === "description") {
      try {
        frontmatter[key] = JSON.parse(rawValue);
      } catch {
        fail("AGENT_FRONTMATTER_UNREADABLE", `${relative} description is not a quoted string`, {
          path: relative,
        });
      }
      if (typeof frontmatter[key] !== "string") {
        fail("AGENT_FRONTMATTER_UNREADABLE", `${relative} description is not a string`, { path: relative });
      }
    } else if (key === "tools") {
      frontmatter[key] = rawValue.split(", ");
    } else {
      frontmatter[key] = rawValue;
    }
  }
  requireFields(frontmatter, declaration.frontmatter_fields, `${relative} frontmatter`, "AGENT_FRONTMATTER_UNREADABLE");
  return frontmatter;
};

const AGENT_FILE_PATTERN = /^ef-[a-z0-9-]+\.md$/u;

/**
 * Read the shipped custom-agent files and check each against its RoleSpec.
 *
 * A stray agent file that maps to no declared role is refused; a shipped file
 * that contradicts its RoleSpec is refused; a declared role whose file is not
 * generated yet is a finding.  The refusals keep an invented agent out; the
 * findings keep the generation gap honest.
 */
const readShippedAgents = (root, declaration, table) => {
  const suffix = declaration.agent_file_suffix;
  const expectedByFile = new Map(table.map((row) => [`${row.name}${suffix}`, row.role_id]));

  const present = new Set();
  for (const entry of readdirSync(posix.join(root, ADAPTER_ROOT)).sort()) {
    if (!entry.endsWith(suffix) || !AGENT_FILE_PATTERN.test(entry)) continue;
    if (!expectedByFile.has(entry)) {
      fail("AGENT_FILE_UNDECLARED", `agent file ${entry} maps to no declared role`, { file: entry });
    }
    present.add(entry);
  }

  const findings = [];
  const presentRoleIds = [];
  const missingRoleIds = [];
  for (const descriptor of table) {
    const file = `${descriptor.name}${suffix}`;
    const relative = `${ADAPTER_ROOT}/${file}`;
    if (!present.has(file) || !pathExists(root, relative)) {
      findings.push({ code: "AGENT_FILE_MISSING", name: descriptor.name, path: relative, role_id: descriptor.role_id });
      missingRoleIds.push(descriptor.role_id);
      continue;
    }
    const frontmatter = parseAgentFrontmatter(
      readText(root, relative, "AGENT_FRONTMATTER_UNREADABLE"),
      declaration,
      relative,
    );
    if (frontmatter.name !== descriptor.name) {
      fail("AGENT_NAME_DRIFT", `${relative} declares a name its RoleSpec does not`, {
        declared: frontmatter.name,
        expected: descriptor.name,
        role_id: descriptor.role_id,
      });
    }
    if (frontmatter.description !== descriptor.description) {
      fail("AGENT_DESCRIPTION_DRIFT", `${relative} declares a description its RoleSpec does not`, {
        role_id: descriptor.role_id,
      });
    }
    if (
      frontmatter.tools.length !== descriptor.tools.length ||
      frontmatter.tools.some((tool, index) => tool !== descriptor.tools[index])
    ) {
      fail("AGENT_TOOLS_DRIFT", `${relative} declares a tool grant its write scope does not earn`, {
        declared: [...frontmatter.tools],
        expected: [...descriptor.tools],
        role_id: descriptor.role_id,
      });
    }
    if (frontmatter.model !== descriptor.model) {
      fail("AGENT_MODEL_DRIFT", `${relative} declares a model the binding does not`, {
        declared: frontmatter.model,
        expected: descriptor.model,
        role_id: descriptor.role_id,
      });
    }
    presentRoleIds.push(descriptor.role_id);
  }

  findings.sort((left, right) => (`${left.code} ${left.path}` < `${right.code} ${right.path}` ? -1 : 1));
  return {
    findings,
    missingRoleIds: missingRoleIds.slice().sort(),
    presentRoleIds: presentRoleIds.slice().sort(),
  };
};

/** Read, cross-check and freeze the whole Claude Code role binding. */
export const loadClaudeBinding = ({ root = REPOSITORY_ROOT } = {}) => {
  const declaration = readDeclaration(root);
  const adapterHost = selectDeclared(HOOK_HOSTS, declaration.declared_host, "declaration.declared_host", "HOST_UNDECLARED");
  const agentTable = buildAgentDescriptorTable({
    baseTools: declaration.base_tools,
    model: declaration.model,
    root,
    writeTool: declaration.write_tool,
  });
  const worktreePlan = deriveWorktreePlan(agentTable);
  const agents = readShippedAgents(root, declaration, agentTable);

  return deepFreeze({
    adapterHost,
    agentTable,
    declaration,
    findings: agents.findings,
    missingRoleIds: agents.missingRoleIds,
    presentRoleIds: agents.presentRoleIds,
    root,
    status: agents.findings.length === 0 ? BINDING_STATUS.BOUND : BINDING_STATUS.DEGRADED,
    worktreePlan,
  });
};

/** The files whose bytes decide the binding, each named with its digest. */
export const BINDING_SOURCE_PATHS = Object.freeze(
  [BINDING_DECLARATION_PATH, ROLE_MAPPING_PATH, ROLE_REGISTRY_PATH].sort(),
);

/**
 * An immutable receipt for the binding: what was read, which roles have agent
 * files, which do not, how the writers are isolated, and the hash of exactly
 * those fields.  No clock and no randomness, so the same repository always
 * produces the same receipt and a changed input always produces a different one.
 */
export const claudeBindingReceipt = (binding) => {
  const suffix = binding.declaration.agent_file_suffix;
  const sources = [
    ...BINDING_SOURCE_PATHS.map((path) => ({
      path,
      sha256: sha256(readBytes(binding.root, path, "DECLARATION_NONCANONICAL")),
    })),
    ...binding.presentRoleIds.map((roleId) => {
      const descriptor = binding.agentTable.find((row) => row.role_id === roleId);
      const path = `${ADAPTER_ROOT}/${descriptor.name}${suffix}`;
      return { path, sha256: sha256(readBytes(binding.root, path, "AGENT_FRONTMATTER_UNREADABLE")) };
    }),
  ].sort((left, right) => (left.path < right.path ? -1 : 1));

  const preimage = {
    adapter_host: binding.adapterHost,
    adapter_id: binding.declaration.adapter_id,
    adapter_version: binding.declaration.adapter_version,
    agent_count: binding.agentTable.length,
    agent_table_hash: agentTableHash(binding.agentTable),
    binding_status: binding.status,
    findings: binding.findings.map((row) => ({
      code: row.code,
      name: row.name,
      path: row.path,
      role_id: row.role_id,
    })),
    missing_agents: [...binding.missingRoleIds],
    present_agents: [...binding.presentRoleIds],
    read_only_agents: binding.agentTable
      .filter((row) => row.isolation !== "worktree")
      .map((row) => row.role_id)
      .sort(),
    sources,
    worktrees: binding.worktreePlan.map((row) => ({
      isolation: row.isolation,
      role_id: row.role_id,
      write_scope: [...row.write_scope],
    })),
  };
  const receiptHash = sha256HookJson(preimage);
  return deepFreeze({
    receipt_id: `EFX02-CLAUDE-${receiptHash.slice("sha256:".length, "sha256:".length + 16)}`,
    ...preimage,
    receipt_hash: receiptHash,
  });
};
