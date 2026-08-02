"""The typed mutation-operator registry.

An evolution run is only auditable if the operators it applied are identifiable
afterwards, and an operator id is only identifying if exactly one operator ever
claims it.  So registration is where three boundaries are held at once.

First, membership: an operator may only be registered for a genome kind inside
the sealed C05 mutable search space, in *both* directions — what it reads and
what it produces.  An operator that outputs something outside the space would
manufacture candidates the archive has no contract for, and one that reads
outside it would let material the search may not touch flow into material it
may.  Second, identity: a second operator claiming a registered id is refused
rather than overwriting, because a lineage naming that id would otherwise be
ambiguous about which code produced the candidate.  Third, typing: an operator
declares its parameters as schema fragments, and arguments are bound against
those fragments rather than passed through, so "typed registry" means the
registry can actually refuse a wrong argument.

Prompt-affecting operators carry a fourth boundary.  An operator whose input or
output is a prompt genome edits the instructions a generator receives, which
EF4-I55 puts inside quarantine: registering one requires a prompt mutation
proposal built by the governance quarantine module, and claiming that operator
as active goes through the S05 inert-mutations gate, which in turn asks the
quarantine module whether the proposal may influence a run at all.  Nothing
here decides that question; it is asked of the surfaces that own it.

No clock and no randomness: an operator brings its own id, inputs are copied
rather than mutated, and every record re-derives its own digest.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ...contracts import ContractViolation, validate_artifact
from ...domain.hashing import hash_excluding, sha256_of_payload
from ...governance.quarantine import may_influence_run
from ...security.v4_s05 import ThreatControlError, require_inert_mutations
from .declarations import (
    INPUT_KINDS_FIELD,
    OPERATOR_CLASS_FIELD,
    OPERATOR_ID_FIELD,
    OPERATOR_SPEC_KIND,
    OUTPUT_KIND_FIELD,
    PROMPT_PROPOSAL_KIND,
    PROPOSAL_HASH_FIELD,
    PROPOSAL_ID_FIELD,
    PROPOSED_PROMPT_FIELD,
    RISK_CLASS_FIELD,
    SOURCE_PROMPT_FIELD,
    STATUS_FIELD,
    VERSION_FIELD,
    _fail,
    _require_mapping,
    _require_text,
    mutable_genome_kinds,
    mutable_prompt_genome_kind,
    operator_contract,
    prompt_proposal_contract,
    proposal_status_vocabulary,
    require_sealed_digest,
)

__all__ = ["MutationOperatorRegistry", "operator_genome_kinds"]


def operator_genome_kinds(spec: Mapping[str, Any]) -> tuple[str, ...]:
    """Every genome kind an operator declares, read and written alike.

    Derived from the specification's own declared types rather than accepted as
    a separate argument: a caller able to declare a kind beside the spec could
    register an operator whose contract says one thing and whose registration
    says another.
    """
    document = _require_mapping(spec, "spec")
    declared = [str(document.get(OUTPUT_KIND_FIELD) or "")]
    inputs = document.get(INPUT_KINDS_FIELD)
    if isinstance(inputs, Sequence) and not isinstance(inputs, (str, bytes)):
        declared.extend(str(item) for item in inputs)
    return tuple(sorted({kind for kind in declared if kind}))


class MutationOperatorRegistry:
    """Registered operators, their parameter contracts and quarantine status.

    The registry is a record keeper, not an executor: it never applies an
    operator, scores one, or decides that a prompt change is safe.  It refuses
    registrations that would make later attribution impossible and refuses
    activation claims the quarantine has not released.
    """

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._parameters: dict[str, dict[str, Any]] = {}
        self._proposals: dict[str, dict[str, Any]] = {}

    def operator_ids(self) -> tuple[str, ...]:
        """Registered ids, sorted, so the registry reads the same every time."""
        return tuple(sorted(self._records))

    def record(self, operator_id: str) -> dict[str, Any]:
        """One registration record, copied so a caller cannot edit the registry."""
        identifier = _require_text(operator_id, OPERATOR_ID_FIELD)
        if identifier not in self._records:
            _fail(
                "OPERATOR_UNREGISTERED",
                f"no operator is registered under {identifier}",
                {
                    OPERATOR_ID_FIELD: identifier,
                    "registered": list(self.operator_ids()),
                },
            )
        return dict(self._records[identifier])

    def records(self) -> tuple[dict[str, Any], ...]:
        """Every record, in id order."""
        return tuple(dict(self._records[key]) for key in self.operator_ids())

    def parameter_contract(self, operator_id: str) -> dict[str, Any]:
        """The parameter fragments an operator declared, copied."""
        self.record(operator_id)
        return {
            name: dict(fragment)
            for name, fragment in self._parameters[str(operator_id)].items()
        }

    def proposal(self, operator_id: str) -> dict[str, Any] | None:
        """The quarantined proposal a prompt-affecting operator was registered with."""
        self.record(operator_id)
        held = self._proposals.get(str(operator_id))
        return None if held is None else dict(held)

    def registry_hash(self) -> str:
        """A digest over every record, so two registries can be compared exactly."""
        return sha256_of_payload(list(self.records()))

    def register(
        self,
        *,
        spec: Mapping[str, Any],
        declared_parameters: Mapping[str, Any],
        proposal: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register one operator, or refuse without changing the registry.

        Every refusal happens before anything is stored, so a rejected
        registration leaves no half-registered operator behind for a later
        lookup to find.
        """
        operator_contract()
        document = dict(_require_mapping(spec, "spec"))
        try:
            validate_artifact(OPERATOR_SPEC_KIND, document)
        except ContractViolation as error:
            _fail(
                "OPERATOR_SPEC_MALFORMED",
                "the operator specification does not satisfy its canonical schema",
                {"schema_errors": list(error.errors)},
            )

        identifier = _require_text(document.get(OPERATOR_ID_FIELD), OPERATOR_ID_FIELD)
        if identifier in self._records:
            _fail(
                "OPERATOR_ID_DUPLICATED",
                f"operator id {identifier} is already registered",
                {
                    OPERATOR_ID_FIELD: identifier,
                    "registered_hash": self._records[identifier]["record_hash"],
                },
            )

        kinds = operator_genome_kinds(document)
        sealed = mutable_genome_kinds()
        outside = sorted(set(kinds) - set(sealed))
        if outside:
            _fail(
                "OPERATOR_KIND_OUTSIDE_SEARCH_SPACE",
                "the operator declares genome kinds outside the sealed search space",
                {
                    OPERATOR_ID_FIELD: identifier,
                    "mutable_search_space": list(sealed),
                    "outside": outside,
                },
            )

        parameters = self._validated_parameters(declared_parameters, identifier)
        prompt_affecting = mutable_prompt_genome_kind() in kinds
        held_proposal = self._validated_proposal(proposal, prompt_affecting, identifier)

        record: dict[str, Any] = {
            "declared_parameter_names": sorted(parameters),
            "genome_kinds": list(kinds),
            OPERATOR_CLASS_FIELD: str(document[OPERATOR_CLASS_FIELD]),
            OPERATOR_ID_FIELD: identifier,
            "output_genome_kind": str(document[OUTPUT_KIND_FIELD]),
            "parameter_contract_hash": sha256_of_payload(parameters),
            "prompt_affecting": prompt_affecting,
            PROPOSAL_ID_FIELD: (
                None if held_proposal is None else str(held_proposal[PROPOSAL_ID_FIELD])
            ),
            "quarantine_inert": (
                None if held_proposal is None else not may_influence_run(held_proposal)
            ),
            "quarantine_status": (
                None if held_proposal is None else str(held_proposal[STATUS_FIELD])
            ),
            RISK_CLASS_FIELD: str(document[RISK_CLASS_FIELD]),
            "spec_hash": sha256_of_payload(document),
            VERSION_FIELD: str(document[VERSION_FIELD]),
        }
        record["record_hash"] = hash_excluding(record, "record_hash")

        self._records[identifier] = record
        self._parameters[identifier] = parameters
        if held_proposal is not None:
            self._proposals[identifier] = held_proposal
        return dict(record)

    def _validated_parameters(
        self, declared_parameters: Mapping[str, Any], operator_id: str
    ) -> dict[str, Any]:
        """The declared parameter fragments, each proven to be a usable schema.

        An empty declaration is accepted and means exactly what it says: the
        operator takes no parameters, and binding any argument to it will be
        refused.  What is not accepted is a fragment that could never validate
        anything, because that advertises a type contract the registry cannot
        enforce.
        """
        declared = _require_mapping(declared_parameters, "declared_parameters")
        contract: dict[str, Any] = {}
        for name in sorted(map(str, declared)):
            fragment = declared[name]
            if not name.strip():
                _fail(
                    "PARAMETER_SCHEMA_MALFORMED",
                    "a declared parameter has no name",
                    {OPERATOR_ID_FIELD: operator_id},
                )
            if not isinstance(fragment, Mapping) or not fragment:
                _fail(
                    "PARAMETER_SCHEMA_MALFORMED",
                    f"parameter {name} declares no schema fragment",
                    {OPERATOR_ID_FIELD: operator_id, "parameter": name},
                )
            try:
                Draft202012Validator.check_schema(dict(fragment))
            except SchemaError as error:
                _fail(
                    "PARAMETER_SCHEMA_MALFORMED",
                    f"parameter {name} is not a usable schema fragment",
                    {
                        OPERATOR_ID_FIELD: operator_id,
                        "detail": error.message,
                        "parameter": name,
                    },
                )
            contract[name] = dict(fragment)
        return contract

    def _validated_proposal(
        self,
        proposal: Mapping[str, Any] | None,
        prompt_affecting: bool,
        operator_id: str,
    ) -> dict[str, Any] | None:
        """The quarantine proposal a prompt-affecting operator must arrive with."""
        if proposal is None:
            if prompt_affecting:
                _fail(
                    "PROMPT_MUTATION_UNPROPOSED",
                    "a prompt-affecting operator needs a quarantined proposal",
                    {OPERATOR_ID_FIELD: operator_id},
                )
            return None
        if not prompt_affecting:
            _fail(
                "PROPOSAL_NOT_APPLICABLE",
                "this operator touches no prompt genome, so no proposal applies",
                {OPERATOR_ID_FIELD: operator_id},
            )
        document = dict(_require_mapping(proposal, "proposal"))
        prompt_proposal_contract()
        proposal_status_vocabulary()
        try:
            validate_artifact(PROMPT_PROPOSAL_KIND, document)
        except ContractViolation as error:
            _fail(
                "PROPOSAL_MALFORMED",
                "the prompt mutation proposal does not satisfy its canonical schema",
                {OPERATOR_ID_FIELD: operator_id, "schema_errors": list(error.errors)},
            )
        require_sealed_digest(document, PROPOSAL_HASH_FIELD, PROMPT_PROPOSAL_KIND)
        return document

    def bind_parameters(
        self, operator_id: str, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Bind arguments to an operator's declared parameters, or refuse.

        Missing and undeclared names are reported together with every value
        error, so a caller fixing a call sees the whole gap in one pass instead
        of rediscovering the next problem after each repair.
        """
        record = self.record(operator_id)
        contract = self._parameters[str(operator_id)]
        supplied = dict(_require_mapping(arguments, "arguments"))

        missing = sorted(set(contract) - set(supplied))
        undeclared = sorted(set(supplied) - set(contract))
        errors: list[str] = []
        for name in sorted(set(contract) & set(supplied)):
            validator = Draft202012Validator(contract[name])
            errors.extend(
                f"{name}: {failure.message}"
                for failure in validator.iter_errors(supplied[name])
            )
        if missing or undeclared or errors:
            _fail(
                "PARAMETER_CONTRACT_VIOLATED",
                "the arguments do not satisfy the operator's declared parameters",
                {
                    OPERATOR_ID_FIELD: str(operator_id),
                    "missing": missing,
                    "undeclared": undeclared,
                    "value_errors": sorted(errors),
                },
            )

        binding: dict[str, Any] = {
            "arguments": dict(sorted(supplied.items())),
            OPERATOR_ID_FIELD: str(operator_id),
            "parameter_contract_hash": record["parameter_contract_hash"],
        }
        binding["binding_hash"] = hash_excluding(binding, "binding_hash")
        return binding

    def claim_active_prompt_operator(
        self, operator_id: str, *, target_run_id: str
    ) -> dict[str, Any]:
        """Claim a prompt-affecting operator as active on a run, or refuse.

        The refusal is not decided here.  The claim is handed to the S05
        inert-mutations gate with the proposed genome named as the run's active
        prompt surface; that gate asks the quarantine module whether the
        proposal may influence a run, and an unreleased proposal makes the
        claim an activation without qualification.
        """
        record = self.record(operator_id)
        run = _require_text(target_run_id, "target_run_id")
        proposal = self._proposals.get(str(operator_id))
        if proposal is None:
            _fail(
                "PROPOSAL_NOT_APPLICABLE",
                "only a prompt-affecting operator is claimed through the gate",
                {OPERATOR_ID_FIELD: str(operator_id)},
            )
            return {}

        activated = str(proposal[PROPOSED_PROMPT_FIELD])
        try:
            gate = require_inert_mutations(
                target_run_id=run,
                active_prompt_genome_ids=(activated,),
                proposals=(dict(proposal),),
            )
        except ThreatControlError as error:
            _fail(
                "PROMPT_MUTATION_INERT",
                str(error),
                {
                    OPERATOR_ID_FIELD: str(operator_id),
                    "gate_code": error.code,
                    PROPOSED_PROMPT_FIELD: activated,
                },
            )
            return {}

        claim: dict[str, Any] = {
            "active_prompt_genome_id": activated,
            "gate": dict(gate),
            OPERATOR_ID_FIELD: str(operator_id),
            PROPOSAL_ID_FIELD: str(proposal[PROPOSAL_ID_FIELD]),
            "quarantine_status": str(proposal[STATUS_FIELD]),
            "record_hash": record["record_hash"],
            SOURCE_PROMPT_FIELD: str(proposal[SOURCE_PROMPT_FIELD]),
            "target_run_id": run,
        }
        claim["claim_hash"] = hash_excluding(claim, "claim_hash")
        return claim
