#!/usr/bin/env python3
"""A03 required check ``boundary_cycle_policy_check``.

Deterministic attestation that the module / boundary map declared in
``docs/v4_plugin_architecture.md`` (section 4 dependency map and section 5 cycle
policy), reinforced by ADR-032, refined by ADR-034, and by the declared
boundary graph in ``packages/boundary-policy.json``, has no forbidden dependency
cycle and no authority-to-adapter inversion.

The check follows the definition ADR-032 pins for ``boundary_cycle_policy_check``
and the refinement ADR-034 makes to ADR-032 rule 5. It parses the actual Python
imports under ``src/epistemic_foundry`` and enforces, fail-closed, every one of:

1. **Layer discipline.** No importer -> dependency edge where the dependency is
   more outward (``rank(dependency) > rank(importer)``); and no authority
   (L0/L1/L2) component imports an adapter (L4) component.
2. **No authority/adapter in any cycle.** No L0/L1/L2 authority component
   (``contracts``, ``domain``, ``noetic_ledger``, ``foundry_kernel``) and no L4
   adapter (``plugin_shell``, ``providers``, ``shinka_adapter``, ``cli``,
   ``adapters``) may appear in ANY strongly connected component of size >= 2 at
   ANY granularity (top-level or module-slice). No allowlist entry may cover
   such a component.
3. **Module-slice acyclicity (load-bearing runtime invariant, ADR-034).** The
   import graph at MODULE-SLICE granularity — each top-level component AND each
   ``component/v4_*`` subpackage is a distinct node, every import resolved to its
   finest slice — MUST be a strict DAG. Any module-slice cycle is a real runtime
   circular import and fails the check unconditionally. This is strictly more
   obligation than a top-level-only cycle check.
4. **Fingerprinted top-level exception (ADR-034).** A top-level component SCC of
   size >= 2 is admitted only if it (a) is exactly size 2, (b) is two L3 governed
   services, (c) matches an enumerated exemption whose exact component pair AND
   module->module carrier-edge set is pinned as a fingerprint, (d) has every
   carrier cross-edge be a public ``component/v4_*`` package-API import with no
   private-submodule reach-in, and (e) has an acyclic module-slice subgraph on
   the pair. A new top-level cycle, a grown >= 3 SCC, a changed carrier module,
   a private reach-in, or any unpinned pair fails the check.
5. **Documented-policy anchors + declared boundary graph.** The architecture map
   anchors, the inward layer ordering, ``sourceImportPolicy =
   public-package-api-only``, and ``duplicateImplementationPolicy = forbidden``
   are all still required (never dropped).

Layer model (inward = lower rank; an edge is allowed only when the dependency's
rank is <= the importer's rank):

    L0 foundation : contracts, domain          (imports no EF component)
    L1 ledger     : noetic_ledger              (imports L0 only)
    L2 kernel     : foundry_kernel             (imports L0, L1)
    L3 service    : every other component      (imports L0/L1/L2 + acyclic peers)
    L4 adapter    : plugin_shell, providers,   (composition layer; imports inward)
                    shinka_adapter, cli, adapters

The two top-level 2-cycles tolerated under ADR-034 are, with fingerprints:

    E1 operators <-> security
       security/v4_s06 -> operators/v4_j05   (governance retroactivity surface)
       operators/v4_j05 -> security/v4_s05   (inert-mutation threat control)
    E2 evidence <-> retrieval
       evidence/v4_k06 -> retrieval/v4_o05   (plan-identity / receipt schema)
       retrieval/v4_o05 -> evidence/v4_k05   (novelty-within-boundary)
       retrieval/v4_o06 -> evidence/v4_k05   (novelty-within-boundary)

Both are strict DAGs at module-slice granularity — no runtime circular import.

This is attestation evidence. It reads documents and source; it never edits
them. Every assertion is fail-closed.

Run as a pytest module::

    .venv/Scripts/python.exe -m pytest \
        artifacts/work_packages/A03/attempts/0001/test_boundary_cycle_policy_check.py \
        -p no:cacheprovider

Or standalone to emit deterministic JSON evidence::

    .venv/Scripts/python.exe \
        artifacts/work_packages/A03/attempts/0001/test_boundary_cycle_policy_check.py \
        --output artifacts/work_packages/A03/attempts/0001/boundary-cycle-policy-check.json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[5]

ARCH_DOC = ROOT / "docs/v4_plugin_architecture.md"
BOUNDARY_POLICY = ROOT / "packages/boundary-policy.json"
PY_ROOT = ROOT / "src/epistemic_foundry"
PY_PACKAGE = "epistemic_foundry"

#: Layer ranks. Lower rank is more inward; an edge importer -> dependency is
#: allowed only when rank(dependency) <= rank(importer).
FOUNDATION, LEDGER, KERNEL, SERVICE, ADAPTER = 0, 1, 2, 3, 4
RANK_NAME = {
    FOUNDATION: "L0 foundation",
    LEDGER: "L1 ledger",
    KERNEL: "L2 kernel",
    SERVICE: "L3 service",
    ADAPTER: "L4 adapter",
}

FOUNDATION_COMPONENTS = frozenset({"contracts", "domain"})
LEDGER_COMPONENTS = frozenset({"noetic_ledger"})
KERNEL_COMPONENTS = frozenset({"foundry_kernel"})
ADAPTER_COMPONENTS = frozenset(
    {"plugin_shell", "providers", "shinka_adapter", "cli", "adapters"}
)

#: Components that may never appear in any cycle at any granularity (ADR-034).
AUTHORITY_COMPONENTS = FOUNDATION_COMPONENTS | LEDGER_COMPONENTS | KERNEL_COMPONENTS
FORBIDDEN_IN_CYCLE = AUTHORITY_COMPONENTS | ADAPTER_COMPONENTS

#: Documented-policy anchors that must be present in the architecture map so the
#: layer constants above stay tied to the human boundary contract.
DOC_ANCHORS: tuple[tuple[str, str], ...] = (
    ("acyclic requirement", r"must be acyclic|graph must be a directed acyclic|acyclic"),
    ("inward-only rule", r"inward or to a lower-numbered layer"),
    ("L4 composition-only", r"L4 is the only composition layer"),
    (
        "authority never imports adapters",
        r"Kernel and Ledger may\s*\n?\s*never import Plugin Shell",
    ),
    ("foundry_kernel is L2", r"L2 foundry_kernel"),
    ("noetic_ledger is L1", r"L1 noetic_ledger"),
    ("contracts/domain are L0", r"L0 contracts\s*·?\s*domain"),
    ("boundary change needs ADR", r"boundary change requires a new ADR"),
    ("module-slice granularity (ADR-034)", r"module-slice granularity"),
)


# --------------------------------------------------------------------------- #
# ADR-034 fingerprinted exemptions (closed list)
# --------------------------------------------------------------------------- #
class Exemption:
    """A pinned, fingerprinted top-level 2-cycle permitted by ADR-034."""

    __slots__ = ("name", "pair", "carrier_edges", "justification")

    def __init__(
        self,
        name: str,
        pair: frozenset[str],
        carrier_edges: frozenset[tuple[str, str]],
        justification: str,
    ) -> None:
        self.name = name
        self.pair = pair
        self.carrier_edges = carrier_edges
        self.justification = justification


EXEMPT_TOP_LEVEL_CYCLES: tuple[Exemption, ...] = (
    Exemption(
        name="E1",
        pair=frozenset({"operators", "security"}),
        carrier_edges=frozenset(
            {
                ("security/v4_s06", "operators/v4_j05"),
                ("operators/v4_j05", "security/v4_s05"),
            }
        ),
        justification=(
            "ADR-034: L3<->L3 integration gate. security.v4_s06 consumes the "
            "governance-retroactivity public surface of operators.v4_j05; "
            "operators.v4_j05 consumes the inert-mutation threat-control public "
            "surface of security.v4_s05. Module-slice graph is a strict DAG; no "
            "authority/adapter participates; sealed public APIs unchanged."
        ),
    ),
    Exemption(
        name="E2",
        pair=frozenset({"evidence", "retrieval"}),
        carrier_edges=frozenset(
            {
                ("evidence/v4_k06", "retrieval/v4_o05"),
                ("retrieval/v4_o05", "evidence/v4_k05"),
                ("retrieval/v4_o06", "evidence/v4_k05"),
            }
        ),
        justification=(
            "ADR-034: L3<->L3 integration gate. evidence.v4_k06 consumes the "
            "plan-identity / receipt-schema public surface of retrieval.v4_o05; "
            "retrieval.v4_o05 and retrieval.v4_o06 consume the "
            "novelty-within-boundary public surface of evidence.v4_k05. "
            "Module-slice graph is a strict DAG; no authority/adapter "
            "participates; sealed public APIs unchanged."
        ),
    ),
)


class BoundaryError(AssertionError):
    """Fail-closed boundary-policy violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BoundaryError(message)


def read_text(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    require(path.is_file(), f"required document missing: {rel}")
    data = path.read_bytes()
    require(not data.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM forbidden: {rel}")
    text = data.decode("utf-8", errors="strict")
    require("�" not in text, f"replacement character found: {rel}")
    return text


# --------------------------------------------------------------------------- #
# documented-policy anchors
# --------------------------------------------------------------------------- #
def check_doc_anchors() -> dict[str, bool]:
    text = read_text(ARCH_DOC)
    present: dict[str, bool] = {}
    for label, pattern in DOC_ANCHORS:
        found = re.search(pattern, text, re.IGNORECASE) is not None
        require(found, f"docs/v4_plugin_architecture.md: missing policy anchor: {label}")
        present[label] = True
    return present


# --------------------------------------------------------------------------- #
# declared boundary graph (packages/boundary-policy.json)
# --------------------------------------------------------------------------- #
def check_declared_boundary_graph() -> dict[str, Any]:
    text = read_text(BOUNDARY_POLICY)
    policy = json.loads(text)
    require(
        policy.get("sourceImportPolicy") == "public-package-api-only",
        "boundary-policy.json: sourceImportPolicy must be 'public-package-api-only'",
    )
    layers = policy.get("layers")
    require(isinstance(layers, dict) and layers, "boundary-policy.json: missing layers")

    # The declared layer ranks must respect the inward ordering.
    order = ["foundation", "authority", "service", "adapter"]
    ranks = []
    for name in order:
        require(name in layers, f"boundary-policy.json: layer {name!r} not declared")
        ranks.append(layers[name])
    require(
        ranks == sorted(ranks) and len(set(ranks)) == len(ranks),
        f"boundary-policy.json: layer ranks not strictly inward-ordered: "
        f"{dict(zip(order, ranks))}",
    )

    components = policy.get("components")
    require(isinstance(components, list) and components, "boundary-policy.json: no components")
    for comp in components:
        require(
            comp.get("layer") in layers,
            f"boundary-policy.json: component {comp.get('directory')!r} has "
            f"undeclared layer {comp.get('layer')!r}",
        )

    require(
        policy.get("python", {}).get("duplicateImplementationPolicy") == "forbidden",
        "boundary-policy.json: python.duplicateImplementationPolicy must be 'forbidden'",
    )
    return {
        "layer_ranks": {name: layers[name] for name in order},
        "declared_component_count": len(components),
        "inward_ordered": True,
    }


# --------------------------------------------------------------------------- #
# Python import graph over src/epistemic_foundry (module-slice granularity)
# --------------------------------------------------------------------------- #
def discover_components() -> set[str]:
    require(PY_ROOT.is_dir(), "src/epistemic_foundry missing")
    components: set[str] = set()
    for child in PY_ROOT.iterdir():
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        if any(child.rglob("*.py")):
            components.add(child.name)
    require(bool(components), "src/epistemic_foundry: no component packages found")
    return components


def layer_of(component: str) -> int:
    if component in FOUNDATION_COMPONENTS:
        return FOUNDATION
    if component in LEDGER_COMPONENTS:
        return LEDGER
    if component in KERNEL_COMPONENTS:
        return KERNEL
    if component in ADAPTER_COMPONENTS:
        return ADAPTER
    return SERVICE


def component_of(slice_name: str) -> str:
    return slice_name.split("/", 1)[0]


def _slice_of_parts(parts: list[str]) -> str:
    """Collapse resolved package parts to their finest module slice.

    ``parts`` is e.g. ``['epistemic_foundry', 'security', 'v4_s06', ...]``. The
    slice is the top-level component, plus the first ``v4_*`` subpackage segment
    when present, so each component and each ``component/v4_*`` is a distinct
    node.
    """
    component = parts[1]
    if len(parts) >= 3 and parts[2].startswith("v4_"):
        return f"{component}/{parts[2]}"
    return component


def _package_parts(py_file: Path) -> list[str]:
    """Return the module's package path parts, e.g. ['epistemic_foundry','cli']."""
    rel = py_file.relative_to(PY_ROOT.parent)  # relative to src/
    parts = list(rel.parts)
    return parts[:-1]


def file_slice(py_file: Path) -> str:
    """Finest module slice that owns ``py_file``."""
    rel_parts = list(py_file.relative_to(PY_ROOT).parts)
    component = rel_parts[0]
    if len(rel_parts) >= 2 and rel_parts[1].startswith("v4_"):
        return f"{component}/{rel_parts[1]}"
    return component


def _resolve_target_parts(
    module: str | None, level: int, pkg_parts: list[str]
) -> list[str] | None:
    """Resolve an import to its absolute ``epistemic_foundry.*`` parts list."""
    if level == 0:
        if not module:
            return None
        parts = module.split(".")
    else:
        if level - 1 > len(pkg_parts):
            return None
        base = pkg_parts[: len(pkg_parts) - (level - 1)]
        parts = base + (module.split(".") if module else [])
    if len(parts) < 2 or parts[0] != PY_PACKAGE:
        return None
    return parts


def build_module_graph(
    components: set[str],
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Return ``(edges, private_reachin_edges)`` at module-slice granularity.

    ``edges`` is the set of ``(importer_slice, dependency_slice)`` cross-slice
    edges. ``private_reachin_edges`` is the subset whose underlying import
    reaches into a submodule *beneath* the dependency slice's public
    ``component/v4_*`` package boundary (i.e. not a public-package-API import).
    """
    edges: set[tuple[str, str]] = set()
    private_reachin: set[tuple[str, str]] = set()

    def _consider(src_slice: str, parts: list[str]) -> None:
        dep_component = parts[1]
        if dep_component not in components:
            return
        dep_slice = _slice_of_parts(parts)
        if dep_slice == src_slice:
            return
        edge = (src_slice, dep_slice)
        edges.add(edge)
        # Public-package-API depth: a ``component/v4_x`` slice's public boundary
        # is exactly ``epistemic_foundry.component.v4_x`` (3 parts). Anything
        # deeper reaches into a private submodule beneath the v4_* public API.
        if "/" in dep_slice:
            if len(parts) > 3:
                private_reachin.add(edge)

    for py_file in sorted(PY_ROOT.rglob("*.py")):
        rel_parts = py_file.relative_to(PY_ROOT).parts
        owner = rel_parts[0]
        if owner not in components:
            continue
        try:
            tree = ast.parse(py_file.read_bytes(), filename=str(py_file))
        except SyntaxError as exc:  # pragma: no cover - fail closed
            raise BoundaryError(
                f"{py_file.relative_to(ROOT).as_posix()}: syntax error: {exc}"
            ) from exc
        src_slice = file_slice(py_file)
        pkg_parts = _package_parts(py_file)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    parts = _resolve_target_parts(alias.name, 0, pkg_parts)
                    if parts is not None:
                        _consider(src_slice, parts)
            elif isinstance(node, ast.ImportFrom):
                base = _resolve_target_parts(node.module, node.level, pkg_parts)
                if base is None:
                    continue
                _consider(src_slice, base)
                # Refine ``from ...component import v4_x`` to the finest slice by
                # inspecting the imported names against real v4_* subpackages.
                if len(base) == 2:
                    for alias in node.names:
                        name = alias.name
                        if name.startswith("v4_") and (PY_ROOT / base[1] / name).is_dir():
                            _consider(src_slice, base + [name])
    return edges, private_reachin


# --------------------------------------------------------------------------- #
# strongly connected components (Tarjan, iterative)
# --------------------------------------------------------------------------- #
def strongly_connected_components(
    nodes: set[str], edges: set[tuple[str, str]]
) -> list[list[str]]:
    adjacency: dict[str, list[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        adjacency.setdefault(src, [])
        adjacency.setdefault(dst, [])
    for src, dst in edges:
        adjacency[src].append(dst)
    for node in adjacency:
        adjacency[node].sort()

    index_counter = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    result: list[list[str]] = []

    for start in sorted(adjacency):
        if start in indices:
            continue
        work: list[tuple[str, int]] = [(start, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                indices[node] = index_counter
                lowlink[node] = index_counter
                index_counter += 1
                stack.append(node)
                on_stack[node] = True
            recursed = False
            neighbours = adjacency[node]
            for j in range(pi, len(neighbours)):
                nxt = neighbours[j]
                if nxt not in indices:
                    work[-1] = (node, j + 1)
                    work.append((nxt, 0))
                    recursed = True
                    break
                if on_stack.get(nxt):
                    lowlink[node] = min(lowlink[node], indices[nxt])
            if recursed:
                continue
            if lowlink[node] == indices[node]:
                component: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    component.append(w)
                    if w == node:
                        break
                result.append(sorted(component))
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
    return result


# --------------------------------------------------------------------------- #
# core fail-closed boundary predicate (pure; unit-testable in isolation)
# --------------------------------------------------------------------------- #
def evaluate_boundary(
    module_edges: set[tuple[str, str]],
    *,
    private_reachin_edges: frozenset[tuple[str, str]] = frozenset(),
    component_layer: Callable[[str], int] = layer_of,
    exemptions: tuple[Exemption, ...] = EXEMPT_TOP_LEVEL_CYCLES,
) -> dict[str, Any]:
    """Apply every fail-closed boundary obligation to a module-slice graph.

    Raises :class:`BoundaryError` on any violation; returns evidence on success.
    """
    module_nodes = {s for e in module_edges for s in e}

    # Top-level component graph derived from the module-slice graph.
    top_edges: set[tuple[str, str]] = set()
    for src_slice, dst_slice in module_edges:
        a, b = component_of(src_slice), component_of(dst_slice)
        if a != b:
            top_edges.add((a, b))
    top_nodes = {c for e in top_edges for c in e}

    # -- Obligation 1a: layer discipline (no outward-pointing edge). --------- #
    inversions: list[dict[str, Any]] = []
    for a, b in sorted(top_edges):
        ra, rb = component_layer(a), component_layer(b)
        if rb > ra:
            inversions.append(
                {
                    "importer": a,
                    "importer_layer": RANK_NAME[ra],
                    "dependency": b,
                    "dependency_layer": RANK_NAME[rb],
                }
            )
    require(
        not inversions,
        "forbidden layer-inverting import edge(s): "
        + "; ".join(
            f"{f['importer']}({f['importer_layer']}) -> "
            f"{f['dependency']}({f['dependency_layer']})"
            for f in inversions
        ),
    )

    # -- Obligation 1b: no authority component imports an adapter. ----------- #
    for a, b in sorted(top_edges):
        if a in AUTHORITY_COMPONENTS and b in ADAPTER_COMPONENTS:
            require(False, f"authority component {a} imports adapter {b}")

    # -- Obligation 3: module-slice graph must be a strict DAG. -------------- #
    module_sccs = [c for c in strongly_connected_components(module_nodes, module_edges) if len(c) >= 2]
    # self-loops (a slice importing itself) never occur (skipped at build), so a
    # module SCC always means a genuine multi-node circular import.
    for scc in module_sccs:
        offenders = sorted({component_of(s) for s in scc} & FORBIDDEN_IN_CYCLE)
        require(
            not offenders,
            f"authority/adapter component(s) {offenders} in module-slice cycle: "
            f"{' -> '.join(scc + [scc[0]])}",
        )
    require(
        not module_sccs,
        "forbidden module-slice import cycle (runtime circular import): "
        + "; ".join(" -> ".join(scc + [scc[0]]) for scc in module_sccs),
    )

    # -- Obligation 2 + 4: top-level SCC discipline + fingerprinted allowlist. #
    permitted: list[dict[str, Any]] = []
    for scc in strongly_connected_components(top_nodes, top_edges):
        if len(scc) < 2:
            continue
        # Obligation 2: no authority/adapter may appear in any top-level cycle.
        offenders = sorted(set(scc) & FORBIDDEN_IN_CYCLE)
        require(
            not offenders,
            f"authority/adapter component(s) {offenders} in top-level cycle: "
            f"{' -> '.join(scc + [scc[0]])}",
        )
        # (a) exactly size 2.
        require(
            len(scc) == 2,
            f"forbidden top-level cycle of size {len(scc)} (>2): "
            f"{' -> '.join(scc + [scc[0]])} — a further ADR is required",
        )
        pair = frozenset(scc)
        # (b) both L3 services.
        require(
            all(component_layer(c) == SERVICE for c in scc),
            f"top-level 2-cycle {sorted(scc)} contains a non-L3 component",
        )
        # (c) matches a pinned exemption pair.
        match = next((ex for ex in exemptions if ex.pair == pair), None)
        require(
            match is not None,
            f"top-level 2-cycle {sorted(scc)} is not in the ADR-034 allowlist",
        )
        assert match is not None  # for type-checkers
        # (c cont.) exact carrier-edge fingerprint.
        actual_carriers = frozenset(
            (s, d)
            for (s, d) in module_edges
            if {component_of(s), component_of(d)} == pair
            and component_of(s) != component_of(d)
        )
        require(
            actual_carriers == match.carrier_edges,
            f"ADR-034 {match.name} carrier fingerprint mismatch for {sorted(pair)}: "
            f"expected {sorted(match.carrier_edges)}, found {sorted(actual_carriers)}",
        )
        # (d) every carrier is a public-package-API import (no private reach-in).
        reachins = sorted(actual_carriers & private_reachin_edges)
        require(
            not reachins,
            f"ADR-034 {match.name}: private-submodule reach-in on carrier "
            f"edge(s) {reachins} — carriers must import the v4_* public API only",
        )
        # (e) the module-slice subgraph induced on the pair is acyclic.
        pair_nodes = {s for s in module_nodes if component_of(s) in pair}
        pair_edges = {
            (s, d)
            for (s, d) in module_edges
            if s in pair_nodes and d in pair_nodes
        }
        induced_cycles = [
            c for c in strongly_connected_components(pair_nodes, pair_edges) if len(c) >= 2
        ]
        require(
            not induced_cycles,
            f"ADR-034 {match.name}: module-slice subgraph on {sorted(pair)} is "
            f"cyclic: {induced_cycles}",
        )
        permitted.append(
            {
                "exemption": match.name,
                "adr": "ADR-034",
                "components": sorted(pair),
                "carrier_edges": sorted(f"{s} -> {d}" for s, d in actual_carriers),
                "both_l3_services": True,
                "module_slice_subgraph_acyclic": True,
                "public_package_api_only": True,
                "justification": match.justification,
            }
        )

    permitted.sort(key=lambda p: p["exemption"])
    return {
        "top_level_edge_count": len(top_edges),
        "module_slice_edge_count": len(module_edges),
        "module_slice_node_count": len(module_nodes),
        "layer_inversions": 0,
        "authority_imports_adapter": False,
        "module_slice_acyclic": True,
        "top_level_cycles_permitted": permitted,
        "top_level_forbidden_cycles": 0,
    }


# --------------------------------------------------------------------------- #
# evidence assembly (live tree)
# --------------------------------------------------------------------------- #
def build_evidence() -> dict[str, Any]:
    doc_anchors = check_doc_anchors()
    declared = check_declared_boundary_graph()
    components = discover_components()
    module_edges, private_reachin = build_module_graph(components)

    boundary = evaluate_boundary(
        module_edges,
        private_reachin_edges=frozenset(private_reachin),
    )

    module_nodes = {s for e in module_edges for s in e} | set(components)
    layer_histogram: dict[str, int] = {name: 0 for name in RANK_NAME.values()}
    for comp in components:
        layer_histogram[RANK_NAME[layer_of(comp)]] += 1

    return {
        "schema_version": 2,
        "work_package_id": "A03",
        "attempt_id": "A03-0001",
        "check": "boundary_cycle_policy_check",
        "status": "PASS",
        "governing_records": ["ADR-032", "ADR-034"],
        "documented_policy_anchors": doc_anchors,
        "declared_boundary_graph": declared,
        "python_import_graph": {
            "root": "src/epistemic_foundry",
            "component_count": len(components),
            "module_slice_node_count": len(module_nodes),
            "module_slice_edge_count": len(module_edges),
            "top_level_edge_count": boundary["top_level_edge_count"],
            "layer_histogram": layer_histogram,
        },
        "layer_discipline": {
            "layer_inversions": boundary["layer_inversions"],
            "authority_imports_adapter": boundary["authority_imports_adapter"],
        },
        "module_slice_graph_is_strict_dag": boundary["module_slice_acyclic"],
        "authority_or_adapter_in_any_cycle": False,
        "top_level_forbidden_cycle_count": boundary["top_level_forbidden_cycles"],
        "adr_034_permitted_cycles": boundary["top_level_cycles_permitted"],
        "exit_criterion": {
            "plugin_shell_and_kernel_authority_separated": True,
            "component_import_boundaries_documented": True,
        },
    }


# --------------------------------------------------------------------------- #
# pytest surface
# --------------------------------------------------------------------------- #
def test_documented_policy_anchors_present() -> None:
    evidence = build_evidence()
    assert evidence["status"] == "PASS"
    assert all(evidence["documented_policy_anchors"].values())


def test_declared_boundary_graph_inward_ordered() -> None:
    assert build_evidence()["declared_boundary_graph"]["inward_ordered"] is True


def test_no_layer_inversions_and_no_authority_adapter_import() -> None:
    evidence = build_evidence()
    assert evidence["layer_discipline"]["layer_inversions"] == 0
    assert evidence["layer_discipline"]["authority_imports_adapter"] is False


def test_module_slice_graph_is_strict_dag() -> None:
    evidence = build_evidence()
    assert evidence["module_slice_graph_is_strict_dag"] is True
    assert evidence["authority_or_adapter_in_any_cycle"] is False


def test_top_level_cycles_are_only_the_two_adr034_exemptions() -> None:
    evidence = build_evidence()
    assert evidence["top_level_forbidden_cycle_count"] == 0
    permitted = evidence["adr_034_permitted_cycles"]
    pairs = sorted(p["components"] for p in permitted)
    assert pairs == [["evidence", "retrieval"], ["operators", "security"]]
    for entry in permitted:
        assert entry["both_l3_services"] is True
        assert entry["module_slice_subgraph_acyclic"] is True
        assert entry["public_package_api_only"] is True


def test_exit_criteria_attested() -> None:
    crit = build_evidence()["exit_criterion"]
    assert crit["plugin_shell_and_kernel_authority_separated"] is True
    assert crit["component_import_boundaries_documented"] is True


# --------------------------------------------------------------------------- #
# standalone evidence emitter
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="A03 boundary_cycle_policy_check")
    parser.add_argument(
        "--output", type=Path, help="Write deterministic JSON evidence to this path"
    )
    args = parser.parse_args()
    try:
        evidence = build_evidence()
    except BoundaryError as exc:
        print(f"A03_BOUNDARY_CYCLE_POLICY_CHECK_FAIL: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output = output.resolve()
        require(output.is_relative_to(ROOT.resolve()), "output must stay inside repo")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        print(
            "A03_BOUNDARY_CYCLE_POLICY_CHECK_PASS: wrote "
            + output.relative_to(ROOT.resolve()).as_posix()
        )
    else:
        sys.stdout.write(rendered)
        print("A03_BOUNDARY_CYCLE_POLICY_CHECK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
