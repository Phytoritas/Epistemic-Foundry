"""Executable-candidate threat controls over the evolution security surfaces.

The firewall seals evaluators and holdouts, the quarantine holds mutation
proposals inert, and the sandbox contracts bound ordinary tools — but nothing
asked the question EF4-I64 poses about an *evolution candidate*: before this
generated thing runs, is every declared control actually in place, and does
the run's active surface contain anything the quarantine has not released?

Three gates do the work.  Execution qualification refuses candidate code
whose target manifest leaves a network open, declares no quota, names no
effect-receipt channel, or runs outside a declared sandbox class — and it
re-verifies the evaluator/holdout isolation through the sealed firewall
rather than trusting flags.  The mutation gate refuses a run whose active
prompt surface carries a genome its proposal has not qualified (EF4-I55),
and delegates the retroactivity rule to the quarantine module that owns it.
The leakage audit turns the firewall's holdout intersection into the
canonical leakage-audit record with the incident actions the threat model
prescribes (EF4-I44).

The sandbox-class vocabulary and the threat register are parsed from
`docs/evolution_security_threat_model.md`, the invariant's own evidence
artifact; the network, safety and status vocabularies are read from their
canonical schemas positionally, because holding those enum values as
literals is exactly what EF4-I22 forbids.  Nothing here scores, promotes or
executes anything.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ...budgets.envelope import (
    BudgetViolation,
    normalize_hard_limits,
    spend_is_bounded,
)
from ...contracts import (
    ContractViolation,
    default_registry,
    repo_root,
    validate_artifact,
)
from ...domain.hashing import hash_excluding
from ...domain.ids import new_id
from ...governance.quarantine import (
    QuarantineViolation,
    may_influence_run,
    require_not_retroactive,
)
from ...verifier_firewall.firewall import (
    CANDIDATE_GENERATING_ROLES,
    VerifierFirewall,
)

THREAT_MODEL_PATH = "docs/evolution_security_threat_model.md"

#: Every way this module refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "APPROVAL_MISSING": (
        "a high-risk target declares an approval policy that approves nothing, "
        "so the riskiest execution class would run without a human gate"
    ),
    "CANDIDATE_KIND_UNQUALIFIED": (
        "execution was requested for a kind outside the sealed mutable search "
        "space; only a canonical genome kind is a candidate at all"
    ),
    "CAPABILITY_UNDECLARED": (
        "the target allows network egress but declares no capability "
        "requirement, so the allowlist would bound nothing"
    ),
    "HOLDOUT_REACHABLE": (
        "a candidate-generating role can reach the hidden holdout, which lets "
        "a generator fit the material it will be judged against"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this module requires, and continuing would "
        "qualify an execution it never validated"
    ),
    "LEAKAGE_SURFACE_MISSING": (
        "the audit did not check every leakage surface the invariant names; an "
        "unchecked channel is where the holdout escapes"
    ),
    "NETWORK_POLICY_OPEN": (
        "candidate code may not run under an open network policy; egress is "
        "denied by default and an approval path is not a boundary"
    ),
    "QUARANTINED_INFLUENCE": (
        "the run's active surface carries a genome whose proposal the "
        "quarantine has not released; activation requires future-run "
        "qualification"
    ),
    "QUOTA_MISSING": (
        "the execution declares no enforceable resource limit, so a runaway "
        "candidate would be bounded by nothing but the host"
    ),
    "RECEIPT_CHANNEL_MISSING": (
        "no effect-receipt channel is bound, so whatever the candidate did "
        "would be unaccounted for afterwards"
    ),
    "RETROACTIVE_MUTATION": (
        "a mutation proposal was applied to the run that produced it, which is "
        "how a run rewrites the judgments it already received"
    ),
    "SANDBOX_CLASS_UNDECLARED": (
        "the target names a sandbox profile the threat model does not declare, "
        "and candidate code never runs outside a declared class"
    ),
    "THREAT_MODEL_UNREADABLE": (
        "the threat model document could not be parsed, so neither the sandbox "
        "classes nor the threat register can be trusted"
    ),
    "THREAT_UNCOVERED": (
        "a registered threat has no control evidence bound to it, so coverage "
        "would be claimed by omission"
    ),
    "THREAT_UNDECLARED": (
        "control evidence names a threat the register does not declare, which "
        "pads the coverage record with unreviewable rows"
    ),
}

INVARIANTS_PATH = "manifests/product_invariants.yaml"
LEAKAGE_INVARIANT_ID = "EF4-I44"

#: Incident actions the threat model prescribes on a failed audit.  Their
#: agreement with the document's incident-handling section is asserted by the
#: schema-and-type suite rather than assumed.
INCIDENT_ACTIONS: tuple[str, ...] = (
    "immediate typed stop",
    "checkpoint quarantine",
    "impact analysis",
    "explicit requalification",
)


class ThreatControlError(ValueError):
    """An execution, mutation or audit request would breach a control."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise ThreatControlError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ThreatControlError(code, message, context)


def _threat_model_text() -> str:
    path = repo_root() / THREAT_MODEL_PATH
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        _fail(
            "THREAT_MODEL_UNREADABLE",
            f"cannot read {THREAT_MODEL_PATH}: {error}",
            {"path": THREAT_MODEL_PATH},
        )
        return ""


def sandbox_classes() -> tuple[str, ...]:
    """The declared sandbox classes, parsed from the threat model itself."""
    text = _threat_model_text()
    section = re.search(r"## Sandbox classes\n(.*?)(?:\n## |\Z)", text, re.DOTALL)
    if section is None:
        _fail("THREAT_MODEL_UNREADABLE", "the sandbox-classes section is absent")
    names = re.findall(r"^- `([a-z_]+)`:", section.group(1), re.MULTILINE)
    if not names:
        _fail("THREAT_MODEL_UNREADABLE", "the sandbox-classes section names no class")
    return tuple(names)


def threat_register() -> dict[str, str]:
    """The high-priority threat table: threat -> prescribed control."""
    text = _threat_model_text()
    section = re.search(r"## High-priority threats\n(.*?)(?:\n## |\Z)", text, re.DOTALL)
    if section is None:
        _fail("THREAT_MODEL_UNREADABLE", "the threat table is absent")
    rows: dict[str, str] = {}
    for line in section.group(1).splitlines():
        match = re.fullmatch(r"\| ([^|]+) \| ([^|]+) \|", line.strip())
        if match is None:
            continue
        threat, control = match.group(1).strip(), match.group(2).strip()
        if threat in {"Threat", "---"} or set(threat) == {"-"}:
            continue
        rows[threat] = control
    if not rows:
        _fail("THREAT_MODEL_UNREADABLE", "the threat table declares no row")
    return rows


def required_leakage_surfaces() -> tuple[str, ...]:
    """The audit's minimum surfaces, parsed from the invariant that names them.

    EF4-I44's own statement enumerates the leakage channels as a
    slash-separated list before the word "leakage"; reading it from the
    invariant keeps this module from holding channel names as literals
    (one of them is a canonical enum value elsewhere) and means a widened
    invariant widens the audit's floor without an edit here.
    """
    import yaml

    path = repo_root() / INVARIANTS_PATH
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        _fail(
            "THREAT_MODEL_UNREADABLE",
            f"cannot read {INVARIANTS_PATH}: {error}",
            {"path": INVARIANTS_PATH},
        )
    statement = next(
        (
            str(row["statement"])
            for row in document["invariants"]
            if row.get("id") == LEAKAGE_INVARIANT_ID
        ),
        None,
    )
    if statement is None:
        _fail(
            "THREAT_MODEL_UNREADABLE",
            f"{LEAKAGE_INVARIANT_ID} is absent from the invariant manifest",
            {"invariant": LEAKAGE_INVARIANT_ID},
        )
    match = re.search(r"([\w]+(?:/[\w]+)+) leakage", statement)
    if match is None:
        _fail(
            "THREAT_MODEL_UNREADABLE",
            f"{LEAKAGE_INVARIANT_ID} no longer enumerates its leakage channels",
            {"statement": statement},
        )
    return tuple(sorted(match.group(1).split("/")))


def build_threat_coverage(
    *,
    run_id: str,
    control_evidence: Mapping[str, Sequence[str]],
    coverage_id: str | None = None,
) -> dict[str, Any]:
    """Bind evidence artifacts to every registered threat, or refuse.

    Coverage is exact in both directions: a registered threat without
    evidence is refused rather than skipped, and evidence for a threat the
    register does not declare is refused rather than padding the record.
    """
    register = threat_register()
    provided = {
        str(threat): list(map(str, ids)) for threat, ids in control_evidence.items()
    }
    uncovered = sorted(threat for threat in register if not provided.get(threat))
    if uncovered:
        _fail(
            "THREAT_UNCOVERED",
            "registered threats lack control evidence",
            {"uncovered": uncovered},
        )
    undeclared = sorted(set(provided) - set(register))
    if undeclared:
        _fail(
            "THREAT_UNDECLARED",
            "control evidence names unregistered threats",
            {"undeclared": undeclared},
        )
    coverage: dict[str, Any] = {
        "coverage_id": coverage_id or new_id("ETC"),
        "run_id": run_id,
        "threat_model_path": THREAT_MODEL_PATH,
        "threats": {
            threat: {
                "control": register[threat],
                "evidence_artifact_ids": sorted(provided[threat]),
            }
            for threat in sorted(register)
        },
    }
    coverage["coverage_hash"] = hash_excluding(coverage, "coverage_hash")
    return coverage


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


def _manifest_vocabulary(field: str) -> list[str]:
    document = default_registry().document("validation-target-manifest")
    return list(document["properties"][field]["enum"])


def qualify_candidate_execution(
    *,
    candidate_kind: str,
    target_manifest: Mapping[str, Any],
    budget_envelope: Mapping[str, Any],
    effect_receipt_channel_id: str,
    firewall: VerifierFirewall,
    holdout_read_probe_principal: str = "S05-EXECUTION-PROBE",
    qualification_id: str | None = None,
) -> dict[str, Any]:
    """Decide whether candidate code may execute at all (EF4-I64).

    Every control is verified against the surface that owns it: the search
    space against the sealed C05 index, the manifest against its canonical
    schema, the quotas through the budget module's own normalizer, and the
    isolation through the sealed firewall — including a live probe that every
    candidate-generating role is denied holdout access, so the isolation
    claim is exercised rather than assumed.
    """
    import json

    index_path = repo_root() / "schemas/v4_c05/family-index.json"
    search_space = [
        entry.rsplit("/", 1)[-1].removesuffix(".schema.json")
        for entry in json.loads(index_path.read_text(encoding="utf-8"))[
            "mutable_search_space"
        ]
    ]
    if candidate_kind not in search_space:
        _fail(
            "CANDIDATE_KIND_UNQUALIFIED",
            f"{candidate_kind} is not in the sealed mutable search space",
            {"candidate_kind": candidate_kind, "mutable_search_space": search_space},
        )

    manifest = dict(_require_mapping(target_manifest, "target_manifest"))
    validate_artifact("validation-target-manifest", manifest)

    declared_classes = sandbox_classes()
    profile = str(manifest["sandbox_profile"])
    if profile not in declared_classes:
        _fail(
            "SANDBOX_CLASS_UNDECLARED",
            f"sandbox profile {profile} is not a declared class",
            {"declared": list(declared_classes), "profile": profile},
        )

    # The schema declares these vocabularies in escalating order (closed ->
    # open, benign -> dangerous, no approval -> all effects).  Positions are
    # used instead of the enum values themselves because holding another
    # schema's enum literals is what EF4-I22 forbids; the schema-and-type
    # suite asserts the ordering assumption against the schema text.
    network_order = _manifest_vocabulary("network_policy")
    safety_order = _manifest_vocabulary("safety_class")
    approval_order = _manifest_vocabulary("approval_policy")
    network = str(manifest["network_policy"])
    if network == network_order[-1]:
        _fail(
            "NETWORK_POLICY_OPEN",
            "candidate code may not run under the open network policy",
            {"declared_order": network_order, "network_policy": network},
        )
    capabilities = list(manifest["capability_requirements"])
    if network == network_order[1] and not capabilities:
        _fail(
            "CAPABILITY_UNDECLARED",
            "an allowlisted network needs declared capability requirements",
            {"network_policy": network},
        )
    if (
        str(manifest["safety_class"]) == safety_order[-1]
        and str(manifest["approval_policy"]) == approval_order[0]
    ):
        _fail(
            "APPROVAL_MISSING",
            "the highest safety class cannot run with no approval policy",
            {
                "approval_policy": str(manifest["approval_policy"]),
                "safety_class": str(manifest["safety_class"]),
            },
        )

    envelope = dict(_require_mapping(budget_envelope, "budget_envelope"))
    try:
        validate_artifact("budget-envelope", envelope)
    except ContractViolation as error:
        _fail("INPUT_INVALID", str(error), {"budget_envelope": envelope})

    expected_budget_hash = hash_excluding(envelope, "budget_hash")
    if envelope["budget_hash"] != expected_budget_hash:
        _fail(
            "INPUT_INVALID",
            "budget_envelope.budget_hash does not match its canonical content",
            {
                "budget_id": envelope["budget_id"],
                "expected_budget_hash": expected_budget_hash,
                "submitted_budget_hash": envelope["budget_hash"],
            },
        )
    if not spend_is_bounded(envelope):
        _fail(
            "QUOTA_MISSING",
            "the budget envelope does not declare bounded enforcement",
            {
                "budget_id": envelope["budget_id"],
                "enforcement": envelope["enforcement"],
            },
        )

    try:
        limits = normalize_hard_limits(envelope["hard_limits"])
    except BudgetViolation as error:
        _fail("QUOTA_MISSING", str(error), {"hard_limits": envelope["hard_limits"]})
    for dimension, value in limits.items():
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            _fail(
                "INPUT_INVALID",
                f"hard_limits.{dimension} must be a non-negative integer or null",
                {
                    "dimension": dimension,
                    "submitted_type": type(value).__name__,
                },
            )
    if all(value is None for value in limits.values()):
        _fail(
            "QUOTA_MISSING",
            "every quota dimension is null; nothing bounds the execution",
            {"hard_limits": limits},
        )

    channel = str(effect_receipt_channel_id or "").strip()
    if not channel:
        _fail("RECEIPT_CHANNEL_MISSING", "an effect-receipt channel must be bound")

    firewall.verify_self()
    reachable = sorted(
        role
        for role in CANDIDATE_GENERATING_ROLES
        if firewall.may_read_holdout(holdout_read_probe_principal, role)
    )
    if reachable:
        _fail(
            "HOLDOUT_REACHABLE",
            "candidate-generating roles can read the hidden holdout",
            {"roles": reachable},
        )

    register = threat_register()
    qualification: dict[str, Any] = {
        "budget_enforcement": str(envelope["enforcement"]),
        "budget_hash": str(envelope["budget_hash"]),
        "budget_id": str(envelope["budget_id"]),
        "candidate_kind": candidate_kind,
        "capability_requirements": sorted(map(str, capabilities)),
        "effect_receipt_channel_id": channel,
        "evaluator_bundle_hash": firewall.sealed_hash,
        "hard_limits": limits,
        "network_policy": network,
        "qualification_id": qualification_id or new_id("EXQ"),
        "safety_class": str(manifest["safety_class"]),
        "sandbox_profile": profile,
        "target_id": str(manifest["target_id"]),
        # The threats this qualification actually exercised, named from the
        # register so the record cannot claim coverage the model never asked
        # for.
        "threats_controlled": sorted(
            threat
            for threat in register
            if threat
            in {
                "candidate mutates evaluator",
                "candidate reads holdout",
                "shell/network abuse",
                "unsafe challenge",
            }
        ),
    }
    qualification["qualification_hash"] = hash_excluding(
        qualification, "qualification_hash"
    )
    return qualification


def require_inert_mutations(
    *,
    target_run_id: str,
    active_prompt_genome_ids: Sequence[str],
    proposals: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Refuse a run whose active surface holds unreleased mutations (EF4-I55).

    Influence is judged by the quarantine module that owns the vocabulary,
    and the retroactivity rule is delegated to its own enforcement point so
    this gate cannot drift from the proposals it polices.
    """
    active = set(map(str, active_prompt_genome_ids))
    allowed_statuses = default_registry().document("prompt-mutation-proposal")[
        "properties"
    ]["status"]["enum"]
    held: list[dict[str, Any]] = []
    released = 0
    for position, candidate_proposal in enumerate(proposals):
        proposal = dict(_require_mapping(candidate_proposal, f"proposals[{position}]"))
        status = proposal.get("status")
        if not isinstance(status, str) or status not in allowed_statuses:
            _fail(
                "INPUT_INVALID",
                f"proposals[{position}].status must be a canonical prompt-mutation-proposal status",
                {
                    "allowed_statuses": list(allowed_statuses),
                    "position": position,
                    "status": status,
                },
            )
        proposed = str(proposal.get("proposed_prompt_genome_id") or "")
        influences = may_influence_run(proposal)
        if proposed and proposed in active:
            if not influences:
                held.append(
                    {
                        "proposal_id": str(proposal.get("proposal_id")),
                        "proposed_prompt_genome_id": proposed,
                        "status": str(proposal.get("status")),
                    }
                )
                continue
            try:
                require_not_retroactive(proposal, target_run_id=target_run_id)
            except QuarantineViolation as error:
                _fail(
                    "RETROACTIVE_MUTATION",
                    str(error),
                    {"proposal_id": str(proposal.get("proposal_id"))},
                )
            released += 1
    if held:
        _fail(
            "QUARANTINED_INFLUENCE",
            "the active prompt surface carries unreleased mutations",
            {"held": held},
        )
    return {
        "active_prompt_genome_count": len(active),
        "proposals_examined": len(proposals),
        "released_activations": released,
        "target_run_id": target_run_id,
    }


def build_leakage_audit(
    *,
    firewall: VerifierFirewall,
    run_or_bundle_id: str,
    surfaces_checked: Sequence[str],
    observed_artifact_ids: Sequence[str],
    access_log_artifact_id: str,
    similarity_alerts: Sequence[str] = (),
    leakage_audit_id: str | None = None,
) -> dict[str, Any]:
    """Turn the firewall's holdout intersection into the canonical audit.

    The audit must check at least the surfaces EF4-I44 names — tool, log and
    cache — and its status vocabulary is read from the canonical schema
    rather than restated.  A failed audit carries the incident actions the
    threat model prescribes; it never converts an exposure into a score
    adjustment.
    """
    checked = sorted(set(map(str, surfaces_checked)))
    missing = sorted(set(required_leakage_surfaces()) - set(checked))
    if missing:
        _fail(
            "LEAKAGE_SURFACE_MISSING",
            "the audit skipped surfaces the invariant names",
            {"checked": checked, "missing": missing},
        )
    exposures = firewall.leakage_invalidates(list(map(str, observed_artifact_ids)))
    statuses = default_registry().document("leakage-audit")["properties"]["status"][
        "enum"
    ]
    # Positional selection from the declared vocabulary: index 0 is the clean
    # outcome and index 1 the failed one, asserted against the schema by the
    # schema-and-type suite (EF4-I22 forbids holding the values here).
    audit: dict[str, Any] = {
        "leakage_audit_id": leakage_audit_id or new_id("LKA"),
        "run_or_bundle_id": run_or_bundle_id,
        "surfaces_checked": checked,
        "detected_exposures": exposures,
        "similarity_alerts": sorted(map(str, similarity_alerts)),
        "access_log_artifact_id": access_log_artifact_id,
        "status": statuses[1] if exposures else statuses[0],
        "required_actions": list(INCIDENT_ACTIONS) if exposures else [],
    }
    audit["audit_hash"] = hash_excluding(audit, "audit_hash")
    validate_artifact("leakage-audit", audit)
    return audit
