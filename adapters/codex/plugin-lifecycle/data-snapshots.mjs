import {
  FAILURE,
  LIMITS,
  STATUS,
  canonicalJson,
  exactFields,
  fail,
  hashJson,
} from "./core.mjs";
import { dataSnapshotPortReady } from "./contracts.mjs";

export function createDataSnapshotManager({
  store,
  config,
  composition,
  ownerEpoch,
  effectId,
  portCall,
  revalidateLease,
}) {
  const metadataFor = (value) => ({
    capability_id: composition.dataSnapshot.capability_id,
    snapshot_hash: value.snapshot_hash,
    entry_count: value.entry_count,
    file_count: value.file_count,
    byte_size: value.byte_size,
  });

  const verifySnapshotRecord = (record) => {
    if (record === null) fail(FAILURE.STATE_CORRUPT, "snapshot record is missing");
    let metadata;
    try {
      metadata = JSON.parse(record.inventory_json);
    } catch {
      fail(FAILURE.STATE_CORRUPT, "provider snapshot metadata is invalid");
    }
    const expected = metadataFor(record);
    if (
      !/^sha256:[0-9a-f]{64}$/u.test(record.snapshot_hash) ||
      record.preserved_root !== "" ||
      record.inventory_bytes !== Buffer.byteLength(record.inventory_json, "utf8") ||
      canonicalJson(metadata) !== canonicalJson(expected) ||
      !Number.isSafeInteger(record.entry_count) ||
      record.entry_count < 0 ||
      record.entry_count > LIMITS.maxEntries ||
      !Number.isSafeInteger(record.file_count) ||
      record.file_count < 0 ||
      record.file_count > record.entry_count ||
      !Number.isSafeInteger(record.byte_size) ||
      record.byte_size < 0 ||
      record.byte_size > LIMITS.maxTreeBytes
    ) fail(FAILURE.STATE_CORRUPT, "provider snapshot record differs from its bounded identity");
    return record;
  };

  const captureRecord = (receipt) => {
    const metadata = metadataFor(receipt);
    const inventoryJson = canonicalJson(metadata);
    return {
      snapshot_hash: receipt.snapshot_hash,
      entry_count: receipt.entry_count,
      file_count: receipt.file_count,
      byte_size: receipt.byte_size,
      inventory_bytes: Buffer.byteLength(inventoryJson, "utf8"),
      inventory_json: inventoryJson,
      preserved_root: "",
    };
  };

  const validateCaptureReceipt = (value, { operationId, expectedEffectId, leaseId, allowNotApplied = false }) => {
    exactFields(
      value,
      [
        "status",
        "operation_id",
        "owner_epoch",
        "effect_id",
        "phase",
        "snapshot_hash",
        "capability_id",
        "external_snapshot_id",
        "lease_id",
        "current_token",
        "entry_count",
        "file_count",
        "byte_size",
        "receipt_hash",
      ],
      "data snapshot capture receipt",
    );
    const preimage = {
      status: value.status,
      operation_id: value.operation_id,
      owner_epoch: value.owner_epoch,
      effect_id: value.effect_id,
      phase: value.phase,
      snapshot_hash: value.snapshot_hash,
      capability_id: value.capability_id,
      external_snapshot_id: value.external_snapshot_id,
      lease_id: value.lease_id,
      current_token: value.current_token,
      entry_count: value.entry_count,
      file_count: value.file_count,
      byte_size: value.byte_size,
    };
    const captured = value.status === "CAPTURED";
    const notApplied = allowNotApplied && value.status === "NOT_APPLIED";
    if (
      (!captured && !notApplied) ||
      value.operation_id !== operationId ||
      value.owner_epoch !== ownerEpoch() ||
      value.effect_id !== expectedEffectId ||
      value.phase !== "CAPTURE" ||
      value.capability_id !== composition.dataSnapshot.capability_id ||
      value.lease_id !== leaseId ||
      value.receipt_hash !== hashJson("PLUGIN_LIFECYCLE_V3_DATA_SNAPSHOT_CAPTURE_RECEIPT", preimage) ||
      (captured && (
        typeof value.snapshot_hash !== "string" ||
        !/^sha256:[0-9a-f]{64}$/u.test(value.snapshot_hash) ||
        typeof value.external_snapshot_id !== "string" ||
        value.external_snapshot_id.length === 0 ||
        typeof value.current_token !== "string" ||
        value.current_token.length === 0 ||
        !Number.isSafeInteger(value.entry_count) ||
        value.entry_count < 0 ||
        value.entry_count > LIMITS.maxEntries ||
        !Number.isSafeInteger(value.file_count) ||
        value.file_count < 0 ||
        value.file_count > value.entry_count ||
        !Number.isSafeInteger(value.byte_size) ||
        value.byte_size < 0 ||
        value.byte_size > LIMITS.maxTreeBytes
      )) ||
      (notApplied && (
        value.snapshot_hash !== null ||
        value.external_snapshot_id !== null ||
        value.current_token !== null ||
        value.entry_count !== 0 ||
        value.file_count !== 0 ||
        value.byte_size !== 0
      ))
    ) fail(FAILURE.HOST_UNSUPPORTED, "data snapshot capture receipt is not durable and operation-bound", STATUS.UNSUPPORTED);
    return value;
  };

  const validateMutationReceipt = (
    value,
    {
      operationId,
      expectedEffectId,
      phase,
      snapshotHash,
      externalSnapshotId,
      leaseId,
      currentToken = null,
      allowNotApplied = false,
    },
  ) => {
    exactFields(
      value,
      [
        "status",
        "operation_id",
        "owner_epoch",
        "effect_id",
        "phase",
        "snapshot_hash",
        "capability_id",
        "external_snapshot_id",
        "lease_id",
        "current_token",
        "receipt_hash",
      ],
      "data snapshot receipt",
    );
    const expectedStatus = { RESTORE: "RESTORED", DISPOSE: "DISPOSED" }[phase];
    if (expectedStatus === undefined) fail(FAILURE.STATE_CORRUPT, "data snapshot phase is unknown");
    const preimage = {
      status: value.status,
      operation_id: value.operation_id,
      owner_epoch: value.owner_epoch,
      effect_id: value.effect_id,
      phase: value.phase,
      snapshot_hash: value.snapshot_hash,
      capability_id: value.capability_id,
      external_snapshot_id: value.external_snapshot_id,
      lease_id: value.lease_id,
      current_token: value.current_token,
    };
    if (
      ![expectedStatus, ...(allowNotApplied ? ["NOT_APPLIED"] : [])].includes(value.status) ||
      value.operation_id !== operationId ||
      value.owner_epoch !== ownerEpoch() ||
      value.effect_id !== expectedEffectId ||
      value.phase !== phase ||
      value.snapshot_hash !== snapshotHash ||
      value.capability_id !== composition.dataSnapshot.capability_id ||
      value.external_snapshot_id !== externalSnapshotId ||
      value.lease_id !== leaseId ||
      value.current_token !== currentToken ||
      value.receipt_hash !== hashJson("PLUGIN_LIFECYCLE_V3_DATA_SNAPSHOT_RECEIPT", preimage)
    ) fail(FAILURE.HOST_UNSUPPORTED, "data snapshot receipt is not durable and operation-bound", STATUS.UNSUPPORTED);
    return value;
  };

  const validateCompareReceipt = (value, { operationId, expectedEffectId, snapshot, link }) => {
    exactFields(
      value,
      [
        "status",
        "operation_id",
        "owner_epoch",
        "effect_id",
        "snapshot_hash",
        "capability_id",
        "external_snapshot_id",
        "current_token",
        "receipt_hash",
      ],
      "data snapshot comparison receipt",
    );
    const preimage = {
      status: value.status,
      operation_id: value.operation_id,
      owner_epoch: value.owner_epoch,
      effect_id: value.effect_id,
      snapshot_hash: value.snapshot_hash,
      capability_id: value.capability_id,
      external_snapshot_id: value.external_snapshot_id,
      current_token: value.current_token,
    };
    if (
      !["MATCH", "DIFF"].includes(value.status) ||
      value.operation_id !== operationId ||
      value.owner_epoch !== ownerEpoch() ||
      value.effect_id !== expectedEffectId ||
      value.snapshot_hash !== snapshot.snapshot_hash ||
      value.capability_id !== link.capability_id ||
      value.external_snapshot_id !== link.external_snapshot_id ||
      typeof value.current_token !== "string" ||
      value.current_token.length === 0 ||
      value.receipt_hash !== hashJson("PLUGIN_LIFECYCLE_V3_DATA_COMPARE_RECEIPT", preimage)
    ) fail(FAILURE.HOST_UNSUPPORTED, "data comparison is not fresh and snapshot-bound", STATUS.UNSUPPORTED);
    return value;
  };

  const capturePayload = (operationId, id, lease) => ({
    operation_id: operationId,
    owner_epoch: ownerEpoch(),
    effect_id: id,
    plugin_data_root: config.pluginDataRoot,
    capability_id: composition.dataSnapshot.capability_id,
    max_entries: LIMITS.maxEntries,
    max_total_bytes: LIMITS.maxTreeBytes,
    max_file_bytes: LIMITS.maxFileBytes,
    lease,
  });

  const comparePluginData = (operationId, lease, snapshot, captureOperationId) => {
    verifySnapshotRecord(snapshot);
    const link = store.operationSnapshot(captureOperationId);
    if (
      link === null ||
      link.snapshot_hash !== snapshot.snapshot_hash ||
      link.capability_id !== composition.dataSnapshot.capability_id ||
      link.status === "DISPOSED"
    ) fail(FAILURE.STATE_CORRUPT, "data comparison lost its exact provider snapshot link");
    const currentLease = revalidateLease(lease);
    const id = effectId();
    store.intentEffect({
      operationId,
      effectId: id,
      kind: "DATA_SNAPSHOT_COMPARE",
      intent: {
        capture_operation_id: captureOperationId,
        snapshot_hash: snapshot.snapshot_hash,
        capability_id: link.capability_id,
        external_snapshot_id: link.external_snapshot_id,
      },
    });
    const receipt = validateCompareReceipt(
      portCall(
        config.dataSnapshotPort,
        "compare",
        {
          operation_id: operationId,
          owner_epoch: ownerEpoch(),
          effect_id: id,
          capture_operation_id: captureOperationId,
          plugin_data_root: config.pluginDataRoot,
          snapshot_hash: snapshot.snapshot_hash,
          capability_id: link.capability_id,
          external_snapshot_id: link.external_snapshot_id,
          lease: currentLease,
        },
        "data snapshot",
      ),
      { operationId, expectedEffectId: id, snapshot, link },
    );
    store.resolveEffect({
      effectId: id,
      resolution: {
        status: receipt.status,
        receipt_hash: receipt.receipt_hash,
        current_token: receipt.current_token,
      },
    });
    return {
      matches: receipt.status === "MATCH",
      current_hash: null,
      current_token: receipt.current_token,
      lease: currentLease,
    };
  };

  const persistCapture = (operationId, id, receipt) => {
    const record = store.saveSnapshot(captureRecord(receipt));
    verifySnapshotRecord(record);
    const link = store.resolveSnapshotCapture({
      effectId: id,
      snapshotLink: {
        snapshot_hash: record.snapshot_hash,
        capability_id: receipt.capability_id,
        external_snapshot_id: receipt.external_snapshot_id,
        capture_receipt_hash: receipt.receipt_hash,
      },
      resolution: {
        status: "APPLIED",
        receipt_hash: receipt.receipt_hash,
        current_token: receipt.current_token,
      },
    });
    return { record, link, capture_operation_id: operationId };
  };

  const ensureStableSnapshotBoundary = (captureOperationId, lease) => {
    const link = store.operationSnapshot(captureOperationId);
    if (
      link === null ||
      link.status === "DISPOSED" ||
      link.capability_id !== composition.dataSnapshot.capability_id
    ) fail(FAILURE.STATE_CORRUPT, "provider snapshot boundary lost its exact link");
    const snapshot = verifySnapshotRecord(store.snapshotRecord(link.snapshot_hash));
    const effects = store.effects(captureOperationId);
    const capture = effects.find((item) => item.kind === "DATA_SNAPSHOT_CAPTURE");
    if (capture === undefined || capture.resolution_json === null) {
      fail(FAILURE.STATE_CORRUPT, "provider snapshot boundary lost its capture resolution");
    }
    let captureResolution;
    try {
      captureResolution = JSON.parse(capture.resolution_json);
    } catch {
      fail(FAILURE.STATE_CORRUPT, "provider capture resolution is invalid");
    }
    try {
      exactFields(
        captureResolution,
        ["status", "receipt_hash", "current_token"],
        "provider capture resolution",
      );
    } catch {
      fail(FAILURE.STATE_CORRUPT, "provider capture resolution is outside its closed shape");
    }
    if (
      captureResolution.status !== "APPLIED" ||
      captureResolution.receipt_hash !== link.capture_receipt_hash ||
      !/^sha256:[0-9a-f]{64}$/u.test(captureResolution.receipt_hash) ||
      typeof captureResolution.current_token !== "string" ||
      captureResolution.current_token.length === 0
    ) fail(FAILURE.STATE_CORRUPT, "provider capture resolution is not snapshot-bound");

    const comparisons = effects.filter((item) => {
      if (item.kind !== "DATA_SNAPSHOT_COMPARE" || item.ordinal <= capture.ordinal || item.resolution_json === null) {
        return false;
      }
      let intent;
      try {
        intent = JSON.parse(item.intent_json);
      } catch {
        fail(FAILURE.STATE_CORRUPT, "provider comparison intent is invalid");
      }
      try {
        exactFields(
          intent,
          ["capture_operation_id", "snapshot_hash", "capability_id", "external_snapshot_id"],
          "provider comparison intent",
        );
      } catch {
        fail(FAILURE.STATE_CORRUPT, "provider comparison intent is outside its closed shape");
      }
      let resolution;
      try {
        resolution = JSON.parse(item.resolution_json);
      } catch {
        fail(FAILURE.STATE_CORRUPT, "provider comparison resolution is invalid");
      }
      return resolution?.status !== "NOT_APPLIED" &&
        intent.capture_operation_id === captureOperationId &&
        intent.snapshot_hash === snapshot.snapshot_hash &&
        intent.capability_id === link.capability_id &&
        intent.external_snapshot_id === link.external_snapshot_id;
    });
    let currentLease = lease;
    if (comparisons.length === 0) {
      if (currentLease === null) {
        fail(FAILURE.QUIESCENCE_REQUIRED, "incomplete snapshot boundary lost quiescence", STATUS.BLOCKED);
      }
      const comparison = comparePluginData(captureOperationId, currentLease, snapshot, captureOperationId);
      currentLease = comparison.lease;
      return {
        stable: comparison.matches && comparison.current_token === captureResolution.current_token,
        snapshot,
        lease: currentLease,
      };
    }
    const first = comparisons.sort((left, right) => left.ordinal - right.ordinal)[0];
    let comparisonResolution;
    try {
      comparisonResolution = JSON.parse(first.resolution_json);
    } catch {
      fail(FAILURE.STATE_CORRUPT, "provider comparison resolution is invalid");
    }
    try {
      exactFields(
        comparisonResolution,
        ["status", "receipt_hash", "current_token"],
        "provider comparison resolution",
      );
    } catch {
      fail(FAILURE.STATE_CORRUPT, "provider comparison resolution is outside its closed shape");
    }
    if (
      !["MATCH", "DIFF"].includes(comparisonResolution.status) ||
      typeof comparisonResolution.receipt_hash !== "string" ||
      !/^sha256:[0-9a-f]{64}$/u.test(comparisonResolution.receipt_hash) ||
      typeof comparisonResolution.current_token !== "string" ||
      comparisonResolution.current_token.length === 0
    ) fail(FAILURE.STATE_CORRUPT, "provider comparison resolution is not closed");
    return {
      stable:
        comparisonResolution.status === "MATCH" &&
        comparisonResolution.current_token === captureResolution.current_token,
      snapshot,
      lease: currentLease,
    };
  };

  const snapshotPluginData = (operationId, lease) => {
    if (!dataSnapshotPortReady(config.dataSnapshotPort)) {
      fail(FAILURE.HOST_UNSUPPORTED, "full-filesystem data snapshot port is unavailable", STATUS.UNSUPPORTED);
    }
    let currentLease = revalidateLease(lease);
    store.ensureSnapshotCapacity(LIMITS.maxEntries, LIMITS.maxTreeBytes);
    const id = effectId();
    store.intentEffect({
      operationId,
      effectId: id,
      kind: "DATA_SNAPSHOT_CAPTURE",
      intent: {
        operation_id: operationId,
        owner_epoch: ownerEpoch(),
        plugin_data_root: config.pluginDataRoot,
        capability_id: composition.dataSnapshot.capability_id,
        lease_id: currentLease.lease_id,
        max_entries: LIMITS.maxEntries,
        max_total_bytes: LIMITS.maxTreeBytes,
        max_file_bytes: LIMITS.maxFileBytes,
      },
    });
    const receipt = validateCaptureReceipt(
      portCall(config.dataSnapshotPort, "capture", capturePayload(operationId, id, currentLease), "data snapshot"),
      { operationId, expectedEffectId: id, leaseId: currentLease.lease_id },
    );
    currentLease = revalidateLease(currentLease);
    const captured = persistCapture(operationId, id, receipt);
    const comparison = comparePluginData(operationId, currentLease, captured.record, operationId);
    if (!comparison.matches || comparison.current_token !== receipt.current_token) {
      fail(FAILURE.PLUGIN_DATA_CHANGED, "plugin data changed across the provider snapshot boundary");
    }
    return {
      ...captured.record,
      capture_operation_id: operationId,
      external_snapshot_id: captured.link.external_snapshot_id,
      lease: comparison.lease,
    };
  };

  const restorePluginData = (
    operationId,
    lease,
    snapshot,
    captureOperationId,
    _expectedCurrentHash,
    expectedCurrentToken,
  ) => {
    if (!dataSnapshotPortReady(config.dataSnapshotPort)) {
      fail(FAILURE.HOST_UNSUPPORTED, "full-filesystem data restore port is unavailable", STATUS.UNSUPPORTED);
    }
    verifySnapshotRecord(snapshot);
    const link = store.operationSnapshot(captureOperationId);
    if (
      link === null ||
      link.snapshot_hash !== snapshot.snapshot_hash ||
      link.capability_id !== composition.dataSnapshot.capability_id ||
      link.status === "DISPOSED"
    ) fail(FAILURE.STATE_CORRUPT, "durable provider snapshot link is unavailable");
    if (typeof expectedCurrentToken !== "string" || expectedCurrentToken.length === 0) {
      fail(FAILURE.PLUGIN_DATA_CHANGED, "plugin data restore lacks the provider current-state token");
    }
    let currentLease = revalidateLease(lease);
    const id = effectId();
    store.intentEffect({
      operationId,
      effectId: id,
      kind: "DATA_SNAPSHOT_RESTORE",
      intent: {
        operation_id: operationId,
        owner_epoch: ownerEpoch(),
        capture_operation_id: captureOperationId,
        snapshot_hash: snapshot.snapshot_hash,
        external_snapshot_id: link.external_snapshot_id,
        expected_current_token: expectedCurrentToken,
        plugin_data_root: config.pluginDataRoot,
        capability_id: link.capability_id,
        lease_id: currentLease.lease_id,
      },
    });
    const receipt = validateMutationReceipt(
      portCall(
        config.dataSnapshotPort,
        "restore",
        {
          operation_id: operationId,
          owner_epoch: ownerEpoch(),
          effect_id: id,
          capture_operation_id: captureOperationId,
          plugin_data_root: config.pluginDataRoot,
          snapshot_hash: snapshot.snapshot_hash,
          external_snapshot_id: link.external_snapshot_id,
          capability_id: link.capability_id,
          expected_current_token: expectedCurrentToken,
          lease: currentLease,
        },
        "data snapshot",
      ),
      {
        operationId,
        expectedEffectId: id,
        phase: "RESTORE",
        snapshotHash: snapshot.snapshot_hash,
        externalSnapshotId: link.external_snapshot_id,
        leaseId: currentLease.lease_id,
        currentToken: expectedCurrentToken,
      },
    );
    currentLease = revalidateLease(currentLease);
    store.resolveSnapshotRestore({
      effectId: id,
      captureOperationId,
      receiptHash: receipt.receipt_hash,
      resolution: { status: "APPLIED", receipt_hash: receipt.receipt_hash },
    });
    const comparison = comparePluginData(operationId, currentLease, snapshot, captureOperationId);
    if (!comparison.matches) fail(FAILURE.ROLLBACK_FAILED, "provider restore did not reproduce the exact snapshot");
    return comparison.lease;
  };

  const disposeSnapshotLink = (operationId, link, lease) => {
    if (link.status === "DISPOSED") return lease;
    if (!dataSnapshotPortReady(config.dataSnapshotPort)) {
      fail(FAILURE.HOST_UNSUPPORTED, "full-filesystem data snapshot disposal is unavailable", STATUS.UNSUPPORTED);
    }
    let currentLease = revalidateLease(lease);
    verifySnapshotRecord(store.snapshotRecord(link.snapshot_hash));
    const id = effectId();
    store.intentEffect({
      operationId,
      effectId: id,
      kind: "DATA_SNAPSHOT_DISPOSE",
      intent: {
        capture_operation_id: link.operation_id,
        snapshot_hash: link.snapshot_hash,
        capability_id: link.capability_id,
        external_snapshot_id: link.external_snapshot_id,
        lease_id: currentLease.lease_id,
      },
    });
    const receipt = validateMutationReceipt(
      portCall(
        config.dataSnapshotPort,
        "dispose",
        {
          operation_id: operationId,
          owner_epoch: ownerEpoch(),
          effect_id: id,
          capture_operation_id: link.operation_id,
          snapshot_hash: link.snapshot_hash,
          capability_id: link.capability_id,
          external_snapshot_id: link.external_snapshot_id,
          lease: currentLease,
        },
        "data snapshot",
      ),
      {
        operationId,
        expectedEffectId: id,
        phase: "DISPOSE",
        snapshotHash: link.snapshot_hash,
        externalSnapshotId: link.external_snapshot_id,
        leaseId: currentLease.lease_id,
      },
    );
    currentLease = revalidateLease(currentLease);
    store.resolveSnapshotDispose({
      effectId: id,
      captureOperationId: link.operation_id,
      receiptHash: receipt.receipt_hash,
      resolution: { status: "APPLIED", receipt_hash: receipt.receipt_hash },
    });
    return currentLease;
  };

  const reconcileEffect = ({ operation, effect, intent, recoveredLease }) => {
    if (![
      "DATA_SNAPSHOT_CAPTURE",
      "DATA_SNAPSHOT_RESTORE",
      "DATA_SNAPSHOT_DISPOSE",
      "DATA_SNAPSHOT_COMPARE",
    ].includes(effect.kind)) return { handled: false, recoveredLease };
    if (
      !Object.hasOwn(intent, "capability_id") ||
      intent.capability_id !== composition.dataSnapshot.capability_id ||
      config.dataSnapshotPort?.capability_id !== composition.dataSnapshot.capability_id
    ) fail(FAILURE.HOST_UNSUPPORTED, "pending data capability identity differs", STATUS.UNSUPPORTED);
    if (effect.kind === "DATA_SNAPSHOT_COMPARE") {
      store.resolveEffect({ effectId: effect.effect_id, resolution: { status: "NOT_APPLIED" } });
      return { handled: true, recoveredLease };
    }
    if (!dataSnapshotPortReady(config.dataSnapshotPort)) {
      fail(FAILURE.HOST_UNSUPPORTED, "pending full snapshot effect cannot be reconciled", STATUS.UNSUPPORTED);
    }
    if (recoveredLease === null) fail(FAILURE.QUIESCENCE_REQUIRED, "pending snapshot effect lost quiescence", STATUS.BLOCKED);
    let currentLease = revalidateLease(recoveredLease);
    if (intent.lease_id !== currentLease.lease_id) {
      fail(FAILURE.QUIESCENCE_REQUIRED, "pending snapshot lease binding differs", STATUS.BLOCKED);
    }
    if (effect.kind === "DATA_SNAPSHOT_CAPTURE") {
      exactFields(
        intent,
        [
          "operation_id",
          "owner_epoch",
          "plugin_data_root",
          "capability_id",
          "lease_id",
          "max_entries",
          "max_total_bytes",
          "max_file_bytes",
        ],
        "stored provider capture intent",
      );
      let receipt = validateCaptureReceipt(
        portCall(
          config.dataSnapshotPort,
          "reconcile",
          {
            operation_id: operation.operation_id,
            owner_epoch: ownerEpoch(),
            effect_id: effect.effect_id,
            phase: "CAPTURE",
            plugin_data_root: config.pluginDataRoot,
            capability_id: composition.dataSnapshot.capability_id,
            lease: currentLease,
          },
          "data snapshot",
        ),
        {
          operationId: operation.operation_id,
          expectedEffectId: effect.effect_id,
          leaseId: currentLease.lease_id,
          allowNotApplied: true,
        },
      );
      if (receipt.status === "NOT_APPLIED") {
        currentLease = revalidateLease(currentLease);
        receipt = validateCaptureReceipt(
          portCall(
            config.dataSnapshotPort,
            "capture",
            capturePayload(operation.operation_id, effect.effect_id, currentLease),
            "data snapshot",
          ),
          {
            operationId: operation.operation_id,
            expectedEffectId: effect.effect_id,
            leaseId: currentLease.lease_id,
          },
        );
      }
      currentLease = revalidateLease(currentLease);
      const captured = persistCapture(operation.operation_id, effect.effect_id, receipt);
      const comparison = comparePluginData(
        operation.operation_id,
        currentLease,
        captured.record,
        operation.operation_id,
      );
      if (!comparison.matches || comparison.current_token !== receipt.current_token) {
        fail(FAILURE.PLUGIN_DATA_CHANGED, "reconciled snapshot is not current");
      }
      return { handled: true, recoveredLease: comparison.lease };
    }

    const link = store.operationSnapshot(intent.capture_operation_id);
    if (
      link === null ||
      link.snapshot_hash !== intent.snapshot_hash ||
      link.capability_id !== intent.capability_id ||
      link.external_snapshot_id !== intent.external_snapshot_id
    ) fail(FAILURE.STATE_CORRUPT, "pending snapshot effect lost its exact provider link");
    const snapshot = verifySnapshotRecord(store.snapshotRecord(link.snapshot_hash));
    const phase = effect.kind === "DATA_SNAPSHOT_DISPOSE" ? "DISPOSE" : "RESTORE";
    const currentToken = phase === "RESTORE" ? intent.expected_current_token : null;
    let receipt = validateMutationReceipt(
      portCall(
        config.dataSnapshotPort,
        "reconcile",
        {
          operation_id: operation.operation_id,
          owner_epoch: ownerEpoch(),
          effect_id: effect.effect_id,
          phase,
          capture_operation_id: intent.capture_operation_id,
          plugin_data_root: config.pluginDataRoot,
          snapshot_hash: snapshot.snapshot_hash,
          external_snapshot_id: link.external_snapshot_id,
          capability_id: link.capability_id,
          expected_current_token: currentToken,
          lease: currentLease,
        },
        "data snapshot",
      ),
      {
        operationId: operation.operation_id,
        expectedEffectId: effect.effect_id,
        phase,
        snapshotHash: snapshot.snapshot_hash,
        externalSnapshotId: link.external_snapshot_id,
        leaseId: currentLease.lease_id,
        currentToken,
        allowNotApplied: true,
      },
    );
    if (receipt.status === "NOT_APPLIED") {
      currentLease = revalidateLease(currentLease);
      receipt = validateMutationReceipt(
        portCall(
          config.dataSnapshotPort,
          phase === "DISPOSE" ? "dispose" : "restore",
          {
            operation_id: operation.operation_id,
            owner_epoch: ownerEpoch(),
            effect_id: effect.effect_id,
            capture_operation_id: intent.capture_operation_id,
            plugin_data_root: config.pluginDataRoot,
            snapshot_hash: snapshot.snapshot_hash,
            external_snapshot_id: link.external_snapshot_id,
            capability_id: link.capability_id,
            expected_current_token: currentToken,
            lease: currentLease,
          },
          "data snapshot",
        ),
        {
          operationId: operation.operation_id,
          expectedEffectId: effect.effect_id,
          phase,
          snapshotHash: snapshot.snapshot_hash,
          externalSnapshotId: link.external_snapshot_id,
          leaseId: currentLease.lease_id,
          currentToken,
        },
      );
    }
    currentLease = revalidateLease(currentLease);
    if (phase === "DISPOSE") {
      store.resolveSnapshotDispose({
        effectId: effect.effect_id,
        captureOperationId: link.operation_id,
        receiptHash: receipt.receipt_hash,
        resolution: { status: "APPLIED", receipt_hash: receipt.receipt_hash },
      });
      return { handled: true, recoveredLease: currentLease };
    }
    store.resolveSnapshotRestore({
      effectId: effect.effect_id,
      captureOperationId: intent.capture_operation_id,
      receiptHash: receipt.receipt_hash,
      resolution: { status: "APPLIED", receipt_hash: receipt.receipt_hash },
    });
    const comparison = comparePluginData(
      operation.operation_id,
      currentLease,
      snapshot,
      intent.capture_operation_id,
    );
    if (!comparison.matches) fail(FAILURE.ROLLBACK_FAILED, "reconciled provider restore is not exact");
    return { handled: true, recoveredLease: comparison.lease };
  };

  return Object.freeze({
    verifySnapshotRecord,
    snapshotPluginData,
    comparePluginData,
    restorePluginData,
    disposeSnapshotLink,
    ensureStableSnapshotBoundary,
    reconcileEffect,
  });
}
