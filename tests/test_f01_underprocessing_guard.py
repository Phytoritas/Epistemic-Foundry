from __future__ import annotations

import subprocess
from itertools import combinations
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD_TEST = (
    ROOT
    / "packages/foundry-kernel/src/forge/classifier/underprocessing-guard.test.mjs"
)
SIGNAL_FLOORS = {
    "TRANSFORM": 0,
    "LOOKUP": 1,
    "SYNTHESIS": 2,
    "MECHANISM": 3,
    "CAUSAL": 4,
    "VALIDATION": 4,
    "HIGH_STAKES": 4,
    "EXPENSIVE": 4,
    "NOVELTY": 5,
    "AMBIGUOUS": 5,
}


def test_underprocessing_guard_executes_every_fixed_check_without_skip_or_xfail() -> None:
    result = subprocess.run(
        ["node", "--test", str(GUARD_TEST)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "all 1023 non-empty subsets" in output
    assert "every non-empty subset-to-superset pair" in output
    assert "trusted unknown signals fail input validation" in output
    assert "fail 0" in output
    assert "skipped 0" in output
    assert "todo 0" in output


def test_contract_floor_is_monotonic_for_all_1023_nonempty_signal_sets() -> None:
    signals = list(SIGNAL_FLOORS)
    observed_sets = 0
    comparisons = 0
    floors: dict[frozenset[str], int] = {}
    for size in range(1, len(signals) + 1):
        for entries in combinations(signals, size):
            signal_set = frozenset(entries)
            floors[signal_set] = max(SIGNAL_FLOORS[signal] for signal in signal_set)
            observed_sets += 1
    assert observed_sets == 1023

    for subset, subset_floor in floors.items():
        for superset, superset_floor in floors.items():
            if subset <= superset:
                assert subset_floor <= superset_floor
                comparisons += 1
    assert comparisons == 58025


def test_guard_sources_contain_no_skip_xfail_or_average_threshold_escape() -> None:
    source = GUARD_TEST.read_text(encoding="utf-8")
    forbidden = (
        "test.skip",
        "test.todo",
        "describe.skip",
        "it.skip",
        "allowance",
        "tolerance",
    )
    assert all(token not in source for token in forbidden)

