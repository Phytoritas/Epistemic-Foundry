// T01 canonical tool-catalog projection: exactly thirteen frozen tools.

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));

function readJson(relative) {
  return JSON.parse(readFileSync(join(ROOT, relative), "utf8"));
}

const document = readJson("packages/plugin-host/src/mcp/generated/tool-descriptors.json");

test("t01_tool_catalog: descriptor projection derives from the canonical catalog", () => {
  assert.equal(document.generated_from, "contracts/mcp/t01/tool-catalog.yaml");
  assert.equal(document.protocol_version, "2026-07-28");
  assert.ok(Array.isArray(document.tools));
});

test("t01_tool_catalog: exactly nine PURE_READ and four DURABLE_PLAN_ARTIFACT tools", () => {
  const names = document.tools.map((tool) => tool.name);
  const reads = document.tools.filter(
    (tool) => tool.annotations.sideEffectClass === "PURE_READ",
  );
  const plans = document.tools.filter(
    (tool) => tool.annotations.sideEffectClass === "DURABLE_PLAN_ARTIFACT",
  );

  assert.equal(document.tools.length, 13);
  assert.equal(new Set(names).size, 13);
  assert.equal(reads.length, 9);
  assert.equal(plans.length, 4);
  for (const tool of document.tools) {
    assert.match(tool.name, /^foundry\.[a-z][a-z_]*(\.[a-z][a-z_]*)*$/);
    assert.equal(
      tool.annotations.readOnlyHint,
      tool.annotations.sideEffectClass === "PURE_READ",
    );
  }
});

test("t01_tool_catalog: planning tools bind exactly one canonical artifact schema", () => {
  for (const tool of document.tools) {
    const refs = tool.annotations.dataSchemaRefs;
    assert.ok(Array.isArray(refs), tool.name);
    if (tool.annotations.sideEffectClass === "DURABLE_PLAN_ARTIFACT") {
      assert.equal(refs.length, 1, tool.name);
    }
    for (const ref of refs) {
      assert.match(
        ref,
        /^https:\/\/epistemic-foundry\.local\/schemas\/[a-z0-9-]+\.schema\.json$/,
        tool.name,
      );
    }
  }
});

test("t01_tool_catalog: the plugin MCP declaration is the packaged stateless STDIO server", () => {
  const declaration = readJson("plugins/epistemic-foundry/.mcp.json");
  const servers = declaration.mcpServers;

  assert.deepEqual(Object.keys(servers), ["epistemic-foundry"]);
  const server = servers["epistemic-foundry"];
  assert.equal(server.command, "node");
  assert.deepEqual(server.args, ["./dist/mcp-server.mjs"]);
});

test("t01_tool_catalog: the packaged profile advertises the whole canonical catalog", () => {
  const packaged = readJson("plugins/epistemic-foundry/dist/tool-descriptors.json");
  const catalog = readJson("packages/plugin-host/src/mcp/generated/tool-descriptors.json");

  assert.equal(packaged.protocol_version, catalog.protocol_version);
  assert.equal(packaged.tools.length, 13);
  assert.deepEqual(
    packaged.tools.map((tool) => tool.name),
    catalog.tools.map((tool) => tool.name),
  );
  for (const tool of packaged.tools) {
    const canonical = catalog.tools.find((entry) => entry.name === tool.name);
    assert.ok(canonical, tool.name);
    assert.deepEqual(tool.inputSchema, canonical.inputSchema, tool.name);
    assert.deepEqual(tool.annotations, canonical.annotations, tool.name);
  }
});

test("t01_tool_catalog: the bundled workspace-map payload matches its source", () => {
  const manifest = readJson(
    "plugins/epistemic-foundry/dist/workspace-map/bundle-manifest.json",
  );
  assert.equal(manifest.source, "packages/workspace-map/src");

  const entries = Object.entries(manifest.files);
  assert.ok(entries.length > 0, "bundle manifest must record files");
  for (const [relative, recorded] of entries) {
    const source = readFileSync(join(ROOT, "packages/workspace-map/src", relative));
    const bundled = readFileSync(
      join(ROOT, "plugins/epistemic-foundry/dist/workspace-map", relative),
    );
    assert.deepEqual(bundled, source, `${relative} drifted from its source`);
    assert.equal(
      `sha256:${createHash("sha256").update(source).digest("hex")}`,
      recorded,
      `${relative} hash does not match the recorded provenance`,
    );
  }
});
