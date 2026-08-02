// Bind the ui-api surface to the canonical OpenAPI document on disk.
//
// `src/epistemic_foundry/contracts/registry.py` states the authority: the
// repository-root `openapi/` tree is the source authority, and the packaged
// `src/epistemic_foundry/_canonical/openapi/` copy is a build-time projection
// of it.  This module therefore reads the root document — the declaring
// source — and records its byte digest so every derived artifact (route table,
// coverage record, generated client) can be traced back to the exact bytes it
// was derived from.

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { bytesSha256 } from "./canonical-hash.mjs";
import { projectRouteTable } from "./route-table.mjs";
import { refuse } from "./surface-errors.mjs";
import { parseYamlSubset } from "./yaml-subset.mjs";

/** Repository root, resolved from this module rather than the process cwd. */
export const REPOSITORY_ROOT = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../..",
);

/** The declaring source, relative to the repository root. */
export const CANONICAL_OPENAPI_PATH = "openapi/epistemic-foundry-v1.openapi.yaml";

/** The build-time package projection of the same document. */
export const PACKAGED_OPENAPI_PATH =
  "src/epistemic_foundry/_canonical/openapi/epistemic-foundry-v1.openapi.yaml";

/**
 * Read one repository file as UTF-8 text plus its byte digest.
 *
 * @param {string} relativePath repository-root-relative path
 */
export const readRepositoryDocument = (relativePath) => {
  const absolutePath = resolve(REPOSITORY_ROOT, relativePath);
  let bytes;
  try {
    bytes = readFileSync(absolutePath);
  } catch (error) {
    refuse("DOCUMENT_SOURCE_MISSING", `cannot read ${relativePath}`, {
      cause: String(error && error.code ? error.code : error),
      relativePath,
    });
  }
  return Object.freeze({
    relativePath,
    sha256: bytesSha256(bytes),
    text: bytes.toString("utf8"),
  });
};

/**
 * Load, validate and project the canonical OpenAPI document.
 *
 * @param {string} [relativePath] override for tests and fixtures
 */
export const loadRouteTable = (relativePath = CANONICAL_OPENAPI_PATH) => {
  const source = readRepositoryDocument(relativePath);
  return projectRouteTable(parseYamlSubset(source.text), {
    documentPath: source.relativePath,
    documentSha256: source.sha256,
  });
};

/**
 * Project a route table from in-memory YAML, for fixtures and adversarial
 * cases that must never touch the repository tree.
 *
 * @param {string} text
 * @param {string} [documentPath]
 */
export const projectRouteTableFromText = (text, documentPath = "<in-memory>") =>
  projectRouteTable(parseYamlSubset(text), {
    documentPath,
    documentSha256: bytesSha256(text),
  });
