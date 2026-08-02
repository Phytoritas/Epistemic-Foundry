import assert from "node:assert/strict";
import test from "node:test";

import {
  admitForgeTransition,
  sha256TransitionJson,
  TransitionAdmissionError,
} from "./transition-admission-gate.mjs";
import {
  activeArtifactStore,
  phaseTransitionFixture,
  putJsonArtifact,
  registerClassification,
  registerGateDecision,
  registerPhaseArtifactSet,
  registerPhaseEvidence,
  sealGateDecision,
  sealPhaseArtifactSet,
  sealState,
  transitionRequest,
} from "./gate-test-support.mjs";

const expectCode = (code) => (error) =>
  error instanceof TransitionAdmissionError && error.code === code;

const gateBindings = (fixture) => ({
  gateVersion: "4.0.0",
  inputArtifactIds: [fixture.evidence.artifact_id],
  policyBundleHash: fixture.state.policy_hash,
});

const resealGateDecision = (decision) => {
  const { decision_hash: ignored, ...semantic } = decision;
  void ignored;
  return { ...semantic, decision_hash: sha256TransitionJson(semantic) };
};

test("transition_receipt_test: a complete current phase set admits deterministically", (t) => {
  const fixture = phaseTransitionFixture(t);
  const stateBefore = structuredClone(fixture.state);
  const requestBefore = structuredClone(fixture.request);

  const first = admitForgeTransition({
    current_state: fixture.state,
    transition_request: fixture.request,
    artifact_store: fixture.store,
  });
  const second = admitForgeTransition({
    current_state: structuredClone(fixture.state),
    transition_request: structuredClone(fixture.request),
    artifact_store: fixture.store,
  });

  assert.deepEqual(second, first);
  assert.deepEqual(fixture.state, stateBefore);
  assert.deepEqual(fixture.request, requestBefore);
  assert.equal(first.admission.decision, "ADMIT");
  assert.equal(first.admission.admission_version, "4.0.0-f03.2");
  assert.equal(first.admission.phase_artifact_set_id, fixture.phaseSet.set_id);
  assert.equal(first.admission.phase_artifact_set_hash, fixture.phaseSet.set_hash);
  assert.match(first.admission.admission_id, /^FTA-[0-9a-f]{64}$/u);
  assert.match(first.admission.admission_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(Object.isFrozen(first), true);
  assert.equal(Object.isFrozen(first.admission.receipt_bindings), true);
});

test("transition_receipt_test: prose-only and unresolved receipt transitions fail closed", (t) => {
  const store = activeArtifactStore(t);
  const state = sealState({ phase: "IDLE", revision: 0 });
  const proseOnly = transitionRequest({ state, to: "F" });
  assert.throws(
    () =>
      admitForgeTransition({
        current_state: state,
        transition_request: proseOnly,
        artifact_store: store,
      }),
    expectCode("TRANSITION_RECEIPT_REQUIRED"),
  );

  const unresolved = transitionRequest({ state, to: "F", receiptIds: ["AR-F03-missing"] });
  assert.throws(
    () =>
      admitForgeTransition({
        current_state: state,
        transition_request: unresolved,
        artifact_store: store,
      }),
    expectCode("ARTIFACT_RECEIPT_UNRESOLVED"),
  );
});

test("transition_receipt_test: resolver claims cannot replace byte and receipt integrity", (t) => {
  const fixture = phaseTransitionFixture(t, { suffix: "resolver-integrity" });
  const tamperedBytesStore = {
    resolveReceipt(receiptId) {
      const resolved = fixture.store.resolveReceipt(receiptId);
      if (receiptId !== fixture.evidence.receipt_id) return resolved;
      return { ...resolved, bytes: Buffer.from("tampered resolver bytes", "utf8") };
    },
  };
  assert.throws(
    () =>
      admitForgeTransition({
        current_state: fixture.state,
        transition_request: fixture.request,
        artifact_store: tamperedBytesStore,
      }),
    expectCode("ARTIFACT_CONTENT_SIZE_MISMATCH"),
  );

  const missingIntegrityEvidenceStore = {
    resolveReceipt(receiptId) {
      const resolved = fixture.store.resolveReceipt(receiptId);
      if (receiptId !== fixture.evidence.receipt_id) return resolved;
      const receipt = {
        ...resolved.receipt,
        validation_results: resolved.receipt.validation_results.filter(
          ({ check }) => check !== "artifact_manifest_sha256",
        ),
      };
      const { receipt_hash: ignored, ...semantic } = receipt;
      void ignored;
      return {
        ...resolved,
        receipt: { ...semantic, receipt_hash: sha256TransitionJson(semantic) },
      };
    },
  };
  assert.throws(
    () =>
      admitForgeTransition({
        current_state: fixture.state,
        transition_request: fixture.request,
        artifact_store: missingIntegrityEvidenceStore,
      }),
    expectCode("ARTIFACT_RECEIPT_INTEGRITY_EVIDENCE_MISMATCH"),
  );
});

test("transition_receipt_test: malformed validation evidence fails with a typed error", (t) => {
  const fixture = phaseTransitionFixture(t, { suffix: "malformed-validation" });
  const malformedValidationStore = {
    resolveReceipt(receiptId) {
      const resolved = fixture.store.resolveReceipt(receiptId);
      if (receiptId !== fixture.evidence.receipt_id) return resolved;
      const receipt = { ...resolved.receipt, validation_results: [null] };
      const { receipt_hash: ignored, ...semantic } = receipt;
      void ignored;
      return {
        ...resolved,
        receipt: { ...semantic, receipt_hash: sha256TransitionJson(semantic) },
      };
    },
  };

  assert.throws(
    () =>
      admitForgeTransition({
        current_state: fixture.state,
        transition_request: fixture.request,
        artifact_store: malformedValidationStore,
      }),
    expectCode("ARTIFACT_RECEIPT_INVALID"),
  );
});

test("transition_receipt_test: IDLE requires a real receipt but no fictional prior phase set", (t) => {
  const store = activeArtifactStore(t);
  const { artifact: classification, registration } = registerClassification(store);
  const state = sealState({ phase: "IDLE", revision: 0 });
  const request = transitionRequest({
    state,
    to: "F",
    receiptIds: [registration.receipt.receipt_id],
  });
  const admitted = admitForgeTransition({
    current_state: state,
    transition_request: request,
    artifact_store: store,
  });
  assert.equal(admitted.phase_artifact_set, null);
  assert.equal(admitted.admission.phase_artifact_set_id, null);
  assert.deepEqual(admitted.idle_classification, {
    classification_id: classification.classification_id,
    classification_hash: classification.classification_hash,
  });
});

test("transition_receipt_test: IDLE rejects an unrelated receipt and a forged classification identity", (t) => {
  const store = activeArtifactStore(t);
  const unrelated = putJsonArtifact(
    store,
    { artifact_id: "ART-F03-unrelated" },
    {
      artifactId: "ART-F03-unrelated",
      receiptId: "AR-F03-unrelated",
      schemaRef: "schemas/insight-card.schema.json",
      artifactType: "phase_evidence",
    },
  );
  const state = sealState({ phase: "IDLE", revision: 0 });
  const unrelatedRequest = transitionRequest({
    state,
    to: "F",
    receiptIds: [unrelated.receipt.receipt_id],
  });
  assert.throws(
    () =>
      admitForgeTransition({
        current_state: state,
        transition_request: unrelatedRequest,
        artifact_store: store,
      }),
    expectCode("CLASSIFICATION_RECEIPT_REQUIRED"),
  );

  const forged = putJsonArtifact(
    store,
    {
      classification_id: `EWC-${"b".repeat(64)}`,
      classification_hash: `sha256:${"c".repeat(64)}`,
    },
    {
      artifactId: `EWC-${"b".repeat(64)}`,
      receiptId: "AR-F03-forged-classification",
      schemaRef: "schemas/epistemic-work-classification.schema.json",
      artifactType: "epistemic_work_classification",
    },
  );
  const forgedRequest = transitionRequest({
    state,
    to: "F",
    receiptIds: [forged.receipt.receipt_id],
  });
  assert.throws(
    () =>
      admitForgeTransition({
        current_state: state,
        transition_request: forgedRequest,
        artifact_store: store,
      }),
    expectCode("INVALID_CLASSIFICATION_ARTIFACT"),
  );
});

test("transition_receipt_test: IDLE classification projection and state binding fail closed", (t) => {
  const sourceStore = activeArtifactStore(t);
  const { artifact } = registerClassification(sourceStore, { suffix: "baseline" });
  const state = sealState({ phase: "IDLE", revision: 0 });

  const projectionStore = activeArtifactStore(t);
  const wrongProjection = putJsonArtifact(
    projectionStore,
    { ...artifact, required_phases: ["F", "O", "E"] },
    {
      artifactId: artifact.classification_id,
      receiptId: "AR-F03-classification-wrong-projection",
      schemaRef: "schemas/epistemic-work-classification.schema.json",
      artifactType: "epistemic_work_classification",
    },
  );
  const projectionRequest = transitionRequest({
    state,
    to: "F",
    receiptIds: [wrongProjection.receipt.receipt_id],
  });
  assert.throws(
    () =>
      admitForgeTransition({
        current_state: state,
        transition_request: projectionRequest,
        artifact_store: projectionStore,
      }),
    expectCode("INVALID_CLASSIFICATION_ARTIFACT"),
  );

  const causalStore = activeArtifactStore(t);
  const causal = registerClassification(causalStore, { signal: "CAUSAL", suffix: "causal" });
  const classMismatchRequest = transitionRequest({
    state,
    to: "F",
    receiptIds: [causal.registration.receipt.receipt_id],
  });
  assert.throws(
    () =>
      admitForgeTransition({
        current_state: state,
        transition_request: classMismatchRequest,
        artifact_store: causalStore,
      }),
    expectCode("CLASSIFICATION_STATE_MISMATCH"),
  );
});

test("transition_receipt_test: IDLE classification requires exact schema-validation evidence", (t) => {
  const store = activeArtifactStore(t);
  const { registration } = registerClassification(store, { suffix: "schema-receipt" });
  const state = sealState({ phase: "IDLE", revision: 0 });
  const forgedResolver = {
    resolveReceipt(receiptId) {
      const resolved = store.resolveReceipt(receiptId);
      const receipt = {
        ...resolved.receipt,
        validation_results: resolved.receipt.validation_results.filter(
          (row) => row.check !== "canonical_schema_validation",
        ),
      };
      const { receipt_hash: ignored, ...semantic } = receipt;
      void ignored;
      return {
        ...resolved,
        receipt: { ...semantic, receipt_hash: sha256TransitionJson(semantic) },
      };
    },
  };
  const request = transitionRequest({
    state,
    to: "F",
    receiptIds: [registration.receipt.receipt_id],
  });
  assert.throws(
    () =>
      admitForgeTransition({
        current_state: state,
        transition_request: request,
        artifact_store: forgedResolver,
      }),
    expectCode("CLASSIFICATION_SCHEMA_RECEIPT_REQUIRED"),
  );
});

test("transition_receipt_test: incomplete, invalid, and tampered phase sets cannot advance", (t) => {
  for (const row of [
    { name: "incomplete", complete: false, missingKinds: ["InsightCard"], status: "VALID", code: "PHASE_ARTIFACT_SET_INCOMPLETE" },
    { name: "invalid", complete: true, missingKinds: [], status: "INVALID", code: "PHASE_ARTIFACT_NOT_VALID" },
  ]) {
    const store = activeArtifactStore(t);
    const evidence = registerPhaseEvidence(store, { suffix: row.name });
    evidence.status = row.status;
    const phaseSet = sealPhaseArtifactSet({
      phase: "F",
      requiredArtifacts: [evidence],
      complete: row.complete,
      missingKinds: row.missingKinds,
      suffix: row.name,
    });
    const setRegistration = registerPhaseArtifactSet(store, phaseSet);
    const state = sealState({ artifactIds: [evidence.artifact_id] });
    const request = transitionRequest({
      state,
      receiptIds: [evidence.receipt_id, setRegistration.receipt.receipt_id],
    });
    assert.throws(
      () =>
        admitForgeTransition({ current_state: state, transition_request: request, artifact_store: store }),
      expectCode(row.code),
    );
  }

  const store = activeArtifactStore(t);
  const evidence = registerPhaseEvidence(store, { suffix: "tampered" });
  const sealed = sealPhaseArtifactSet({ phase: "F", requiredArtifacts: [evidence], suffix: "tampered" });
  const tampered = { ...sealed, missing_kinds: ["post-seal mutation"] };
  const registration = registerPhaseArtifactSet(store, tampered);
  const state = sealState({ artifactIds: [evidence.artifact_id] });
  const request = transitionRequest({
    state,
    receiptIds: [evidence.receipt_id, registration.receipt.receipt_id],
  });
  assert.throws(
    () => admitForgeTransition({ current_state: state, transition_request: request, artifact_store: store }),
    expectCode("PHASE_ARTIFACT_SET_HASH_MISMATCH"),
  );
});

test("transition_receipt_test: phase entries bind exact receipt, hash, schema, and state retention", (t) => {
  for (const mutation of ["receipt", "hash", "schema", "state"]) {
    const store = activeArtifactStore(t);
    const evidence = registerPhaseEvidence(store, { suffix: `binding-${mutation}` });
    const mutated = { ...evidence };
    if (mutation === "receipt") mutated.receipt_id = "AR-F03-unrelated";
    if (mutation === "hash") mutated.content_hash = `sha256:${"1".repeat(64)}`;
    if (mutation === "schema") mutated.schema_ref = "schemas/other.schema.json";
    const phaseSet = sealPhaseArtifactSet({
      phase: "F",
      requiredArtifacts: [mutated],
      suffix: `binding-${mutation}`,
    });
    const setRegistration = registerPhaseArtifactSet(store, phaseSet);
    const state = sealState({ artifactIds: mutation === "state" ? [] : [evidence.artifact_id] });
    const request = transitionRequest({
      state,
      receiptIds: [evidence.receipt_id, setRegistration.receipt.receipt_id],
    });
    assert.throws(
      () => admitForgeTransition({ current_state: state, transition_request: request, artifact_store: store }),
      expectCode(mutation === "state" ? "PHASE_ARTIFACT_NOT_IN_STATE" : "PHASE_ARTIFACT_RECEIPT_MISMATCH"),
    );
  }
});

test("transition_receipt_test: session, revision, phase, and state hash are admission inputs", (t) => {
  const fixture = phaseTransitionFixture(t, { suffix: "bindings" });
  const cases = [
    [{ ...fixture.request, session_id: "FS-F03-other" }, "SESSION_MISMATCH"],
    [{ ...fixture.request, expected_revision: fixture.state.revision + 1 }, "STALE_REVISION"],
    [{ ...fixture.request, from_phase: "O" }, "FROM_PHASE_MISMATCH"],
  ];
  for (const [request, code] of cases) {
    assert.throws(
      () => admitForgeTransition({ current_state: fixture.state, transition_request: request, artifact_store: fixture.store }),
      expectCode(code),
    );
  }
  assert.throws(
    () =>
      admitForgeTransition({
        current_state: { ...fixture.state, open_blockers: ["mutated"] },
        transition_request: fixture.request,
        artifact_store: fixture.store,
      }),
    expectCode("FORGE_STATE_HASH_MISMATCH"),
  );
});

test("transition_receipt_test: E requires exact resolving and satisfied GateDecision artifacts", (t) => {
  const fixture = phaseTransitionFixture(t, { phase: "G", to: "E", suffix: "gate" });
  const passing = sealGateDecision({ ...gateBindings(fixture) });
  const gateRegistration = registerGateDecision(fixture.store, passing);
  const request = transitionRequest({
    state: fixture.state,
    to: "E",
    receiptIds: [...fixture.receiptIds, gateRegistration.receipt.receipt_id],
    gateResultIds: [passing.gate_id],
  });
  const admitted = admitForgeTransition({
    current_state: fixture.state,
    transition_request: request,
    artifact_store: fixture.store,
  });
  assert.deepEqual(admitted.admission.gate_decisions, [
    { gate_id: passing.gate_id, decision_hash: passing.decision_hash, status: "PASS" },
  ]);

  const missing = transitionRequest({
    state: fixture.state,
    to: "E",
    receiptIds: fixture.receiptIds,
  });
  assert.throws(
    () => admitForgeTransition({ current_state: fixture.state, transition_request: missing, artifact_store: fixture.store }),
    expectCode("GATE_DECISION_REQUIRED"),
  );
});

test("transition_receipt_test: unresolved, failing, blocked, and forged gates cannot admit E", (t) => {
  for (const status of ["FAIL", "BLOCK"]) {
    const fixture = phaseTransitionFixture(t, { phase: "G", to: "E", suffix: `gate-${status}` });
    const decision = sealGateDecision({
      ...gateBindings(fixture),
      gateId: `GD-F03-${status}`,
      status,
    });
    const gate = registerGateDecision(fixture.store, decision);
    const request = transitionRequest({
      state: fixture.state,
      to: "E",
      receiptIds: [...fixture.receiptIds, gate.receipt.receipt_id],
      gateResultIds: [decision.gate_id],
    });
    assert.throws(
      () => admitForgeTransition({ current_state: fixture.state, transition_request: request, artifact_store: fixture.store }),
      expectCode("UNSATISFIED_GATE"),
    );
  }

  const fixture = phaseTransitionFixture(t, { phase: "G", to: "E", suffix: "gate-forged" });
  const valid = sealGateDecision({
    ...gateBindings(fixture),
    gateId: "GD-F03-forged",
  });
  const forged = { ...valid, reasons: ["mutated after decision"] };
  const gate = registerGateDecision(fixture.store, forged);
  const request = transitionRequest({
    state: fixture.state,
    to: "E",
    receiptIds: [...fixture.receiptIds, gate.receipt.receipt_id],
    gateResultIds: [forged.gate_id],
  });
  assert.throws(
    () => admitForgeTransition({ current_state: fixture.state, transition_request: request, artifact_store: fixture.store }),
    expectCode("GATE_DECISION_HASH_MISMATCH"),
  );
});

test("transition_receipt_test: GateDecision evidence IDs must resolve through transition receipts", (t) => {
  const fixture = phaseTransitionFixture(t, { phase: "G", to: "E", suffix: "gate-evidence" });
  const decision = sealGateDecision({
    ...gateBindings(fixture),
    gateId: "GD-F03-unresolved-evidence",
    evidenceIds: ["ART-F03-missing-gate-evidence"],
  });
  const gate = registerGateDecision(fixture.store, decision);
  const request = transitionRequest({
    state: fixture.state,
    to: "E",
    receiptIds: [...fixture.receiptIds, gate.receipt.receipt_id],
    gateResultIds: [decision.gate_id],
  });
  assert.throws(
    () =>
      admitForgeTransition({
        current_state: fixture.state,
        transition_request: request,
        artifact_store: fixture.store,
      }),
    expectCode("GATE_EVIDENCE_UNRESOLVED"),
  );
});

test("transition_receipt_test: policy-evidenced NOT_REQUIRED is a satisfied PASS conclusion", (t) => {
  const fixture = phaseTransitionFixture(t, {
    phase: "G",
    to: "E",
    suffix: "gate-not-required",
  });
  const decision = sealGateDecision({
    ...gateBindings(fixture),
    gateId: "GD-F03-policy-not-required",
    status: "PASS",
    decision: "NOT_REQUIRED",
    evidenceIds: [fixture.evidence.artifact_id],
  });
  const gate = registerGateDecision(fixture.store, decision);
  const request = transitionRequest({
    state: fixture.state,
    to: "E",
    receiptIds: [...fixture.receiptIds, gate.receipt.receipt_id],
    gateResultIds: [decision.gate_id],
  });

  const admitted = admitForgeTransition({
    current_state: fixture.state,
    transition_request: request,
    artifact_store: fixture.store,
  });
  assert.equal(admitted.gate_decisions[0].decision, "NOT_REQUIRED");
  assert.equal(admitted.gate_decisions[0].status, "PASS");
  assert.deepEqual(admitted.admission.gate_decisions, [
    { gate_id: decision.gate_id, decision_hash: decision.decision_hash, status: "PASS" },
  ]);
});

test("transition_receipt_test: canonical GateDecision fields and authority bindings fail closed", (t) => {
  const rows = [
    {
      name: "missing-gate-version",
      mutate: (decision) => {
        const { gate_version: ignored, ...withoutGateVersion } = decision;
        void ignored;
        return withoutGateVersion;
      },
      code: "INVALID_GATE_DECISION",
    },
    {
      name: "policy-mismatch",
      mutate: (decision) =>
        resealGateDecision({ ...decision, policy_bundle_hash: `sha256:${"9".repeat(64)}` }),
      code: "GATE_DECISION_POLICY_MISMATCH",
    },
    {
      name: "unresolved-input",
      mutate: (decision) =>
        resealGateDecision({
          ...decision,
          input_artifact_ids: ["ART-F03-unresolved-gate-input"],
        }),
      code: "GATE_INPUT_ARTIFACT_UNRESOLVED",
    },
    {
      name: "decision-status-mismatch",
      mutate: (decision) => resealGateDecision({ ...decision, decision: "FAIL" }),
      code: "GATE_DECISION_STATUS_MISMATCH",
    },
    {
      name: "not-required-with-failing-status",
      mutate: (decision) =>
        resealGateDecision({ ...decision, status: "FAIL", decision: "NOT_REQUIRED" }),
      code: "GATE_DECISION_STATUS_MISMATCH",
    },
  ];

  for (const row of rows) {
    const fixture = phaseTransitionFixture(t, {
      phase: "G",
      to: "E",
      suffix: `canonical-${row.name}`,
    });
    const valid = sealGateDecision({
      ...gateBindings(fixture),
      gateId: `GD-F03-canonical-${row.name}`,
    });
    const decision = row.mutate(valid);
    const gate = registerGateDecision(fixture.store, decision);
    const request = transitionRequest({
      state: fixture.state,
      to: "E",
      receiptIds: [...fixture.receiptIds, gate.receipt.receipt_id],
      gateResultIds: [decision.gate_id],
    });
    assert.throws(
      () =>
        admitForgeTransition({
          current_state: fixture.state,
          transition_request: request,
          artifact_store: fixture.store,
        }),
      expectCode(row.code),
      row.name,
    );
  }
});

test("transition_receipt_test: FAIL and BLOCK are never absorbed outside E", (t) => {
  for (const status of ["FAIL", "BLOCK"]) {
    const fixture = phaseTransitionFixture(t, { phase: "F", to: "O", suffix: `non-e-${status}` });
    const decision = sealGateDecision({
      ...gateBindings(fixture),
      gateId: `GD-F03-non-e-${status}`,
      status,
    });
    const gate = registerGateDecision(fixture.store, decision);
    const request = transitionRequest({
      state: fixture.state,
      to: "O",
      receiptIds: [...fixture.receiptIds, gate.receipt.receipt_id],
      gateResultIds: [decision.gate_id],
    });
    assert.throws(
      () =>
        admitForgeTransition({
          current_state: fixture.state,
          transition_request: request,
          artifact_store: fixture.store,
        }),
      expectCode("UNSATISFIED_GATE"),
    );
  }
});
