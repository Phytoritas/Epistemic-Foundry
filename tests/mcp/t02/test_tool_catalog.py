"""T02 catalog integrity: exact nine mutating tools, verified end to end."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from epistemic_foundry.application.mcp_common import (
    PROTOCOL_VERSION,
    CatalogIntegrityError,
    load_catalog,
)
from epistemic_foundry.application.mcp_mutating import (
    EXPECTED_MUTATING_TOOL_COUNT,
    MUTATING_SIDE_EFFECT_CLASS,
    MUTATION_ERROR_CODES,
    MUTATION_ERROR_MAPPING,
    MutatingToolCatalog,
    load_catalog_set,
    load_mutating_catalog,
)

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "contracts/mcp/t02/tool-catalog.yaml"
CATALOG_SET_PATH = ROOT / "contracts/mcp/catalog-set.yaml"


def _catalog_document() -> dict:
    return yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))


def _rebuild(document: dict) -> MutatingToolCatalog:
    input_schemas = {
        str(row["input_schema"]): json.loads(
            (ROOT / str(row["input_schema"])).read_text(encoding="utf-8")
        )
        for row in document["tools"]
    }
    return MutatingToolCatalog(
        common_input_schema=json.loads(
            (ROOT / str(document["common_input_schema"])).read_text(encoding="utf-8")
        ),
        document=document,
        input_schemas=input_schemas,
        result_schema=json.loads(
            (ROOT / str(document["mutation_result_schema"])).read_text(encoding="utf-8")
        ),
        error_details_schema=json.loads(
            (ROOT / str(document["mutation_error_details_schema"])).read_text(
                encoding="utf-8"
            )
        ),
        envelope_result_schema=json.loads(
            (ROOT / "contracts/mcp/t01/foundry-mcp-tool-result.schema.json").read_text(
                encoding="utf-8"
            )
        ),
        envelope_error_schema=json.loads(
            (ROOT / "contracts/mcp/t01/foundry-mcp-tool-error.schema.json").read_text(
                encoding="utf-8"
            )
        ),
    )


def test_catalog_declares_exactly_nine_mutating_tools() -> None:
    catalog = load_mutating_catalog(ROOT)

    assert len(catalog.tool_names) == EXPECTED_MUTATING_TOOL_COUNT
    assert len(set(catalog.tool_names)) == EXPECTED_MUTATING_TOOL_COUNT
    for spec in catalog.tools.values():
        assert spec.side_effect_class == MUTATING_SIDE_EFFECT_CLASS
        assert spec.capability.startswith("mcp.write.")
        assert spec.data_schema_refs


def test_every_tool_binds_a_resolvable_input_schema() -> None:
    catalog = load_mutating_catalog(ROOT)

    for name, spec in catalog.tools.items():
        schema = catalog.input_schema(name)
        assert (ROOT / spec.input_schema_path).is_file()
        required = set(schema["required"])
        assert {
            "workspace_id",
            "dry_run",
            "expected_revision",
            "idempotency_key",
            "approval_record_ids",
            "target_ref",
            "arguments",
        } <= required
        # A client may never supply server-created authority or evidence.
        assert "capability_lease" not in schema["properties"]
        assert "effect_receipt" not in schema["properties"]


def test_expected_revision_nullability_follows_the_catalog() -> None:
    catalog = load_mutating_catalog(ROOT)

    for name, spec in catalog.tools.items():
        declared = catalog.input_schema(name)["properties"]["expected_revision"]
        if spec.expected_revision_required:
            assert declared["type"] == "string"
        else:
            assert declared["type"] == "null"


def test_the_sealed_t01_catalog_is_untouched_and_disjoint() -> None:
    sealed = load_catalog(ROOT)
    mutating = load_mutating_catalog(ROOT)

    assert len(sealed.tool_names) == 13
    assert not set(sealed.tool_names) & set(mutating.tool_names)
    for spec in sealed.tools.values():
        assert spec.side_effect_class != MUTATING_SIDE_EFFECT_CLASS


def test_catalog_set_orders_and_counts_the_composed_surface() -> None:
    catalog_set = load_catalog_set(ROOT)

    assert catalog_set["global_exact_count"] == 22
    assert [entry["exact_count"] for entry in catalog_set["catalogs"]] == [13, 9]
    assert catalog_set["merge_order"] == [
        entry["catalog_id"] for entry in catalog_set["catalogs"]
    ]


def test_catalog_set_holds_no_tool_name_literal() -> None:
    text = CATALOG_SET_PATH.read_text(encoding="utf-8")
    mutating = load_mutating_catalog(ROOT)
    sealed = load_catalog(ROOT)

    for name in (*mutating.tool_names, *sealed.tool_names):
        assert name not in text


def test_generated_descriptor_projection_matches_the_catalog() -> None:
    from epistemic_foundry.application.mcp_common import tool_descriptors

    generated = json.loads(
        (
            ROOT
            / "packages/plugin-host/src/mcp/write/generated/t02-tool-descriptors.json"
        ).read_text(encoding="utf-8")
    )
    catalog = load_mutating_catalog(ROOT)
    catalog_set = load_catalog_set(ROOT)

    assert generated == {
        "catalog_set": {
            "catalogs": [
                {
                    "catalog_id": entry["catalog_id"],
                    "descriptor_projection": entry["descriptor_projection"],
                    "exact_count": entry["exact_count"],
                }
                for entry in catalog_set["catalogs"]
            ],
            "global_exact_count": catalog_set["global_exact_count"],
            "merge_order": list(catalog_set["merge_order"]),
            "set_id": catalog_set["set_id"],
        },
        "generated_from": "contracts/mcp/t02/tool-catalog.yaml",
        "protocol_version": PROTOCOL_VERSION,
        "tools": tool_descriptors(catalog),
    }


def test_mutation_error_codes_map_onto_the_sealed_enum() -> None:
    sealed_error_schema = json.loads(
        (ROOT / "contracts/mcp/t01/foundry-mcp-tool-error.schema.json").read_text(
            encoding="utf-8"
        )
    )
    sealed_enum = set(sealed_error_schema["properties"]["error_code"]["enum"])
    details_schema = json.loads(
        (
            ROOT / "contracts/mcp/t02/schemas/mutation-error-details.schema.json"
        ).read_text(encoding="utf-8")
    )

    assert set(details_schema["properties"]["mutation_error_code"]["enum"]) == set(
        MUTATION_ERROR_CODES
    )
    assert set(MUTATION_ERROR_MAPPING) == set(MUTATION_ERROR_CODES)
    assert set(MUTATION_ERROR_MAPPING.values()) <= sealed_enum


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda d: d["tools"].pop(), "cardinality"),
        (lambda d: d.__setitem__("mutating_tool_count", 8), "cardinality"),
        (lambda d: d.__setitem__("protocol_version", "1999-01-01"), "protocol version"),
        (
            lambda d: d["tools"][0].__setitem__("side_effect_class", "PURE_READ"),
            "MUTATING_EFFECT",
        ),
        (
            lambda d: d["tools"][0].__setitem__("approval_class", "SOMETIMES"),
            "approval class",
        ),
        (lambda d: d["tools"][0].__setitem__("risk_class", "spicy"), "risk class"),
        (lambda d: d.__setitem__("extra_field", True), "field set invalid"),
        (lambda d: d["tools"][0].pop("capability"), "field set invalid"),
    ],
)
def test_a_drifted_catalog_fails_closed(mutate, fragment: str) -> None:
    document = _catalog_document()
    mutate(document)

    with pytest.raises(CatalogIntegrityError) as caught:
        _rebuild(document)

    assert fragment in str(caught.value)


def test_a_duplicate_tool_name_fails_closed() -> None:
    document = _catalog_document()
    document["tools"].append(copy.deepcopy(document["tools"][0]))
    document["mutating_tool_count"] = len(document["tools"])

    with pytest.raises(CatalogIntegrityError) as caught:
        _rebuild(document)

    assert "duplicate" in str(caught.value)


def test_a_drifted_catalog_set_count_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "contracts/mcp/t01").mkdir(parents=True)
    (tmp_path / "contracts/mcp/t02").mkdir(parents=True)
    for relative in (
        "contracts/mcp/t01/tool-catalog.yaml",
        "contracts/mcp/t02/tool-catalog.yaml",
    ):
        (tmp_path / relative).write_text(
            (ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8"
        )
    document = yaml.safe_load(CATALOG_SET_PATH.read_text(encoding="utf-8"))
    document["catalogs"][1]["exact_count"] = 8
    document["global_exact_count"] = 21
    (tmp_path / "contracts/mcp/catalog-set.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(CatalogIntegrityError) as caught:
        load_catalog_set(tmp_path)

    assert "does not match" in str(caught.value)
