import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  assembleIntakeFrame,
  frameSha256,
  IntakeContractError,
  parseIntakeFrame,
  serializeIntakeFrame,
} from "./index.mjs";
import {
  measurementCompatibility,
  ontologyResolution,
  readyInput,
} from "./intake-test-fixtures.mjs";
import { intakeInternalsForTests } from "./intake-frame.mjs";

const clone = (value) => structuredClone(value);
const decode = (value) => new TextDecoder("utf-8", { fatal: true }).decode(value);

test("frame_roundtrip_test: canonical export parses and re-exports byte-for-byte", () => {
  const input = readyInput();
  input.ontology_resolutions = [ontologyResolution()];
  input.measurement_compatibilities = [measurementCompatibility()];
  const frame = assembleIntakeFrame(input);

  const first = serializeIntakeFrame(frame);
  const imported = parseIntakeFrame(first);
  const second = serializeIntakeFrame(imported);

  assert.deepEqual(imported, frame);
  assert.deepEqual(second, first);
  assert.equal(frameSha256(imported), `sha256:${createHash("sha256").update(first).digest("hex")}`);
});

test("frame_roundtrip_test: input object key order does not change export bytes", () => {
  const left = readyInput();
  const right = Object.fromEntries(Object.entries(readyInput()).reverse());
  right.insight_card = Object.fromEntries(Object.entries(right.insight_card).reverse());

  assert.deepEqual(
    serializeIntakeFrame(assembleIntakeFrame(left)),
    serializeIntakeFrame(assembleIntakeFrame(right)),
  );
});

test("frame_roundtrip_test: meaningful array order is preserved", () => {
  const input = readyInput();
  input.insight_card.predictions = ["First prediction", "Second prediction"];

  const imported = parseIntakeFrame(serializeIntakeFrame(assembleIntakeFrame(input)));

  assert.deepEqual(imported.insight_card.predictions, ["First prediction", "Second prediction"]);
});

test("frame_roundtrip_test: one-byte content tampering fails hash verification", () => {
  const serialized = serializeIntakeFrame(assembleIntakeFrame(readyInput()));
  const tampered = Buffer.from(serialized);
  const location = tampered.indexOf(Buffer.from("eligible"));
  assert.notEqual(location, -1);
  tampered[location] = "E".charCodeAt(0);

  assert.throws(
    () => parseIntakeFrame(tampered),
    (error) => error instanceof IntakeContractError && error.code === "INTAKE_FRAME_HASH_MISMATCH",
  );
});

test("frame_roundtrip_test: semantically equal non-canonical JSON is rejected", () => {
  const serialized = serializeIntakeFrame(assembleIntakeFrame(readyInput()));
  const nonCanonical = ` ${decode(serialized)}`;

  assert.throws(
    () => parseIntakeFrame(nonCanonical),
    (error) => error instanceof IntakeContractError && error.code === "INTAKE_FRAME_NOT_CANONICAL",
  );
});

test("frame_roundtrip_test: invalid UTF-8 is rejected before JSON parsing", () => {
  const invalid = Uint8Array.from([0xc3, 0x28]);

  assert.throws(
    () => parseIntakeFrame(invalid),
    (error) => error instanceof IntakeContractError && error.code === "INTAKE_FRAME_INVALID_UTF8",
  );
});

test("frame_roundtrip_test: an Inbox frame cannot be exported", () => {
  const input = readyInput();
  input.insight_card.registration_status = "inbox";
  input.council_ready = false;
  input.council_blockers = ["COUNCIL_REGISTRATION_STATUS_NOT_ELIGIBLE"];
  const frame = assembleIntakeFrame(input);

  assert.throws(
    () => serializeIntakeFrame(frame),
    (error) => error instanceof IntakeContractError && error.code === "INTAKE_EXPORT_BLOCKED",
  );
});

test("frame_roundtrip_test: a fabricated derived gate cannot be serialized", () => {
  const frame = clone(assembleIntakeFrame(readyInput()));
  frame.exportable = false;

  assert.throws(
    () => serializeIntakeFrame(frame),
    (error) =>
      error instanceof IntakeContractError && error.code === "INTAKE_FRAME_DERIVATION_MISMATCH",
  );
});

test("frame_roundtrip_test: unknown export envelope fields fail closed", () => {
  const serialized = serializeIntakeFrame(assembleIntakeFrame(readyInput()));
  const envelope = JSON.parse(decode(serialized));
  envelope.model_confidence = 1;

  assert.throws(
    () => parseIntakeFrame(JSON.stringify(envelope)),
    (error) => error instanceof IntakeContractError && error.code === "INTAKE_FIELD_SET_INVALID",
  );
});

test("frame_roundtrip_test: export and import leave caller-owned input untouched", () => {
  const input = readyInput();
  const before = clone(input);

  const serialized = serializeIntakeFrame(assembleIntakeFrame(input));
  parseIntakeFrame(serialized);

  assert.deepEqual(input, before);
});

test("frame_roundtrip_test: I02 lowercase and leap-second RFC 3339 output round-trips", () => {
  const input = readyInput();
  input.insight_card.created_at = "2016-12-31t23:59:60z";

  const imported = parseIntakeFrame(serializeIntakeFrame(assembleIntakeFrame(input)));

  assert.equal(imported.insight_card.created_at, "2016-12-31t23:59:60z");
});

test("frame_roundtrip_test: browser SHA-256 matches the Node oracle across padding and Unicode cases", () => {
  const statements = [
    ...[10, 31, 55, 56, 57, 63, 64, 65, 119, 120, 121].map((length) =>
      "x".repeat(length),
    ),
    "검증 가능한 통찰 프레임 🌱",
  ];

  for (const statement of statements) {
    const input = readyInput();
    input.insight_card.statement = statement;
    const serialized = serializeIntakeFrame(assembleIntakeFrame(input));
    const envelope = JSON.parse(decode(serialized));
    const preimage = intakeInternalsForTests.canonicalJson({
      format: envelope.format,
      frame: envelope.frame,
    });

    assert.equal(
      envelope.frame_hash,
      `sha256:${createHash("sha256").update(preimage, "utf8").digest("hex")}`,
    );
    assert.equal(
      frameSha256(envelope.frame),
      `sha256:${createHash("sha256").update(serialized).digest("hex")}`,
    );
  }
});
