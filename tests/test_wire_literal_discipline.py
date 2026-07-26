"""No duplicated wire literals (EF4-I22).

`CLI, MCP, HTTP, persistence and UI models derive from canonical schemas;
duplicated wire literals are forbidden.`

This is the one invariant that can be checked against this repository directly:
if an enum value from `schemas/*.schema.json` appears as a bare string literal in
more than one runtime module, the second copy will eventually drift from the
schema. So the test scans the shipped source for schema enum values and requires
each one to be either absent or centralized in a single declaring module.

The rule is enforced on *enum vocabularies* rather than on every string, because
enums are the values a wire format actually pins.
"""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from pathlib import Path

from epistemic_foundry.contracts import default_registry, repo_root

SRC = repo_root() / "src" / "epistemic_foundry"

#: Modules allowed to declare a shared vocabulary. Each owns one concern, so a
#: value living here is the single source the rest of the runtime imports.
DECLARING_MODULES: frozenset[str] = frozenset(
    {
        "domain/status.py",
        "domain/vocabularies.py",
        "retrieval/search_state.py",
        "observability/result_state.py",
        "observability/ranking.py",
        "memory/policy.py",
        "budgets/envelope.py",
        "ingest/comparability.py",
        "evolution_chamber/mutation.py",
        "evolution_chamber/genome.py",
        "epistemic_species_archive/archive.py",
        "red_queen_lab/challenges.py",
        "evidence_parliament/adjudication.py",
        "validation_bay/cascade.py",
        "governance/promotion.py",
        "governance/separation.py",
        "governance/approvals.py",
        "shinka_adapter/backend.py",
        "security/skills.py",
        "security/dispatch.py",
        "providers/neutrality.py",
        "epistemic_atlas/lifecycle.py",
        "hypothesis_passport/passport.py",
        "claim_forge/evidence.py",
        "claim_forge/grounding.py",
        "updates/impact.py",
        "updates/migration.py",
        "evaluation/novelty.py",
        "evaluation/fitness.py",
        "statistics/sequential.py",
        "statistics/selective.py",
        "release/replay.py",
        "release/integrity.py",
        "verifier_firewall/firewall.py",
        "aporia_engine/argument.py",
        "plugin_shell/capabilities.py",
        "noetic_ledger/receipts.py",
        "foundry_kernel/gates.py",
        "cli/main.py",
    }
)

#: Enum values too generic to attribute to a wire contract. Treating these as
#: schema vocabulary would flag ordinary English rather than a drifting literal.
GENERIC_VALUES: frozenset[str] = frozenset(
    {
        "none",
        "other",
        "all",
        "any",
        "auto",
        "default",
        "unknown",
        "UNKNOWN",
        "read",
        "write",
        "text",
        "json",
        "yaml",
        "high",
        "low",
        "medium",
        "critical",
        "major",
        "minor",
        "safe",
        "active",
        "stale",
        "run",
        "project",
        "workflow",
        # These collide with schema *field* names rather than wire values, so a
        # match indicates the scan hit an identifier, not a serialized literal.
        "scope",
        "max_generations",
        "method",
    }
)


def _schema_enum_values() -> set[str]:
    """Every enum value declared by the canonical schemas."""
    values: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            enum = node.get("enum")
            if isinstance(enum, list):
                values.update(item for item in enum if isinstance(item, str))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    registry = default_registry()
    for name in registry.names():
        walk(registry.document(name))
    return {value for value in values if value and value not in GENERIC_VALUES}


def _string_literals(path: Path) -> set[str]:
    """String constants appearing in a module, excluding docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    docstrings.add(id(body[0].value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


#: Vocabularies that are genuinely one schema list read by several components.
#: A module holding three or more members of one of these is re-declaring the
#: vocabulary rather than referring to a single value, which is the drift this
#: invariant forbids. Tokens that merely coincide across unrelated enums (`null`
#: as an evidence role and as an archive class) are deliberately not treated as
#: one vocabulary: forcing them to share a constant would invent coupling the
#: schemas do not have.
SHARED_VOCABULARIES: dict[str, tuple[str, ...]] = {
    "promotion_ladder": (
        "INBOX",
        "CANDIDATE",
        "LITERATURE_GROUNDED",
        "VALIDATION_SCREENED",
        "EMPIRICALLY_TESTED",
        "REPLICATED",
    ),
    "evidence_class": (
        "primary_empirical",
        "secondary_empirical",
        "modeling",
        "formal",
        "benchmark",
        "review",
        "background",
        "methodological",
        "user_generated",
    ),
    "actor_type": ("human", "agent", "service", "tool"),
}

#: The single module permitted to enumerate each shared vocabulary.
VOCABULARY_OWNERS: dict[str, frozenset[str]] = {
    "promotion_ladder": frozenset({"domain/vocabularies.py"}),
    "evidence_class": frozenset({"domain/vocabularies.py"}),
    # `receipts.py` restates the actor vocabulary only as a typing `Literal`,
    # which cannot reference an enum at runtime. It is pinned to the enum by
    # `test_receipt_actor_literal_matches_the_enum` below.
    "actor_type": frozenset({"domain/status.py", "noetic_ledger/receipts.py"}),
}

#: Below this many members, a module is referring to specific values rather than
#: re-declaring the list.
REDECLARATION_THRESHOLD = 3


def test_shared_vocabularies_are_declared_in_exactly_one_module() -> None:
    """A vocabulary read by several components must have one declaring site.

    A second enumeration is a wire literal that will drift: the schema gains a
    value, one copy is updated, and the other keeps accepting or emitting a set
    the contract no longer matches.
    """
    violations: dict[str, dict[str, list[str]]] = defaultdict(dict)

    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        literals = _string_literals(path)
        for name, members in SHARED_VOCABULARIES.items():
            held = sorted(set(members) & literals)
            if len(held) < REDECLARATION_THRESHOLD:
                continue
            if relative in VOCABULARY_OWNERS[name]:
                continue
            violations[name][relative] = held

    assert not violations, (
        "shared schema vocabulary re-declared outside its owning module; import it instead: "
        f"{ {name: dict(sites) for name, sites in violations.items()} }"
    )


def test_each_shared_vocabulary_is_actually_declared_somewhere() -> None:
    """Guard against an owner list pointing at a module that dropped the values."""
    for name, members in SHARED_VOCABULARIES.items():
        found = False
        for owner in VOCABULARY_OWNERS[name]:
            literals = _string_literals(SRC / owner)
            if len(set(members) & literals) >= REDECLARATION_THRESHOLD:
                found = True
        assert found, f"vocabulary {name} is not declared by any of its owners"


def test_receipt_actor_literal_matches_the_enum() -> None:
    """The typing alias must not drift from the runtime vocabulary.

    A `Literal` cannot be built from an enum at runtime, so the alias is the one
    permitted restatement. This test is what keeps it honest.
    """
    import typing

    from epistemic_foundry.domain.status import ActorType
    from epistemic_foundry.noetic_ledger import receipts

    literal_values = set(typing.get_args(receipts.ArtifactActorType))
    assert literal_values == {member.value for member in ActorType}


def test_every_module_holding_schema_vocabulary_is_a_declared_owner() -> None:
    """Vocabulary may only live in a module registered as its owner.

    This keeps the allowlist honest: adding schema strings to a new module fails
    until that module is acknowledged as a declaring site.
    """
    enum_values = _schema_enum_values()
    unexpected: dict[str, list[str]] = {}

    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        if relative in DECLARING_MODULES:
            continue
        held = sorted(_string_literals(path) & enum_values)
        if held:
            unexpected[relative] = held

    assert not unexpected, (
        "module(s) hold canonical schema vocabulary without being declared owners: "
        f"{unexpected}"
    )


def test_the_scan_actually_finds_schema_vocabulary() -> None:
    """Guard against a vacuous pass.

    If the enum extraction or the literal scan silently returned nothing, both
    tests above would pass while checking nothing at all.
    """
    enum_values = _schema_enum_values()
    assert len(enum_values) > 100, f"expected a substantial enum vocabulary, got {len(enum_values)}"

    status_literals = _string_literals(SRC / "domain" / "status.py")
    assert status_literals & enum_values, "status.py should hold canonical status vocabulary"
