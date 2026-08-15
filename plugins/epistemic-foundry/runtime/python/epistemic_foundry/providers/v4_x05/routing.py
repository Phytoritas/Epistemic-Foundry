"""Cross-provider mutation routing and the safe delayed-reward bandit gate (X05).

X03 sealed model routing and fallback policy, X04 sealed cross-provider parity
and diversity, N05 sealed the bounded proposal/evaluation/persistence lanes and
their exact fan-in accounting, and T05 sealed the external-backend adapter's
pinning, qualification and non-authority boundary.  ``providers/neutrality.py``
owns what it means for one provider to preserve another's canonical result, and
``evaluation/bandits.py`` owns the operator/model bandit vocabulary and the rule
that a bandit learns from validated outcomes rather than the proxy it can game.
Each surface is correct alone; none of them answers the one question this
package exists for: when a mutation is routed across replaceable providers and a
bandit adapts that routing, does the composition keep the providers *neutral*
and the bandit *safe*, and does every decision resolve to an immutable,
re-derivable receipt?

This is an *integration* surface.  It composes the sealed modules and refuses
the compositions that would breach a boundary none of them can see alone,
restating none of their vocabularies (EF4-I22): every canonical token it reasons
about is read positionally out of the schema that declares it, and the safe
bandit-policy token is cross-checked against the set ``evaluation/bandits.py``
already treats as safe, so a reshaped schema fails closed rather than selecting
the wrong value.

*Provider neutrality.*  ``route_mutation`` may select only a provider the parity
gate already made eligible, so no provider is smuggled in outside the approved
set.  ``assert_fallback_neutral`` drives a fallback provider's result through the
sealed neutrality check: a fallback that alters a canonical field — a status, a
verdict, a hash — is refused, because a provider executes a node but is never an
authority on what its result means (EF4-I34).  ``route_external_backend_neutral``
composes the T05 boundary so an external search backend used as a provider never
becomes Foundry authority (EF4-I63).

*Safe delayed reward.*  A learning routing policy must draw its reward from a
validated basis, never the immediate proxy a candidate can game (EF4-I54); a
non-learning policy may carry no reward basis at all.  ``admit_bandit_reward``
composes ``evaluation/bandits.py`` to derive a reward only from validated utility
and safety, refuses a reward with no statistical correction behind it (EF4-I53),
and refuses outright any reward routed at a promotion decision — a combined
signal may order search but never promote (EF4-I45).  ``seal_safe_bandit_state``
seals an operator-bandit state only under a policy the bandit module itself
bounds as safe.

*Exact fan-in.*  ``reconcile_routed_fanin`` composes the N05 schedule gate so a
set of routed mutations cannot report a partial provider fan-out as a complete
one (EF4-I60).

Every decision resolves to an immutable, content-addressed receipt: two runs
over equal inputs produce byte-equal receipts.  Nothing here scores, promotes,
mutates its inputs, or reads a clock.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...contracts import ContractViolation, default_registry, validate_artifact
from ...domain.hashing import hash_excluding, sha256_of_payload
from ...evaluation import bandits
from ...scheduler.v4_n05 import (
    LaneEvent,
    ScheduleError,
    require_valid_schedule,
    seal_schedule_verdict,
    verify_schedule,
)
from ..neutrality import (
    ProviderSemanticsViolation,
    assert_semantics_preserved,
    provider_local_differences,
)

#: Every way this surface refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this surface requires, and continuing would "
        "record a decision derived from something it never validated"
    ),
    "VOCABULARY_DRIFT": (
        "a canonical schema no longer declares its routing or bandit vocabulary "
        "in the shape this surface reads positionally, so selecting a token by "
        "index would pick the wrong value; the surface fails closed rather than "
        "guess"
    ),
    "ROUTING_CONTRACT_VIOLATED": (
        "the model-routing receipt does not satisfy its canonical schema, so its "
        "policy and reward basis would be read from a shape no contract admits"
    ),
    "ROUTING_SELECTION_NOT_ELIGIBLE": (
        "the selected provider is not in the parity-approved eligible set, so a "
        "provider would be routed to outside the set the parity gate cleared, "
        "which is how one provider acquires routing authority the others lack"
    ),
    "ROUTING_POLICY_UNSAFE": (
        "the routing policy explores without a declared safety bound, so a "
        "mutation bandit could concentrate pulls on a provider without any "
        "constraint on the exploration that concentration came from"
    ),
    "ROUTING_REWARD_BASIS_INCOHERENT": (
        "a learning policy carries no validated reward basis, or a non-learning "
        "policy claims one, so the receipt would advertise a reward source that "
        "does not match how the policy actually adapts"
    ),
    "ROUTING_EXPLORATION_INCOHERENT": (
        "a non-learning policy declares a non-zero exploration probability, so "
        "the receipt claims exploration a fixed or manual policy never performs"
    ),
    "FALLBACK_TARGET_NOT_ELIGIBLE": (
        "the fallback provider is not in the eligible set, so a provider parity "
        "never cleared would execute the node when the primary is unavailable"
    ),
    "FALLBACK_SOURCE_EQUALS_TARGET": (
        "the primary and the fallback provider are the same, so nothing was "
        "actually failed over and the neutrality check has nothing to compare"
    ),
    "PROVIDER_SEMANTICS_ALTERED": (
        "the fallback provider changed a canonical field of the result, so the "
        "provider altered what the node means rather than only how it ran — a "
        "provider executes a node but is never an authority on its meaning"
    ),
    "BANDIT_REWARD_BASIS_ABSENT": (
        "the routing receipt carries no reward basis, so there is nothing to "
        "reward the arm on and admitting a reward would invent a signal"
    ),
    "BANDIT_REWARD_PROXY_BASIS": (
        "the reward would train the bandit on the immediate proxy basis, which "
        "is the signal a candidate can game; reward must be drawn from validated "
        "holdout or replication utility (EF4-I54)"
    ),
    "BANDIT_STATISTICAL_CORRECTION_ABSENT": (
        "no applied statistical correction backs the reward, so an adaptive "
        "best-of-many search would update the bandit on an uncorrected estimate "
        "(EF4-I53)"
    ),
    "BANDIT_REWARD_DRIVES_PROMOTION": (
        "the reward is routed at a promotion decision, and a bandit reward may "
        "order search but never promote a candidate (EF4-I45)"
    ),
    "BANDIT_REWARD_UNVALIDATED": (
        "the bandit module refused the reward because it carried no validated "
        "utility, so training on it would converge on the proxy rather than on "
        "being right"
    ),
    "BANDIT_POLICY_UNSAFE": (
        "the sealed bandit state does not run under a policy the bandit module "
        "bounds as safe, so its exploration is not constrained"
    ),
    "BANDIT_STATE_REFUSED": (
        "the bandit module refused the sealed state, so an arm tracked no "
        "validated reward or carried a safety violation beside a positive one"
    ),
    "ROUTING_FANIN_UNACCOUNTED": (
        "the schedule of routed mutations does not account for every candidate "
        "across the lanes, so a partial provider fan-out would be reported as a "
        "complete one (EF4-I60)"
    ),
    "BACKEND_PROVIDER_AUTHORITY_LEAK": (
        "an external backend used as a provider would bind one of its own fields "
        "onto a Foundry authority surface, so a search engine's bookkeeping "
        "would become authority it may never hold (EF4-I63)"
    ),
}

#: Canonical schema names this surface reads.  Each is a registered canonical
#: contract, validated before use rather than restated as fields here.
ROUTING_KIND = "model-routing-receipt"
BANDIT_STATE_KIND = "operator-bandit-state"

#: Identifier prefixes.  Every identifier this surface mints is derived from the
#: record's own content, so nothing here needs entropy and two runs over equal
#: inputs produce byte-equal records.
ROUTING_RECEIPT_PREFIX = "XMR-"
FALLBACK_RECEIPT_PREFIX = "XFN-"
REWARD_RECEIPT_PREFIX = "XBR-"

#: The declared shapes of the two vocabularies this surface reads positionally.
_ROUTING_POLICY_TOKENS = 5
_ROUTING_REWARD_TOKENS = 5
_BANDIT_POLICY_TOKENS = 4


class MutationRoutingError(ValueError):
    """The surface refuses a routing, a fallback, a reward or a state."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise MutationRoutingError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise MutationRoutingError(code, message, context)


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


def _require_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("INPUT_INVALID", f"{label} must be a number", {"label": label})
    return float(value)  # type: ignore[arg-type]


def _enum(kind: str, field: str, expected: int) -> tuple[str, ...]:
    """The declared enum tokens for a schema field, refused on shape drift.

    The tokens are read out of the canonical schema rather than restated here,
    and the count this surface reasons about is checked so a reshaped vocabulary
    fails closed instead of silently letting an index select the wrong token.
    """
    document = default_registry().document(kind)
    enum = document.get("properties", {}).get(field, {}).get("enum")
    if not isinstance(enum, list) or len(enum) != expected:
        _fail(
            "VOCABULARY_DRIFT",
            f"{kind}.{field} is not the expected {expected}-token vocabulary",
            {"enum": enum, "field": field, "schema": kind},
        )
    return tuple(str(value) for value in enum)


@lru_cache(maxsize=1)
def _fields() -> dict[str, str]:
    """The schema field *names* this surface reads, discovered, never restated.

    ``policy`` is itself a canonical enum value elsewhere (a node-contract
    executor type), so writing it as a string literal here would re-declare a
    wire token this package does not own (EF4-I22).  The field name is instead
    discovered: the bandit schema's sole enum property is its policy field, and
    the routing schema's policy field is the one whose ladder shares tokens with
    it — the reward-basis ladder shares none — so the two 5-token routing
    properties are told apart by that overlap rather than by name.
    """
    registry = default_registry()
    routing_props = registry.document(ROUTING_KIND).get("properties", {})
    bandit_props = registry.document(BANDIT_STATE_KIND).get("properties", {})

    bandit_enum_fields = [
        name
        for name, spec in bandit_props.items()
        if isinstance(spec, Mapping)
        and isinstance(spec.get("enum"), list)
        and len(spec["enum"]) == _BANDIT_POLICY_TOKENS
    ]
    if len(bandit_enum_fields) != 1:
        _fail(
            "VOCABULARY_DRIFT",
            "the bandit schema no longer declares exactly one policy vocabulary",
            {"candidates": sorted(bandit_enum_fields)},
        )
    bandit_policy_field = bandit_enum_fields[0]
    bandit_tokens = set(bandit_props[bandit_policy_field]["enum"])

    five_token = [
        name
        for name, spec in routing_props.items()
        if isinstance(spec, Mapping)
        and isinstance(spec.get("enum"), list)
        and len(spec["enum"]) == _ROUTING_POLICY_TOKENS
    ]
    policy_fields = [
        name for name in five_token if set(routing_props[name]["enum"]) & bandit_tokens
    ]
    reward_fields = [
        name
        for name in five_token
        if not (set(routing_props[name]["enum"]) & bandit_tokens)
    ]
    if len(policy_fields) != 1 or len(reward_fields) != 1:
        _fail(
            "VOCABULARY_DRIFT",
            "the routing schema's policy and reward-basis fields are no longer "
            "distinguishable by their overlap with the bandit policy ladder",
            {
                "policy_fields": sorted(policy_fields),
                "reward_fields": sorted(reward_fields),
            },
        )
    return {
        "routing_policy": policy_fields[0],
        "routing_reward": reward_fields[0],
        "bandit_policy": bandit_policy_field,
    }


@lru_cache(maxsize=1)
def _vocab() -> dict[str, Any]:
    """Every canonical token this surface selects, read positionally from schema.

    Holding these as string literals would be a second copy that drifts from the
    contract (EF4-I22).  The indices are the schemas' own declared order — the
    routing policy ladder ``[fixed, ucb, thompson, safe_bandit, manual]``, the
    reward-basis ladder ``[immediate_proxy, validated_improvement,
    delayed_holdout, replication, none]`` and the bandit policy ladder
    ``[ucb, thompson, safe_ucb, fixed]`` — each asserted against its schema by
    the schema-and-type suite.  The safe bandit-policy token is cross-checked
    against the set ``evaluation/bandits.py`` already treats as safe, so the two
    modules cannot disagree about which policy is bounded.
    """
    fields = _fields()
    policy = _enum(ROUTING_KIND, fields["routing_policy"], _ROUTING_POLICY_TOKENS)
    reward = _enum(ROUTING_KIND, fields["routing_reward"], _ROUTING_REWARD_TOKENS)
    bandit_policy = _enum(
        BANDIT_STATE_KIND, fields["bandit_policy"], _BANDIT_POLICY_TOKENS
    )

    safe_bandit_token = bandit_policy[2]
    if bandits.SAFE_POLICIES != frozenset({safe_bandit_token}):
        _fail(
            "VOCABULARY_DRIFT",
            "the bandit safe-policy token no longer matches the set the bandit "
            "module bounds as safe, so the two modules disagree on what is safe",
            {
                "bandits_safe": sorted(bandits.SAFE_POLICIES),
                "selected": safe_bandit_token,
            },
        )

    # A routing policy that adapts without a declared safety bound: the two
    # middle rungs of the routing ladder.  The first, the safe learning rung and
    # the last are the policies this surface admits.
    learning_unsafe = frozenset({policy[1], policy[2]})
    learning_safe = policy[3]
    non_learning = frozenset({policy[0], policy[4]})
    validated_bases = frozenset(reward[1:4])
    return {
        "routing_learning_unsafe": learning_unsafe,
        "routing_learning_safe": learning_safe,
        "routing_non_learning": non_learning,
        "reward_immediate_proxy": reward[0],
        "reward_none": reward[-1],
        "reward_validated": validated_bases,
        "bandit_policy_safe": safe_bandit_token,
    }


def _identified(record: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Attach a content-derived identifier and the record's own hash."""
    record["receipt_id"] = prefix + sha256_of_payload(record)[len("sha256:") :]
    record["receipt_hash"] = hash_excluding(record, "receipt_hash")
    return record


def route_mutation(
    *,
    task_class: str,
    eligible_model_ids: Sequence[str],
    selected_model_id: str,
    policy: str,
    reward_basis: str,
    estimated_cost: float,
    estimated_latency_ms: int,
    exploration_probability: float,
    safety_constraints: Sequence[str] = (),
) -> dict[str, Any]:
    """Route one mutation across eligible providers into a neutral receipt.

    Four boundaries are composed and none substitutes for another: the selected
    provider must be one the parity gate already made eligible, an adapting
    policy must be one this surface bounds as safe, its reward basis must match
    how it adapts (a learning policy draws from a validated basis, a non-learning
    one from none), and a non-learning policy may not claim exploration it never
    performs.  The receipt is a pure function of the inputs: no clock, no random
    draw, and the identifier and hash re-derive from the published content.
    """
    vocab = _vocab()
    task = _require_text(task_class, "task_class")
    eligible = [
        _require_text(value, f"eligible_model_ids[{position}]")
        for position, value in enumerate(
            _require_sequence(eligible_model_ids, "eligible_model_ids")
        )
    ]
    if not eligible:
        _fail(
            "INPUT_INVALID",
            "at least one eligible provider is required to route a mutation",
            {"eligible_model_ids": eligible},
        )
    selected = _require_text(selected_model_id, "selected_model_id")
    fields = _fields()
    pol_field = fields["routing_policy"]
    rew_field = fields["routing_reward"]
    chosen_policy = _require_text(policy, pol_field)
    basis = _require_text(reward_basis, rew_field)

    if selected not in set(eligible):
        _fail(
            "ROUTING_SELECTION_NOT_ELIGIBLE",
            "the selected provider is not in the parity-approved eligible set",
            {
                "eligible_model_ids": sorted(set(eligible)),
                "selected_model_id": selected,
            },
        )

    if chosen_policy in vocab["routing_learning_unsafe"]:
        _fail(
            "ROUTING_POLICY_UNSAFE",
            "the routing policy explores without a declared safety bound",
            {pol_field: chosen_policy},
        )

    is_learning = chosen_policy == vocab["routing_learning_safe"]
    if is_learning:
        if basis not in vocab["reward_validated"]:
            _fail(
                "ROUTING_REWARD_BASIS_INCOHERENT",
                "a learning routing policy must draw reward from a validated basis",
                {pol_field: chosen_policy, rew_field: basis},
            )
    elif chosen_policy in vocab["routing_non_learning"]:
        if basis != vocab["reward_none"]:
            _fail(
                "ROUTING_REWARD_BASIS_INCOHERENT",
                "a non-learning routing policy may carry no reward basis",
                {pol_field: chosen_policy, rew_field: basis},
            )

    exploration = _require_number(exploration_probability, "exploration_probability")
    if chosen_policy in vocab["routing_non_learning"] and exploration != 0:
        _fail(
            "ROUTING_EXPLORATION_INCOHERENT",
            "a non-learning routing policy declares exploration it never performs",
            {"exploration_probability": exploration, pol_field: chosen_policy},
        )

    constraints = [
        _require_text(value, f"safety_constraints[{position}]")
        for position, value in enumerate(
            _require_sequence(safety_constraints, "safety_constraints")
        )
    ]

    receipt: dict[str, Any] = {
        "task_class": task,
        "eligible_model_ids": list(eligible),
        "selected_model_id": selected,
        pol_field: chosen_policy,
        rew_field: basis,
        "estimated_cost": _require_number(estimated_cost, "estimated_cost"),
        "estimated_latency_ms": int(estimated_latency_ms),
        "exploration_probability": exploration,
        "safety_constraints": constraints,
    }
    _identified(receipt, ROUTING_RECEIPT_PREFIX)
    try:
        validate_artifact(ROUTING_KIND, dict(receipt))
    except ContractViolation as error:
        _fail(
            "ROUTING_CONTRACT_VIOLATED",
            "the model-routing receipt does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    return receipt


def assert_fallback_neutral(
    *,
    reference_result: Mapping[str, Any],
    fallback_result: Mapping[str, Any],
    eligible_model_ids: Sequence[str],
    primary_model_id: str,
    fallback_model_id: str,
) -> dict[str, Any]:
    """Fail a provider over only when the fallback preserves canonical meaning.

    The fallback provider must be eligible and distinct from the primary, and its
    result is driven through the sealed neutrality check: a change to any
    canonical field is refused, because that would make the provider an authority
    on the node's meaning rather than only its execution.  Provider-local
    differences — latency, tokens, model identity — are reported, never refused.
    """
    reference = _require_mapping(reference_result, "reference_result")
    fallback = _require_mapping(fallback_result, "fallback_result")
    eligible = {
        _require_text(value, f"eligible_model_ids[{position}]")
        for position, value in enumerate(
            _require_sequence(eligible_model_ids, "eligible_model_ids")
        )
    }
    primary = _require_text(primary_model_id, "primary_model_id")
    target = _require_text(fallback_model_id, "fallback_model_id")

    if primary == target:
        _fail(
            "FALLBACK_SOURCE_EQUALS_TARGET",
            "the primary and the fallback provider are the same",
            {"fallback_model_id": target, "primary_model_id": primary},
        )
    unlisted = sorted({primary, target} - eligible)
    if unlisted:
        _fail(
            "FALLBACK_TARGET_NOT_ELIGIBLE",
            "a routed provider is not in the eligible set",
            {"eligible_model_ids": sorted(eligible), "unlisted": unlisted},
        )

    try:
        assert_semantics_preserved(reference, fallback)
    except ProviderSemanticsViolation as error:
        _fail(
            "PROVIDER_SEMANTICS_ALTERED",
            str(error),
            {"fallback_model_id": target, "primary_model_id": primary},
        )

    receipt: dict[str, Any] = {
        "eligible_model_ids": sorted(eligible),
        "fallback_model_id": target,
        "primary_model_id": primary,
        "provider_local_differences": provider_local_differences(reference, fallback),
        "reference_result_hash": sha256_of_payload(reference),
        "fallback_result_hash": sha256_of_payload(fallback),
        "semantics_preserved": True,
    }
    return _identified(receipt, FALLBACK_RECEIPT_PREFIX)


def admit_bandit_reward(
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
    """Admit a bandit reward only when it is validated, corrected and non-promoting.

    The routing receipt's reward basis must be a validated one, never the
    immediate proxy a candidate can game.  An applied statistical correction must
    back the reward, because an adaptive best-of-many search updated on an
    uncorrected estimate inflates it.  A reward routed at a promotion decision is
    refused outright.  The reward itself is derived by the sealed bandit module,
    which zeroes it on a safety failure and refuses it with no validated utility.
    """
    vocab = _vocab()
    receipt = _require_mapping(routing_receipt, "routing_receipt")
    try:
        validate_artifact(ROUTING_KIND, dict(receipt))
    except ContractViolation as error:
        _fail(
            "ROUTING_CONTRACT_VIOLATED",
            "the model-routing receipt does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    basis = str(receipt["reward_basis"])
    arm = _require_text(arm_id, "arm_id")

    if drives_promotion:
        _fail(
            "BANDIT_REWARD_DRIVES_PROMOTION",
            "a bandit reward may order search but never promote a candidate",
            {"arm_id": arm, "routing_receipt_id": str(receipt["receipt_id"])},
        )
    if basis == vocab["reward_none"]:
        _fail(
            "BANDIT_REWARD_BASIS_ABSENT",
            "the routing receipt carries no reward basis to reward the arm on",
            {"arm_id": arm, "reward_basis": basis},
        )
    if basis == vocab["reward_immediate_proxy"]:
        _fail(
            "BANDIT_REWARD_PROXY_BASIS",
            "the reward would train the bandit on the immediate proxy basis",
            {"arm_id": arm, "reward_basis": basis},
        )
    if basis not in vocab["reward_validated"]:  # pragma: no cover - schema-bounded
        _fail(
            "ROUTING_REWARD_BASIS_INCOHERENT",
            "the routing receipt carries an unrecognized reward basis",
            {"arm_id": arm, "reward_basis": basis},
        )

    correction = _require_mapping(statistical_correction, "statistical_correction")
    correction_id = _require_text(
        correction.get("adjustment_id"), "statistical_correction.adjustment_id"
    )
    if correction.get("correction_applied") is not True:
        _fail(
            "BANDIT_STATISTICAL_CORRECTION_ABSENT",
            "no applied statistical correction backs the reward",
            {"adjustment_id": correction_id, "arm_id": arm},
        )

    try:
        reward = bandits.validated_reward(
            proxy_score=_require_number(proxy_score, "proxy_score"),
            validated_utility=(
                None
                if validated_utility is None
                else _require_number(validated_utility, "validated_utility")
            ),
            safety_passed=bool(safety_passed),
            replication_confirmed=bool(replication_confirmed),
        )
    except bandits.BanditRewardRefused as error:
        _fail(
            "BANDIT_REWARD_UNVALIDATED",
            str(error),
            {"arm_id": arm},
        )

    admission: dict[str, Any] = {
        "arm_id": arm,
        "drives_promotion": False,
        "replication_confirmed": bool(replication_confirmed),
        "reward": float(reward),
        "reward_basis": basis,
        "routing_receipt_id": str(receipt["receipt_id"]),
        "safety_passed": bool(safety_passed),
        "statistical_correction_id": correction_id,
    }
    return _identified(admission, REWARD_RECEIPT_PREFIX)


def seal_safe_bandit_state(
    *,
    evolution_run_id: str,
    arms: Sequence[Mapping[str, Any]],
    exploration_budget: float,
    last_updated: str,
    policy: str | None = None,
    state_id: str | None = None,
) -> dict[str, Any]:
    """Seal an operator-bandit state only under a policy the module bounds as safe.

    The policy is fixed to the safe bandit token unless the caller supplies one,
    and a supplied policy the bandit module does not bound as safe is refused
    before the state is built.  The sealing itself is delegated to
    ``evaluation/bandits.py``, which refuses an arm tracking no validated reward
    or carrying a safety violation beside a positive one.
    """
    vocab = _vocab()
    pol_field = _fields()["bandit_policy"]
    chosen = (
        vocab["bandit_policy_safe"]
        if policy is None
        else _require_text(policy, pol_field)
    )
    if chosen not in bandits.SAFE_POLICIES:
        _fail(
            "BANDIT_POLICY_UNSAFE",
            "the requested policy is not one the bandit module bounds as safe",
            {pol_field: chosen, "safe_policies": sorted(bandits.SAFE_POLICIES)},
        )
    try:
        state = bandits.build_bandit_state(
            evolution_run_id=_require_text(evolution_run_id, "evolution_run_id"),
            policy=chosen,
            arms=[
                _require_mapping(arm, "arm") for arm in _require_sequence(arms, "arms")
            ],
            exploration_budget=_require_number(
                exploration_budget, "exploration_budget"
            ),
            state_id=state_id,
            last_updated=_require_text(last_updated, "last_updated"),
        )
    except bandits.BanditRewardRefused as error:
        _fail(
            "BANDIT_STATE_REFUSED", str(error), {"evolution_run_id": evolution_run_id}
        )
    if not bandits.policy_bounds_safety(state):  # pragma: no cover - guarded above
        _fail(
            "BANDIT_POLICY_UNSAFE",
            "the sealed state does not run under a safety-bounded policy",
            {pol_field: chosen},
        )
    return state


def reconcile_routed_fanin(
    repository_root: str | Path,
    *,
    proposed: Sequence[str],
    events: Sequence[LaneEvent],
    lane_limits: Mapping[str, Mapping[str, Any]],
    schedule_id: str,
    failure_ledger: Sequence[str] = (),
    cancelled: Sequence[str] = (),
    effect_receipts: Sequence[Mapping[str, Any]] = (),
    mutation_receipts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Compose the N05 schedule gate over a set of routed mutations.

    Routed mutations are scheduled work, so the exact fan-in accounting the
    scheduler already owns is reused rather than restated: a partial provider
    fan-out that reported itself complete is refused there and surfaced here with
    the scheduler's own finding in context.  On success the sealed schedule
    verdict is returned, so the reconciliation resolves to a re-derivable record.
    """
    report = verify_schedule(
        repository_root,
        proposed=proposed,
        events=events,
        lane_limits=lane_limits,
        failure_ledger=failure_ledger,
        cancelled=cancelled,
        effect_receipts=effect_receipts,
        mutation_receipts=mutation_receipts,
    )
    try:
        require_valid_schedule(report)
    except ScheduleError as error:
        _fail(
            "ROUTING_FANIN_UNACCOUNTED",
            str(error),
            {"scheduler_code": error.code, "scheduler_context": error.context},
        )
    return seal_schedule_verdict(
        report, schedule_id=_require_text(schedule_id, "schedule_id")
    )


def route_external_backend_neutral(
    *,
    imported: Mapping[str, Any],
    bindings: Mapping[str, str],
) -> dict[str, Any]:
    """Compose the T05 boundary so a backend provider never becomes authority.

    An external search backend used as a mutation provider stays advisory: the
    T05 adapter's own boundary refuses to bind any imported backend field onto a
    Foundry authority surface, and this surface composes that refusal so a
    routing path cannot smuggle a backend's bookkeeping into promotion, evaluator
    or ledger authority (EF4-I63).
    """
    from ...adapters.v4_t05 import AdapterGateError, require_no_imported_authority

    try:
        return require_no_imported_authority(imported=imported, bindings=bindings)
    except AdapterGateError as error:
        _fail(
            "BACKEND_PROVIDER_AUTHORITY_LEAK",
            str(error),
            {"adapter_code": error.code, "adapter_context": error.context},
        )
