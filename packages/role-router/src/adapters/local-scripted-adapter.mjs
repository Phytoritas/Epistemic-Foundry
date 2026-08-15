import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

import { failAdapterExecution } from "./adapter-execution-errors.mjs";

export const LOCAL_SCRIPTED_ADAPTER_KIND = "local_scripted";
export const LOCAL_SCRIPTED_ADAPTER_VERSION = "4.0.0-n02.local-scripted.2";
export const LOCAL_SCRIPTED_ACTION_TYPE = "invoke_local_scripted_adapter";
export const LOCAL_SCRIPTED_TERMINAL_REASON = "local_scripted_complete";

export const LOCAL_SCRIPTED_ADAPTER_PROFILE = Object.freeze({
  kind: LOCAL_SCRIPTED_ADAPTER_KIND,
  adapter_version: LOCAL_SCRIPTED_ADAPTER_VERSION,
  execution: "in_process",
  transport: "none",
  live_provider: false,
  scientific_evidence_status: "none",
  forbidden_capabilities: Object.freeze([
    "canonical_state_write",
    "child_process",
    "credential_access",
    "network_access",
    "provider_fallback",
    "tool_call",
  ]),
});

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const DENIED_OBJECT_KEYS = new Set(["__proto__", "constructor", "prototype"]);
const LOCAL_SCRIPTED_INSTANCES = new WeakSet();
const MAX_FIXTURE_RESPONSES = 1_024;
const MAX_FIXTURE_DEPTH = 64;
const MAX_FIXTURE_NODES = 10_000;
const MAX_FIXTURE_UTF8_BYTES = 1024 * 1024;
const MAX_CANONICAL_FIXTURE_SET_BYTES = 4 * 1024 * 1024;

const boundedUnicodeScalarLength = (value, maxLength) => {
  if (typeof value !== "string") return -1;
  let length = 0;
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return -1;
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      return -1;
    }
    length += 1;
    if (length > maxLength) return length;
  }
  return length;
};

const sortUtf8Keys = (keys) => {
  const encoded = new Map(
    keys.map((key) => [key, Buffer.from(key, "utf8")]),
  );
  return keys.sort((left, right) =>
    Buffer.compare(encoded.get(left), encoded.get(right)),
  );
};

const hasOnlyUnicodeScalars = (value) =>
  boundedUnicodeScalarLength(value, Number.MAX_SAFE_INTEGER) >= 0;

const requireText = (value, label, { maxLength = 4_096 } = {}) => {
  const length = boundedUnicodeScalarLength(value, maxLength);
  if (
    typeof value !== "string" ||
    length < 1 ||
    length > maxLength ||
    value.normalize("NFC") !== value ||
    value.trim().length === 0
  ) {
    failAdapterExecution(
      "LOCAL_SCRIPTED_INPUT_INVALID",
      label + " must be a bounded non-blank NFC Unicode scalar string",
    );
  }
  return value;
};

const requirePlainRecord = (
  candidate,
  label,
  allowedFields,
  requiredFields = allowedFields,
) => {
  if (
    candidate === null ||
    typeof candidate !== "object" ||
    ARRAY_IS_ARRAY(candidate) ||
    IS_PROXY(candidate) ||
    (OBJECT_GET_PROTOTYPE_OF(candidate) !== Object.prototype &&
      OBJECT_GET_PROTOTYPE_OF(candidate) !== null)
  ) {
    failAdapterExecution(
      "LOCAL_SCRIPTED_INPUT_INVALID",
      label + " must be a non-proxy plain data object",
    );
  }
  const allowed = allowedFields === undefined ? null : new Set(allowedFields);
  for (const key of REFLECT_OWN_KEYS(candidate)) {
    if (typeof key !== "string" || (allowed !== null && !allowed.has(key))) {
      failAdapterExecution(
        "LOCAL_SCRIPTED_INPUT_INVALID",
        label + " contains an unsupported field",
      );
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(candidate, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      failAdapterExecution(
        "LOCAL_SCRIPTED_INPUT_INVALID",
        label + "." + String(key) + " must be an enumerable data property",
      );
    }
  }
  for (const field of requiredFields) {
    if (!OBJECT_HAS_OWN(candidate, field)) {
      failAdapterExecution(
        "LOCAL_SCRIPTED_INPUT_INVALID",
        label + "." + field + " is required",
      );
    }
  }
  return candidate;
};

const readDataProperty = (record, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(record, key).value;

const chargeFixtureBudget = (budget, { nodes = 0, utf8Bytes = 0 } = {}) => {
  budget.nodes += nodes;
  budget.utf8Bytes += utf8Bytes;
  if (
    budget.nodes > MAX_FIXTURE_NODES ||
    budget.utf8Bytes > MAX_FIXTURE_UTF8_BYTES
  ) {
    failAdapterExecution(
      "LOCAL_SCRIPTED_FIXTURE_LIMIT_EXCEEDED",
      "fixture data exceeds the bounded node or UTF-8 byte budget",
    );
  }
};

const cloneFrozenJsonValue = (
  value,
  label,
  budget = { nodes: 0, utf8Bytes: 0 },
  ancestors = new Set(),
  depth = 0,
) => {
  if (depth > MAX_FIXTURE_DEPTH) {
    failAdapterExecution(
      "LOCAL_SCRIPTED_FIXTURE_LIMIT_EXCEEDED",
      label + " exceeds the bounded fixture depth",
    );
  }
  chargeFixtureBudget(budget, { nodes: 1 });
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") {
    if (!hasOnlyUnicodeScalars(value)) {
      failAdapterExecution(
        "LOCAL_SCRIPTED_FIXTURE_INVALID",
        label + " contains an invalid Unicode scalar sequence",
      );
    }
    chargeFixtureBudget(budget, {
      utf8Bytes: Buffer.byteLength(value, "utf8"),
    });
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Object.is(value, -0)) {
      failAdapterExecution(
        "LOCAL_SCRIPTED_FIXTURE_INVALID",
        label + " must contain only finite canonical JSON numbers",
      );
    }
    return value;
  }
  if (typeof value !== "object" || IS_PROXY(value)) {
    failAdapterExecution(
      "LOCAL_SCRIPTED_FIXTURE_INVALID",
      label + " must contain JSON plain data only",
    );
  }
  if (ancestors.has(value)) {
    failAdapterExecution(
      "LOCAL_SCRIPTED_FIXTURE_INVALID",
      label + " must not contain cycles",
    );
  }
  ancestors.add(value);
  try {
    if (ARRAY_IS_ARRAY(value)) {
      if (OBJECT_GET_PROTOTYPE_OF(value) !== Array.prototype) {
        failAdapterExecution(
          "LOCAL_SCRIPTED_FIXTURE_INVALID",
          label + " arrays must use Array.prototype",
        );
      }
      if (value.length > MAX_FIXTURE_NODES - budget.nodes) {
        failAdapterExecution(
          "LOCAL_SCRIPTED_FIXTURE_LIMIT_EXCEEDED",
          label + " exceeds the bounded array element budget",
        );
      }
      const output = new Array(value.length);
      for (const key of REFLECT_OWN_KEYS(value)) {
        if (key === "length") continue;
        if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
          failAdapterExecution(
            "LOCAL_SCRIPTED_FIXTURE_INVALID",
            label + " contains a non-element array property",
          );
        }
        const index = Number(key);
        if (
          !Number.isSafeInteger(index) ||
          index >= value.length ||
          String(index) !== key
        ) {
          failAdapterExecution(
            "LOCAL_SCRIPTED_FIXTURE_INVALID",
            label + " contains a non-canonical array index",
          );
        }
      }
      for (let index = 0; index < value.length; index += 1) {
        const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
        if (
          descriptor === undefined ||
          !descriptor.enumerable ||
          !OBJECT_HAS_OWN(descriptor, "value")
        ) {
          failAdapterExecution(
            "LOCAL_SCRIPTED_FIXTURE_INVALID",
            label + " contains a sparse or accessor-backed array element",
          );
        }
        output[index] = cloneFrozenJsonValue(
          descriptor.value,
          label + "[" + index + "]",
          budget,
          ancestors,
          depth + 1,
        );
      }
      return Object.freeze(output);
    }

    if (
      OBJECT_GET_PROTOTYPE_OF(value) !== Object.prototype &&
      OBJECT_GET_PROTOTYPE_OF(value) !== null
    ) {
      failAdapterExecution(
        "LOCAL_SCRIPTED_FIXTURE_INVALID",
        label + " objects must use Object.prototype or a null prototype",
      );
    }
    const keys = REFLECT_OWN_KEYS(value);
    if (keys.length > MAX_FIXTURE_NODES - budget.nodes) {
      failAdapterExecution(
        "LOCAL_SCRIPTED_FIXTURE_LIMIT_EXCEEDED",
        label + " exceeds the bounded object member budget",
      );
    }
    if (keys.some((key) => typeof key !== "string")) {
      failAdapterExecution(
        "LOCAL_SCRIPTED_FIXTURE_INVALID",
        label + " must not contain symbol keys",
      );
    }
    const output = {};
    for (const key of keys) {
      if (DENIED_OBJECT_KEYS.has(key) || !hasOnlyUnicodeScalars(key)) {
        failAdapterExecution(
          "LOCAL_SCRIPTED_FIXTURE_INVALID",
          label + " contains an unsafe object key",
        );
      }
      chargeFixtureBudget(budget, {
        utf8Bytes: Buffer.byteLength(key, "utf8"),
      });
    }
    for (const key of sortUtf8Keys(keys)) {
      const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
      if (
        descriptor === undefined ||
        !descriptor.enumerable ||
        !OBJECT_HAS_OWN(descriptor, "value")
      ) {
        failAdapterExecution(
          "LOCAL_SCRIPTED_FIXTURE_INVALID",
          label + "." + key + " must be an enumerable data property",
        );
      }
      Object.defineProperty(output, key, {
        configurable: false,
        enumerable: true,
        value: cloneFrozenJsonValue(
          descriptor.value,
          label + "." + key,
          budget,
          ancestors,
          depth + 1,
        ),
        writable: false,
      });
    }
    return Object.freeze(output);
  } finally {
    ancestors.delete(value);
  }
};

const normalizeResponses = (candidate) => {
  const responses = requirePlainRecord(
    candidate,
    "responses",
    undefined,
    [],
  );
  const responseKeys = REFLECT_OWN_KEYS(responses);
  if (responseKeys.length > MAX_FIXTURE_RESPONSES) {
    failAdapterExecution(
      "LOCAL_SCRIPTED_FIXTURE_LIMIT_EXCEEDED",
      "responses exceeds the bounded fixture response count",
    );
  }
  const budget = { nodes: 0, utf8Bytes: 0 };
  const entries = new Map();
  for (const key of responseKeys) {
    const responseKey = requireText(key, "responses key", { maxLength: 71 });
    if (!SHA256_PATTERN.test(responseKey)) {
      failAdapterExecution(
        "LOCAL_SCRIPTED_FIXTURE_INVALID",
        "every response key must be the bound NodeInvocation input_hash",
      );
    }
    chargeFixtureBudget(budget, {
      utf8Bytes: Buffer.byteLength(responseKey, "utf8"),
    });
  }
  for (const key of sortUtf8Keys(responseKeys)) {
    const responseKey = key;
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(responses, key);
    entries.set(
      responseKey,
      cloneFrozenJsonValue(
        descriptor.value,
        "responses[" + JSON.stringify(responseKey) + "]",
        budget,
      ),
    );
  }
  if (entries.size === 0) {
    failAdapterExecution(
      "LOCAL_SCRIPTED_FIXTURE_INVALID",
      "responses must contain at least one deterministic fixture",
    );
  }
  const canonicalFixtureSet = JSON.stringify([...entries.entries()]);
  if (
    Buffer.byteLength(canonicalFixtureSet, "utf8") >
    MAX_CANONICAL_FIXTURE_SET_BYTES
  ) {
    failAdapterExecution(
      "LOCAL_SCRIPTED_FIXTURE_LIMIT_EXCEEDED",
      "canonical fixture set exceeds the bounded serialized byte budget",
    );
  }
  const fixtureSetHash =
    "sha256:" +
    createHash("sha256").update(canonicalFixtureSet, "utf8").digest("hex");
  return Object.freeze({ entries, fixtureSetHash });
};

/**
 * Create a branded, network-free adapter backed only by immutable plain-data
 * fixtures. No response callback or provider fallback is accepted.
 */
export const createLocalScriptedAdapter = (candidate) => {
  const options = requirePlainRecord(
    candidate,
    "local scripted adapter options",
    ["responses"],
    ["responses"],
  );
  const { entries: responses, fixtureSetHash } = normalizeResponses(
    readDataProperty(options, "responses"),
  );
  const profile = Object.freeze({
    ...LOCAL_SCRIPTED_ADAPTER_PROFILE,
    fixture_set_hash: fixtureSetHash,
  });
  const adapter = Object.freeze({
    kind: LOCAL_SCRIPTED_ADAPTER_KIND,
    profile,
    hasResponseForInputHash(inputHashCandidate) {
      const inputHash = requireText(
        inputHashCandidate,
        "inputHash",
        { maxLength: 71 },
      );
      if (!SHA256_PATTERN.test(inputHash)) {
        failAdapterExecution(
          "LOCAL_SCRIPTED_INVOCATION_INVALID",
          "inputHash must be a canonical SHA-256 digest",
        );
      }
      return responses.has(inputHash);
    },
    execute(requestCandidate) {
      const request = requirePlainRecord(
        requestCandidate,
        "local scripted execution request",
        ["nodeInvocation"],
        ["nodeInvocation"],
      );
      const invocation = requirePlainRecord(
        readDataProperty(request, "nodeInvocation"),
        "nodeInvocation",
        undefined,
        ["input_hash"],
      );
      const inputHash = readDataProperty(invocation, "input_hash");
      if (typeof inputHash !== "string" || !SHA256_PATTERN.test(inputHash)) {
        failAdapterExecution(
          "LOCAL_SCRIPTED_INVOCATION_INVALID",
          "nodeInvocation.input_hash must be a canonical SHA-256 digest",
          { stage: "adapter_call", adapterInvoked: true },
        );
      }
      if (!responses.has(inputHash)) {
        failAdapterExecution(
          "LOCAL_SCRIPTED_RESPONSE_NOT_FOUND",
          "no deterministic response is sealed for NodeInvocation.input_hash",
          {
            stage: "adapter_call",
            adapterInvoked: true,
            details: { inputHash },
          },
        );
      }
      return cloneFrozenJsonValue(
        responses.get(inputHash),
        "local scripted response",
      );
    },
  });
  LOCAL_SCRIPTED_INSTANCES.add(adapter);
  return adapter;
};

/** Reject lookalike adapters even if they copy the public metadata. */
export const verifyLocalScriptedAdapter = (candidate) => {
  if (
    candidate === null ||
    typeof candidate !== "object" ||
    !LOCAL_SCRIPTED_INSTANCES.has(candidate) ||
    candidate.kind !== LOCAL_SCRIPTED_ADAPTER_KIND
  ) {
    failAdapterExecution(
      "UNSUPPORTED_ADAPTER_KIND",
      "this bounded executor accepts only a branded local_scripted adapter",
    );
  }
  return candidate;
};
