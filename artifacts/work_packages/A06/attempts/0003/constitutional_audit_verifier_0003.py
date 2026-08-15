#!/usr/bin/env python3
"""A06-0003 constitutional re-audit after the A05 promotion-runtime change.

A06-0002 reported ``A06-F005 PASS`` by asserting an implementation shape: that
every executable node reference began with the single module prefix
``...evolution_authority.nodes:``, and that the literal strings
``PromotionCommitter`` and ``decide_promotion(request)`` appeared in
``nodes.py``.

A05 subsequently split the three commit-phase nodes into ``promotion.py`` and
``reconciliation.py`` so the commit path could invoke a Kernel lease-protected
transaction through an injected port.  All three assertions became false while
the finding they were meant to detect stayed closed.

This attempt re-derives F005 from what the finding actually says: the bounded
promotion helper must be bound to the canonical evolution workflow.  It checks
the A05 *package* as the authority boundary, resolves each executor and
confirms the callable is defined inside that package, and verifies the helper
is genuinely reachable from the commit path -- rather than requiring one module
name or two source substrings.

The verifier is read-only outside this attempt directory.
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/A06/attempts/0003"
OUTPUT = ATTEMPT / "constitutional-audit-verification.json"
ATTEMPT_ID = "A06-0003"
sys.path.insert(0, str(ROOT / "src"))

#: The A05 package is the authority boundary.  A promotion node may be
#: implemented in any module A05 owns, but never outside the package.
AUTHORITY_PACKAGE = "epistemic_foundry.governance.evolution_authority"
EXECUTABLE_TYPES = frozenset({"deterministic", "policy", "human_gate"})


def load_yaml(relative: str) -> Any:
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def _resolve_executor(module_path: str, attribute: str, node_id: str) -> Any:
    """Resolve an executor the way the runtime actually resolves it.

    Gate executors are generated per gate and published through the node
    entrypoint table rather than as module attributes, so the table is the
    authoritative lookup and the module attribute is the fallback.
    """

    module = importlib.import_module(module_path)
    table = getattr(module, "NODE_ENTRYPOINTS", None)
    if isinstance(table, dict) and attribute == node_id and node_id in table:
        return table[node_id]
    return getattr(module, attribute, None)


def audit_f005_runtime_binding() -> dict[str, Any]:
    workflow = load_yaml("workflows/evolution_promotion.workflow.yaml")
    nodes = [
        node
        for node in workflow["nodes"]
        if node.get("executor_type") in EXECUTABLE_TYPES
    ]

    unbound: list[str] = []
    foreign: list[str] = []
    unresolved: list[str] = []
    modules: set[str] = set()

    for node in nodes:
        node_id = str(node["node_id"])
        ref = str(node.get("executor_ref", ""))
        module_path, separator, attribute = ref.partition(":")
        if not separator or not attribute or not module_path.startswith(
            f"{AUTHORITY_PACKAGE}."
        ):
            unbound.append(node_id)
            continue
        try:
            executor = _resolve_executor(module_path, attribute, node_id)
        except ImportError:
            unresolved.append(node_id)
            continue
        if not callable(executor) or attribute != node_id:
            unresolved.append(node_id)
            continue
        # A module inside the package can still hold a callable imported from
        # elsewhere, so the defining module is what decides ownership.
        if not getattr(executor, "__module__", "").startswith(AUTHORITY_PACKAGE):
            foreign.append(node_id)
            continue
        modules.add(module_path)

    # The finding is about the bounded helper reaching the canonical workflow.
    # Check reachability from the commit path instead of grepping one file.
    promotion_module = importlib.import_module(f"{AUTHORITY_PACKAGE}.promotion")
    commit_source = inspect.getsource(promotion_module)
    helper_module = importlib.import_module("epistemic_foundry.governance.promotion")
    helper_source = inspect.getsource(helper_module)

    bindings = {
        "chamber_delegates_to_promotion_workflow": (
            "workflows/evolution_promotion.workflow.yaml"
            in (ROOT / "workflows/evolution_chamber_cycle.workflow.yaml").read_text(
                encoding="utf-8"
            )
        ),
        "decider_defined": "def decide_promotion" in helper_source,
        "semantic_validator_defined": (
            "def validate_promotion_decision_semantics" in helper_source
        ),
        "commit_path_invokes_decider": "decide_promotion(" in commit_source,
        "commit_path_invokes_semantic_validator": (
            "validate_promotion_decision_semantics(" in commit_source
        ),
        "commit_path_refuses_without_trusted_port": (
            "require_commit_port(" in commit_source
        ),
    }

    ok = (
        not unbound
        and not foreign
        and not unresolved
        and all(bindings.values())
        and len(nodes) == 21
    )
    return {
        "authority_package": AUTHORITY_PACKAGE,
        "bindings": bindings,
        "f005_status": "PASS" if ok else "FAIL",
        "foreign_runtime_nodes": sorted(foreign),
        "implementing_modules": sorted(modules),
        "runtime_bound_node_count": len(nodes) - len(unbound),
        "superseded_attempt_assumptions": [
            "single module prefix ...evolution_authority.nodes:",
            "literal 'PromotionCommitter' in nodes.py",
            "literal 'decide_promotion(request)' in nodes.py",
        ],
        "unbound_runtime_nodes": sorted(unbound),
        "unresolved_runtime_nodes": sorted(unresolved),
    }


def main() -> int:
    finding = audit_f005_runtime_binding()
    record = {
        "attempt_id": ATTEMPT_ID,
        "f005": finding,
        "scope": (
            "F005 runtime-binding re-audit only.  A06-0002 findings F001-F004 "
            "and the schema-meta audit are unaffected by the A05 promotion "
            "runtime change and remain valid as recorded."
        ),
    }
    OUTPUT.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(record["f005"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if finding["f005_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
