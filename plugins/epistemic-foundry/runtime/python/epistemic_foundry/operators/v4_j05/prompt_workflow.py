"""Prompt genome lifecycle and the quarantine activation workflow.

A prompt genome is the one member of the sealed mutable search space that acts
on the machinery rather than on the science: it is the instruction a generator
receives, so a prompt that quietly changes mid-run changes what every later
candidate could have been.  EF4-I55 answers that by making a prompt change a
*proposal for a future sealed run*, and this module is the path a change has to
walk to become one.

Construction is the first half.  A genome is built against its canonical schema
and is born into the status the schema declares first — a status the quarantine
module's own inert set must agree cannot influence a run — so nothing is ever
constructed already active.

Changing an existing genome is the second half, and it round-trips through
surfaces this module does not own.  The edit itself goes through the evolution
chamber's authority-checked mutation, which refuses a change to a field that
carries authority.  The changed fields are then derived from the actual
before/after documents and handed to the governance quarantine module's own
proposal builder — the proposal is never minted here, because the quarantine
owns what a proposal is, forces it born quarantined, and refuses a change that
names nothing or analyses no risk.  The resulting proposal is put to the S05
inert-mutations gate against the run's declared active prompt surface, so a
caller claiming the successor is already live is refused by the gate rather
than by an opinion held here.  The successor is a new genome with a new id: the
source document is returned untouched, because editing an active prompt in
place is precisely the move the invariant forbids.

Activation is the verdict.  Given a proposal, the run it came from, the run it
would apply to, and the qualification evidence, the future-run-only rule is
checked by the quarantine module's `require_not_retroactive` — the canonical
proposal carries no run linkage of its own (its schema forbids extra fields),
so the run id is supplied beside it and the pair is handed to the rule rather
than the rule being restated here.  What comes back is an activation record
that re-derives its own digest, so a later reader can prove the record is the
one the gates produced.  Nothing here approves a proposal, and no status is
ever written by this module onto a proposal: releasing quarantine is the
qualification process's decision, mirrored by the
`verify_no_retroactive_effect` node of the evaluator update governance
workflow, whose continued existence is verified rather than assumed.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...contracts import ContractViolation, repo_root, validate_artifact
from ...domain.hashing import hash_excluding, sha256_of_payload
from ...evolution_chamber.mutation import AuthorityMutationRefused, apply_mutation
from ...governance.quarantine import (
    QuarantineViolation,
    build_prompt_mutation_proposal,
    may_influence_run,
    require_not_retroactive,
)
from ...security.v4_s05 import ThreatControlError, require_inert_mutations
from .declarations import (
    CONTEXT_CLASSES_FIELD,
    FIRST_VERSION,
    FITNESS_HISTORY_FIELD,
    FORBIDDEN_AUTHORITIES_FIELD,
    IDENTITY_FIELD,
    PARENT_PROMPTS_FIELD,
    PROMPT_GENOME_KIND,
    PROMPT_HASH_FIELD,
    PROMPT_PROPOSAL_KIND,
    PROPOSAL_HASH_FIELD,
    PROPOSAL_ID_FIELD,
    PROPOSED_PROMPT_FIELD,
    SOURCE_PROMPT_FIELD,
    STATUS_FIELD,
    TASK_CLASS_FIELD,
    TEMPLATE_FIELD,
    VERSION_FIELD,
    _fail,
    _require_mapping,
    _require_text,
    prompt_genome_contract,
    prompt_proposal_contract,
    proposal_status_vocabulary,
    quarantined_prompt_status,
    require_sealed_digest,
)

#: The governance workflow whose retroactivity node this activation mirrors.
GOVERNANCE_WORKFLOW = "workflows/evaluator_update_governance.workflow.yaml"
RETROACTIVITY_NODE = "verify_no_retroactive_effect"

#: The run linkage the canonical proposal schema cannot carry.  The proposal
#: forbids additional properties, so the run that produced it travels beside it
#: and the pair is what the quarantine's retroactivity rule is given.
SOURCE_RUN_FIELD = "source_run_id"

#: Fields the lifecycle derives.  A caller that could set them would let a
#: successor forge its own identity, version, parentage or digest.
LIFECYCLE_FIELDS: tuple[str, ...] = (
    IDENTITY_FIELD,
    PARENT_PROMPTS_FIELD,
    PROMPT_HASH_FIELD,
    VERSION_FIELD,
)


def governance_retroactivity_node() -> str:
    """The workflow node this activation mirrors, refused if it is gone.

    The verdict claims to enforce the same rule a canonical workflow declares.
    If that node disappears, the claim is no longer true of anything, so it is
    read rather than asserted.
    """
    import yaml

    path = repo_root() / GOVERNANCE_WORKFLOW
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail(
            "WORKFLOW_CONTRACT_DRIFT",
            f"cannot read {GOVERNANCE_WORKFLOW}",
            {"detail": str(error), "path": GOVERNANCE_WORKFLOW},
        )
    nodes = _require_mapping(document, "workflow").get("nodes")
    declared = {
        str(node.get("node_id"))
        for node in (nodes if isinstance(nodes, list) else [])
        if isinstance(node, Mapping)
    }
    if RETROACTIVITY_NODE not in declared:
        _fail(
            "WORKFLOW_CONTRACT_DRIFT",
            f"{GOVERNANCE_WORKFLOW} no longer declares {RETROACTIVITY_NODE}",
            {"path": GOVERNANCE_WORKFLOW},
        )
    return RETROACTIVITY_NODE


def _text_list(value: object, label: str) -> list[str]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        _fail(
            "INPUT_INVALID", f"{label} must be a sequence of strings", {"label": label}
        )
    items: list[str] = []
    for index, item in enumerate(value):  # type: ignore[union-attr]
        if not isinstance(item, str) or not item.strip():
            _fail(
                "INPUT_INVALID",
                f"{label}[{index}] must be a non-empty string",
                {"label": label, "position": index},
            )
        items.append(item)
    return items


def build_prompt_genome(
    *,
    prompt_genome_id: str,
    task_class: str,
    template: str,
    forbidden_authorities: Sequence[str],
    allowed_context_classes: Sequence[str] = (),
    fitness_history_ids: Sequence[str] = (),
    parent_prompt_ids: Sequence[str] = (),
    version: int = FIRST_VERSION,
) -> dict[str, Any]:
    """Construct a prompt genome, validated and born quarantined.

    `status` is not a parameter, exactly as it is not one on the quarantine
    module's proposal builder: a genome that could be constructed active would
    reach a run without ever passing a qualification.
    """
    prompt_genome_contract()
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        _fail(
            "INPUT_INVALID",
            "version must be a positive integer",
            {VERSION_FIELD: version},
        )
    authorities = _text_list(forbidden_authorities, FORBIDDEN_AUTHORITIES_FIELD)
    if not authorities:
        _fail(
            "PROMPT_AUTHORITY_UNDECLARED",
            "a prompt genome must forbid at least one authority",
            {IDENTITY_FIELD: str(prompt_genome_id)},
        )

    document: dict[str, Any] = {
        CONTEXT_CLASSES_FIELD: _text_list(
            allowed_context_classes, CONTEXT_CLASSES_FIELD
        ),
        FITNESS_HISTORY_FIELD: _text_list(fitness_history_ids, FITNESS_HISTORY_FIELD),
        FORBIDDEN_AUTHORITIES_FIELD: authorities,
        IDENTITY_FIELD: _require_text(prompt_genome_id, IDENTITY_FIELD),
        PARENT_PROMPTS_FIELD: _text_list(parent_prompt_ids, PARENT_PROMPTS_FIELD),
        STATUS_FIELD: quarantined_prompt_status(),
        TASK_CLASS_FIELD: _require_text(task_class, TASK_CLASS_FIELD),
        TEMPLATE_FIELD: _require_text(template, TEMPLATE_FIELD),
        VERSION_FIELD: version,
    }
    return _sealed_genome(document)


def _sealed_genome(document: Mapping[str, Any]) -> dict[str, Any]:
    """Attach the derived digest and validate against the canonical schema."""
    genome = {key: value for key, value in document.items() if key != PROMPT_HASH_FIELD}
    genome[PROMPT_HASH_FIELD] = hash_excluding(genome, PROMPT_HASH_FIELD)
    try:
        validate_artifact(PROMPT_GENOME_KIND, genome)
    except ContractViolation as error:
        _fail(
            "PROMPT_GENOME_MALFORMED",
            "the prompt genome does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    return genome


def _changed_fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Top-level fields whose canonical value differs, additions included.

    Derived from the documents rather than taken from the caller, so a change
    set that reports one edit and performs another is named by what it did.
    """
    changed: list[str] = []
    for key in sorted(set(before) | set(after)):
        if key not in before or key not in after:
            changed.append(key)
        elif sha256_of_payload(before[key]) != sha256_of_payload(after[key]):
            changed.append(key)
    return changed


def propose_prompt_genome_change(
    *,
    source_genome: Mapping[str, Any],
    changes: Mapping[str, Any],
    proposed_prompt_genome_id: str,
    motivation: str,
    risk_analysis: Sequence[str],
    qualification_plan_id: str,
    target_run_id: str,
    active_prompt_genome_ids: Sequence[str] = (),
    proposal_id: str | None = None,
) -> dict[str, Any]:
    """Turn a wanted change into a quarantined proposal and a successor genome.

    This is the only way a change to a prompt genome exists in this package.
    The proposal is built by the quarantine module, the authority check is the
    evolution chamber's, and the active-surface check is S05's; what is added
    here is the successor document and the accounting that ties them together.
    """
    prompt_genome_contract()
    prompt_proposal_contract()
    proposal_status_vocabulary()

    source = dict(_require_mapping(source_genome, "source_genome"))
    try:
        validate_artifact(PROMPT_GENOME_KIND, source)
    except ContractViolation as error:
        _fail(
            "PROMPT_GENOME_MALFORMED",
            "the source prompt genome does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    require_sealed_digest(source, PROMPT_HASH_FIELD, PROMPT_GENOME_KIND)
    source_id = _require_text(source.get(IDENTITY_FIELD), IDENTITY_FIELD)
    proposed_id = _require_text(proposed_prompt_genome_id, PROPOSED_PROMPT_FIELD)
    run = _require_text(target_run_id, "target_run_id")
    if proposed_id == source_id:
        _fail(
            "PROMPT_IDENTITY_REUSED",
            "a successor prompt genome needs an id of its own",
            {IDENTITY_FIELD: source_id},
        )

    requested = dict(_require_mapping(changes, "changes"))
    edited = sorted(set(requested) & set(LIFECYCLE_FIELDS))
    if edited:
        _fail(
            "PROMPT_LINEAGE_FIELD_EDITED",
            "the change edits fields the lifecycle derives",
            {"fields": edited, IDENTITY_FIELD: source_id},
        )
    try:
        mutated = apply_mutation(source, requested)
    except AuthorityMutationRefused as error:
        _fail(
            "PROMPT_AUTHORITY_MUTATION",
            str(error),
            {IDENTITY_FIELD: source_id, "requested": sorted(requested)},
        )
        return {}

    changed_sections = _changed_fields(source, mutated)
    try:
        proposal = build_prompt_mutation_proposal(
            source_prompt_genome_id=source_id,
            proposed_prompt_genome_id=proposed_id,
            motivation=_require_text(motivation, "motivation"),
            changed_sections=changed_sections,
            risk_analysis=list(risk_analysis or ()),
            qualification_plan_id=_require_text(
                qualification_plan_id, "qualification_plan_id"
            ),
            proposal_id=proposal_id,
        )
    except QuarantineViolation as error:
        code = (
            "PROMPT_CHANGE_EMPTY" if not changed_sections else "RISK_ANALYSIS_MISSING"
        )
        _fail(code, str(error), {IDENTITY_FIELD: source_id})
        return {}

    successor = dict(mutated)
    successor[IDENTITY_FIELD] = proposed_id
    successor[VERSION_FIELD] = int(source[VERSION_FIELD]) + 1
    successor[PARENT_PROMPTS_FIELD] = [
        *(str(parent) for parent in source[PARENT_PROMPTS_FIELD]),
        source_id,
    ]
    successor[STATUS_FIELD] = quarantined_prompt_status()
    successor = _sealed_genome(successor)

    try:
        gate = require_inert_mutations(
            target_run_id=run,
            active_prompt_genome_ids=_text_list(
                active_prompt_genome_ids, "active_prompt_genome_ids"
            ),
            proposals=(dict(proposal),),
        )
    except ThreatControlError as error:
        _fail(
            "PROMPT_MUTATION_INERT",
            str(error),
            {"gate_code": error.code, PROPOSED_PROMPT_FIELD: proposed_id},
        )
        return {}

    change: dict[str, Any] = {
        "changed_sections": list(changed_sections),
        "gate": dict(gate),
        "proposal": dict(proposal),
        "proposed_genome": dict(successor),
        SOURCE_PROMPT_FIELD: source_id,
        "source_prompt_hash": str(source[PROMPT_HASH_FIELD]),
        "target_run_id": run,
    }
    change["change_hash"] = hash_excluding(change, "change_hash")
    return change


def build_activation_record(
    *,
    proposal: Mapping[str, Any],
    source_run_id: str,
    target_run_id: str,
    qualification_evidence_ids: Sequence[str],
    activated_at: str,
    operator_id: str | None = None,
    activation_id: str | None = None,
) -> dict[str, Any]:
    """Record that a released proposal may act on one future run, or refuse.

    Three questions are asked, and none of them here: whether the proposal may
    influence a run at all, and whether the target is the run that produced it,
    are the quarantine module's; the record only becomes a record once both
    have been answered by it.  The third — whether qualification happened — is
    answered by evidence artifacts, so an activation binding none is refused
    rather than resting on an assertion.
    """
    prompt_proposal_contract()
    proposal_status_vocabulary()
    node = governance_retroactivity_node()

    document = dict(_require_mapping(proposal, "proposal"))
    try:
        validate_artifact(PROMPT_PROPOSAL_KIND, document)
    except ContractViolation as error:
        _fail(
            "PROPOSAL_MALFORMED",
            "the prompt mutation proposal does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    require_sealed_digest(document, PROPOSAL_HASH_FIELD, PROMPT_PROPOSAL_KIND)
    source_run = _require_text(source_run_id, SOURCE_RUN_FIELD)
    target_run = _require_text(target_run_id, "target_run_id")
    evidence = _text_list(qualification_evidence_ids, "qualification_evidence_ids")
    if not evidence:
        _fail(
            "QUALIFICATION_EVIDENCE_MISSING",
            "an activation must bind the qualification evidence that released it",
            {PROPOSAL_ID_FIELD: str(document[PROPOSAL_ID_FIELD])},
        )

    if not may_influence_run(document):
        _fail(
            "PROMPT_MUTATION_INERT",
            "the proposal is still held by the quarantine and may not act",
            {
                PROPOSAL_ID_FIELD: str(document[PROPOSAL_ID_FIELD]),
                "quarantine_status": str(document[STATUS_FIELD]),
            },
        )
    try:
        require_not_retroactive(
            {**document, SOURCE_RUN_FIELD: source_run}, target_run_id=target_run
        )
    except QuarantineViolation as error:
        _fail(
            "RETROACTIVE_ACTIVATION",
            str(error),
            {SOURCE_RUN_FIELD: source_run, "target_run_id": target_run},
        )

    record: dict[str, Any] = {
        "activated_at": _require_text(activated_at, "activated_at"),
        "activation_id": activation_id or f"PGA-{document[PROPOSAL_ID_FIELD]}",
        "governance_node_id": node,
        "operator_id": None if operator_id is None else str(operator_id),
        "proposal_hash": str(document["proposal_hash"]),
        PROPOSAL_ID_FIELD: str(document[PROPOSAL_ID_FIELD]),
        PROPOSED_PROMPT_FIELD: str(document[PROPOSED_PROMPT_FIELD]),
        "qualification_evidence_ids": sorted(evidence),
        "quarantine_status": str(document[STATUS_FIELD]),
        SOURCE_PROMPT_FIELD: str(document[SOURCE_PROMPT_FIELD]),
        SOURCE_RUN_FIELD: source_run,
        "target_run_id": target_run,
    }
    record["activation_hash"] = hash_excluding(record, "activation_hash")
    return record


def verify_activation_record(record: Mapping[str, Any]) -> str:
    """Re-derive an activation record's digest, or refuse the record.

    A record whose digest does not re-derive from the fields it publishes is
    not the record the gates produced, whatever it says about itself.
    """
    document = dict(_require_mapping(record, "record"))
    claimed = document.get("activation_hash")
    derived = hash_excluding(document, "activation_hash")
    if claimed != derived:
        _fail(
            "ACTIVATION_RECORD_DRIFT",
            "the activation record does not re-derive its own digest",
            {"claimed": claimed, "derived": derived},
        )
    return derived
