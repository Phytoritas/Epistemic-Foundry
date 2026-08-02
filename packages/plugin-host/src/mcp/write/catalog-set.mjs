// Composition of the generated MCP descriptor projections.
//
// This module owns no MCP tool-name literal: it concatenates the generated
// projections named by contracts/mcp/catalog-set.yaml in that file's declared
// merge order and asserts the declared counts (EF4-I22).  No combined catalog
// or combined descriptor file is produced, because a generated file must never
// become a second declaring source.

import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const HERE = dirname(fileURLToPath(import.meta.url));
// packages/plugin-host/src/mcp/write -> repository root
const REPOSITORY_ROOT = join(HERE, "..", "..", "..", "..", "..");

const mutatingDocument = require("./generated/t02-tool-descriptors.json");
const catalogSet = mutatingDocument.catalog_set;

export const PROTOCOL_VERSION = mutatingDocument.protocol_version;
export const CATALOG_SET_ID = catalogSet.set_id;
export const GLOBAL_EXACT_COUNT = catalogSet.global_exact_count;

function loadProjection(entry) {
  const document = require(join(REPOSITORY_ROOT, entry.descriptor_projection));
  if (document.protocol_version !== PROTOCOL_VERSION) {
    throw new Error(`protocol version drifted in ${entry.catalog_id}`);
  }
  if (document.tools.length !== entry.exact_count) {
    throw new Error(
      `${entry.catalog_id} declares ${entry.exact_count} tools but projects ${document.tools.length}`,
    );
  }
  return document.tools;
}

function merge() {
  const byId = new Map(catalogSet.catalogs.map((entry) => [entry.catalog_id, entry]));
  if (byId.size !== catalogSet.catalogs.length) {
    throw new Error("the catalog set declares a duplicate catalog id");
  }
  const merged = [];
  const seen = new Set();
  for (const catalogId of catalogSet.merge_order) {
    const entry = byId.get(catalogId);
    if (entry === undefined) {
      throw new Error(`merge order names an undeclared catalog: ${catalogId}`);
    }
    for (const tool of loadProjection(entry)) {
      if (seen.has(tool.name)) {
        throw new Error(`tool name declared in more than one catalog: ${tool.name}`);
      }
      seen.add(tool.name);
      merged.push(tool);
    }
  }
  if (merged.length !== GLOBAL_EXACT_COUNT) {
    throw new Error(
      `composed surface holds ${merged.length} tools but declares ${GLOBAL_EXACT_COUNT}`,
    );
  }
  return merged;
}

const MERGED = Object.freeze(merge());

/** The full composed tools/list table, in catalog-set merge order. */
export function mergedToolDescriptors() {
  return structuredClone(MERGED);
}

/** Only the mutating half, for adapters that expose the write surface alone. */
export function mutatingToolDescriptors() {
  return structuredClone(mutatingDocument.tools);
}

/** Membership metadata; carries counts and order, never a tool name. */
export function catalogSetMetadata() {
  return structuredClone(catalogSet);
}

/** True when the named tool is declared MUTATING_EFFECT by its catalog. */
export function isMutatingTool(name) {
  return MERGED.some(
    (tool) => tool.name === name && tool.annotations.sideEffectClass === "MUTATING_EFFECT",
  );
}
