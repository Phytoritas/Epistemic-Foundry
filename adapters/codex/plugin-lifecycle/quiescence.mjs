import {
  FAILURE,
  STATUS,
  exactFields,
  fail,
} from "./core.mjs";
import { quiescencePortReady } from "./contracts.mjs";

export function createQuiescenceManager({
  store,
  config,
  ownerEpoch,
  deadline,
  effectId,
  portCall,
  checkDeadline,
  capabilityId,
}) {
  const requirePort = () => {
    if (!quiescencePortReady(config.quiescencePort) || config.quiescencePort.capability_id !== capabilityId) {
      fail(FAILURE.QUIESCENCE_REQUIRED, "quiescence composition identity changed", STATUS.UNSUPPORTED);
    }
  };
  const validateLease = (lease, { operationId, prior = null, requireHorizon = true, label = "quiescence lease" }) => {
    exactFields(
      lease,
      ["state", "operation_id", "owner_epoch", "lease_id", "plugin_data_root", "ownership_token", "expires_at"],
      label,
    );
    const expiresAt = typeof lease.expires_at === "string" ? Date.parse(lease.expires_at) : Number.NaN;
    const currentDeadline = deadline();
    if (
      lease.state !== "QUIESCED" ||
      lease.operation_id !== operationId ||
      lease.owner_epoch !== ownerEpoch() ||
      lease.plugin_data_root !== config.pluginDataRoot ||
      typeof lease.lease_id !== "string" ||
      lease.lease_id.length === 0 ||
      typeof lease.ownership_token !== "string" ||
      lease.ownership_token.length === 0 ||
      !Number.isFinite(expiresAt) ||
      expiresAt <= Date.now() ||
      (requireHorizon && currentDeadline !== null && expiresAt < currentDeadline + 5_000) ||
      (prior !== null && (lease.lease_id !== prior.lease_id || lease.ownership_token !== prior.ownership_token))
    ) fail(FAILURE.QUIESCENCE_REQUIRED, `${label} is not current and operation-bound`, STATUS.BLOCKED);
    return lease;
  };

  const requiredUntil = () => {
    const value = deadline();
    if (value === null) fail(FAILURE.CONCURRENT_OPERATION, "quiescence requires an active bounded call", STATUS.BLOCKED);
    return new Date(value + 5_000).toISOString();
  };

  const renewLease = (lease) => {
    requirePort();
    const renewed = portCall(
      config.quiescencePort,
      "renew",
      { ...lease, required_until: requiredUntil() },
      "quiescence",
    );
    validateLease(renewed, { operationId: lease.operation_id, prior: lease, label: "renewed quiescence lease" });
    store.updateRecoveredLease(lease.operation_id, renewed);
    return renewed;
  };

  const acquireLease = (operationId, selector) => {
    requirePort();
    const id = effectId();
    const input = {
      operation_id: operationId,
      owner_epoch: ownerEpoch(),
      capability_id: capabilityId,
      selector,
      plugin_data_root: config.pluginDataRoot,
      required_until: requiredUntil(),
    };
    store.intentEffect({ operationId, effectId: id, kind: "QUIESCE_ACQUIRE", intent: input });
    const lease = portCall(config.quiescencePort, "acquire", input, "quiescence");
    validateLease(lease, { operationId, label: "acquired quiescence lease" });
    store.recordLeaseAcquire({ effectId: id, lease });
    return lease;
  };

  const revalidateLease = (lease) => {
    requirePort();
    checkDeadline();
    let checked = portCall(config.quiescencePort, "revalidate", lease, "quiescence");
    validateLease(checked, {
      operationId: lease.operation_id,
      prior: lease,
      requireHorizon: false,
      label: "revalidated quiescence lease",
    });
    const currentDeadline = deadline();
    if (currentDeadline !== null && Date.parse(checked.expires_at) < currentDeadline + 5_000) {
      checked = renewLease(checked);
    } else {
      store.updateRecoveredLease(lease.operation_id, checked);
    }
    return checked;
  };

  const recoverLease = (operationId, durableLease) => {
    requirePort();
    let prior;
    try {
      prior = JSON.parse(durableLease.lease_json);
    } catch {
      fail(FAILURE.STATE_CORRUPT, "durable quiescence lease is invalid");
    }
    const recovered = portCall(
      config.quiescencePort,
      "recover",
      {
        operation_id: operationId,
        owner_epoch: ownerEpoch(),
        lease_id: durableLease.lease_id,
        lease: prior,
        plugin_data_root: config.pluginDataRoot,
        required_until: requiredUntil(),
      },
      "quiescence",
    );
    validateLease(recovered, { operationId, prior, label: "recovered quiescence lease" });
    store.updateRecoveredLease(operationId, recovered);
    return recovered;
  };

  const releaseLease = (operationId, lease) => {
    requirePort();
    const current = revalidateLease(lease);
    const id = effectId();
    store.intentEffect({
      operationId,
      effectId: id,
      kind: "QUIESCE_RELEASE",
      intent: {
        operation_id: operationId,
        owner_epoch: ownerEpoch(),
        capability_id: capabilityId,
        lease_id: current.lease_id,
      },
    });
    const released = portCall(
      config.quiescencePort,
      "release",
      { ...current, effect_id: id },
      "quiescence",
    );
    exactFields(released, ["state", "operation_id", "owner_epoch", "effect_id", "lease_id"], "quiescence release");
    if (
      released.state !== "RELEASED" ||
      released.operation_id !== operationId ||
      released.owner_epoch !== ownerEpoch() ||
      released.effect_id !== id ||
      released.lease_id !== current.lease_id
    ) fail(FAILURE.QUIESCENCE_REQUIRED, "quiescence lease was not released", STATUS.BLOCKED);
    store.recordLeaseRelease({ effectId: id, leaseId: current.lease_id });
  };

  return Object.freeze({ validateLease, acquireLease, revalidateLease, recoverLease, releaseLease });
}
