#!/usr/bin/env python3
"""A03 adversarial negative tests for ``boundary_cycle_policy_check``.

These tests exercise the *fail-closed* boundary predicate
``evaluate_boundary`` (the pure core of ``test_boundary_cycle_policy_check``)
on synthetic module-slice graphs to prove the refined ADR-034 predicate
RAISES on every forbidden shape and only PASSES on the two real, pinned
exemptions. They are deliberately hostile: each case is a minimal graph that
isolates one obligation.

Required negative predicates (each must raise :class:`BoundaryError`):

  (i)   an injected 3-node top-level cycle (module-slice acyclic, so it can
        only be rejected by the size-2 top-level rule);
  (ii)  an authority component (``foundry_kernel``) inside a cycle;
  (iii) an adapter component (``providers``) inside a cycle;
  (iv)  an injected MODULE-LEVEL cycle within an exempt component pair;
  (v)   a top-level 2-cycle between two L3 services NOT on the allowlist;
  (vi)  a layer inversion (importer depends on a more-outward layer).

Plus positive control: the two real ADR-034 exemptions PASS, and extra
adversarial fingerprint probes (private reach-in, added carrier edge) fail.

These tests never touch the live tree; they feed hand-built edge sets to the
predicate under test. They import that predicate directly from the sibling
check module so any drift in the real predicate is caught here.

Run::

    .venv/Scripts/python.exe -m pytest \
        artifacts/work_packages/A03/attempts/0001/test_boundary_cycle_policy_negative.py \
        -p no:cacheprovider
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Load the predicate under test from the sibling check module by path so the
# negative suite is pinned to the exact live implementation.
# --------------------------------------------------------------------------- #
_HERE = Path(__file__).resolve().parent
_CHECK_PATH = _HERE / "test_boundary_cycle_policy_check.py"
_spec = importlib.util.spec_from_file_location(
    "a03_boundary_cycle_policy_check_under_test", _CHECK_PATH
)
assert _spec is not None and _spec.loader is not None
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)

evaluate_boundary = bc.evaluate_boundary
BoundaryError = bc.BoundaryError
EXEMPT_TOP_LEVEL_CYCLES = bc.EXEMPT_TOP_LEVEL_CYCLES


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _real_exemption_edges() -> set[tuple[str, str]]:
    """Exactly the pinned carrier edges of both ADR-034 exemptions."""
    edges: set[tuple[str, str]] = set()
    for ex in EXEMPT_TOP_LEVEL_CYCLES:
        edges |= set(ex.carrier_edges)
    return edges


# --------------------------------------------------------------------------- #
# POSITIVE CONTROL: the two real exemptions pass.
# --------------------------------------------------------------------------- #
def test_real_two_exemptions_pass() -> None:
    edges = _real_exemption_edges()
    evidence = evaluate_boundary(edges)
    permitted = evidence["top_level_cycles_permitted"]
    pairs = sorted(p["components"] for p in permitted)
    assert pairs == [["evidence", "retrieval"], ["operators", "security"]]
    assert evidence["module_slice_acyclic"] is True
    assert evidence["layer_inversions"] == 0
    assert evidence["authority_imports_adapter"] is False
    assert evidence["top_level_forbidden_cycles"] == 0
    for entry in permitted:
        assert entry["both_l3_services"] is True
        assert entry["module_slice_subgraph_acyclic"] is True
        assert entry["public_package_api_only"] is True


# --------------------------------------------------------------------------- #
# (i) injected 3-node top-level cycle — module-slice acyclic, so it is only
#     catchable by the "exactly size 2" top-level rule.
# --------------------------------------------------------------------------- #
def test_injected_three_node_top_level_cycle_raises() -> None:
    # Each top-level edge is carried by a *distinct* slice pair, so the
    # module-slice graph is a strict DAG and obligation 3 does not fire first;
    # the 3-cycle exists only at top-level granularity.
    edges = {
        ("aaa/v4_1", "bbb/v4_1"),
        ("bbb/v4_2", "ccc/v4_1"),
        ("ccc/v4_2", "aaa/v4_2"),
    }
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges)
    msg = str(exc.value)
    assert "size 3" in msg
    assert "a further ADR is required" in msg


# --------------------------------------------------------------------------- #
# (ii) authority (foundry_kernel) in a cycle. A kernel-containing cycle always
#      forces an outward (inverting) edge — the predicate is fail-closed either
#      way. A companion equal-rank authority cycle proves the DEDICATED
#      authority-in-cycle guard (obligation 2/3) fires without relying on the
#      inversion check.
# --------------------------------------------------------------------------- #
def test_authority_kernel_in_cycle_raises() -> None:
    edges = {
        ("reasoning/v4_1", "foundry_kernel/v4_1"),
        ("foundry_kernel/v4_2", "reasoning/v4_2"),
    }
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges)
    # foundry_kernel (L2) importing reasoning (L3) is an outward edge.
    assert "foundry_kernel" in str(exc.value)


def test_authority_in_top_level_cycle_without_inversion_raises() -> None:
    # contracts and domain are both L0 -> no layer inversion; this isolates the
    # dedicated "authority/adapter in any top-level cycle" guard.
    edges = {
        ("contracts/v4_1", "domain/v4_1"),
        ("domain/v4_2", "contracts/v4_2"),
    }
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges)
    msg = str(exc.value)
    assert "top-level cycle" in msg
    assert "contracts" in msg and "domain" in msg


def test_authority_in_module_slice_cycle_raises() -> None:
    # Equal-rank authority pair forming a genuine module-slice cycle -> caught
    # by obligation 3's authority/adapter guard at module granularity.
    edges = {
        ("contracts/v4_1", "domain/v4_1"),
        ("domain/v4_1", "contracts/v4_1"),
    }
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges)
    assert "module-slice cycle" in str(exc.value)


# --------------------------------------------------------------------------- #
# (iii) adapter (providers) in a cycle.
# --------------------------------------------------------------------------- #
def test_adapter_providers_in_top_level_cycle_raises() -> None:
    # providers and cli are both L4 adapters -> equal rank, no inversion; this
    # isolates the dedicated adapter-in-cycle guard. providers is a member.
    edges = {
        ("providers/v4_1", "cli/v4_1"),
        ("cli/v4_2", "providers/v4_2"),
    }
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges)
    msg = str(exc.value)
    assert "top-level cycle" in msg
    assert "providers" in msg


# --------------------------------------------------------------------------- #
# (iv) injected MODULE-LEVEL cycle within an exempt component pair. A real
#      runtime circular import between two slices of the exempt (security,
#      operators) pair must fail even though the top-level pair is exempt.
# --------------------------------------------------------------------------- #
def test_module_level_cycle_within_exempt_pair_raises() -> None:
    edges = {
        ("security/v4_s06", "operators/v4_j05"),
        ("operators/v4_j05", "security/v4_s06"),
    }
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges)
    assert "module-slice import cycle" in str(exc.value)


# --------------------------------------------------------------------------- #
# (v) a top-level 2-cycle between two L3 services that is NOT on the allowlist.
# --------------------------------------------------------------------------- #
def test_unlisted_top_level_two_cycle_raises() -> None:
    # reasoning and memory are L3 services but not a pinned exemption pair.
    # Distinct carrier slices keep the module-slice graph acyclic so the case
    # reaches the fingerprint allowlist check.
    edges = {
        ("reasoning/v4_1", "memory/v4_1"),
        ("memory/v4_2", "reasoning/v4_2"),
    }
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges)
    assert "not in the ADR-034 allowlist" in str(exc.value)


# --------------------------------------------------------------------------- #
# (vi) a layer inversion (a single outward-pointing edge, no cycle needed).
# --------------------------------------------------------------------------- #
def test_layer_inversion_raises() -> None:
    # foundry_kernel (L2) importing a reasoning (L3) service is outward.
    edges = {("foundry_kernel/v4_1", "reasoning/v4_1")}
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges)
    assert "layer-inverting" in str(exc.value)


# --------------------------------------------------------------------------- #
# Extra adversarial fingerprint probes: the exemption is load-bearing and tight.
# --------------------------------------------------------------------------- #
def test_added_carrier_edge_breaks_fingerprint_raises() -> None:
    # Start from the real E1 edges and add a second operators->security carrier
    # slice that does NOT form a module cycle. The top-level pair is still
    # exempt, but the carrier set no longer equals the pinned fingerprint.
    edges = _real_exemption_edges() | {("operators/v4_j06", "security/v4_s06")}
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges)
    assert "carrier fingerprint mismatch" in str(exc.value)


def test_private_submodule_reachin_on_carrier_raises() -> None:
    # Mark one real carrier edge as a private-submodule reach-in. Carriers must
    # import the v4_* public API only; a reach-in must fail obligation 4d.
    edges = _real_exemption_edges()
    reachin = frozenset({("security/v4_s06", "operators/v4_j05")})
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges, private_reachin_edges=reachin)
    assert "private-submodule reach-in" in str(exc.value)


def test_grown_exempt_scc_to_three_raises() -> None:
    # Grow the (evidence, retrieval) exemption into a 3-SCC by adding a third
    # L3 participant that closes a top-level cycle with the pair. Must fail:
    # exemptions are pinned to exactly-size-2.
    edges = _real_exemption_edges() | {
        ("evidence/v4_k05", "reasoning/v4_1"),
        ("reasoning/v4_2", "retrieval/v4_o05"),
    }
    with pytest.raises(BoundaryError):
        evaluate_boundary(edges)


# --------------------------------------------------------------------------- #
# LIVE-TREE mutation regression guards.
#
# These run the *real* module-slice graph built from src/epistemic_foundry
# through the predicate under mutated exemption sets, permanently asserting that
# the ADR-034 waiver is a load-bearing tightening rather than a hole: strip the
# allowlist and the two real cycles MUST fail closed; tamper a fingerprint or a
# carrier's public-API depth and the exemption MUST be rejected. This makes the
# "it is a tightening" claim machine-checkable on every run, so future source
# drift cannot silently convert the waiver into a blanket pass.
# --------------------------------------------------------------------------- #
_EXEMPT_PAIRS = [["evidence", "retrieval"], ["operators", "security"]]


def _live_module_graph() -> tuple[set[tuple[str, str]], frozenset[tuple[str, str]]]:
    components = bc.discover_components()
    edges, reachin = bc.build_module_graph(components)
    return edges, frozenset(reachin)


def _live_top_level_sccs(edges: set[tuple[str, str]]) -> list[list[str]]:
    top: set[tuple[str, str]] = set()
    for a, b in edges:
        ca, cb = bc.component_of(a), bc.component_of(b)
        if ca != cb:
            top.add((ca, cb))
    nodes = {c for e in top for c in e}
    return [
        sorted(s)
        for s in bc.strongly_connected_components(nodes, top)
        if len(s) >= 2
    ]


def test_live_top_level_cycles_are_exactly_the_two_exemptions() -> None:
    edges, _ = _live_module_graph()
    assert sorted(_live_top_level_sccs(edges)) == _EXEMPT_PAIRS


def test_live_module_slice_graph_is_strict_dag() -> None:
    edges, _ = _live_module_graph()
    nodes = {s for e in edges for s in e}
    sccs = [s for s in bc.strongly_connected_components(nodes, edges) if len(s) >= 2]
    assert sccs == [], f"live module-slice cycle(s) present: {sccs}"


def test_live_passes_only_with_the_real_exemptions() -> None:
    edges, reachin = _live_module_graph()
    ev = evaluate_boundary(edges, private_reachin_edges=reachin)
    assert sorted(p["components"] for p in ev["top_level_cycles_permitted"]) == _EXEMPT_PAIRS


def test_live_without_any_exemption_both_cycles_are_forbidden() -> None:
    # The decisive tightening proof: remove the ADR-034 allowlist entirely and
    # the live tree must fail closed on the real top-level 2-cycles.
    edges, reachin = _live_module_graph()
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges, private_reachin_edges=reachin, exemptions=())
    assert "not in the ADR-034 allowlist" in str(exc.value)


@pytest.mark.parametrize("keep,forbidden", [("E1", "E2"), ("E2", "E1")])
def test_live_each_exemption_is_individually_necessary(keep: str, forbidden: str) -> None:
    edges, reachin = _live_module_graph()
    only = tuple(x for x in EXEMPT_TOP_LEVEL_CYCLES if x.name == keep)
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges, private_reachin_edges=reachin, exemptions=only)
    assert "not in the ADR-034 allowlist" in str(exc.value)


def test_live_truncated_fingerprint_is_rejected() -> None:
    # Drop one pinned carrier edge from E1's fingerprint: the live carrier set no
    # longer matches, so the exemption must fail closed on a fingerprint mismatch.
    edges, reachin = _live_module_graph()
    mutated = []
    for x in EXEMPT_TOP_LEVEL_CYCLES:
        if x.name == "E1":
            trimmed = frozenset(sorted(x.carrier_edges)[:1])
            mutated.append(bc.Exemption(x.name, x.pair, trimmed, x.justification))
        else:
            mutated.append(x)
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges, private_reachin_edges=reachin, exemptions=tuple(mutated))
    assert "carrier fingerprint mismatch" in str(exc.value)


def test_live_private_reachin_on_a_real_carrier_is_rejected() -> None:
    # If any live carrier were a private-submodule reach-in, the exemption must
    # be refused. Inject that condition on a real carrier and require rejection.
    edges, _ = _live_module_graph()
    real_carrier = next(
        (s, d)
        for (s, d) in edges
        if {bc.component_of(s), bc.component_of(d)} == {"operators", "security"}
    )
    with pytest.raises(BoundaryError) as exc:
        evaluate_boundary(edges, private_reachin_edges=frozenset({real_carrier}))
    assert "private-submodule reach-in" in str(exc.value)
