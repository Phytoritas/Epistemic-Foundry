"""schema_and_type_check — the positional vocabulary matches the canonical schema.

The gate reads the one status token it reasons about positionally out of the
attestation schema that declares it, derives the signing status through the sealed
release-provenance surface, reads its maturity floor from the acceptance matrix,
and grounds the promotion authority in the canonical capability the
evolution-authority registry declares (EF4-I22).  This suite pins those
groundings, proves the gate's refusal codes are internally closed — every code it
raises is a declared ``FINDING_CODES`` entry — and proves no canonical enum value
appears as a bare literal in the shipped module.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.governance.evolution_authority.registry import (
    PROMOTION_COMMIT_CAPABILITY,
)
from epistemic_foundry.release.provenance import derive_signing_status

from v4_z05 import zero_trust_release as mod

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

#: The 288-lens audit is a report artifact, not a canonical schema artifact, so its
#: own field names and status tokens are report vocabulary that only coincidentally
#: collide with unrelated schema enum values.  Reading the audit means naming these,
#: so they are excluded from the enum-literal ban exactly as ``GENERIC_VALUES`` is.
AUDIT_REPORT_VOCABULARY = frozenset({"CONDITIONAL", "results"})


def test_pass_status_token_is_read_positionally_from_the_attestation_schema() -> None:
    enum = default_registry().document("attestation")["properties"]["overall_status"][
        "enum"
    ]
    # The passing rung leads the attestation status ladder, and the gate reads it
    # positionally rather than holding the literal.
    assert mod.reconciled_status_token() == enum[0]
    assert mod._pass_status_token() == enum[0]


def test_unsigned_status_is_derived_by_the_sealed_provenance_surface() -> None:
    # The fail-closed signing status is whatever the sealed release-provenance
    # surface derives over an empty signature set, never a literal held here.
    assert mod.UNSIGNED_STATUS == derive_signing_status([])


def test_maturity_floor_is_read_from_the_acceptance_matrix() -> None:
    import yaml

    from epistemic_foundry.contracts import repo_root

    document = yaml.safe_load(
        (repo_root() / "manifests/acceptance_matrix.yaml").read_text(encoding="utf-8")
    )
    assert mod.release_level_floor() == document["status_of_this_bundle"]


def test_promotion_capability_is_grounded_in_the_registry_constant() -> None:
    # The authority gate keys off the canonical promotion-commit capability the
    # evolution-authority registry declares, never a literal of its own.
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "PROMOTION_COMMIT_CAPABILITY" in source
    assert PROMOTION_COMMIT_CAPABILITY not in _string_literals(MODULE_PATH)


def test_attestation_schema_kind_resolves_in_the_registry() -> None:
    assert default_registry().document("attestation")["title"]
    assert default_registry().document("plugin-release-provenance")["title"]


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
    except mod.ZeroTrustReleaseError as error:
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
    return {
        value
        for value in values
        if value
        and value not in GENERIC_VALUES
        and value not in AUDIT_REPORT_VOCABULARY
    }


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
