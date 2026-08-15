"""Provider diversity, cost, safety and reward-attribution integration gate (X06).

X05 sealed cross-provider mutation routing, the safe delayed-reward bandit and
neutral fallback: ``route_mutation`` keeps a selection inside the parity-approved
eligible set, ``assert_fallback_neutral`` refuses a fallback that alters a
canonical field, ``admit_bandit_reward`` draws a reward only from a validated
basis and refuses one routed at a promotion, ``seal_safe_bandit_state`` bounds a
bandit to a safe policy, and ``route_external_backend_neutral`` keeps an external
backend advisory.  Each surface is correct alone, and none of them answers the
one question this gate exists for: for a single evolution run, do a *diverse* set
of routed providers, the *cost* they carry, the *safe* bandit that adapts them
and the *reward* attributed to them compose into one coherent decision — and does
that composition emit an immutable, re-derivable record that a tampered
sub-decision cannot be laundered into?

This is an *integration* gate.  It composes the sealed X05 surfaces and refuses
the compositions that would breach a boundary none of them can see alone,
restating none of their vocabularies (EF4-I22): every canonical token it reasons
about is either read positionally out of the schema that declares it or delegated
to the sealed module that owns it, so this gate holds no wire literal of its own.

*Provider diversity and cost.*  ``attest_provider_diversity`` re-validates a set
of sealed routing receipts against their canonical schema, re-derives each
receipt's identity so a tampered one is refused rather than counted, requires the
selection to stay inside its own eligible set, and refuses a routed set that
offers no alternative provider at all — a single-provider set is a single point
of authority and failure, not diversity.  The aggregate estimated cost is carried
as *descriptive* bookkeeping only; it is recorded, never gated on a threshold, so
cost never becomes an authority that promotes or rejects a candidate.

*Safe reward attribution.*  ``attribute_provider_reward`` composes X05's
``admit_bandit_reward`` so the reward is drawn from a validated basis, never the
immediate proxy a candidate can game (EF4-I54), is backed by a statistical
correction (EF4-I53) and is refused outright when routed at a promotion decision
(EF4-I45).  ``assert_composed_neutrality`` composes the sealed fallback
neutrality check, and ``refuse_backend_provider_authority`` composes the sealed
external-backend boundary so no backend field is bound onto a Foundry authority
surface (EF4-I63).

*Composition.*  ``integrate_provider_gate`` binds the sealed sub-decisions into
one integration receipt, re-deriving each sub-receipt from its own content so a
tampered sub-decision cannot be laundered into the combined record, refusing a
bandit state that does not run under a policy the bandit module bounds as safe,
refusing a reward attributed to a routing decision outside the attested diverse
set, and refusing any sealed sub-decision that reaches for promotion or backend
authority.

Every decision resolves to an immutable, content-addressed receipt: two runs over
equal inputs produce byte-equal receipts.  Nothing here scores, promotes, mutates
its inputs, or reads a clock.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...contracts import ContractViolation, validate_artifact
from ...domain.hashing import hash_excluding, sha256_of_payload
from ...evaluation import bandits
from ..v4_x05 import (
    MutationRoutingError,
    admit_bandit_reward,
    assert_fallback_neutral,
    route_external_backend_neutral,
)

#: Every way this gate refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record a decision derived from something it never validated"
    ),
    "ROUTING_CONTRACT_VIOLATED": (
        "a routing receipt does not satisfy its canonical schema, so its "
        "selection, eligible set and cost would be read from a shape no contract "
        "admits"
    ),
    "ROUTING_RECEIPT_TAMPERED": (
        "a routing receipt does not re-derive its own identifier and hash, so the "
        "diversity and cost being attested are not the ones the sealed routing "
        "surface produced"
    ),
    "ROUTING_SELECTION_NOT_ELIGIBLE": (
        "a routing receipt selects a provider outside its own eligible set, so a "
        "provider parity never cleared would be counted toward diversity"
    ),
    "PROVIDER_DIVERSITY_ABSENT": (
        "the routed set offers no alternative provider, so a single provider is a "
        "single point of authority and failure rather than a diverse set that can "
        "fail one over to another"
    ),
    "REWARD_ATTRIBUTION_REFUSED": (
        "the sealed bandit-reward admission refused the reward, and this gate "
        "surfaces that refusal instead of attributing a reward the safe-bandit "
        "surface would not admit"
    ),
    "REWARD_ATTRIBUTION_TAMPERED": (
        "the reward admission does not re-derive its own identifier and hash, so "
        "the reward being bound is not the reward the sealed surface admitted"
    ),
    "REWARD_DRIVES_PROMOTION": (
        "the reward admission is marked as driving a promotion decision, and a "
        "bandit reward may order search but never promote a candidate (EF4-I45)"
    ),
    "REWARD_ROUTING_UNLISTED": (
        "the reward is attributed to a routing decision outside the attested "
        "diverse set, so a reward would be routed to a provider this gate never "
        "admitted as part of the run's diversity"
    ),
    "DIVERSITY_ATTESTATION_TAMPERED": (
        "the diversity attestation does not re-derive its own identifier and "
        "hash, so the diverse set being integrated is not the one that was "
        "attested"
    ),
    "NEUTRALITY_REFUSED": (
        "the sealed fallback-neutrality check refused the fallback, and this gate "
        "surfaces that refusal instead of admitting a provider that altered what "
        "a node result means"
    ),
    "FALLBACK_RECEIPT_TAMPERED": (
        "a fallback neutrality receipt does not re-derive its own identifier and "
        "hash, so the neutrality being bound is not the neutrality that was sealed"
    ),
    "FALLBACK_SEMANTICS_ALTERED": (
        "a sealed fallback receipt records that semantics were not preserved, so "
        "binding it would admit a provider that changed a canonical field of a "
        "node result"
    ),
    "BANDIT_STATE_CONTRACT_VIOLATED": (
        "the bandit state does not satisfy its canonical schema, so its policy "
        "and arms would be read from a shape no contract admits"
    ),
    "BANDIT_STATE_TAMPERED": (
        "the bandit state does not re-derive its own hash, so the state being "
        "integrated is not the state the bandit module sealed"
    ),
    "BANDIT_POLICY_UNSAFE": (
        "the bandit state does not run under a policy the bandit module bounds as "
        "safe, so its exploration is not constrained"
    ),
    "BACKEND_PROVIDER_AUTHORITY_LEAK": (
        "an external backend used as a provider would bind one of its own fields "
        "onto a Foundry authority surface, so a backend's bookkeeping would become "
        "authority it may never hold (EF4-I63)"
    ),
}

#: Canonical schema names this gate reads.  Each is a registered canonical
#: contract, validated before use rather than restated as fields here.
ROUTING_KIND = "model-routing-receipt"
BANDIT_STATE_KIND = "operator-bandit-state"

#: Identifier prefixes.  ``XPD`` and ``XIG`` are minted here; the others are the
#: prefixes the sealed X05 surface mints, re-derived here to prove a sub-receipt
#: was produced by that surface rather than forged.  Every identifier is derived
#: from the record's own content, so nothing here needs entropy and two runs over
#: equal inputs produce byte-equal records.
DIVERSITY_ATTESTATION_PREFIX = "XPD-"
INTEGRATION_RECEIPT_PREFIX = "XIG-"
REWARD_ADMISSION_PREFIX = "XBR-"
FALLBACK_RECEIPT_PREFIX = "XFN-"

#: The least number of distinct providers a routed set must span to be diverse.
#: Below two there is no alternative to fail over to, so the set is not diverse.
MINIMUM_PROVIDERS = 2

#: The concerns this integration gate reconciles, named so the combined receipt
#: records which boundaries it composed.  Compound names, none a wire value.
CONCERN_PROVIDER_DIVERSITY = "provider_diversity_and_cost"
CONCERN_REWARD_ATTRIBUTION = "safe_reward_attribution"
CONCERN_PROVIDER_SAFETY = "safe_bandit_policy"
CONCERN_FALLBACK_NEUTRALITY = "fallback_provider_neutrality"
CONCERN_BACKEND_NON_AUTHORITY = "backend_non_authority"


class ProviderGateError(ValueError):
    """The gate refuses a composition, or its evidence, with a documented code."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise ProviderGateError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ProviderGateError(code, message, context)


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return dict(value)  # type: ignore[arg-type]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def _require_sequence(value: object, label: str) -> list[Any]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        _fail("INPUT_INVALID", f"{label} must be a sequence", {"label": label})
    return list(value)  # type: ignore[arg-type]


def _digest_body(payload: Any) -> str:
    """The hex body of a canonical digest, used to derive content-bound ids."""
    return sha256_of_payload(payload)[len("sha256:") :]


def _identified(
    record: dict[str, Any], prefix: str, id_field: str, hash_field: str
) -> dict[str, Any]:
    """Attach a content-derived identifier and the record's own hash."""
    record[id_field] = prefix + _digest_body(record)
    record[hash_field] = hash_excluding(record, hash_field)
    return record


def _require_receipt_identity(
    record: Mapping[str, Any], prefix: str, id_field: str, hash_field: str, code: str
) -> dict[str, Any]:
    """Re-derive a sealed sub-receipt's identifier and hash from its own content.

    The identity scheme is the sealed X05 surface's own: the identifier is the
    prefix over the digest of the body without its identity fields, and the hash
    is the digest of the record without its hash field.  A record that does not
    re-derive both is refused, so a tampered sub-decision cannot be laundered into
    a composition that reads it.
    """
    document = _require_mapping(record, "sub_receipt")
    body = {
        key: value
        for key, value in document.items()
        if key not in {id_field, hash_field}
    }
    expected_id = prefix + _digest_body(body)
    if document.get(id_field) != expected_id or document.get(
        hash_field
    ) != hash_excluding(document, hash_field):
        _fail(
            code,
            "a sealed sub-receipt does not re-derive its own identity",
            {"expected_id": expected_id, "stated_id": document.get(id_field)},
        )
    return document


def attest_provider_diversity(
    *,
    routing_receipts: Sequence[Mapping[str, Any]],
    minimum_providers: int = MINIMUM_PROVIDERS,
) -> dict[str, Any]:
    """Attest that a set of sealed routing receipts is diverse and cost-accounted.

    Each receipt must satisfy the routing schema, re-derive its own identity, and
    select a provider inside its own eligible set.  The union of eligible
    providers across the set must span at least ``minimum_providers``, because a
    set with no alternative provider is a single point of authority and failure
    rather than a diverse set.  The aggregate estimated cost is carried as
    descriptive bookkeeping only — recorded, never gated on a threshold — so cost
    never becomes an authority that promotes or rejects a candidate.
    """
    receipts = _require_sequence(routing_receipts, "routing_receipts")
    if not receipts:
        _fail(
            "INPUT_INVALID",
            "at least one routing receipt is required to attest diversity",
            {"routing_receipts": receipts},
        )
    minimum = int(minimum_providers)

    receipt_ids: list[str] = []
    eligible_union: set[str] = set()
    selected_providers: set[str] = set()
    total_cost = 0.0
    max_latency = 0
    for position, entry in enumerate(receipts):
        document = _require_mapping(entry, f"routing_receipts[{position}]")
        try:
            validate_artifact(ROUTING_KIND, dict(document))
        except ContractViolation as error:
            _fail(
                "ROUTING_CONTRACT_VIOLATED",
                "a routing receipt does not satisfy its canonical schema",
                {"index": position, "schema_errors": list(error.errors)},
            )
        _require_receipt_identity(
            document,
            "XMR-",
            "receipt_id",
            "receipt_hash",
            "ROUTING_RECEIPT_TAMPERED",
        )
        eligible = [str(value) for value in document["eligible_model_ids"]]
        selected = str(document["selected_model_id"])
        if selected not in set(eligible):
            _fail(
                "ROUTING_SELECTION_NOT_ELIGIBLE",
                "a routing receipt selects a provider outside its eligible set",
                {
                    "eligible_model_ids": sorted(set(eligible)),
                    "index": position,
                    "selected_model_id": selected,
                },
            )
        receipt_ids.append(str(document["receipt_id"]))
        eligible_union.update(eligible)
        selected_providers.add(selected)
        total_cost += float(document["estimated_cost"])
        max_latency = max(max_latency, int(document["estimated_latency_ms"]))

    if len(eligible_union) < minimum:
        _fail(
            "PROVIDER_DIVERSITY_ABSENT",
            "the routed set offers no alternative provider",
            {
                "eligible_provider_union": sorted(eligible_union),
                "minimum_providers": minimum,
            },
        )

    attestation: dict[str, Any] = {
        "eligible_provider_union": sorted(eligible_union),
        "max_estimated_latency_ms": max_latency,
        "minimum_providers": minimum,
        "provider_count": len(eligible_union),
        "routing_receipt_ids": sorted(receipt_ids),
        "selected_provider_set": sorted(selected_providers),
        "total_estimated_cost": total_cost,
    }
    return _identified(
        attestation, DIVERSITY_ATTESTATION_PREFIX, "attestation_id", "attestation_hash"
    )


def attribute_provider_reward(
    *,
    routing_receipt: Mapping[str, Any],
    arm_id: str,
    proxy_score: float,
    validated_utility: float | None,
    safety_passed: bool,
    replication_confirmed: bool,
    statistical_correction: Mapping[str, Any],
    drives_promotion: bool = False,
) -> dict[str, Any]:
    """Attribute a reward to a routed provider through the sealed safe bandit.

    The whole safe-reward decision is delegated to X05's ``admit_bandit_reward``,
    which draws the reward from a validated basis rather than the immediate proxy,
    requires a statistical correction, refuses a reward routed at a promotion, and
    zeroes it on a safety failure.  A refusal from that sealed surface is surfaced
    with its own finding in context rather than worked around.
    """
    try:
        return admit_bandit_reward(
            routing_receipt=dict(_require_mapping(routing_receipt, "routing_receipt")),
            arm_id=_require_text(arm_id, "arm_id"),
            proxy_score=proxy_score,
            validated_utility=validated_utility,
            safety_passed=safety_passed,
            replication_confirmed=replication_confirmed,
            statistical_correction=dict(
                _require_mapping(statistical_correction, "statistical_correction")
            ),
            drives_promotion=drives_promotion,
        )
    except MutationRoutingError as error:
        _fail(
            "REWARD_ATTRIBUTION_REFUSED",
            str(error),
            {"routing_finding_code": error.code, "routing_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises


def assert_composed_neutrality(
    *,
    reference_result: Mapping[str, Any],
    fallback_result: Mapping[str, Any],
    eligible_model_ids: Sequence[str],
    primary_model_id: str,
    fallback_model_id: str,
) -> dict[str, Any]:
    """Compose the sealed fallback-neutrality check over a provider failover.

    A fallback provider that alters a canonical field of a node result is refused
    by X05's ``assert_fallback_neutral`` — a provider executes a node but is never
    an authority on what its result means.  A refusal is surfaced with its own
    finding in context; provider-local differences ride through untouched.
    """
    try:
        return assert_fallback_neutral(
            reference_result=dict(
                _require_mapping(reference_result, "reference_result")
            ),
            fallback_result=dict(_require_mapping(fallback_result, "fallback_result")),
            eligible_model_ids=[
                _require_text(value, f"eligible_model_ids[{position}]")
                for position, value in enumerate(
                    _require_sequence(eligible_model_ids, "eligible_model_ids")
                )
            ],
            primary_model_id=_require_text(primary_model_id, "primary_model_id"),
            fallback_model_id=_require_text(fallback_model_id, "fallback_model_id"),
        )
    except MutationRoutingError as error:
        _fail(
            "NEUTRALITY_REFUSED",
            str(error),
            {"routing_finding_code": error.code, "routing_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises


def refuse_backend_provider_authority(
    *,
    imported: Mapping[str, Any],
    bindings: Mapping[str, str],
) -> dict[str, Any]:
    """Compose the sealed external-backend boundary so a backend stays advisory.

    An external backend used as a mutation provider may inform routing but never
    become Foundry authority: X05's ``route_external_backend_neutral`` refuses to
    bind any imported backend field onto a promotion, evaluator or ledger surface,
    and this gate surfaces that refusal rather than admitting the binding.
    """
    try:
        return route_external_backend_neutral(
            imported=dict(_require_mapping(imported, "imported")),
            bindings=dict(_require_mapping(bindings, "bindings")),
        )
    except MutationRoutingError as error:
        _fail(
            "BACKEND_PROVIDER_AUTHORITY_LEAK",
            str(error),
            {"routing_finding_code": error.code, "routing_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises


def integrate_provider_gate(
    *,
    run_id: str,
    diversity_attestation: Mapping[str, Any],
    reward_attribution: Mapping[str, Any],
    bandit_state: Mapping[str, Any],
    fallback_receipts: Sequence[Mapping[str, Any]] = (),
    backend_neutrality: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind the sealed provider sub-decisions into one re-derivable record.

    Each sub-decision is re-derived from its own content, so a tampered one cannot
    be laundered into the combined record.  The bandit state must run under a
    policy the bandit module bounds as safe, the reward must be attributed to a
    routing decision inside the attested diverse set and must not drive a
    promotion, any sealed fallback must have preserved semantics, and any external
    backend must remain non-authoritative.  The combined receipt carries the
    diverse set's descriptive cost bookkeeping — never a threshold authority — and
    records which boundaries it composed.
    """
    run = _require_text(run_id, "run_id")

    attestation = _require_receipt_identity(
        diversity_attestation,
        DIVERSITY_ATTESTATION_PREFIX,
        "attestation_id",
        "attestation_hash",
        "DIVERSITY_ATTESTATION_TAMPERED",
    )
    reward = _require_receipt_identity(
        reward_attribution,
        REWARD_ADMISSION_PREFIX,
        "receipt_id",
        "receipt_hash",
        "REWARD_ATTRIBUTION_TAMPERED",
    )
    if reward.get("drives_promotion") is not False:
        _fail(
            "REWARD_DRIVES_PROMOTION",
            "the reward admission is marked as driving a promotion decision",
            {"reward_attribution_id": reward.get("receipt_id")},
        )
    attested_ids = set(attestation["routing_receipt_ids"])
    if str(reward["routing_receipt_id"]) not in attested_ids:
        _fail(
            "REWARD_ROUTING_UNLISTED",
            "the reward is attributed to a routing decision outside the attested set",
            {
                "attested_routing_receipt_ids": sorted(attested_ids),
                "reward_routing_receipt_id": reward.get("routing_receipt_id"),
            },
        )

    state = _require_mapping(bandit_state, "bandit_state")
    try:
        validate_artifact(BANDIT_STATE_KIND, dict(state))
    except ContractViolation as error:
        _fail(
            "BANDIT_STATE_CONTRACT_VIOLATED",
            "the bandit state does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    if hash_excluding(dict(state), "state_hash") != str(state.get("state_hash")):
        _fail(
            "BANDIT_STATE_TAMPERED",
            "the bandit state does not re-derive its own hash",
            {"state_id": state.get("state_id")},
        )
    if not bandits.policy_bounds_safety(state):
        _fail(
            "BANDIT_POLICY_UNSAFE",
            "the bandit state does not run under a safety-bounded policy",
            {"state_id": state.get("state_id")},
        )

    fallback_ids: list[str] = []
    for position, entry in enumerate(
        _require_sequence(fallback_receipts, "fallback_receipts")
    ):
        fallback = _require_receipt_identity(
            _require_mapping(entry, f"fallback_receipts[{position}]"),
            FALLBACK_RECEIPT_PREFIX,
            "receipt_id",
            "receipt_hash",
            "FALLBACK_RECEIPT_TAMPERED",
        )
        if fallback.get("semantics_preserved") is not True:
            _fail(
                "FALLBACK_SEMANTICS_ALTERED",
                "a sealed fallback receipt records that semantics were not preserved",
                {"fallback_receipt_id": fallback.get("receipt_id")},
            )
        fallback_ids.append(str(fallback["receipt_id"]))

    concerns = [
        CONCERN_PROVIDER_DIVERSITY,
        CONCERN_REWARD_ATTRIBUTION,
        CONCERN_PROVIDER_SAFETY,
    ]
    components: dict[str, Any] = {
        "bandit_state_id": str(state["state_id"]),
        "diversity_attestation_id": str(attestation["attestation_id"]),
        "provider_count": int(attestation["provider_count"]),
        "reward_attribution_id": str(reward["receipt_id"]),
        "total_estimated_cost": float(attestation["total_estimated_cost"]),
    }
    if fallback_ids:
        components["fallback_receipt_ids"] = sorted(fallback_ids)
        concerns.append(CONCERN_FALLBACK_NEUTRALITY)
    if backend_neutrality is not None:
        backend = _require_mapping(backend_neutrality, "backend_neutrality")
        if backend.get("authoritative") is not False:
            _fail(
                "BACKEND_PROVIDER_AUTHORITY_LEAK",
                "the external backend is marked authoritative",
                {"authoritative": backend.get("authoritative")},
            )
        concerns.append(CONCERN_BACKEND_NON_AUTHORITY)

    receipt: dict[str, Any] = {
        "components": dict(sorted(components.items())),
        "concerns_gated": sorted(concerns),
        "run_id": run,
    }
    return _identified(
        receipt, INTEGRATION_RECEIPT_PREFIX, "receipt_id", "receipt_hash"
    )
