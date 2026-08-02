// negative_and_adversarial_tests — every way observability can lie, refused.
//
// Observability fails quietly and expensively: it claims a host that sends no
// events, keeps a registration for an event type nobody delivers, quietly turns
// an observer into an enforcer, reads the holdout material it was built to stay
// away from, or reports coverage it does not have.  So each hostile input is
// staged as a copy of the declaring sources that is wrong in exactly one way,
// and each must be refused by its own code.
//
// The hook gateway is imported code rather than a staged file, so its
// vocabulary is the sealed one in every case below.

import assert from "node:assert/strict";
import { rmSync } from "node:fs";
import test from "node:test";

import {
  assertCoverageClaim,
  assertObservationEnvelope,
  coverageReport,
  deriveEvolutionEventTypes,
  EVOLUTION_BUNDLE_PATH,
  HOLDOUT_BUNDLE_PATH,
  HookObservabilityError,
  loadObservability,
  observeEvolutionEvent,
  REGISTRATIONS_PATH,
} from "./index.mjs";
import {
  asyncRefusal,
  byId,
  CLEAN_PAYLOAD,
  OBSERVATION_TEMPLATE,
  refusal,
  stageBundle,
  stageHoldoutSchema,
  stageRegistrations,
  stageRoot,
  writeStagedJson,
} from "./observability-fixtures.mjs";

const loaded = loadObservability();
const report = coverageReport(loaded);
const honestClaim = () => ({
  coverage_by_event_type: { ...report.coverage_by_event_type },
  not_observed: [...report.not_observed],
});
const refused = (root) => {
  const error = refusal(() => loadObservability({ root }));
  assert.ok(error instanceof HookObservabilityError, error.message);
  return error;
};
const refusedClaim = (claim) => {
  const error = refusal(() => assertCoverageClaim(loaded, claim));
  assert.ok(error instanceof HookObservabilityError, error.message);
  return error;
};

test("h05_refuse: a host the gateway does not declare is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-HOLDOUT-STOP").hosts = ["claude", "gemini"];
  });

  const error = refused(root);
  assert.equal(error.code, "HOST_UNDECLARED");
  assert.equal(error.context.value, "gemini");
});

test("h05_refuse: a host outside the declared observed set is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-HOLDOUT-STOP").hosts = ["claude", "other"];
  });

  const error = refused(root);
  assert.equal(error.code, "HOST_UNDECLARED");
  assert.equal(error.context.value, "other");
});

test("h05_refuse: an event type the gateway does not declare is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-EVOLUTION-PRE-TOOL").event_types = ["PreThought"];
  });

  const error = refused(root);
  assert.equal(error.code, "EVENT_TYPE_UNDECLARED");
  assert.equal(error.context.value, "PreThought");
});

test("h05_refuse: observing outside the evolution event surface is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-EVOLUTION-PRE-TOOL").event_types = ["UserPromptSubmit"];
  });

  const error = refused(root);
  assert.equal(error.code, "EVENT_TYPE_OUT_OF_SURFACE");
  assert.equal(error.context.event_type, "UserPromptSubmit");
});

test("h05_refuse: a bundle registering an undeclared event type is refused", (t) => {
  const root = stageBundle(t, EVOLUTION_BUNDLE_PATH, (bundle) => {
    bundle.hooks.Telepathy = bundle.hooks.PreToolUse;
  });

  const error = refused(root);
  assert.equal(error.code, "EVENT_TYPE_UNDECLARED");
  assert.equal(error.context.event_type, "Telepathy");
});

test("h05_refuse: an empty evolution event surface is refused as vacuous", (t) => {
  const root = stageRoot(t);
  writeStagedJson(root, EVOLUTION_BUNDLE_PATH, { hooks: {} });
  writeStagedJson(root, HOLDOUT_BUNDLE_PATH, { hooks: {} });

  const error = refused(root);
  assert.equal(error.code, "EVOLUTION_SURFACE_EMPTY");
});

test("h05_refuse: a coverage disposition outside the gateway vocabulary is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-EVOLUTION-PRE-TOOL").coverage = "TOTAL";
  });

  const error = refused(root);
  assert.equal(error.code, "COVERAGE_UNDECLARED");
  assert.equal(error.context.coverage, "TOTAL");
});

test("h05_refuse: a coverage rank that is not the gateway vocabulary is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    declaration.coverage_rank = { ...declaration.coverage_rank, TOTAL: 3 };
  });

  const error = refused(root);
  assert.equal(error.code, "COVERAGE_UNDECLARED");
  assert.ok(error.context.declared.includes("TOTAL"));
});

test("h05_refuse: a registration claiming more coverage than its hosts is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-HOLDOUT-STOP").coverage = "OBSERVED";
  });

  const error = refused(root);
  assert.equal(error.code, "COVERAGE_OVERCLAIMED");
  assert.equal(error.context.declared, "OBSERVED");
  assert.equal(error.context.derived, "PARTIAL");
});

test("h05_refuse: a registration hiding coverage it actually has is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-EVOLUTION-PRE-TOOL").coverage = "UNOBSERVED";
  });

  const error = refused(root);
  assert.equal(error.code, "COVERAGE_UNDERSTATED");
  assert.equal(error.context.derived, "OBSERVED");
});

test("h05_refuse: an observer emitting a control-bearing decision is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-EVOLUTION-PRE-TOOL").emits_decision = "BLOCK";
  });

  const error = refused(root);
  assert.equal(error.code, "OBSERVER_AUTHORITY_CLAIMED");
  assert.equal(error.context.decision, "BLOCK");
});

test("h05_refuse: reclassifying a decision as control does not smuggle it back in", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    declaration.observer_decisions = ["ERROR", "NOT_APPLICABLE"];
    declaration.control_decisions = ["ADVISORY", "ALLOW", "BLOCK", "REWRITE"];
  });

  const error = refused(root);
  assert.equal(error.code, "OBSERVER_AUTHORITY_CLAIMED");
  assert.equal(error.context.decision, "ADVISORY");
});

test("h05_refuse: a decision the gateway does not declare is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-EVOLUTION-PRE-TOOL").emits_decision = "WATCH";
  });

  const error = refused(root);
  assert.equal(error.code, "DECISION_UNDECLARED");
  assert.equal(error.context.decision, "WATCH");
});

test("h05_refuse: an incomplete decision partition is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    declaration.observer_decisions = ["ADVISORY", "NOT_APPLICABLE"];
  });

  const error = refused(root);
  assert.equal(error.code, "DECISION_PARTITION_INCOMPLETE");
  assert.ok(error.context.vocabulary.includes("ERROR"));
});

test("h05_refuse: an overlapping decision partition is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    declaration.control_decisions = ["ADVISORY", "ALLOW", "BLOCK", "REWRITE"];
  });

  const error = refused(root);
  assert.equal(error.code, "DECISION_PARTITION_INCOMPLETE");
});

test("h05_refuse: requesting a hidden holdout partition is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-HOLDOUT-STOP").payload_access = [
      "acl_policy_hash",
      "hidden_partition_handles",
    ];
  });

  const error = refused(root);
  assert.equal(error.code, "HOLDOUT_OBSERVATION_DENIED");
  assert.equal(error.context.field, "hidden_partition_handles");
});

test("h05_refuse: requesting a sealed holdout access flag is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-EVOLUTION-PRE-TOOL").payload_access = ["candidate_access"];
  });

  const error = refused(root);
  assert.equal(error.code, "HOLDOUT_OBSERVATION_DENIED");
  assert.equal(error.context.field, "candidate_access");
});

test("h05_refuse: requesting a field the holdout schema does not declare is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-EVOLUTION-PRE-TOOL").payload_access = ["hidden_answers"];
  });

  const error = refused(root);
  assert.equal(error.code, "HOLDOUT_FLAG_UNDECLARED");
  assert.equal(error.context.field, "hidden_answers");
});

test("h05_refuse: a holdout schema that pins nothing closed is refused as vacuous", (t) => {
  const root = stageHoldoutSchema(t, (schema) => {
    for (const [name, definition] of Object.entries(schema.properties)) {
      if (definition.const === false) schema.properties[name] = { type: "boolean" };
    }
  });

  const error = refused(root);
  assert.equal(error.code, "HOLDOUT_PREDICATE_EMPTY");
  assert.deepEqual(error.context.denied_access_flags, []);
});

test("h05_refuse: two registrations sharing one identifier are refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-HOLDOUT-STOP").registration_id = "EFH05-OBS-EVOLUTION-PRE-TOOL";
  });

  const error = refused(root);
  assert.equal(error.code, "REGISTRATION_DUPLICATED");
  assert.equal(error.context.registration_id, "EFH05-OBS-EVOLUTION-PRE-TOOL");
});

test("h05_refuse: two registrations claiming one host and event pair are refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-EVOLUTION-POST-TOOL").event_types = [
      "PostToolUse",
      "PreToolUse",
    ];
  });

  const error = refused(root);
  assert.equal(error.code, "REGISTRATION_DUPLICATED");
  assert.equal(error.context.pair, "claude:PreToolUse");
  assert.deepEqual(error.context.registration_ids, [
    "EFH05-OBS-EVOLUTION-POST-TOOL",
    "EFH05-OBS-EVOLUTION-PRE-TOOL",
  ]);
});

test("h05_refuse: an unsorted declaration is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    declaration.registrations = [...declaration.registrations].reverse();
  });

  const error = refused(root);
  assert.equal(error.code, "DECLARATION_NONCANONICAL");
});

test("h05_refuse: a repeated host entry is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-HOLDOUT-STOP").hosts = ["claude", "claude"];
  });

  const error = refused(root);
  assert.equal(error.code, "DECLARATION_NONCANONICAL");
});

test("h05_refuse: an unexpected field on a registration is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-EVOLUTION-PRE-TOOL").may_block = true;
  });

  const error = refused(root);
  assert.equal(error.code, "REGISTRATION_UNREADABLE");
  assert.ok(error.context.actual.includes("may_block"));
});

test("h05_refuse: a missing registration-set field is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    delete declaration.observed_hosts;
  });

  const error = refused(root);
  assert.equal(error.code, "REGISTRATION_UNREADABLE");
});

test("h05_refuse: a non-positive hook timeout is refused", (t) => {
  const root = stageRegistrations(t, (declaration) => {
    byId(declaration, "EFH05-OBS-EVOLUTION-PRE-TOOL").timeout_seconds = 0;
  });

  const error = refused(root);
  assert.equal(error.code, "REGISTRATION_UNREADABLE");
  assert.equal(error.context.registration_id, "EFH05-OBS-EVOLUTION-PRE-TOOL");
});

test("h05_refuse: a missing registration file is refused rather than treated as empty", (t) => {
  const root = stageRoot(t);
  rmSync(`${root}/${REGISTRATIONS_PATH}`, { force: true });

  const error = refused(root);
  assert.equal(error.code, "REGISTRATION_UNREADABLE");
  assert.equal(error.context.path, REGISTRATIONS_PATH);
});

test("h05_refuse: a bundle without a hooks object is refused", () => {
  const error = refusal(() => deriveEvolutionEventTypes([[EVOLUTION_BUNDLE_PATH, { hooks: [] }]]));

  assert.equal(error.code, "REGISTRATION_UNREADABLE");
  assert.equal(error.context.path, EVOLUTION_BUNDLE_PATH);
});

test("h05_refuse: an observation for an undeclared registration is refused", async () => {
  const error = await asyncRefusal(() =>
    observeEvolutionEvent(loaded, {
      ...OBSERVATION_TEMPLATE,
      payload: CLEAN_PAYLOAD,
      registrationId: "EFH05-OBS-INVENTED",
    }),
  );

  assert.equal(error.code, "OBSERVATION_UNREGISTERED");
  assert.equal(error.context.registration_id, "EFH05-OBS-INVENTED");
});

test("h05_refuse: an observation from a host the registration does not watch is refused", async () => {
  const error = await asyncRefusal(() =>
    observeEvolutionEvent(loaded, {
      ...OBSERVATION_TEMPLATE,
      host: "other",
      payload: CLEAN_PAYLOAD,
    }),
  );

  assert.equal(error.code, "OBSERVATION_UNREGISTERED");
  assert.equal(error.context.host, "other");
});

test("h05_refuse: an observation for an event the registration does not watch is refused", async () => {
  const error = await asyncRefusal(() =>
    observeEvolutionEvent(loaded, {
      ...OBSERVATION_TEMPLATE,
      eventType: "PostToolUse",
      payload: CLEAN_PAYLOAD,
    }),
  );

  assert.equal(error.code, "OBSERVATION_UNREGISTERED");
  assert.equal(error.context.event_type, "PostToolUse");
});

test("h05_refuse: an observation without a caller timestamp is refused", async () => {
  const error = await asyncRefusal(() =>
    observeEvolutionEvent(loaded, {
      ...OBSERVATION_TEMPLATE,
      observedAt: undefined,
      payload: CLEAN_PAYLOAD,
    }),
  );

  assert.equal(error.code, "TIMESTAMP_REQUIRED");
});

test("h05_refuse: an observation carrying holdout-flagged material is refused", async () => {
  const error = await asyncRefusal(() =>
    observeEvolutionEvent(loaded, {
      ...OBSERVATION_TEMPLATE,
      payload: { candidate_id: "CAND-0003", hidden_partition_handles: ["H1"] },
    }),
  );

  assert.equal(error.code, "HOLDOUT_OBSERVATION_DENIED");
  assert.deepEqual(error.context.paths, ["payload.hidden_partition_handles"]);
});

test("h05_refuse: holdout material nested inside an observed payload is refused", async () => {
  const error = await asyncRefusal(() =>
    observeEvolutionEvent(loaded, {
      ...OBSERVATION_TEMPLATE,
      payload: { evaluation: { partitions: [{ ood_partition_handles: ["O1"] }] } },
    }),
  );

  assert.equal(error.code, "HOLDOUT_OBSERVATION_DENIED");
  assert.deepEqual(error.context.paths, [
    "payload.evaluation.partitions[0].ood_partition_handles",
  ]);
});

test("h05_refuse: a non-object observation payload is refused", async () => {
  const error = await asyncRefusal(() =>
    observeEvolutionEvent(loaded, { ...OBSERVATION_TEMPLATE, payload: "raw text" }),
  );

  assert.equal(error.code, "REGISTRATION_UNREADABLE");
});

test("h05_refuse: an envelope altered after sealing is refused", async () => {
  const envelope = await observeEvolutionEvent(loaded, {
    ...OBSERVATION_TEMPLATE,
    payload: CLEAN_PAYLOAD,
  });

  const error = refusal(() =>
    assertObservationEnvelope({ ...envelope, coverage: "UNOBSERVED" }, { case: "tampered" }),
  );
  assert.equal(error.code, "ENVELOPE_REJECTED");
  assert.equal(error.context.gateway_code, "HOOK_ENVELOPE_HASH_MISMATCH");
});

test("h05_refuse: an envelope that is not the declared object is refused", () => {
  const error = refusal(() => assertObservationEnvelope({ coverage: "OBSERVED" }));

  assert.equal(error.code, "ENVELOPE_REJECTED");
  assert.equal(error.context.gateway_code, "HOOK_ENVELOPE_INVALID");
});

test("h05_refuse: a coverage claim asserting full coverage is refused", () => {
  const claim = honestClaim();
  claim.coverage_by_event_type.PreToolUse = "OBSERVED";

  const error = refusedClaim(claim);
  assert.equal(error.code, "COVERAGE_OVERCLAIMED");
  assert.equal(error.context.event_type, "PreToolUse");
});

test("h05_refuse: a coverage claim erasing an observed event type is refused", () => {
  const claim = honestClaim();
  claim.coverage_by_event_type.Stop = "UNOBSERVED";

  const error = refusedClaim(claim);
  assert.equal(error.code, "COVERAGE_UNDERSTATED");
  assert.equal(error.context.event_type, "Stop");
});

test("h05_refuse: a coverage claim omitting an unobserved pair is refused", () => {
  const claim = honestClaim();
  claim.not_observed = claim.not_observed.filter((pair) => pair !== "other:PreToolUse");

  const error = refusedClaim(claim);
  assert.equal(error.code, "COVERAGE_OVERCLAIMED");
  assert.deepEqual(error.context.omitted, ["other:PreToolUse"]);
});

test("h05_refuse: a coverage claim inventing an unobserved pair is refused", () => {
  const claim = honestClaim();
  claim.not_observed = [...claim.not_observed, "codex:PreToolUse"].sort();

  const error = refusedClaim(claim);
  assert.equal(error.code, "COVERAGE_UNDERSTATED");
  assert.deepEqual(error.context.invented, ["codex:PreToolUse"]);
});

test("h05_refuse: a coverage claim outside the gateway vocabulary is refused", () => {
  const claim = honestClaim();
  claim.coverage_by_event_type.SessionStart = "MOSTLY";

  const error = refusedClaim(claim);
  assert.equal(error.code, "COVERAGE_UNDECLARED");
  assert.equal(error.context.event_type, "SessionStart");
});

test("h05_refuse: a coverage claim that is not the declared object is refused", () => {
  const error = refusedClaim({ coverage_by_event_type: {}, not_observed: [], extra: true });

  assert.equal(error.code, "REGISTRATION_UNREADABLE");
});
