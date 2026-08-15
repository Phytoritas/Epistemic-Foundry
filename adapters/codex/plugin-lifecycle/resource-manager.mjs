import fs from "node:fs";
import path from "node:path";
import {
  FAILURE,
  STATUS,
  LifecycleError,
  boundedJson,
  canonicalJson,
  exactFields,
  fail,
} from "./core.mjs";
import { marketplaceDocument, sameAbsolutePath } from "./contracts.mjs";

const DISPOSAL_FIELDS = Object.freeze([
  "resource_type",
  "resource_id",
  "root",
  "expected_hash",
  "resource_tree_hash",
  "plugin_name",
  "registration_name",
  "lease_id",
  "effect_id",
  "quarantine_path",
  "private_root_capability_id",
]);

export function createResourceManager({
  store,
  inspectTree,
  checkDeadline,
  revalidatePrivateRoots,
  effectId,
  verifyPackageRecord,
  privateRootCapabilityId,
  durableFsyncDirectory,
  durableQuarantineDirectory,
  durableRemoveQuarantine,
}) {
  const reconciliationFailure = (message) =>
    fail(FAILURE.RECONCILIATION_REQUIRED, message, STATUS.BLOCKED);

  const exactIntent = (intent) => {
    exactFields(intent, DISPOSAL_FIELDS, "resource disposal intent");
    if (
      intent.private_root_capability_id !== privateRootCapabilityId ||
      !/^eff_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u.test(intent.effect_id)
    ) reconciliationFailure("resource disposal capability or effect binding differs");
  };

  const filesystemRoot = (intent) => {
    if (intent.resource_type === "marketplace") {
      if (!/^ef-lifecycle-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}$/u.test(intent.resource_id)) {
        reconciliationFailure("marketplace cleanup id is invalid");
      }
      return path.join(store.roots.marketplaces, intent.resource_id);
    }
    if (intent.resource_type === "package") {
      if (!/^sha256:[0-9a-f]{64}$/u.test(intent.expected_hash) || intent.resource_id !== intent.expected_hash) {
        reconciliationFailure("content cleanup identity is invalid");
      }
      return path.join(store.roots.packages, intent.expected_hash.slice(7));
    }
    return null;
  };

  const validateQuarantineBinding = (intent, expectedRoot) => {
    if (expectedRoot === null) {
      if (intent.quarantine_path !== null || intent.resource_tree_hash !== null) {
        reconciliationFailure("non-filesystem disposal names a filesystem identity");
      }
      return;
    }
    const expectedQuarantine = path.join(store.roots.recovery, `quarantine-${intent.effect_id}`);
    if (
      typeof intent.root !== "string" ||
      typeof intent.quarantine_path !== "string" ||
      !path.isAbsolute(intent.root) ||
      !path.isAbsolute(intent.quarantine_path) ||
      !sameAbsolutePath(intent.root, expectedRoot) ||
      !sameAbsolutePath(intent.quarantine_path, expectedQuarantine) ||
      path.dirname(intent.quarantine_path) !== store.roots.recovery ||
      !/^sha256:[0-9a-f]{64}$/u.test(intent.resource_tree_hash)
    ) reconciliationFailure("resource disposal escaped its exact owned or quarantine root");
  };

  const validateLayoutAt = (intent, targetRoot, recovery = false) => {
    try {
      if (intent.resource_type === "marketplace") {
        const rootIdentity = inspectTree(targetRoot);
        if (rootIdentity.tree_hash !== intent.resource_tree_hash) {
          fail(FAILURE.STATE_CORRUPT, "marketplace cleanup resource hash drifted");
        }
        if (rootIdentity.entry_count < 4) fail(FAILURE.STATE_CORRUPT, "marketplace cleanup tree is incomplete");
        if (canonicalJson(fs.readdirSync(targetRoot).sort()) !== canonicalJson([".agents", "plugins"])) {
          fail(FAILURE.STATE_CORRUPT, "marketplace cleanup tree has unknown top-level entries");
        }
        if (
          canonicalJson(fs.readdirSync(path.join(targetRoot, ".agents")).sort()) !== canonicalJson(["plugins"]) ||
          canonicalJson(fs.readdirSync(path.join(targetRoot, ".agents", "plugins")).sort()) !==
            canonicalJson(["marketplace.json"]) ||
          canonicalJson(fs.readdirSync(path.join(targetRoot, "plugins")).sort()) !==
            canonicalJson([intent.plugin_name])
        ) fail(FAILURE.STATE_CORRUPT, "marketplace cleanup layout differs");
        const payload = inspectTree(path.join(targetRoot, "plugins", intent.plugin_name), {
          pluginName: intent.plugin_name,
        });
        if (payload.tree_hash !== intent.expected_hash) fail(FAILURE.STATE_CORRUPT, "marketplace cleanup payload drifted");
        const descriptorPath = path.join(targetRoot, ".agents", "plugins", "marketplace.json");
        const descriptorStat = fs.lstatSync(descriptorPath, { bigint: true });
        if (descriptorStat.isSymbolicLink() || !descriptorStat.isFile() || descriptorStat.nlink !== 1n) {
          fail(FAILURE.STATE_CORRUPT, "marketplace cleanup descriptor is not ordinary");
        }
        let descriptor;
        try {
          descriptor = boundedJson(JSON.parse(fs.readFileSync(descriptorPath, "utf8")), "marketplace cleanup descriptor");
        } catch (cause) {
          if (cause instanceof LifecycleError) throw cause;
          fail(FAILURE.STATE_CORRUPT, "marketplace cleanup descriptor is invalid");
        }
        if (canonicalJson(descriptor) !== canonicalJson(marketplaceDocument(intent.registration_name, intent.plugin_name))) {
          fail(FAILURE.STATE_CORRUPT, "marketplace cleanup descriptor drifted");
        }
        return rootIdentity;
      } else if (intent.resource_type === "package") {
        const rootIdentity = inspectTree(targetRoot);
        if (rootIdentity.tree_hash !== intent.resource_tree_hash) {
          fail(FAILURE.STATE_CORRUPT, "content cleanup resource hash drifted");
        }
        if (canonicalJson(fs.readdirSync(targetRoot).sort()) !== canonicalJson(["data"])) {
          fail(FAILURE.STATE_CORRUPT, "content cleanup container is not closed");
        }
        const identity = inspectTree(path.join(targetRoot, "data"), { pluginName: intent.plugin_name });
        if (identity.tree_hash !== intent.expected_hash) fail(FAILURE.STATE_CORRUPT, "content cleanup identity drifted");
        return rootIdentity;
      } else {
        fail(FAILURE.STATE_CORRUPT, "filesystem disposal type is unknown");
      }
    } catch (cause) {
      if (recovery) reconciliationFailure("quarantined or original resource identity no longer matches its intent");
      throw cause;
    }
  };

  const markDisposed = (intent) => {
    if (intent.resource_type === "marketplace") store.markMarketplaceDisposed(intent.resource_id);
    else if (intent.resource_type === "package") store.markPackageDisposed(intent.resource_id);
    else if (intent.resource_type === "snapshot") store.markSnapshotDisposed(intent.resource_id);
    else store.markRecoveryDisposed(intent.resource_id);
  };

  const validateResourceDisposal = (intent) => {
    exactIntent(intent);
    checkDeadline();
    revalidatePrivateRoots();
    const expectedRoot = filesystemRoot(intent);
    validateQuarantineBinding(intent, expectedRoot);
    if (expectedRoot !== null) {
      if (!fs.existsSync(expectedRoot) || fs.existsSync(intent.quarantine_path)) {
        fail(FAILURE.STATE_CORRUPT, "resource disposal boundary is not pristine");
      }
      validateLayoutAt(intent, expectedRoot, false);
    } else if (intent.resource_type === "snapshot") {
      if (
        !/^sha256:[0-9a-f]{64}$/u.test(intent.expected_hash) ||
        intent.resource_id !== intent.expected_hash ||
        intent.root !== null ||
        store.snapshotRecord(intent.resource_id) === null
      ) fail(FAILURE.STATE_CORRUPT, "provider snapshot cleanup identity is invalid");
    } else if (intent.resource_type === "recovery") {
      if (intent.root !== null) {
        fail(FAILURE.HOST_UNSUPPORTED, "filesystem recovery payload cleanup is unsupported", STATUS.UNSUPPORTED);
      }
    } else {
      fail(FAILURE.STATE_CORRUPT, "resource disposal type is unknown");
    }
    revalidatePrivateRoots();
    checkDeadline();
  };

  const applyResourceDisposal = (intent) => {
    exactIntent(intent);
    checkDeadline();
    revalidatePrivateRoots();
    const expectedRoot = filesystemRoot(intent);
    validateQuarantineBinding(intent, expectedRoot);
    if (expectedRoot === null) {
      if (!store.resourceDisposed(intent.resource_type, intent.resource_id)) markDisposed(intent);
      revalidatePrivateRoots();
      checkDeadline();
      return;
    }

    const originalExists = fs.existsSync(expectedRoot);
    const quarantineExists = fs.existsSync(intent.quarantine_path);
    if (originalExists && quarantineExists) {
      reconciliationFailure("resource exists in both its original and quarantine locations");
    }
    const disposed = store.resourceDisposed(intent.resource_type, intent.resource_id);
    if (quarantineExists) {
      const quarantineIdentity = validateLayoutAt(intent, intent.quarantine_path, true);
      if (fs.existsSync(expectedRoot)) reconciliationFailure("resource path was replaced during quarantine validation");
      if (!disposed) markDisposed(intent);
      durableRemoveQuarantine(intent.quarantine_path, quarantineIdentity.tree_hash);
    } else if (originalExists) {
      if (disposed) reconciliationFailure("a replacement appeared at a disposed resource path");
      validateLayoutAt(intent, expectedRoot, true);
      durableQuarantineDirectory(expectedRoot, intent.quarantine_path, intent.resource_tree_hash);
      const quarantineIdentity = validateLayoutAt(intent, intent.quarantine_path, true);
      if (fs.existsSync(expectedRoot)) reconciliationFailure("resource path was replaced during quarantine transition");
      markDisposed(intent);
      durableRemoveQuarantine(intent.quarantine_path, quarantineIdentity.tree_hash);
    } else {
      if (!disposed) reconciliationFailure("resource disappeared before its quarantine transition resolved");
      durableFsyncDirectory(store.roots.recovery);
    }
    revalidatePrivateRoots();
    checkDeadline();
  };

  const disposeOwnedResource = (operationId, resourceType, row, lease) => {
    const marketplacePackage = resourceType === "marketplace"
      ? verifyPackageRecord(store.packageRecord(row.package_hash))
      : null;
    if (resourceType === "marketplace" && marketplacePackage === null) {
      fail(FAILURE.STATE_CORRUPT, "marketplace cleanup package is missing");
    }
    const id = effectId();
    const filesystemResource = resourceType === "marketplace" || resourceType === "package";
    const resourceRoot = resourceType === "marketplace"
      ? row.root
      : resourceType === "package"
        ? path.dirname(row.preserved_root)
        : null;
    const intent = {
      resource_type: resourceType,
      resource_id:
        resourceType === "marketplace"
          ? row.marketplace_id
          : resourceType === "package"
            ? row.package_hash
            : resourceType === "snapshot"
              ? row.snapshot_hash
              : row.operation_id,
      root:
        resourceType === "marketplace"
          ? row.root
          : resourceType === "package"
            ? path.dirname(row.preserved_root)
            : resourceType === "snapshot"
              ? null
              : row.backup_root,
      expected_hash:
        resourceType === "marketplace" || resourceType === "package"
          ? row.package_hash
          : row.snapshot_hash,
      resource_tree_hash: filesystemResource ? inspectTree(resourceRoot).tree_hash : null,
      plugin_name:
        resourceType === "marketplace"
          ? marketplacePackage.plugin_name
          : resourceType === "package"
            ? row.plugin_name
            : null,
      registration_name: resourceType === "marketplace" ? row.registration_name : null,
      lease_id: lease.lease_id,
      effect_id: id,
      quarantine_path: filesystemResource ? path.join(store.roots.recovery, `quarantine-${id}`) : null,
      private_root_capability_id: privateRootCapabilityId,
    };
    validateResourceDisposal(intent);
    store.intentEffect({ operationId, effectId: id, kind: "RESOURCE_DISPOSE", intent });
    applyResourceDisposal(intent);
    store.resolveEffect({ effectId: id, resolution: { status: "APPLIED" } });
  };

  return Object.freeze({ applyResourceDisposal, disposeOwnedResource });
}
