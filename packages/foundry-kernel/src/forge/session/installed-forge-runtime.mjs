import {
  ARTIFACT_STORE_MODE,
  openContentAddressedArtifactStore,
} from "../../artifacts/content-addressed-artifact-store.mjs";
import {
  createCapabilityAuthority,
  sealCapabilityPolicy,
} from "../../capabilities/capability-authority.mjs";
import { createNoeticLedger } from "../../ledger/noetic-ledger.mjs";
import {
  SQLITE_STORE_MODE,
  openSQLiteStateStore,
} from "../../state/sqlite/sqlite-state-store.mjs";
import {
  createClassificationCommitter,
  createWorkClassificationWorker,
} from "../classifier/index.mjs";

import {
  OBJECT_FREEZE,
  readDataProperty,
  requirePlainRecord,
} from "./canonical-json.mjs";
import { createDurableForgeSessionPort } from "./durable-forge-session.mjs";
import { createSessionOpenWorker } from "./session-open-worker.mjs";
import { createSessionTransitionWorker } from "./session-transition-worker.mjs";

const OBJECT_HAS_OWN = Object.hasOwn;
const STABLE_CAUSE_CODE_PATTERN = /^[A-Z][A-Z0-9_]*$/u;
const OPEN_ERROR_CODE = "INSTALLED_FORGE_RUNTIME_OPEN_FAILED";
const OPTIONS_ERROR_CODE = "INSTALLED_FORGE_RUNTIME_OPTIONS_INVALID";
const READ_OPTION_KEYS = OBJECT_FREEZE([
  "databasePath",
  "artifactRoot",
  "clock",
  "sqliteOptions",
]);
const FULL_OPTION_KEYS = OBJECT_FREEZE([
  ...READ_OPTION_KEYS,
  "capabilityPolicy",
  "classificationRuntime",
  "openRuntime",
  "transitionRuntime",
]);
const READ_RUNTIME_DEPENDENCIES = new WeakMap();

const stableCauseCode = (candidate, fallback) => {
  const value = candidate?.code;
  return typeof value === "string" && STABLE_CAUSE_CODE_PATTERN.test(value)
    ? value
    : fallback;
};

export class InstalledForgeRuntimeOpenError extends Error {
  constructor(causeCode) {
    super("installed Forge runtime could not be opened");
    this.name = "InstalledForgeRuntimeOpenError";
    this.code = OPEN_ERROR_CODE;
    this.causeCode = typeof causeCode === "string" && STABLE_CAUSE_CODE_PATTERN.test(causeCode)
      ? causeCode
      : "INSTALLED_FORGE_RUNTIME_OPEN_FAILED";
  }
}

const optionError = () => new InstalledForgeRuntimeOpenError(OPTIONS_ERROR_CODE);

const normalizeOptions = (candidate, { allowedKeys, requiredKeys, includeMutation }) => {
  try {
    const value = requirePlainRecord(candidate, "installed Forge runtime options", {
      allowedKeys,
      requiredKeys,
      code: OPTIONS_ERROR_CODE,
    });
    const normalized = {
      databasePath: readDataProperty(value, "databasePath", "options", OPTIONS_ERROR_CODE),
      artifactRoot: readDataProperty(value, "artifactRoot", "options", OPTIONS_ERROR_CODE),
      clock: readDataProperty(value, "clock", "options", OPTIONS_ERROR_CODE),
      sqliteOptions: OBJECT_HAS_OWN(value, "sqliteOptions")
        ? readDataProperty(value, "sqliteOptions", "options", OPTIONS_ERROR_CODE)
        : undefined,
    };
    if (includeMutation) {
      normalized.capabilityPolicy = readDataProperty(
        value,
        "capabilityPolicy",
        "options",
        OPTIONS_ERROR_CODE,
      );
      normalized.classificationRuntime = OBJECT_HAS_OWN(value, "classificationRuntime")
        ? readDataProperty(value, "classificationRuntime", "options", OPTIONS_ERROR_CODE)
        : null;
      normalized.openRuntime = OBJECT_HAS_OWN(value, "openRuntime")
        ? readDataProperty(value, "openRuntime", "options", OPTIONS_ERROR_CODE)
        : null;
      normalized.transitionRuntime = OBJECT_HAS_OWN(value, "transitionRuntime")
        ? readDataProperty(value, "transitionRuntime", "options", OPTIONS_ERROR_CODE)
        : null;
    }
    return OBJECT_FREEZE(normalized);
  } catch {
    throw optionError();
  }
};

const normalizeReadOptions = (candidate) => normalizeOptions(candidate, {
  allowedKeys: READ_OPTION_KEYS,
  requiredKeys: ["databasePath", "artifactRoot", "clock"],
  includeMutation: false,
});

const normalizeFullOptions = (candidate) => normalizeOptions(candidate, {
  allowedKeys: FULL_OPTION_KEYS,
  requiredKeys: [
    "databasePath",
    "artifactRoot",
    "capabilityPolicy",
    "clock",
  ],
  includeMutation: true,
});

const closeAfterConstructionFailure = (artifactStore, stateStore) => {
  if (artifactStore !== null) {
    try {
      artifactStore.close();
    } catch {
      // The construction error remains authoritative.
    }
  }
  if (stateStore !== null) {
    try {
      stateStore.close();
    } catch {
      // The construction error remains authoritative.
    }
  }
};

const createClose = (artifactStore, stateStore) => {
  let attempted = false;
  let hasCloseError = false;
  let closeError;
  return () => {
    if (attempted) {
      if (hasCloseError) throw closeError;
      return;
    }
    attempted = true;
    try {
      artifactStore.close();
    } catch (error) {
      hasCloseError = true;
      closeError = error;
    }
    try {
      stateStore.close();
    } catch (error) {
      if (!hasCloseError) {
        hasCloseError = true;
        closeError = error;
      }
    }
    if (hasCloseError) throw closeError;
  };
};

const openStateStore = (databasePath, sqliteOptions) => {
  try {
    return openSQLiteStateStore(databasePath, sqliteOptions);
  } catch (error) {
    throw new InstalledForgeRuntimeOpenError(
      stableCauseCode(error, "SQLITE_OPEN_FAILED"),
    );
  }
};

const openArtifactStore = (artifactRoot) => {
  try {
    return openContentAddressedArtifactStore(artifactRoot);
  } catch (error) {
    throw new InstalledForgeRuntimeOpenError(
      stableCauseCode(error, "ARTIFACT_STORE_OPEN_FAILED"),
    );
  }
};

const createArtifactReadPort = (artifactStore) => OBJECT_FREEZE({
  enumerateReceipts: (...args) => artifactStore.enumerateReceipts(...args),
  readArtifact: (...args) => artifactStore.readArtifact(...args),
  readManifest: (...args) => artifactStore.readManifest(...args),
  readReceipt: (...args) => artifactStore.readReceipt(...args),
  resolveReceipt: (...args) => artifactStore.resolveReceipt(...args),
});

const createClassificationReadPort = (classificationPort) => OBJECT_FREEZE({
  readActiveClassification: (...args) => classificationPort.readActiveClassification(...args),
  readClassification: (...args) => classificationPort.readClassification(...args),
  readClassificationReplayProjection: (...args) =>
    classificationPort.readClassificationReplayProjection(...args),
  strictReplay: (...args) => classificationPort.strictReplay(...args),
});

const createSessionReadPort = (sessionPort) => OBJECT_FREEZE({
  readSession: (...args) => sessionPort.readSession(...args),
});

const bindReadRuntimeDependencies = (runtime, dependencies) => {
  READ_RUNTIME_DEPENDENCIES.set(runtime, OBJECT_FREEZE(dependencies));
  return runtime;
};

const resolveReadRuntimeDependencies = (runtime) => {
  const dependencies = READ_RUNTIME_DEPENDENCIES.get(runtime);
  if (dependencies === undefined) {
    throw new InstalledForgeRuntimeOpenError("INSTALLED_FORGE_RUNTIME_DEPENDENCY_BINDING_MISSING");
  }
  return dependencies;
};

const openReadRuntime = (options) => {
  let stateStore = null;
  let artifactStore = null;
  try {
    stateStore = openStateStore(options.databasePath, options.sqliteOptions);
    if (stateStore.mode !== SQLITE_STORE_MODE.ACTIVE) {
      throw new InstalledForgeRuntimeOpenError(
        stableCauseCode(stateStore.safeModeReason, "SQLITE_STORE_NOT_ACTIVE"),
      );
    }
    artifactStore = openArtifactStore(options.artifactRoot);
    if (artifactStore.mode !== ARTIFACT_STORE_MODE.ACTIVE) {
      throw new InstalledForgeRuntimeOpenError(
        stableCauseCode(
          artifactStore.safeModeReason,
          "ARTIFACT_STORE_NOT_ACTIVE",
        ),
      );
    }
    const ledger = createNoeticLedger({ stateStore, artifactStore });
    const classificationPort = createClassificationCommitter({
      stateStore,
      artifactStore,
      ledger,
      clock: options.clock,
    });
    const sessionPort = createDurableForgeSessionPort({
      stateStore,
      artifactStore,
      ledger,
      classificationPort,
      clock: options.clock,
    });
    const runtime = OBJECT_FREEZE({
      artifactStore: createArtifactReadPort(artifactStore),
      classificationPort: createClassificationReadPort(classificationPort),
      sessionPort: createSessionReadPort(sessionPort),
      close: createClose(artifactStore, stateStore),
    });
    return bindReadRuntimeDependencies(runtime, {
      stateStore,
      artifactStore,
      ledger,
      classificationPort,
      sessionPort,
    });
  } catch (error) {
    closeAfterConstructionFailure(artifactStore, stateStore);
    throw error;
  }
};

export const openInstalledForgeReadRuntime = (options) =>
  openReadRuntime(normalizeReadOptions(options));

export const openInstalledForgeRuntime = (options) => {
  const normalized = normalizeFullOptions(options);
  let base = null;
  try {
    base = openReadRuntime(normalized);
    const dependencies = resolveReadRuntimeDependencies(base);
    const policy = sealCapabilityPolicy(normalized.capabilityPolicy);
    const authority = createCapabilityAuthority({
      stateStore: dependencies.stateStore,
      artifactStore: dependencies.artifactStore,
      ledger: dependencies.ledger,
      policy,
      clock: normalized.clock,
    });
    const classificationWorker = normalized.classificationRuntime === null
      ? null
      : createWorkClassificationWorker({
          stateStore: dependencies.stateStore,
          artifactStore: dependencies.artifactStore,
          ledger: dependencies.ledger,
          authority,
          classification: dependencies.classificationPort,
          clock: normalized.clock,
          runtime: normalized.classificationRuntime,
        });
    const openWorker = normalized.openRuntime === null
      ? null
      : createSessionOpenWorker({
          stateStore: dependencies.stateStore,
          artifactStore: dependencies.artifactStore,
          ledger: dependencies.ledger,
          authority,
          session: dependencies.sessionPort,
          classification: dependencies.classificationPort,
          clock: normalized.clock,
          runtime: normalized.openRuntime,
        });
    const transitionWorker = normalized.transitionRuntime === null
      ? null
      : createSessionTransitionWorker({
          stateStore: dependencies.stateStore,
          artifactStore: dependencies.artifactStore,
          ledger: dependencies.ledger,
          authority,
          session: dependencies.sessionPort,
          clock: normalized.clock,
          runtime: normalized.transitionRuntime,
        });
    return OBJECT_FREEZE({
      artifactStore: base.artifactStore,
      classificationPort: base.classificationPort,
      classificationWorker,
      sessionPort: base.sessionPort,
      openWorker,
      transitionWorker,
      close: base.close,
    });
  } catch (error) {
    if (base !== null) {
      try {
        base.close();
      } catch {
        // The full-runtime construction error remains authoritative.
      }
    }
    throw error;
  }
};
