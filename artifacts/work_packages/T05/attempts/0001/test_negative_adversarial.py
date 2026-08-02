"""negative_and_adversarial_tests — every way the adapter is asked to overclaim.

Each attack is the concrete overclaim the package exists to refuse: a backend
that is not pinned to one build, a qualification that claims a capability the
build does not enable, a qualification that is not bound to a checked executor
profile, an executor for a command the tool surface does not project, an import
whose population does not add up, an imported score routed onto a Foundry
authority surface, and a record that has been edited after it was sealed.  Each
input is wrong in exactly one way and is refused by its own code.
"""

from __future__ import annotations

from typing import Any

import pytest

from epistemic_foundry.adapters.v4_t05 import (
    AdapterGateError,
    assert_backend_pinned,
    build_executor_registry,
    command_projection,
    import_shinka_run,
    pin_backend,
    qualify_backend_adapter,
    require_no_imported_authority,
)
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.shinka_adapter.backend import BackendNotQualified
from fixtures import (
    SANDBOX_PROFILE,
    backend_manifest,
    binding_arguments,
    capability_tests,
    execution_qualification,
    identities,
    import_arguments,
    imported_run,
)


def refused(run, code: str) -> AdapterGateError:
    with pytest.raises(AdapterGateError) as caught:
        run()
    assert caught.value.code == code, caught.value.code
    return caught.value


def reseal(record: dict[str, Any], field: str) -> dict[str, Any]:
    sealed = dict(record)
    sealed[field] = hash_excluding(sealed, field)
    return sealed


@pytest.mark.parametrize(
    "revision",
    ["main", "HEAD", "v0.3.1", "a" * 12, "a" * 39, "sha256:" + "a" * 63, "A" * 40],
)
def test_a_revision_that_is_not_a_full_digest_is_refused(revision: str) -> None:
    error = refused(
        lambda: backend_manifest(source_revision=revision), "BACKEND_UNPINNED"
    )
    assert error.context["source_revision"] == revision


@pytest.mark.parametrize("version", ["latest", "^1.2.3", "1.2", ">=0.3", "0.3.x"])
def test_a_version_that_is_not_an_exact_release_is_refused(version: str) -> None:
    error = refused(
        lambda: backend_manifest(package_version=version), "BACKEND_UNPINNED"
    )
    assert error.context["package_version"] == version


def test_a_hand_built_unpinned_manifest_is_refused_at_qualification() -> None:
    smuggled = reseal(
        {**backend_manifest(), "source_revision": "trunk-ish"}, "manifest_hash"
    )

    refused(lambda: assert_backend_pinned(smuggled), "BACKEND_UNPINNED")
    refused(
        lambda: qualify_backend_adapter(**binding_arguments(manifest=smuggled)),
        "BACKEND_UNPINNED",
    )


def test_the_composed_license_refusal_still_raises_as_itself() -> None:
    # pin_backend adds refusals; it does not swallow the ones the shinka
    # adapter already makes, so a caller can still tell which contract stopped.
    with pytest.raises(BackendNotQualified):
        pin_backend(
            backend_manifest_id="SBM-T05-NO-LICENSE",
            backend_name="ShinkaEvolve",
            source_repository="https://example.invalid/shinka-evolve.git",
            source_revision="a" * 40,
            package_version="0.3.1",
            license="   ",
            supported_candidate_types=["experiment-genome"],
            enabled_features=[],
            disabled_features=[],
            sandbox_profile_id=SANDBOX_PROFILE,
            adapter_version="4.0.0-t05.1",
        )


def test_claiming_a_capability_the_manifest_disables_is_refused() -> None:
    error = refused(
        lambda: qualify_backend_adapter(
            **binding_arguments(
                capability_tests=capability_tests(resume_integrity=True)
            )
        ),
        "CAPABILITY_OVERCLAIMED",
    )
    assert error.context["contradicted"] == ["resume_integrity"]


def test_claiming_a_capability_the_manifest_never_enables_is_refused() -> None:
    error = refused(
        lambda: qualify_backend_adapter(
            **binding_arguments(
                manifest=backend_manifest(
                    enabled_features=["deterministic_seed"], disabled_features=[]
                )
            )
        ),
        "CAPABILITY_OVERCLAIMED",
    )
    assert "sandbox_isolation" in error.context["undeclared"]


def test_a_verdict_the_schema_does_not_declare_is_refused() -> None:
    error = refused(
        lambda: qualify_backend_adapter(**binding_arguments(status="APPROVED")),
        "QUALIFICATION_STATUS_UNDECLARED",
    )
    assert error.context["status"] == "APPROVED"


def test_the_strongest_verdict_still_needs_its_critical_tests() -> None:
    # The shinka adapter owns this refusal; T05 must not have made it
    # reachable-around by building the record itself.
    with pytest.raises(BackendNotQualified):
        qualify_backend_adapter(
            **binding_arguments(
                status="QUALIFIED",
                manifest=backend_manifest(
                    enabled_features=["deterministic_seed"],
                    disabled_features=[],
                ),
                capability_tests=capability_tests(
                    sandbox_isolation=False,
                    effect_receipts=False,
                    evaluator_separation=False,
                    candidate_count_reconciliation=False,
                    resume_integrity=False,
                ),
            )
        )


def test_an_execution_qualification_missing_a_field_is_refused() -> None:
    stripped = {
        key: value
        for key, value in execution_qualification().items()
        if key != "effect_receipt_channel_id"
    }

    error = refused(
        lambda: qualify_backend_adapter(
            **binding_arguments(execution_qualification=stripped)
        ),
        "EXECUTION_PROFILE_UNBOUND",
    )
    assert error.context["missing"] == ["effect_receipt_channel_id"]


def test_an_edited_execution_qualification_is_refused() -> None:
    tampered = {**execution_qualification(), "effect_receipt_channel_id": "ER-OTHER"}

    refused(
        lambda: qualify_backend_adapter(
            **binding_arguments(execution_qualification=tampered)
        ),
        "RECORD_HASH_MISMATCH",
    )


def test_an_undeclared_executor_profile_is_refused() -> None:
    forged = reseal(
        {**execution_qualification(), "sandbox_profile": "plugin_host_process"},
        "qualification_hash",
    )

    error = refused(
        lambda: qualify_backend_adapter(
            **binding_arguments(execution_qualification=forged)
        ),
        "EXECUTION_PROFILE_UNBOUND",
    )
    assert error.context["sandbox_profile"] == "plugin_host_process"


def test_a_profile_the_manifest_does_not_pin_is_refused() -> None:
    error = refused(
        lambda: qualify_backend_adapter(
            **binding_arguments(manifest=backend_manifest(sandbox_profile_id="pure"))
        ),
        "EXECUTION_PROFILE_UNBOUND",
    )
    assert error.context["manifest_profile"] == "pure"
    assert error.context["sandbox_profile"] == SANDBOX_PROFILE


@pytest.mark.parametrize(
    "command", ["evolve run", "backend shinka qualify", "promote evolved"]
)
def test_an_executor_for_an_unprojected_command_is_refused(command: str) -> None:
    error = refused(
        lambda: build_executor_registry(
            registry_id="T05-REG-BAD", executors={command: "EXEC-1"}
        ),
        "EXECUTOR_UNPROJECTED",
    )
    assert error.context["unprojected"] == [command]


def test_every_proposed_command_is_refused_together() -> None:
    projection = command_projection()
    error = refused(
        lambda: build_executor_registry(
            registry_id="T05-REG-ALL",
            executors={
                command: "EXEC-1"
                for command in projection["proposed_unavailable_commands"]
            },
        ),
        "EXECUTOR_UNPROJECTED",
    )
    assert len(error.context["unprojected"]) == 25


def test_a_partly_projected_registration_is_refused_as_a_whole() -> None:
    projection = command_projection()
    error = refused(
        lambda: build_executor_registry(
            registry_id="T05-REG-MIXED",
            executors={
                projection["available_commands"][0]: "EXEC-OK",
                "evolve setup": "EXEC-BAD",
            },
        ),
        "EXECUTOR_UNPROJECTED",
    )
    assert error.context["unprojected"] == ["evolve setup"]


def test_an_invented_command_is_refused_rather_than_registered() -> None:
    refused(
        lambda: build_executor_registry(
            registry_id="T05-REG-INVENTED", executors={"evolve ascend": "EXEC-1"}
        ),
        "EXECUTOR_UNPROJECTED",
    )


def test_an_import_that_loses_candidates_is_refused() -> None:
    error = refused(
        lambda: import_shinka_run(
            **import_arguments(
                candidate_identities={
                    "proposed": identities(3),
                    "generated": identities(3),
                    "evaluated": identities(2),
                    "persisted": identities(2),
                }
            )
        ),
        "IMPORT_COUNTS_UNRECONCILED",
    )
    assert error.context["missing"] == ["cand-2"]


def test_an_import_with_a_candidate_nobody_proposed_is_refused() -> None:
    error = refused(
        lambda: import_shinka_run(
            **import_arguments(
                candidate_identities={
                    "proposed": identities(2),
                    "generated": identities(2),
                    "evaluated": identities(2),
                    "persisted": [*identities(2), "smuggled"],
                }
            )
        ),
        "IMPORT_COUNTS_UNRECONCILED",
    )
    assert error.context["unknown_identities"] == ["persisted"]


def test_an_import_that_omits_a_pipeline_stage_is_refused() -> None:
    error = refused(
        lambda: import_shinka_run(
            **import_arguments(
                candidate_identities={
                    "proposed": identities(1),
                    "generated": identities(1),
                    "persisted": identities(1),
                }
            )
        ),
        "INPUT_INVALID",
    )
    assert error.context["missing_stages"] == ["evaluated"]


def test_an_import_that_invents_a_stage_is_refused() -> None:
    error = refused(
        lambda: import_shinka_run(
            **import_arguments(
                candidate_identities={
                    "proposed": identities(1),
                    "generated": identities(1),
                    "evaluated": identities(1),
                    "persisted": identities(1),
                    "promoted": identities(1),
                }
            )
        ),
        "INPUT_INVALID",
    )
    assert error.context["unknown_stages"] == ["promoted"]


@pytest.mark.parametrize(
    "surface",
    ["promotion_decision", "evaluator_bundle", "gate_decision", "holdout_manifest"],
)
def test_routing_an_imported_signal_into_authority_is_refused(surface: str) -> None:
    error = refused(
        lambda: require_no_imported_authority(
            imported=imported_run(), bindings={"combined_score": surface}
        ),
        "BACKEND_AUTHORITY_LEAK",
    )
    assert surface in str(error)


def test_an_unclassified_imported_field_is_refused() -> None:
    refused(
        lambda: require_no_imported_authority(
            imported=imported_run(), bindings={"secret_fitness": "search_hint"}
        ),
        "BACKEND_AUTHORITY_LEAK",
    )


def test_an_envelope_that_claims_authority_is_refused() -> None:
    forged = reseal({**imported_run(), "authoritative": True}, "import_hash")

    refused(
        lambda: require_no_imported_authority(imported=forged, bindings={}),
        "BACKEND_AUTHORITY_LEAK",
    )


def test_an_edited_import_envelope_is_refused() -> None:
    tampered = {**imported_run(), "authoritative": True}

    refused(
        lambda: require_no_imported_authority(imported=tampered, bindings={}),
        "RECORD_HASH_MISMATCH",
    )


def test_an_edited_imported_run_record_is_refused() -> None:
    envelope = imported_run()
    record = {**envelope["imported_run"], "manufactured_receipts": True}
    forged = reseal({**envelope, "imported_run": record}, "import_hash")

    refused(
        lambda: require_no_imported_authority(imported=forged, bindings={}),
        "RECORD_HASH_MISMATCH",
    )


def test_an_edited_backend_manifest_is_refused() -> None:
    tampered = {**backend_manifest(), "adapter_version": "9.9.9"}

    refused(lambda: assert_backend_pinned(tampered), "RECORD_HASH_MISMATCH")


@pytest.mark.parametrize("value", ["not-a-mapping", 7, None, ["a"]])
def test_a_non_mapping_record_is_refused(value: object) -> None:
    refused(lambda: assert_backend_pinned(value), "INPUT_INVALID")
    refused(
        lambda: build_executor_registry(registry_id="T05-REG-X", executors=value),
        "INPUT_INVALID",
    )


@pytest.mark.parametrize("value", ["", "   ", 7, None])
def test_a_blank_identifier_is_refused(value: object) -> None:
    refused(
        lambda: build_executor_registry(registry_id=value, executors={}),
        "INPUT_INVALID",
    )


def test_a_candidate_identity_that_is_not_a_string_is_refused() -> None:
    refused(
        lambda: import_shinka_run(
            **import_arguments(
                candidate_identities={
                    "proposed": [None],
                    "generated": [None],
                    "evaluated": [None],
                    "persisted": [None],
                }
            )
        ),
        "INPUT_INVALID",
    )


def test_a_candidate_stage_that_is_not_a_list_is_refused() -> None:
    refused(
        lambda: import_shinka_run(
            **import_arguments(
                candidate_identities={
                    "proposed": "cand-0",
                    "generated": ["cand-0"],
                    "evaluated": ["cand-0"],
                    "persisted": ["cand-0"],
                }
            )
        ),
        "INPUT_INVALID",
    )
