"""Every way this package refuses, and every contract it reads rather than restates.

A typed operator registry is only typed if the types come from somewhere that
outranks it.  The mutable search space is sealed by C05 and already read by the
I05 intake, the operator shape is declared by
`schemas/mutation-operator-spec.schema.json`, the prompt genome by
`schemas/prompt-genome.schema.json`, and the proposal that gates any prompt
change by `schemas/prompt-mutation-proposal.schema.json`.  This module is the
one place those authorities are opened, so the registry and the prompt workflow
beside it cannot each grow their own private copy of the vocabulary.

The status vocabularies are selected *positionally* from the schemas that
declare them, never held as literals: EF4-I22 forbids a second runtime copy of
a wire value, and a status is exactly a wire value.  The positions are not
taken on trust either.  A prompt genome is born into the status at position
zero, so that status must be one the quarantine module's own ``INERT_STATUSES``
treats as unable to influence a run; the status this package calls active must
not be in that set.  Both checks are imported comparisons rather than
restatements, and the schema-and-type suite additionally pins the declared
ordering against the schema text so a reordering breaks loudly instead of
silently activating the wrong thing.
"""

from __future__ import annotations

from typing import Any, Mapping

from ...contracts import default_registry
from ...domain.hashing import hash_excluding
from ...governance.quarantine import INERT_STATUSES
from ...intake.v4_i05 import GenomeIntakeError
from ...intake.v4_i05 import mutable_genome_kinds as _sealed_search_space

#: Every way this package refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "ACTIVATION_RECORD_DRIFT": (
        "the activation record does not re-derive its own digest from the "
        "fields it publishes, so it is not the record it claims to be"
    ),
    "DIGEST_NOT_RE_DERIVABLE": (
        "the document's own digest does not re-derive from the fields it "
        "publishes, so it was edited after whoever sealed it signed for it"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this package requires, and continuing would "
        "register or activate something it never validated"
    ),
    "OPERATOR_CONTRACT_DRIFT": (
        "a field this registry reads is no longer declared by the canonical "
        "mutation operator schema, so the record would be typed against fiction"
    ),
    "OPERATOR_ID_DUPLICATED": (
        "two operators claim the same id, so the registry could not say which "
        "one a lineage naming that id was actually produced by"
    ),
    "OPERATOR_KIND_OUTSIDE_SEARCH_SPACE": (
        "the operator declares a genome kind outside the sealed C05 mutable "
        "search space, and that boundary is governance rather than preference"
    ),
    "OPERATOR_SPEC_MALFORMED": (
        "the submitted specification does not satisfy the canonical mutation "
        "operator schema, so registering it would type nothing at all"
    ),
    "OPERATOR_UNREGISTERED": (
        "the request names an operator id this registry does not hold, and an "
        "unregistered operator has no declared parameters or quarantine status"
    ),
    "PARAMETER_CONTRACT_VIOLATED": (
        "the supplied arguments do not satisfy the parameters the operator "
        "declared, so the operator would run on something it never accepted"
    ),
    "PARAMETER_SCHEMA_MALFORMED": (
        "a declared parameter is not a usable schema fragment, so the registry "
        "would advertise a type contract it could never actually enforce"
    ),
    "PROMPT_AUTHORITY_MUTATION": (
        "the change edits a field that carries authority over the run rather "
        "than the prompt content the search is allowed to explore"
    ),
    "PROMPT_AUTHORITY_UNDECLARED": (
        "the prompt genome forbids no authority, so nothing would bound what "
        "an evolved prompt is permitted to reach for"
    ),
    "PROMPT_CHANGE_EMPTY": (
        "the requested change alters no field of the source genome, so there "
        "is nothing for an independent qualification to examine"
    ),
    "PROMPT_GENOME_CONTRACT_DRIFT": (
        "a field this lifecycle writes is no longer declared by the canonical "
        "prompt genome schema, so the construction would drift from contract"
    ),
    "PROMPT_GENOME_MALFORMED": (
        "the prompt genome does not satisfy its canonical schema, and an "
        "unvalidated prompt is an unbounded instruction to a generator"
    ),
    "PROMPT_IDENTITY_REUSED": (
        "the proposed genome reuses the source id, which edits an existing "
        "prompt in place instead of proposing a successor for a future run"
    ),
    "PROMPT_LINEAGE_FIELD_EDITED": (
        "the change edits identity, version, parentage or digest, which the "
        "lifecycle derives so a successor cannot forge its own provenance"
    ),
    "PROMPT_MUTATION_INERT": (
        "the active prompt surface would carry a genome whose proposal the "
        "quarantine has not released, which is activation without qualification"
    ),
    "PROMPT_MUTATION_UNPROPOSED": (
        "a prompt-affecting operator was registered with no quarantined "
        "proposal, so its prompt change would never face qualification"
    ),
    "PROPOSAL_MALFORMED": (
        "the mutation proposal does not satisfy its canonical schema, so the "
        "quarantine workflow would be reasoning about an unvalidated document"
    ),
    "PROPOSAL_NOT_APPLICABLE": (
        "a prompt mutation proposal was supplied for an operator that touches "
        "no prompt genome, which claims a qualification it never needed"
    ),
    "QUALIFICATION_EVIDENCE_MISSING": (
        "the activation binds no qualification evidence, so the release from "
        "quarantine would rest on an assertion rather than on artifacts"
    ),
    "RETROACTIVE_ACTIVATION": (
        "the proposal would be applied to the run that produced it, which is "
        "how a run rewrites the judgments it has already received"
    ),
    "RISK_ANALYSIS_MISSING": (
        "the change declares no risk analysis, and a prompt shapes what a "
        "generator sees, so an unanalyzed change is an unbounded one"
    ),
    "SEARCH_SPACE_DRIFT": (
        "the sealed C05 mutable search space cannot be read or no longer lists "
        "the genome kind this package governs, so it refuses categorically"
    ),
    "STATUS_CONTRACT_DRIFT": (
        "a canonical status vocabulary no longer declares the positions this "
        "package selects, so quarantined and active could not be told apart"
    ),
    "WORKFLOW_CONTRACT_DRIFT": (
        "the governance workflow no longer declares the retroactivity node "
        "this activation mirrors, so the verdict would mirror nothing"
    ),
}

#: Canonical schema names.  These are schema *names*, not wire vocabulary.
PROMPT_GENOME_KIND = "prompt-genome"
OPERATOR_SPEC_KIND = "mutation-operator-spec"
PROMPT_PROPOSAL_KIND = "prompt-mutation-proposal"

#: Fields read back out of the canonical schemas rather than trusted.
STATUS_FIELD = "status"
IDENTITY_FIELD = "prompt_genome_id"
VERSION_FIELD = "version"
TEMPLATE_FIELD = "template"
TASK_CLASS_FIELD = "task_class"
CONTEXT_CLASSES_FIELD = "allowed_context_classes"
FORBIDDEN_AUTHORITIES_FIELD = "forbidden_authorities"
FITNESS_HISTORY_FIELD = "fitness_history_ids"
PARENT_PROMPTS_FIELD = "parent_prompt_ids"
PROMPT_HASH_FIELD = "prompt_hash"

#: Operator specification fields.
OPERATOR_ID_FIELD = "operator_id"
OPERATOR_CLASS_FIELD = "operator_class"
INPUT_KINDS_FIELD = "input_genome_types"
OUTPUT_KIND_FIELD = "output_genome_type"
PROMPT_REF_FIELD = "prompt_ref"
RISK_CLASS_FIELD = "risk_class"

#: Proposal fields.
PROPOSAL_ID_FIELD = "proposal_id"
PROPOSAL_HASH_FIELD = "proposal_hash"
SOURCE_PROMPT_FIELD = "source_prompt_genome_id"
PROPOSED_PROMPT_FIELD = "proposed_prompt_genome_id"

#: A prompt genome is born at the first declared status and is active at the
#: third.  Both assumptions are verified against the quarantine module's own
#: inert set on every read; neither value is held here.
QUARANTINED_POSITION = 0
ACTIVE_POSITION = 2

#: The first version of a genome that descends from no prompt.
FIRST_VERSION = 1


class MutationOperatorError(ValueError):
    """A registration, prompt change or activation would breach a contract."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise MutationOperatorError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise MutationOperatorError(code, message, context)


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def require_sealed_digest(
    document: Mapping[str, Any], hash_field: str, label: str
) -> str:
    """Refuse a document whose own digest does not re-derive from its fields.

    Every canonical record that carries a `*_hash` derives it over itself with
    that field removed, so a status flipped in place without re-sealing is
    visible here.  It is not proof of authorship — it is proof that the
    document and its digest are at least the same document.
    """
    claimed = document.get(hash_field)
    derived = hash_excluding(dict(document), hash_field)
    if claimed != derived:
        _fail(
            "DIGEST_NOT_RE_DERIVABLE",
            f"the {label} digest does not re-derive from its own fields",
            {"claimed": claimed, "derived": derived, "label": label},
        )
    return derived


def mutable_genome_kinds() -> tuple[str, ...]:
    """The genome kinds the sealed C05 index permits mutating, as schema names.

    Composed from the I05 intake, which already reads the sealed family index:
    a second reader here would be a second place the governance boundary could
    be interpreted, and the whole point of the seal is that there is one.
    """
    try:
        return _sealed_search_space()
    except GenomeIntakeError as error:
        _fail(
            "SEARCH_SPACE_DRIFT",
            "the sealed mutable search space could not be read",
            {"code": error.code, "detail": str(error)},
        )
        return ()


def mutable_prompt_genome_kind() -> str:
    """The prompt genome kind, refused if the seal no longer covers it.

    Fail-closed: if C05 ever seals a search space without prompt genomes, this
    package stops registering prompt-affecting operators rather than governing
    a kind that may no longer be evolved at all.
    """
    kinds = mutable_genome_kinds()
    if PROMPT_GENOME_KIND not in kinds:
        _fail(
            "SEARCH_SPACE_DRIFT",
            f"{PROMPT_GENOME_KIND} is not in the sealed mutable search space",
            {"genome_kind": PROMPT_GENOME_KIND, "mutable_search_space": list(kinds)},
        )
    return PROMPT_GENOME_KIND


def operator_contract() -> dict[str, Any]:
    """The canonical mutation-operator schema, with the read fields verified.

    The field names are read back out of the schema instead of trusted, so a
    rename in the contract fails here rather than leaving a registry that
    silently types nothing.
    """
    return _contract_with_fields(
        OPERATOR_SPEC_KIND,
        (
            OPERATOR_ID_FIELD,
            OPERATOR_CLASS_FIELD,
            INPUT_KINDS_FIELD,
            OUTPUT_KIND_FIELD,
            PROMPT_REF_FIELD,
            RISK_CLASS_FIELD,
            VERSION_FIELD,
        ),
    )


def prompt_genome_contract() -> dict[str, Any]:
    """The canonical prompt genome schema, with every written field verified."""
    return _contract_with_fields(
        PROMPT_GENOME_KIND,
        (
            IDENTITY_FIELD,
            VERSION_FIELD,
            TASK_CLASS_FIELD,
            TEMPLATE_FIELD,
            CONTEXT_CLASSES_FIELD,
            FORBIDDEN_AUTHORITIES_FIELD,
            FITNESS_HISTORY_FIELD,
            PARENT_PROMPTS_FIELD,
            STATUS_FIELD,
            PROMPT_HASH_FIELD,
        ),
    )


def prompt_proposal_contract() -> dict[str, Any]:
    """The canonical prompt mutation proposal schema, with its read fields."""
    return _contract_with_fields(
        PROMPT_PROPOSAL_KIND,
        (PROPOSAL_ID_FIELD, SOURCE_PROMPT_FIELD, PROPOSED_PROMPT_FIELD, STATUS_FIELD),
    )


def _contract_with_fields(kind: str, fields: tuple[str, ...]) -> dict[str, Any]:
    """A canonical document whose declared properties still cover `fields`.

    Membership is checked against the declared *properties* rather than the
    schema's own required list, because the word naming that list is itself a
    canonical enum value elsewhere and EF4-I22 forbids holding it here.  The
    schema-and-type suite separately asserts that these fields are in fact
    required by their schemas.
    """
    document = default_registry().document(kind)
    declared = set(document.get("properties") or ())
    missing = sorted(set(fields) - declared)
    if missing:
        code = {
            PROMPT_GENOME_KIND: "PROMPT_GENOME_CONTRACT_DRIFT",
            OPERATOR_SPEC_KIND: "OPERATOR_CONTRACT_DRIFT",
        }.get(kind, "STATUS_CONTRACT_DRIFT")
        _fail(
            code,
            f"the canonical {kind} schema no longer declares every read field",
            {"missing": missing, "schema": kind},
        )
    return document


def _status_vocabulary(kind: str) -> tuple[str, ...]:
    document = _contract_with_fields(kind, (STATUS_FIELD,))
    declared = document["properties"][STATUS_FIELD].get("enum")
    if not isinstance(declared, list) or not declared:
        _fail(
            "STATUS_CONTRACT_DRIFT",
            f"the canonical {kind} schema declares no status vocabulary",
            {"schema": kind},
        )
    return tuple(str(value) for value in declared)  # type: ignore[union-attr]


def prompt_status_vocabulary() -> tuple[str, ...]:
    """The prompt genome status vocabulary, in the order the schema declares."""
    return _status_vocabulary(PROMPT_GENOME_KIND)


def proposal_status_vocabulary() -> tuple[str, ...]:
    """The proposal status vocabulary, verified against the quarantine's own set.

    The quarantine module owns which statuses are inert.  If its set ever names
    a status the canonical schema does not declare, the two have drifted and
    every judgment built on either one is unsafe.
    """
    vocabulary = _status_vocabulary(PROMPT_PROPOSAL_KIND)
    unknown = sorted(INERT_STATUSES - set(vocabulary))
    if unknown:
        _fail(
            "STATUS_CONTRACT_DRIFT",
            "the quarantine's inert statuses are not all declared by the schema",
            {"schema": PROMPT_PROPOSAL_KIND, "undeclared": unknown},
        )
    return vocabulary


def quarantined_prompt_status() -> str:
    """The status a prompt genome is born into, verified to be inert.

    Selected positionally and then checked against the quarantine module's own
    inert set: a genome born into a status that could influence a run would
    make construction itself an activation.
    """
    vocabulary = prompt_status_vocabulary()
    if len(vocabulary) <= ACTIVE_POSITION:
        _fail(
            "STATUS_CONTRACT_DRIFT",
            "the prompt status vocabulary is shorter than the declared positions",
            {"declared": list(vocabulary)},
        )
    status = vocabulary[QUARANTINED_POSITION]
    if status not in INERT_STATUSES:
        _fail(
            "STATUS_CONTRACT_DRIFT",
            "the first declared prompt status is not one the quarantine holds inert",
            {"declared": list(vocabulary)},
        )
    return status


def active_prompt_status() -> str:
    """The status at which a prompt genome is on a run's active surface.

    Selected positionally and refused if it is a status the quarantine treats
    as inert, because that would make the active surface unreachable by
    definition and hide every gate this package runs.
    """
    vocabulary = prompt_status_vocabulary()
    quarantined_prompt_status()
    status = vocabulary[ACTIVE_POSITION]
    if status in INERT_STATUSES:
        _fail(
            "STATUS_CONTRACT_DRIFT",
            "the declared active prompt status is one the quarantine holds inert",
            {"declared": list(vocabulary)},
        )
    return status
