"""The FORGE-EVOLVE lifecycle integration and replay gate.

A FORGE session frames a hypothesis and then hands it to the EVOLVE subprotocol,
which searches for variants under an immutable evaluator until a typed stop
certificate ends the run.  Two things can be dishonest about that handoff.  The
lifecycle can be inconsistent: a run that loops past its own budget, re-enters
from a checkpoint it never committed, stops without a certificate, or swaps its
evaluator mid-run has produced a search whose account of itself cannot be
trusted.  And the replay can be a fiction: a run that claims to reproduce
byte-for-byte while its own report records artifact-hash mismatches, missing
pins, or drift did not actually replay, and a search that cannot be replayed
cannot be audited (EF4-I39).  This gate refuses exactly those two dishonesties.

It is an *integration* gate.  It re-uses the already-sealed surfaces that each
own a piece of the account and adds only the composition, restating none of
their vocabularies (EF4-I22):

* **Lifecycle** is read through the F05 EVOLVE state machine.  F05 already walks
  a run's transitions, bounds its return edges by the LoopContract, and refuses
  a run whose stop certificate does not certify the stop it records.  The gate
  composes that verdict rather than re-deriving it, mapping an F05 refusal onto
  a lifecycle or stop-certificate finding.
* **Seed intake** is read through the I05 genome intake.  The population the run
  claims to have seeded is screened and bootstrapped by I05, and the gate refuses
  a run whose declared seed genomes are not exactly the ones intake admitted.
* **Operators** are read through the R05 typed operator registry.  Every operator
  the run applied must resolve to one R05 declares; an unregistered operator put
  an unreviewed edit into the lineage.
* **Evaluator immutability** (EF4-I43) is derived from the run's own committed
  checkpoints: every checkpoint a return edge crossed must bind the one evaluator
  bundle hash, or the run changed the authority it was judged against.
* **Candidate reconciliation** (EF4-I60): the run's declared candidate set must be
  exactly its seeds plus the children its operators produced, with nothing
  unaccounted.
* **Replay** is read from a ReplayReport, and never trusted to flatter itself: a
  run is honoured only when its own report shows a strict, exact, drift-free
  replay with no artifact-hash mismatch and no missing pin, and a report whose
  claims contradict its own counters is refused as dishonest.

Nothing here scores, selects, promotes or evaluates a candidate, and no input is
mutated.  The gate acquires no evaluator, holdout or promotion authority: it
reads sealed verdicts and refuses, it never certifies.  The receipt is a pure
function of the inputs — there is no clock and no random draw, the caller
supplies ``created_at``, and the gate identifier and receipt hash are
re-derivable from the published content.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from ...contracts import (
    ContractViolation,
    SchemaNotFound,
    default_registry,
    repo_root,
    validate_artifact,
)
from ...domain.hashing import (
    canonical_json,
    hash_excluding,
    is_schema_digest,
    sha256_hex,
    sha256_of_payload,
)
from ...evolution.v4_f05 import (
    EvolveStateError,
    Transition,
    evaluate_run,
    require_valid_run,
    stop_reasons,
)
from ...intake.v4_i05 import GENOME_KIND, bootstrap_seed_population
from ...intake.v4_i05 import screening as intake
from ...reasoning.v4_r05 import operator_registry

#: Every way this gate refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership.
FINDING_CODES: Final[dict[str, str]] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record a decision derived from something it never validated"
    ),
    "FORGE_SESSION_CONTRACT_VIOLATED": (
        "the FORGE session does not satisfy its canonical schema, so any handoff "
        "read from it would be read from a shape no contract admits"
    ),
    "REPLAY_REPORT_CONTRACT_VIOLATED": (
        "the replay report does not satisfy its canonical schema, so its "
        "equivalence verdict and hash counters are unusable"
    ),
    "FORGE_HANDOFF_ABSENT": (
        "the FORGE session never transitioned into the EVOLVE handoff phase, so "
        "there is no lifecycle edge for the EVOLVE run to continue from"
    ),
    "FORGE_RUN_SPEC_MISBOUND": (
        "the FORGE session and the EVOLVE run name different run specs, so the "
        "session handed off to some other run and this account is not continuous"
    ),
    "LIFECYCLE_TRANSITIONS_INCONSISTENT": (
        "the EVOLVE state machine refuses the run's transitions, budget or return "
        "edges, so the lifecycle took a path the workflow never described"
    ),
    "STOP_CERTIFICATE_INCONSISTENT": (
        "the run's stop certificate does not certify the stop it records, so a "
        "stop cannot be distinguished from a crash and its resume point is unsafe"
    ),
    "EVALUATOR_BUNDLE_MUTATED": (
        "the run's committed checkpoints bind more than one evaluator bundle hash, "
        "so the evaluator changed mid-run and the earlier judgments are void"
    ),
    "EVALUATOR_BUNDLE_UNBOUND": (
        "a committed return checkpoint binds no content-addressed evaluator bundle, "
        "so the run has no immutable evaluator authority at that resume point"
    ),
    "SEED_INTAKE_REFUSED": (
        "the seed population the run claims does not survive I05 intake screening, "
        "so the search was seeded with something intake never admitted"
    ),
    "SEED_POPULATION_UNRECONCILED": (
        "the run's declared seed genomes are not exactly the genomes intake "
        "admitted, so the population that was searched is not the one screened"
    ),
    "OPERATOR_UNDECLARED": (
        "the run applied an operator the R05 registry does not declare, so an "
        "unreviewed edit was placed into the candidate lineage"
    ),
    "CANDIDATE_SET_UNRECONCILED": (
        "the run's candidate set is not exactly its seeds plus its operators' "
        "children, so a candidate was searched or dropped without an account"
    ),
    "REPLAY_RUN_MISBOUND": (
        "the replay report reproduces a different run than the one under the gate, "
        "so it says nothing about whether this run replays"
    ),
    "REPLAY_REPORT_DISHONEST": (
        "the replay report's equivalence verdict contradicts its own hash, pin, "
        "gate or verdict counters, so it flatters a replay its evidence refuses"
    ),
    "REPLAY_NOT_BYTE_FOR_BYTE": (
        "the run's own replay report is not a strict, exact, drift-free "
        "reproduction, so the run cannot be replayed byte-for-byte and is refused"
    ),
}

#: Canonical schema names this gate reads.  Each is a registered canonical
#: contract, verified before use rather than restated as fields here.
FORGE_SESSION_KIND: Final = "forge-session-state"
REPLAY_REPORT_KIND: Final = "replay-report"

#: The gate decision tokens.  These are the gate's own outcome vocabulary, not a
#: canonical wire enum, so holding them here declares nothing a schema owns.
ADMIT: Final = "ADMIT"
REFUSE: Final = "REFUSE"

#: The checkpoint component that pins the run's evaluator authority.  A field
#: name of the evolution-checkpoint contract, not a wire enum value.
EVALUATOR_BUNDLE_FIELD: Final = "evaluator_bundle_hash"

#: F05 refusal codes that name a stop-certificate fault rather than a transition
#: fault, so the gate can attribute the finding to the right lifecycle concern.
_STOP_CERTIFICATE_CODES: Final = frozenset(
    {"STOP_CERTIFICATE_INVALID", "RUN_UNTERMINATED"}
)


class LifecycleReplayRefused(ValueError):
    """The gate refuses a run, or its evidence, with a documented code."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    """Raise an input-integrity refusal, before any decision receipt exists."""
    if code not in FINDING_CODES:
        raise LifecycleReplayRefused(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise LifecycleReplayRefused(code, message, context)


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return dict(value)  # type: ignore[arg-type]


def _require_sequence(value: object, label: str) -> list[Any]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        _fail("INPUT_INVALID", f"{label} must be a sequence", {"label": label})
    return list(value)  # type: ignore[arg-type]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def _require_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("INPUT_INVALID", f"{label} must be an integer", {"label": label})
    return int(value)


@lru_cache(maxsize=1)
def _vocab() -> dict[str, str]:
    """Every canonical token the gate reasons about, read from the schema.

    Holding these as string literals would be a second copy that drifts from the
    contract (EF4-I22).  The EVOLVE handoff phase is the FORGE lifecycle's own
    terminal phase — the last declared phase value — and the replay tokens are the
    schema's own declared order, each list published so a reshape that changes a
    length fails closed here rather than silently selecting the wrong token.
    """
    registry = default_registry()
    session = registry.document(FORGE_SESSION_KIND)["properties"]
    phases = [str(value) for value in session["phase"]["enum"]]
    if len(phases) < 2:
        _fail(
            "FORGE_SESSION_CONTRACT_VIOLATED",
            "the forge-session-state schema declares no phase vocabulary",
            {"phases": phases},
        )
    replay = registry.document(REPLAY_REPORT_KIND)["properties"]
    modes = [str(value) for value in replay["mode"]["enum"]]
    equivalences = [str(value) for value in replay["event_equivalence"]["enum"]]
    drifts = [str(value) for value in replay["drift_classification"]["enum"]]
    if len(modes) < 2 or len(equivalences) < 2 or len(drifts) < 1:
        _fail(
            "REPLAY_REPORT_CONTRACT_VIOLATED",
            "the replay-report schema does not declare its expected vocabularies",
            {"modes": modes, "event_equivalence": equivalences, "drift": drifts},
        )
    return {
        "evolve_phase": phases[-1],
        "strict_mode": modes[0],
        "exact_equivalence": equivalences[0],
        "equivalent_equivalence": equivalences[1],
        "no_drift": drifts[0],
    }


def evolve_handoff_phase() -> str:
    """The FORGE phase that hands off to the EVOLVE subprotocol."""
    return _vocab()["evolve_phase"]


def replay_vocabulary() -> dict[str, str]:
    """The canonical replay tokens the gate reasons about, read from the schema."""
    vocab = _vocab()
    return {key: vocab[key] for key in vocab if key != "evolve_phase"}


def _f05_report(
    root: str | Path, run: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, EvolveStateError | None]:
    """Walk the run through the F05 machine, deferring any refusal to the axis.

    The transitions are required to be F05 ``Transition`` objects here, so an
    ``INPUT_INVALID`` from the machine cannot mask a caller-shape error as a
    lifecycle finding; every other F05 refusal is a genuine lifecycle fault and
    is returned for the lifecycle axis to attribute.
    """
    transitions = run["transitions"]
    for position, transition in enumerate(transitions):
        if not isinstance(transition, Transition):
            _fail(
                "INPUT_INVALID",
                f"run.transitions[{position}] is not an F05 Transition",
                {"position": position},
            )
    try:
        report = evaluate_run(
            root,
            transitions=transitions,
            loop_contract=run["loop_contract"],
            stop_certificate=run["stop_certificate"],
            dry_rounds_observed=run["dry_rounds_observed"],
        )
    except EvolveStateError as error:
        if error.code == "INPUT_INVALID":
            _fail("INPUT_INVALID", str(error), dict(error.context))
        return None, error
    return report, None


def _evaluator_bundle_bindings(
    run: Mapping[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return distinct evaluator hashes and any return checkpoints lacking one."""

    loop_contract = run["loop_contract"]
    exit_node_id = str(loop_contract["exit_node_id"])
    entry_node_id = str(loop_contract["entry_node_id"])
    seen: set[str] = set()
    unbound: list[dict[str, Any]] = []
    for position, transition in enumerate(run["transitions"]):
        if transition.source != exit_node_id or transition.target != entry_node_id:
            continue
        checkpoint = transition.checkpoint
        if not isinstance(checkpoint, Mapping):
            unbound.append(
                {
                    "checkpoint_id": transition.checkpoint_id,
                    "position": position,
                    "reason": "checkpoint_payload_missing",
                }
            )
            continue
        value = checkpoint.get(EVALUATOR_BUNDLE_FIELD)
        if not is_schema_digest(value):
            unbound.append(
                {
                    "checkpoint_id": transition.checkpoint_id,
                    "position": position,
                    "reason": "evaluator_bundle_hash_invalid",
                }
            )
            continue
        seen.add(value)
    return sorted(seen), unbound


def _evaluator_bundle_hashes(run: Mapping[str, Any]) -> list[str]:
    """The distinct evaluator bundle hashes the run's checkpoints bind."""

    return _evaluator_bundle_bindings(run)[0]


def _lifecycle_finding(
    report: dict[str, Any] | None,
    error: EvolveStateError | None,
    run: Mapping[str, Any],
) -> tuple[str, str, dict[str, Any]] | None:
    """Attribute an F05 refusal to a lifecycle or stop-certificate finding."""
    if error is None and report is not None:
        try:
            require_valid_run(report)
        except EvolveStateError as raised:
            error = raised
    if error is None:
        # A stop certificate must belong to the run it stops; F05 checks the
        # certificate's internal consistency but not its binding to this run.
        certificate = run["stop_certificate"]
        if isinstance(certificate, Mapping):
            certified = str(certificate.get("evolution_run_id") or "")
            if certified != run["evolution_run_id"]:
                return (
                    "STOP_CERTIFICATE_INCONSISTENT",
                    "the stop certificate certifies a different evolution run",
                    {
                        "certified_run": certified,
                        "evolution_run_id": run["evolution_run_id"],
                    },
                )
        return None
    if error.code in _STOP_CERTIFICATE_CODES:
        code = "STOP_CERTIFICATE_INCONSISTENT"
    else:
        code = "LIFECYCLE_TRANSITIONS_INCONSISTENT"
    return code, str(error), {"f05_code": error.code, **dict(error.context)}


def _seed_finding(
    run: Mapping[str, Any], *, created_at: str, screened_at: str
) -> tuple[str, str, dict[str, Any]] | None:
    """Bootstrap the seed population through I05 and reconcile it with the run."""
    try:
        population = bootstrap_seed_population(
            submissions=run["seed_submissions"],
            minimum_signature_diversity=run["minimum_signature_diversity"],
            island_id=run["island_id"],
            created_at=created_at,
            screened_at=screened_at,
        )
    except intake.GenomeIntakeError as error:
        return (
            "SEED_INTAKE_REFUSED",
            "the seed population does not survive I05 intake screening",
            {"i05_code": error.code, **dict(error.context)},
        )
    admitted = set(population["seed_genome_ids"])
    declared = {str(item) for item in run["seed_genome_ids"]}
    if admitted != declared:
        return (
            "SEED_POPULATION_UNRECONCILED",
            "the run's declared seeds are not the genomes intake admitted",
            {
                "admitted": sorted(admitted),
                "declared": sorted(declared),
            },
        )
    return None


def _operator_children(
    run: Mapping[str, Any],
) -> tuple[
    tuple[str, str, dict[str, Any]] | None,
    list[str],
    list[str],
]:
    """Resolve every applied operator and collect the children it produced."""
    registry = operator_registry()
    children: list[str] = []
    operators: list[str] = []
    for position, application in enumerate(run["operator_applications"]):
        record = _require_mapping(application, f"operator_applications[{position}]")
        operator_id = _require_text(
            record.get("operator_id"), f"operator_applications[{position}].operator_id"
        )
        child_id = _require_text(
            record.get("child_genome_id"),
            f"operator_applications[{position}].child_genome_id",
        )
        if operator_id not in registry:
            return (
                (
                    "OPERATOR_UNDECLARED",
                    "the run applied an operator the R05 registry does not declare",
                    {"operator_id": operator_id, "declared": sorted(registry)},
                ),
                [],
                [],
            )
        operators.append(operator_id)
        children.append(child_id)
    return None, sorted(set(operators)), children


def _replay_finding(
    replay_report: Mapping[str, Any], run: Mapping[str, Any]
) -> tuple[str, str, dict[str, Any]] | None:
    """Refuse a replay that is misbound, self-contradictory, or not exact."""
    vocab = _vocab()
    source = str(replay_report["source_run_id"])
    if source != run["evolution_run_id"]:
        return (
            "REPLAY_RUN_MISBOUND",
            "the replay report reproduces a different run than the one under gate",
            {"source_run_id": source, "evolution_run_id": run["evolution_run_id"]},
        )

    equivalence = str(replay_report["event_equivalence"])
    mismatches = int(replay_report["artifact_hash_mismatches"])
    matches = int(replay_report["artifact_hash_matches"])
    unavailable = list(replay_report["unavailable_pins"])
    drift = str(replay_report["drift_classification"])
    gate_differences = list(replay_report["gate_differences"])
    verdict_differences = list(replay_report["verdict_differences"])
    differences = gate_differences + verdict_differences

    # A report that claims exact equivalence while its own counters record a
    # mismatch, a missing pin, drift or a gate/verdict difference is refused as
    # dishonest before its verdict is taken at face value.
    if equivalence == vocab["exact_equivalence"] and (
        mismatches > 0 or unavailable or drift != vocab["no_drift"] or differences
    ):
        return (
            "REPLAY_REPORT_DISHONEST",
            "the report claims exact equivalence its own counters contradict",
            {
                "artifact_hash_mismatches": mismatches,
                "unavailable_pins": unavailable,
                "drift_classification": drift,
                "differences": differences,
            },
        )
    # No drift may be claimed while gate or verdict differences remain recorded.
    if drift == vocab["no_drift"] and differences:
        return (
            "REPLAY_REPORT_DISHONEST",
            "the report classifies no drift while recording gate or verdict differences",
            {"drift_classification": drift, "differences": differences},
        )

    byte_for_byte = (
        str(replay_report["mode"]) == vocab["strict_mode"]
        and equivalence == vocab["exact_equivalence"]
        and mismatches == 0
        and matches > 0
        and not unavailable
        and drift == vocab["no_drift"]
        and not differences
    )
    if not byte_for_byte:
        return (
            "REPLAY_NOT_BYTE_FOR_BYTE",
            "the run's own replay report is not a strict, exact, drift-free replay",
            {
                "mode": str(replay_report["mode"]),
                "event_equivalence": equivalence,
                "artifact_hash_matches": matches,
                "artifact_hash_mismatches": mismatches,
                "unavailable_pins": unavailable,
                "drift_classification": drift,
                "differences": differences,
            },
        )
    return None


def _validate_run(run: Mapping[str, Any]) -> dict[str, Any]:
    """Read every field the run must carry, refusing a malformed shape."""
    record = _require_mapping(run, "run")
    validated: dict[str, Any] = {
        "evolution_run_id": _require_text(
            record.get("evolution_run_id"), "run.evolution_run_id"
        ),
        "run_spec_id": _require_text(record.get("run_spec_id"), "run.run_spec_id"),
        "seed_submissions": _require_sequence(
            record.get("seed_submissions"), "run.seed_submissions"
        ),
        "minimum_signature_diversity": _require_int(
            record.get("minimum_signature_diversity"),
            "run.minimum_signature_diversity",
        ),
        "island_id": _require_text(record.get("island_id"), "run.island_id"),
        "transitions": _require_sequence(record.get("transitions"), "run.transitions"),
        "loop_contract": _require_mapping(
            record.get("loop_contract"), "run.loop_contract"
        ),
        "dry_rounds_observed": _require_int(
            record.get("dry_rounds_observed"), "run.dry_rounds_observed"
        ),
        "operator_applications": _require_sequence(
            record.get("operator_applications"), "run.operator_applications"
        ),
        "candidate_genome_ids": [
            _require_text(item, "run.candidate_genome_ids[]")
            for item in _require_sequence(
                record.get("candidate_genome_ids"), "run.candidate_genome_ids"
            )
        ],
        "seed_genome_ids": [
            _require_text(item, "run.seed_genome_ids[]")
            for item in _require_sequence(
                record.get("seed_genome_ids"), "run.seed_genome_ids"
            )
        ],
    }
    certificate = record.get("stop_certificate")
    if certificate is not None and not isinstance(certificate, Mapping):
        _fail("INPUT_INVALID", "run.stop_certificate must be a mapping or null")
    validated["stop_certificate"] = (
        dict(certificate) if isinstance(certificate, Mapping) else None
    )
    return validated


def _first_finding(
    *,
    forge_session: Mapping[str, Any],
    run: dict[str, Any],
    replay_report: Mapping[str, Any],
    report: dict[str, Any] | None,
    error: EvolveStateError | None,
    created_at: str,
    screened_at: str,
    operators: list[str],
    children: list[str],
    operator_finding: tuple[str, str, dict[str, Any]] | None,
) -> tuple[str, str, dict[str, Any]] | None:
    """Evaluate the gate's axes in priority order and return the first refusal."""
    vocab = _vocab()

    # FORGE handoff: the session reached the EVOLVE phase and names this run.
    if str(forge_session.get("phase")) != vocab["evolve_phase"]:
        return (
            "FORGE_HANDOFF_ABSENT",
            "the FORGE session is not in the EVOLVE handoff phase",
            {"phase": forge_session.get("phase"), "expected": vocab["evolve_phase"]},
        )
    history = forge_session.get("phase_history") or []
    if not any(
        isinstance(entry, Mapping) and str(entry.get("to")) == vocab["evolve_phase"]
        for entry in history
    ):
        return (
            "FORGE_HANDOFF_ABSENT",
            "the FORGE session records no transition into the EVOLVE handoff phase",
            {"expected": vocab["evolve_phase"]},
        )
    if str(forge_session.get("run_spec_id")) != run["run_spec_id"]:
        return (
            "FORGE_RUN_SPEC_MISBOUND",
            "the FORGE session and the EVOLVE run name different run specs",
            {
                "session_run_spec": forge_session.get("run_spec_id"),
                "run_spec_id": run["run_spec_id"],
            },
        )

    # Lifecycle and stop certificate: the F05 machine's own verdict.
    lifecycle = _lifecycle_finding(report, error, run)
    if lifecycle is not None:
        return lifecycle

    # Evaluator immutability (EF4-I43): one bundle across every checkpoint.
    bundles, unbound = _evaluator_bundle_bindings(run)
    if len(bundles) > 1:
        context: dict[str, Any] = {"evaluator_bundle_hashes": bundles}
        if unbound:
            context["unbound_checkpoints"] = unbound
        return (
            "EVALUATOR_BUNDLE_MUTATED",
            "the run's checkpoints bind more than one evaluator bundle hash",
            context,
        )
    if unbound:
        return (
            "EVALUATOR_BUNDLE_UNBOUND",
            "a committed return checkpoint binds no canonical evaluator bundle hash",
            {"unbound_checkpoints": unbound},
        )
    if len(bundles) == 0:
        loop_contract = run["loop_contract"]
        exit_node_id = str(loop_contract["exit_node_id"])
        entry_node_id = str(loop_contract["entry_node_id"])
        return_edges = sum(
            1
            for transition in run["transitions"]
            if transition.source == exit_node_id and transition.target == entry_node_id
        )
        return (
            "EVALUATOR_BUNDLE_UNBOUND",
            "the run binds no content-addressed evaluator bundle",
            {
                "return_edges": return_edges,
                "evaluator_bundle_hashes": bundles,
            },
        )

    # Seed intake (I05): the run's seeds are exactly what intake admitted.
    seed = _seed_finding(run, created_at=created_at, screened_at=screened_at)
    if seed is not None:
        return seed

    # Operators (R05): every applied operator is one the registry declares.
    if operator_finding is not None:
        return operator_finding

    # Candidate reconciliation (EF4-I60): seeds plus children, nothing else.
    expected = {str(item) for item in run["seed_genome_ids"]} | {
        str(item) for item in children
    }
    declared = {str(item) for item in run["candidate_genome_ids"]}
    if expected != declared:
        return (
            "CANDIDATE_SET_UNRECONCILED",
            "the candidate set is not exactly the seeds plus the operator children",
            {
                "expected": sorted(expected),
                "declared": sorted(declared),
                "unaccounted": sorted(declared - expected),
                "missing": sorted(expected - declared),
            },
        )

    # Replay: the run's own report shows an honest byte-for-byte reproduction.
    return _replay_finding(replay_report, run)


def derive_lifecycle_replay(
    *,
    forge_session: Mapping[str, Any],
    run: Mapping[str, Any],
    replay_report: Mapping[str, Any],
    created_at: str,
    screened_at: str,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Derive the gate decision and its immutable receipt without enforcing it.

    Input-integrity failures — a malformed run, a session or replay report that
    fails its schema — refuse immediately, because there is no well-formed
    decision to record over evidence the gate cannot read.  Once every input is
    validated, the decision always produces a receipt, whether it admits the run
    or refuses it, so every gate decision over well-formed inputs is auditable
    and re-derivable.
    """
    stamp = _require_text(created_at, "created_at")
    _require_text(screened_at, "screened_at")
    root = repository_root if repository_root is not None else repo_root()

    session = _require_mapping(forge_session, "forge_session")
    try:
        validate_artifact(FORGE_SESSION_KIND, session)
    except ContractViolation as error:
        _fail(
            "FORGE_SESSION_CONTRACT_VIOLATED",
            "the FORGE session does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    derived_state_hash = hash_excluding(session, "state_hash")
    if session["state_hash"] != derived_state_hash:
        _fail(
            "FORGE_SESSION_CONTRACT_VIOLATED",
            "the FORGE session does not re-derive its own state hash",
            {
                "session_id": str(session["session_id"]),
                "declared": str(session["state_hash"]),
                "derived": derived_state_hash,
            },
        )

    replay = _require_mapping(replay_report, "replay_report")
    try:
        validate_artifact(REPLAY_REPORT_KIND, replay)
    except ContractViolation as error:
        _fail(
            "REPLAY_REPORT_CONTRACT_VIOLATED",
            "the replay report does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    derived_report_hash = hash_excluding(replay, "report_hash")
    if replay["report_hash"] != derived_report_hash:
        _fail(
            "REPLAY_REPORT_CONTRACT_VIOLATED",
            "the replay report does not re-derive its own report hash",
            {
                "replay_id": str(replay["replay_id"]),
                "declared": str(replay["report_hash"]),
                "derived": derived_report_hash,
            },
        )

    validated = _validate_run(run)
    report, error = _f05_report(root, validated)
    operator_finding, operators, children = _operator_children(validated)

    finding = _first_finding(
        forge_session=session,
        run=validated,
        replay_report=replay,
        report=report,
        error=error,
        created_at=stamp,
        screened_at=screened_at,
        operators=operators,
        children=children,
        operator_finding=operator_finding,
    )

    if finding is None:
        decision, finding_code, message, decision_context = (
            ADMIT,
            None,
            "the FORGE-EVOLVE lifecycle is consistent and the run replays byte-for-byte",
            {},
        )
    else:
        finding_code, message, decision_context = finding
        decision = REFUSE

    counts = (report or {}).get("counts") or {}
    receipt: dict[str, Any] = {
        "gate": "forge-evolve-lifecycle-replay",
        "created_at": stamp,
        "decision": decision,
        "finding_code": finding_code,
        "message": message,
        "decision_context": decision_context,
        "evolution_run_id": validated["evolution_run_id"],
        "run_spec_id": validated["run_spec_id"],
        "forge_session_id": str(session["session_id"]),
        "forge_session_hash": sha256_of_payload(session),
        "forge_phase": str(session["phase"]),
        "replay_report_id": str(replay["replay_id"]),
        "replay_report_hash": sha256_of_payload(replay),
        "source_run_id": str(replay["source_run_id"]),
        "replay_mode": str(replay["mode"]),
        "replay_event_equivalence": str(replay["event_equivalence"]),
        "lifecycle_valid": bool(report is not None and report.get("valid")),
        "return_edges": int(counts.get("return_edges", 0)),
        "evaluator_bundle_hashes": _evaluator_bundle_hashes(validated),
        "seed_genome_ids": sorted(str(item) for item in validated["seed_genome_ids"]),
        "candidate_genome_ids": sorted(
            str(item) for item in validated["candidate_genome_ids"]
        ),
        "operator_ids": operators,
    }
    receipt["gate_id"] = (
        "FELR-"
        + sha256_hex(
            canonical_json(
                {
                    "created_at": stamp,
                    "decision": decision,
                    "evolution_run_id": receipt["evolution_run_id"],
                    "forge_session_hash": receipt["forge_session_hash"],
                    "replay_report_hash": receipt["replay_report_hash"],
                    "run_spec_id": receipt["run_spec_id"],
                }
            )
        )[len("sha256:") :]
    )
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def evaluate_lifecycle_replay(
    *,
    forge_session: Mapping[str, Any],
    run: Mapping[str, Any],
    replay_report: Mapping[str, Any],
    created_at: str,
    screened_at: str,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Enforce the gate: return the receipt on admit, raise on any refusal.

    The refusal carries its finding code and the same immutable receipt the
    derivation produced, so a caller that catches it still holds the auditable
    record of why the run was stopped.
    """
    receipt = derive_lifecycle_replay(
        forge_session=forge_session,
        run=run,
        replay_report=replay_report,
        created_at=created_at,
        screened_at=screened_at,
        repository_root=repository_root,
    )
    if receipt["decision"] != ADMIT:
        raise LifecycleReplayRefused(
            str(receipt["finding_code"]),
            str(receipt["message"]),
            {"receipt": receipt, **dict(receipt["decision_context"])},
        )
    return receipt


#: The stop-reason vocabulary the composed F05 machine reasons about, re-exported
#: so a caller can read it without re-declaring it here.
STOP_REASONS: Final = stop_reasons()

#: The hypothesis-genome kind the composed I05 intake screens, re-exported for
#: callers building the seed submissions this gate reconciles.
SEED_GENOME_KIND: Final = GENOME_KIND

# ``SchemaNotFound`` is imported so a caller can distinguish a missing canonical
# schema (an environment fault) from a refusal; re-exported for that use.
__all__ = [
    "ADMIT",
    "FINDING_CODES",
    "REFUSE",
    "SEED_GENOME_KIND",
    "STOP_REASONS",
    "LifecycleReplayRefused",
    "SchemaNotFound",
    "derive_lifecycle_replay",
    "evaluate_lifecycle_replay",
    "evolve_handoff_phase",
    "replay_vocabulary",
]
