// T01 schema resolution: every descriptor reference resolves to the exact
// canonical file with a matching $id — no duplicated wire schemas (EF4-I22).

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));

function readJson(relative) {
  return JSON.parse(readFileSync(join(ROOT, relative), "utf8"));
}

const document = readJson("packages/plugin-host/src/mcp/generated/tool-descriptors.json");

test("t01_schema_resolution: every inputSchema equals its contract input file", () => {
  for (const tool of document.tools) {
    const contractFile = readJson(
      join("contracts", "mcp", "t01", "inputs", `${tool.name}.input.schema.json`),
    );
    assert.deepEqual(tool.inputSchema, contractFile, tool.name);
    assert.equal(
      contractFile.$id,
      `https://epistemic-foundry.local/contracts/mcp/t01/inputs/${tool.name}.input.schema.json`,
    );
    assert.equal(contractFile.additionalProperties, false, tool.name);
    assert.ok(contractFile.required.includes("workspace_id"), tool.name);
  }
});

test("t01_schema_resolution: there is one input schema file per catalog tool", () => {
  const files = readdirSync(join(ROOT, "contracts", "mcp", "t01", "inputs")).sort();
  const expected = document.tools
    .map((tool) => `${tool.name}.input.schema.json`)
    .sort();

  assert.deepEqual(files, expected);
});

test("t01_schema_resolution: every data schema ref resolves to the canonical authority", () => {
  const prefix = "https://epistemic-foundry.local/schemas/";
  for (const tool of document.tools) {
    for (const ref of tool.annotations.dataSchemaRefs) {
      const fileName = ref.slice(prefix.length);
      const canonical = readJson(join("schemas", fileName));
      assert.equal(canonical.$id, ref, `${tool.name} -> ${ref}`);
    }
  }
});

test("t01_schema_resolution: shared envelope schemas resolve with exact ids", () => {
  const result = readJson("contracts/mcp/t01/foundry-mcp-tool-result.schema.json");
  const error = readJson("contracts/mcp/t01/foundry-mcp-tool-error.schema.json");

  assert.equal(
    result.$id,
    "https://epistemic-foundry.local/contracts/mcp/t01/foundry-mcp-tool-result.schema.json",
  );
  assert.equal(
    error.$id,
    "https://epistemic-foundry.local/contracts/mcp/t01/foundry-mcp-tool-error.schema.json",
  );
  assert.equal(result.properties.protocol_version.const, "2026-07-28");
  assert.equal(error.properties.protocol_version.const, "2026-07-28");
  assert.deepEqual(result.properties.read_model_state.enum, [
    "READY",
    "EMPTY_CONFIRMED",
    "DEGRADED",
    "UNAVAILABLE",
  ]);
  assert.deepEqual(error.properties.error_code.enum, [
    "INVALID_REQUEST",
    "UNKNOWN_TOOL",
    "INVALID_INPUT",
    "UNAUTHENTICATED",
    "WORKSPACE_DENIED",
    "UNAUTHORIZED",
    "NOT_FOUND",
    "IDEMPOTENCY_CONFLICT",
    "PLAN_COMPILATION_REJECTED",
    "INTERNAL",
  ]);
});
