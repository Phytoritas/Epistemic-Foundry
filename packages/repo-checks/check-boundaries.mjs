import { readFile, readdir, stat } from "node:fs/promises";
import { dirname, extname, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const workspaceRoot = resolve(repoRoot, "packages");
const policy = JSON.parse(await readFile(resolve(workspaceRoot, "boundary-policy.json"), "utf8"));
const failures = [];
const fail = (message) => failures.push(message);
const sourceExtensions = new Set([".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"]);
const dependencyFields = ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"];
const componentByName = new Map();
const componentByDirectory = new Map(policy.components.map((component) => [component.directory, component]));
const edges = new Map(policy.components.map((component) => [component.packageName, new Set()]));

const walk = async (root) => {
  const output = [];
  for (const entry of await readdir(root, { withFileTypes: true })) {
    if (["node_modules", "dist", "build", "coverage"].includes(entry.name)) continue;
    const path = resolve(root, entry.name);
    if (entry.isDirectory()) output.push(...await walk(path));
    else if (entry.isFile()) output.push(path);
  }
  return output;
};

for (const component of policy.components) {
  const componentRoot = resolve(workspaceRoot, component.directory);
  const manifest = JSON.parse(await readFile(resolve(componentRoot, "package.json"), "utf8"));
  component.version = manifest.version;
  componentByName.set(component.packageName, component);
}

for (const component of policy.components) {
  const componentRoot = resolve(workspaceRoot, component.directory);
  const manifest = JSON.parse(await readFile(resolve(componentRoot, "package.json"), "utf8"));
  for (const field of dependencyFields) {
    for (const [dependency, version] of Object.entries(manifest[field] ?? {})) {
      if (!componentByName.has(dependency)) continue;
      const sourceLayer = policy.layers[component.layer];
      const target = componentByName.get(dependency);
      if (version !== target.version) {
        fail(`${manifest.name}: internal dependency ${dependency} must exactly match ${target.version}`);
      }
      edges.get(manifest.name).add(dependency);
      const targetLayer = policy.layers[target.layer];
      if (component.layer !== "tooling" && target.layer === "tooling") {
        fail(`${manifest.name}: product component may not depend on tooling ${dependency}`);
      }
      if (component.layer !== "tooling" && targetLayer > sourceLayer) {
        fail(`${manifest.name}: outward dependency on ${dependency} violates layer direction`);
      }
    }
  }

  for (const path of await walk(componentRoot)) {
    if (!sourceExtensions.has(extname(path))) continue;
    const text = await readFile(path, "utf8");
    const importPattern = /(?:from\s*|import\s*\(|require\s*\()\s*["']([^"']+)["']/g;
    for (const match of text.matchAll(importPattern)) {
      const specifier = match[1];
      if (/^@epistemic-foundry\/[^/]+\/src(?:\/|$)/.test(specifier)) {
        fail(`${relative(repoRoot, path)}: private source import ${specifier}`);
      }
      if (!specifier.startsWith(".")) continue;
      const resolved = resolve(dirname(path), specifier);
      const rel = relative(workspaceRoot, resolved).split(sep);
      const target = componentByDirectory.get(rel[0]);
      if (target && target.directory !== component.directory && rel.includes("src")) {
        fail(`${relative(repoRoot, path)}: relative import reaches ${target.directory}/src`);
      }
    }
  }
}

const visiting = new Set();
const visited = new Set();
const visit = (name, stack = []) => {
  if (visiting.has(name)) {
    fail(`workspace dependency cycle: ${[...stack, name].join(" -> ")}`);
    return;
  }
  if (visited.has(name)) return;
  visiting.add(name);
  for (const dependency of edges.get(name) ?? []) visit(dependency, [...stack, name]);
  visiting.delete(name);
  visited.add(name);
};
for (const name of edges.keys()) visit(name);

for (const root of [policy.python.runtimeRoot, policy.python.componentRoot]) {
  const absolute = resolve(repoRoot, root);
  if (!(await stat(absolute).then(() => true, () => false))) continue;
  for (const path of await walk(absolute)) {
    if (extname(path) !== ".py") continue;
    const text = await readFile(path, "utf8");
    if (/sys\.path\.(?:append|insert)\s*\(/.test(text)) {
      fail(`${relative(repoRoot, path)}: sys.path mutation can bypass component boundaries`);
    }
    if (/['"](?:\.\.\/)+(?:packages|python|src)\//.test(text)) {
      fail(`${relative(repoRoot, path)}: filesystem source import bypass detected`);
    }
  }
}

if (failures.length) {
  console.error(JSON.stringify({ check: "forbidden_source_import_check", status: "FAIL", failures }, null, 2));
  process.exit(1);
}

const edgeCount = [...edges.values()].reduce((count, dependencies) => count + dependencies.size, 0);
console.log(JSON.stringify({
  check: "forbidden_source_import_check",
  status: "PASS",
  components: policy.components.length,
  internalPackageEdges: edgeCount,
  policy: policy.sourceImportPolicy,
}, null, 2));
