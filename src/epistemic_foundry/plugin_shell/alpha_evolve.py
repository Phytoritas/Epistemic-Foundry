"""Invocation-scoped EVOLVE invariant observations for the plugin shell.

This module composes existing runtime authorities; it does not define a new
canonical artifact or acceptance gate.  The five checks trace directly to the
existing implementations of EF4-I60 (candidate reconciliation), EF4-I43/I44
(sealed evaluator and holdout), EF4-I47 (novelty outage typing), EF4-I55
(prompt quarantine), and EF4-I64 (candidate execution policy).

No scientific equation, empirical threshold, score, or default biological or
physical value is introduced here.  Scientific and policy values come from the
caller and are handed to existing functions through their current Python
signatures; optional technical IDs and timestamps retain each builder's existing
default behavior.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from inspect import signature
from typing import Any

from ..contracts import ContractViolation
from ..evaluation import NoveltyAssessmentRefused, assess_novelty
from ..evolution_chamber.reconciliation import (
    ReconciliationFailed,
    reconcile_candidates,
    require_reconciled,
)
from ..evolution_chamber.run_spec import build_evolution_run_spec
from ..governance.quarantine import (
    QuarantineViolation,
    build_prompt_mutation_proposal,
    require_not_retroactive,
)
from ..security import execution_blockers
from ..verifier_firewall.firewall import (
    EvaluatorDrift,
    FirewallRefusal,
    VerifierFirewall,
)

CHECK_NAMES: tuple[str, ...] = (
    "candidate_reconciliation",
    "evaluator_immutability",
    "novelty_outage",
    "prompt_current_run_authority",
    "sandbox_security",
)


class AlphaInvocationError(ValueError):
    """The ephemeral alpha-check invocation cannot bind to the runtime APIs."""


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AlphaInvocationError(f"{label} must be a JSON object/mapping")
    return dict(value)


def _section(invocation: Mapping[str, Any], name: str) -> dict[str, Any] | None:
    value = invocation.get(name)
    if value is None:
        return None
    return _mapping(value, name)


def _reject_unknown_keys(
    value: Mapping[str, Any], allowed: Sequence[str], label: str
) -> None:
    unknown = sorted(str(key) for key in value if key not in set(allowed))
    if unknown:
        raise AlphaInvocationError(f"{label} has unsupported keys: {unknown}")


def _require_keys(
    value: Mapping[str, Any], required: Sequence[str], label: str
) -> None:
    missing = [key for key in required if key not in value]
    if missing:
        raise AlphaInvocationError(f"{label} is missing required keys: {missing}")


def _string_sequence(value: object, label: str) -> Sequence[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AlphaInvocationError(f"{label} must be an array/sequence of strings")
    if any(not isinstance(item, str) for item in value):
        raise AlphaInvocationError(f"{label} must contain only strings")
    return value


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AlphaInvocationError(f"{label} must be a non-empty string")
    return value


def _bind_kwargs(
    function: Callable[..., Any], kwargs: Mapping[str, Any], label: str
) -> dict[str, Any]:
    """Bind to the existing callable signature without copying its contract."""
    try:
        bound = signature(function).bind(**dict(kwargs))
    except TypeError as error:
        raise AlphaInvocationError(
            f"{label} cannot bind to the runtime API: {error}"
        ) from error
    return dict(bound.arguments)


def _error_code(error: BaseException) -> str:
    existing = getattr(error, "code", None)
    return str(existing) if existing else type(error).__name__


def _result(
    state: str,
    *,
    domain_output: Any,
    message: str,
    limitations: Sequence[str],
    error: BaseException | None = None,
) -> dict[str, Any]:
    return {
        "state": state,
        "domain_output": domain_output,
        "error_code": None if error is None else _error_code(error),
        "message": str(error) if error is not None else message,
        "limitations": list(limitations),
    }


def _unassessed(message: str, limitations: Sequence[str]) -> dict[str, Any]:
    return _result(
        "UNASSESSED",
        domain_output=None,
        message=message,
        limitations=limitations,
    )


def _candidate_reconciliation(
    section: Mapping[str, Any] | None,
) -> dict[str, Any]:
    limitations = (
        "This reconciles only the explicitly supplied identity lists.",
        "It does not observe a scheduler, persistence system, or external side effect.",
    )
    if section is None:
        return _unassessed(
            "No candidate identity lists were supplied.", limitations
        )

    required = (
        "proposed",
        "generated",
        "evaluated",
        "persisted",
        "failed",
        "cancelled",
    )
    _reject_unknown_keys(section, required, "candidate_reconciliation")
    _require_keys(section, required, "candidate_reconciliation")
    for name in required:
        _string_sequence(section[name], f"candidate_reconciliation.{name}")

    kwargs = _bind_kwargs(
        reconcile_candidates, section, "candidate_reconciliation"
    )
    report = reconcile_candidates(**kwargs)
    try:
        require_reconciled(report)
    except ReconciliationFailed as error:
        return _result(
            "BLOCKED",
            domain_output=report,
            message="",
            limitations=limitations,
            error=error,
        )

    proposed = set(section["proposed"])
    unknown_terminal = {
        name: sorted(set(section[name]) - proposed)
        for name in ("failed", "cancelled")
        if set(section[name]) - proposed
    }
    if unknown_terminal:
        error = ReconciliationFailed(
            "terminal dispositions contain identities absent from proposed: "
            f"{unknown_terminal}; failed/cancelled cannot account for an "
            "identity that was never proposed"
        )
        return _result(
            "BLOCKED",
            domain_output={
                "reconciliation": report,
                "terminal_identities_absent_from_proposed": unknown_terminal,
            },
            message="",
            limitations=limitations,
            error=error,
        )
    return _result(
        "OBSERVED",
        domain_output=report,
        message=(
            "The existing reconciliation functions accounted for every supplied "
            "identity."
        ),
        limitations=limitations,
    )


def _validate_run_spec_argument_shapes(kwargs: Mapping[str, Any]) -> None:
    for name in ("population_types", "seed_genome_ids"):
        if name in kwargs:
            _string_sequence(
                kwargs[name],
                f"evaluator_immutability.run_spec_kwargs.{name}",
            )
    for name in ("max_generations", "max_candidates", "random_seed"):
        value = kwargs.get(name)
        if name in kwargs and (isinstance(value, bool) or not isinstance(value, int)):
            raise AlphaInvocationError(
                f"evaluator_immutability.run_spec_kwargs.{name} must be an integer"
            )
    if "external_backend_enabled" in kwargs and not isinstance(
        kwargs["external_backend_enabled"], bool
    ):
        raise AlphaInvocationError(
            "evaluator_immutability.run_spec_kwargs.external_backend_enabled "
            "must be a boolean"
        )
    if "resolved_refs" in kwargs:
        _mapping(
            kwargs["resolved_refs"],
            "evaluator_immutability.run_spec_kwargs.resolved_refs",
        )


def _evaluator_immutability(
    section: Mapping[str, Any] | None,
) -> dict[str, Any]:
    limitations = (
        "The run specification and firewall records are caller supplied.",
        "The firewall checks semantic record content; this does not measure "
        "filesystem or storage immutability.",
        "Hidden holdout content is neither requested nor inspected.",
        "No evaluator qualification or release status is inferred.",
    )
    if section is None:
        return _unassessed(
            "No run specification or evaluator records were supplied.", limitations
        )

    allowed = (
        "run_spec_kwargs",
        "firewall_kwargs",
        "observed_bundle",
    )
    _reject_unknown_keys(section, allowed, "evaluator_immutability")
    _require_keys(section, ("run_spec_kwargs",), "evaluator_immutability")
    run_spec_kwargs = _mapping(
        section["run_spec_kwargs"],
        "evaluator_immutability.run_spec_kwargs",
    )
    _validate_run_spec_argument_shapes(run_spec_kwargs)
    bound_run_spec = _bind_kwargs(
        build_evolution_run_spec,
        run_spec_kwargs,
        "evaluator_immutability.run_spec_kwargs",
    )
    try:
        run_spec = build_evolution_run_spec(**bound_run_spec)
    except (ContractViolation, ValueError) as error:
        return _result(
            "BLOCKED",
            domain_output=None,
            message="",
            limitations=limitations,
            error=error,
        )

    missing_records = [
        name
        for name in ("firewall_kwargs", "observed_bundle")
        if section.get(name) is None
    ]
    firewall_kwargs: dict[str, Any] | None = None
    if section.get("firewall_kwargs") is not None:
        firewall_kwargs = _mapping(
            section["firewall_kwargs"],
            "evaluator_immutability.firewall_kwargs",
        )
        firewall_keys = ("bundle", "holdout", "holdout_read_principal_ids")
        _reject_unknown_keys(
            firewall_kwargs,
            firewall_keys,
            "evaluator_immutability.firewall_kwargs",
        )
        missing_records.extend(
            f"firewall_kwargs.{name}"
            for name in firewall_keys
            if firewall_kwargs.get(name) is None
        )
    if missing_records:
        return _result(
            "UNASSESSED",
            domain_output={
                "evolution_run_spec": run_spec,
                "missing_firewall_inputs": missing_records,
            },
            message=(
                "The run specification was built, but evaluator immutability was not "
                "assessed because caller-supplied firewall records are incomplete."
            ),
            limitations=limitations,
        )

    if firewall_kwargs is None:  # pragma: no cover - guarded by missing_records
        raise RuntimeError("firewall kwargs disappeared after invocation validation")
    observed_bundle = _mapping(
        section["observed_bundle"],
        "evaluator_immutability.observed_bundle",
    )
    bound_firewall = _bind_kwargs(
        VerifierFirewall,
        firewall_kwargs,
        "evaluator_immutability.firewall_kwargs",
    )
    bundle = _mapping(
        bound_firewall["bundle"],
        "evaluator_immutability.firewall_kwargs.bundle",
    )
    holdout = _mapping(
        bound_firewall["holdout"],
        "evaluator_immutability.firewall_kwargs.holdout",
    )
    _string_sequence(
        bound_firewall["holdout_read_principal_ids"],
        "evaluator_immutability.firewall_kwargs.holdout_read_principal_ids",
    )
    bound_firewall["bundle"] = bundle
    bound_firewall["holdout"] = holdout

    try:
        firewall = VerifierFirewall(**bound_firewall)
        firewall.verify_self()
        firewall.assert_unchanged(observed_bundle)

        resolved_refs = run_spec["resolved_refs"]
        required_bindings = (
            (
                "run_spec.evaluator_bundle_id",
                run_spec["evaluator_bundle_id"],
                "bundle.evaluator_id",
                bundle["evaluator_id"],
            ),
            (
                "run_spec.holdout_manifest_id",
                run_spec["holdout_manifest_id"],
                "holdout.holdout_id",
                holdout["holdout_id"],
            ),
            (
                "run_spec.resolved_refs.evaluator_bundle.content_hash",
                resolved_refs["evaluator_bundle"]["content_hash"],
                "bundle.bundle_hash",
                bundle["bundle_hash"],
            ),
            (
                "run_spec.resolved_refs.holdout_manifest.content_hash",
                resolved_refs["holdout_manifest"]["content_hash"],
                "holdout.manifest_hash",
                holdout["manifest_hash"],
            ),
        )
        mismatches = [
            f"{left_name}={left!r} != {right_name}={right!r}"
            for left_name, left, right_name, right in required_bindings
            if left != right
        ]
        if mismatches:
            raise FirewallRefusal(
                "evolution run does not bind the firewall records exactly: "
                + "; ".join(mismatches)
            )
    except (ContractViolation, FirewallRefusal, EvaluatorDrift) as error:
        return _result(
            "BLOCKED",
            domain_output={"evolution_run_spec": run_spec},
            message="",
            limitations=limitations,
            error=error,
        )

    return _result(
        "OBSERVED",
        domain_output={
            "evolution_run_spec": run_spec,
            "verifier_firewall": {
                "bundle_id": firewall.bundle_id,
                "sealed_hash": firewall.sealed_hash,
            },
        },
        message=(
            "The existing run-spec builder and VerifierFirewall accepted the supplied "
            "records, observed bundle as unchanged, and exact run-spec identity/content "
            "bindings."
        ),
        limitations=limitations,
    )


def _novelty_outage(section: Mapping[str, Any] | None) -> dict[str, Any]:
    limitations = (
        "This calls assess_novelty only over caller-supplied search metadata.",
        "It does not execute a prior-art search or turn novelty into scientific "
        "support or truth.",
    )
    if section is None:
        return _unassessed("No novelty inputs were supplied.", limitations)

    for name in (
        "searched_sources",
        "unsearched_sources",
        "closest_prior_art_refs",
        "distinguishing_features",
        "novelty_dimensions",
        "limitations",
    ):
        if name in section:
            _string_sequence(section[name], f"novelty_outage.{name}")
    kwargs = _bind_kwargs(assess_novelty, section, "novelty_outage")
    try:
        assessment = assess_novelty(**kwargs)
    except (ContractViolation, NoveltyAssessmentRefused) as error:
        return _result(
            "BLOCKED",
            domain_output=None,
            message="",
            limitations=limitations,
            error=error,
        )

    state = (
        "UNASSESSED"
        if assessment["novelty_status"] == "NOT_ASSESSED"
        else "OBSERVED"
    )
    return _result(
        state,
        domain_output=assessment,
        message=(
            "The existing novelty assessment returned "
            f"{assessment['novelty_status']} with ceiling "
            f"{assessment['promotion_ceiling']}."
        ),
        limitations=limitations,
    )


def _prompt_current_run_authority(
    section: Mapping[str, Any] | None,
) -> dict[str, Any]:
    limitations = (
        "The proposal is constructed by the existing builder and remains "
        "QUARANTINED.",
        "No prompt is activated, qualified, or granted current-run authority.",
    )
    if section is None:
        return _unassessed(
            "No prompt mutation proposal inputs were supplied.", limitations
        )

    allowed = ("proposal_kwargs", "source_run_id", "target_run_id")
    _reject_unknown_keys(section, allowed, "prompt_current_run_authority")
    _require_keys(section, allowed, "prompt_current_run_authority")
    proposal_kwargs = _mapping(
        section["proposal_kwargs"],
        "prompt_current_run_authority.proposal_kwargs",
    )
    for name in ("changed_sections", "risk_analysis"):
        if name in proposal_kwargs:
            _string_sequence(
                proposal_kwargs[name],
                f"prompt_current_run_authority.proposal_kwargs.{name}",
            )
    source_run_id = _nonempty_text(
        section["source_run_id"],
        "prompt_current_run_authority.source_run_id",
    )
    target_run_id = _nonempty_text(
        section["target_run_id"],
        "prompt_current_run_authority.target_run_id",
    )
    bound_proposal = _bind_kwargs(
        build_prompt_mutation_proposal,
        proposal_kwargs,
        "prompt_current_run_authority.proposal_kwargs",
    )
    try:
        proposal = build_prompt_mutation_proposal(**bound_proposal)
    except (ContractViolation, QuarantineViolation) as error:
        return _result(
            "BLOCKED",
            domain_output=None,
            message="",
            limitations=limitations,
            error=error,
        )

    try:
        require_not_retroactive(
            {**proposal, "source_run_id": source_run_id},
            target_run_id=target_run_id,
        )
    except QuarantineViolation as error:
        return _result(
            "BLOCKED",
            domain_output=proposal,
            message="",
            limitations=limitations,
            error=error,
        )

    return _result(
        "OBSERVED",
        domain_output=proposal,
        message=(
            "The future-only check returned without activating or modifying the "
            "proposal."
        ),
        limitations=limitations,
    )


def _sandbox_security(section: Mapping[str, Any] | None) -> dict[str, Any]:
    limitations = (
        "This is a policy decision over caller-supplied profile, lease, "
        "capabilities, and operation context.",
        "A policy denial or absence of policy blockers is not an OS/container "
        "escape measurement.",
        "Only execution_blockers semantics are observed; profile and lease "
        "construction are not re-run here.",
        "No candidate code is executed.",
    )
    if section is None:
        return _unassessed(
            "No sandbox policy inputs were supplied.", limitations
        )

    allowed = ("profile", "lease", "requested_capabilities", "operation")
    _reject_unknown_keys(section, allowed, "sandbox_security")
    _require_keys(section, allowed, "sandbox_security")
    profile = _mapping(section["profile"], "sandbox_security.profile")
    lease = _mapping(section["lease"], "sandbox_security.lease")
    requested = _string_sequence(
        section["requested_capabilities"],
        "sandbox_security.requested_capabilities",
    )
    operation = _mapping(section["operation"], "sandbox_security.operation")
    overlap = sorted(
        set(operation).intersection({"profile", "lease", "requested_capabilities"})
    )
    if overlap:
        raise AlphaInvocationError(
            f"sandbox_security.operation cannot replace policy inputs: {overlap}"
        )
    for name in ("now", "evaluator_bundle_id", "holdout_manifest_id"):
        _nonempty_text(
            operation.get(name),
            f"sandbox_security.operation.{name}",
        )
    if "reachable_resource_ids" in operation:
        _string_sequence(
            operation["reachable_resource_ids"],
            "sandbox_security.operation.reachable_resource_ids",
        )
    if "declared_capabilities" in profile:
        _string_sequence(
            profile["declared_capabilities"],
            "sandbox_security.profile.declared_capabilities",
        )
    if "quotas" in profile:
        _mapping(profile["quotas"], "sandbox_security.profile.quotas")
    if "capabilities" in lease:
        _string_sequence(
            lease["capabilities"], "sandbox_security.lease.capabilities"
        )

    kwargs = {
        **operation,
        "profile": profile,
        "lease": lease,
        "requested_capabilities": requested,
    }
    bound = _bind_kwargs(execution_blockers, kwargs, "sandbox_security")
    blockers = execution_blockers(**bound)
    state = "BLOCKED" if blockers else "OBSERVED"
    return _result(
        state,
        domain_output={"blockers": blockers},
        message=(
            "The existing execution policy returned blockers for this operation."
            if blockers
            else "The existing execution policy returned no blockers for this operation."
        ),
        limitations=limitations,
    )


def alpha_check(invocation: Mapping[str, Any]) -> dict[str, Any]:
    """Compose five existing EVOLVE checks into one JSON-serializable observation.

    Sections are optional so absence remains explicit ``UNASSESSED``.  A section
    that is present must bind to the current runtime function signature; malformed
    structure raises :class:`AlphaInvocationError` rather than being converted to
    a scientific or policy observation.

    ``candidate_reconciliation`` and ``novelty_outage`` contain the exact kwargs
    for ``reconcile_candidates`` and ``assess_novelty``.  Evaluator input contains
    ``run_spec_kwargs``, optional ``firewall_kwargs``, and an optional
    ``observed_bundle``.  Prompt input contains ``proposal_kwargs`` plus source and
    target run IDs.  Sandbox input contains the supplied ``profile``, ``lease``,
    ``requested_capabilities``, and the remaining ``execution_blockers`` kwargs
    under ``operation``.  This shape is an invocation convention only, not a
    persisted contract.
    """
    document = _mapping(invocation, "alpha-check invocation")
    _reject_unknown_keys(document, CHECK_NAMES, "alpha-check invocation")

    checks = {
        "candidate_reconciliation": _candidate_reconciliation(
            _section(document, "candidate_reconciliation")
        ),
        "evaluator_immutability": _evaluator_immutability(
            _section(document, "evaluator_immutability")
        ),
        "novelty_outage": _novelty_outage(
            _section(document, "novelty_outage")
        ),
        "prompt_current_run_authority": _prompt_current_run_authority(
            _section(document, "prompt_current_run_authority")
        ),
        "sandbox_security": _sandbox_security(
            _section(document, "sandbox_security")
        ),
    }
    return {
        "observation_type": "EVOLVE_INVARIANT_COMPOSITION",
        "checks": checks,
        "limitations": [
            "This is an ephemeral observation over caller-supplied inputs, not "
            "canonical state.",
            "It creates no schema, receipt, gate decision, acceptance record, "
            "acceptance metric, or release claim.",
            "It does not execute evolution, candidate code, hidden evaluation, "
            "calibration, validation, or promotion.",
            "For byte-repeatable output, callers must supply optional IDs and "
            "timestamps instead of using existing builder defaults.",
        ],
    }


__all__ = ["AlphaInvocationError", "alpha_check"]
