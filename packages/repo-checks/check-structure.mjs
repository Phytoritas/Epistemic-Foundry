import { readFile, readdir, stat } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const readJson = async (path) => JSON.parse(await readFile(path, "utf8"));
const exists = async (path) => stat(path).then(() => true, () => false);
const failures = [];
const fail = (message) => failures.push(message);

const rootPackage = await readJson(resolve(repoRoot, "package.json"));
const policy = await readJson(resolve(repoRoot, "packages/boundary-policy.json"));
const pyproject = await readFile(resolve(repoRoot, "pyproject.toml"), "utf8");
const pnpmWorkspace = await readFile(resolve(repoRoot, "pnpm-workspace.yaml"), "utf8");

if (rootPackage.private !== true) fail("root package.json must be private");
if (JSON.stringify(rootPackage.workspaces) !== JSON.stringify(["packages/*"])) {
  fail("root package.json must declare exactly the packages/* workspace");
}
if (!/^\s*-\s+["']?packages\/\*["']?\s*$/m.test(pnpmWorkspace)) {
  fail("pnpm-workspace.yaml must declare packages/*");
}

for (const [key, value] of Object.entries({
  node_root: "packages",
  python_runtime_root: policy.python.runtimeRoot,
  python_component_root: policy.python.componentRoot,
  component_source_imports: "forbidden",
})) {
  const expression = new RegExp(`^${key}\\s*=\\s*["']${value.replaceAll("/", "\\/")}["']\\s*$`, "m");
  if (!expression.test(pyproject)) fail(`pyproject.toml missing workspace binding ${key}=${value}`);
}

for (const root of [policy.python.runtimeRoot, policy.python.componentRoot]) {
  if (!(await exists(resolve(repoRoot, root)))) fail(`missing explicit Python root: ${root}`);
}

const expectedDirectories = new Set(policy.components.map(({ directory }) => directory));
const actualDirectories = new Set(
  (await readdir(resolve(repoRoot, policy.workspaceRoot), { withFileTypes: true }))
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name),
);
for (const directory of expectedDirectories) {
  if (!actualDirectories.has(directory)) fail(`missing workspace component directory: ${directory}`);
}

const packageNames = new Set();
for (const component of policy.components) {
  const manifestPath = resolve(repoRoot, policy.workspaceRoot, component.directory, "package.json");
  if (!(await exists(manifestPath))) {
    fail(`missing component package.json: ${component.directory}`);
    continue;
  }
  const manifest = await readJson(manifestPath);
  if (manifest.name !== component.packageName) {
    fail(`${component.directory}: package name ${manifest.name} != ${component.packageName}`);
  }
  if (manifest.private !== true) fail(`${component.packageName}: scaffold packages must be private`);
  if (packageNames.has(manifest.name)) fail(`duplicate workspace package name: ${manifest.name}`);
  packageNames.add(manifest.name);
}

if (failures.length) {
  console.error(JSON.stringify({ check: "repo_structure_check", status: "FAIL", failures }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({
  check: "repo_structure_check",
  status: "PASS",
  nodeWorkspaceRoot: policy.workspaceRoot,
  nodeComponents: policy.components.length,
  pythonRuntimeRoot: policy.python.runtimeRoot,
  pythonComponentRoot: policy.python.componentRoot,
}, null, 2));
