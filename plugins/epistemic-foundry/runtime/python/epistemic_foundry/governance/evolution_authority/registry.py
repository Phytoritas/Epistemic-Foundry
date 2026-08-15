"""A05 G00-G14 gate registry and canonical promotion-workflow binding.

This module is the constitutional bridge ordered by
HD-EF4-A06-RM001-20260730-001: it binds the bounded promotion helpers in
:mod:`epistemic_foundry.governance.promotion` to the canonical 23-node
``evolution_promotion`` workflow, freezes the charter's gate-applicability
matrix, and implements the deterministic G00 pin-resolution contract.  Gate
identifiers are imported from the bounded helper, never re-declared
(EF4-I22).  Nothing here can mutate an evaluator, holdout, policy, ledger, or
prior decision; every check is a pure function over sealed inputs.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, Final

from ..promotion import CANONICAL_GATE_IDS
from ...domain.vocabularies import PROMOTION_LADDER
from ...contracts.registry import default_registry

EVOLUTION_PROMOTION_WORKFLOW_ID: Final = "evolution_promotion"
EXPECTED_PROMOTION_NODE_COUNT: Final = 23
NODE_ID_PATTERN: Final = re.compile(
    default_registry().document("node-contract")["properties"]["node_id"]["pattern"]
)

#: Charter section 4.2 applicability matrix.  ``R`` = substantive evidence
#: required, ``P`` = the gate executes and needs policy-backed NOT_REQUIRED
#: evidence, ``C`` = conditional on policy/work-class triggers.  No gate is
#: ever omitted.
GATE_APPLICABILITY: Final = MappingProxyType(
    {
        CANONICAL_GATE_IDS[0]: ("R", "R", "R", "R", "R", "R"),
        CANONICAL_GATE_IDS[1]: ("R", "R", "R", "R", "R", "R"),
        CANONICAL_GATE_IDS[2]: ("R", "R", "R", "R", "R", "R"),
        CANONICAL_GATE_IDS[3]: ("P", "R", "R", "R", "R", "R"),
        CANONICAL_GATE_IDS[4]: ("R", "R", "R", "R", "R", "R"),
        CANONICAL_GATE_IDS[5]: ("P", "P", "R", "R", "R", "R"),
        CANONICAL_GATE_IDS[6]: ("P", "P", "R", "R", "R", "R"),
        CANONICAL_GATE_IDS[7]: ("P", "P", "P", "R", "R", "R"),
        CANONICAL_GATE_IDS[8]: ("P", "P", "R", "R", "R", "R"),
        CANONICAL_GATE_IDS[9]: ("P", "P", "R", "R", "R", "R"),
        CANONICAL_GATE_IDS[10]: ("R", "R", "R", "R", "R", "R"),
        CANONICAL_GATE_IDS[11]: ("P", "P", "R", "R", "R", "R"),
        CANONICAL_GATE_IDS[12]: ("P", "P", "P", "R", "R", "R"),
        CANONICAL_GATE_IDS[13]: ("C", "C", "C", "C", "C", "C"),
        CANONICAL_GATE_IDS[14]: ("R", "R", "R", "R", "R", "R"),
    }
)

#: Charter section 8: the exact receipt-bound promotion order.
PROMOTION_WORKFLOW_STEPS: Final = (
    "record_request_intent",
    "seal_requested_level_and_revision",
    "build_phase_e_promotion_pack",
    "verify_pack_artifacts_and_receipts",
    "execute_gates_g00_through_g10",
    "run_parliament_adjudication",
    "execute_g11",
    "execute_g12",
    "recheck_g10_ceiling",
    "execute_g13",
    "calculate_grantable_level",
    "record_commit_intent",
    "acquire_promotion_commit_lease",
    "compare_and_swap_expected_revisions",
    "record_promotion_decision_and_passport_revision",
    "append_ledger_event",
    "record_effect_and_artifact_receipts",
    "complete_g14_after_reconciliation",
)

#: Gate identifier -> canonical workflow node that emits its GateDecision.
#: G14 completes only in the reconciliation node after the atomic commit.
GATE_NODE_BINDINGS: Final = MappingProxyType(
    {
        CANONICAL_GATE_IDS[0]: "gate_g00_pin_resolution",
        CANONICAL_GATE_IDS[1]: "gate_g01_policy_authority",
        CANONICAL_GATE_IDS[2]: "gate_g02_evaluator_holdout_firewall",
        CANONICAL_GATE_IDS[3]: "gate_g03_schema_lineage_count",
        CANONICAL_GATE_IDS[4]: "gate_g04_source_provenance",
        CANONICAL_GATE_IDS[5]: "gate_g05_search_coverage",
        CANONICAL_GATE_IDS[6]: "gate_g06_method_scope_dependency",
        CANONICAL_GATE_IDS[7]: "gate_g07_validation_leakage",
        CANONICAL_GATE_IDS[8]: "gate_g08_adaptive_statistics",
        CANONICAL_GATE_IDS[9]: "gate_g09_red_queen",
        CANONICAL_GATE_IDS[10]: "gate_g10_replication_ceiling",
        CANONICAL_GATE_IDS[11]: "gate_g11_parliament",
        CANONICAL_GATE_IDS[12]: "gate_g12_independent_attestation",
        CANONICAL_GATE_IDS[13]: "gate_g13_human_policy_approval",
        CANONICAL_GATE_IDS[14]: "reconcile_commit_receipts",
    }
)

#: Advisory model outputs: the only schemas an llm node may emit on the
#: promotion path.  A PromotionDecision can never be one of them.
ADVISORY_LLM_OUTPUT_SCHEMAS: Final = frozenset(
    {
        "schemas/adjudication.schema.json",
        "schemas/attestation.schema.json",
    }
)
PROMOTION_DECISION_SCHEMA: Final = "schemas/promotion-decision.schema.json"
PROMOTION_COMMIT_CAPABILITY: Final = "promotion:commit"

#: Charter section 2.2: every unconditional resolved-reference key.
REQUIRED_RESOLVED_REF_KEYS: Final = (
    "base_run_spec",
    "schema_bundle",
    "workflow",
    "policy_bundle",
    "corpus_evidence_snapshot",
    "ontology",
    "domain_pack",
    "evaluator_bundle",
    "holdout_manifest",
    "operator_registry",
    "prompt_bundle",
    "model_routing_policy",
    "provider_adapter_manifest",
    "statistical_plan",
    "selection_policy",
    "stop_policy",
    "replication_policy",
    "archive_niche_policy",
    "budget_envelope",
    "execution_environment_toolchain_manifest",
)
CONDITIONAL_RESOLVED_REF_KEYS: Final = ("external_backend_manifest",)

#: Charter section 2.1: the immutable resolution tuple.
RESOLVED_REF_TUPLE_FIELDS: Final = (
    "logical_id",
    "exact_version_or_revision",
    "content_hash",
    "resolver_id",
    "resolver_version",
    "resolved_artifact_locator",
    "resolved_at",
    "authority_source_class",
    "reproducibility_class",
)

_FLOATING_TOKENS: Final = frozenset({"main", "latest", "head", "HEAD", "current"})
_RANGE_PATTERN: Final = re.compile(r"[\^~*]|>=|<=|>|<|\.x$")
_SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")


class EvolutionAuthorityError(PermissionError):
    """Typed fail-closed constitutional violation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def schema_enum_token(kind: str, field: str, token: str) -> str:
    """Resolve one canonical enum token instead of restating it (EF4-I22).

    Wire vocabulary belongs to the canonical schema, so a status literal is
    read back from the contract rather than retyped next to the code that
    branches on it.  The lookup is by value, not by position, so a reordered
    vocabulary fails closed instead of silently selecting a different status,
    and a token that a schema no longer declares stops the caller rather than
    quietly never matching.
    """

    document = default_registry().document(kind)
    values = document.get("properties", {}).get(field, {}).get("enum")
    if not isinstance(values, list) or token not in values:
        raise EvolutionAuthorityError(
            "VOCABULARY_DRIFT",
            f"{kind}.{field} no longer declares {token!r}",
        )
    return token


def applicability(gate_id: str, requested_level: str) -> str:
    """Return ``R``/``P``/``C`` for one gate at one requested level."""

    if gate_id not in GATE_APPLICABILITY:
        raise EvolutionAuthorityError("GATE_UNKNOWN", f"unknown gate {gate_id!r}")
    try:
        column = PROMOTION_LADDER.index(requested_level)
    except ValueError as error:
        raise EvolutionAuthorityError(
            "LEVEL_UNKNOWN", f"unknown promotion level {requested_level!r}"
        ) from error
    return GATE_APPLICABILITY[gate_id][column]


def resolve_references(resolved_refs: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic G00 pin-resolution evaluation (charter sections 2.1-2.3).

    Returns a typed outcome mapping with ``status`` in
    ``PASS | FAIL | BLOCKED | SPEC_GAP`` and sorted ``reasons``.  It never
    resolves a floating reference to a current value.
    """

    reasons: list[str] = []
    status = "PASS"

    def worsen(new_status: str, reason: str) -> None:
        nonlocal status
        reasons.append(reason)
        order = {"PASS": 0, "SPEC_GAP": 1, "BLOCKED": 2, "FAIL": 3}
        if order[new_status] > order[status]:
            status = new_status

    if not isinstance(resolved_refs, Mapping):
        return {"status": "FAIL", "reasons": ["resolved_refs must be an object"]}
    for key in REQUIRED_RESOLVED_REF_KEYS:
        if key not in resolved_refs:
            worsen("FAIL", f"unresolved required reference: {key}")
    for key in resolved_refs:
        if (
            key not in REQUIRED_RESOLVED_REF_KEYS
            and key not in CONDITIONAL_RESOLVED_REF_KEYS
        ):
            worsen("FAIL", f"unknown resolved-reference key: {key}")
    for key, entry in resolved_refs.items():
        if not isinstance(entry, Mapping):
            worsen("FAIL", f"{key}: resolution tuple must be an object")
            continue
        for field in RESOLVED_REF_TUPLE_FIELDS:
            value = entry.get(field)
            if not isinstance(value, str) or not value:
                worsen(
                    "FAIL",
                    f"{key}.{field}: missing tuple field makes the entry unresolved",
                )
        revision = entry.get("exact_version_or_revision")
        if isinstance(revision, str) and (
            revision in _FLOATING_TOKENS or _RANGE_PATTERN.search(revision)
        ):
            worsen(
                "FAIL",
                f"{key}: floating reference {revision!r} is forbidden and is not resolved to HEAD",
            )
        content_hash = entry.get("content_hash")
        if (
            isinstance(content_hash, str)
            and content_hash
            and not _SHA256_PATTERN.match(content_hash)
        ):
            worsen("FAIL", f"{key}: content_hash is not sha256:<64 lowercase hex>")
        if entry.get("content_hash_matches") is False:
            worsen(
                "FAIL",
                f"{key}: resolved bytes do not match the sealed content_hash",
            )
        if entry.get("resolved_bytes_available") is False:
            worsen(
                "BLOCKED",
                f"{key}: the exact sealed artifact is unavailable; no replacement is selected",
            )
        if entry.get("set_semantic_sort_declared") is False:
            worsen(
                "SPEC_GAP",
                f"{key}: set-semantic array has no schema-declared canonical sort",
            )
    return {"status": status, "reasons": sorted(reasons)}


#: Charter section 6: roles an attestor must be independent of.
ATTESTOR_CONFLICT_ROLES: Final = (
    "candidate_generator_ids",
    "candidate_implementer_ids",
    "first_adjudicator_ids",
    "prompt_lineage_actor_ids",
    "promotion_commit_authority_ids",
)


def verify_attestor_independence(attestor_id: str, context: Mapping[str, Any]) -> None:
    """Reject a self- or non-independent attestation (charter section 6)."""

    if not isinstance(attestor_id, str) or not attestor_id:
        raise EvolutionAuthorityError(
            "ATTESTOR_INDEPENDENCE_VIOLATION", "attestor identity is missing"
        )
    for role in ATTESTOR_CONFLICT_ROLES:
        members = context.get(role, ())
        if attestor_id in tuple(members):
            raise EvolutionAuthorityError(
                "ATTESTOR_INDEPENDENCE_VIOLATION",
                f"attestor {attestor_id!r} holds the conflicting role {role}",
            )


def verify_approval_independence(approver_id: str, maker_ids: Sequence[str]) -> None:
    """Reject self-approval: makers cannot approve their own work (EF4-I12)."""

    if not isinstance(approver_id, str) or not approver_id:
        raise EvolutionAuthorityError(
            "SELF_APPROVAL_FORBIDDEN", "approver identity is missing"
        )
    if approver_id in tuple(maker_ids):
        raise EvolutionAuthorityError(
            "SELF_APPROVAL_FORBIDDEN",
            f"maker {approver_id!r} cannot approve its own promotion",
        )


def _node_map(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = document.get("nodes")
    if not isinstance(nodes, Sequence):
        raise EvolutionAuthorityError("WORKFLOW_INVALID", "workflow has no node array")
    result: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, Mapping):
            raise EvolutionAuthorityError("WORKFLOW_INVALID", "node must be an object")
        snapshot = dict(node)
        node_id = snapshot.get("node_id")
        if not isinstance(node_id, str) or NODE_ID_PATTERN.fullmatch(node_id) is None:
            raise EvolutionAuthorityError(
                "WORKFLOW_INVALID", "node_id does not match the canonical node contract"
            )
        if node_id in result:
            raise EvolutionAuthorityError(
                "WORKFLOW_INVALID", f"duplicate node_id {node_id!r}"
            )
        result[node_id] = snapshot
    return result


def _ancestors(nodes: Mapping[str, Mapping[str, Any]], node_id: str) -> set[str]:
    seen: set[str] = set()
    stack = [node_id]
    while stack:
        current = stack.pop()
        for dependency in nodes.get(current, {}).get("depends_on", []):
            if dependency not in seen:
                seen.add(str(dependency))
                stack.append(str(dependency))
    return seen


def _resolve_owned_executor(module_path: str, attribute: str, node_id: str) -> Any:
    """Resolve one A05-owned executor, refusing anything unresolvable.

    Gate executors are generated per gate and published through the node
    entrypoint table rather than as module attributes, so the table is the
    authoritative lookup and the module attribute is the fallback.  The import
    is local because the executor modules import this module for the canonical
    gate identifiers; resolving at call time keeps that dependency one-way.
    """

    from importlib import import_module

    try:
        module = import_module(module_path)
    except ImportError as error:
        raise EvolutionAuthorityError(
            "RUNTIME_BINDING_MISSING", f"cannot import {module_path!r}"
        ) from error
    table = getattr(module, "NODE_ENTRYPOINTS", None)
    executor = None
    if isinstance(table, Mapping) and attribute == node_id:
        executor = table.get(node_id)
    if executor is None:
        executor = getattr(module, attribute, None)
    if not callable(executor):
        raise EvolutionAuthorityError(
            "RUNTIME_BINDING_MISSING",
            f"{module_path}:{attribute} is not a callable executor",
        )
    return executor


def verify_promotion_workflow_binding(document: Mapping[str, Any]) -> dict[str, Any]:
    """Prove the 23-node promotion workflow enforces the constitutional chain.

    Raises :class:`EvolutionAuthorityError` on any violation; returns the
    verified binding summary otherwise.
    """

    if document.get("workflow_id") != EVOLUTION_PROMOTION_WORKFLOW_ID:
        raise EvolutionAuthorityError(
            "WORKFLOW_INVALID", "document is not the evolution_promotion workflow"
        )
    nodes = _node_map(document)
    if len(nodes) != EXPECTED_PROMOTION_NODE_COUNT:
        raise EvolutionAuthorityError(
            "WORKFLOW_INVALID",
            f"evolution_promotion must hold exactly {EXPECTED_PROMOTION_NODE_COUNT} nodes",
        )

    for gate_id, node_id in GATE_NODE_BINDINGS.items():
        node = nodes.get(node_id)
        if node is None:
            raise EvolutionAuthorityError(
                "GATE_NODE_MISSING", f"{gate_id} has no bound node {node_id}"
            )
        declared = " ".join(str(check) for check in node.get("acceptance_checks", []))
        if gate_id not in declared:
            raise EvolutionAuthorityError(
                "GATE_NOT_DECLARED", f"{node_id} does not declare {gate_id}"
            )
        if gate_id != CANONICAL_GATE_IDS[14] and node.get("output_schema_ref") != (
            "schemas/gate-decision.schema.json"
        ):
            raise EvolutionAuthorityError(
                "GATE_OUTPUT_INVALID", f"{node_id} must emit a GateDecision"
            )
        if node.get("executor_type") == "llm":
            raise EvolutionAuthorityError(
                "GATE_EXECUTOR_INVALID", f"{node_id} cannot be an llm executor"
            )

    ordered_gate_nodes = [GATE_NODE_BINDINGS[gate] for gate in CANONICAL_GATE_IDS]
    for earlier, later in zip(ordered_gate_nodes, ordered_gate_nodes[1:], strict=False):
        if earlier not in _ancestors(nodes, later):
            raise EvolutionAuthorityError(
                "GATE_ORDER_INVALID", f"{later} does not depend on {earlier}"
            )

    for node_id, node in nodes.items():
        output = node.get("output_schema_ref")
        if node.get("executor_type") == "llm":
            if output not in ADVISORY_LLM_OUTPUT_SCHEMAS:
                raise EvolutionAuthorityError(
                    "LLM_AUTHORITY_VIOLATION",
                    f"llm node {node_id} may only emit advisory adjudication/attestation",
                )
        if output == PROMOTION_DECISION_SCHEMA:
            if node.get("executor_type") != "deterministic":
                raise EvolutionAuthorityError(
                    "PROMOTION_DECISION_EXECUTOR_INVALID",
                    "only a deterministic node may emit a PromotionDecision",
                )
            if PROMOTION_COMMIT_CAPABILITY not in node.get("capabilities", []):
                raise EvolutionAuthorityError(
                    "PROMOTION_COMMIT_CAPABILITY_MISSING",
                    "the committing node must hold promotion:commit",
                )
    commit_holders = [
        node_id
        for node_id, node in nodes.items()
        if PROMOTION_COMMIT_CAPABILITY in node.get("capabilities", [])
    ]
    if len(commit_holders) != 1:
        raise EvolutionAuthorityError(
            "PROMOTION_COMMIT_CAPABILITY_SCOPE",
            f"exactly one node may hold promotion:commit, found {sorted(commit_holders)}",
        )

    required_outputs = {
        "schemas/action-intent.schema.json",
        "schemas/phase-artifact-set.schema.json",
        "schemas/artifact-receipt.schema.json",
        "schemas/gate-decision.schema.json",
        "schemas/adjudication.schema.json",
        "schemas/attestation.schema.json",
        "schemas/approval-record.schema.json",
        "schemas/capability-lease.schema.json",
        PROMOTION_DECISION_SCHEMA,
        "schemas/effect-receipt.schema.json",
    }
    emitted = {str(node.get("output_schema_ref")) for node in nodes.values()}
    missing_outputs = sorted(required_outputs - emitted)
    if missing_outputs:
        raise EvolutionAuthorityError(
            "AUTHORITY_ARTIFACT_OUTPUT_MISSING",
            f"promotion workflow does not emit: {missing_outputs}",
        )

    # Every executable node must resolve to an implementation A05 actually
    # owns.  A string prefix is not enough: a module inside this package can
    # hold an imported callable from anywhere, so the resolved function's own
    # defining module is checked too.  The package, not one module, is the
    # boundary, because A05 may split gate execution from commit orchestration.
    package_prefix = "epistemic_foundry.governance.evolution_authority."
    unbound: list[str] = []
    for node_id, node in nodes.items():
        if node.get("executor_type") not in {"deterministic", "policy", "human_gate"}:
            continue
        ref = str(node.get("executor_ref", ""))
        module_path, separator, attribute = ref.partition(":")
        if (
            not separator
            or not attribute
            or not module_path.startswith(package_prefix)
        ):
            unbound.append(node_id)
            continue
        try:
            executor = _resolve_owned_executor(module_path, attribute, node_id)
        except EvolutionAuthorityError:
            unbound.append(node_id)
            continue
        # The attribute must be this node's own entrypoint, and the callable
        # must be defined inside A05 rather than imported from another package.
        if attribute != node_id or not getattr(
            executor, "__module__", ""
        ).startswith(package_prefix):
            unbound.append(node_id)
    if unbound:
        unbound = sorted(unbound)
        raise EvolutionAuthorityError(
            "RUNTIME_BINDING_MISSING",
            f"nodes are not bound to the evolution-authority runtime: {unbound}",
        )

    return {
        "workflow_id": EVOLUTION_PROMOTION_WORKFLOW_ID,
        "node_count": len(nodes),
        "gate_nodes": dict(GATE_NODE_BINDINGS),
        "commit_capability_holder": commit_holders[0],
        "status": "PASS",
    }


def verify_evolution_chamber_binding(document: Mapping[str, Any]) -> dict[str, Any]:
    """Prove the chamber delegates promotion to the canonical subworkflow."""

    nodes = _node_map(document)
    promotion = nodes.get("run_evidence_parliament_promotion")
    if promotion is None:
        raise EvolutionAuthorityError(
            "WORKFLOW_INVALID", "chamber promotion node is missing"
        )
    if (
        promotion.get("executor_type") != "subworkflow"
        or promotion.get("executor_ref")
        != "workflows/evolution_promotion.workflow.yaml"
    ):
        raise EvolutionAuthorityError(
            "PROMOTION_NOT_DELEGATED",
            "the chamber must delegate promotion to workflows/evolution_promotion.workflow.yaml",
        )
    if promotion.get("output_schema_ref") == PROMOTION_DECISION_SCHEMA:
        raise EvolutionAuthorityError(
            "PROMOTION_DECISION_EXECUTOR_INVALID",
            "the chamber node cannot emit the PromotionDecision directly",
        )
    for node_id, node in nodes.items():
        if node.get("executor_type") == "llm" and node.get("output_schema_ref") == (
            PROMOTION_DECISION_SCHEMA
        ):
            raise EvolutionAuthorityError(
                "LLM_AUTHORITY_VIOLATION",
                f"llm node {node_id} emits a PromotionDecision",
            )
    return {
        "workflow_id": document.get("workflow_id"),
        "promotion_delegation": promotion.get("executor_ref"),
        "status": "PASS",
    }
