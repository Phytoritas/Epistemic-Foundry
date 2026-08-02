import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { openContentAddressedArtifactStore } from "../artifacts/content-addressed-artifact-store.mjs";
import { openSQLiteStateStore } from "../state/sqlite/sqlite-state-store.mjs";
import {
  NoeticLedgerError,
  createNoeticLedger,
  decodeJsonPayload,
} from "./noetic-ledger.mjs";
import {
  createLedgerFixture,
  eventInput,
  fixedTimestamp,
  putJsonPayload,
} from "./ledger-test-support.mjs";

const expectCode = (code) => (error) =>
  error instanceof NoeticLedgerError && error.code === code;

const appendDeltas = (artifactStore, ledger) => {
  for (let index = 1; index <= 3; index += 1) {
    putJsonPayload(artifactStore, `ART-E01-delta-${index}`, { delta: index });
    ledger.append(
      eventInput({
        eventId: `EVT-E01-delta-${index}`,
        occurredAt: fixedTimestamp(index),
        payloadArtifactId: `ART-E01-delta-${index}`,
      }),
    );
  }
};

const sumReducer = (state, { event, payloadBytes }) => {
  const payload = decodeJsonPayload(payloadBytes);
  return {
    sum: state.sum + payload.delta,
    event_ids: [...state.event_ids, event.event_id],
  };
};

test("reducer_replay_test: verified events rebuild byte-stable materialized state", (t) => {
  const { artifactStore, ledger } = createLedgerFixture(t);
  appendDeltas(artifactStore, ledger);
  const first = ledger.rebuild("RUN-E01-test", {
    initialState: { event_ids: [], sum: 0 },
    reducer: sumReducer,
  });
  const second = ledger.rebuild("RUN-E01-test", {
    initialState: { sum: 0, event_ids: [] },
    reducer: sumReducer,
  });

  assert.deepEqual(first.state, {
    event_ids: ["EVT-E01-delta-1", "EVT-E01-delta-2", "EVT-E01-delta-3"],
    sum: 6,
  });
  assert.equal(Object.isFrozen(first.state), true);
  assert.equal(Object.isFrozen(first.state.event_ids), true);
  assert.equal(first.state_hash, second.state_hash);
  assert.deepEqual(first, second);
  assert.match(first.state_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("reducer_replay_test: reopening both durable stores reproduces identical state", (t) => {
  const fixture = createLedgerFixture(t);
  appendDeltas(fixture.artifactStore, fixture.ledger);
  const before = fixture.ledger.rebuild("RUN-E01-test", {
    initialState: { event_ids: [], sum: 0 },
    reducer: sumReducer,
  });
  fixture.stateStore.close();
  fixture.artifactStore.close();

  const stateStore = openSQLiteStateStore(fixture.databasePath);
  const artifactStore = openContentAddressedArtifactStore(fixture.artifactRoot);
  try {
    const ledger = createNoeticLedger({ artifactStore, stateStore });
    const after = ledger.rebuild("RUN-E01-test", {
      initialState: { event_ids: [], sum: 0 },
      reducer: sumReducer,
    });
    assert.deepEqual(after, before);
  } finally {
    stateStore.close();
    artifactStore.close();
  }
});

test("reducer_replay_test: a reducer must be deterministic at every event boundary", (t) => {
  const { artifactStore, ledger } = createLedgerFixture(t);
  putJsonPayload(artifactStore, "ART-E01-nondeterministic", { value: 1 });
  ledger.append(
    eventInput({
      eventId: "EVT-E01-nondeterministic",
      payloadArtifactId: "ART-E01-nondeterministic",
    }),
  );
  let hiddenCounter = 0;
  assert.throws(
    () =>
      ledger.rebuild("RUN-E01-test", {
        initialState: { value: 0 },
        reducer: () => ({ value: ++hiddenCounter }),
      }),
    expectCode("REDUCER_NON_DETERMINISTIC"),
  );
});

test("reducer_replay_test: async reducers and non-JSON outputs are rejected", (t) => {
  const { artifactStore, ledger } = createLedgerFixture(t);
  putJsonPayload(artifactStore, "ART-E01-reducer-invalid", { value: 1 });
  ledger.append(
    eventInput({
      eventId: "EVT-E01-reducer-invalid",
      payloadArtifactId: "ART-E01-reducer-invalid",
    }),
  );
  assert.throws(
    () =>
      ledger.rebuild("RUN-E01-test", {
        initialState: {},
        reducer: async () => ({}),
      }),
    expectCode("ASYNC_REDUCER_DENIED"),
  );
  assert.throws(
    () =>
      ledger.rebuild("RUN-E01-test", {
        initialState: {},
        reducer: () => new Date("2026-07-28T00:00:00Z"),
      }),
    expectCode("REDUCER_OUTPUT_INVALID"),
  );
});

test("reducer_replay_test: reducer inputs are isolated and immutable", (t) => {
  const { artifactStore, ledger } = createLedgerFixture(t);
  putJsonPayload(artifactStore, "ART-E01-immutable", { value: 1 });
  ledger.append(
    eventInput({ eventId: "EVT-E01-immutable", payloadArtifactId: "ART-E01-immutable" }),
  );
  assert.throws(
    () =>
      ledger.rebuild("RUN-E01-test", {
        initialState: { count: 0 },
        reducer: (state) => {
          state.count += 1;
          return state;
        },
      }),
    expectCode("REDUCER_FAILED"),
  );
  assert.throws(
    () =>
      ledger.rebuild("RUN-E01-test", {
        initialState: { count: 0 },
        reducer: (state, { event }) => {
          event.event_type = "tampered";
          return state;
        },
      }),
    expectCode("REDUCER_FAILED"),
  );
});

test("reducer_replay_test: artifact tamper fails before reducer execution", (t) => {
  const { artifactRoot, artifactStore, ledger } = createLedgerFixture(t);
  putJsonPayload(artifactStore, "ART-E01-tampered-payload", { value: 1 });
  ledger.append(
    eventInput({
      eventId: "EVT-E01-tampered-payload",
      payloadArtifactId: "ART-E01-tampered-payload",
    }),
  );
  const manifest = artifactStore.readManifest("ART-E01-tampered-payload");
  const hex = manifest.content_hash.slice("sha256:".length);
  fs.writeFileSync(
    path.join(artifactRoot, "sha256", hex.slice(0, 2), hex.slice(2), "content.bin"),
    Buffer.from('{"value":2}', "utf8"),
  );
  let reducerCalls = 0;
  assert.throws(
    () =>
      ledger.rebuild("RUN-E01-test", {
        initialState: {},
        reducer: () => {
          reducerCalls += 1;
          return {};
        },
      }),
    expectCode("PAYLOAD_RESOLUTION_FAILED"),
  );
  assert.equal(reducerCalls, 0);
});

test("reducer_replay_test: an empty run deterministically preserves canonical initial state", (t) => {
  const { ledger } = createLedgerFixture(t);
  let reducerCalls = 0;
  const rebuilt = ledger.rebuild("RUN-E01-empty", {
    initialState: { status: "EMPTY", values: [] },
    reducer: () => {
      reducerCalls += 1;
      return null;
    },
  });
  assert.equal(reducerCalls, 0);
  assert.deepEqual(rebuilt.state, { status: "EMPTY", values: [] });
  assert.equal(rebuilt.event_count, 0);
  assert.equal(rebuilt.tail_event_hash, null);
  assert.match(rebuilt.state_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("reducer_replay_test: JSON payload decoding rejects invalid UTF-8, BOM, and syntax", () => {
  assert.throws(() => decodeJsonPayload(Buffer.from([0xff])), expectCode("PAYLOAD_JSON_INVALID"));
  assert.throws(
    () => decodeJsonPayload(Buffer.from([0xef, 0xbb, 0xbf, 0x7b, 0x7d])),
    expectCode("PAYLOAD_JSON_INVALID"),
  );
  assert.throws(() => decodeJsonPayload(Buffer.from("{", "utf8")), expectCode("PAYLOAD_JSON_INVALID"));
});

test("reducer_replay_test: state hashing rejects hidden array properties", (t) => {
  const { ledger } = createLedgerFixture(t);
  const values = [];
  Object.defineProperty(values, "9", {
    enumerable: true,
    value: "not-an-element",
  });
  assert.throws(
    () =>
      ledger.rebuild("RUN-E01-empty", {
        initialState: { values },
        reducer: () => null,
      }),
    expectCode("INVALID_INPUT"),
  );
});
