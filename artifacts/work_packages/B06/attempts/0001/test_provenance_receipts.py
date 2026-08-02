"""provenance_and_receipt_audit — every verdict this gate publishes proves itself.

The pin ledger, the reproducibility record and the gate manifest each re-derive
their own hash from exactly the fields they publish, and each entry in the
ledger names the sealed file it was read from together with that file's digest,
so a reader can re-read the source rather than trust the summary.  The gate
holds no clock and no random source: timestamps arrive from the caller, and the
only process it starts is the build itself.  Nothing it is handed is modified.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import b06_gate
from b06_gate import (
    BUILD_OUTPUT_PLACEHOLDER,
    DECLARED_NORMALIZATIONS,
    GENERATOR_RELPATH,
    LEDGER_NAME,
    MANIFEST_NAME,
    OUTPUT_DIR,
    REPRODUCIBILITY_NAME,
    build_command,
    build_gate_manifest,
    build_reproducibility_record,
    compare_build_trees,
    emit_pin_ledger,
    epoch_timestamp,
    hash_excluding,
    render,
    tree_sha256,
    validate_pin_ledger,
)
from fixtures import EPOCH, ROOT, TIMESTAMP, WHEEL_NAME, identical_outputs, ledger

GATE = Path(b06_gate.__file__)

#: Names that would put a clock or a random source inside the gate.
FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "getrandbits",
        "monotonic",
        "now",
        "perf_counter",
        "random",
        "randint",
        "shuffle",
        "time",
        "today",
        "urandom",
        "utcnow",
        "uuid1",
        "uuid4",
    }
)
FORBIDDEN_MODULES = frozenset({"random", "secrets", "time", "uuid"})


def gate_tree() -> ast.Module:
    return ast.parse(GATE.read_text(encoding="utf-8"))


def reproducibility() -> dict:
    return build_reproducibility_record(
        artifacts={WHEEL_NAME: {"bytes": 10, "sha256": "sha256:" + "a" * 64}},
        source_snapshot_sha256="sha256:" + "b" * 64,
        source_date_epoch=EPOCH,
        command=build_command(
            "toolchains/python-build-constraints.txt", BUILD_OUTPUT_PLACEHOLDER
        ),
        generated_at=TIMESTAMP,
    )


def manifest(**overrides: object) -> dict:
    arguments: dict = {
        "outputs": {f"{OUTPUT_DIR}/{LEDGER_NAME}": "sha256:" + "c" * 64},
        "ledger": ledger(),
        "reproducibility": reproducibility(),
        "generated_at": TIMESTAMP,
        "generator_sha256": "sha256:" + "d" * 64,
    }
    arguments.update(overrides)
    return build_gate_manifest(**arguments)  # type: ignore[arg-type]


def test_each_record_re_derives_its_own_hash() -> None:
    documents = (ledger(), reproducibility(), manifest())
    fields = ("ledger_hash", "record_hash", "manifest_hash")

    for document, field in zip(documents, fields, strict=True):
        assert hash_excluding(document, field) == document[field]


def test_a_record_edited_after_sealing_no_longer_matches_its_hash() -> None:
    document = reproducibility()
    document["bit_identical"] = False

    assert hash_excluding(document, "record_hash") != document["record_hash"]


def test_the_manifest_binds_the_generator_that_wrote_it() -> None:
    document = manifest()

    assert document["generator"]["path"] == GENERATOR_RELPATH
    assert (ROOT / GENERATOR_RELPATH).resolve() == GATE.resolve()
    assert document["generator"]["sha256"].startswith("sha256:")


def test_the_manifest_defaults_to_the_running_generator_digest() -> None:
    import hashlib

    document = manifest(generator_sha256=None)
    expected = "sha256:" + hashlib.sha256(GATE.read_bytes()).hexdigest()

    assert document["generator"]["sha256"] == expected


def test_every_pin_traces_to_a_sealed_file_with_the_recorded_digest() -> None:
    import hashlib

    for entry in ledger()["entries"]:
        path = ROOT / entry["source_path"]
        assert path.is_file(), entry["source_path"]
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["source_sha256"] == digest, entry["pin_id"]


def test_every_executable_pin_carries_a_digest_and_every_blocked_one_a_reason() -> None:
    for entry in ledger()["entries"]:
        if entry["execution_permitted"]:
            assert entry["digest"] is not None, entry["pin_id"]
            assert entry["unpinned_fields"] == []
        else:
            assert entry["blocking_reason"], entry["pin_id"]
            assert entry["unpinned_fields"], entry["pin_id"]


def test_the_reproducibility_record_publishes_the_normalization_it_applied() -> None:
    document = reproducibility()

    assert document["normalizations"] == dict(DECLARED_NORMALIZATIONS)
    assert document["source_date_epoch"] == EPOCH
    assert document["build_command"][:2] == ["uv", "build"]
    assert document["generator"] == GENERATOR_RELPATH


def test_the_gate_reads_no_clock_and_no_random_source() -> None:
    tree = gate_tree()
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert not FORBIDDEN_ATTRIBUTES & attributes, sorted(
        FORBIDDEN_ATTRIBUTES & attributes
    )
    assert not FORBIDDEN_ATTRIBUTES & names, sorted(FORBIDDEN_ATTRIBUTES & names)
    assert not FORBIDDEN_MODULES & imported, sorted(FORBIDDEN_MODULES & imported)


def test_the_only_process_the_gate_starts_is_the_build() -> None:
    starters = [
        node
        for node in ast.walk(gate_tree())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]
    enclosing = {
        node.name
        for node in ast.walk(gate_tree())
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "run"
            and isinstance(inner.func.value, ast.Name)
            and inner.func.value.id == "subprocess"
            for inner in ast.walk(node)
        )
    }

    assert len(starters) == 1
    assert enclosing == {"run_build"}


def test_a_timestamp_is_derived_from_the_declared_epoch_not_from_a_clock() -> None:
    assert epoch_timestamp(EPOCH) == TIMESTAMP
    assert epoch_timestamp(EPOCH) == epoch_timestamp(EPOCH)


def test_nothing_the_gate_is_handed_is_modified(tmp_path: Path) -> None:
    first, second = identical_outputs(tmp_path)
    trees = (tree_sha256(first), tree_sha256(second))
    document = ledger()
    sealed = json.dumps(document, ensure_ascii=False, sort_keys=True)
    outputs = {f"{OUTPUT_DIR}/{LEDGER_NAME}": "sha256:" + "c" * 64}
    snapshot = dict(outputs)

    compare_build_trees(first, second)
    validate_pin_ledger(document)
    build_gate_manifest(
        outputs=outputs,
        ledger=document,
        reproducibility=reproducibility(),
        generated_at=TIMESTAMP,
    )

    assert (tree_sha256(first), tree_sha256(second)) == trees
    assert json.dumps(document, ensure_ascii=False, sort_keys=True) == sealed
    assert outputs == snapshot


def test_the_emitted_ledger_re_validates_from_its_own_bytes(tmp_path: Path) -> None:
    result = emit_pin_ledger(ROOT, generated_at=TIMESTAMP, out_dir=tmp_path)
    reloaded = json.loads((tmp_path / LEDGER_NAME).read_text(encoding="utf-8"))

    assert validate_pin_ledger(reloaded)["status"] == "PASS"
    assert reloaded["ledger_hash"] == result["ledger_hash"]
    assert render(reloaded) == (tmp_path / LEDGER_NAME).read_bytes()


def test_no_receipt_carries_a_machine_local_path() -> None:
    documents = (ledger(), reproducibility(), manifest())

    assert BUILD_OUTPUT_PLACEHOLDER in reproducibility()["build_command"]
    for document in documents:
        rendered = render(document).decode("utf-8")
        assert not re.search(r"[A-Za-z]:\\\\|/home/|/Users/", rendered), rendered[:200]


def test_the_gate_names_the_three_receipts_it_writes() -> None:
    names = {LEDGER_NAME, REPRODUCIBILITY_NAME, MANIFEST_NAME}

    assert len(names) == 3
    assert all(name.endswith(".json") for name in names)
    assert OUTPUT_DIR == "build/v4_b06"
