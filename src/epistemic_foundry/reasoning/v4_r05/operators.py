"""Scientific mutation, typed crossover, mechanism and Aporia operators.

Evolution proposes variants of a hypothesis.  What separates a *scientific*
variant from a random edit is that the variant stays accountable to the same
contract as its parent: it touches only genes the operator declared, it leaves
identity, lineage and authority alone, and it can be re-derived byte for byte
from the parent plus the operator plus the caller's identifiers.  This module
is that discipline expressed as a typed registry.

Each operator declares three things and invents none of them.  Its **genome
kind** is a kind the sealed C05 family index still lists as mutable, read
through the I05 intake surface that already owns that boundary.  Its **gene
fields** are verified to be properties of that genome's own canonical schema,
so an operator cannot claim a gene the contract does not declare.  Its
**epistemic mode** is one of the two edge partitions the Aporia Engine declares
over the canonical argument graph — the strict edges, whose conclusion follows
from its premise, and the defeasible ones, whose support can be defeated.  A
copy of any of those vocabularies here would be a second source that drifts
(EF4-I22), so each is imported or read rather than restated.

Four refusals carry the weight.  A mutation touching a field the operator never
declared is refused, because an operator that edits more than it admits cannot
be reviewed for what it actually does.  A mutation touching identity, lineage
or authority is refused by path — the Evolution Chamber already owns that
boundary and this module composes its check rather than repeating it, so a
candidate can never rewrite the rules it is judged by or forge its own descent.
A typed crossover is refused unless both parents resolve to the same genome
kind and their mechanisms agree, derived from the genomes' own mechanism field
rather than from the compatibility report, because a report that says otherwise
would splice a child asserting a mechanism neither parent's evidence supports.
And an Aporia operator is refused unless it cites a question a real argument
graph leaves open, since answering a contradiction nobody recorded is not an
answer.

Every application produces a child *and* the lineage that explains it: parents
recorded, generation exactly one above the deepest parent, ancestry accumulated,
and the whole record re-derivable from its own published fields.  There is no
clock and no random draw: the caller supplies timestamps and identifiers, and
`new_id` runs only when the caller declines to name the child.  Nothing here
scores, selects, promotes or evaluates anything, and inputs are never mutated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ...aporia_engine.argument import (
    DEFEASIBLE_EDGE_TYPES,
    STRICT_EDGE_TYPES,
    is_resolved,
    open_questions,
)
from ...contracts import ContractViolation, default_registry, validate_artifact
from ...domain.hashing import hash_excluding, sha256_of_payload
from ...domain.ids import new_id
from ...evolution_chamber.crossover import crossover_permitted
from ...evolution_chamber.mutation import (
    FORBIDDEN_MUTATION_PATHS,
    AuthorityMutationRefused,
    apply_mutation,
)
from ...intake.v4_i05 import mutable_genome_kinds
from ...intake.v4_i05 import screening as intake

#: Every way this module refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "APORIA_CITATION_MALFORMED": (
        "the cited contradiction is not the argument-graph shape the Aporia "
        "Engine publishes, so nothing verifiable was actually cited"
    ),
    "APORIA_CITATION_MISSING": (
        "the operator answers a recorded contradiction, and applying it with "
        "no citation would let any edit be presented as a resolution"
    ),
    "APORIA_CITATION_NOT_OPEN": (
        "the cited question is not open in that argument graph, so the child "
        "would claim to answer something the graph never left unanswered"
    ),
    "APORIA_CITATION_SUBJECT_MISMATCH": (
        "the cited argument graph reasons about a different hypothesis, so its "
        "open questions say nothing about the genome being mutated"
    ),
    "AUTHORITY_FIELD_TOUCHED": (
        "the edit reaches a field carrying evaluator, holdout, policy or "
        "promotion authority, and evolution may propose but never certify"
    ),
    "CHILD_CONTRACT_VIOLATED": (
        "the produced child does not satisfy its own canonical genome schema, "
        "so the operator manufactured a candidate no contract admits"
    ),
    "CROSSOVER_KIND_MISMATCH": (
        "the two parents do not resolve to the one genome kind this operator "
        "splices, and a cross-kind child has no contract either parent met"
    ),
    "CROSSOVER_NOT_PERMITTED": (
        "the compatibility report is not an unconditional allow, and an "
        "unassessed or repair-pending axis is not permission to splice"
    ),
    "CROSSOVER_REPORT_MISMATCH": (
        "the compatibility report does not name both parents, so it assessed "
        "some other pair and says nothing at all about this splice"
    ),
    "GENE_FIELD_UNDECLARED_BY_SCHEMA": (
        "an operator declares a gene the canonical genome schema does not "
        "declare, so the registry would authorize editing a field that is gone"
    ),
    "IDENTITY_FIELD_IMMUTABLE": (
        "the edit renames the candidate itself, and a child that reuses or "
        "chooses its own identity makes its descent unreadable"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this module requires, and continuing would "
        "record a child derived from something it never validated"
    ),
    "LINEAGE_CONTRACT_VIOLATED": (
        "the lineage produced or supplied does not satisfy the canonical "
        "lineage schema, so the descent record could not be replayed"
    ),
    "LINEAGE_FIELD_IMMUTABLE": (
        "the edit rewrites the line the candidate descends from, which would "
        "let a candidate adopt an ancestry it never actually had"
    ),
    "MECHANISM_FIELD_UNDECLARED": (
        "this genome kind declares no mechanism field, so mechanism agreement "
        "cannot be derived and a typed crossover refuses rather than guesses"
    ),
    "MECHANISM_INCOMPATIBLE": (
        "the parents propose different mechanisms, and splicing them yields a "
        "child asserting a mechanism neither parent's evidence supports"
    ),
    "MUTATION_EMPTY": (
        "the edit changes no gene the operator declared, and recording it as a "
        "mutation would inflate the population with a renamed copy"
    ),
    "OPERATOR_ARITY_MISMATCH": (
        "the operator was applied through the wrong surface, and a splice and "
        "a single-parent edit do not produce the same kind of descent record"
    ),
    "OPERATOR_KIND_OUTSIDE_SEARCH_SPACE": (
        "the operator targets a genome kind the sealed C05 index no longer "
        "lists as mutable, and the search space is a governance boundary"
    ),
    "OPERATOR_MODE_UNDECLARED": (
        "the operator declares an epistemic mode that is not one of the Aporia "
        "Engine's own edge partitions, so its inference strength is unstated"
    ),
    "OPERATOR_UNKNOWN": (
        "no declared operator carries that identifier, and applying an unknown "
        "operator would place an unreviewed edit into the lineage"
    ),
    "PARENT_CONTRACT_VIOLATED": (
        "the parent does not satisfy its own canonical genome schema, so any "
        "child derived from it would inherit a shape no contract admits"
    ),
    "PARENT_LINEAGE_MISMATCH": (
        "the supplied lineage does not describe the supplied parent, so the "
        "child's generation and ancestry would be counted from the wrong line"
    ),
    "STRICT_INFERENCE_VIOLATED": (
        "the operator declares a strict mode, but the child asserts content "
        "the parent does not contain, which is defeasible support not proof"
    ),
    "UNDECLARED_FIELD_TOUCHED": (
        "the edit reaches a gene this operator never declared, and an operator "
        "that edits more than it admits cannot be reviewed for what it does"
    ),
}

#: The canonical contract names this module reads.  These are schema *names*
#: rather than wire vocabulary, and each one is verified before use.
LINEAGE_KIND = intake.LINEAGE_KIND
ARGUMENT_KIND = "argument-graph"
CHALLENGE_KIND = "challenge-genome"
EXPERIMENT_KIND = "experiment-genome"

#: The genome schema key whose contents bound what an operator may declare.
PROPERTY_KEY = "properties"

#: The two epistemic modes, taken from the Aporia Engine's own partition of the
#: canonical argument-graph edge types.  A strict edge asserts that its
#: conclusion follows; a defeasible one asserts support that can be defeated.
STRICT_MODE = STRICT_EDGE_TYPES
DEFEASIBLE_MODE = DEFEASIBLE_EDGE_TYPES
EPISTEMIC_MODES: tuple[frozenset[str], ...] = (STRICT_MODE, DEFEASIBLE_MODE)

#: Aporia citation envelope keys and the graph field naming its subject.
GRAPH_KEY = "argument_graph"
OPEN_QUESTION_KEY = "open_question_ids"
GRAPH_SUBJECT_FIELD = "hypothesis_id"
GRAPH_IDENTITY_FIELD = "argument_graph_id"

#: Compatibility report fields this module reads back rather than trusts.
REPORT_PARENTS_FIELD = "candidate_ids"
REPORT_IDENTITY_FIELD = "report_id"

#: Lineage record fields.
CANDIDATE_FIELD = "candidate_id"
GENERATION_FIELD = "generation"
ISLAND_FIELD = "island_id"
ANCESTOR_FIELD = "ancestor_hashes"
PARENTS_FIELD = "parent_ids"
SPLICE_PARENTS_FIELD = "crossover_parent_ids"
INSPIRATION_FIELD = "inspiration_ids"
OPERATORS_FIELD = "mutation_operator_ids"

#: Genome fields the engine owns rather than the operator: a child names itself,
#: counts its own revision and carries the caller's timestamp.
REVISION_FIELD = "revision"
STAMP_FIELD = "created_at"

#: One generation, and one revision, per application.
GENERATION_STEP = 1


class MutationOperatorError(ValueError):
    """An operator application would corrupt a candidate, a lineage or a gate."""

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


def _require_sequence(value: object, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        _fail("INPUT_INVALID", f"{label} must be a sequence", {"label": label})
    return value  # type: ignore[return-value]


@dataclass(frozen=True)
class GenomeKindContract:
    """What a genome kind calls its identity, its line and its mechanism.

    Every field named here is verified to be a property of that kind's own
    canonical schema before the registry will hand out an operator for it, so a
    schema rename closes the door instead of silently editing nothing.
    """

    genome_kind: str
    identity_field: str
    id_prefix: str
    mechanism_field: str | None
    lineage_field: str | None
    revision_field: str | None
    stamp_field: str | None


@dataclass(frozen=True)
class ScientificOperator:
    """One typed operator: a kind, the genes it may touch, and its mode."""

    operator_id: str
    genome_kind: str
    gene_fields: tuple[str, ...]
    epistemic_mode: frozenset[str]
    aporia_grounded: bool = False
    splices_parents: bool = False


#: The genome kinds this module operates on.  `prompt-genome` is inside the
#: sealed search space and is deliberately absent: a co-evolved mutation prompt
#: has to be qualified in quarantine before it may be applied at all, so R05
#: declares no operator that would edit one on the ordinary path.
_KIND_CONTRACTS: tuple[GenomeKindContract, ...] = (
    GenomeKindContract(
        genome_kind=intake.GENOME_KIND,
        identity_field=intake.IDENTITY_FIELD,
        id_prefix="HG",
        mechanism_field=intake.MECHANISM_FIELD,
        lineage_field=intake.LINEAGE_FIELD,
        revision_field=REVISION_FIELD,
        stamp_field=STAMP_FIELD,
    ),
    GenomeKindContract(
        genome_kind=CHALLENGE_KIND,
        identity_field="challenge_genome_id",
        id_prefix="CG",
        mechanism_field=None,
        lineage_field=intake.LINEAGE_FIELD,
        revision_field=None,
        stamp_field=None,
    ),
    GenomeKindContract(
        genome_kind=EXPERIMENT_KIND,
        identity_field="experiment_genome_id",
        id_prefix="EG",
        mechanism_field=None,
        lineage_field=None,
        revision_field=None,
        stamp_field=None,
    ),
)

#: The declared operators.  Each one names genes of exactly one kind; the
#: registry refuses to publish any of them until the schema agrees.
_OPERATORS: tuple[ScientificOperator, ...] = (
    ScientificOperator(
        operator_id="mechanism-refinement",
        genome_kind=intake.GENOME_KIND,
        gene_fields=(intake.MECHANISM_FIELD,),
        epistemic_mode=DEFEASIBLE_MODE,
    ),
    ScientificOperator(
        operator_id="scope-respecification",
        genome_kind=intake.GENOME_KIND,
        gene_fields=(intake.SCOPE_FIELD,),
        epistemic_mode=DEFEASIBLE_MODE,
    ),
    ScientificOperator(
        operator_id="prediction-extension",
        genome_kind=intake.GENOME_KIND,
        gene_fields=("prediction_gene_ids",),
        epistemic_mode=DEFEASIBLE_MODE,
    ),
    ScientificOperator(
        operator_id="prediction-restriction",
        genome_kind=intake.GENOME_KIND,
        gene_fields=("prediction_gene_ids",),
        epistemic_mode=STRICT_MODE,
    ),
    ScientificOperator(
        operator_id="falsifier-strengthening",
        genome_kind=intake.GENOME_KIND,
        gene_fields=(intake.FALSIFIER_FIELD,),
        epistemic_mode=DEFEASIBLE_MODE,
    ),
    ScientificOperator(
        operator_id="alternative-widening",
        genome_kind=intake.GENOME_KIND,
        gene_fields=("alternative_hypothesis_ids",),
        epistemic_mode=DEFEASIBLE_MODE,
    ),
    ScientificOperator(
        operator_id="measurement-retyping",
        genome_kind=intake.GENOME_KIND,
        gene_fields=("measurement_contract_ids",),
        epistemic_mode=DEFEASIBLE_MODE,
    ),
    ScientificOperator(
        operator_id="budget-simplification",
        genome_kind=intake.GENOME_KIND,
        gene_fields=("complexity_budget",),
        epistemic_mode=STRICT_MODE,
    ),
    ScientificOperator(
        operator_id="aporia-response",
        genome_kind=intake.GENOME_KIND,
        gene_fields=("alternative_hypothesis_ids", "uncertainty_notes"),
        epistemic_mode=DEFEASIBLE_MODE,
        aporia_grounded=True,
    ),
    ScientificOperator(
        operator_id="mechanism-preserving-splice",
        genome_kind=intake.GENOME_KIND,
        gene_fields=(
            "canonical_claim",
            "alternative_hypothesis_ids",
            intake.FALSIFIER_FIELD,
            "measurement_contract_ids",
            "prediction_gene_ids",
            "uncertainty_notes",
        ),
        epistemic_mode=DEFEASIBLE_MODE,
        splices_parents=True,
    ),
    ScientificOperator(
        operator_id="challenge-construction",
        genome_kind=CHALLENGE_KIND,
        gene_fields=("construction", "success_criterion"),
        epistemic_mode=DEFEASIBLE_MODE,
    ),
    ScientificOperator(
        operator_id="challenge-retargeting",
        genome_kind=CHALLENGE_KIND,
        gene_fields=("target_genome_id",),
        epistemic_mode=DEFEASIBLE_MODE,
    ),
    ScientificOperator(
        operator_id="design-comparator",
        genome_kind=EXPERIMENT_KIND,
        gene_fields=("comparator", "controls"),
        epistemic_mode=DEFEASIBLE_MODE,
    ),
    ScientificOperator(
        operator_id="design-outcome-extension",
        genome_kind=EXPERIMENT_KIND,
        gene_fields=("outcomes",),
        epistemic_mode=DEFEASIBLE_MODE,
    ),
)


def genome_properties(genome_kind: str) -> dict[str, Any]:
    """The properties the named canonical genome schema declares."""
    document = default_registry().document(genome_kind)
    properties = document.get(PROPERTY_KEY)
    if not isinstance(properties, Mapping) or not properties:
        _fail(
            "GENE_FIELD_UNDECLARED_BY_SCHEMA",
            "the canonical genome schema declares no properties",
            {"genome_kind": genome_kind},
        )
    return dict(properties)  # type: ignore[arg-type]


def genome_kind_contracts() -> dict[str, GenomeKindContract]:
    """The verified kind contracts, keyed by the canonical schema name.

    Verification runs on every call rather than once at import: the sealed
    search space and the genome schemas are the authorities, and a module that
    cached their answer would keep operating after either of them moved.
    """
    mutable = set(mutable_genome_kinds())
    contracts: dict[str, GenomeKindContract] = {}
    for contract in _KIND_CONTRACTS:
        if contract.genome_kind not in mutable:
            _fail(
                "OPERATOR_KIND_OUTSIDE_SEARCH_SPACE",
                f"{contract.genome_kind} is not in the sealed mutable search space",
                {"genome_kind": contract.genome_kind, "mutable": sorted(mutable)},
            )
        properties = genome_properties(contract.genome_kind)
        named = (
            contract.identity_field,
            contract.mechanism_field,
            contract.lineage_field,
            contract.revision_field,
            contract.stamp_field,
        )
        missing = sorted(
            field for field in named if field is not None and field not in properties
        )
        if missing:
            _fail(
                "GENE_FIELD_UNDECLARED_BY_SCHEMA",
                "the canonical genome schema no longer declares every named field",
                {"genome_kind": contract.genome_kind, "missing": missing},
            )
        contracts[contract.genome_kind] = contract
    return contracts


def kind_contract(genome_kind: str) -> GenomeKindContract:
    """The verified contract for one genome kind, refused when undeclared."""
    contracts = genome_kind_contracts()
    if genome_kind not in contracts:
        _fail(
            "OPERATOR_KIND_OUTSIDE_SEARCH_SPACE",
            f"no operator surface is declared for {genome_kind}",
            {"declared": sorted(contracts), "genome_kind": genome_kind},
        )
    return contracts[genome_kind]


def genome_kind_of(document: Mapping[str, Any]) -> str:
    """The one declared kind whose canonical schema this document satisfies.

    A genome document does not carry its own kind, so the kind is derived by
    validation rather than taken from a caller-supplied label: a label can be
    wrong, and a splice that trusted it would cross two contracts.
    """
    matched: list[str] = []
    for genome_kind in genome_kind_contracts():
        try:
            validate_artifact(genome_kind, dict(document))
        except ContractViolation:
            continue
        matched.append(genome_kind)
    if len(matched) != 1:
        _fail(
            "PARENT_CONTRACT_VIOLATED",
            "the document satisfies no single declared genome contract",
            {"matched": sorted(matched)},
        )
    return matched[0]


def immutable_fields(contract: GenomeKindContract) -> frozenset[str]:
    """Fields no operator may declare or touch, for this kind.

    The authority paths come from the Evolution Chamber rather than from a copy
    here: it already owns the boundary between proposing and certifying, and a
    second list would eventually disagree with the one that is enforced.
    """
    engine_owned = {
        field
        for field in (
            contract.identity_field,
            contract.lineage_field,
            contract.revision_field,
            contract.stamp_field,
        )
        if field is not None
    }
    return frozenset(FORBIDDEN_MUTATION_PATHS | engine_owned)


def operator_registry() -> dict[str, ScientificOperator]:
    """The typed operator registry, verified against every declaring source.

    An operator is published only when its kind is still mutable, its mode is
    one the Aporia Engine declares, and every gene it names is a property of the
    genome schema and is not an identity, lineage or authority field.
    """
    contracts = genome_kind_contracts()
    registry: dict[str, ScientificOperator] = {}
    for operator in _OPERATORS:
        if operator.genome_kind not in contracts:
            _fail(
                "OPERATOR_KIND_OUTSIDE_SEARCH_SPACE",
                f"operator {operator.operator_id} targets an undeclared kind",
                {"genome_kind": operator.genome_kind},
            )
        contract = contracts[operator.genome_kind]
        if operator.epistemic_mode not in EPISTEMIC_MODES:
            _fail(
                "OPERATOR_MODE_UNDECLARED",
                f"operator {operator.operator_id} declares an unknown mode",
                {"operator_id": operator.operator_id},
            )
        if not operator.gene_fields:
            _fail(
                "GENE_FIELD_UNDECLARED_BY_SCHEMA",
                f"operator {operator.operator_id} declares no gene at all",
                {"operator_id": operator.operator_id},
            )
        properties = genome_properties(operator.genome_kind)
        undeclared = sorted(set(operator.gene_fields) - set(properties))
        if undeclared:
            _fail(
                "GENE_FIELD_UNDECLARED_BY_SCHEMA",
                f"operator {operator.operator_id} names genes the schema lacks",
                {"operator_id": operator.operator_id, "undeclared": undeclared},
            )
        reserved = sorted(set(operator.gene_fields) & immutable_fields(contract))
        if reserved:
            _fail(
                "LINEAGE_FIELD_IMMUTABLE",
                f"operator {operator.operator_id} claims a reserved field",
                {"operator_id": operator.operator_id, "reserved": reserved},
            )
        registry[operator.operator_id] = operator
    return registry


def operators_for(genome_kind: str) -> tuple[ScientificOperator, ...]:
    """Every declared operator for one genome kind, in identifier order."""
    kind_contract(genome_kind)
    return tuple(
        operator
        for operator in sorted(
            operator_registry().values(), key=lambda entry: entry.operator_id
        )
        if operator.genome_kind == genome_kind
    )


def resolve_operator(operator_id: str) -> ScientificOperator:
    """The declared operator with that identifier, refused when unknown."""
    registry = operator_registry()
    if operator_id not in registry:
        _fail(
            "OPERATOR_UNKNOWN",
            f"no declared operator carries the identifier {operator_id}",
            {"declared": sorted(registry), "operator_id": operator_id},
        )
    return registry[operator_id]


def aporia_citation_shape() -> tuple[str, ...]:
    """The envelope an Aporia operator must cite, as the keys it must carry."""
    return (GRAPH_KEY, OPEN_QUESTION_KEY)


def require_aporia_citation(
    citation: Any, *, subject_id: str
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Validate a cited contradiction, returning the graph and what it left open.

    The graph is validated against the canonical argument contract and then read
    through the Aporia Engine's own accounting: a graph the engine calls
    resolved records nothing to answer, and an identifier the engine does not
    list among the open questions was never left open by that graph.
    """
    if citation is None:
        _fail(
            "APORIA_CITATION_MISSING",
            "this operator answers a recorded contradiction and none was cited",
            {"subject_id": subject_id},
        )
    envelope = _require_mapping(citation, GRAPH_KEY)
    absent = sorted(set(aporia_citation_shape()) - set(envelope))
    if absent:
        _fail(
            "APORIA_CITATION_MALFORMED",
            "the citation envelope does not carry the graph and the questions",
            {"absent": absent},
        )
    graph = dict(_require_mapping(envelope[GRAPH_KEY], GRAPH_KEY))
    try:
        validate_artifact(ARGUMENT_KIND, graph)
    except ContractViolation as error:
        _fail(
            "APORIA_CITATION_MALFORMED",
            "the cited graph does not satisfy the canonical argument contract",
            {"schema_errors": list(error.errors)},
        )
    if str(graph.get(GRAPH_SUBJECT_FIELD)) != str(subject_id):
        _fail(
            "APORIA_CITATION_SUBJECT_MISMATCH",
            "the cited graph reasons about a different hypothesis",
            {
                "cited_subject": graph.get(GRAPH_SUBJECT_FIELD),
                "subject_id": subject_id,
            },
        )
    if is_resolved(graph):
        _fail(
            "APORIA_CITATION_NOT_OPEN",
            "the cited graph is resolved and records nothing left to answer",
            {GRAPH_IDENTITY_FIELD: graph.get(GRAPH_IDENTITY_FIELD)},
        )
    left_open = tuple(open_questions(graph))
    cited = _require_sequence(envelope[OPEN_QUESTION_KEY], OPEN_QUESTION_KEY)
    if not cited:
        _fail(
            "APORIA_CITATION_MALFORMED",
            "the citation names no open question of the graph it cites",
            {"cited": list(cited)},
        )
    unmatched = sorted({str(item) for item in cited} - set(left_open))
    if unmatched:
        _fail(
            "APORIA_CITATION_NOT_OPEN",
            "the citation names questions the graph does not leave open",
            {"left_open": list(left_open), "unmatched": unmatched},
        )
    return graph, tuple(sorted({str(item) for item in cited}))


def mechanism_agreement(
    parents: Sequence[Mapping[str, Any]], *, genome_kind: str
) -> str:
    """The one mechanism both parents propose, refused when they disagree.

    Derived from the genomes' own mechanism field rather than from a
    compatibility report: a report is an assessment and can be stale or wrong,
    while the field is what the child would actually inherit.
    """
    contract = kind_contract(genome_kind)
    if contract.mechanism_field is None:
        _fail(
            "MECHANISM_FIELD_UNDECLARED",
            f"{genome_kind} declares no mechanism field to compare",
            {"genome_kind": genome_kind},
        )
        raise AssertionError  # pragma: no cover - _fail always raises
    declared = {
        _require_text(
            _require_mapping(parent, "parent").get(contract.mechanism_field),
            contract.mechanism_field,
        )
        for parent in parents
    }
    if len(declared) != 1:
        _fail(
            "MECHANISM_INCOMPATIBLE",
            "the parents propose different mechanisms and cannot be spliced",
            {"mechanisms": sorted(declared)},
        )
    return declared.pop()


def _changed_fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Keys whose canonical value differs, including additions and removals."""
    changed: list[str] = []
    for key in sorted(set(before) | set(after)):
        if key not in before or key not in after:
            changed.append(key)
        elif sha256_of_payload(before[key]) != sha256_of_payload(after[key]):
            changed.append(key)
    return changed


def _contained(before: Any, after: Any) -> bool:
    """True when `after` asserts no content `before` does not already carry.

    Two shapes can be checked from the genome alone: a list whose members are a
    subset, and an integer that did not grow.  Anything else counts as new
    content, because a strict claim that cannot be verified is an overclaim.
    """
    if isinstance(before, list) and isinstance(after, list):
        carried = {sha256_of_payload(item) for item in before}
        return all(sha256_of_payload(item) in carried for item in after)
    if (
        isinstance(before, int)
        and isinstance(after, int)
        and not isinstance(before, bool)
        and not isinstance(after, bool)
    ):
        return after <= before
    return False


def _verify_parent(
    contract: GenomeKindContract,
    parent: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> None:
    """The parent satisfies its contract and the lineage really describes it."""
    try:
        validate_artifact(contract.genome_kind, dict(parent))
    except ContractViolation as error:
        _fail(
            "PARENT_CONTRACT_VIOLATED",
            "the parent does not satisfy its canonical genome schema",
            {"schema_errors": list(error.errors)},
        )
    try:
        validate_artifact(LINEAGE_KIND, dict(lineage))
    except ContractViolation as error:
        _fail(
            "LINEAGE_CONTRACT_VIOLATED",
            "the supplied lineage does not satisfy the canonical schema",
            {"schema_errors": list(error.errors)},
        )
    identity = str(parent.get(contract.identity_field))
    if str(lineage.get(CANDIDATE_FIELD)) != identity:
        _fail(
            "PARENT_LINEAGE_MISMATCH",
            "the supplied lineage names a different candidate",
            {"lineage_candidate": lineage.get(CANDIDATE_FIELD), "parent": identity},
        )
    if contract.lineage_field is not None:
        declared = str(parent.get(contract.lineage_field))
        if str(lineage.get(intake.LINEAGE_FIELD)) != declared:
            _fail(
                "PARENT_LINEAGE_MISMATCH",
                "the supplied lineage belongs to a different line",
                {
                    "genome_line": declared,
                    "lineage_line": lineage.get(intake.LINEAGE_FIELD),
                },
            )


def _guard_edit(
    operator: ScientificOperator,
    contract: GenomeKindContract,
    changes: Mapping[str, Any],
) -> None:
    """Refuse an edit before it is applied, most specific refusal first."""
    touched = set(changes)
    if contract.identity_field in touched:
        _fail(
            "IDENTITY_FIELD_IMMUTABLE",
            "an operator may not name the child; the engine mints its identity",
            {"field": contract.identity_field},
        )
    reserved = {
        field
        for field in (contract.lineage_field, contract.revision_field)
        if field is not None
    }
    lineage_touched = sorted(touched & reserved)
    if lineage_touched:
        _fail(
            "LINEAGE_FIELD_IMMUTABLE",
            "an operator may not rewrite the line or revision it descends from",
            {"fields": lineage_touched},
        )
    authority = sorted(touched & FORBIDDEN_MUTATION_PATHS)
    if authority:
        _fail(
            "AUTHORITY_FIELD_TOUCHED",
            "an operator may not touch a field that carries authority",
            {"fields": authority},
        )
    undeclared = sorted(touched - set(operator.gene_fields))
    if undeclared:
        _fail(
            "UNDECLARED_FIELD_TOUCHED",
            f"operator {operator.operator_id} does not declare these genes",
            {"operator_id": operator.operator_id, "undeclared": undeclared},
        )


def _compose_child(
    operator: ScientificOperator,
    contract: GenomeKindContract,
    base: Mapping[str, Any],
    changes: Mapping[str, Any],
    *,
    child_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Apply the edit through the Chamber's guard and stamp the engine fields."""
    properties = genome_properties(contract.genome_kind)
    engine_owned: dict[str, Any] = {contract.identity_field: child_id}
    if contract.revision_field is not None and contract.revision_field in properties:
        engine_owned[contract.revision_field] = (
            int(base[contract.revision_field]) + GENERATION_STEP
        )
    if contract.stamp_field is not None and contract.stamp_field in properties:
        engine_owned[contract.stamp_field] = created_at
    try:
        child = apply_mutation(base, {**dict(changes), **engine_owned})
    except AuthorityMutationRefused as error:
        _fail(
            "AUTHORITY_FIELD_TOUCHED",
            str(error),
            {"operator_id": operator.operator_id},
        )
        raise AssertionError  # pragma: no cover - _fail always raises
    gene_changes = set(_changed_fields(base, child)) & set(operator.gene_fields)
    if not gene_changes:
        _fail(
            "MUTATION_EMPTY",
            f"operator {operator.operator_id} changed no gene it declares",
            {"operator_id": operator.operator_id},
        )
    if operator.epistemic_mode is STRICT_MODE:
        overreaching = sorted(
            field
            for field in gene_changes
            if not _contained(base.get(field), child.get(field))
        )
        if overreaching:
            _fail(
                "STRICT_INFERENCE_VIOLATED",
                "a strict operator asserted content its parent does not contain",
                {"fields": overreaching, "operator_id": operator.operator_id},
            )
    try:
        validate_artifact(contract.genome_kind, child)
    except ContractViolation as error:
        _fail(
            "CHILD_CONTRACT_VIOLATED",
            "the produced child does not satisfy its canonical genome schema",
            {"schema_errors": list(error.errors)},
        )
    return child


def _child_lineage(
    contract: GenomeKindContract,
    operator: ScientificOperator,
    parents: Sequence[Mapping[str, Any]],
    lineages: Sequence[Mapping[str, Any]],
    *,
    child_id: str,
    created_at: str,
) -> dict[str, Any]:
    """The descent record: parents named, generation one deeper, ancestry kept.

    Ancestry is a set rather than a sequence.  Two parents contribute two
    histories with no single true order, so the hashes are sorted and the record
    stays byte-identical across replays of the same application.
    """
    parent_ids = [str(parent[contract.identity_field]) for parent in parents]
    ancestors: set[str] = set()
    for parent, lineage in zip(parents, lineages):
        ancestors.update(str(item) for item in lineage[ANCESTOR_FIELD])
        ancestors.add(sha256_of_payload(dict(parent)))
    generation = max(int(item[GENERATION_FIELD]) for item in lineages)
    record: dict[str, Any] = {
        ANCESTOR_FIELD: sorted(ancestors),
        CANDIDATE_FIELD: child_id,
        STAMP_FIELD: created_at,
        SPLICE_PARENTS_FIELD: list(parent_ids) if operator.splices_parents else [],
        GENERATION_FIELD: generation + GENERATION_STEP,
        INSPIRATION_FIELD: [],
        ISLAND_FIELD: str(lineages[0][ISLAND_FIELD]),
        intake.LINEAGE_FIELD: str(lineages[0][intake.LINEAGE_FIELD]),
        OPERATORS_FIELD: [operator.operator_id],
        PARENTS_FIELD: list(parent_ids),
    }
    try:
        validate_artifact(LINEAGE_KIND, record)
    except ContractViolation as error:
        _fail(
            "LINEAGE_CONTRACT_VIOLATED",
            "the produced lineage does not satisfy the canonical schema",
            {"schema_errors": list(error.errors)},
        )
    return record


def _application_record(
    operator: ScientificOperator,
    contract: GenomeKindContract,
    parents: Sequence[Mapping[str, Any]],
    child: Mapping[str, Any],
    lineage: Mapping[str, Any],
    *,
    created_at: str,
    changed: Sequence[str],
    cited_questions: Sequence[str],
    report_id: str | None,
) -> dict[str, Any]:
    """One self-proving record of what was applied and what it produced."""
    record: dict[str, Any] = {
        "aporia_open_question_ids": list(cited_questions),
        "changed_fields": sorted(changed),
        "child": dict(child),
        "child_hash": sha256_of_payload(dict(child)),
        "crossover_report_id": report_id,
        "epistemic_mode": sorted(operator.epistemic_mode),
        "gene_fields": list(operator.gene_fields),
        "genome_kind": contract.genome_kind,
        "lineage": dict(lineage),
        "operator_id": operator.operator_id,
        "parent_genome_hashes": [sha256_of_payload(dict(item)) for item in parents],
        "parent_genome_ids": [str(item[contract.identity_field]) for item in parents],
        STAMP_FIELD: created_at,
    }
    record["record_hash"] = hash_excluding(record, "record_hash")
    return record


def apply_scientific_mutation(
    *,
    operator_id: str,
    parent: Mapping[str, Any],
    parent_lineage: Mapping[str, Any],
    changes: Mapping[str, Any],
    created_at: str,
    child_genome_id: str | None = None,
    aporia_citation: Any = None,
) -> dict[str, Any]:
    """Apply one declared operator and return the child with its descent.

    The result is a pure function of the inputs whenever the caller supplies
    `child_genome_id`; `new_id` runs only when the caller declines to name the
    child, so replay stays in the caller's hands and the record hash covers
    whichever identifier was used.
    """
    operator = resolve_operator(operator_id)
    if operator.splices_parents:
        _fail(
            "OPERATOR_ARITY_MISMATCH",
            f"operator {operator_id} splices two parents and is not a mutation",
            {"operator_id": operator_id},
        )
    contract = kind_contract(operator.genome_kind)
    document = dict(_require_mapping(parent, "parent"))
    lineage = dict(_require_mapping(parent_lineage, "parent_lineage"))
    edit = dict(_require_mapping(changes, "changes"))
    _require_text(created_at, STAMP_FIELD)
    _verify_parent(contract, document, lineage)

    cited: tuple[str, ...] = ()
    if operator.aporia_grounded:
        _, cited = require_aporia_citation(
            aporia_citation, subject_id=str(document[contract.identity_field])
        )
    elif aporia_citation is not None:
        _fail(
            "INPUT_INVALID",
            f"operator {operator_id} is not grounded in a recorded contradiction",
            {"operator_id": operator_id},
        )

    _guard_edit(operator, contract, edit)
    child_id = _require_text(
        child_genome_id or new_id(contract.id_prefix), "child_genome_id"
    )
    child = _compose_child(
        operator, contract, document, edit, child_id=child_id, created_at=created_at
    )
    descent = _child_lineage(
        contract,
        operator,
        [document],
        [lineage],
        child_id=child_id,
        created_at=created_at,
    )
    return _application_record(
        operator,
        contract,
        [document],
        child,
        descent,
        created_at=created_at,
        changed=_changed_fields(document, child),
        cited_questions=cited,
        report_id=None,
    )


def apply_typed_crossover(
    *,
    operator_id: str,
    parents: Sequence[Mapping[str, Any]],
    parent_lineages: Sequence[Mapping[str, Any]],
    inherited_fields: Sequence[str],
    compatibility_report: Mapping[str, Any],
    created_at: str,
    child_genome_id: str | None = None,
) -> dict[str, Any]:
    """Splice two same-kind parents whose mechanisms already agree.

    Three independent things must hold and none may substitute for another: both
    parents resolve to the genome kind this operator splices, the Evolution
    Chamber's own report unconditionally allows the pair, and the mechanism the
    child would inherit is the same one in both parents.  The report is an
    assessment; the mechanism check reads the genomes themselves, so a report
    that is wrong about the mechanism cannot let the splice through.
    """
    operator = resolve_operator(operator_id)
    if not operator.splices_parents:
        _fail(
            "OPERATOR_ARITY_MISMATCH",
            f"operator {operator_id} mutates one parent and cannot splice two",
            {"operator_id": operator_id},
        )
    contract = kind_contract(operator.genome_kind)
    documents = [
        dict(_require_mapping(item, "parent"))
        for item in _require_sequence(parents, "parents")
    ]
    lineages = [
        dict(_require_mapping(item, "parent_lineage"))
        for item in _require_sequence(parent_lineages, "parent_lineages")
    ]
    if len(documents) != 2 or len(lineages) != len(documents):
        _fail(
            "INPUT_INVALID",
            "a typed crossover takes exactly two parents and their lineages",
            {"lineages": len(lineages), "parents": len(documents)},
        )
    _require_text(created_at, STAMP_FIELD)

    resolved = sorted({genome_kind_of(document) for document in documents})
    if resolved != [operator.genome_kind]:
        _fail(
            "CROSSOVER_KIND_MISMATCH",
            "the parents do not both resolve to the kind this operator splices",
            {"genome_kind": operator.genome_kind, "resolved": resolved},
        )
    for document, lineage in zip(documents, lineages):
        _verify_parent(contract, document, lineage)
    identities = [str(document[contract.identity_field]) for document in documents]
    if len(set(identities)) != len(identities):
        _fail(
            "INPUT_INVALID",
            "a candidate cannot be spliced with itself",
            {PARENTS_FIELD: identities},
        )

    report = dict(_require_mapping(compatibility_report, "compatibility_report"))
    named = {
        str(item)
        for item in _require_sequence(
            report.get(REPORT_PARENTS_FIELD) or [], REPORT_PARENTS_FIELD
        )
    }
    if not set(identities) <= named:
        _fail(
            "CROSSOVER_REPORT_MISMATCH",
            "the compatibility report does not name both parents",
            {PARENTS_FIELD: identities, REPORT_PARENTS_FIELD: sorted(named)},
        )
    if not crossover_permitted(report):
        _fail(
            "CROSSOVER_NOT_PERMITTED",
            "the compatibility report is not an unconditional allow",
            {REPORT_IDENTITY_FIELD: report.get(REPORT_IDENTITY_FIELD)},
        )
    mechanism_agreement(documents, genome_kind=operator.genome_kind)

    donated = list(_require_sequence(inherited_fields, "inherited_fields"))
    if not donated:
        _fail(
            "MUTATION_EMPTY",
            "a splice that inherits nothing from the second parent is a copy",
            {"operator_id": operator_id},
        )
    base, donor = documents
    edit: dict[str, Any] = {}
    for field in donated:
        name = _require_text(field, "inherited_field")
        if name not in donor:
            _fail(
                "UNDECLARED_FIELD_TOUCHED",
                "the second parent does not carry an inherited gene",
                {"field": name},
            )
        edit[name] = donor[name]
    _guard_edit(operator, contract, edit)
    child_id = _require_text(
        child_genome_id or new_id(contract.id_prefix), "child_genome_id"
    )
    child = _compose_child(
        operator, contract, base, edit, child_id=child_id, created_at=created_at
    )
    descent = _child_lineage(
        contract,
        operator,
        documents,
        lineages,
        child_id=child_id,
        created_at=created_at,
    )
    return _application_record(
        operator,
        contract,
        documents,
        child,
        descent,
        created_at=created_at,
        changed=_changed_fields(base, child),
        cited_questions=(),
        report_id=(
            None
            if report.get(REPORT_IDENTITY_FIELD) is None
            else str(report[REPORT_IDENTITY_FIELD])
        ),
    )
