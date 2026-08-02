"""schema_and_type_check — the positional vocabulary matches the canonical schema.

The terminal gate reads the maturity floor from the acceptance matrix and the one
passing status token positionally from the attestation schema, both through the
composed Z05 surface, and derives the fail-closed signing status through the sealed
release-provenance surface (EF4-I22).  This suite pins those groundings, proves the
gate's refusal codes are internally closed — every code it raises is a declared
``FINDING_CODES`` entry — proves its own forbidden-maturity-claim vocabulary is not
a canonical wire enum, and proves no canonical enum value appears as a bare literal
in the shipped module.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.contracts import default_registry, repo_root

from v4_z05.zero_trust_release import (
    UNSIGNED_STATUS,
    reconciled_status_token,
    release_level_floor,
)
from v4_z06 import truthful_release as mod

MODULE_PATH = Path(mod.__file__)

GENERIC_VALUES = frozenset(
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
        "scope",
        "max_generations",
        "method",
    }
)


def test_maturity_floor_is_read_through_the_composed_z05_surface() -> None:
    import yaml

    document = yaml.safe_load(
        (repo_root() / "manifests/acceptance_matrix.yaml").read_text(encoding="utf-8")
    )
    # The terminal gate never restates the floor; it reads the Z05 surface, which
    # reads the acceptance matrix.
    assert release_level_floor() == document["status_of_this_bundle"]


def test_pass_token_is_read_through_the_composed_z05_surface() -> None:
    enum = default_registry().document("attestation")["properties"]["overall_status"][
        "enum"
    ]
    assert reconciled_status_token() == enum[0]


def test_unsigned_status_is_derived_by_the_sealed_provenance_surface() -> None:
    from epistemic_foundry.release.provenance import derive_signing_status

    assert UNSIGNED_STATUS == derive_signing_status([])


def test_forbidden_maturity_claims_are_not_canonical_wire_enums() -> None:
    # The forbidden-claim vocabulary is Z06's own honesty vocabulary; holding it is
    # only legitimate if it does not collide with a canonical schema enum value.
    collisions = sorted(mod.FORBIDDEN_MATURITY_CLAIMS & _schema_enum_values())
    assert not collisions, (
        f"forbidden-claim tokens collide with schema enums: {collisions}"
    )


def test_every_raised_finding_code_is_declared() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    raised: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_fail"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            raised.add(node.args[0].value)
    assert raised, "the scan found no _fail codes"
    undeclared = sorted(raised - set(mod.FINDING_CODES))
    assert not undeclared, f"undeclared finding codes raised: {undeclared}"


def test_finding_codes_are_all_documented_with_a_reason() -> None:
    for code, why in mod.FINDING_CODES.items():
        assert code == code.upper()
        assert isinstance(why, str) and len(why) > 50


def test_fail_refuses_an_undeclared_code() -> None:
    try:
        mod._fail("NOT_A_DECLARED_CODE", "should never surface")
    except mod.TruthfulReleaseError as error:
        assert error.code == "INPUT_INVALID"
    else:  # pragma: no cover - the guard must refuse
        raise AssertionError("an undeclared finding code was accepted")


def _schema_enum_values() -> set[str]:
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
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def test_module_holds_no_canonical_enum_literal() -> None:
    """The shipped module must read every canonical token, never restate one."""
    held = sorted(_string_literals(MODULE_PATH) & _schema_enum_values())
    assert not held, f"canonical enum values appear as literals: {held}"
