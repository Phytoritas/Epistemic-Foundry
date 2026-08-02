"""schema_and_type_check — the gate is bound to the canonical schemas.

Behaviour tests drive the gate; this file checks the vocabulary it reasons with
is read from the canonical contracts rather than restated.  The EVOLVE handoff
phase is the FORGE lifecycle's own terminal phase, the replay tokens are the
replay-report schema's own enums, and the composed stop-reason vocabulary is the
one the F05 machine publishes.  Because the gate reads all of this on demand, a
schema rename closes the gate here instead of letting it reason against a value
the contract no longer declares.
"""

from __future__ import annotations

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.evolution.v4_f05 import stop_reasons
from epistemic_foundry.evolution.v4_f06 import (
    FINDING_CODES,
    SEED_GENOME_KIND,
    STOP_REASONS,
    evolve_handoff_phase,
    replay_vocabulary,
)
from epistemic_foundry.intake.v4_i05 import GENOME_KIND

_registry = default_registry()


def test_the_handoff_phase_is_the_forge_lifecycles_terminal_phase() -> None:
    phases = [
        str(v)
        for v in _registry.document("forge-session-state")["properties"]["phase"][
            "enum"
        ]
    ]
    assert evolve_handoff_phase() == phases[-1]


def test_the_replay_vocabulary_is_read_from_the_replay_report_schema() -> None:
    replay = _registry.document("replay-report")["properties"]
    modes = [str(v) for v in replay["mode"]["enum"]]
    equivalences = [str(v) for v in replay["event_equivalence"]["enum"]]
    drifts = [str(v) for v in replay["drift_classification"]["enum"]]
    vocab = replay_vocabulary()
    assert vocab["strict_mode"] == modes[0]
    assert vocab["exact_equivalence"] == equivalences[0]
    assert vocab["equivalent_equivalence"] == equivalences[1]
    assert vocab["no_drift"] == drifts[0]


def test_the_stop_reason_vocabulary_comes_from_the_composed_f05_machine() -> None:
    assert STOP_REASONS == stop_reasons()
    assert STOP_REASONS  # the machine publishes a non-empty stop vocabulary


def test_the_seed_genome_kind_is_the_one_i05_intake_screens() -> None:
    assert SEED_GENOME_KIND == GENOME_KIND


def test_the_finding_codes_are_documented_and_nonempty() -> None:
    assert FINDING_CODES
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert isinstance(reason, str) and reason.strip()


def test_input_invalid_is_a_declared_finding_code() -> None:
    # Every input-integrity refusal resolves through this code, so its absence
    # would make the gate raise an undeclared code.
    assert "INPUT_INVALID" in FINDING_CODES


def test_the_canonical_schemas_the_gate_reads_are_registered() -> None:
    for name in ("forge-session-state", "replay-report", "evolution-stop-certificate"):
        assert name in set(_registry.names())
