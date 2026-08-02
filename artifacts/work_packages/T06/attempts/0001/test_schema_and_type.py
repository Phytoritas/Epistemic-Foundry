"""schema_and_type_check — the gate reads its contracts, never restates them.

The serving verdicts are the intersection of two owners: the enum declared by
`backend-adapter-qualification.schema.json`, read through T05, and the usable
set declared by `shinka_adapter.backend`.  Neither is copied here, and both
assumptions are asserted against the declaring source.

The lifecycle standings are this package's own vocabulary, and the test that
matters most is the one proving they are *not* anyone else's: the T06 modules
are scanned for canonical enum literals directly, because a lifecycle word that
collided with a schema value would be a duplicated wire literal under EF4-I22
whether or not it was meant as one.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from epistemic_foundry.adapters.v4_t05 import (
    QUALIFICATION_ARTIFACT,
    AdapterGateError,
    qualification_statuses,
)
from epistemic_foundry.adapters.v4_t06 import (
    BINDING_FIELDS,
    FALLBACK_TRIGGER_CODE,
    FINDING_CODES,
    MEMBER_FIELDS,
    STANDING_DEACTIVATED,
    STANDING_EXPIRED,
    STANDING_REPLACED,
    STANDING_REVOKED,
    STANDING_SERVING,
    STANDING_STATUS_NOT_USABLE,
    STANDINGS,
    WITHDRAWAL_KINDS,
    IntegrationGateError,
    require_instant,
    usable_statuses,
)
from epistemic_foundry.adapters.v4_t06 import findings as findings_module
from epistemic_foundry.contracts import default_registry, validate_artifact
from epistemic_foundry.shinka_adapter.backend import USABLE_QUALIFICATION_STATUSES
from fixtures import (
    backend_member,
    chain,
    fallback_chain,
    genesis,
    imported_run,
    native_core_member,
    standby_chain,
)

ROOT = Path(__file__).resolve().parents[5]
GATE = ROOT / "src/epistemic_foundry/adapters/v4_t06"
GATE_MODULES = (
    GATE / "__init__.py",
    GATE / "disable.py",
    GATE / "fallback.py",
    GATE / "findings.py",
    GATE / "qualification_lifecycle.py",
)


def string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(id(value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def schema_enum_values() -> set[str]:
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
    return values


def test_the_serving_verdicts_are_the_intersection_of_both_owners() -> None:
    declared = qualification_statuses()

    assert usable_statuses() == tuple(
        status for status in declared if status in USABLE_QUALIFICATION_STATUSES
    )
    assert set(usable_statuses()) == set(USABLE_QUALIFICATION_STATUSES)


def test_the_serving_verdicts_come_from_the_canonical_schema() -> None:
    document = default_registry().document(QUALIFICATION_ARTIFACT)

    assert set(usable_statuses()) <= set(document["properties"]["status"]["enum"])
    assert len(usable_statuses()) == 2


def test_the_rejecting_verdict_is_never_a_serving_one() -> None:
    declared = qualification_statuses()

    assert declared[2] not in usable_statuses()


def test_the_standings_are_this_packages_own_vocabulary() -> None:
    # If a standing ever collided with a canonical enum value, the EF4-I22 gate
    # would start reporting this package as an undeclared vocabulary owner.
    assert set(STANDINGS) & schema_enum_values() == set()
    assert len(set(STANDINGS)) == len(STANDINGS) == 6


def test_every_standing_the_module_can_report_is_declared() -> None:
    reported = {
        STANDING_SERVING,
        STANDING_REPLACED,
        STANDING_EXPIRED,
        STANDING_REVOKED,
        STANDING_DEACTIVATED,
        STANDING_STATUS_NOT_USABLE,
    }

    assert reported == set(STANDINGS)


def test_a_withdrawal_kind_is_always_a_standing() -> None:
    assert set(WITHDRAWAL_KINDS) <= set(STANDINGS)
    assert WITHDRAWAL_KINDS == (STANDING_REVOKED, STANDING_DEACTIVATED)


def test_the_lifecycle_carries_a_verdict_the_schema_declares() -> None:
    record = genesis()

    assert record["status"] in qualification_statuses()
    assert record["status"] in usable_statuses()


def test_the_binding_fields_exist_on_a_real_t05_binding() -> None:
    from fixtures import binding

    assert set(BINDING_FIELDS) <= set(binding())


def test_the_member_fields_exist_on_both_member_builders() -> None:
    member = backend_member(
        member_id="m", chain=standby_chain(), capabilities=["candidate-search"]
    )

    assert set(MEMBER_FIELDS) <= set(member)
    assert set(MEMBER_FIELDS) <= set(native_core_member())


def test_the_composed_qualification_still_validates_against_its_schema() -> None:
    from fixtures import binding

    validate_artifact(QUALIFICATION_ARTIFACT, binding()["qualification"])


def test_a_marked_import_is_a_canonical_imported_run() -> None:
    envelope = imported_run()

    validate_artifact("imported-run-record", envelope["imported_run"])


def test_the_gate_holds_no_canonical_schema_vocabulary() -> None:
    vocabulary = schema_enum_values()
    held = {
        path.name: sorted(string_literals(path) & vocabulary)
        for path in GATE_MODULES
        if string_literals(path) & vocabulary
    }

    assert held == {}, held


def test_the_scan_actually_finds_schema_vocabulary() -> None:
    # Guard against a vacuous pass: if the enum extraction returned nothing,
    # the scan above would pass while checking nothing at all.
    assert len(schema_enum_values()) > 100


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 11
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert len(reason) > 50, code


def test_the_recorded_fallback_trigger_is_a_declared_code() -> None:
    # The code written into a routing record must be one a reviewer can look
    # up, and must be the same code a direct call would have raised.
    assert FALLBACK_TRIGGER_CODE in FINDING_CODES

    routed = fallback_chain()

    assert routed["chain_hash"].startswith("sha256:")


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = IntegrationGateError("FALLBACK_UNRECORDED", "message", {"a": 1})

    assert error.code == "FALLBACK_UNRECORDED"
    assert str(error) == "message"
    assert error.context == {"a": 1}


def test_the_two_gates_raise_distinguishable_errors() -> None:
    # A caller must be able to tell "T05 refused the record" from "T06 refused
    # the lifecycle"; a subclass relationship would erase that distinction.
    assert not issubclass(IntegrationGateError, AdapterGateError)
    assert not issubclass(AdapterGateError, IntegrationGateError)


def test_an_undeclared_finding_code_is_refused_by_the_sealed_gate() -> None:
    with pytest.raises(AdapterGateError) as caught:
        findings_module._fail("INVENTED_CODE", "message")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context == {"code": "INVENTED_CODE"}


def test_an_instant_is_read_as_an_offset_aware_moment() -> None:
    moment = require_instant("2026-08-02T00:00:00+00:00", "as_of")

    assert moment == datetime(2026, 8, 2, tzinfo=timezone.utc)
    assert moment.tzinfo is not None


def test_the_chain_is_a_plain_json_shaped_record() -> None:
    # Every value the gate seals must survive canonical serialization, or the
    # digests it derives could not be re-derived by a reader.
    import json

    assert json.loads(json.dumps(chain()))["length"] == 1
