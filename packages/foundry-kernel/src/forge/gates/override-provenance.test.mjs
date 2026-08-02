import assert from "node:assert/strict";
import test from "node:test";

import {
  admitForgeTransition,
  sha256TransitionJson,
  TransitionAdmissionError,
} from "./transition-admission-gate.mjs";
import {
  phaseTransitionFixture,
  registerGateDecision,
  registerHumanDecision,
  sealGateDecision,
  sealHumanDecision,
  transitionRequest,
} from "./gate-test-support.mjs";

const expectCode = (code) => (error) =>
  error instanceof TransitionAdmissionError && error.code === code;

const gateBindings = (fixture) => ({
  gateVersion: "4.0.0",
  inputArtifactIds: [fixture.evidence.artifact_id],
  policyBundleHash: fixture.state.policy_hash,
});

const waiverFixture = (t, suffix = "waiver") => {
  const fixture = phaseTransitionFixture(t, { phase: "G", to: "E", suffix });
  const gate = sealGateDecision({
    ...gateBindings(fixture),
    gateId: `GD-F03-${suffix}`,
    status: "WAIVE",
    nonWaivable: false,
    waiverAuthority: "HUMAN-F03-owner",
    waiverReason: "bounded limitation accepted",
  });
  const gateRegistration = registerGateDecision(fixture.store, gate);
  return { ...fixture, gate, gateRegistration };
};

test("override_provenance_test: a valid human-authored decision explicitly admits WAIVE", (t) => {
  const fixture = waiverFixture(t, "style");
  const decision = sealHumanDecision({ gateId: fixture.gate.gate_id });
  const humanRegistration = registerHumanDecision(fixture.store, decision);
  const request = transitionRequest({
    state: fixture.state,
    to: "E",
    receiptIds: [
      ...fixture.receiptIds,
      fixture.gateRegistration.receipt.receipt_id,
      humanRegistration.receipt.receipt_id,
    ],
    gateResultIds: [fixture.gate.gate_id],
    humanDecisionId: decision.decision_id,
  });

  const admitted = admitForgeTransition({
    current_state: fixture.state,
    transition_request: request,
    artifact_store: fixture.store,
  });
  assert.equal(admitted.human_decision.decision_hash, decision.decision_hash);
  assert.equal(admitted.admission.human_decision_id, decision.decision_id);
  assert.equal(admitted.admission.human_decision_hash, decision.decision_hash);
  assert.deepEqual(admitted.admission.gate_decisions, [
    { gate_id: fixture.gate.gate_id, decision_hash: fixture.gate.decision_hash, status: "WAIVE" },
  ]);
});

test("override_provenance_test: authority strings never substitute for a HumanDecision receipt", (t) => {
  const fixture = waiverFixture(t, "missing-human");
  const request = transitionRequest({
    state: fixture.state,
    to: "E",
    receiptIds: [...fixture.receiptIds, fixture.gateRegistration.receipt.receipt_id],
    gateResultIds: [fixture.gate.gate_id],
  });
  assert.throws(
    () => admitForgeTransition({ current_state: fixture.state, transition_request: request, artifact_store: fixture.store }),
    expectCode("HUMAN_DECISION_REQUIRED"),
  );

  const claimed = { ...request, human_decision_id: "HD-F03-missing" };
  assert.throws(
    () => admitForgeTransition({ current_state: fixture.state, transition_request: claimed, artifact_store: fixture.store }),
    expectCode("HUMAN_DECISION_ARTIFACT_REQUIRED"),
  );
});

test("override_provenance_test: non-waivable gates stay non-waivable with human approval", (t) => {
  const fixture = phaseTransitionFixture(t, { phase: "G", to: "E", suffix: "non-waivable" });
  const gate = sealGateDecision({
    ...gateBindings(fixture),
    gateId: "GD-F03-non-waivable",
    status: "WAIVE",
    nonWaivable: true,
    waiverAuthority: "HUMAN-F03-owner",
    waiverReason: "forbidden attempt",
  });
  const gateRegistration = registerGateDecision(fixture.store, gate);
  const decision = sealHumanDecision({ gateId: gate.gate_id });
  const humanRegistration = registerHumanDecision(fixture.store, decision);
  const request = transitionRequest({
    state: fixture.state,
    to: "E",
    receiptIds: [
      ...fixture.receiptIds,
      gateRegistration.receipt.receipt_id,
      humanRegistration.receipt.receipt_id,
    ],
    gateResultIds: [gate.gate_id],
    humanDecisionId: decision.decision_id,
  });
  assert.throws(
    () => admitForgeTransition({ current_state: fixture.state, transition_request: request, artifact_store: fixture.store }),
    expectCode("NON_WAIVABLE_GATE_OVERRIDE"),
  );
});

test("override_provenance_test: service-authored HumanDecision receipts are rejected", (t) => {
  const fixture = waiverFixture(t, "service-human");
  const decision = sealHumanDecision({ gateId: fixture.gate.gate_id });
  const humanRegistration = registerHumanDecision(fixture.store, decision, {
    actorId: decision.authority_id,
    actorType: "service",
  });
  const request = transitionRequest({
    state: fixture.state,
    to: "E",
    receiptIds: [
      ...fixture.receiptIds,
      fixture.gateRegistration.receipt.receipt_id,
      humanRegistration.receipt.receipt_id,
    ],
    gateResultIds: [fixture.gate.gate_id],
    humanDecisionId: decision.decision_id,
  });
  assert.throws(
    () => admitForgeTransition({ current_state: fixture.state, transition_request: request, artifact_store: fixture.store }),
    expectCode("HUMAN_DECISION_AUTHORITY_MISMATCH"),
  );
});

test("override_provenance_test: wrong decision type, authority, scope, run, and hash fail closed", (t) => {
  const cases = [
    {
      name: "type",
      decision: (gate) => sealHumanDecision({ gateId: gate.gate_id, decisionType: "accept" }),
      code: "HUMAN_DECISION_TYPE_MISMATCH",
    },
    {
      name: "authority",
      decision: (gate) => sealHumanDecision({ gateId: gate.gate_id, authorityId: "HUMAN-F03-other" }),
      code: "HUMAN_DECISION_AUTHORITY_MISMATCH",
    },
    {
      name: "scope",
      decision: (gate) => {
        const decision = sealHumanDecision({ gateId: "GD-F03-other", affectedArtifactIds: [] });
        return { ...decision, run_id: gate.run_id };
      },
      reseal: true,
      code: "HUMAN_DECISION_SCOPE_MISMATCH",
    },
    {
      name: "run",
      decision: (gate) => sealHumanDecision({ gateId: gate.gate_id, runId: "RUN-F03-other" }),
      code: "HUMAN_DECISION_SCOPE_MISMATCH",
    },
    {
      name: "hash",
      decision: (gate) => ({ ...sealHumanDecision({ gateId: gate.gate_id }), rationale: "mutated" }),
      code: "HUMAN_DECISION_INTEGRITY_FAILED",
    },
  ];

  for (const row of cases) {
    const fixture = waiverFixture(t, `wrong-${row.name}`);
    let decision = row.decision(fixture.gate);
    if (row.reseal === true) {
      const { decision_hash: ignored, ...semantic } = decision;
      void ignored;
      decision = { ...semantic, decision_hash: sha256TransitionJson(semantic) };
    }
    const humanRegistration = registerHumanDecision(fixture.store, decision);
    const request = transitionRequest({
      state: fixture.state,
      to: "E",
      receiptIds: [
        ...fixture.receiptIds,
        fixture.gateRegistration.receipt.receipt_id,
        humanRegistration.receipt.receipt_id,
      ],
      gateResultIds: [fixture.gate.gate_id],
      humanDecisionId: decision.decision_id,
    });
    assert.throws(
      () => admitForgeTransition({ current_state: fixture.state, transition_request: request, artifact_store: fixture.store }),
      expectCode(row.code),
      row.name,
    );
  }
});

test("override_provenance_test: an undeclared or unused override artifact is never implicit", (t) => {
  const fixture = phaseTransitionFixture(t, { phase: "G", to: "E", suffix: "unused" });
  const gate = sealGateDecision({
    ...gateBindings(fixture),
    gateId: "GD-F03-pass-unused",
  });
  const gateRegistration = registerGateDecision(fixture.store, gate);
  const decision = sealHumanDecision({ gateId: gate.gate_id });
  const humanRegistration = registerHumanDecision(fixture.store, decision);

  const undeclared = transitionRequest({
    state: fixture.state,
    to: "E",
    receiptIds: [
      ...fixture.receiptIds,
      gateRegistration.receipt.receipt_id,
      humanRegistration.receipt.receipt_id,
    ],
    gateResultIds: [gate.gate_id],
  });
  assert.throws(
    () => admitForgeTransition({ current_state: fixture.state, transition_request: undeclared, artifact_store: fixture.store }),
    expectCode("HUMAN_DECISION_NOT_DECLARED"),
  );

  const unused = { ...undeclared, human_decision_id: decision.decision_id };
  assert.throws(
    () => admitForgeTransition({ current_state: fixture.state, transition_request: unused, artifact_store: fixture.store }),
    expectCode("HUMAN_DECISION_SCOPE_MISMATCH"),
  );
});
