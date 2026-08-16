"""The composed tools/list surface: 13 sealed + 11 mutating, in declared order."""

from __future__ import annotations

from pathlib import Path

from epistemic_foundry.application.mcp_common import load_catalog, tool_descriptors
from epistemic_foundry.application.mcp_mutating import (
    MUTATING_SIDE_EFFECT_CLASS,
    load_catalog_set,
    load_mutating_catalog,
)

ROOT = Path(__file__).resolve().parents[3]


def _composed() -> list[dict]:
    return [
        *tool_descriptors(load_catalog(ROOT)),
        *tool_descriptors(load_mutating_catalog(ROOT)),
    ]


def test_composed_surface_has_exactly_twenty_four_unique_tools() -> None:
    composed = _composed()
    names = [descriptor["name"] for descriptor in composed]

    assert len(composed) == load_catalog_set(ROOT)["global_exact_count"] == 24
    assert len(set(names)) == 24


def test_merge_order_places_the_sealed_surface_first() -> None:
    catalog_set = load_catalog_set(ROOT)
    sealed_count = catalog_set["catalogs"][0]["exact_count"]
    composed = _composed()

    head = {descriptor["name"] for descriptor in composed[:sealed_count]}
    tail = {descriptor["name"] for descriptor in composed[sealed_count:]}

    assert head == set(load_catalog(ROOT).tool_names)
    assert tail == set(load_mutating_catalog(ROOT).tool_names)


def test_mutating_descriptors_advertise_their_side_effect_class() -> None:
    catalog = load_mutating_catalog(ROOT)

    for descriptor in tool_descriptors(catalog):
        annotations = descriptor["annotations"]
        assert annotations["sideEffectClass"] == MUTATING_SIDE_EFFECT_CLASS
        assert annotations["readOnlyHint"] is False
        assert annotations["capability"] == catalog.spec(descriptor["name"]).capability


def test_sealed_descriptors_stay_read_only_in_the_composed_surface() -> None:
    sealed = load_catalog(ROOT)

    for descriptor in tool_descriptors(sealed):
        annotations = descriptor["annotations"]
        assert annotations["sideEffectClass"] != MUTATING_SIDE_EFFECT_CLASS
        assert annotations["readOnlyHint"] == (
            annotations["sideEffectClass"] == "PURE_READ"
        )


def test_every_descriptor_carries_its_canonical_input_schema() -> None:
    catalog = load_mutating_catalog(ROOT)

    for descriptor in tool_descriptors(catalog):
        assert descriptor["inputSchema"] == catalog.input_schema(descriptor["name"])
        assert descriptor["inputSchema"]["additionalProperties"] is False
