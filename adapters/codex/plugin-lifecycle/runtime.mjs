import { randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {
  FAILURE,
  LIMITS,
  STATUS,
  LifecycleError,
  boundedJson,
  canonicalJson,
  errorOutcome,
  exactFields,
  fail,
  hashJson,
  isPlainObject,
  makeResult,
  strictVersion,
} from "./core.mjs";
import {
  createHostClient,
  exactMarketplaceEntry,
  exactPluginEntry,
  parseHostVersionText,
  parseSelector,
  resolveConfiguration,
} from "./host.mjs";
import { createSagaStore } from "./store.mjs";
import {
  callCapabilityPort,
  dataSnapshotPortReady,
  marketplaceDocument,
  migrationPortReady,
  parseMigrationPlan,
  publicPackage,
  qualifyComposition,
  quiescencePortReady,
  sameAbsolutePath,
  unsupportedCompositionPort,
  validateMigrationReceipt,
} from "./contracts.mjs";
import { createResourceManager } from "./resource-manager.mjs";
import { createDataSnapshotManager } from "./data-snapshots.mjs";
import { createHostEffects } from "./host-effects.mjs";
import { createQuiescenceManager } from "./quiescence.mjs";
import {
  copyExactTree as copyExactTreeRaw,
  durableFsyncDirectory,
  durablePublishDirectory,
  durableQuarantineDirectory,
  durableRemoveQuarantine,
  durableSyncTree,
  identityFromRecord,
  inspectTree as inspectTreeRaw,
  preserveTree as preserveTreeRaw,
  reconcileOwnedStaging,
  treeRecord,
} from "./tree.mjs";

const SUCCESS = Object.freeze({
  probeHost: "Host capabilities reported.",
  capture: "Installed package captured.",
  prepare: "Candidate package prepared.",
  activate: "Prepared package activated.",
  verify: "Active package checks passed.",
  rollback: "Previous package restored.",
  uninstall: "Lifecycle selectors were removed and plugin data was preserved.",
  cancel: "Preparation was cancelled before host effects.",
  finalize: "Terminal preparation history was finalized for bounded cleanup.",
  cleanup: "Eligible lifecycle resources were cleaned up.",
  close: "Lifecycle port was closed.",
});

export function buildLifecyclePort(options, contractPath) {
  const config = resolveConfiguration(options);
  let composition;
  try {
    composition = qualifyComposition(config);
  } catch (cause) {
    return unsupportedCompositionPort(cause);
  }
  let store;
  try {
    store = createSagaStore({ lifecycleRoot: config.lifecycleRoot, contractPath });
  } catch (cause) {
    return unsupportedCompositionPort(cause);
  }
  const host = createHostClient(config, composition.capabilityIds);
  let startupReconciliation = null;
  let activeDeadline = null;
  let activeOwnerEpoch = null;
  let closed = false;

  const revalidateCompositionCapabilities = () => {
    const observed = {
      privateRoot: config.privateRootPort?.capability_id ?? null,
      dataSnapshot: config.dataSnapshotPort?.capability_id ?? null,
      quiescence: config.quiescencePort?.capability_id ?? null,
      command: config.commandPortInjected ? config.commandPort.capability_id ?? null : null,
      conditionalMutation: config.commandPort.conditional_mutation_capability_id ?? null,
      migration: config.migrationPort?.capability_id ?? null,
      trust: config.trustPort?.capability_id ?? null,
      verification: config.verificationPort?.capability_id ?? null,
    };
    if (canonicalJson(observed) !== canonicalJson(composition.capabilityIds)) {
      fail(FAILURE.HOST_UNSUPPORTED, "runtime capability composition identity changed", STATUS.UNSUPPORTED);
    }
  };

  const operationLimits = () => ({ ...LIMITS, deadlineMs: activeDeadline });
  const inspectTree = (root, options = {}) =>
    inspectTreeRaw(root, { ...options, limits: { ...(options.limits ?? LIMITS), deadlineMs: activeDeadline } });
  const copyExactTree = (sourceRoot, destinationRoot, identity) => {
    revalidatePrivateRoots();
    const copied = copyExactTreeRaw(sourceRoot, destinationRoot, identity, operationLimits());
    revalidatePrivateRoots();
    return copied;
  };
  const preserveTree = (value) => {
    revalidatePrivateRoots();
    const preserved = preserveTreeRaw({ ...value, limits: operationLimits() });
    revalidatePrivateRoots();
    return preserved;
  };
  const checkDeadline = () => {
    if (activeDeadline !== null && Date.now() > activeDeadline) {
      fail(FAILURE.RESOURCE_LIMIT, "lifecycle operation deadline exceeded");
    }
  };

  const revalidatePrivateRoots = () => {
    checkDeadline();
    revalidateCompositionCapabilities();
    if (activeOwnerEpoch === null) fail(FAILURE.CONCURRENT_OPERATION, "private roots require lifecycle ownership", STATUS.BLOCKED);
    const raw = callCapabilityPort(
      config.privateRootPort,
      "revalidate",
      {
        lifecycle_root: config.lifecycleRoot,
        roots_hash: composition.privateRoot.roots_hash,
        capability_id: composition.privateRoot.capability_id,
        owner_epoch: activeOwnerEpoch,
      },
      "private root",
    );
    exactFields(
      raw,
      ["status", "lifecycle_root", "roots_hash", "capability_id", "owner_epoch", "receipt_hash"],
      "private root revalidation",
    );
    if (
      raw.status !== "PROTECTED_LOCAL" ||
      raw.lifecycle_root !== config.lifecycleRoot ||
      raw.roots_hash !== composition.privateRoot.roots_hash ||
      raw.capability_id !== composition.privateRoot.capability_id ||
      raw.owner_epoch !== activeOwnerEpoch ||
      raw.receipt_hash !== hashJson("PLUGIN_LIFECYCLE_V3_PRIVATE_ROOT_REVALIDATION", {
        status: raw.status,
        lifecycle_root: raw.lifecycle_root,
        roots_hash: raw.roots_hash,
        capability_id: raw.capability_id,
        owner_epoch: raw.owner_epoch,
      })
    ) fail(FAILURE.HOST_UNSUPPORTED, "private root protection was not revalidated", STATUS.UNSUPPORTED);
    checkDeadline();
  };

  const activeHash = () => store.projection().active_package_hash;
  const opId = () => `op_${randomUUID()}`;
  const effectId = () => `eff_${randomUUID()}`;
  const pathsOverlap = (left, right) => {
    const a = path.resolve(left).normalize("NFC");
    const b = path.resolve(right).normalize("NFC");
    const normalize = (value) => process.platform === "win32" || process.platform === "darwin"
      ? value.toLowerCase()
      : value;
    const x = normalize(a);
    const y = normalize(b);
    return x === y || x.startsWith(`${y}${path.sep}`) || y.startsWith(`${x}${path.sep}`);
  };
  const uuidFromHash = (value) => {
    const hex = value.slice(7, 39).split("");
    if (hex.length !== 32 || hex.some((item) => !/[0-9a-f]/u.test(item))) {
      fail(FAILURE.STATE_CORRUPT, "deterministic lifecycle identity hash is invalid");
    }
    hex[12] = "4";
    hex[16] = "8";
    const joined = hex.join("");
    return `${joined.slice(0, 8)}-${joined.slice(8, 12)}-${joined.slice(12, 16)}-${joined.slice(16, 20)}-${joined.slice(20)}`;
  };
  const descriptorText = (value, max = 257) => typeof value === "string" && value.length <= max ? value : null;
  const requirePreparedId = (value) => {
    if (
      typeof value !== "string" ||
      !/^prep_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u.test(value)
    ) fail(FAILURE.INVALID_INPUT, "prepared id is invalid");
    return value;
  };
  const verifyPackageRecord = (record) => {
    if (record === null) fail(FAILURE.STATE_CORRUPT, "package record is missing");
    const observed = inspectTree(record.preserved_root, { pluginName: record.plugin_name });
    if (
      observed.tree_hash !== record.package_hash ||
      observed.plugin_version !== record.plugin_version ||
      observed.manifest_hash !== record.manifest_hash ||
      observed.has_hooks !== (record.has_hooks === 1 || record.has_hooks === true) ||
      observed.hook_subject_hash !== record.hook_subject_hash ||
      observed.entry_count !== record.entry_count ||
      observed.file_count !== record.file_count ||
      observed.byte_size !== record.byte_size ||
      observed.inventory_bytes !== record.inventory_bytes ||
      canonicalJson(observed.inventory) !== record.inventory_json
    ) fail(FAILURE.STATE_CORRUPT, "preserved package differs from its exact database row");
    return record;
  };
  const packageRecord = (packageHash) => {
    const record = store.packageRecord(packageHash);
    return record === null ? null : verifyPackageRecord(record);
  };
  const { applyResourceDisposal, disposeOwnedResource } = createResourceManager({
    store,
    inspectTree,
    checkDeadline,
    revalidatePrivateRoots,
    effectId,
    verifyPackageRecord,
    privateRootCapabilityId: composition.capabilityIds.privateRoot,
    durableFsyncDirectory,
    durableQuarantineDirectory: (sourceRoot, quarantineRoot, expectedTreeHash) =>
      durableQuarantineDirectory(sourceRoot, quarantineRoot, expectedTreeHash, operationLimits()),
    durableRemoveQuarantine: (quarantineRoot, expectedTreeHash) =>
      durableRemoveQuarantine(quarantineRoot, expectedTreeHash, operationLimits()),
  });

  const finishFailure = (operationId, method, error, context = {}, projectionPatch = {}) => {
    const outcome = errorOutcome(error, context);
    const recordsTrustBoundary = [
      FAILURE.TRUST_REQUIRED,
      FAILURE.TRUST_DECLINED,
      FAILURE.TRUST_UNAVAILABLE,
    ].includes(outcome.code);
    try {
      store.finishOperation({
        operationId,
        outcome,
        projectionPatch,
        preparationPatch:
          !recordsTrustBoundary ||
          context.prepared_id === undefined ||
          store.preparation(context.prepared_id) === null
            ? null
            : {
                prepared_id: context.prepared_id,
                patch: { status: outcome.status, updated_at: new Date().toISOString() },
              },
      });
    } catch {
      return makeResult(method, { ...outcome, code: FAILURE.IO_FAILURE }, null);
    }
    return makeResult(method, outcome, activeHash());
  };

  const {
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
    requireDestructiveHostCapability,
  } = createHostEffects({
    store,
    host,
    config,
    effectId,
    checkDeadline,
    revalidatePrivateRoots,
    inspectTree,
    verifyPackageRecord,
  });
  const createMarketplace = (operationId, packageRecord, purpose, allocation) => {
    revalidatePrivateRoots();
    const identity = identityFromRecord(packageRecord);
    const { marketplaceId, registrationName, selector } = allocation;
    if (
      !/^ef-lifecycle-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}$/u.test(marketplaceId) ||
      registrationName !== marketplaceId ||
      parseSelector(selector).pluginName !== packageRecord.plugin_name ||
      parseSelector(selector).marketplaceName !== registrationName
    ) fail(FAILURE.STATE_CORRUPT, "preallocated marketplace identity is invalid");
    const finalRoot = path.join(store.roots.marketplaces, marketplaceId);
    const verifyMarketplaceRoot = () => {
      inspectTree(finalRoot);
      if (
        canonicalJson(fs.readdirSync(finalRoot).sort()) !== canonicalJson([".agents", "plugins"]) ||
        canonicalJson(fs.readdirSync(path.join(finalRoot, ".agents")).sort()) !== canonicalJson(["plugins"]) ||
        canonicalJson(fs.readdirSync(path.join(finalRoot, ".agents", "plugins")).sort()) !==
          canonicalJson(["marketplace.json"]) ||
        canonicalJson(fs.readdirSync(path.join(finalRoot, "plugins")).sort()) !==
          canonicalJson([packageRecord.plugin_name])
      ) fail(FAILURE.STATE_CORRUPT, "owned marketplace layout is not closed");
      const payload = inspectTree(path.join(finalRoot, "plugins", packageRecord.plugin_name), {
        pluginName: packageRecord.plugin_name,
      });
      if (payload.tree_hash !== packageRecord.package_hash) {
        fail(FAILURE.STATE_CORRUPT, "owned marketplace payload drifted");
      }
      let document;
      try {
        document = JSON.parse(fs.readFileSync(path.join(finalRoot, ".agents", "plugins", "marketplace.json"), "utf8"));
      } catch {
        fail(FAILURE.STATE_CORRUPT, "owned marketplace descriptor is invalid");
      }
      if (canonicalJson(document) !== canonicalJson(marketplaceDocument(registrationName, packageRecord.plugin_name))) {
        fail(FAILURE.STATE_CORRUPT, "owned marketplace descriptor drifted");
      }
    };
    const existing = store.marketplace(marketplaceId);
    if (existing !== null) {
      if (
        existing.registration_name !== registrationName ||
        existing.selector !== selector ||
        existing.package_hash !== packageRecord.package_hash ||
        existing.purpose !== purpose ||
        !sameAbsolutePath(existing.root, finalRoot)
      ) fail(FAILURE.STATE_CORRUPT, "preallocated marketplace record collision");
      verifyMarketplaceRoot();
      durableSyncTree(finalRoot, operationLimits());
      return existing;
    }
    store.ensureMarketplaceCapacity(packageRecord.package_hash, marketplaceId);
    const stageRoot = path.join(store.roots.staging, `stage-${operationId}-marketplace`);
    if (!fs.existsSync(finalRoot)) {
      if (fs.existsSync(stageRoot)) fail(FAILURE.STATE_CORRUPT, "marketplace staging root collision");
      fs.mkdirSync(stageRoot, { recursive: false });
      try {
        const pluginParent = path.join(stageRoot, "plugins");
        fs.mkdirSync(pluginParent, { recursive: false });
        copyExactTree(packageRecord.preserved_root, path.join(pluginParent, packageRecord.plugin_name), identity);
        const metadata = path.join(stageRoot, ".agents", "plugins");
        fs.mkdirSync(metadata, { recursive: true });
        fs.writeFileSync(
          path.join(metadata, "marketplace.json"),
          `${JSON.stringify(marketplaceDocument(registrationName, packageRecord.plugin_name), null, 2)}\n`,
          { encoding: "utf8", flag: "wx", mode: 0o600 },
        );
        revalidatePrivateRoots();
        durablePublishDirectory(stageRoot, finalRoot, operationLimits());
        revalidatePrivateRoots();
      } catch (cause) {
        if (fs.existsSync(stageRoot)) fs.rmSync(stageRoot, { recursive: true, force: true });
        throw cause;
      }
    }
    verifyMarketplaceRoot();
    durableSyncTree(finalRoot, operationLimits());
    const saved = store.saveMarketplace({
      marketplace_id: marketplaceId,
      registration_name: registrationName,
      root: finalRoot,
      selector,
      package_hash: packageRecord.package_hash,
      purpose,
    });
    revalidatePrivateRoots();
    return saved;
  };

  const savePackageIdentity = (operationId, identity) => {
    store.ensurePackageCapacity(identity);
    const preservedRoot = preserveTree({
      sourceRoot: identity.root,
      identity,
      storeRoot: store.roots.packages,
      stagingRoot: store.roots.staging,
      operationId,
      kind: "package",
    });
    return store.savePackage(treeRecord(identity, preservedRoot));
  };

  const portCall = (port, method, payload, label) => {
    if (!isPlainObject(port) || typeof port[method] !== "function") {
      fail(FAILURE.HOST_UNSUPPORTED, `${label} port is unavailable`, STATUS.UNSUPPORTED);
    }
    checkDeadline();
    revalidateCompositionCapabilities();
    revalidatePrivateRoots();
    let value;
    try {
      value = port[method](boundedJson(payload, `${label} input`));
    } catch {
      fail(FAILURE.HOST_UNSUPPORTED, `${label} port failed`, STATUS.UNSUPPORTED);
    }
    if (value?.then !== undefined) fail(FAILURE.HOST_UNSUPPORTED, `${label} port is asynchronous`, STATUS.UNSUPPORTED);
    revalidatePrivateRoots();
    checkDeadline();
    return boundedJson(value, `${label} output`);
  };

  const {
    validateLease,
    acquireLease,
    revalidateLease,
    recoverLease,
    releaseLease,
  } = createQuiescenceManager({
    store,
    config,
    ownerEpoch: () => activeOwnerEpoch,
    deadline: () => activeDeadline,
    effectId,
    portCall,
    checkDeadline,
    capabilityId: composition.binding.quiescence_capability_id,
  });
  const {
    verifySnapshotRecord,
    snapshotPluginData,
    comparePluginData,
    restorePluginData,
    disposeSnapshotLink,
    ensureStableSnapshotBoundary,
    reconcileEffect: reconcileDataEffect,
  } = createDataSnapshotManager({
    store,
    config,
    composition,
    ownerEpoch: () => activeOwnerEpoch,
    effectId,
    portCall,
    revalidateLease,
  });

  const requireTrust = (operationId, preparation, candidate, previous) => {
    if (candidate.package_hash === previous.package_hash) return;
    if (!isPlainObject(config.trustPort) || typeof config.trustPort.request !== "function") {
      fail(FAILURE.TRUST_UNAVAILABLE, "fresh package-closure trust is unavailable", STATUS.DEGRADED);
    }
    const trust = portCall(
      config.trustPort,
      "request",
      {
        operation_id: operationId,
        prepared_id: preparation.prepared_id,
        selector: preparation.activation_selector,
        capability_id: composition.capabilityIds.trust,
        subject_hash: candidate.package_hash,
        previous_subject_hash: previous.package_hash,
        trust_nonce: preparation.trust_nonce,
      },
      "trust",
    );
    exactFields(
      trust,
      [
        "status",
        "operation_id",
        "prepared_id",
        "selector",
        "subject_hash",
        "previous_subject_hash",
        "trust_nonce",
        "receipt_hash",
      ],
      "trust result",
    );
    const trustPreimage = {
      status: trust.status,
      operation_id: trust.operation_id,
      prepared_id: trust.prepared_id,
      selector: trust.selector,
      subject_hash: trust.subject_hash,
      previous_subject_hash: trust.previous_subject_hash,
      trust_nonce: trust.trust_nonce,
    };
    if (
      trust.operation_id !== operationId ||
      trust.prepared_id !== preparation.prepared_id ||
      trust.selector !== preparation.activation_selector ||
      trust.subject_hash !== candidate.package_hash ||
      trust.previous_subject_hash !== previous.package_hash ||
      trust.trust_nonce !== preparation.trust_nonce ||
      trust.receipt_hash !== hashJson("PLUGIN_LIFECYCLE_V3_TRUST_RECEIPT", trustPreimage)
    ) fail(FAILURE.TRUST_REQUIRED, "trust result is not freshly bound", STATUS.BLOCKED);
    if (trust.status === "DECLINED") fail(FAILURE.TRUST_DECLINED, "trust declined", STATUS.BLOCKED);
    if (trust.status !== "TRUSTED") fail(FAILURE.TRUST_UNAVAILABLE, "trust unavailable", STATUS.DEGRADED);
  };

  const migrationEffect = (operationId, phase, plan) => {
    if (!migrationPortReady(config.migrationPort)) {
      fail(FAILURE.MIGRATION_REQUIRED, "migration port lacks durable receipt methods", STATUS.UNSUPPORTED);
    }
    const id = effectId();
    const kind = phase === "APPLY" ? "MIGRATION_APPLY" : "MIGRATION_ROLLBACK";
    store.intentEffect({
      operationId,
      effectId: id,
      kind,
      intent: {
        plan_hash: plan.plan_hash,
        phase,
        owner_epoch: activeOwnerEpoch,
        migration_capability_id: composition.capabilityIds.migration,
      },
    });
    const raw = portCall(
      config.migrationPort,
      phase === "APPLY" ? "apply" : "rollback",
      {
        operation_id: operationId,
        owner_epoch: activeOwnerEpoch,
        effect_id: id,
        capability_id: composition.capabilityIds.migration,
        plan,
      },
      "migration",
    );
    const receipt = validateMigrationReceipt(raw, {
      operationId,
      ownerEpoch: activeOwnerEpoch,
      effectId: id,
      planHash: plan.plan_hash,
      phase,
    });
    store.resolveEffect({ effectId: id, resolution: { status: receipt.status, receipt_hash: receipt.receipt_hash } });
    if ((phase === "APPLY" && receipt.status !== "APPLIED") || (phase === "ROLLBACK" && receipt.status !== "ROLLED_BACK")) {
      fail(phase === "APPLY" ? FAILURE.MIGRATION_FAILED : FAILURE.MIGRATION_ROLLBACK_FAILED, "migration receipt is not successful");
    }
    return receipt;
  };

  const storedMigrationPlan = (preparation) => {
    if (preparation.migration_plan_json === null) return null;
    try {
      return parseMigrationPlan(
        JSON.parse(preparation.migration_plan_json),
        preparation.candidate_package_hash,
        preparation.previous_package_hash,
      );
    } catch {
      fail(FAILURE.STATE_CORRUPT, "stored migration plan is invalid");
    }
  };

  const preparationMigrationApplied = (preparedId) =>
    store.preparationHasEffectResolution(preparedId, "MIGRATION_APPLY", ["APPLIED"]);
  const preparationMigrationRolledBack = (preparedId) =>
    store.preparationHasEffectResolution(preparedId, "MIGRATION_ROLLBACK", ["ROLLED_BACK"]);
  const preparationPluginMutated = (preparedId) => [
    "HOST_PLUGIN_ADD",
    "HOST_PLUGIN_REMOVE",
  ].some((kind) => store.preparationHasEffectResolution(preparedId, kind, ["APPLIED"]));

  const exactPreviousAdd = (operationId, preparation, previous, lease) => {
    let currentLease = lease;
    const rollbackMarketplace = store.marketplace(preparation.rollback_marketplace_id);
    if (
      rollbackMarketplace === null ||
      rollbackMarketplace.package_hash !== previous.package_hash ||
      rollbackMarketplace.selector !== preparation.rollback_selector
    ) fail(FAILURE.STATE_CORRUPT, "rollback marketplace does not bind the captured previous package");
    const registration = exactMarketplaceEntry(listMarketplaces(operationId), rollbackMarketplace.registration_name);
    if (registration !== null && (registration.root === null || !sameAbsolutePath(registration.root, rollbackMarketplace.root))) {
      fail(FAILURE.HOST_AMBIGUOUS, "rollback marketplace name is occupied by an unrelated root");
    }
    const existing = exactOwnedInstalled(operationId, preparation.rollback_selector, previous);
    if (existing !== null && existing.enabled && registration !== null) {
      return { installed: existing, lease: currentLease };
    }
    if (existing !== null) {
      currentLease = revalidateLease(currentLease);
      removePlugin(operationId, preparation.rollback_selector, previous);
    }
    if (registration === null) {
      currentLease = revalidateLease(currentLease);
      addMarketplace(operationId, rollbackMarketplace);
    }
    currentLease = revalidateLease(currentLease);
    const added = addPlugin(operationId, preparation.rollback_selector, previous);
    if (added === null) fail(FAILURE.ROLLBACK_FAILED, "previous exact selector did not install");
    return { installed: added, lease: currentLease };
  };

  const reconcileOwnedMarketplaces = (allowCleanup = false) => {
    revalidatePrivateRoots();
    const pending = store.pending();
    const pendingEffect = pending === null ? null : store.unresolvedEffect(pending.operation_id);
    let pendingDisposalId = null;
    const pendingPreparationIds = new Set();
    if (pendingEffect?.kind === "RESOURCE_DISPOSE") {
      const intent = JSON.parse(pendingEffect.intent_json);
      if (intent.resource_type === "marketplace") pendingDisposalId = intent.resource_id;
    }
    if (pending?.method === "prepare") {
      let intent;
      try {
        intent = boundedJson(JSON.parse(pending.intent_json), "pending prepare intent");
      } catch {
        fail(FAILURE.STATE_CORRUPT, "pending prepare intent is invalid");
      }
      for (const id of [intent.candidate_marketplace_id, intent.rollback_marketplace_id]) {
        if (typeof id === "string") pendingPreparationIds.add(id);
      }
    }
    const recorded = new Map(store.allMarketplaces().map((item) => [item.marketplace_id, item]));
    const entries = fs.readdirSync(store.roots.marketplaces, { withFileTypes: true });
    if (entries.length > LIMITS.maxRetainedObjects) fail(FAILURE.RESOURCE_LIMIT, "marketplace root entry bound exceeded");
    let cleaned = 0;
    for (const entry of entries) {
      if (!entry.isDirectory() || !/^ef-lifecycle-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u.test(entry.name)) {
        fail(FAILURE.STATE_CORRUPT, "lifecycle marketplace root contains an unknown entry");
      }
      const item = recorded.get(entry.name);
      const target = path.join(store.roots.marketplaces, entry.name);
      if (item === undefined) {
        if (
          allowCleanup &&
          entry.name !== pendingDisposalId &&
          !pendingPreparationIds.has(entry.name) &&
          cleaned < LIMITS.maxCleanupItems
        ) {
          inspectTree(target);
          fs.rmSync(target, { recursive: true, force: true });
          cleaned += 1;
        } else if (
          allowCleanup &&
          entry.name !== pendingDisposalId &&
          !pendingPreparationIds.has(entry.name)
        ) {
          fail(FAILURE.RESOURCE_LIMIT, "bounded marketplace orphan cleanup is incomplete");
        }
      } else if (path.resolve(item.root) !== path.resolve(target)) {
        fail(FAILURE.STATE_CORRUPT, "recorded marketplace escaped its owned root");
      }
    }
    for (const item of recorded.values()) {
      if (!fs.existsSync(item.root) && item.marketplace_id !== pendingDisposalId) {
        fail(FAILURE.STATE_CORRUPT, "recorded marketplace root is missing");
      }
    }
    revalidatePrivateRoots();
  };

  const validateContentStores = (allowCleanup = false, protectedPackageHashes = new Set()) => {
    revalidatePrivateRoots();
    const allowedTop = new Set([
      "marketplaces",
      "packages",
      "recovery",
      "snapshots",
      "staging",
      "lifecycle.sqlite3",
      "lifecycle.sqlite3-shm",
      "lifecycle.sqlite3-wal",
      "lifecycle.sqlite3-journal",
      "ownership.sqlite3",
      "ownership.sqlite3-shm",
      "ownership.sqlite3-wal",
      "ownership.sqlite3-journal",
    ]);
    if (fs.readdirSync(store.roots.root).some((name) => !allowedTop.has(name))) {
      fail(FAILURE.STATE_CORRUPT, "lifecycleRoot contains an unknown entry");
    }
    const recordedPackages = new Set(store.packageHashes().map((hash) => hash.slice(7)));
    const packageEntries = fs.readdirSync(store.roots.packages, { withFileTypes: true });
    if (packageEntries.length > LIMITS.maxRetainedObjects) {
      fail(FAILURE.RESOURCE_LIMIT, "content store entry bound exceeded");
    }
    let cleanedPackages = 0;
    for (const entry of packageEntries) {
      if (!entry.isDirectory() || !/^[0-9a-f]{64}$/u.test(entry.name)) {
        fail(FAILURE.STATE_CORRUPT, "content-addressed store contains an unknown entry");
      }
      if (!recordedPackages.has(entry.name)) {
        const fullHash = `sha256:${entry.name}`;
        if (!protectedPackageHashes.has(fullHash)) {
          if (allowCleanup && cleanedPackages < LIMITS.maxCleanupItems) {
            fs.rmSync(path.join(store.roots.packages, entry.name), { recursive: true, force: true });
            cleanedPackages += 1;
          } else if (allowCleanup) {
            fail(FAILURE.RESOURCE_LIMIT, "bounded package orphan cleanup is incomplete");
          }
        }
        continue;
      }
      const children = fs.readdirSync(path.join(store.roots.packages, entry.name));
      if (children.length !== 1 || children[0] !== "data") {
        fail(FAILURE.STATE_CORRUPT, "recorded content-addressed container is not closed");
      }
    }
    const packageNames = new Set(packageEntries.map((entry) => entry.name));
    if ([...recordedPackages].some((hash) => !packageNames.has(hash))) {
      fail(FAILURE.STATE_CORRUPT, "recorded package content is missing");
    }

    // PLUGIN_DATA bytes remain exclusively inside the injected full-filesystem
    // provider. The private snapshots directory is never a payload store.
    const snapshotEntries = fs.readdirSync(store.roots.snapshots, { withFileTypes: true });
    if (snapshotEntries.length > LIMITS.maxRetainedObjects) {
      fail(FAILURE.RESOURCE_LIMIT, "snapshot root entry bound exceeded");
    }
    let cleanedSnapshots = 0;
    for (const entry of snapshotEntries) {
      if (!entry.isDirectory() || !/^[0-9a-f]{64}$/u.test(entry.name)) {
        fail(FAILURE.STATE_CORRUPT, "snapshot root contains an unknown entry");
      }
      if (allowCleanup && cleanedSnapshots < LIMITS.maxCleanupItems) {
        fs.rmSync(path.join(store.roots.snapshots, entry.name), { recursive: true, force: true });
        cleanedSnapshots += 1;
      } else {
        fail(FAILURE.STATE_CORRUPT, "snapshot provider payload escaped into lifecycleRoot");
      }
    }
    if (fs.readdirSync(store.roots.recovery).length !== 0) {
      fail(FAILURE.STATE_CORRUPT, "reserved recovery root contains an unknown entry");
    }
    revalidatePrivateRoots();
  };

  const uninstallDescriptor = (preparedId) => {
    requirePreparedId(preparedId);
    const preparation = store.preparation(preparedId);
    if (preparation === null) fail(FAILURE.NOT_FOUND, "preparation is missing");
    const terminalRetry = preparation.status === STATUS.UNINSTALLED;
    const candidate = terminalRetry ? { package_hash: preparation.candidate_package_hash } : packageRecord(preparation.candidate_package_hash);
    const previous = terminalRetry ? { package_hash: preparation.previous_package_hash } : packageRecord(preparation.previous_package_hash);
    const candidateMarketplace = store.marketplace(preparation.candidate_marketplace_id, terminalRetry);
    const rollbackMarketplace = store.marketplace(preparation.rollback_marketplace_id, terminalRetry);
    if (
      candidate === null ||
      previous === null ||
      candidateMarketplace === null ||
      rollbackMarketplace === null ||
      candidateMarketplace.selector !== preparation.activation_selector ||
      candidateMarketplace.package_hash !== candidate.package_hash ||
      rollbackMarketplace.selector !== preparation.rollback_selector ||
      rollbackMarketplace.package_hash !== previous.package_hash
    ) fail(FAILURE.STATE_CORRUPT, "preparation-owned uninstall target set is incomplete");
    return {
      preparedId,
      selector: preparation.activation_selector,
      intent: {
        prepared_id: preparedId,
        selectors: [
          { selector: preparation.activation_selector, package_hash: candidate.package_hash },
          { selector: preparation.rollback_selector, package_hash: previous.package_hash },
        ],
        marketplaces: [candidateMarketplace, rollbackMarketplace].map((item) => ({
          marketplace_id: item.marketplace_id,
          registration_name: item.registration_name,
          root: item.root,
          selector: item.selector,
          package_hash: item.package_hash,
        })),
      },
    };
  };

  const validateUninstallIntent = (intent, preparation) => {
    exactFields(intent, ["prepared_id", "selectors", "marketplaces"], "stored uninstall intent");
    if (
      intent.prepared_id !== preparation.prepared_id ||
      !Array.isArray(intent.selectors) ||
      intent.selectors.length !== 2 ||
      !Array.isArray(intent.marketplaces) ||
      intent.marketplaces.length !== 2
    ) {
      fail(FAILURE.STATE_CORRUPT, "stored uninstall target set is invalid");
    }
    const expectedSelectors = new Map([
      [preparation.activation_selector, preparation.candidate_package_hash],
      [preparation.rollback_selector, preparation.previous_package_hash],
    ]);
    for (const target of intent.selectors) {
      exactFields(target, ["selector", "package_hash"], "stored uninstall selector target");
      if (expectedSelectors.get(target.selector) !== target.package_hash) {
        fail(FAILURE.STATE_CORRUPT, "stored uninstall selector escaped its preparation");
      }
      expectedSelectors.delete(target.selector);
    }
    if (expectedSelectors.size !== 0) fail(FAILURE.STATE_CORRUPT, "stored uninstall selector set is incomplete");
    const expectedMarketplaces = new Map([
      [preparation.candidate_marketplace_id, preparation.activation_selector],
      [preparation.rollback_marketplace_id, preparation.rollback_selector],
    ]);
    for (const target of intent.marketplaces) {
      exactFields(
        target,
        ["marketplace_id", "registration_name", "root", "selector", "package_hash"],
        "stored uninstall marketplace target",
      );
      const row = store.marketplace(target.marketplace_id, preparation.status === STATUS.UNINSTALLED);
      if (
        row === null ||
        (preparation.status !== STATUS.UNINSTALLED && row.disposed_at !== null) ||
        expectedMarketplaces.get(target.marketplace_id) !== target.selector ||
        row.registration_name !== target.registration_name ||
        !sameAbsolutePath(row.root, target.root) ||
        row.selector !== target.selector ||
        row.package_hash !== target.package_hash
      ) fail(FAILURE.STATE_CORRUPT, "stored uninstall marketplace escaped its preparation");
      expectedMarketplaces.delete(target.marketplace_id);
    }
    if (expectedMarketplaces.size !== 0) fail(FAILURE.STATE_CORRUPT, "stored uninstall marketplace set is incomplete");
  };

  const assertPreparationHostAbsent = (operationId, preparation, frozenIntent = null) => {
    const selectors = frozenIntent === null
      ? [preparation.activation_selector, preparation.rollback_selector]
      : frozenIntent.selectors.map((item) => item.selector);
    const marketplaceTargets = frozenIntent === null
      ? [preparation.candidate_marketplace_id, preparation.rollback_marketplace_id].map((marketplaceId) => {
          const row = store.marketplace(marketplaceId, true);
          if (row === null) fail(FAILURE.STATE_CORRUPT, "terminal preparation marketplace record is missing");
          return { registration_name: row.registration_name };
        })
      : frozenIntent.marketplaces;
    const plugins = listPlugins(operationId);
    const marketplaces = listMarketplaces(operationId);
    if (
      selectors.some((selector) => exactPluginEntry(plugins, selector) !== null) ||
      marketplaceTargets.some(
        (target) => exactMarketplaceEntry(marketplaces, target.registration_name) !== null,
      )
    ) {
      fail(
        FAILURE.HOST_AMBIGUOUS,
        "terminal preparation-owned host state reappeared",
        STATUS.BLOCKED,
      );
    }
  };

  const resumeUninstall = (operationId, intent, recoveredLease = null) => {
    const preparation = store.preparation(intent.prepared_id);
    if (preparation === null) fail(FAILURE.STATE_CORRUPT, "pending uninstall preparation is missing");
    validateUninstallIntent(intent, preparation);
    if (preparation.status === STATUS.UNINSTALLED) {
      assertPreparationHostAbsent(operationId, preparation, intent);
      const current = store.projection();
      return {
        outcome: {
          ok: true,
          status: STATUS.UNINSTALLED,
          code: null,
          message: SUCCESS.uninstall,
          prepared_id: preparation.prepared_id,
          package_hash: null,
          data: {
            plugin_data_hash: store.operationSnapshot(operationId)?.snapshot_hash ?? null,
            selectors_removed: intent.selectors.map((item) => item.selector).sort(),
            idempotent: true,
          },
        },
        projectionPatch: { status: current.status, failure_code: current.failure_code },
        preparationPatch: null,
      };
    }
    if (preparation.finalized_at !== null) fail(FAILURE.INVALID_TRANSITION, "finalized preparation cannot be uninstalled");
    if (!quiescencePortReady(config.quiescencePort)) {
      fail(FAILURE.QUIESCENCE_REQUIRED, "uninstall requires durable quiescence ownership", STATUS.UNSUPPORTED);
    }
    const packages = new Map(intent.selectors.map((target) => {
      const record = packageRecord(target.package_hash);
      if (record === null) fail(FAILURE.STATE_CORRUPT, "uninstall package is missing");
      return [target.selector, record];
    }));
    const pluginsBefore = listPlugins(operationId);
    const marketplacesBefore = listMarketplaces(operationId);
    const destructiveTargetPresent =
      intent.selectors.some((target) => exactPluginEntry(pluginsBefore, target.selector) !== null) ||
      intent.marketplaces.some(
        (target) => exactMarketplaceEntry(marketplacesBefore, target.registration_name) !== null,
      );
    if (destructiveTargetPresent) requireDestructiveHostCapability();
    let lease = recoveredLease;
    const durableLease = store.lease(operationId);
    if (durableLease?.status === "HELD") {
      if (lease === null) lease = recoverLease(operationId, durableLease);
    } else {
      lease = acquireLease(operationId, preparation.activation_selector);
    }
    let snapshotLink = store.operationSnapshot(operationId);
    let snapshot;
    if (snapshotLink === null) {
      if (store.effects(operationId).some((item) => [
        "HOST_PLUGIN_REMOVE",
        "HOST_MARKETPLACE_REMOVE",
      ].includes(item.kind))) {
        fail(FAILURE.STATE_CORRUPT, "uninstall mutation exists without its pre-effect provider snapshot");
      }
      snapshot = snapshotPluginData(operationId, lease);
      lease = snapshot.lease;
      snapshotLink = store.operationSnapshot(operationId);
    } else {
      snapshot = verifySnapshotRecord(store.snapshotRecord(snapshotLink.snapshot_hash));
      lease = revalidateLease(lease);
    }
    for (const target of intent.selectors) {
      const installed = exactOwnedInstalled(operationId, target.selector, packages.get(target.selector));
      if (installed !== null) {
        lease = revalidateLease(lease);
        removePlugin(operationId, target.selector, packages.get(target.selector));
      }
    }
    for (const target of intent.marketplaces) {
      const marketplace = store.marketplace(target.marketplace_id);
      const observed = exactMarketplaceEntry(listMarketplaces(operationId), target.registration_name);
      if (observed !== null) {
        if (observed.root === null || !sameAbsolutePath(observed.root, target.root)) {
          fail(FAILURE.HOST_AMBIGUOUS, "uninstall marketplace no longer binds its preparation-owned root");
        }
        lease = revalidateLease(lease);
        removeMarketplace(operationId, marketplace);
      } else if (marketplace.registered === 1) {
        store.setMarketplaceRegistered(marketplace.marketplace_id, false);
      }
    }
    const pluginsAfter = listPlugins(operationId);
    for (const target of intent.selectors) {
      if (exactPluginEntry(pluginsAfter, target.selector) !== null) {
        fail(FAILURE.HOST_AMBIGUOUS, "preparation-owned selector remains after uninstall");
      }
    }
    const marketplacesAfter = listMarketplaces(operationId);
    for (const target of intent.marketplaces) {
      if (exactMarketplaceEntry(marketplacesAfter, target.registration_name) !== null) {
        fail(FAILURE.HOST_AMBIGUOUS, "preparation-owned marketplace remains after uninstall");
      }
    }
    const comparison = comparePluginData(operationId, lease, snapshot, operationId);
    lease = comparison.lease;
    if (!comparison.matches) {
      lease = restorePluginData(
        operationId,
        lease,
        snapshot,
        operationId,
        comparison.current_hash,
        comparison.current_token,
      );
    }
    releaseLease(operationId, lease);
    const current = store.projection();
    const removesActive = intent.selectors.some((target) => target.selector === current.active_selector);
    return {
      outcome: {
        ok: true,
        status: STATUS.UNINSTALLED,
        code: null,
        message: SUCCESS.uninstall,
        prepared_id: preparation.prepared_id,
        package_hash: null,
        data: {
          plugin_data_hash: snapshot.snapshot_hash,
          selectors_removed: intent.selectors.map((item) => item.selector).sort(),
          idempotent: false,
        },
      },
      projectionPatch: removesActive
        ? {
            active_selector: null,
            active_package_hash: null,
            previous_selector: null,
            previous_package_hash: null,
          }
        : current.active_selector !== null
          ? { status: current.status, failure_code: current.failure_code }
          : {},
      preparationPatch: {
        prepared_id: preparation.prepared_id,
        patch: { status: STATUS.UNINSTALLED, updated_at: new Date().toISOString() },
      },
    };
  };

  const reconcilePending = () => {
    revalidatePrivateRoots();
    reconcileOwnedStaging(store.roots.staging, operationLimits(), false);
    let operation = store.pending();
    if (operation === null) {
      reconcileOwnedStaging(store.roots.staging, operationLimits(), true);
      reconcileOwnedMarketplaces(true);
      validateContentStores(true);
      return null;
    }
    operation = store.claimPending(operation.operation_id);
    let durableLease = store.lease(operation.operation_id);
    let recoveredLease = null;
    let effect = store.unresolvedEffect(operation.operation_id);

    if (
      durableLease?.status === "HELD" &&
      effect?.kind !== "QUIESCE_RELEASE"
    ) {
      if (!quiescencePortReady(config.quiescencePort)) {
        fail(FAILURE.QUIESCENCE_REQUIRED, "pending operation cannot recover its durable lease", STATUS.UNSUPPORTED);
      }
      recoveredLease = recoverLease(operation.operation_id, durableLease);
    }

    if (effect?.kind === "RESOURCE_DISPOSE") {
      if (recoveredLease === null) {
        fail(FAILURE.QUIESCENCE_REQUIRED, "pending resource disposal lost quiescence", STATUS.BLOCKED);
      }
      recoveredLease = revalidateLease(recoveredLease);
      const disposalIntent = JSON.parse(effect.intent_json);
      if (disposalIntent.effect_id !== effect.effect_id) {
        fail(FAILURE.RECONCILIATION_REQUIRED, "resource quarantine effect binding differs", STATUS.BLOCKED);
      }
      if (disposalIntent.lease_id !== recoveredLease.lease_id) {
        fail(FAILURE.QUIESCENCE_REQUIRED, "pending resource disposal lease binding differs", STATUS.BLOCKED);
      }
      applyResourceDisposal(disposalIntent);
      store.resolveEffect({ effectId: effect.effect_id, resolution: { status: "APPLIED" } });
      effect = null;
    }
    reconcileOwnedMarketplaces(false);
    validateContentStores(false);

    if (effect !== null) {
      const intent = JSON.parse(effect.intent_json);
      if (
        effect.kind.startsWith("HOST_") &&
        (!Object.hasOwn(intent, "command_capability_id") ||
          intent.command_capability_id !== composition.capabilityIds.command)
      ) fail(FAILURE.HOST_UNSUPPORTED, "pending host effect capability identity differs", STATUS.UNSUPPORTED);
      if (["HOST_PLUGIN_REMOVE", "HOST_PLUGIN_ADD", "HOST_MARKETPLACE_ADD", "HOST_MARKETPLACE_REMOVE"].includes(effect.kind)) {
        if (recoveredLease === null) fail(FAILURE.QUIESCENCE_REQUIRED, "host mutation lost quiescence ownership", STATUS.BLOCKED);
        recoveredLease = revalidateLease(recoveredLease);
      }
      if (effect.kind === "HOST_PLUGIN_REMOVE") {
        exactFields(
          intent,
          [
            "selector",
            "expected_package_hash",
            "expected_root",
            "command_capability_id",
            "conditional_mutation_capability_id",
            "args",
          ],
          "stored plugin removal intent",
        );
        if (
          typeof intent.conditional_mutation_capability_id !== "string" ||
          intent.conditional_mutation_capability_id.length === 0 ||
          intent.conditional_mutation_capability_id !== composition.capabilityIds.conditionalMutation
        ) fail(FAILURE.STATE_CORRUPT, "pending plugin removal capability identity is invalid");
        const read = mutationReadback({ effectId: effect.effect_id }, ["plugin", "list", "--json"], "reconcile plugin remove");
        const observed = exactPluginEntry(read.payload, intent.selector, { requireRoot: true });
        let status = "APPLIED";
        if (observed !== null) {
          const expected = packageRecord(intent.expected_package_hash);
          if (expected === null) fail(FAILURE.STATE_CORRUPT, "plugin removal package record is missing");
          const identity = inspectTree(observed.root, { pluginName: expected.plugin_name });
          status =
            identity.tree_hash === expected.package_hash && sameAbsolutePath(observed.root, intent.expected_root)
              ? "NOT_APPLIED"
              : "MISMATCH";
        }
        store.resolveEffect({
          effectId: effect.effect_id,
          resolution: { status },
          diagnostic: read.diagnostic,
        });
      } else if (effect.kind === "HOST_PLUGIN_ADD") {
        exactFields(
          intent,
          ["selector", "expected_package_hash", "command_capability_id", "args"],
          "stored plugin add intent",
        );
        const read = mutationReadback({ effectId: effect.effect_id }, ["plugin", "list", "--json"], "reconcile plugin add");
        const observed = exactPluginEntry(read.payload, intent.selector, { requireRoot: true });
        let resolution = { status: "NOT_APPLIED" };
        if (observed !== null) {
          const identity = inspectTree(observed.root, { pluginName: parseSelector(intent.selector).pluginName });
          const marketplace = store.allMarketplaces().find((item) => item.selector === intent.selector);
          if (marketplace === undefined || marketplace.package_hash !== intent.expected_package_hash) {
            fail(FAILURE.STATE_CORRUPT, "plugin add effect lost its lifecycle marketplace binding");
          }
          const packageRecordValue = packageRecord(marketplace.package_hash);
          if (packageRecordValue === null) fail(FAILURE.STATE_CORRUPT, "plugin add package record is missing");
          const payload = inspectTree(path.join(marketplace.root, "plugins", packageRecordValue.plugin_name), {
            pluginName: packageRecordValue.plugin_name,
          });
          resolution = {
            status:
              observed.enabled &&
              identity.tree_hash === intent.expected_package_hash &&
              payload.tree_hash === intent.expected_package_hash
                ? "APPLIED"
                : "MISMATCH",
            observed_package_hash: identity.tree_hash,
          };
        }
        store.resolveEffect({ effectId: effect.effect_id, resolution, diagnostic: read.diagnostic });
      } else if (effect.kind === "HOST_MARKETPLACE_ADD" || effect.kind === "HOST_MARKETPLACE_REMOVE") {
        exactFields(
          intent,
          effect.kind === "HOST_MARKETPLACE_REMOVE"
            ? [
                "marketplace_id",
                "name",
                "root",
                "expected_marketplace_hash",
                "expected_package_hash",
                "command_capability_id",
                "conditional_mutation_capability_id",
                "args",
              ]
            : [
                "marketplace_id",
                "name",
                "root",
                "expected_marketplace_hash",
                "expected_package_hash",
                "command_capability_id",
                "args",
              ],
          "stored marketplace mutation intent",
        );
        if (
          effect.kind === "HOST_MARKETPLACE_REMOVE" &&
          (typeof intent.conditional_mutation_capability_id !== "string" ||
            intent.conditional_mutation_capability_id.length === 0 ||
            intent.conditional_mutation_capability_id !== composition.capabilityIds.conditionalMutation)
        ) fail(FAILURE.STATE_CORRUPT, "pending marketplace removal capability identity is invalid");
        const marketplace = store.marketplace(intent.marketplace_id);
        if (
          marketplace === null ||
          marketplace.registration_name !== intent.name ||
          marketplace.package_hash !== intent.expected_package_hash ||
          !sameAbsolutePath(marketplace.root, intent.root)
        ) {
          fail(FAILURE.STATE_CORRUPT, "marketplace effect lost its exact record binding");
        }
        const read = mutationReadback(
          { effectId: effect.effect_id },
          ["plugin", "marketplace", "list", "--json"],
          "reconcile marketplace mutation",
        );
        const observed = exactMarketplaceEntry(read.payload, intent.name);
        const packageRecordValue = packageRecord(marketplace.package_hash);
        if (packageRecordValue === null) fail(FAILURE.STATE_CORRUPT, "marketplace effect package is missing");
        const payload = inspectTree(path.join(marketplace.root, "plugins", packageRecordValue.plugin_name), {
          pluginName: packageRecordValue.plugin_name,
        });
        const marketplaceIdentity = inspectTree(marketplace.root);
        const payloadMatches =
          payload.tree_hash === packageRecordValue.package_hash &&
          marketplaceIdentity.tree_hash === intent.expected_marketplace_hash;
        let status;
        if (effect.kind === "HOST_MARKETPLACE_ADD") {
          status = observed === null
            ? "NOT_APPLIED"
            : observed.root !== null && sameAbsolutePath(observed.root, marketplace.root) && payloadMatches
              ? "APPLIED"
              : "MISMATCH";
        } else {
          status = observed === null && payloadMatches
            ? "APPLIED"
            : observed !== null && observed.root !== null && sameAbsolutePath(observed.root, marketplace.root) && payloadMatches
              ? "NOT_APPLIED"
              : "MISMATCH";
        }
        store.resolveEffect({
          effectId: effect.effect_id,
          resolution: { status },
          diagnostic: read.diagnostic,
        });
      } else if (effect.kind.startsWith("MIGRATION_") && migrationPortReady(config.migrationPort)) {
        exactFields(
          intent,
          ["plan_hash", "phase", "owner_epoch", "migration_capability_id"],
          "stored migration intent",
        );
        if (intent.migration_capability_id !== composition.capabilityIds.migration) {
          fail(FAILURE.HOST_UNSUPPORTED, "pending migration capability identity differs", STATUS.UNSUPPORTED);
        }
        const preparation = operation.prepared_id === null ? null : store.preparation(operation.prepared_id);
        const plan = preparation === null ? null : storedMigrationPlan(preparation);
        if (plan === null) fail(FAILURE.STATE_CORRUPT, "pending migration plan is missing");
        const phase = effect.kind === "MIGRATION_APPLY" ? "APPLY" : "ROLLBACK";
        if (
          intent.plan_hash !== plan.plan_hash ||
          intent.phase !== phase
        ) fail(FAILURE.STATE_CORRUPT, "pending migration intent binding differs");
        const receipt = validateMigrationReceipt(
          portCall(
            config.migrationPort,
            "reconcile",
            {
              operation_id: operation.operation_id,
              owner_epoch: activeOwnerEpoch,
              effect_id: effect.effect_id,
              capability_id: composition.capabilityIds.migration,
              plan,
            },
            "migration",
          ),
          {
            operationId: operation.operation_id,
            ownerEpoch: activeOwnerEpoch,
            effectId: effect.effect_id,
            planHash: plan.plan_hash,
            phase,
          },
        );
        store.resolveEffect({
          effectId: effect.effect_id,
          resolution: { status: receipt.status, receipt_hash: receipt.receipt_hash },
        });
      } else if (effect.kind.startsWith("MIGRATION_")) {
        fail(FAILURE.MIGRATION_REQUIRED, "pending migration lacks its durable reconciliation port", STATUS.UNSUPPORTED);
      } else if (effect.kind === "QUIESCE_ACQUIRE") {
        exactFields(
          intent,
          [
            "operation_id",
            "owner_epoch",
            "capability_id",
            "selector",
            "plugin_data_root",
            "required_until",
          ],
          "stored quiescence acquire intent",
        );
        if (
          !quiescencePortReady(config.quiescencePort) ||
          config.quiescencePort.capability_id !== composition.binding.quiescence_capability_id ||
          intent.capability_id !== composition.binding.quiescence_capability_id
        ) {
          fail(FAILURE.QUIESCENCE_REQUIRED, "pending acquire lacks its durable quiescence port", STATUS.UNSUPPORTED);
        }
        const raw = portCall(
          config.quiescencePort,
          "reconcile",
          {
            operation_id: operation.operation_id,
            owner_epoch: activeOwnerEpoch,
            effect_id: effect.effect_id,
            capability_id: composition.binding.quiescence_capability_id,
          },
          "quiescence",
        );
        exactFields(
          raw,
          ["state", "operation_id", "owner_epoch", "effect_id", "lease_id", "plugin_data_root", "ownership_token", "expires_at"],
          "quiescence acquire reconciliation",
        );
        if (raw.effect_id !== effect.effect_id) fail(FAILURE.QUIESCENCE_REQUIRED, "acquire reconciliation effect differs", STATUS.BLOCKED);
        const { effect_id: ignoredEffectId, ...leaseValue } = raw;
        recoveredLease = validateLease(leaseValue, {
          operationId: operation.operation_id,
          label: "reconciled acquired lease",
        });
        store.recordLeaseAcquire({ effectId: effect.effect_id, lease: recoveredLease });
      } else if (effect.kind === "QUIESCE_RELEASE") {
        exactFields(
          intent,
          ["operation_id", "owner_epoch", "capability_id", "lease_id"],
          "stored quiescence release intent",
        );
        if (
          !quiescencePortReady(config.quiescencePort) ||
          config.quiescencePort.capability_id !== composition.binding.quiescence_capability_id ||
          intent.capability_id !== composition.binding.quiescence_capability_id ||
          durableLease?.status !== "HELD"
        ) {
          fail(FAILURE.QUIESCENCE_REQUIRED, "pending release lost durable lease ownership", STATUS.UNSUPPORTED);
        }
        const released = portCall(
          config.quiescencePort,
          "reconcile",
          {
            operation_id: operation.operation_id,
            owner_epoch: activeOwnerEpoch,
            effect_id: effect.effect_id,
            capability_id: composition.binding.quiescence_capability_id,
          },
          "quiescence",
        );
        exactFields(released, ["state", "operation_id", "owner_epoch", "effect_id", "lease_id"], "quiescence release reconciliation");
        if (
          released.state !== "RELEASED" ||
          released.operation_id !== operation.operation_id ||
          released.owner_epoch !== activeOwnerEpoch ||
          released.effect_id !== effect.effect_id ||
          released.lease_id !== durableLease.lease_id
        ) fail(FAILURE.QUIESCENCE_REQUIRED, "release reconciliation is not resolving", STATUS.BLOCKED);
        store.recordLeaseRelease({ effectId: effect.effect_id, leaseId: durableLease.lease_id });
        recoveredLease = null;
      } else {
        const dataReconciliation = reconcileDataEffect({
          operation,
          effect,
          intent,
          recoveredLease,
        });
        if (dataReconciliation.handled) {
          recoveredLease = dataReconciliation.recoveredLease;
        } else if (effect.kind === "RESOURCE_DISPOSE") {
          if (recoveredLease === null) {
            fail(FAILURE.QUIESCENCE_REQUIRED, "pending resource disposal lost quiescence", STATUS.BLOCKED);
          }
          recoveredLease = revalidateLease(recoveredLease);
          if (intent.lease_id !== recoveredLease.lease_id) {
            fail(FAILURE.QUIESCENCE_REQUIRED, "pending resource disposal lease binding differs", STATUS.BLOCKED);
          }
          if (intent.effect_id !== effect.effect_id) {
            fail(FAILURE.RECONCILIATION_REQUIRED, "resource quarantine effect binding differs", STATUS.BLOCKED);
          }
          applyResourceDisposal(intent);
          store.resolveEffect({ effectId: effect.effect_id, resolution: { status: "APPLIED" } });
        } else if (["HOST_PLUGIN_LIST", "HOST_MARKETPLACE_LIST", "HOST_VERSION_READ"].includes(effect.kind)) {
          exactFields(
            intent,
            ["mutation", "command_capability_id", "args"],
            "stored host read intent",
          );
          if (intent.mutation !== false) fail(FAILURE.STATE_CORRUPT, "stored host read intent is mutating");
          store.resolveEffect({ effectId: effect.effect_id, resolution: { status: "NOT_APPLIED" } });
        } else {
          fail(FAILURE.STATE_CORRUPT, "pending effect kind is unknown");
        }
      }
    }

    const preEffectSnapshot = store.operationSnapshot(operation.operation_id);
    let preEffectBoundary = null;
    if (preEffectSnapshot !== null && ["activate", "uninstall"].includes(operation.method)) {
      preEffectBoundary = ensureStableSnapshotBoundary(operation.operation_id, recoveredLease);
      recoveredLease = preEffectBoundary.lease;
      if (!preEffectBoundary.stable) {
        durableLease = store.lease(operation.operation_id);
        if (durableLease?.status === "HELD") {
          if (recoveredLease === null) recoveredLease = recoverLease(operation.operation_id, durableLease);
          releaseLease(operation.operation_id, recoveredLease);
        }
        const current = store.projection();
        const outcome = {
          ok: false,
          status: STATUS.BLOCKED,
          code: FAILURE.PLUGIN_DATA_CHANGED,
          prepared_id: operation.prepared_id,
          package_hash: null,
          rolled_back: false,
          data: null,
        };
        const projection = store.finishOperation({
          operationId: operation.operation_id,
          outcome,
          projectionPatch: { status: current.status, failure_code: current.failure_code },
        });
        return makeResult(operation.method, outcome, projection.active_package_hash);
      }
    }

    const operationEffects = store.effects(operation.operation_id);
    const resolutionStatus = (item) => {
      if (item.resolution_json === null) return null;
      let resolution;
      try {
        resolution = boundedJson(JSON.parse(item.resolution_json), "stored effect resolution");
      } catch (cause) {
        if (cause instanceof LifecycleError) throw cause;
        fail(FAILURE.STATE_CORRUPT, "stored effect resolution is invalid");
      }
      return typeof resolution.status === "string" ? resolution.status : null;
    };
    const effectChangedState = (kinds) => operationEffects.some(
      (item) => kinds.includes(item.kind) && ![null, "NOT_APPLIED", "FAILED"].includes(resolutionStatus(item)),
    );
    const snapshotLink = store.operationSnapshot(operation.operation_id);
    if (operation.method === "prepare") {
      let storedIntent;
      try {
        storedIntent = boundedJson(JSON.parse(operation.intent_json), "pending prepare intent");
      } catch {
        fail(FAILURE.STATE_CORRUPT, "pending prepare intent is invalid");
      }
      const descriptor = prepareDescriptor({
        selector: storedIntent.selector,
        candidate_root: storedIntent.candidate_root,
        expected_hash: storedIntent.expected_hash,
        migration_plan: storedIntent.migration_plan,
      });
      if (
        operation.prepared_id !== descriptor.preparedId ||
        canonicalJson(storedIntent) !== canonicalJson(descriptor.intent)
      ) fail(FAILURE.STATE_CORRUPT, "pending prepare allocation differs from its deterministic intent");
      let completed;
      try {
        completed = performPrepare(operation.operation_id, descriptor);
      } catch (cause) {
        if (store.unresolvedEffect(operation.operation_id) !== null || store.lease(operation.operation_id)?.status === "HELD") {
          throw cause;
        }
        return finishFailure(
          operation.operation_id,
          "prepare",
          cause,
          { prepared_id: descriptor.preparedId },
        );
      }
      const projection = store.finishOperation({
        operationId: operation.operation_id,
        outcome: completed.outcome,
        projectionPatch: completed.projectionPatch ?? {},
        preparationPatch: completed.preparationPatch ?? null,
      });
      return makeResult(operation.method, completed.outcome, projection.active_package_hash);
    }
    if (operation.method === "uninstall") {
      let uninstallIntent;
      try {
        uninstallIntent = boundedJson(JSON.parse(operation.intent_json), "pending uninstall intent");
      } catch {
        fail(FAILURE.STATE_CORRUPT, "pending uninstall intent is invalid");
      }
      const completed = resumeUninstall(operation.operation_id, uninstallIntent, recoveredLease);
      const projection = store.finishOperation({
        operationId: operation.operation_id,
        outcome: completed.outcome,
        projectionPatch: completed.projectionPatch,
        preparationPatch: completed.preparationPatch,
      });
      return makeResult(operation.method, completed.outcome, projection.active_package_hash);
    }
    if (operation.method === "finalize" && operation.prepared_id !== null) {
      const preparation = store.preparation(operation.prepared_id);
      if (preparation === null) fail(FAILURE.STATE_CORRUPT, "pending finalization preparation is missing");
      if (preparation.finalized_at !== null) {
        assertPreparationHostAbsent(operation.operation_id, preparation);
        const outcome = {
          ok: true,
          status: preparation.status,
          code: null,
          message: SUCCESS.finalize,
          prepared_id: preparation.prepared_id,
          package_hash: preparation.candidate_package_hash,
          rolled_back: false,
          data: { finalized_at: preparation.finalized_at, idempotent: true },
        };
        const projection = store.finishOperation({
          operationId: operation.operation_id,
          outcome,
          projectionPatch: finalizationProjectionPatch(preparation),
        });
        return makeResult(operation.method, outcome, projection.active_package_hash);
      }
    }
    let projectionPatch = {};
    let preparationStatus = STATUS.BLOCKED;
    let rolledBack = false;
    let terminalSuccess = false;
    let releaseUnusedActivationSnapshot = false;
    let safeActivationRetry = false;
    if (["activate", "verify", "rollback"].includes(operation.method) && operation.prepared_id !== null) {
      const preparation = store.preparation(operation.prepared_id);
      if (preparation === null) fail(FAILURE.STATE_CORRUPT, "pending lifecycle preparation is missing");
      const candidate = packageRecord(preparation.candidate_package_hash);
      const previous = packageRecord(preparation.previous_package_hash);
      if (candidate === null || previous === null) fail(FAILURE.STATE_CORRUPT, "pending lifecycle package is missing");
      const activeMutation = effectChangedState([
        "HOST_PLUGIN_REMOVE",
        "HOST_PLUGIN_ADD",
        "MIGRATION_APPLY",
      ]);
      const durableHostMutation = preparationPluginMutated(preparation.prepared_id);
      const mustRollback =
        operation.method === "verify" ||
        (operation.method === "rollback" && durableHostMutation) ||
        (operation.method === "activate" && activeMutation);
      if (operation.method === "rollback" && !durableHostMutation) {
        if (preparationMigrationApplied(preparation.prepared_id)) {
          fail(FAILURE.STATE_CORRUPT, "pending no-effect rollback has an applied migration");
        }
        const previousInstalled = exactInstalled(
          operation.operation_id,
          preparation.previous_selector,
          previous.package_hash,
        );
        const plugins = listPlugins(operation.operation_id);
        const marketplaces = listMarketplaces(operation.operation_id);
        const candidateMarketplace = store.marketplace(preparation.candidate_marketplace_id);
        const rollbackMarketplace = store.marketplace(preparation.rollback_marketplace_id);
        if (candidateMarketplace === null || rollbackMarketplace === null) {
          fail(FAILURE.STATE_CORRUPT, "pending no-effect rollback marketplace is missing");
        }
        if (
          previousInstalled === null ||
          exactPluginEntry(plugins, preparation.activation_selector) !== null ||
          exactPluginEntry(plugins, preparation.rollback_selector) !== null ||
          exactMarketplaceEntry(marketplaces, candidateMarketplace.registration_name) !== null ||
          exactMarketplaceEntry(marketplaces, rollbackMarketplace.registration_name) !== null
        ) fail(FAILURE.HOST_AMBIGUOUS, "pending no-effect rollback observed changed host state");
        rolledBack = true;
        preparationStatus = STATUS.ROLLED_BACK;
        terminalSuccess = true;
        projectionPatch = {
          active_selector: preparation.previous_selector,
          active_package_hash: previous.package_hash,
          previous_selector: null,
          previous_package_hash: null,
        };
      } else if (mustRollback) {
        if (
          preparation.plugin_data_snapshot_hash === null ||
          preparation.plugin_data_snapshot_operation_id === null
        ) fail(FAILURE.STATE_CORRUPT, "mutated lifecycle operation lost its pre-effect snapshot link");
        durableLease = store.lease(operation.operation_id);
        if (durableLease?.status !== "HELD") {
          recoveredLease = acquireLease(operation.operation_id, operation.selector ?? preparation.activation_selector);
        } else if (recoveredLease === null) {
          recoveredLease = recoverLease(operation.operation_id, durableLease);
        }
        rollbackWithin(
          operation.operation_id,
          preparation,
          candidate,
          previous,
          recoveredLease,
        );
        recoveredLease = null;
        rolledBack = true;
        preparationStatus = STATUS.ROLLED_BACK;
        projectionPatch = {
          active_selector: preparation.rollback_selector,
          active_package_hash: previous.package_hash,
          previous_selector: preparation.activation_selector,
          previous_package_hash: candidate.package_hash,
        };
        terminalSuccess = operation.method === "rollback";
      } else if (effectChangedState(["HOST_MARKETPLACE_ADD"])) {
        const marketplace = store.marketplace(preparation.candidate_marketplace_id);
        if (marketplace === null) fail(FAILURE.STATE_CORRUPT, "pending candidate marketplace is missing");
        durableLease = store.lease(operation.operation_id);
        if (durableLease?.status !== "HELD") {
          recoveredLease = acquireLease(operation.operation_id, preparation.previous_selector);
        } else if (recoveredLease === null) {
          recoveredLease = recoverLease(operation.operation_id, durableLease);
        }
        const observed = exactMarketplaceEntry(listMarketplaces(operation.operation_id), marketplace.registration_name);
        if (observed !== null) {
          if (observed.root === null || !sameAbsolutePath(observed.root, marketplace.root)) {
            fail(FAILURE.HOST_AMBIGUOUS, "pending marketplace name no longer binds its owned root");
          }
          recoveredLease = revalidateLease(recoveredLease);
          removeMarketplace(operation.operation_id, marketplace);
        }
      }
      safeActivationRetry =
        operation.method === "activate" &&
        !mustRollback &&
        !rolledBack;
      releaseUnusedActivationSnapshot =
        safeActivationRetry &&
        snapshotLink !== null &&
        preEffectBoundary !== null;
      if (safeActivationRetry) preparationStatus = STATUS.PREPARED;
    }
    if (releaseUnusedActivationSnapshot) {
      if (preEffectBoundary === null) {
        fail(FAILURE.STATE_CORRUPT, "unused activation snapshot lost its stable boundary");
      }
      durableLease = store.lease(operation.operation_id);
      if (durableLease?.status !== "HELD") {
        const preparation = operation.prepared_id === null ? null : store.preparation(operation.prepared_id);
        if (preparation === null) fail(FAILURE.STATE_CORRUPT, "unused activation snapshot lost its preparation");
        recoveredLease = acquireLease(operation.operation_id, preparation.previous_selector);
      } else if (recoveredLease === null) {
        recoveredLease = recoverLease(operation.operation_id, durableLease);
      }
      const comparison = comparePluginData(
        operation.operation_id,
        recoveredLease,
        preEffectBoundary.snapshot,
        operation.operation_id,
      );
      recoveredLease = comparison.lease;
      if (!comparison.matches) {
        recoveredLease = restorePluginData(
          operation.operation_id,
          recoveredLease,
          preEffectBoundary.snapshot,
          operation.operation_id,
          comparison.current_hash,
          comparison.current_token,
        );
      }
      if (operation.prepared_id !== null) {
        store.updatePreparation(operation.prepared_id, {
          plugin_data_snapshot_hash: null,
          plugin_data_snapshot_operation_id: null,
          updated_at: new Date().toISOString(),
        });
      }
    }
    durableLease = store.lease(operation.operation_id);
    if (durableLease?.status === "HELD") {
      if (recoveredLease === null) recoveredLease = recoverLease(operation.operation_id, durableLease);
      releaseLease(operation.operation_id, recoveredLease);
    }
    const outcome = {
      ok: terminalSuccess,
      status: terminalSuccess ? STATUS.ROLLED_BACK : (rolledBack ? STATUS.ROLLED_BACK : STATUS.BLOCKED),
      code: terminalSuccess ? null : FAILURE.RECONCILIATION_REQUIRED,
      message: terminalSuccess ? SUCCESS.rollback : undefined,
      prepared_id: operation.prepared_id,
      package_hash:
        rolledBack && operation.prepared_id !== null
          ? store.preparation(operation.prepared_id).previous_package_hash
          : null,
      rolled_back: rolledBack,
      data: null,
    };
    store.finishOperation({
      operationId: operation.operation_id,
      outcome,
      projectionPatch,
      preparationPatch:
        operation.prepared_id === null || store.preparation(operation.prepared_id) === null
          ? null
          : {
              prepared_id: operation.prepared_id,
              patch: { status: preparationStatus, updated_at: new Date().toISOString() },
            },
    });
    return makeResult(operation.method, outcome, activeHash());
  };

  const executeOwned = (method, descriptorOrFactory, action) => {
    if (startupReconciliation !== null) {
      const result = startupReconciliation;
      startupReconciliation = null;
      return result;
    }
    let reconciled;
    try {
      reconciled = reconcilePending();
    } catch (cause) {
      return makeResult(method, errorOutcome(cause), activeHash());
    }
    if (reconciled !== null) return reconciled;
    let descriptor;
    try {
      descriptor = typeof descriptorOrFactory === "function" ? descriptorOrFactory() : descriptorOrFactory;
    } catch (cause) {
      return makeResult(method, errorOutcome(cause), activeHash());
    }
    const operationId = opId();
    try {
      store.startOperation({ operationId, method, ...descriptor });
    } catch (cause) {
      return makeResult(method, errorOutcome(cause), activeHash());
    }
    try {
      const completed = action(operationId, descriptor);
      const projection = store.finishOperation({
        operationId,
        outcome: completed.outcome,
        projectionPatch: completed.projectionPatch ?? {},
        preparationPatch: completed.preparationPatch ?? null,
      });
      return makeResult(method, completed.outcome, projection.active_package_hash);
    } catch (cause) {
      const recoveryKinds = new Set([
        "HOST_PLUGIN_ADD",
        "HOST_PLUGIN_REMOVE",
        "HOST_MARKETPLACE_ADD",
        "HOST_MARKETPLACE_REMOVE",
        "MIGRATION_APPLY",
        "MIGRATION_ROLLBACK",
        "DATA_SNAPSHOT_RESTORE",
      ]);
      if (
        store.unresolvedEffect(operationId) !== null ||
        store.lease(operationId)?.status === "HELD" ||
        store.effects(operationId).some((effect) => recoveryKinds.has(effect.kind))
      ) {
        return makeResult(method, {
          ok: false,
          status: STATUS.BLOCKED,
          code: FAILURE.RECONCILIATION_REQUIRED,
          prepared_id: descriptor.preparedId ?? null,
          rolled_back: false,
          data: null,
        }, activeHash());
      }
      return finishFailure(
        operationId,
        method,
        cause,
        { prepared_id: descriptor.preparedId },
        {},
      );
    }
  };

  const execute = (method, descriptor, action) => {
    if (closed) {
      return makeResult(method, {
        ok: false,
        status: STATUS.BLOCKED,
        code: FAILURE.INVALID_TRANSITION,
        rolled_back: false,
        data: null,
      }, null);
    }
    try {
      return store.withOwnership((ownerEpoch) => {
        activeOwnerEpoch = ownerEpoch;
        activeDeadline = Date.now() + config.maxOperationMs;
        try {
          revalidateCompositionCapabilities();
          revalidatePrivateRoots();
          store.initialize({ binding: composition.binding, bindingHash: composition.bindingHash });
          revalidatePrivateRoots();
          return executeOwned(method, descriptor, action);
        } finally {
          activeDeadline = null;
          activeOwnerEpoch = null;
        }
      });
    } catch (cause) {
      activeDeadline = null;
      activeOwnerEpoch = null;
      return makeResult(method, errorOutcome(cause), null);
    }
  };

  const probeHost = () =>
    execute("probeHost", { intent: { mutation: false } }, (operationId) => {
      let version;
      if (config.probePort === null) {
        const result = readHostEffect(operationId, "HOST_VERSION_READ", ["--version"], { mutation: false }, "host version");
        version = parseHostVersionText(result.stdout);
        listPlugins(operationId);
        listMarketplaces(operationId);
      } else {
        let raw;
        const probeInput = {
          codex_executable: config.executable.path,
          codex_executable_hash: config.executable.content_hash,
          required_operations: [
            "plugin list --json",
            "plugin marketplace list --json",
            "plugin marketplace add",
            "plugin marketplace remove",
            "plugin add",
            "plugin remove",
          ],
          version_pinned_activation: false,
        };
        try {
          raw = config.probePort(boundedJson(probeInput, "probe input"));
        } catch {
          fail(FAILURE.HOST_UNSUPPORTED, "probe port failed", STATUS.UNSUPPORTED);
        }
        if (raw?.then !== undefined) fail(FAILURE.HOST_UNSUPPORTED, "probe port is asynchronous", STATUS.UNSUPPORTED);
        const probed = boundedJson(raw, "probe output");
        revalidatePrivateRoots();
        exactFields(
          probed,
          [
            "host_version",
            "exact_selector_lifecycle",
            "marketplace_lifecycle",
            "version_pinned_activation",
            "receipt_hash",
          ],
          "probe output",
        );
        const probePreimage = {
          ...probeInput,
          host_version: probed.host_version,
          exact_selector_lifecycle: probed.exact_selector_lifecycle,
          marketplace_lifecycle: probed.marketplace_lifecycle,
        };
        if (
          probed.exact_selector_lifecycle !== "SUPPORTED" ||
          probed.marketplace_lifecycle !== "SUPPORTED" ||
          probed.version_pinned_activation !== false ||
          probed.receipt_hash !== hashJson("PLUGIN_LIFECYCLE_V3_HOST_PROBE_RECEIPT", probePreimage)
        ) fail(FAILURE.HOST_UNSUPPORTED, "probe port did not qualify the narrow lifecycle operations", STATUS.UNSUPPORTED);
        try {
          version = strictVersion(probed.host_version);
        } catch {
          fail(FAILURE.HOST_OUTPUT_INVALID, "probe version is not strict SemVer");
        }
      }
      const data = {
        host: "codex_cli",
        host_version: version,
        version_pinned_activation: false,
        mode: "DEGRADED",
        capabilities: {
          exact_selector_lifecycle: {
            state: host.conditionalMutationCapabilityId === null ? "UNSUPPORTED" : "SUPPORTED",
          },
          conditional_destructive_lifecycle: {
            state: host.conditionalMutationCapabilityId === null ? "UNSUPPORTED" : "SUPPORTED",
          },
          version_pinned_activation: { state: "UNSUPPORTED" },
          atomic_upgrade: { state: "UNSUPPORTED" },
          crash_idempotent_migration: { state: migrationPortReady(config.migrationPort) ? "SUPPORTED" : "UNSUPPORTED" },
          quiescent_data_ownership: {
            state:
              quiescencePortReady(config.quiescencePort) &&
              config.quiescencePort.capability_id === composition.binding.quiescence_capability_id
                ? "SUPPORTED"
                : "UNSUPPORTED",
          },
          full_filesystem_data_snapshot: {
            state: dataSnapshotPortReady(config.dataSnapshotPort) ? "SUPPORTED" : "UNSUPPORTED",
          },
          protected_private_state: { state: "SUPPORTED" },
          installed_verification: {
            state:
              isPlainObject(config.verificationPort) &&
              ["health", "replay", "integrity"].every((name) => typeof config.verificationPort[name] === "function")
                ? "SUPPORTED"
                : "UNSUPPORTED",
          },
        },
      };
      return {
        outcome: { ok: true, status: STATUS.DEGRADED, code: null, message: SUCCESS.probeHost, data },
      };
    });

  const capture = (selector) =>
    execute("capture", { selector: descriptorText(selector), intent: { selector: descriptorText(selector) } }, (operationId) => {
      const installed = exactInstalled(operationId, selector);
      if (installed === null) fail(FAILURE.NOT_FOUND, "exact selector is not installed");
      reconcileOwnedStaging(store.roots.staging, operationLimits(), true);
      reconcileOwnedMarketplaces(true);
      validateContentStores(true);
      const packageRecord = savePackageIdentity(operationId, installed.identity);
      const current = store.projection();
      if (
        current.active_selector !== null &&
        (current.active_selector !== selector || current.active_package_hash !== packageRecord.package_hash)
      ) fail(FAILURE.CONCURRENT_OPERATION, "capture conflicts with recorded active projection", STATUS.BLOCKED);
      return {
        outcome: {
          ok: true,
          status: STATUS.CAPTURED,
          code: null,
          message: SUCCESS.capture,
          package_hash: packageRecord.package_hash,
          data: { package: publicPackage(packageRecord) },
        },
        projectionPatch: {
          active_selector: selector,
          active_package_hash: packageRecord.package_hash,
        },
      };
    });

  const prepareDescriptor = (request) => {
    if (!isPlainObject(request)) fail(FAILURE.INVALID_INPUT, "prepare request must be an object");
    for (const key of Object.keys(request)) {
      if (!["selector", "candidate_root", "expected_hash", "migration_plan"].includes(key)) {
        fail(FAILURE.INVALID_INPUT, "prepare request has unsupported fields");
      }
    }
    const parsed = parseSelector(request.selector);
    if (
      typeof request.candidate_root !== "string" ||
      !path.isAbsolute(request.candidate_root) ||
      path.resolve(request.candidate_root) !== path.normalize(request.candidate_root) ||
      (process.platform === "win32" && /^(?:\\\\|\/\/)/u.test(request.candidate_root)) ||
      typeof request.expected_hash !== "string" ||
      !/^sha256:[0-9a-f]{64}$/u.test(request.expected_hash)
    ) fail(FAILURE.INVALID_INPUT, "prepare requires a canonical local candidate_root and sha256 expected_hash");
    const closedRequest = boundedJson(
      {
        selector: request.selector,
        candidate_root: request.candidate_root,
        expected_hash: request.expected_hash,
        migration_plan: request.migration_plan ?? null,
      },
      "prepare intent",
    );
    const intentHash = hashJson("PLUGIN_LIFECYCLE_V3_PREPARE_INTENT", {
      composition_binding_hash: composition.bindingHash,
      request: closedRequest,
    });
    const preparedId = `prep_${uuidFromHash(intentHash)}`;
    const candidateMarketplaceId = `ef-lifecycle-${uuidFromHash(hashJson("PLUGIN_LIFECYCLE_V3_MARKETPLACE_ID", {
      intent_hash: intentHash,
      purpose: "candidate",
    }))}`;
    const rollbackMarketplaceId = `ef-lifecycle-${uuidFromHash(hashJson("PLUGIN_LIFECYCLE_V3_MARKETPLACE_ID", {
      intent_hash: intentHash,
      purpose: "rollback",
    }))}`;
    const activationSelector = `${parsed.pluginName}@${candidateMarketplaceId}`;
    const rollbackSelector = `${parsed.pluginName}@${rollbackMarketplaceId}`;
    parseSelector(activationSelector);
    parseSelector(rollbackSelector);
    return {
      selector: request.selector,
      preparedId,
      candidateAllocation: {
        marketplaceId: candidateMarketplaceId,
        registrationName: candidateMarketplaceId,
        selector: activationSelector,
      },
      rollbackAllocation: {
        marketplaceId: rollbackMarketplaceId,
        registrationName: rollbackMarketplaceId,
        selector: rollbackSelector,
      },
      trustNonce: hashJson("PLUGIN_LIFECYCLE_V3_TRUST_NONCE", { intent_hash: intentHash }),
      intent: {
        ...closedRequest,
        intent_hash: intentHash,
        prepared_id: preparedId,
        candidate_marketplace_id: candidateMarketplaceId,
        rollback_marketplace_id: rollbackMarketplaceId,
        activation_selector: activationSelector,
        rollback_selector: rollbackSelector,
      },
    };
  };

  const preparationData = (preparation, candidate, previous, plan, idempotent) => ({
    candidate: publicPackage(candidate),
    previous: publicPackage(previous),
    activation_selector: preparation.activation_selector,
    rollback_selector: preparation.rollback_selector,
    migration_requested: plan !== null,
    trust_required: candidate.package_hash !== previous.package_hash,
    idempotent,
  });

  const performPrepare = (operationId, descriptor) => {
      const existing = store.preparation(descriptor.preparedId);
      if (existing !== null) {
        const candidate = packageRecord(existing.candidate_package_hash);
        const previous = packageRecord(existing.previous_package_hash);
        if (
          candidate === null ||
          previous === null ||
          existing.selector !== descriptor.selector ||
          existing.activation_selector !== descriptor.candidateAllocation.selector ||
          existing.rollback_selector !== descriptor.rollbackAllocation.selector ||
          existing.candidate_marketplace_id !== descriptor.candidateAllocation.marketplaceId ||
          existing.rollback_marketplace_id !== descriptor.rollbackAllocation.marketplaceId ||
          candidate.package_hash !== descriptor.intent.expected_hash ||
          existing.trust_nonce !== descriptor.trustNonce
        ) fail(FAILURE.STATE_CORRUPT, "deterministic preparation identity collision");
        const plan = storedMigrationPlan(existing);
        const requestedPlan = parseMigrationPlan(
          descriptor.intent.migration_plan,
          candidate.package_hash,
          previous.package_hash,
        );
        if (canonicalJson(plan) !== canonicalJson(requestedPlan)) {
          fail(FAILURE.STATE_CORRUPT, "stored preparation migration plan differs from its intent");
        }
        createMarketplace(operationId, candidate, "candidate", descriptor.candidateAllocation);
        createMarketplace(operationId, previous, "rollback", descriptor.rollbackAllocation);
        return {
          outcome: {
            ok: true,
            status: existing.status,
            code: null,
            message: SUCCESS.prepare,
            prepared_id: existing.prepared_id,
            package_hash: candidate.package_hash,
            data: preparationData(existing, candidate, previous, plan, true),
          },
        };
      }
      reconcileOwnedStaging(store.roots.staging, operationLimits(), true);
      reconcileOwnedMarketplaces(true);
      const parsed = parseSelector(descriptor.selector);
      if ([config.lifecycleRoot, config.pluginDataRoot, config.codexHome, config.cwd, config.executable.path].some(
        (root) => pathsOverlap(descriptor.intent.candidate_root, root),
      )) fail(FAILURE.UNSAFE_PATH, "candidate package overlaps a controlled runtime root");
      const candidateIdentity = inspectTree(descriptor.intent.candidate_root, { pluginName: parsed.pluginName });
      if ([config.lifecycleRoot, config.pluginDataRoot, config.codexHome, config.cwd, config.executable.path].some(
        (root) => pathsOverlap(candidateIdentity.root, root),
      )) fail(FAILURE.UNSAFE_PATH, "candidate package overlaps a controlled runtime root");
      if (candidateIdentity.tree_hash !== descriptor.intent.expected_hash) {
        fail(FAILURE.IDENTITY_MISMATCH, "candidate expected hash differs");
      }
      const previousInstalled = exactInstalled(operationId, descriptor.selector);
      if (previousInstalled === null) fail(FAILURE.NOT_FOUND, "previous exact selector is absent");
      const current = store.projection();
      if (
        current.active_selector !== null &&
        (current.active_selector !== descriptor.selector || current.active_package_hash !== previousInstalled.identity.tree_hash)
      ) fail(FAILURE.CONCURRENT_OPERATION, "prepare conflicts with recorded active projection", STATUS.BLOCKED);
      validateContentStores(true, new Set([
        candidateIdentity.tree_hash,
        previousInstalled.identity.tree_hash,
      ]));
      const plan = parseMigrationPlan(
        descriptor.intent.migration_plan,
        candidateIdentity.tree_hash,
        previousInstalled.identity.tree_hash,
      );
      if (plan !== null && !migrationPortReady(config.migrationPort)) {
        fail(FAILURE.MIGRATION_REQUIRED, "migration port lacks durable resolving receipts", STATUS.UNSUPPORTED);
      }
      const candidate = savePackageIdentity(operationId, candidateIdentity);
      const previous = savePackageIdentity(operationId, previousInstalled.identity);
      const marketplace = createMarketplace(operationId, candidate, "candidate", descriptor.candidateAllocation);
      const rollbackMarketplace = createMarketplace(operationId, previous, "rollback", descriptor.rollbackAllocation);
      const now = new Date().toISOString();
      const preparation = store.savePreparation({
        prepared_id: descriptor.preparedId,
        selector: descriptor.selector,
        activation_selector: marketplace.selector,
        rollback_selector: rollbackMarketplace.selector,
        status: STATUS.PREPARED,
        candidate_package_hash: candidate.package_hash,
        previous_selector: descriptor.selector,
        previous_package_hash: previous.package_hash,
        previous_root: previousInstalled.identity.root,
        candidate_marketplace_id: marketplace.marketplace_id,
        rollback_marketplace_id: rollbackMarketplace.marketplace_id,
        migration_plan_json: plan === null ? null : canonicalJson(plan),
        trust_nonce: descriptor.trustNonce,
        created_at: now,
        updated_at: now,
      });
      return {
        outcome: {
          ok: true,
          status: STATUS.PREPARED,
          code: null,
          message: SUCCESS.prepare,
          prepared_id: preparation.prepared_id,
          package_hash: candidate.package_hash,
          data: preparationData(preparation, candidate, previous, plan, false),
        },
        preparationPatch: {
          prepared_id: preparation.prepared_id,
          patch: { status: STATUS.PREPARED, updated_at: now },
        },
      };
    };

  const prepare = (request) =>
    execute("prepare", () => prepareDescriptor(request), performPrepare);

  const rollbackWithin = (operationId, preparation, candidate, previous, lease) => {
    const migrationWasApplied = preparationMigrationApplied(preparation.prepared_id);
    const plan = migrationWasApplied ? storedMigrationPlan(preparation) : null;
    if (migrationWasApplied && plan === null) fail(FAILURE.STATE_CORRUPT, "applied migration lost its closed plan");
    if (plan !== null && !migrationPortReady(config.migrationPort)) {
      fail(FAILURE.MIGRATION_REQUIRED, "applied migration lost its durable rollback port", STATUS.UNSUPPORTED);
    }
    if (
      preparation.plugin_data_snapshot_hash === null ||
      preparation.plugin_data_snapshot_operation_id === null
    ) {
      fail(FAILURE.ROLLBACK_FAILED, "pre-effect plugin data snapshot link is missing");
    }
    const boundary = ensureStableSnapshotBoundary(
      preparation.plugin_data_snapshot_operation_id,
      lease,
    );
    lease = boundary.lease;
    const snapshot = boundary.snapshot;
    if (!boundary.stable || snapshot.snapshot_hash !== preparation.plugin_data_snapshot_hash) {
      fail(FAILURE.ROLLBACK_FAILED, "pre-effect plugin data snapshot boundary is not stable");
    }
    lease = comparePluginData(
      operationId,
      lease,
      snapshot,
      preparation.plugin_data_snapshot_operation_id,
    ).lease;
    const candidateMarketplace = createMarketplace(operationId, candidate, "candidate", {
      marketplaceId: preparation.candidate_marketplace_id,
      registrationName: preparation.candidate_marketplace_id,
      selector: preparation.activation_selector,
    });
    createMarketplace(operationId, previous, "rollback", {
      marketplaceId: preparation.rollback_marketplace_id,
      registrationName: preparation.rollback_marketplace_id,
      selector: preparation.rollback_selector,
    });
    const candidatePresent = exactOwnedInstalled(operationId, preparation.activation_selector, candidate);
    if (candidatePresent !== null) {
      lease = revalidateLease(lease);
      removePlugin(operationId, preparation.activation_selector, candidate);
    }
    if (exactMarketplaceEntry(listMarketplaces(operationId), candidateMarketplace.registration_name) !== null) {
      lease = revalidateLease(lease);
      removeMarketplace(operationId, candidateMarketplace);
    }
    const migrationAlreadyRolledBack = preparationMigrationRolledBack(preparation.prepared_id);
    if (plan !== null && !migrationAlreadyRolledBack) {
      lease = revalidateLease(lease);
      migrationEffect(operationId, "ROLLBACK", plan);
    }
    const comparison = comparePluginData(
      operationId,
      lease,
      snapshot,
      preparation.plugin_data_snapshot_operation_id,
    );
    lease = comparison.lease;
    if (!comparison.matches) {
      lease = restorePluginData(
        operationId,
        lease,
        snapshot,
        preparation.plugin_data_snapshot_operation_id,
        comparison.current_hash,
        comparison.current_token,
      );
    }
    if (plan !== null) {
      lease = revalidateLease(lease);
      const compatible = validateMigrationReceipt(
        portCall(
          config.migrationPort,
          "verifyCompatible",
          {
            operation_id: operationId,
            owner_epoch: activeOwnerEpoch,
            effect_id: null,
            plan,
            target_package_hash: previous.package_hash,
          },
          "migration",
        ),
        {
          operationId,
          ownerEpoch: activeOwnerEpoch,
          effectId: null,
          planHash: plan.plan_hash,
          phase: "ROLLBACK",
        },
      );
      if (compatible.status !== "COMPATIBLE") fail(FAILURE.MIGRATION_ROLLBACK_FAILED, "restored store is incompatible");
    }
    lease = revalidateLease(lease);
    lease = exactPreviousAdd(operationId, preparation, previous, lease).lease;
    releaseLease(operationId, lease);
    return {
      ok: false,
      status: STATUS.FAILED,
      code: FAILURE.CHECK_FAILED,
      prepared_id: preparation.prepared_id,
      package_hash: candidate.package_hash,
      rolled_back: true,
      data: null,
    };
  };

  const activate = (preparedId) =>
    execute("activate", { preparedId: descriptorText(preparedId, 64), intent: { prepared_id: descriptorText(preparedId, 64) } }, (operationId) => {
      requirePreparedId(preparedId);
      const preparation = store.preparation(preparedId);
      if (preparation === null) fail(FAILURE.NOT_FOUND, "preparation is missing");
      if (![STATUS.PREPARED, STATUS.DEGRADED].includes(preparation.status)) {
        fail(FAILURE.INVALID_TRANSITION, "activation requires PREPARED");
      }
      const candidate = packageRecord(preparation.candidate_package_hash);
      const previous = packageRecord(preparation.previous_package_hash);
      if (candidate === null || previous === null) fail(FAILURE.STATE_CORRUPT, "preparation package is missing");
      if (!quiescencePortReady(config.quiescencePort)) {
        fail(FAILURE.QUIESCENCE_REQUIRED, "no safe quiescence ownership contract", STATUS.UNSUPPORTED);
      }
      requireDestructiveHostCapability();
      const observedPrevious = exactInstalled(operationId, preparation.previous_selector, previous.package_hash);
      if (observedPrevious === null) fail(FAILURE.IDENTITY_MISMATCH, "previous exact selector is absent");
      const projection = store.projection();
      if (
        projection.active_selector !== null &&
        (projection.active_selector !== preparation.previous_selector ||
          projection.active_package_hash !== preparation.previous_package_hash)
      ) fail(FAILURE.CONCURRENT_OPERATION, "active projection conflicts with preparation", STATUS.BLOCKED);
      requireTrust(operationId, preparation, candidate, previous);
      const plan = storedMigrationPlan(preparation);
      if (plan !== null && !migrationPortReady(config.migrationPort)) {
        fail(FAILURE.MIGRATION_REQUIRED, "durable migration port is unavailable", STATUS.UNSUPPORTED);
      }
      verifyOriginalMarketplaceSource(operationId, preparation.previous_selector, previous);
      let lease = acquireLease(operationId, preparation.previous_selector);
      const snapshot = snapshotPluginData(operationId, lease);
      lease = snapshot.lease;
      store.updatePreparation(preparedId, {
        plugin_data_snapshot_hash: snapshot.snapshot_hash,
        plugin_data_snapshot_operation_id: snapshot.capture_operation_id,
        updated_at: new Date().toISOString(),
      });
      verifyOriginalMarketplaceSource(operationId, preparation.previous_selector, previous);
      const previousAfterSnapshot = exactInstalled(operationId, preparation.previous_selector, previous.package_hash);
      if (previousAfterSnapshot === null) fail(FAILURE.IDENTITY_MISMATCH, "previous selector changed before quiescent removal");
      const marketplace = createMarketplace(operationId, candidate, "candidate", {
        marketplaceId: preparation.candidate_marketplace_id,
        registrationName: preparation.candidate_marketplace_id,
        selector: preparation.activation_selector,
      });
      createMarketplace(operationId, previous, "rollback", {
        marketplaceId: preparation.rollback_marketplace_id,
        registrationName: preparation.rollback_marketplace_id,
        selector: preparation.rollback_selector,
      });
      let previousRemoved = false;
      try {
        lease = revalidateLease(lease);
        removePlugin(operationId, preparation.previous_selector, previous);
        previousRemoved = true;
        if (plan !== null) {
          lease = revalidateLease(lease);
          migrationEffect(operationId, "APPLY", plan);
        }
        lease = revalidateLease(lease);
        addMarketplace(operationId, marketplace);
        lease = revalidateLease(lease);
        const installed = addPlugin(operationId, preparation.activation_selector, candidate);
        if (installed === null) fail(FAILURE.IDENTITY_MISMATCH, "candidate exact selector did not activate");
        releaseLease(operationId, lease);
        return {
          outcome: {
            ok: true,
            status: STATUS.ACTIVE,
            code: null,
            message: SUCCESS.activate,
            prepared_id: preparedId,
            package_hash: candidate.package_hash,
            rolled_back: false,
            data: { package: publicPackage(candidate) },
          },
          projectionPatch: {
            active_selector: preparation.activation_selector,
            active_package_hash: candidate.package_hash,
            previous_selector: preparation.previous_selector,
            previous_package_hash: previous.package_hash,
          },
          preparationPatch: {
            prepared_id: preparedId,
            patch: { status: STATUS.ACTIVE, updated_at: new Date().toISOString() },
          },
        };
      } catch (cause) {
        if (!previousRemoved) {
          try {
            if (exactMarketplaceEntry(listMarketplaces(operationId), marketplace.registration_name) !== null) {
              lease = revalidateLease(lease);
              removeMarketplace(operationId, marketplace);
            }
            const comparison = comparePluginData(
              operationId,
              lease,
              snapshot,
              operationId,
            );
            lease = comparison.lease;
            if (!comparison.matches) {
              lease = restorePluginData(
                operationId,
                lease,
                snapshot,
                operationId,
                comparison.current_hash,
                comparison.current_token,
              );
            }
            store.updatePreparation(preparedId, {
              plugin_data_snapshot_hash: null,
              plugin_data_snapshot_operation_id: null,
              updated_at: new Date().toISOString(),
            });
            releaseLease(operationId, lease);
          } catch { /* pending effect remains reconcilable */ }
          throw cause;
        }
        try {
          const outcome = rollbackWithin(
            operationId,
            store.preparation(preparedId),
            candidate,
            previous,
            lease,
          );
          outcome.code = cause instanceof LifecycleError ? cause.code : FAILURE.ROLLBACK_FAILED;
          return {
            outcome,
            projectionPatch: {
              active_selector: preparation.rollback_selector,
              active_package_hash: previous.package_hash,
              previous_selector: preparation.activation_selector,
              previous_package_hash: candidate.package_hash,
            },
            preparationPatch: {
              prepared_id: preparedId,
              patch: { status: STATUS.ROLLED_BACK, updated_at: new Date().toISOString() },
            },
          };
        } catch {
          fail(FAILURE.ROLLBACK_FAILED, "automatic rollback could not restore exact state");
        }
      }
    });

  const verify = (preparedId) =>
    execute("verify", { preparedId: descriptorText(preparedId, 64), intent: { prepared_id: descriptorText(preparedId, 64) } }, (operationId) => {
      requirePreparedId(preparedId);
      const preparation = store.preparation(preparedId);
      if (preparation === null || preparation.status !== STATUS.ACTIVE) {
        fail(FAILURE.INVALID_TRANSITION, "verify requires ACTIVE preparation");
      }
      const candidate = packageRecord(preparation.candidate_package_hash);
      const previous = packageRecord(preparation.previous_package_hash);
      if (candidate === null || previous === null) fail(FAILURE.STATE_CORRUPT, "verification package record is missing");
      const checks = {};
      let passed = true;
      try {
        const installed = exactInstalled(operationId, preparation.activation_selector, candidate.package_hash);
        if (installed === null) passed = false;
      } catch {
        passed = false;
      }
      const installedTrusted = passed;
      for (const name of ["health", "replay", "integrity"]) {
        if (!installedTrusted) {
          checks[name] = { ok: false, state: "UNAVAILABLE" };
          continue;
        }
        try {
          const value = portCall(
            config.verificationPort,
            name,
            {
              operation_id: operationId,
              prepared_id: preparedId,
              selector: preparation.activation_selector,
              package_hash: candidate.package_hash,
              capability_id: composition.capabilityIds.verification,
            },
            "verification",
          );
          exactFields(
            value,
            ["ok", "operation_id", "prepared_id", "selector", "package_hash", "check", "result_hash"],
            "verification result",
          );
          checks[name] = { ok: value.ok === true, state: value.ok === true ? "PASS" : "FAIL" };
          const verificationPreimage = {
            ok: value.ok,
            operation_id: value.operation_id,
            prepared_id: value.prepared_id,
            selector: value.selector,
            package_hash: value.package_hash,
            check: value.check,
          };
          if (
            value.ok !== true ||
            value.operation_id !== operationId ||
            value.prepared_id !== preparedId ||
            value.selector !== preparation.activation_selector ||
            value.package_hash !== candidate.package_hash ||
            value.check !== name ||
            value.result_hash !== hashJson("PLUGIN_LIFECYCLE_V3_VERIFICATION_RECEIPT", verificationPreimage)
          ) passed = false;
        } catch {
          checks[name] = { ok: false, state: "UNAVAILABLE" };
          passed = false;
        }
      }
      if (passed) {
        return {
          outcome: {
            ok: true,
            status: STATUS.VERIFIED,
            code: null,
            message: SUCCESS.verify,
            prepared_id: preparedId,
            package_hash: candidate.package_hash,
            data: { checks },
          },
          preparationPatch: {
            prepared_id: preparedId,
            patch: { status: STATUS.VERIFIED, updated_at: new Date().toISOString() },
          },
        };
      }
      if (!quiescencePortReady(config.quiescencePort)) {
        fail(FAILURE.ROLLBACK_FAILED, "verification failed without rollback ownership");
      }
      const candidateMarketplace = store.marketplace(preparation.candidate_marketplace_id);
      if (candidateMarketplace === null) fail(FAILURE.STATE_CORRUPT, "verification rollback marketplace is missing");
      if (
        exactPluginEntry(listPlugins(operationId), preparation.activation_selector) !== null ||
        exactMarketplaceEntry(listMarketplaces(operationId), candidateMarketplace.registration_name) !== null
      ) requireDestructiveHostCapability();
      const lease = acquireLease(operationId, preparation.activation_selector);
      const outcome = rollbackWithin(operationId, preparation, candidate, previous, lease);
      outcome.code = FAILURE.CHECK_FAILED;
      outcome.data = { checks };
      return {
        outcome,
        projectionPatch: {
          active_selector: preparation.rollback_selector,
          active_package_hash: previous.package_hash,
          previous_selector: preparation.activation_selector,
          previous_package_hash: candidate.package_hash,
        },
        preparationPatch: {
          prepared_id: preparedId,
          patch: { status: STATUS.ROLLED_BACK, updated_at: new Date().toISOString() },
        },
      };
    });

  const rollback = (preparedId) =>
    execute("rollback", { preparedId: descriptorText(preparedId, 64), intent: { prepared_id: descriptorText(preparedId, 64) } }, (operationId) => {
      requirePreparedId(preparedId);
      const preparation = store.preparation(preparedId);
      if (preparation === null) fail(FAILURE.NOT_FOUND, "preparation is missing");
      if (preparation.finalized_at !== null) {
        fail(FAILURE.INVALID_TRANSITION, "finalized preparation cannot be rolled back");
      }
      if (![
        STATUS.PREPARED,
        STATUS.DEGRADED,
        STATUS.ACTIVE,
        STATUS.VERIFIED,
        STATUS.FAILED,
        STATUS.BLOCKED,
        STATUS.UNSUPPORTED,
        STATUS.ROLLED_BACK,
      ].includes(preparation.status)) {
        fail(FAILURE.INVALID_TRANSITION, "preparation cannot be rolled back");
      }
      const candidate = packageRecord(preparation.candidate_package_hash);
      const previous = packageRecord(preparation.previous_package_hash);
      if (candidate === null || previous === null) fail(FAILURE.STATE_CORRUPT, "rollback package record is missing");
      if (!preparationPluginMutated(preparedId)) {
        if (preparationMigrationApplied(preparedId)) {
          fail(FAILURE.STATE_CORRUPT, "applied migration has no preceding durable host quiescence mutation");
        }
        const existing = exactInstalled(operationId, preparation.previous_selector, previous.package_hash);
        const candidatePresent = exactPluginEntry(listPlugins(operationId), preparation.activation_selector);
        const rollbackPresent = exactPluginEntry(listPlugins(operationId), preparation.rollback_selector);
        const marketplaces = listMarketplaces(operationId);
        const candidateMarketplace = store.marketplace(preparation.candidate_marketplace_id);
        const rollbackMarketplace = store.marketplace(preparation.rollback_marketplace_id);
        if (candidateMarketplace === null || rollbackMarketplace === null) {
          fail(FAILURE.STATE_CORRUPT, "no-effect rollback marketplace is missing");
        }
        if (
          existing === null ||
          candidatePresent !== null ||
          rollbackPresent !== null ||
          exactMarketplaceEntry(marketplaces, candidateMarketplace.registration_name) !== null ||
          exactMarketplaceEntry(marketplaces, rollbackMarketplace.registration_name) !== null
        ) {
          fail(FAILURE.HOST_AMBIGUOUS, "host state changed without a durable lifecycle mutation");
        }
        return {
          outcome: {
            ok: true,
            status: STATUS.ROLLED_BACK,
            code: null,
            message: SUCCESS.rollback,
            prepared_id: preparedId,
            package_hash: previous.package_hash,
            rolled_back: true,
            data: null,
          },
          projectionPatch: {
            active_selector: preparation.previous_selector,
            active_package_hash: previous.package_hash,
          },
          preparationPatch: {
            prepared_id: preparedId,
            patch: { status: STATUS.ROLLED_BACK, updated_at: new Date().toISOString() },
          },
        };
      }
      if (
        preparation.plugin_data_snapshot_hash === null ||
        preparation.plugin_data_snapshot_operation_id === null
      ) fail(FAILURE.ROLLBACK_FAILED, "mutated rollback boundary lost its provider snapshot");
      const candidateMarketplace = store.marketplace(preparation.candidate_marketplace_id);
      if (candidateMarketplace === null) fail(FAILURE.STATE_CORRUPT, "rollback candidate marketplace is missing");
      if (
        exactPluginEntry(listPlugins(operationId), preparation.activation_selector) !== null ||
        exactMarketplaceEntry(listMarketplaces(operationId), candidateMarketplace.registration_name) !== null
      ) requireDestructiveHostCapability();
      const lease = acquireLease(operationId, preparation.activation_selector);
      const outcome = rollbackWithin(operationId, preparation, candidate, previous, lease);
      outcome.ok = true;
      outcome.status = STATUS.ROLLED_BACK;
      outcome.code = null;
      outcome.message = SUCCESS.rollback;
      outcome.package_hash = previous.package_hash;
      return {
        outcome,
        projectionPatch: {
          active_selector: preparation.rollback_selector,
          active_package_hash: previous.package_hash,
          previous_selector: preparation.activation_selector,
          previous_package_hash: candidate.package_hash,
        },
        preparationPatch: {
          prepared_id: preparedId,
          patch: { status: STATUS.ROLLED_BACK, updated_at: new Date().toISOString() },
        },
      };
    });

  const uninstall = (preparedId) =>
    execute("uninstall", () => uninstallDescriptor(preparedId), (operationId, descriptor) =>
      resumeUninstall(operationId, descriptor.intent));

  const cancel = (preparedId) =>
    execute("cancel", { preparedId: descriptorText(preparedId, 64), intent: { prepared_id: descriptorText(preparedId, 64) } }, () => {
      requirePreparedId(preparedId);
      const preparation = store.cancelPreparation(preparedId);
      return {
        outcome: {
          ok: true,
          status: STATUS.BLOCKED,
          code: null,
          message: SUCCESS.cancel,
          prepared_id: preparedId,
          package_hash: preparation.candidate_package_hash,
          data: null,
        },
      };
    });

  const finalizationProjectionPatch = (preparation) => {
    const current = store.projection();
    const ownedSelectors = new Set([preparation.activation_selector, preparation.rollback_selector]);
    const activeOwned = current.active_selector !== null && ownedSelectors.has(current.active_selector);
    const previousOwned = current.previous_selector !== null && ownedSelectors.has(current.previous_selector);
    const activeIsCapturedPrevious =
      current.active_selector === preparation.previous_selector &&
      current.active_package_hash === preparation.previous_package_hash;
    const neutralStatus = current.active_selector === null || activeOwned
      ? STATUS.IDLE
      : activeIsCapturedPrevious
        ? STATUS.CAPTURED
        : current.status;
    return {
      ...(activeOwned ? { active_selector: null, active_package_hash: null } : {}),
      ...(current.active_selector === null || activeOwned || previousOwned
        ? { previous_selector: null, previous_package_hash: null }
        : {}),
      status: neutralStatus,
      failure_code:
        neutralStatus === STATUS.IDLE || neutralStatus === STATUS.CAPTURED
          ? null
          : current.failure_code,
    };
  };

  const finalize = (preparedId) =>
    execute("finalize", { preparedId: descriptorText(preparedId, 64), intent: { prepared_id: descriptorText(preparedId, 64) } }, (operationId) => {
      requirePreparedId(preparedId);
      let preparation = store.preparation(preparedId);
      if (preparation === null) fail(FAILURE.NOT_FOUND, "preparation is missing");
      if (![
        STATUS.ROLLED_BACK,
        STATUS.FAILED,
        STATUS.BLOCKED,
        STATUS.UNINSTALLED,
        STATUS.UNSUPPORTED,
      ].includes(preparation.status)) {
        fail(FAILURE.INVALID_TRANSITION, "finalize requires an already terminal preparation");
      }
      if (preparation.finalized_at !== null) {
        assertPreparationHostAbsent(operationId, preparation);
        return {
          outcome: {
            ok: true,
            status: preparation.status,
            code: null,
            message: SUCCESS.finalize,
            prepared_id: preparedId,
            package_hash: preparation.candidate_package_hash,
            data: { finalized_at: preparation.finalized_at, idempotent: true },
          },
          projectionPatch: finalizationProjectionPatch(preparation),
        };
      }
      const plugins = listPlugins(operationId);
      if (
        exactPluginEntry(plugins, preparation.activation_selector) !== null ||
        exactPluginEntry(plugins, preparation.rollback_selector) !== null
      ) fail(FAILURE.INVALID_TRANSITION, "installed lifecycle selector prevents finalization");
      const marketplaces = listMarketplaces(operationId);
      for (const marketplaceId of [preparation.candidate_marketplace_id, preparation.rollback_marketplace_id]) {
        const marketplace = store.marketplace(marketplaceId);
        if (marketplace === null) fail(FAILURE.STATE_CORRUPT, "preparation marketplace is missing");
        if (exactMarketplaceEntry(marketplaces, marketplace.registration_name) !== null) {
          fail(FAILURE.INVALID_TRANSITION, "registered lifecycle marketplace prevents finalization");
        }
        store.setMarketplaceRegistered(marketplace.marketplace_id, false);
      }
      preparation = store.finalizePreparation(preparedId, operationId);
      return {
        outcome: {
          ok: true,
          status: preparation.status,
          code: null,
          message: SUCCESS.finalize,
          prepared_id: preparedId,
          package_hash: preparation.candidate_package_hash,
          data: { finalized_at: preparation.finalized_at, idempotent: false },
        },
        projectionPatch: finalizationProjectionPatch(preparation),
      };
    });

  const cleanup = (request) =>
    execute("cleanup", { intent: { request_received: isPlainObject(request) } }, (operationId) => {
      if (!isPlainObject(request)) fail(FAILURE.INVALID_INPUT, "cleanup request must be an object");
      exactFields(request, ["before", "max_items"], "cleanup request");
      const beforeMs = typeof request.before === "string" ? Date.parse(request.before) : Number.NaN;
      if (
        !Number.isFinite(beforeMs) ||
        new Date(beforeMs).toISOString() !== request.before ||
        beforeMs > Date.now() ||
        !Number.isSafeInteger(request.max_items) ||
        request.max_items < 1 ||
        request.max_items > LIMITS.maxCleanupItems
      ) fail(FAILURE.INVALID_INPUT, "cleanup bounds are invalid");
      const currentProjection = store.projection();
      let cleanupLease = acquireLease(
        operationId,
        currentProjection.active_selector ?? "lifecycle-cleanup@ef-lifecycle-internal",
      );
      cleanupLease = revalidateLease(cleanupLease);
      reconcileOwnedStaging(store.roots.staging, operationLimits(), true);
      reconcileOwnedMarketplaces(true);
      validateContentStores(true);
      const candidates = store.cleanupCandidates({ before: request.before, maxItems: request.max_items });
      let remaining = request.max_items;
      const cleaned = {
        operation_snapshots: 0,
        marketplaces: 0,
        recoveries: 0,
        diagnostics: 0,
        packages: 0,
        snapshots: 0,
      };
      const take = (items) => items.slice(0, remaining);
      for (const item of take(candidates.operationSnapshots)) {
        cleanupLease = revalidateLease(cleanupLease);
        cleanupLease = disposeSnapshotLink(operationId, item, cleanupLease);
        cleaned.operation_snapshots += 1;
        remaining -= 1;
      }
      for (const item of take(candidates.marketplaces)) {
        cleanupLease = revalidateLease(cleanupLease);
        disposeOwnedResource(operationId, "marketplace", item, cleanupLease);
        cleaned.marketplaces += 1;
        remaining -= 1;
      }
      for (const item of take(candidates.recoveries)) {
        cleanupLease = revalidateLease(cleanupLease);
        disposeOwnedResource(operationId, "recovery", item, cleanupLease);
        cleaned.recoveries += 1;
        remaining -= 1;
      }
      for (const item of take(candidates.diagnostics)) {
        store.purgeDiagnostic(item.blob_hash);
        cleaned.diagnostics += 1;
        remaining -= 1;
      }
      for (const item of take(candidates.packages)) {
        cleanupLease = revalidateLease(cleanupLease);
        disposeOwnedResource(operationId, "package", item, cleanupLease);
        cleaned.packages += 1;
        remaining -= 1;
      }
      for (const item of take(candidates.snapshots)) {
        cleanupLease = revalidateLease(cleanupLease);
        disposeOwnedResource(operationId, "snapshot", item, cleanupLease);
        cleaned.snapshots += 1;
        remaining -= 1;
      }
      releaseLease(operationId, cleanupLease);
      return {
        outcome: {
          ok: true,
          status: STATUS.IDLE,
          code: null,
          message: SUCCESS.cleanup,
          data: { cleaned },
        },
        projectionPatch: {
          status: currentProjection.status,
          failure_code: currentProjection.failure_code,
        },
      };
    });

  const close = () => {
    if (closed) return makeResult("close", { ok: true, status: STATUS.IDLE, code: null, message: SUCCESS.close }, null);
    let activeAtClose = null;
    try {
      store.withOwnership((ownerEpoch) => {
        activeOwnerEpoch = ownerEpoch;
        activeDeadline = Date.now() + config.maxOperationMs;
        try {
          revalidatePrivateRoots();
          store.initialize({ binding: composition.binding, bindingHash: composition.bindingHash });
          revalidatePrivateRoots();
          reconcilePending();
          activeAtClose = activeHash();
          startupReconciliation = null;
        } finally {
          activeDeadline = null;
          activeOwnerEpoch = null;
        }
      });
      store.close();
      closed = true;
      return makeResult("close", { ok: true, status: STATUS.IDLE, code: null, message: SUCCESS.close }, activeAtClose);
    } catch (cause) {
      activeDeadline = null;
      activeOwnerEpoch = null;
      return makeResult("close", errorOutcome(cause), activeAtClose);
    }
  };

  try {
    startupReconciliation = store.withOwnership((ownerEpoch) => {
      activeOwnerEpoch = ownerEpoch;
      activeDeadline = Date.now() + config.maxOperationMs;
      try {
        revalidatePrivateRoots();
        store.initialize({ binding: composition.binding, bindingHash: composition.bindingHash });
        revalidatePrivateRoots();
        return reconcilePending();
      } finally {
        activeDeadline = null;
        activeOwnerEpoch = null;
      }
    });
  } catch (cause) {
    activeDeadline = null;
    activeOwnerEpoch = null;
    startupReconciliation = makeResult("reconcile", errorOutcome(cause), null);
  }
  return Object.freeze({
    probeHost,
    capture,
    prepare,
    activate,
    verify,
    rollback,
    uninstall,
    cancel,
    finalize,
    cleanup,
    close,
    dispose: close,
  });
}
