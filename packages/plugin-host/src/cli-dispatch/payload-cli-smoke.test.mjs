import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../..",
);
const dispatcherSource = path.join(
  repositoryRoot,
  "plugins",
  "epistemic-foundry",
  "bin",
  "efoundry.mjs",
);

const fixtureCli = `
import fs from "node:fs";

const args = process.argv.slice(2);
const exitFlag = args.indexOf("--fixture-exit-code");
const exitCode = exitFlag === -1 ? 0 : Number(args[exitFlag + 1]);
const stdin = fs.readFileSync(0, "utf8");

process.stdout.write(JSON.stringify({
  args,
  cwd: process.cwd(),
  fixture_url: import.meta.url,
  marker: process.env.EFOUNDRY_G02_MARKER,
  path_value: process.env.PATH,
  stdin,
}) + "\\n");
process.stderr.write("fixture-stderr\\n");
process.exitCode = exitCode;
`;

function makePayload(t, { includeTarget = true } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "efoundry G02 한글 "));
  const pluginRoot = path.join(root, "installed plugin");
  const binRoot = path.join(pluginRoot, "bin");
  const distRoot = path.join(pluginRoot, "dist");
  const cwd = path.join(root, "workspace with spaces", "연구");
  fs.mkdirSync(binRoot, { recursive: true });
  fs.mkdirSync(cwd, { recursive: true });
  fs.copyFileSync(dispatcherSource, path.join(binRoot, "efoundry.mjs"));
  if (includeTarget) {
    fs.mkdirSync(distRoot, { recursive: true });
    fs.writeFileSync(path.join(distRoot, "cli.mjs"), fixtureCli, "utf8");
  }
  t.after(() => fs.rmSync(root, { force: true, recursive: true }));
  return {
    cwd,
    dispatcher: path.join(binRoot, "efoundry.mjs"),
    pluginRoot,
  };
}

test("payload_cli_smoke: absolute plugin entry works without an efoundry PATH alias", (t) => {
  const payload = makePayload(t);
  const args = [
    "status",
    "--label",
    "value with spaces",
    "검증",
    "--fixture-exit-code",
    "23",
  ];
  const result = spawnSync(process.execPath, [payload.dispatcher, ...args], {
    cwd: payload.cwd,
    encoding: "utf8",
    env: {
      ...process.env,
      EFOUNDRY_G02_MARKER: "marker-한글",
      PATH: "",
    },
    input: "stdin-through-dispatcher\n",
    windowsHide: true,
  });

  assert.equal(result.error, undefined);
  assert.equal(result.signal, null);
  assert.equal(result.status, 23);
  assert.equal(result.stderr, "fixture-stderr\n");
  const observed = JSON.parse(result.stdout);
  assert.deepEqual(observed.args, args);
  assert.equal(observed.cwd, payload.cwd);
  assert.equal(observed.marker, "marker-한글");
  assert.equal(observed.path_value, "");
  assert.equal(observed.stdin, "stdin-through-dispatcher\n");
  assert.ok(
    fileURLToPath(observed.fixture_url).startsWith(payload.pluginRoot + path.sep),
    `payload target escaped the installed plugin: ${observed.fixture_url}`,
  );
});

test("payload_cli_smoke: a missing payload target fails instead of using a repo or PATH fallback", (t) => {
  const payload = makePayload(t, { includeTarget: false });
  const result = spawnSync(process.execPath, [payload.dispatcher, "status"], {
    cwd: payload.cwd,
    encoding: "utf8",
    env: { ...process.env, PATH: "" },
    windowsHide: true,
  });

  assert.equal(result.error, undefined);
  assert.notEqual(result.status, 0);
  assert.equal(result.stdout, "");
  assert.match(result.stderr, /dist[\\/]cli\.mjs/u);
  assert.doesNotMatch(result.stderr, /src[\\/]epistemic_foundry/u);
});
