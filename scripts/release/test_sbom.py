"""Z02 sbom_test: deterministic, complete, fail-closed bill of materials.

This required-check module proves, through the deterministic
:mod:`z02_release_engine`, that the SBOM covers every shipped payload file, is
hash-re-derivable, and refuses any bill of materials that omits, adds, or
misrepresents a component.  It reads the payload rooted at
``plugins/epistemic-foundry`` and states no host or platform of its own.
"""

from __future__ import annotations

import copy

import z02_release_engine as engine

FIXED_TS = "1970-01-01T00:00:00Z"


def test_sbom_is_deterministic_and_hash_rederivable() -> None:
    first = engine.build_sbom(generated_at=FIXED_TS)
    second = engine.build_sbom(generated_at=FIXED_TS)
    assert first == second
    assert first["sbom_sha256"] == second["sbom_sha256"]
    recomputed = engine.record_sha256(
        {k: v for k, v in first.items() if k != "sbom_sha256"}
    )
    assert recomputed == first["sbom_sha256"]


def test_sbom_covers_every_payload_file() -> None:
    sbom = engine.build_sbom(generated_at=FIXED_TS)
    report = engine.sbom_completeness_report(sbom)
    assert report["complete"] is True
    assert report["refusals"] == []
    assert sbom["component_count"] == report["payload_file_count"] > 0


def test_sbom_component_digests_match_the_payload_bytes() -> None:
    sbom = engine.build_sbom(generated_at=FIXED_TS)
    live = {entry["path"]: entry["sha256"] for entry in engine.payload_inventory()}
    for component in sbom["components"]:
        assert component["sha256"] == live[component["path"]]
        assert component["sha256"].startswith("sha256:")


def test_sbom_is_labelled_unverified_reference() -> None:
    sbom = engine.build_sbom(generated_at=FIXED_TS)
    assert sbom["sbom_status"] == "UNVERIFIED_REFERENCE_SBOM"
    assert sbom["declaring_source"] == engine.PROVENANCE_SCHEMA


def test_sbom_missing_component_is_refused_fail_closed() -> None:
    sbom = engine.build_sbom(generated_at=FIXED_TS)
    mutated = copy.deepcopy(sbom)
    mutated["components"] = mutated["components"][1:]
    report = engine.sbom_completeness_report(mutated)
    assert report["complete"] is False
    codes = {r["code"] for r in report["refusals"]}
    assert "EF_Z02_SBOM_COMPONENT_MISSING" in codes


def test_sbom_extra_component_is_refused_fail_closed() -> None:
    sbom = engine.build_sbom(generated_at=FIXED_TS)
    mutated = copy.deepcopy(sbom)
    mutated["components"].append(
        {"path": "not/a/real/file.bin", "byte_size": 1, "sha256": "sha256:" + "0" * 64}
    )
    report = engine.sbom_completeness_report(mutated)
    assert report["complete"] is False
    codes = {r["code"] for r in report["refusals"]}
    assert "EF_Z02_SBOM_COMPONENT_EXTRA" in codes


def test_sbom_tampered_digest_is_refused_fail_closed() -> None:
    sbom = engine.build_sbom(generated_at=FIXED_TS)
    mutated = copy.deepcopy(sbom)
    mutated["components"][0]["sha256"] = "sha256:" + "f" * 64
    report = engine.sbom_completeness_report(mutated)
    assert report["complete"] is False
    codes = {r["code"] for r in report["refusals"]}
    assert "EF_Z02_SBOM_HASH_MISMATCH" in codes


def test_every_refusal_reason_exceeds_fifty_characters() -> None:
    for code, reason in engine.REFUSAL_REASONS.items():
        assert len(reason) > 50, f"{code} reason too short"
