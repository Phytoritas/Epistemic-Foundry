// Bundle the workspace-map snapshot producer into the installed plugin payload.
//
// The packaged plugin must start with no repository checkout, but the map
// semantics live in @epistemic-foundry/workspace-map and the repository
// forbids cross-package source imports (`public-package-api-only`). Copying the
// exact source files into the payload keeps one implementation: the copy is
// generated, never hand-edited, and its provenance hash is recorded so drift
// remains detectable.
//
// Usage:
//   node packages/plugin-host/src/cli/bundle-map-worker.mjs
//   node packages/plugin-host/src/cli/bundle-map-worker.mjs --check
//   node packages/plugin-host/src/cli/bundle-map-worker.mjs --preflight

import { createHash, randomUUID } from "node:crypto";
import {
  lstat,
  mkdir,
  readFile,
  readdir,
  rename,
  unlink,
  writeFile,
} from "node:fs/promises";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = resolve(fileURLToPath(new URL("../../../..", import.meta.url)));
const PLUGIN_ROOT = join(REPO_ROOT, "plugins", "epistemic-foundry");
const SOURCE_DIR = join(REPO_ROOT, "packages", "workspace-map", "src");
const FINAL_PAYLOAD_DIR = join(PLUGIN_ROOT, "dist", "workspace-map");
const PRIVATE_STAGE_ENV = "EFOUNDRY_PRIVATE_STAGING_ROOT";
const PRIVATE_STAGE_PREFIX = ".efoundry-build-";
const PRIVATE_STAGE_MARKER = ".epistemic-foundry-private-stage";
const PRIVATE_STAGE_MARKER_TEXT = "epistemic-foundry-private-stage-v1\n";

/** Exact source files the snapshot producer needs, in dependency order. */
const BUNDLED_FILES = Object.freeze([
  "inventory/workspace-inventory.mjs",
  "inventory/index.mjs",
  "ranking/baseline/baseline-centrality.mjs",
  "ranking/baseline/index.mjs",
  "ranking/query/query-ranking-common.mjs",
  "ranking/query/query-personalization.mjs",
  "ranking/query/risk-change-impact.mjs",
  "ranking/query/index.mjs",
  "snapshot/repository-scan.mjs",
  "snapshot/workspace-map-snapshot.mjs",
  "snapshot/index.mjs",
]);
const EXPECTED_FILES = new Set([...BUNDLED_FILES, "bundle-manifest.json"]);
const EXPECTED_DIRECTORIES = new Set();
for (const relative of BUNDLED_FILES) {
  const parts = relative.split("/");
  for (let depth = 1; depth < parts.length; depth += 1) {
    EXPECTED_DIRECTORIES.add(parts.slice(0, depth).join("/"));
  }
}

const sha256 = (text) => createHash("sha256").update(text, "utf8").digest("hex");

const lstatIfPresent = async (path) => {
  try {
    return await lstat(path);
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
};

const resolveTarget = async () => {
  const configured = process.env[PRIVATE_STAGE_ENV];
  if (!configured) return { payloadDir: FINAL_PAYLOAD_DIR, privateStage: false };

  const stageRoot = resolve(configured);
  if (
    dirname(stageRoot) !== PLUGIN_ROOT ||
    !basename(stageRoot).startsWith(PRIVATE_STAGE_PREFIX)
  ) {
    throw new Error(
      `${PRIVATE_STAGE_ENV} must name a private ${PRIVATE_STAGE_PREFIX}* sibling inside the plugin root`,
    );
  }
  const metadata = await lstatIfPresent(stageRoot);
  if (metadata === null || metadata.isSymbolicLink() || !metadata.isDirectory()) {
    throw new Error(`${PRIVATE_STAGE_ENV} must name an existing non-symlink directory`);
  }
  const markerPath = join(stageRoot, PRIVATE_STAGE_MARKER);
  const markerMetadata = await lstatIfPresent(markerPath);
  if (
    markerMetadata === null ||
    markerMetadata.isSymbolicLink() ||
    !markerMetadata.isFile() ||
    (await readFile(markerPath, "utf8")) !== PRIVATE_STAGE_MARKER_TEXT
  ) {
    throw new Error(`${PRIVATE_STAGE_ENV} does not carry the private staging marker`);
  }
  return {
    payloadDir: join(stageRoot, "dist", "workspace-map"),
    privateStage: true,
  };
};

const workspaceMapInventory = async (payloadDir, { allowAbsent = false } = {}) => {
  let rootMetadata;
  try {
    rootMetadata = await lstatIfPresent(payloadDir);
  } catch (error) {
    return { absent: false, mismatched: [`workspace-map: could not inspect output root: ${error.message}`] };
  }
  if (rootMetadata === null) {
    return {
      absent: true,
      mismatched: allowAbsent ? [] : ["workspace-map: output root is missing"],
    };
  }
  if (rootMetadata.isSymbolicLink()) {
    return { absent: false, mismatched: ["workspace-map: output root is a symlink"] };
  }
  if (!rootMetadata.isDirectory()) {
    return { absent: false, mismatched: ["workspace-map: output root is not a directory"] };
  }

  const mismatched = [];
  const observedFiles = new Set();
  const observedDirectories = new Set();
  const pending = [[payloadDir, ""]];
  while (pending.length > 0) {
    const [directory, prefix] = pending.pop();
    let entries;
    try {
      entries = (await readdir(directory, { withFileTypes: true })).sort((left, right) =>
        left.name.localeCompare(right.name),
      );
    } catch (error) {
      return {
        absent: false,
        mismatched: [`workspace-map: could not enumerate output tree: ${error.message}`],
      };
    }
    for (const entry of entries) {
      const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isSymbolicLink()) {
        mismatched.push(`${relative}: symlink is not allowed`);
      } else if (entry.isDirectory()) {
        if (!EXPECTED_DIRECTORIES.has(relative)) {
          mismatched.push(`${relative}: unexpected directory`);
        } else {
          observedDirectories.add(relative);
          pending.push([join(directory, entry.name), relative]);
        }
      } else if (entry.isFile()) {
        if (!EXPECTED_FILES.has(relative)) {
          mismatched.push(`${relative}: unexpected file`);
        } else {
          observedFiles.add(relative);
        }
      } else {
        mismatched.push(`${relative}: special entry is not allowed`);
      }
    }
  }

  for (const expected of [...EXPECTED_DIRECTORIES].sort()) {
    if (!observedDirectories.has(expected)) {
      mismatched.push(`${expected}: required directory is missing`);
    }
  }
  for (const expected of [...EXPECTED_FILES].sort()) {
    if (!observedFiles.has(expected)) {
      mismatched.push(`${expected}: required file is missing`);
    }
  }
  return { absent: false, mismatched };
};

const atomicWriteText = async (path, text) => {
  await mkdir(dirname(path), { recursive: true });
  const temporary = join(
    dirname(path),
    `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`,
  );
  try {
    await writeFile(temporary, text, { encoding: "utf8", flag: "wx" });
    await rename(temporary, path);
  } catch (error) {
    try {
      await unlink(temporary);
    } catch (cleanupError) {
      if (cleanupError.code !== "ENOENT") {
        error.message = `${error.message}; temporary cleanup also failed: ${cleanupError.message}`;
      }
    }
    throw error;
  }
};

const main = async () => {
  const checkOnly = process.argv.includes("--check");
  const preflightOnly = process.argv.includes("--preflight");
  const knownArguments = new Set(["--check", "--preflight"]);
  const unknownArguments = process.argv.slice(2).filter((argument) => !knownArguments.has(argument));
  if (unknownArguments.length > 0 || (checkOnly && preflightOnly)) {
    console.error(
      JSON.stringify(
        {
          status: "BUILD_REFUSED",
          mismatched: [
            unknownArguments.length > 0
              ? `unknown arguments: ${unknownArguments.join(", ")}`
              : "--check and --preflight are mutually exclusive",
          ],
        },
        null,
        2,
      ),
    );
    process.exitCode = 1;
    return;
  }

  let target;
  try {
    target = await resolveTarget();
  } catch (error) {
    console.error(JSON.stringify({ status: "BUILD_REFUSED", mismatched: [error.message] }, null, 2));
    process.exitCode = 1;
    return;
  }
  if (preflightOnly && target.privateStage) {
    console.error(
      JSON.stringify(
        { status: "BUILD_REFUSED", mismatched: ["preflight must inspect the final payload"] },
        null,
        2,
      ),
    );
    process.exitCode = 1;
    return;
  }

  let allowAbsent = target.privateStage;
  if (preflightOnly) {
    const parentMetadata = await lstatIfPresent(dirname(target.payloadDir));
    allowAbsent = parentMetadata === null;
  }
  const inventory = await workspaceMapInventory(target.payloadDir, { allowAbsent });
  if (inventory.mismatched.length > 0) {
    console.error(
      JSON.stringify(
        {
          status: checkOnly ? "DRIFTED" : "BUILD_REFUSED",
          mismatched: inventory.mismatched,
        },
        null,
        2,
      ),
    );
    process.exitCode = 1;
    return;
  }
  if (preflightOnly) {
    console.log(JSON.stringify({ status: inventory.absent ? "ABSENT" : "PREFLIGHT_OK" }));
    return;
  }

  const prepared = [];
  const manifest = {};
  try {
    for (const relative of BUNDLED_FILES) {
      const source = await readFile(join(SOURCE_DIR, relative), "utf8");
      manifest[relative] = `sha256:${sha256(source)}`;
      prepared.push({ relative, source });
    }
  } catch (error) {
    console.error(JSON.stringify({ status: "BUILD_REFUSED", mismatched: [error.message] }, null, 2));
    process.exitCode = 1;
    return;
  }

  const mismatched = [];
  for (const { relative, source } of prepared) {
    const destination = join(target.payloadDir, relative);
    if (checkOnly) {
      let bundled = null;
      try {
        bundled = await readFile(destination, "utf8");
      } catch {
        mismatched.push(`${relative}: missing from payload`);
        continue;
      }
      if (bundled !== source) mismatched.push(`${relative}: payload differs from source`);
      continue;
    }
    try {
      await atomicWriteText(destination, source);
    } catch (error) {
      console.error(
        JSON.stringify(
          { status: "BUILD_FAILED", mismatched: [`${relative}: ${error.message}`] },
          null,
          2,
        ),
      );
      process.exitCode = 1;
      return;
    }
  }

  const manifestPath = join(target.payloadDir, "bundle-manifest.json");
  const manifestText = `${JSON.stringify(
    { source: "packages/workspace-map/src", files: manifest },
    null,
    2,
  )}\n`;
  if (checkOnly) {
    let bundledManifest = null;
    try {
      bundledManifest = await readFile(manifestPath, "utf8");
    } catch {
      mismatched.push("bundle-manifest.json: missing from payload");
    }
    if (bundledManifest !== null && bundledManifest !== manifestText) {
      mismatched.push("bundle-manifest.json: payload differs from source");
    }
    if (mismatched.length > 0) {
      console.error(JSON.stringify({ status: "DRIFTED", mismatched }, null, 2));
      process.exitCode = 1;
      return;
    }
    console.log(JSON.stringify({ status: "CURRENT", file_count: BUNDLED_FILES.length }));
    return;
  }

  try {
    // The manifest is the subtree commit marker, so it is written last.
    await atomicWriteText(manifestPath, manifestText);
  } catch (error) {
    console.error(
      JSON.stringify(
        { status: "BUILD_FAILED", mismatched: [`bundle-manifest.json: ${error.message}`] },
        null,
        2,
      ),
    );
    process.exitCode = 1;
    return;
  }
  console.log(JSON.stringify({ status: "BUNDLED", file_count: BUNDLED_FILES.length }));
};

await main();
