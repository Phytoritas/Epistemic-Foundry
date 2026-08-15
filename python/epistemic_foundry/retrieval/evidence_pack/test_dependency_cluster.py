from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from .contracts import (
    EvidencePackContractError,
    build_dependency_clusters,
    validate_evidence_dependency_cluster,
    validate_evidence_dependency_cluster_shape,
    validate_evidence_dependency_clusters_from_sources,
)

ROOT = Path(__file__).resolve().parents[4]
CREATED_AT = "2026-07-31T00:00:00Z"
RUN_ID = "RUN-1"


class DuplicateItemsMapping(Mapping[str, object]):
    def __init__(self, items: list[tuple[str, object]]) -> None:
        self._items = items

    def __getitem__(self, key: str) -> object:
        for candidate, value in reversed(self._items):
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(dict(self._items))

    def __len__(self) -> int:
        return len(dict(self._items))

    def items(self) -> list[tuple[str, object]]:
        return list(self._items)


def cluster_schema_validator() -> Draft202012Validator:
    schema = json.loads(
        (ROOT / "schemas" / "evidence-dependency-cluster.schema.json").read_text(
            encoding="utf-8"
        )
    )
    return Draft202012Validator(schema)


def unit(evidence_id: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "evidence_id": evidence_id,
        "source_span_id": f"SPAN-{evidence_id}",
        "canonical_source_key": f"SRC-{evidence_id}",
        "source_version": "v1",
        "peer_review_status": "PUBLISHED",
        "publication_family_id": None,
        "team_series_id": None,
        "dataset_ids": [],
        "cohort_ids": [],
        "experiment_ids": [],
        "reused_artifact_ids": [],
        "review_of_evidence_ids": [],
        "derived_from_evidence_ids": [],
        "origin_result_ids": [f"RES-{evidence_id}"],
        "provenance_refs": [f"DOC-{evidence_id}"],
    }
    value.update(overrides)
    return value


def preprint_family_units() -> list[dict[str, object]]:
    return [
        unit(
            "EVN-0001",
            peer_review_status="PREPRINT",
            publication_family_id="FAM-1",
            dataset_ids=["D1"],
        ),
        unit("EVN-0002", publication_family_id="FAM-1", dataset_ids=["D1"]),
        unit("EVN-0003", dataset_ids=["D2"]),
    ]


def build(units: list[dict[str, object]], **kwargs: object):
    return build_dependency_clusters(
        units, run_id=RUN_ID, created_at=CREATED_AT, **kwargs
    )


def reseal_cluster(payload: dict[str, object]) -> dict[str, object]:
    preimage = {key: value for key, value in payload.items() if key != "cluster_hash"}
    encoded = json.dumps(
        preimage,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    payload["cluster_hash"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    return payload


def test_dependency_cluster_test_shared_dataset_and_preprint_family_merge() -> None:
    clusters = build(preprint_family_units())

    assert len(clusters) == 1
    payload = clusters[0].payload
    assert payload["evidence_ids"] == ["EVN-0001", "EVN-0002"]
    assert payload["dependency_types"] == ["SAME_DATASET", "PREPRINT_JOURNAL_VERSION"]
    assert payload["representative_evidence_ids"] == ["EVN-0002"]
    assert payload["independent_unit_count"] == 1
    assert payload["support_count_raw"] == 2
    assert payload["support_count_adjusted"] == 1.0
    assert payload["independence_confidence"] == 0.95
    assert payload["provenance_refs"] == ["DOC-EVN-0001", "DOC-EVN-0002"]


def test_dependency_cluster_test_singletons_have_no_cluster_record() -> None:
    clusters = build([unit("EVN-1"), unit("EVN-2")])

    assert clusters == ()


def test_dependency_cluster_test_transitive_union_uses_weakest_confidence() -> None:
    units = [
        unit("EVN-A", peer_review_status="PREPRINT", team_series_id="TS-1"),
        unit("EVN-B", team_series_id="TS-1", reused_artifact_ids=["M-1"]),
        unit(
            "EVN-C",
            peer_review_status="REPORT",
            reused_artifact_ids=["M-1"],
            derived_from_evidence_ids=["EVN-D"],
        ),
        unit("EVN-D"),
        unit("EVN-E", peer_review_status="REVIEW", review_of_evidence_ids=["EVN-D"]),
    ]

    clusters = build(units)

    assert len(clusters) == 1
    payload = clusters[0].payload
    assert payload["evidence_ids"] == ["EVN-A", "EVN-B", "EVN-C", "EVN-D", "EVN-E"]
    assert payload["dependency_types"] == [
        "REVIEW_PRIMARY_CHAIN",
        "SAME_TEAM_SERIES",
        "MODEL_OR_CODE_REUSE",
        "CITATION_DEPENDENCY",
    ]
    assert payload["representative_evidence_ids"] == ["EVN-B"]
    assert payload["independence_confidence"] == 0.6
    assert payload["support_count_raw"] == 5
    assert payload["support_count_adjusted"] == 1.0


def test_dependency_cluster_test_declared_unknown_link_merges_with_provenance() -> None:
    units = [unit("EVN-1"), unit("EVN-2")]
    link = {
        "source_evidence_id": "EVN-1",
        "target_evidence_id": "EVN-2",
        "dependency_type": "UNKNOWN",
        "provenance_ref": "AUDIT-7",
    }

    clusters = build(units, declared_links=[link])

    payload = clusters[0].payload
    assert payload["dependency_types"] == ["UNKNOWN"]
    assert payload["independence_confidence"] == 0.5
    assert "AUDIT-7" in payload["provenance_refs"]


@pytest.mark.parametrize(
    ("link", "code"),
    [
        (
            {
                "source_evidence_id": "EVN-1",
                "target_evidence_id": "EVN-9",
                "dependency_type": "UNKNOWN",
                "provenance_ref": "AUDIT-7",
            },
            "LINK_TARGET_UNKNOWN",
        ),
        (
            {
                "source_evidence_id": "EVN-1",
                "target_evidence_id": "EVN-1",
                "dependency_type": "UNKNOWN",
                "provenance_ref": "AUDIT-7",
            },
            "LINK_SELF_REFERENCE",
        ),
        (
            {
                "source_evidence_id": "EVN-1",
                "target_evidence_id": "EVN-2",
                "dependency_type": "SHARED",
                "provenance_ref": "AUDIT-7",
            },
            "DEPENDENCY_TYPE_UNKNOWN",
        ),
    ],
)
def test_dependency_cluster_test_declared_link_failures(
    link: dict[str, object], code: str
) -> None:
    with pytest.raises(EvidencePackContractError) as raised:
        build([unit("EVN-1"), unit("EVN-2")], declared_links=[link])
    assert raised.value.code == code


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("review_of_evidence_ids", "REVIEW_TARGET_UNKNOWN"),
        ("derived_from_evidence_ids", "CITATION_TARGET_UNKNOWN"),
    ],
)
def test_dependency_cluster_test_reference_targets_must_exist(
    field: str, code: str
) -> None:
    with pytest.raises(EvidencePackContractError) as raised:
        build([unit("EVN-1", **{field: ["EVN-MISSING"]})])
    assert raised.value.code == code


def test_dependency_cluster_test_duplicate_evidence_ids_fail_closed() -> None:
    with pytest.raises(EvidencePackContractError) as raised:
        build([unit("EVN-1"), unit("EVN-1")])
    assert raised.value.code == "EVIDENCE_ID_DUPLICATE"


def test_dependency_cluster_test_duplicate_projected_keys_fail_closed() -> None:
    source = unit("EVN-1")
    duplicate = DuplicateItemsMapping(
        [("evidence_id", "EVN-shadow"), *source.items()]
    )

    with pytest.raises(EvidencePackContractError) as raised:
        build_dependency_clusters(
            [duplicate], run_id=RUN_ID, created_at=CREATED_AT
        )

    assert raised.value.code == "INPUT_INVALID"


def test_dependency_cluster_test_identity_strings_are_not_trimmed() -> None:
    clusters = build(
        [
            unit("EVN-1", dataset_ids=["D1"]),
            unit(" EVN-1 ", dataset_ids=["D1"]),
        ]
    )

    assert clusters[0].payload["evidence_ids"] == [" EVN-1 ", "EVN-1"]


def test_dependency_cluster_test_whitespace_only_identity_is_rejected() -> None:
    with pytest.raises(EvidencePackContractError) as raised:
        build([unit("   ")])

    assert raised.value.code == "INPUT_INVALID"


def test_dependency_cluster_test_unknown_unit_field_fails_closed() -> None:
    broken = unit("EVN-1")
    broken["surprise"] = True
    with pytest.raises(EvidencePackContractError) as raised:
        build([broken])
    assert raised.value.code == "FIELD_SET_INVALID"


def test_dependency_cluster_test_unit_order_cannot_change_canonical_bytes() -> None:
    units = preprint_family_units()
    forward = build(units)
    reversed_clusters = build(list(reversed(units)))

    assert [entry.canonical_bytes for entry in forward] == [
        entry.canonical_bytes for entry in reversed_clusters
    ]


def test_dependency_cluster_test_output_is_schema_valid_and_revalidates() -> None:
    validator = cluster_schema_validator()
    for cluster in build(preprint_family_units()):
        payload = cluster.payload
        validator.validate(payload)
        assert (
            validate_evidence_dependency_cluster(payload).canonical_bytes
            == cluster.canonical_bytes
        )


def test_dependency_cluster_shape_validation_grants_no_source_authority() -> None:
    units = preprint_family_units()
    payload = build(units)[0].payload
    payload["support_count_adjusted"] = 0.5
    reseal_cluster(payload)

    assert (
        validate_evidence_dependency_cluster_shape(payload).payload[
            "support_count_adjusted"
        ]
        == 0.5
    )
    with pytest.raises(EvidencePackContractError) as raised:
        validate_evidence_dependency_clusters_from_sources(
            [payload],
            units=units,
            run_id=RUN_ID,
            created_at=CREATED_AT,
        )

    assert raised.value.code == "CLUSTER_RECONSTRUCTION_MISMATCH"


def test_dependency_cluster_source_validation_returns_rebuilt_records() -> None:
    units = preprint_family_units()
    clusters = build(units)

    rebuilt = validate_evidence_dependency_clusters_from_sources(
        [entry.payload for entry in clusters],
        units=units,
        run_id=RUN_ID,
        created_at=CREATED_AT,
    )

    assert [entry.canonical_bytes for entry in rebuilt] == [
        entry.canonical_bytes for entry in clusters
    ]


def test_dependency_cluster_test_canonical_example_is_schema_valid() -> None:
    example = json.loads(
        (ROOT / "examples" / "sample_evidence-dependency-cluster.json").read_text(
            encoding="utf-8"
        )
    )
    cluster_schema_validator().validate(example)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda value: value.update(support_count_adjusted=2.5),
            "ADJUSTED_COUNT_INVALID",
        ),
        (
            lambda value: value.update(rationale="tampered rationale"),
            "CLUSTER_HASH_MISMATCH",
        ),
        (
            lambda value: value.update(
                evidence_ids=list(reversed(value["evidence_ids"]))
            ),
            "EVIDENCE_ORDER_INVALID",
        ),
        (
            lambda value: value.update(representative_evidence_ids=["EVN-9999"]),
            "REPRESENTATIVE_NOT_MEMBER",
        ),
        (
            lambda value: value.update(
                dependency_types=list(reversed(value["dependency_types"]))
            ),
            "DEPENDENCY_TYPE_ORDER_INVALID",
        ),
        (lambda value: value.update(independence_confidence=1.5), "INPUT_INVALID"),
        (lambda value: value.update(extra_field=1), "FIELD_SET_INVALID"),
        (
            lambda value: value.update(independent_unit_count=3),
            "INDEPENDENT_COUNT_INVALID",
        ),
    ],
)
def test_dependency_cluster_test_tamper_fails_closed(mutation, code: str) -> None:
    payload = build(preprint_family_units())[0].payload
    mutation(payload)
    with pytest.raises(EvidencePackContractError) as raised:
        validate_evidence_dependency_cluster(payload)
    assert raised.value.code == code


def test_dependency_cluster_test_same_inputs_replay_identically() -> None:
    first = build(preprint_family_units())
    second = build(preprint_family_units())

    assert [entry.canonical_bytes for entry in first] == [
        entry.canonical_bytes for entry in second
    ]
