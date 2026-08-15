// Bounded repository scan for the first WorkspaceMapSnapshot profile.
//
// The M01-M03 modules are pure: they compute over data a caller supplies and
// never touch a filesystem.  This module is the one place that reads a
// workspace, and it deliberately reads a narrow slice: JavaScript-family
// source files and their relative import edges.
//
// That narrowness is the point.  A map that silently mixes "we did not look"
// with "there is nothing there" is worse than a small honest map, so the scan
// reports exactly which entity and edge classes it covered and which known
// classes it skipped.  Callers publish those lists as the snapshot's
// included_scopes and excluded_scopes.
//
// The scan freezes its input: it enumerates admissible files, hashes their
// exact bytes, and derives a root_hash from that manifest.  A caller can
// re-run the scan afterwards and compare root_hash to detect a workspace that
// changed mid-read, which would otherwise yield a graph whose nodes and edges
// never coexisted.

import { createHash } from "node:crypto";
import { readFile, readdir, realpath, stat } from "node:fs/promises";
import { join, posix, relative, resolve, sep } from "node:path";

export class WorkspaceScanError extends Error {
  constructor(code, message, details = null) {
    super(message);
    this.name = "WorkspaceScanError";
    this.code = code;
    this.details = details;
  }
}

const fail = (code, message, details = null) => {
  throw new WorkspaceScanError(code, message, details);
};

/** Extensions this profile can parse well enough to claim coverage. */
export const SCANNED_EXTENSIONS = Object.freeze([".mjs", ".js", ".cjs", ".ts", ".mts", ".cts"]);

/** Directories skipped as not-first-party or not-source. */
export const SKIPPED_DIRECTORIES = Object.freeze([
  "node_modules",
  ".git",
  "dist",
  "build",
  "coverage",
  ".venv",
  "__pycache__",
]);

/**
 * Coverage this profile actually achieves, in the canonical M01 vocabulary.
 *
 * Published verbatim as the snapshot's scope disclosure so a reader can tell
 * what the map means without reading this source.
 */
export const REPOSITORY_PROFILE_SCOPES = Object.freeze({
  included: Object.freeze([
    "CODE:SOURCE_FILE",
    "CODE:TEST",
    "CODE:IMPORTS(relative)",
  ]),
  excluded: Object.freeze([
    "CODE:PACKAGE",
    "CODE:CODE_SYMBOL",
    "CODE:IMPORTS(bare-specifier)",
    "CODE:SCHEMA_REF",
    "CODE:API_CONTRACT_REF",
    "CODE:WORKFLOW",
    "CODE:WORK_PACKAGE",
    "CODE:SKILL",
    "CODE:HOOK",
    "CODE:MCP_TOOL",
    "RESEARCH:*",
    "ARTIFACT:*",
    "SOURCE_CLASS:DIST",
    "SOURCE_CLASS:GENERATED",
    "SOURCE_CLASS:VENDOR",
  ]),
});

const sha256 = (bytes) => `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

const isScannable = (name) => SCANNED_EXTENSIONS.some((extension) => name.endsWith(extension));

/** A test file is still first-party source, but its source_class differs. */
const sourceClassFor = (relativePath) =>
  /(^|\/)tests?(\/|$)|\.test\.|\.spec\./.test(relativePath) ? "TEST" : "SOURCE";

const kindFor = (sourceClass) => (sourceClass === "TEST" ? "TEST" : "SOURCE_FILE");

/**
 * Enumerate admissible files under an authorized root.
 *
 * Symlinks are resolved and rejected when they escape the root: a map that
 * silently followed a link outside the workspace would attribute foreign code
 * to this workspace's identity.
 */
const enumerateFiles = async (root, current, collected) => {
  const entries = await readdir(current, { withFileTypes: true });
  for (const entry of entries.sort((left, right) => (left.name < right.name ? -1 : 1))) {
    if (entry.name.startsWith(".") && entry.name !== ".codex-plugin") continue;
    const absolute = join(current, entry.name);
    if (entry.isDirectory()) {
      if (SKIPPED_DIRECTORIES.includes(entry.name)) continue;
      await enumerateFiles(root, absolute, collected);
      continue;
    }
    if (!entry.isFile() && !entry.isSymbolicLink()) continue;
    if (!isScannable(entry.name)) continue;

    let resolved;
    try {
      resolved = await realpath(absolute);
    } catch (cause) {
      fail("UNREADABLE_PATH", `cannot resolve ${absolute}`, { cause: cause.message });
    }
    if (resolved !== absolute && !resolved.startsWith(root + sep)) {
      fail("PATH_ESCAPES_WORKSPACE", `${absolute} resolves outside the workspace root`);
    }
    const info = await stat(resolved);
    if (!info.isFile()) continue;
    collected.push({ absolute, relative: relative(root, absolute).split(sep).join("/") });
  }
  return collected;
};

/** Relative import and require specifiers, with their 1-based line numbers. */
const IMPORT_PATTERNS = Object.freeze([
  /\bfrom\s+["'](\.[^"']*)["']/g,
  /\bimport\s+["'](\.[^"']*)["']/g,
  /\bimport\s*\(\s*["'](\.[^"']*)["']\s*\)/g,
  /\brequire\s*\(\s*["'](\.[^"']*)["']\s*\)/g,
]);

const extractRelativeImports = (text) => {
  const found = new Map();
  for (const pattern of IMPORT_PATTERNS) {
    pattern.lastIndex = 0;
    let match = pattern.exec(text);
    while (match !== null) {
      const line = text.slice(0, match.index).split("\n").length;
      if (!found.has(match[1])) found.set(match[1], line);
      match = pattern.exec(text);
    }
  }
  return [...found.entries()].sort((left, right) => (left[0] < right[0] ? -1 : 1));
};

/** Resolve a relative specifier the way Node would, within the scanned set. */
const resolveSpecifier = (fromRelative, specifier, known) => {
  const base = posix.dirname(fromRelative);
  const target = posix.normalize(posix.join(base, specifier));
  if (known.has(target)) return target;
  for (const extension of SCANNED_EXTENSIONS) {
    if (known.has(target + extension)) return target + extension;
    const asIndex = posix.join(target, `index${extension}`);
    if (known.has(asIndex)) return asIndex;
  }
  return null;
};

/**
 * Scan a workspace root into `buildWorkspaceInventory` and
 * `extractWorkspaceEdges` inputs.
 *
 * Returns the inventory input, the reference list, and the frozen root_hash
 * so a caller can re-verify the workspace did not change during assembly.
 */
export const scanRepositoryWorkspace = async ({ workspaceRoot, workspaceId, owner }) => {
  if (typeof workspaceRoot !== "string" || workspaceRoot.length === 0) {
    fail("INVALID_SCAN_INPUT", "workspaceRoot must be a non-empty string");
  }
  if (typeof workspaceId !== "string" || workspaceId.length === 0) {
    fail("INVALID_SCAN_INPUT", "workspaceId must be a non-empty string");
  }
  const ownerId = typeof owner === "string" && owner.length > 0 ? owner : "M04";

  let root;
  try {
    root = await realpath(resolve(workspaceRoot));
  } catch (cause) {
    fail("WORKSPACE_UNREADABLE", `cannot resolve workspace root`, { cause: cause.message });
  }

  const files = await enumerateFiles(root, root, []);
  files.sort((left, right) => (left.relative < right.relative ? -1 : 1));

  const contents = new Map();
  const entities = [];
  const unreadablePaths = [];
  for (const file of files) {
    let bytes;
    try {
      bytes = await readFile(file.absolute);
    } catch {
      // A file that vanished or cannot be read is recorded, not skipped
      // silently: absence of evidence must stay visible in the inventory.
      unreadablePaths.push(file.relative);
      continue;
    }
    contents.set(file.relative, bytes.toString("utf8"));
    const sourceClass = sourceClassFor(file.relative);
    entities.push({
      entity_id: `CODE:${file.relative}`,
      kind: kindFor(sourceClass),
      label: posix.basename(file.relative),
      path: file.relative,
      locator: null,
      content_hash: sha256(bytes),
      owner: ownerId,
      source_class: sourceClass,
      aliases: [],
    });
  }

  const known = new Set(contents.keys());
  const references = [];
  for (const [relativePath, text] of [...contents.entries()].sort((left, right) =>
    left[0] < right[0] ? -1 : 1,
  )) {
    for (const [specifier, line] of extractRelativeImports(text)) {
      const target = resolveSpecifier(relativePath, specifier, known);
      references.push({
        source_entity_id: `CODE:${relativePath}`,
        kind: "IMPORTS",
        // An unresolved specifier keeps its PATH identity so the extraction
        // records it as an explicit gap rather than dropping the edge.
        target_identity: {
          namespace: "PATH",
          value: target ?? posix.normalize(posix.join(posix.dirname(relativePath), specifier)),
        },
        target_hint: specifier,
        source_locator: `${relativePath}:${line}`,
        owner: ownerId,
      });
    }
  }

  // root_hash seals the exact bytes this scan observed, so a later rescan can
  // prove whether the workspace shifted underneath the map.
  const manifest = entities
    .map((entity) => `${entity.path}\u0000${entity.content_hash}`)
    .join("\n");

  return {
    root,
    inventoryInput: {
      workspace_id: workspaceId,
      root_hash: sha256(Buffer.from(manifest, "utf8")),
      entities,
      unreadable_paths: unreadablePaths.sort(),
    },
    references,
    scannedFileCount: entities.length,
  };
};
