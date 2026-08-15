import fs from "node:fs";
import path from "node:path";
import {
  FAILURE,
  STATUS,
  LifecycleError,
  boundedJson,
  fail,
} from "./core.mjs";
import {
  exactMarketplaceEntry,
  exactPluginEntry,
  parseSelector,
} from "./host.mjs";
import { sameAbsolutePath } from "./contracts.mjs";

function readOrdinaryJson(file, maxBytes, label) {
  const before = fs.lstatSync(file, { bigint: true });
  if (before.isSymbolicLink() || !before.isFile() || before.nlink !== 1n || before.size > BigInt(maxBytes)) {
    fail(FAILURE.HOST_UNSUPPORTED, `${label} is not safely readable`, STATUS.UNSUPPORTED);
  }
  const fd = fs.openSync(file, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
  try {
    const opened = fs.fstatSync(fd, { bigint: true });
    if (opened.dev !== before.dev || opened.ino !== before.ino) {
      fail(FAILURE.HOST_UNSUPPORTED, `${label} changed before read`, STATUS.UNSUPPORTED);
    }
    const text = fs.readFileSync(fd, { encoding: "utf8" });
    const after = fs.fstatSync(fd, { bigint: true });
    if (
      after.dev !== opened.dev ||
      after.ino !== opened.ino ||
      after.size !== opened.size ||
      after.mtimeNs !== opened.mtimeNs ||
      after.ctimeNs !== opened.ctimeNs
    ) fail(FAILURE.HOST_UNSUPPORTED, `${label} changed during read`, STATUS.UNSUPPORTED);
    return boundedJson(JSON.parse(text), label, {
      bytes: maxBytes,
      depth: 16,
      nodes: 4096,
      string: 256 * 1024,
    });
  } catch (cause) {
    if (cause instanceof LifecycleError) throw cause;
    fail(FAILURE.HOST_UNSUPPORTED, `${label} is invalid`, STATUS.UNSUPPORTED);
  } finally {
    fs.closeSync(fd);
  }
}

export function createHostEffects({
  store,
  host,
  config,
  effectId,
  checkDeadline,
  revalidatePrivateRoots,
  inspectTree,
  verifyPackageRecord,
}) {
  const readHostEffect = (operationId, kind, args, intent, label) => {
    checkDeadline();
    revalidatePrivateRoots();
    store.ensureDiagnosticCapacity(1);
    const id = effectId();
    store.intentEffect({
      operationId,
      effectId: id,
      kind,
      intent: { ...intent, command_capability_id: host.commandCapabilityId, args },
    });
    const result = args.includes("--json") ? host.json(args, label) : host.invoke(args);
    store.resolveEffect({
      effectId: id,
      resolution: { status: result.ok ? "APPLIED" : "FAILED" },
      diagnostic: result.diagnostic,
    });
    if (!result.ok) fail(FAILURE.HOST_COMMAND_FAILED, `${label} failed`);
    revalidatePrivateRoots();
    checkDeadline();
    return result;
  };

  const beginHostMutation = (operationId, kind, args, intent, label, mutationGuard = null) => {
    checkDeadline();
    revalidatePrivateRoots();
    const conditionalMutation = mutationGuard === null ? null : host.requireConditionalMutation(mutationGuard);
    store.ensureDiagnosticCapacity(2);
    const id = effectId();
    store.intentEffect({
      operationId,
      effectId: id,
      kind,
      intent: {
        ...intent,
        command_capability_id: host.commandCapabilityId,
        ...(conditionalMutation === null
          ? {}
          : { conditional_mutation_capability_id: conditionalMutation.capability_id }),
        args,
      },
    });
    const result = host.invoke(args, mutationGuard);
    store.attachEffectDiagnostic({ effectId: id, diagnostic: result.diagnostic });
    if (!result.ok) fail(FAILURE.HOST_COMMAND_FAILED, `${label} failed`);
    revalidatePrivateRoots();
    checkDeadline();
    return { effectId: id };
  };

  const mutationReadback = (effect, args, label) => {
    checkDeadline();
    revalidatePrivateRoots();
    const result = host.invoke(args);
    store.attachEffectDiagnostic({ effectId: effect.effectId, diagnostic: result.diagnostic });
    if (!result.ok) fail(FAILURE.HOST_COMMAND_FAILED, `${label} failed`);
    revalidatePrivateRoots();
    let payload;
    try {
      payload = boundedJson(JSON.parse(result.stdout), label, {
        bytes: config.maxOutputBytes,
        depth: 32,
        nodes: 100_000,
        string: 256 * 1024,
      });
    } catch (cause) {
      if (cause instanceof LifecycleError) throw cause;
      fail(FAILURE.HOST_OUTPUT_INVALID, `${label} did not return bounded JSON`);
    }
    checkDeadline();
    return { payload, diagnostic: result.diagnostic };
  };

  const listPlugins = (operationId) => readHostEffect(
    operationId,
    "HOST_PLUGIN_LIST",
    ["plugin", "list", "--json"],
    { mutation: false },
    "plugin list",
  ).payload;

  const listMarketplaces = (operationId) => readHostEffect(
    operationId,
    "HOST_MARKETPLACE_LIST",
    ["plugin", "marketplace", "list", "--json"],
    { mutation: false },
    "marketplace list",
  ).payload;

  const exactInstalled = (operationId, selector, expectedHash = null) => {
    const found = exactPluginEntry(listPlugins(operationId), selector, { requireRoot: true });
    if (found === null) return null;
    if (!found.enabled) fail(FAILURE.IDENTITY_MISMATCH, "exact selector is disabled");
    const parsed = parseSelector(selector);
    const identity = inspectTree(found.root, { pluginName: parsed.pluginName });
    if (expectedHash !== null && identity.tree_hash !== expectedHash) {
      fail(FAILURE.IDENTITY_MISMATCH, "exact selector package hash differs");
    }
    return { ...found, identity };
  };

  const exactOwnedInstalled = (operationId, selector, expectedPackage) => {
    const found = exactPluginEntry(listPlugins(operationId), selector, { requireRoot: true });
    if (found === null) return null;
    const identity = inspectTree(found.root, { pluginName: expectedPackage.plugin_name });
    if (identity.tree_hash !== expectedPackage.package_hash) {
      fail(FAILURE.HOST_AMBIGUOUS, "lifecycle selector is occupied by a different package");
    }
    return { ...found, identity };
  };

  const addMarketplace = (operationId, marketplace) => {
    const packageRecord = verifyPackageRecord(store.packageRecord(marketplace.package_hash));
    if (packageRecord === null) fail(FAILURE.STATE_CORRUPT, "marketplace package record is missing");
    const payloadRoot = path.join(marketplace.root, "plugins", packageRecord.plugin_name);
    const marketplaceBefore = inspectTree(marketplace.root);
    const payload = inspectTree(payloadRoot, { pluginName: packageRecord.plugin_name });
    if (payload.tree_hash !== packageRecord.package_hash) fail(FAILURE.IDENTITY_MISMATCH, "marketplace payload drifted");
    const prior = exactMarketplaceEntry(listMarketplaces(operationId), marketplace.registration_name);
    if (prior !== null) {
      if (prior.root === null || !sameAbsolutePath(prior.root, marketplace.root)) {
        fail(FAILURE.HOST_AMBIGUOUS, "marketplace name is occupied by an unrelated root");
      }
      store.setMarketplaceRegistered(marketplace.marketplace_id, true);
      return;
    }
    const marketplaceAtDispatch = inspectTree(marketplace.root);
    if (marketplaceAtDispatch.tree_hash !== marketplaceBefore.tree_hash) {
      fail(FAILURE.IDENTITY_MISMATCH, "marketplace changed before host registration");
    }
    const effect = beginHostMutation(
      operationId,
      "HOST_MARKETPLACE_ADD",
      ["plugin", "marketplace", "add", marketplace.root, "--json"],
      {
        marketplace_id: marketplace.marketplace_id,
        name: marketplace.registration_name,
        root: marketplace.root,
        expected_marketplace_hash: marketplaceBefore.tree_hash,
        expected_package_hash: packageRecord.package_hash,
      },
      "marketplace add",
    );
    const readback = mutationReadback(effect, ["plugin", "marketplace", "list", "--json"], "marketplace add readback");
    const observed = exactMarketplaceEntry(readback.payload, marketplace.registration_name);
    if (observed === null) {
      store.resolveEffect({ effectId: effect.effectId, resolution: { status: "NOT_APPLIED" }, diagnostic: readback.diagnostic });
      fail(FAILURE.HOST_OUTPUT_INVALID, "added marketplace is absent from exact host list");
    }
    if (observed.root === null || !sameAbsolutePath(observed.root, marketplace.root)) {
      store.resolveEffect({ effectId: effect.effectId, resolution: { status: "MISMATCH" }, diagnostic: readback.diagnostic });
      fail(FAILURE.HOST_AMBIGUOUS, "added marketplace root is not uniquely lifecycle-owned");
    }
    const payloadAfter = inspectTree(payloadRoot, { pluginName: packageRecord.plugin_name });
    const marketplaceAfter = inspectTree(marketplace.root);
    if (
      payloadAfter.tree_hash !== packageRecord.package_hash ||
      marketplaceAfter.tree_hash !== marketplaceBefore.tree_hash
    ) {
      store.resolveEffect({ effectId: effect.effectId, resolution: { status: "MISMATCH" }, diagnostic: readback.diagnostic });
      fail(FAILURE.IDENTITY_MISMATCH, "marketplace payload changed during host registration");
    }
    store.resolveEffect({ effectId: effect.effectId, resolution: { status: "APPLIED" }, diagnostic: readback.diagnostic });
  };

  const removeMarketplace = (operationId, marketplace) => {
    const packageRecord = verifyPackageRecord(store.packageRecord(marketplace.package_hash));
    if (packageRecord === null) fail(FAILURE.STATE_CORRUPT, "marketplace package record is missing");
    const marketplaceBefore = inspectTree(marketplace.root);
    const prior = exactMarketplaceEntry(listMarketplaces(operationId), marketplace.registration_name);
    if (prior === null) {
      store.setMarketplaceRegistered(marketplace.marketplace_id, false);
      return;
    }
    if (prior.root === null || !sameAbsolutePath(prior.root, marketplace.root)) {
      fail(FAILURE.HOST_AMBIGUOUS, "marketplace removal would affect an unrelated root");
    }
    const payload = inspectTree(path.join(marketplace.root, "plugins", packageRecord.plugin_name), {
      pluginName: packageRecord.plugin_name,
    });
    if (payload.tree_hash !== packageRecord.package_hash) fail(FAILURE.IDENTITY_MISMATCH, "marketplace payload drifted");
    const marketplaceAtDispatch = inspectTree(marketplace.root);
    if (marketplaceAtDispatch.tree_hash !== marketplaceBefore.tree_hash) {
      fail(FAILURE.IDENTITY_MISMATCH, "marketplace changed before host removal");
    }
    const effect = beginHostMutation(
      operationId,
      "HOST_MARKETPLACE_REMOVE",
      ["plugin", "marketplace", "remove", marketplace.registration_name, "--json"],
      {
        marketplace_id: marketplace.marketplace_id,
        name: marketplace.registration_name,
        root: marketplace.root,
        expected_marketplace_hash: marketplaceBefore.tree_hash,
        expected_package_hash: packageRecord.package_hash,
      },
      "marketplace remove",
      {
        kind: "MARKETPLACE_REMOVE",
        identity: marketplace.registration_name,
        expected_root: marketplace.root,
        expected_tree_hash: marketplaceBefore.tree_hash,
      },
    );
    const readback = mutationReadback(effect, ["plugin", "marketplace", "list", "--json"], "marketplace remove readback");
    if (exactMarketplaceEntry(readback.payload, marketplace.registration_name) !== null) {
      store.resolveEffect({ effectId: effect.effectId, resolution: { status: "MISMATCH" }, diagnostic: readback.diagnostic });
      fail(FAILURE.HOST_AMBIGUOUS, "removed marketplace remains in exact host list");
    }
    const marketplaceAfter = inspectTree(marketplace.root);
    if (marketplaceAfter.tree_hash !== marketplaceBefore.tree_hash) {
      store.resolveEffect({ effectId: effect.effectId, resolution: { status: "MISMATCH" }, diagnostic: readback.diagnostic });
      fail(FAILURE.IDENTITY_MISMATCH, "marketplace payload changed during host removal");
    }
    store.resolveEffect({ effectId: effect.effectId, resolution: { status: "APPLIED" }, diagnostic: readback.diagnostic });
  };

  const removePlugin = (operationId, selector, expectedPackage) => {
    const packageRecord = verifyPackageRecord(expectedPackage);
    if (packageRecord === null) fail(FAILURE.STATE_CORRUPT, "plugin removal package record is missing");
    const prior = exactOwnedInstalled(operationId, selector, packageRecord);
    if (prior === null) fail(FAILURE.IDENTITY_MISMATCH, "exact selector disappeared before removal");
    const effect = beginHostMutation(
      operationId,
      "HOST_PLUGIN_REMOVE",
      ["plugin", "remove", selector, "--json"],
      {
        selector,
        expected_package_hash: packageRecord.package_hash,
        expected_root: prior.root,
      },
      "plugin remove",
      {
        kind: "PLUGIN_REMOVE",
        identity: selector,
        expected_root: prior.root,
        expected_tree_hash: packageRecord.package_hash,
      },
    );
    const readback = mutationReadback(effect, ["plugin", "list", "--json"], "plugin remove readback");
    const observed = exactPluginEntry(readback.payload, selector, { requireRoot: true });
    if (observed !== null) {
      const identity = inspectTree(observed.root, { pluginName: packageRecord.plugin_name });
      const status =
        identity.tree_hash === packageRecord.package_hash && sameAbsolutePath(observed.root, prior.root)
          ? "NOT_APPLIED"
          : "MISMATCH";
      store.resolveEffect({ effectId: effect.effectId, resolution: { status }, diagnostic: readback.diagnostic });
      fail(FAILURE.HOST_AMBIGUOUS, "removed selector remains installed");
    }
    store.resolveEffect({ effectId: effect.effectId, resolution: { status: "APPLIED" }, diagnostic: readback.diagnostic });
  };

  const addPlugin = (operationId, selector, expectedPackage) => {
    const preserved = inspectTree(expectedPackage.preserved_root, { pluginName: expectedPackage.plugin_name });
    if (preserved.tree_hash !== expectedPackage.package_hash) fail(FAILURE.STATE_CORRUPT, "preserved package drifted");
    if (exactPluginEntry(listPlugins(operationId), selector) !== null) {
      fail(FAILURE.HOST_AMBIGUOUS, "candidate selector is already occupied");
    }
    const effect = beginHostMutation(
      operationId,
      "HOST_PLUGIN_ADD",
      ["plugin", "add", selector, "--json"],
      { selector, expected_package_hash: expectedPackage.package_hash },
      "plugin add",
    );
    const readback = mutationReadback(effect, ["plugin", "list", "--json"], "plugin add readback");
    const found = exactPluginEntry(readback.payload, selector, { requireRoot: true });
    if (found === null) {
      store.resolveEffect({ effectId: effect.effectId, resolution: { status: "NOT_APPLIED" }, diagnostic: readback.diagnostic });
      fail(FAILURE.IDENTITY_MISMATCH, "added exact selector is absent or disabled");
    }
    if (!found.enabled) {
      store.resolveEffect({ effectId: effect.effectId, resolution: { status: "MISMATCH" }, diagnostic: readback.diagnostic });
      fail(FAILURE.IDENTITY_MISMATCH, "added exact selector is absent or disabled");
    }
    const parsed = parseSelector(selector);
    const installed = inspectTree(found.root, { pluginName: parsed.pluginName });
    if (installed.tree_hash !== expectedPackage.package_hash) {
      store.resolveEffect({
        effectId: effect.effectId,
        resolution: { status: "MISMATCH", observed_package_hash: installed.tree_hash },
        diagnostic: readback.diagnostic,
      });
      fail(FAILURE.IDENTITY_MISMATCH, "added exact selector package hash differs");
    }
    const preservedAfter = inspectTree(expectedPackage.preserved_root, { pluginName: expectedPackage.plugin_name });
    if (preservedAfter.tree_hash !== expectedPackage.package_hash) {
      store.resolveEffect({ effectId: effect.effectId, resolution: { status: "MISMATCH" }, diagnostic: readback.diagnostic });
      fail(FAILURE.STATE_CORRUPT, "preserved package changed during plugin add");
    }
    store.resolveEffect({ effectId: effect.effectId, resolution: { status: "APPLIED" }, diagnostic: readback.diagnostic });
    return { ...found, identity: installed };
  };

  const verifyOriginalMarketplaceSource = (operationId, selector, expectedPackage) => {
    const parsed = parseSelector(selector);
    const marketplace = exactMarketplaceEntry(listMarketplaces(operationId), parsed.marketplaceName);
    if (marketplace === null || marketplace.root === null) {
      fail(FAILURE.HOST_UNSUPPORTED, "original marketplace source root is not observable", STATUS.UNSUPPORTED);
    }
    const descriptorPath = path.join(marketplace.root, ".agents", "plugins", "marketplace.json");
    const descriptor = readOrdinaryJson(descriptorPath, 1024 * 1024, "original marketplace descriptor");
    if (descriptor.name !== parsed.marketplaceName) {
      fail(FAILURE.HOST_UNSUPPORTED, "original marketplace descriptor identity differs", STATUS.UNSUPPORTED);
    }
    const matches = Array.isArray(descriptor.plugins)
      ? descriptor.plugins.filter((item) => item?.name === parsed.pluginName)
      : [];
    if (matches.length !== 1 || matches[0]?.source?.source !== "local") {
      fail(FAILURE.HOST_UNSUPPORTED, "original exact plugin source is not one local entry", STATUS.UNSUPPORTED);
    }
    const relative = matches[0].source.path;
    if (typeof relative !== "string" || relative.includes("\\") || path.isAbsolute(relative)) {
      fail(FAILURE.HOST_UNSUPPORTED, "original marketplace source path is not canonical local data", STATUS.UNSUPPORTED);
    }
    const sourceRoot = path.resolve(marketplace.root, relative);
    const escaped = path.relative(path.resolve(marketplace.root), sourceRoot);
    if (escaped === "" || escaped === ".." || escaped.startsWith(`..${path.sep}`) || path.isAbsolute(escaped)) {
      fail(FAILURE.UNSAFE_PATH, "original marketplace source escaped its root");
    }
    const observed = inspectTree(sourceRoot, { pluginName: parsed.pluginName });
    if (observed.tree_hash !== expectedPackage.package_hash) {
      fail(FAILURE.IDENTITY_MISMATCH, "original marketplace source drifted from the captured previous package");
    }
  };

  return Object.freeze({
    readHostEffect,
    mutationReadback,
    listPlugins,
    listMarketplaces,
    exactInstalled,
    exactOwnedInstalled,
    addMarketplace,
    removeMarketplace,
    removePlugin,
    addPlugin,
    verifyOriginalMarketplaceSource,
    requireDestructiveHostCapability: host.requireConditionalMutationCapability,
  });
}
