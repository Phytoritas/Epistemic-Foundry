#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const manifestPath = resolve(repoRoot, "packages/contracts/src/generated/contract-manifest.json");
const pythonManifestPath = resolve(repoRoot, "python/epistemic_foundry/contracts/contract-manifest.json");
const uiManifestPath = resolve(repoRoot, "web/src/generated/contract-manifest.json");

const readJson = async (path) => JSON.parse(await readFile(path, "utf8"));
const manifest = await readJson(manifestPath);
const pythonManifest = await readJson(pythonManifestPath);
const uiManifest = await readJson(uiManifestPath);
const registry = await import("@epistemic-foundry/contracts");

const compact = (value) => JSON.stringify(value);
const failures = [];
if (compact(manifest) !== compact(pythonManifest)) failures.push("python manifest differs");
if (compact(manifest) !== compact(uiManifest)) failures.push("UI manifest differs");
if (compact(manifest) !== compact(registry.contractManifest)) failures.push("runtime registry differs");

const fixtures = {};
for (const contract of manifest.contracts) {
  const path = resolve(repoRoot, contract.example_file);
  const raw = await readFile(path);
  const value = JSON.parse(raw.toString("utf8"));
  const digest = `sha256:${createHash("sha256").update(raw).digest("hex")}`;
  if (digest !== contract.example_sha256) {
    failures.push(`${contract.example_file}: example hash mismatch`);
  }
  fixtures[contract.example_file] = value;
}

const result = {
  check: "cross_language_fixture_node",
  status: failures.length ? "FAIL" : "PASS",
  schema_count: manifest.schema_count,
  example_count: Object.keys(fixtures).length,
  schema_bundle_sha256: manifest.schema_bundle_sha256,
  example_bundle_sha256: manifest.example_bundle_sha256,
  failures,
  fixtures,
};
console.log(JSON.stringify(result));
if (failures.length) process.exit(1);
