"""EF4-I63 backend isolation and EF4-I32/I35/I36 release, install, and messaging."""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.hashing import sha256_of_payload
from epistemic_foundry.release.provenance import (
    REQUIRED_INSTALL_CHECKS,
    ProvenanceIncomplete,
    RemoteAdapterRefused,
    build_release_provenance,
    build_remote_adapter_profile,
    install_acceptance_blockers,
    installability_is_demonstrated,
    release_is_shippable,
    signing_status_of,
)
from epistemic_foundry.shinka_adapter.isolation import (
    FOUNDRY_AUTHORITY_SURFACES,
    BackendAuthorityRefused,
    foundry_runs_without_backend,
    import_backend_state,
    imported_state_is_authoritative,
    require_no_authority_routing,
    require_optional,
)

DIGEST = sha256_of_payload({"content": "x"})


# -- EF4-I63 the backend is optional -------------------------------------


def test_i63_foundry_runs_without_any_backend() -> None:
    assert foundry_runs_without_backend() is True


def test_i63_a_required_backend_is_refused() -> None:
    """A backend the Foundry cannot proceed without has acquired authority."""
    with pytest.raises(BackendAuthorityRefused) as excinfo:
        require_optional(
            {"evolution_run_id": "ERUN-1", "search_backend": {"name": "shinka", "required": True}}
        )
    assert "has become authority" in str(excinfo.value)


def test_i63_an_optional_backend_is_accepted() -> None:
    require_optional(
        {"evolution_run_id": "ERUN-1", "search_backend": {"name": "shinka", "required": False}}
    )


def test_i63_no_backend_at_all_is_accepted() -> None:
    require_optional({"evolution_run_id": "ERUN-1"})


# -- EF4-I63 signals never reach authority surfaces ----------------------


@pytest.mark.parametrize("surface", FOUNDRY_AUTHORITY_SURFACES)
def test_i63_no_signal_may_route_into_an_authority_surface(surface: str) -> None:
    with pytest.raises(BackendAuthorityRefused) as excinfo:
        require_no_authority_routing({"combined_score": surface})
    assert surface in str(excinfo.value)


def test_i63_advisory_routing_is_permitted() -> None:
    require_no_authority_routing({"combined_score": "search_ordering", "island": "telemetry"})


def test_i63_an_unclassified_signal_fails_closed() -> None:
    with pytest.raises(BackendAuthorityRefused) as excinfo:
        require_no_authority_routing({"secret_sauce": "telemetry"})
    assert "not classified as advisory" in str(excinfo.value)


# -- EF4-I63 import is translation, not adoption -------------------------


def an_import(**overrides: object) -> dict:
    kwargs: dict = {
        "source_version": "shinka-0.3.1",
        "target_version": "4.0.0",
        "source_run_id": "SHK-RUN-1",
        "target_session_id": "SESS-1",
        "source_snapshot_hash": DIGEST,
        "migration_plan_id": "MP-1",
        "unconverted_fields": ["bandit_state.posterior"],
    }
    kwargs.update(overrides)
    return import_backend_state(**kwargs)  # type: ignore[arg-type]


def test_i63_imported_run_starts_idle() -> None:
    """An imported run holds no Foundry receipts, so it earned no transitions."""
    assert an_import()["derived_phase"] == "IDLE"


def test_i63_import_never_manufactures_receipts() -> None:
    assert an_import()["manufactured_receipts"] is False


def test_i63_phase_and_receipt_claims_are_not_parameters() -> None:
    with pytest.raises(TypeError):
        import_backend_state(  # type: ignore[call-arg]
            source_version="shinka-0.3.1",
            target_version="4.0.0",
            source_run_id="SHK-RUN-1",
            target_session_id="SESS-1",
            source_snapshot_hash=DIGEST,
            migration_plan_id="MP-1",
            unconverted_fields=[],
            derived_phase="G",
        )


def test_i63_unconverted_fields_stay_visible() -> None:
    assert an_import()["unconverted_fields"] == ["bandit_state.posterior"]


def test_i63_even_a_clean_import_is_not_authoritative() -> None:
    assert imported_state_is_authoritative(an_import(unconverted_fields=[])) is False


# -- EF4-I32 release provenance ------------------------------------------


def a_check(check_id: str, status: str = "PASS") -> dict:
    return {"check_id": check_id, "status": status, "details": "", "remediation": []}


BUILD_CHECKS = [
    a_check("reproducible_build"),
    a_check("sbom_generated"),
    a_check("manifest_complete"),
    a_check("clean_extraction"),
]

SIGNATURE = {"kind": "sigstore", "identity": "builder@example.invalid", "signature": "abc123"}


def a_provenance(**overrides: object) -> dict:
    kwargs: dict = {
        "plugin_id": "epistemic-foundry",
        "version": "4.0.0",
        "source_revision": "c0ffee1234567890c0ffee1234567890c0ffee12",
        "source_hash": DIGEST,
        "bundle_hash": DIGEST,
        "sbom_hash": DIGEST,
        "manifest_hash": DIGEST,
        "builder_identity": "ci://build/42",
        "builder_environment_hash": DIGEST,
        "checks": list(BUILD_CHECKS),
        "signatures": [SIGNATURE],
    }
    kwargs.update(overrides)
    return build_release_provenance(**kwargs)  # type: ignore[arg-type]


def test_i32_complete_signed_provenance_is_shippable() -> None:
    provenance = a_provenance()
    assert signing_status_of(provenance) == "SIGNED"
    assert release_is_shippable(provenance) is True


def test_i32_reproducibility_is_derived_from_the_check() -> None:
    """A builder asserting its own reproducibility is the wrong witness."""
    provenance = a_provenance(
        checks=[a_check("reproducible_build", "WARN"), *BUILD_CHECKS[1:]]
    )
    assert provenance["builder"]["reproducible"] is False


@pytest.mark.parametrize(
    "check_id", ["reproducible_build", "sbom_generated", "manifest_complete", "clean_extraction"]
)
def test_i32_a_missing_build_check_is_refused(check_id: str) -> None:
    checks = [check for check in BUILD_CHECKS if check["check_id"] != check_id]
    with pytest.raises(ProvenanceIncomplete) as excinfo:
        a_provenance(checks=checks)
    assert check_id in str(excinfo.value)


def test_i32_a_not_run_check_is_not_a_passing_one() -> None:
    checks = [a_check("sbom_generated", "NOT_RUN"), *BUILD_CHECKS[:1], *BUILD_CHECKS[2:]]
    with pytest.raises(ProvenanceIncomplete) as excinfo:
        a_provenance(checks=checks)
    assert "NOT_RUN check is not a" in str(excinfo.value)


@pytest.mark.parametrize("revision", ["main", "master", "HEAD", "latest", ""])
def test_i32_a_floating_source_revision_is_refused(revision: str) -> None:
    with pytest.raises(ProvenanceIncomplete) as excinfo:
        a_provenance(source_revision=revision)
    assert "floating" in str(excinfo.value)


def test_i32_an_undigested_bundle_is_refused() -> None:
    with pytest.raises(ProvenanceIncomplete) as excinfo:
        a_provenance(bundle_hash="v4.0.0")
    assert "cannot be rebuilt" in str(excinfo.value)


def test_i32_unsigned_bundle_is_recordable_but_not_shippable() -> None:
    provenance = a_provenance(signatures=[])
    assert signing_status_of(provenance) == "UNSIGNED"
    assert release_is_shippable(provenance) is False


def test_i32_an_empty_signature_value_is_invalid_not_signed() -> None:
    provenance = a_provenance(signatures=[{**SIGNATURE, "signature": "  "}])
    assert signing_status_of(provenance) == "INVALID"
    assert release_is_shippable(provenance) is False


def test_i32_signing_status_is_not_a_parameter() -> None:
    with pytest.raises(TypeError):
        build_release_provenance(  # type: ignore[call-arg]
            plugin_id="epistemic-foundry",
            version="4.0.0",
            source_revision="c0ffee1234567890c0ffee1234567890c0ffee12",
            source_hash=DIGEST,
            bundle_hash=DIGEST,
            sbom_hash=DIGEST,
            manifest_hash=DIGEST,
            builder_identity="ci://build/42",
            builder_environment_hash=DIGEST,
            checks=list(BUILD_CHECKS),
            signatures=[],
            signing_status="SIGNED",
        )


# -- EF4-I35 installability is tested ------------------------------------


def test_i35_every_install_path_the_invariant_names_is_required() -> None:
    assert REQUIRED_INSTALL_CHECKS == (
        "fresh_install",
        "pathless_execution",
        "upgrade",
        "downgrade",
        "uninstall",
        "cross_platform_paths",
    )


def test_i35_a_full_install_matrix_is_demonstrated() -> None:
    checks = [a_check(name) for name in REQUIRED_INSTALL_CHECKS]
    assert install_acceptance_blockers(checks) == []
    assert installability_is_demonstrated(checks) is True


@pytest.mark.parametrize("skipped", REQUIRED_INSTALL_CHECKS)
def test_i35_an_untested_install_path_blocks_by_name(skipped: str) -> None:
    """`NOT_RUN` is how an untested path ships, so it fails the gate."""
    checks = [
        a_check(name, "NOT_RUN" if name == skipped else "PASS")
        for name in REQUIRED_INSTALL_CHECKS
    ]
    assert install_acceptance_blockers(checks) == [skipped]
    assert installability_is_demonstrated(checks) is False


def test_i35_an_absent_check_is_also_a_blocker() -> None:
    checks = [a_check(name) for name in REQUIRED_INSTALL_CHECKS if name != "downgrade"]
    assert install_acceptance_blockers(checks) == ["downgrade"]


def test_i35_partial_success_is_not_summarized_as_a_count() -> None:
    checks = [
        a_check(name, "FAIL" if name in {"upgrade", "uninstall"} else "PASS")
        for name in REQUIRED_INSTALL_CHECKS
    ]
    assert install_acceptance_blockers(checks) == ["upgrade", "uninstall"]


# -- EF4-I36 remote messaging is minimized -------------------------------


def test_i36_a_notification_only_adapter_is_permitted() -> None:
    profile = build_remote_adapter_profile(
        adapter_name="slack-notify",
        capabilities=["send_message"],
        enabled_by_default=False,
        approval_required=True,
    )
    assert profile["enabled_by_default"] is False


@pytest.mark.parametrize(
    "capability",
    ["command_execution", "shell", "arbitrary_command", "raw_evidence_export", "holdout_read"],
)
def test_i36_a_remote_execution_or_export_capability_is_refused(capability: str) -> None:
    with pytest.raises(RemoteAdapterRefused) as excinfo:
        build_remote_adapter_profile(
            adapter_name="slack-notify",
            capabilities=["send_message", capability],
            enabled_by_default=False,
            approval_required=True,
        )
    assert "not a notification channel" in str(excinfo.value)


def test_i36_an_adapter_enabled_by_default_is_refused() -> None:
    with pytest.raises(RemoteAdapterRefused) as excinfo:
        build_remote_adapter_profile(
            adapter_name="slack-notify",
            capabilities=["send_message"],
            enabled_by_default=True,
            approval_required=True,
        )
    assert "never opted into" in str(excinfo.value)
