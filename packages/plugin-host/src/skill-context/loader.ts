import { lstat, readFile, realpath, stat } from "node:fs/promises";
import path from "node:path";

import {
  assertActivationBudget,
  assertReferenceFileBudget,
  metadataFitsHost,
  validateHostMetadataBudget,
} from "./budget.ts";
import { failSkillContext } from "./errors.ts";
import {
  canonicalizeJson,
  loadSkillInventory,
  serializeInitialMetadata,
  sha256Bytes,
  sha256Text,
} from "./inventory.ts";
import { assertReachability } from "./reachability.ts";
import { selectReferences } from "./selector.ts";
import type {
  HostMetadataBudget,
  MetadataProjectionResult,
  ReferenceInventoryEntry,
  ResolveSkillContextOptions,
  ResolvedSkillContext,
  SkillInventory,
  SkillInventoryEntry,
} from "./types.ts";

const UTF8_FATAL = new TextDecoder("utf-8", { fatal: true });

const withinCaseFolded = (target: string, root: string): boolean => {
  const normalizedTarget = path.resolve(target).toLocaleLowerCase("en-US");
  const normalizedRoot = path.resolve(root).toLocaleLowerCase("en-US");
  return (
    normalizedTarget === normalizedRoot ||
    normalizedTarget.startsWith(`${normalizedRoot}${path.sep}`)
  );
};

const pathPartsFromRoot = (root: string, target: string): string[] => {
  const relative = path.relative(root, target);
  if (
    relative === "" ||
    relative === "." ||
    relative.startsWith(`..${path.sep}`) ||
    relative === ".." ||
    path.isAbsolute(relative)
  ) {
    failSkillContext("REFERENCE_PATH_TRAVERSAL", "target is outside its permitted root", {
      target,
      root,
    });
  }
  return relative.split(path.sep);
};

const assertNoLinkedComponent = async (root: string, target: string): Promise<void> => {
  const parts = pathPartsFromRoot(root, target);
  let current = root;
  for (const part of parts) {
    current = path.join(current, part);
    let metadata;
    try {
      metadata = await lstat(current);
    } catch (error) {
      failSkillContext("REFERENCE_TARGET_MISSING", "a selected path component is missing", {
        path: current,
        cause: error instanceof Error ? error.message : String(error),
      });
    }
    if (metadata.isSymbolicLink()) {
      failSkillContext("REFERENCE_SYMLINK_DENIED", "symlink or junction components are forbidden", {
        path: current,
      });
    }
  }
  const finalMetadata = await stat(target);
  if (!finalMetadata.isFile()) {
    failSkillContext("REFERENCE_TARGET_MISSING", "selected context target is not a regular file", {
      path: target,
    });
  }
  if (finalMetadata.nlink !== 1) {
    failSkillContext("REFERENCE_HARDLINK_DENIED", "hard-linked context files are forbidden", {
      path: target,
      link_count: finalMetadata.nlink,
    });
  }
};

const resolveContainedFile = async (
  root: string,
  relativePosixPath: string,
  permittedRoot: string,
): Promise<string> => {
  const lexicalTarget = path.resolve(root, ...relativePosixPath.split("/"));
  const lexicalPermitted = path.resolve(root, ...permittedRoot.split("/"));
  if (!withinCaseFolded(lexicalTarget, lexicalPermitted)) {
    failSkillContext("REFERENCE_PATH_TRAVERSAL", "path escapes the permitted lexical root", {
      path: relativePosixPath,
    });
  }
  await assertNoLinkedComponent(root, lexicalTarget);
  let resolvedTarget: string;
  let resolvedPermitted: string;
  try {
    [resolvedTarget, resolvedPermitted] = await Promise.all([
      realpath(lexicalTarget),
      realpath(lexicalPermitted),
    ]);
  } catch (error) {
    failSkillContext("REFERENCE_TARGET_MISSING", "realpath resolution failed", {
      path: relativePosixPath,
      cause: error instanceof Error ? error.message : String(error),
    });
  }
  if (!withinCaseFolded(resolvedTarget, resolvedPermitted)) {
    failSkillContext("REFERENCE_PATH_TRAVERSAL", "realpath escapes the permitted root", {
      path: relativePosixPath,
    });
  }
  return resolvedTarget;
};

interface CanonicalFile {
  path: string;
  bytes: Buffer;
  text: string;
  sha256: string;
  byteCount: number;
}

const readCanonicalFile = async (
  root: string,
  relativePosixPath: string,
  permittedRoot: string,
): Promise<CanonicalFile> => {
  const target = await resolveContainedFile(root, relativePosixPath, permittedRoot);
  const bytes = await readFile(target);
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    failSkillContext("REFERENCE_CONTENT_DRIFT", "context file must not contain a UTF-8 BOM", {
      path: relativePosixPath,
    });
  }
  let text: string;
  try {
    text = UTF8_FATAL.decode(bytes);
  } catch {
    failSkillContext("REFERENCE_CONTENT_DRIFT", "context file is not valid UTF-8", {
      path: relativePosixPath,
    });
  }
  if (text.includes("\r") || !text.endsWith("\n")) {
    failSkillContext(
      "REFERENCE_CONTENT_DRIFT",
      "context file must use LF and end with a newline",
      { path: relativePosixPath },
    );
  }
  return {
    path: target,
    bytes,
    text,
    sha256: sha256Bytes(bytes),
    byteCount: bytes.length,
  };
};

const assertSealedFile = (
  file: CanonicalFile,
  expected: { path: string; sha256: string; byte_count: number },
): void => {
  if (file.sha256 !== expected.sha256 || file.byteCount !== expected.byte_count) {
    failSkillContext("REFERENCE_CONTENT_DRIFT", "file bytes do not match inventory seal", {
      path: expected.path,
      expected_sha256: expected.sha256,
      actual_sha256: file.sha256,
      expected_bytes: expected.byte_count,
      actual_bytes: file.byteCount,
    });
  }
};

const verifyAgentProjection = async (
  pluginRoot: string,
  skill: SkillInventoryEntry,
): Promise<void> => {
  const agentPath = skill.path.replace(/SKILL\.md$/u, "agents/openai.yaml");
  const file = await readCanonicalFile(pluginRoot, agentPath, "skills");
  const expectedImplicit = skill.allow_implicit_invocation ? "true" : "false";
  const dispositionMatches = [
    ...file.text.matchAll(/^  invocation_disposition: ([A-Z_]+)$/gmu),
  ].map((entry) => entry[1]);
  const implicitMatches = [
    ...file.text.matchAll(/^  allow_implicit_invocation: (true|false)$/gmu),
  ].map((entry) => entry[1]);
  if (
    dispositionMatches.length !== 1 ||
    dispositionMatches[0] !== skill.invocation_disposition ||
    implicitMatches.length !== 1 ||
    implicitMatches[0] !== expectedImplicit
  ) {
    failSkillContext(
      "SKILL_INVOCATION_POLICY_DRIFT",
      `${skill.skill_id} agent projection differs from inventory policy`,
    );
  }
};

const verifyAuthoritySources = async (
  repositoryRoot: string,
  reference: ReferenceInventoryEntry,
): Promise<void> => {
  for (const source of reference.authority_sources) {
    const file = await readCanonicalFile(repositoryRoot, source.path, "");
    if (file.sha256 !== source.sha256) {
      failSkillContext(
        "REFERENCE_AUTHORITY_STALE",
        `${reference.reference_id} authority source has changed`,
        { source_path: source.path, expected: source.sha256, actual: file.sha256 },
      );
    }
  }
};

export const buildInitialMetadataProjection = (
  inventory: SkillInventory,
  hostBudget: HostMetadataBudget | undefined = undefined,
  explicitParentRequested = false,
): MetadataProjectionResult => {
  const validatedHostBudget = validateHostMetadataBudget(hostBudget);
  const text = serializeInitialMetadata(inventory.skills);
  const seal = inventory.metadata_projection;
  if (sha256Text(text) !== seal.sha256 || Buffer.byteLength(text, "utf8") !== seal.byte_count) {
    failSkillContext("INVENTORY_HASH_MISMATCH", "metadata projection seal does not match inventory");
  }
  if (metadataFitsHost(seal, validatedHostBudget, inventory.budgets)) {
    return Object.freeze({
      text,
      sha256: seal.sha256,
      byte_count: seal.byte_count,
      token_count: seal.token_count,
      skill_count: inventory.skills.length,
      degraded_mode: "NONE",
      warnings: Object.freeze([]) as unknown as string[],
    });
  }
  if (
    explicitParentRequested &&
    validatedHostBudget?.parent_explicitly_reachable === true
  ) {
    return Object.freeze({
      text: "",
      sha256: sha256Text(""),
      byte_count: 0,
      token_count: 0,
      skill_count: 0,
      degraded_mode: "EXPLICIT_PARENT_ONLY",
      warnings: Object.freeze(["HOST_SKILL_METADATA_BUDGET_INSUFFICIENT"]) as unknown as string[],
    });
  }
  failSkillContext(
    "HOST_SKILL_METADATA_BUDGET_INSUFFICIENT",
    "host metadata budget cannot represent all 29 canonical skills",
    { host_budget: validatedHostBudget ?? null },
  );
};

export interface FileVerificationResult {
  skill_files_verified: number;
  reference_files_verified: number;
  authority_sources_verified: number;
  agent_projections_verified: number;
}

export const verifyInventoryFiles = async (
  inventory: SkillInventory,
  pluginRoot: string,
  repositoryRoot = path.resolve(pluginRoot, "..", ".."),
): Promise<FileVerificationResult> => {
  let authoritySourcesVerified = 0;
  for (const skill of inventory.skills) {
    const file = await readCanonicalFile(pluginRoot, skill.path, "skills");
    assertSealedFile(file, skill);
    await verifyAgentProjection(pluginRoot, skill);
  }
  for (const reference of inventory.references) {
    const file = await readCanonicalFile(
      pluginRoot,
      reference.path,
      "skills/foundry/references",
    );
    assertSealedFile(file, reference);
    assertReferenceFileBudget(file.byteCount, reference.token_count, inventory.budgets);
    await verifyAuthoritySources(repositoryRoot, reference);
    authoritySourcesVerified += reference.authority_sources.length;
  }
  return Object.freeze({
    skill_files_verified: inventory.skills.length,
    reference_files_verified: inventory.references.length,
    authority_sources_verified: authoritySourcesVerified,
    agent_projections_verified: inventory.skills.length,
  });
};

const deepFreeze = <T>(candidate: T): T => {
  if (candidate !== null && typeof candidate === "object") {
    for (const value of Object.values(candidate as Record<string, unknown>)) deepFreeze(value);
    Object.freeze(candidate);
  }
  return candidate;
};

export const resolveSkillContext = async (
  options: ResolveSkillContextOptions,
): Promise<ResolvedSkillContext> => {
  const inventory = await loadSkillInventory(options.plugin_root);
  assertReachability(inventory);
  const selection = selectReferences({
    inventory,
    routingDecision: options.routing_decision,
    conditions: options.conditions,
    invocationAuthority: options.invocation_authority,
    explicitReferenceIds: options.explicit_reference_ids,
    explicitReferenceAuthorityIds: options.explicit_reference_authority_ids,
    llmProposals: options.llm_proposals,
  });
  const skill = inventory.skills.find(
    (entry) => entry.skill_id === selection.selected_skill_id,
  )!;
  const explicitParentRequested =
    options.routing_decision.mode === "explicit" && skill.skill_id === "foundry";
  const projection = buildInitialMetadataProjection(
    inventory,
    options.host_metadata_budget,
    explicitParentRequested,
  );
  const repositoryRoot = options.repository_root ?? path.resolve(options.plugin_root, "..", "..");
  const skillFile = await readCanonicalFile(options.plugin_root, skill.path, "skills");
  assertSealedFile(skillFile, skill);
  await verifyAgentProjection(options.plugin_root, skill);

  const referenceById = new Map(
    inventory.references.map((entry) => [entry.reference_id, entry]),
  );
  const orderedReferences: Array<{ entry: ReferenceInventoryEntry; file: CanonicalFile }> = [];
  for (const referenceId of selection.ordered_reference_ids) {
    const reference = referenceById.get(referenceId);
    if (reference === undefined) {
      failSkillContext("REFERENCE_TARGET_MISSING", `selected reference ${referenceId} is absent`);
    }
    const file = await readCanonicalFile(
      options.plugin_root,
      reference.path,
      "skills/foundry/references",
    );
    assertSealedFile(file, reference);
    await verifyAuthoritySources(repositoryRoot, reference);
    orderedReferences.push({ entry: reference, file });
  }
  const totalReferenceBytes = orderedReferences.reduce(
    (total, current) => total + current.file.byteCount,
    0,
  );
  const totalReferenceTokens = orderedReferences.reduce(
    (total, current) => total + current.entry.token_count,
    0,
  );
  assertActivationBudget(
    {
      skill_bytes: skillFile.byteCount,
      skill_tokens: skill.token_count,
      reference_count: orderedReferences.length,
      reference_depth: selection.transitive_depth,
      reference_bytes: totalReferenceBytes,
      reference_tokens: totalReferenceTokens,
    },
    inventory.budgets,
  );
  const preimage = {
    inventory_id: inventory.inventory_id,
    inventory_hash: inventory.inventory_hash,
    routing_decision_id: options.routing_decision.decision_id,
    selected_skill_id: skill.skill_id,
    skill_path: skill.path,
    skill_sha256: skillFile.sha256,
    skill_byte_count: skillFile.byteCount,
    skill_token_count: skill.token_count,
    ordered_reference_ids: selection.ordered_reference_ids,
    ordered_reference_paths: orderedReferences.map((entry) => entry.entry.path),
    reference_hashes: orderedReferences.map((entry) => ({
      reference_id: entry.entry.reference_id,
      sha256: entry.file.sha256,
    })),
    reference_selection_reasons: selection.reference_selection_reasons,
    transitive_depth: selection.transitive_depth,
    total_reference_bytes: totalReferenceBytes,
    total_reference_tokens: totalReferenceTokens,
    total_activation_bytes: skillFile.byteCount + totalReferenceBytes,
    total_activation_tokens: skill.token_count + totalReferenceTokens,
    invocation_disposition: skill.invocation_disposition,
    degraded_mode: projection.degraded_mode,
    warnings: [...projection.warnings, ...selection.warnings],
    errors: [] as string[],
  };
  return deepFreeze({
    ...preimage,
    context_hash: sha256Text(canonicalizeJson(preimage)),
  });
};
