// Read-and-verify: do the shipped custom-agent files actually bind to the
// canonical roles, and are their writers isolated?
//
// Nothing here rewrites an agent file.  The adapter declaration and role mapping
// live under `adapters/claude-code`; the host-visible custom agents are read from
// the declared `.claude/agents` surface.  The host metadata this binding
// publishes is checked against a source entitled to make it: the hook gateway
// declares the host, the role
// registry declares the roles and their scopes, and the binding declaration
// declares the concrete tool grant and model a generated file must carry.
//
// Two kinds of outcome are kept apart on purpose.  An agent file that
// contradicts its RoleSpec-derived host metadata — a wrong name, description,
// tool grant or model — is
// a refusal: the binding is wrong and must not be reported as anything else.  A
// declared role whose agent file is not generated at this revision is a finding,
// and the binding is DEGRADED — the role is real, and the part of the surface
// that does not ship yet is named rather than implied.

import {
  closeSync,
  constants as fsConstants,
  fstatSync,
  openSync,
  readFileSync,
  readdirSync,
  realpathSync,
  statSync,
} from "node:fs";
import { isAbsolute, join, posix, relative, sep, win32 } from "node:path";

import { HOOK_HOSTS, sha256HookJson } from "../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  BINDING_DECLARATION_PATH,
  BINDING_STATUS,
  ClaudeAdapterError,
  deepFreeze,
  fail,
  isPlainObject,
  readBytes,
  readJson,
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
  "agent_root",
  "base_tools",
  "declared_host",
  "frontmatter_fields",
  "model",
  "optional_frontmatter",
  "write_tool",
]);

const requireRepositoryRelativePath = (candidate, label, code) => {
  if (
    typeof candidate !== "string" ||
    candidate.length === 0 ||
    candidate.includes("\\") ||
    candidate.includes("\0") ||
    posix.isAbsolute(candidate) ||
    win32.isAbsolute(candidate) ||
    /^[A-Za-z]:/u.test(candidate)
  ) {
    fail(code, `${label} must be a repository-relative POSIX path`, { path: candidate });
  }
  const normalized = posix.normalize(candidate);
  if (
    normalized !== candidate ||
    normalized === "." ||
    normalized === ".." ||
    normalized.startsWith("../")
  ) {
    fail(code, `${label} escapes or is not canonical within the repository`, {
      normalized,
      path: candidate,
    });
  }
  return normalized;
};

const resolveAgentRoot = (root, agentRoot, code) => {
  const canonical = requireRepositoryRelativePath(agentRoot, "declaration.agent_root", code);
  let repositoryRoot;
  let actualRoot;
  let rootIsDirectory;
  try {
    repositoryRoot = realpathSync(root);
    actualRoot = realpathSync(join(root, canonical));
    rootIsDirectory = statSync(actualRoot).isDirectory();
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    fail(code, `declared agent root cannot be resolved: ${error.message}`, { path: agentRoot });
  }
  const fromRepository = relative(repositoryRoot, actualRoot);
  if (
    fromRepository === "" ||
    fromRepository === ".." ||
    fromRepository.startsWith(`..${sep}`) ||
    isAbsolute(fromRepository) ||
    !rootIsDirectory
  ) {
    fail(code, "declared agent root does not resolve to a repository directory", {
      path: agentRoot,
    });
  }
  return actualRoot;
};

const sameFileIdentity = (left, right) =>
  left.dev === right.dev &&
  left.ino === right.ino &&
  left.size === right.size &&
  left.mtimeNs === right.mtimeNs &&
  left.ctimeNs === right.ctimeNs;

const captureAgentFile = (root, agentRoot, file, code) => {
  const actualRoot = resolveAgentRoot(root, agentRoot, code);
  if (actualRoot === null) return null;
  let actualPathBefore;
  try {
    actualPathBefore = realpathSync(join(actualRoot, file));
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    fail(code, `agent file cannot be resolved: ${error.message}`, { file });
  }
  const fromAgentRoot = relative(actualRoot, actualPathBefore);
  if (
    fromAgentRoot === "" ||
    fromAgentRoot === ".." ||
    fromAgentRoot.startsWith(`..${sep}`) ||
    isAbsolute(fromAgentRoot)
  ) {
    fail(code, "agent file does not resolve inside the declared agent root", { file });
  }
  let descriptor;
  try {
    descriptor = openSync(actualPathBefore, fsConstants.O_RDONLY);
  } catch (error) {
    fail(code, `agent file ${file} cannot be opened: ${error.message}`, { file });
  }
  let capture = null;
  let captureError = null;
  try {
    const before = fstatSync(descriptor, { bigint: true });
    if (!before.isFile()) {
      fail(code, "agent path is not a regular file", { file });
    }
    const bytes = readFileSync(descriptor);
    const after = fstatSync(descriptor, { bigint: true });
    let actualPathAfter;
    let pathIdentity;
    try {
      actualPathAfter = realpathSync(join(actualRoot, file));
      pathIdentity = statSync(actualPathAfter, { bigint: true });
    } catch (error) {
      fail(code, `agent file changed while being captured: ${error.message}`, { file });
    }
    if (
      actualPathAfter !== actualPathBefore ||
      !sameFileIdentity(before, after) ||
      before.dev !== pathIdentity.dev ||
      before.ino !== pathIdentity.ino
    ) {
      fail(code, "agent file changed while being captured", { file });
    }
    capture = { bytes, sha256: sha256(bytes) };
  } catch (error) {
    captureError = error;
  }
  try {
    closeSync(descriptor);
  } catch (error) {
    if (captureError === null) captureError = error;
  }
  if (captureError !== null) {
    if (captureError instanceof ClaudeAdapterError) throw captureError;
    fail(code, `agent file capture failed: ${captureError.message}`, { file });
  }
  return capture;
};

const listAgentEntries = (actualRoot, code) => {
  if (actualRoot === null) return [];
  try {
    return readdirSync(actualRoot).sort();
  } catch (error) {
    fail(code, `declared agent root cannot be listed: ${error.message}`);
  }
};

const captureDeclaringSources = (root) =>
  BINDING_SOURCE_PATHS.map((path) => ({
    path,
    sha256: sha256(readBytes(root, path, "DECLARATION_NONCANONICAL")),
  })).sort((left, right) => (left.path < right.path ? -1 : 1));

const sameSources = (left, right) =>
  left.length === right.length &&
  left.every(
    (source, index) =>
      source.path === right[index].path && source.sha256 === right[index].sha256,
  );

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
  for (const key of ["adapter_id", "adapter_version", "agent_file_suffix", "agent_root", "declared_host", "model", "write_tool"]) {
    if (typeof declaration[key] !== "string" || declaration[key].length === 0) {
      fail("DECLARATION_NONCANONICAL", `declaration.${key} must be a non-empty string`, { key });
    }
  }
  requireRepositoryRelativePath(
    declaration.agent_root,
    "declaration.agent_root",
    "DECLARATION_NONCANONICAL",
  );
  if (!isPlainObject(declaration.optional_frontmatter)) {
    fail("DECLARATION_NONCANONICAL", "declaration.optional_frontmatter must be an object");
  }
  const optionalFields = Object.keys(declaration.optional_frontmatter);
  if (optionalFields.some((key, index) => key !== [...optionalFields].sort()[index])) {
    fail("DECLARATION_NONCANONICAL", "declaration.optional_frontmatter must be key-sorted");
  }
  for (const key of optionalFields) {
    if (
      !/^[A-Za-z][A-Za-z0-9_]*$/u.test(key) ||
      typeof declaration.optional_frontmatter[key] !== "string" ||
      declaration.optional_frontmatter[key].length === 0 ||
      declaration.frontmatter_fields.includes(key)
    ) {
      fail("DECLARATION_NONCANONICAL", "declaration.optional_frontmatter is invalid", { key });
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
    const field = /^([A-Za-z][A-Za-z0-9_]*): (.+)$/u.exec(line);
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
  const optionalFields = Object.keys(declaration.optional_frontmatter);
  const actualFields = Object.keys(frontmatter);
  const missing = declaration.frontmatter_fields.filter((key) => !actualFields.includes(key));
  const unknown = actualFields.filter(
    (key) => !declaration.frontmatter_fields.includes(key) && !optionalFields.includes(key),
  );
  if (missing.length > 0 || unknown.length > 0) {
    fail("AGENT_FRONTMATTER_UNREADABLE", `${relative} frontmatter fields are not canonical`, {
      missing,
      path: relative,
      unknown,
    });
  }
  for (const key of optionalFields) {
    if (
      Object.hasOwn(frontmatter, key) &&
      frontmatter[key] !== declaration.optional_frontmatter[key]
    ) {
      fail("AGENT_FRONTMATTER_UNREADABLE", `${relative} optional frontmatter is not declared`, {
        declared: frontmatter[key],
        expected: declaration.optional_frontmatter[key],
        key,
        path: relative,
      });
    }
  }
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
  const actualAgentRoot = resolveAgentRoot(
    root,
    declaration.agent_root,
    "DECLARATION_NONCANONICAL",
  );
  for (const entry of listAgentEntries(actualAgentRoot, "DECLARATION_NONCANONICAL")) {
    if (!entry.endsWith(suffix) || !AGENT_FILE_PATTERN.test(entry)) continue;
    if (!expectedByFile.has(entry)) {
      fail("AGENT_FILE_UNDECLARED", `agent file ${entry} maps to no declared role`, {
        file: entry,
        root: declaration.agent_root,
      });
    }
    present.add(entry);
  }

  const findings = [];
  const sources = [];
  const presentRoleIds = [];
  const missingRoleIds = [];
  for (const descriptor of table) {
    const file = `${descriptor.name}${suffix}`;
    const relative = `${declaration.agent_root}/${file}`;
    const captured = present.has(file)
      ? captureAgentFile(root, declaration.agent_root, file, "AGENT_FRONTMATTER_UNREADABLE")
      : null;
    if (captured === null) {
      findings.push({ code: "AGENT_FILE_MISSING", name: descriptor.name, path: relative, role_id: descriptor.role_id });
      missingRoleIds.push(descriptor.role_id);
      continue;
    }
    const frontmatter = parseAgentFrontmatter(
      captured.bytes.toString("utf8"),
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
    sources.push({ path: relative, sha256: captured.sha256 });
  }

  const finalEntries = new Set(
    listAgentEntries(actualAgentRoot, "AGENT_FRONTMATTER_UNREADABLE").filter(
      (entry) => entry.endsWith(suffix) && AGENT_FILE_PATTERN.test(entry),
    ),
  );
  if (
    present.size !== finalEntries.size ||
    [...present].some((entry) => !finalEntries.has(entry))
  ) {
    fail("AGENT_FRONTMATTER_UNREADABLE", "live agent set changed while being captured", {
      root: declaration.agent_root,
    });
  }

  findings.sort((left, right) => (`${left.code} ${left.path}` < `${right.code} ${right.path}` ? -1 : 1));
  return {
    findings,
    missingRoleIds: missingRoleIds.slice().sort(),
    presentRoleIds: presentRoleIds.slice().sort(),
    sources: sources.slice().sort((left, right) => (left.path < right.path ? -1 : 1)),
  };
};

/** Read, cross-check and freeze the whole Claude Code role binding. */
export const loadClaudeBinding = ({ root = REPOSITORY_ROOT } = {}) => {
  const declaringSourcesBefore = captureDeclaringSources(root);
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
  const declaringSourcesAfter = captureDeclaringSources(root);
  if (!sameSources(declaringSourcesBefore, declaringSourcesAfter)) {
    fail("DECLARATION_NONCANONICAL", "binding sources changed while being read");
  }

  return deepFreeze({
    adapterHost,
    agentRoot: declaration.agent_root,
    agentTable,
    declaration,
    declaringSources: declaringSourcesAfter,
    findings: agents.findings,
    missingRoleIds: agents.missingRoleIds,
    presentRoleIds: agents.presentRoleIds,
    agentSources: agents.sources,
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
  const current = loadClaudeBinding({ root: binding.root });
  const sources = [
    ...current.declaringSources.map((source) => ({ ...source })),
    ...current.agentSources.map((source) => ({ ...source })),
  ].sort((left, right) => (left.path < right.path ? -1 : 1));

  const preimage = {
    adapter_host: current.adapterHost,
    adapter_id: current.declaration.adapter_id,
    adapter_version: current.declaration.adapter_version,
    agent_root: current.agentRoot,
    agent_count: current.agentTable.length,
    agent_table_hash: agentTableHash(current.agentTable),
    binding_status: current.status,
    findings: current.findings.map((row) => ({
      code: row.code,
      name: row.name,
      path: row.path,
      role_id: row.role_id,
    })),
    missing_agents: [...current.missingRoleIds],
    present_agents: [...current.presentRoleIds],
    read_only_agents: current.agentTable
      .filter((row) => row.isolation !== "worktree")
      .map((row) => row.role_id)
      .sort(),
    sources,
    worktrees: current.worktreePlan.map((row) => ({
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
