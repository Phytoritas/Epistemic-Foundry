from __future__ import annotations

import importlib.util
import json
import sys
import unicodedata
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "j02"
INVENTORY_PATH = ROOT / "plugins" / "epistemic-foundry" / "skills" / "skill-inventory.json"
COUNTER_PATH = ROOT / "tools" / "skill-context" / "count_tokens.py"


def _load_counter() -> ModuleType:
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("j02_count_tokens", COUNTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the canonical J02 token counter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COUNTER = _load_counter()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_inventory_identity_metadata_and_dispositions_are_exact() -> None:
    inventory = _json(INVENTORY_PATH)
    expected = _json(FIXTURES / "skill-inventory.expected.json")

    assert inventory["inventory_id"] == expected["inventory_id"]
    assert inventory["inventory_version"] == expected["inventory_version"]
    assert inventory["inventory_hash"] == expected["inventory_hash"]
    assert inventory["parent_skill_id"] == expected["parent_skill_id"]
    assert inventory["metadata_projection"] == expected["metadata_projection"]
    assert len(inventory["skills"]) == expected["skill_count"] == 29
    assert len(inventory["references"]) == expected["reference_count"] == 17

    observed_dispositions = {
        skill["skill_id"]: skill["invocation_disposition"]
        for skill in inventory["skills"]
    }
    assert observed_dispositions == expected["skill_dispositions"]
    assert sorted(reference["reference_id"] for reference in inventory["references"]) == sorted(
        expected["reference_ids"]
    )

    parent = [skill for skill in inventory["skills"] if skill["skill_id"] == "foundry"]
    assert len(parent) == 1
    assert len(parent[0]["child_skills"]) == 28
    assert set(parent[0]["child_skills"]) == {
        skill["skill_id"] for skill in inventory["skills"] if skill["skill_id"] != "foundry"
    }

    names = [skill["name"] for skill in inventory["skills"]]
    paths = [skill["path"] for skill in inventory["skills"]]
    assert len(set(names)) == 29
    assert len(set(paths)) == 29
    for skill in inventory["skills"]:
        assert skill["status"] == "ACTIVE"
        assert skill["name"].isascii()
        assert skill["path"].isascii()
        assert "\\" not in skill["path"]
        assert not Path(skill["path"]).is_absolute()
        assert "\t" not in skill["description"]
        assert "\n" not in skill["description"]
        assert "\r" not in skill["description"]
        assert len(skill["description"].encode("utf-8")) <= 140
        assert skill["description"] == COUNTER.normalize_description(skill["description"])

    metadata = COUNTER.serialize_metadata(inventory["skills"])
    encoding = COUNTER.require_tokenizer()
    token_count, _ = COUNTER.count_text(metadata, encoding)
    actual_projection = {
        "sha256": COUNTER.sha256_bytes(metadata.encode("utf-8")),
        "byte_count": len(metadata.encode("utf-8")),
        "token_count": token_count,
    }
    assert actual_projection == inventory["metadata_projection"]
    COUNTER.assert_metadata_budget(
        actual_projection["byte_count"], actual_projection["token_count"], len(inventory["skills"])
    )


def test_all_skill_and_reference_file_seals_use_exact_tokenizer_counts() -> None:
    inventory = _json(INVENTORY_PATH)
    encoding = COUNTER.require_tokenizer()

    for skill in inventory["skills"]:
        path = ROOT / "plugins" / "epistemic-foundry" / skill["path"]
        data, text = COUNTER.read_canonical_text(path)
        token_count, token_ids = COUNTER.count_text(text, encoding)
        assert token_ids
        assert COUNTER.sha256_bytes(data) == skill["sha256"]
        assert len(data) == skill["byte_count"] <= 4096
        assert token_count == skill["token_count"] <= 1024

    for reference in inventory["references"]:
        path = ROOT / "plugins" / "epistemic-foundry" / reference["path"]
        data, text = COUNTER.read_canonical_text(path)
        token_count, token_ids = COUNTER.count_text(text, encoding)
        assert token_ids
        assert COUNTER.sha256_bytes(data) == reference["sha256"]
        assert len(data) == reference["byte_count"] <= 4096
        assert token_count == reference["token_count"] <= 1024


def test_all_29_default_progressive_activations_fit_every_budget() -> None:
    inventory = _json(INVENTORY_PATH)
    fixture = _json(FIXTURES / "reference-selection-cases.json")
    defaults = [case for case in fixture["cases"] if case["category"] == "DEFAULT"]
    skills = {skill["skill_id"]: skill for skill in inventory["skills"]}
    references = {
        reference["reference_id"]: reference for reference in inventory["references"]
    }

    def closure_for(reference_ids: list[str]) -> set[str]:
        closure: set[str] = set()

        def visit(reference_id: str) -> None:
            if reference_id in closure:
                return
            closure.add(reference_id)
            for dependency_id in references[reference_id]["depends_on"]:
                visit(dependency_id)

        for reference_id in reference_ids:
            visit(reference_id)
        return closure

    assert len(defaults) == len(skills) == 29
    assert {case["skill_id"] for case in defaults} == set(skills)
    for case in defaults:
        skill = skills[case["skill_id"]]
        closure = closure_for(skill["direct_references"])
        assert sum(references[reference_id]["byte_count"] for reference_id in closure) == case[
            "total_reference_bytes"
        ]
        assert sum(references[reference_id]["token_count"] for reference_id in closure) == case[
            "total_reference_tokens"
        ]
        candidate = {
            "skill_bytes": skill["byte_count"],
            "skill_tokens": skill["token_count"],
            "reference_count": len(closure),
            "reference_depth": case["transitive_depth"],
            "reference_bytes": case["total_reference_bytes"],
            "reference_tokens": case["total_reference_tokens"],
        }
        COUNTER.assert_activation_budget(candidate)
        assert skill["byte_count"] + case["total_reference_bytes"] <= 28672
        assert skill["token_count"] + case["total_reference_tokens"] <= 7168


def test_pinned_tokenizer_vectors_are_exact_and_repeatable(tmp_path: Path) -> None:
    fixture = _json(FIXTURES / "tokenizer-vectors.json")
    assert fixture["tokenizer"] == {
        "package": "tiktoken",
        "version": "0.13.0",
        "encoding": "o200k_base",
        "disallowed_special": [],
    }
    encoding = COUNTER.require_tokenizer()
    assert len(fixture["vectors"]) == 7

    for vector in fixture["vectors"]:
        text = vector["text"]
        if vector.get("normalize_nfc"):
            text = unicodedata.normalize("NFC", text)
        assert text == vector["encoded_text"]
        first_count, first_ids = COUNTER.count_text(text, encoding)
        second_count, second_ids = COUNTER.count_text(text, encoding)
        assert first_ids == second_ids == vector["token_ids"]
        assert first_count == second_count == len(vector["token_ids"])

    crlf = next(vector for vector in fixture["vectors"] if vector["id"] == "crlf")
    crlf_path = tmp_path / "crlf.md"
    crlf_path.write_bytes(crlf["text"].encode("utf-8"))
    with pytest.raises(COUNTER.TokenizerContractError) as caught:
        COUNTER.read_canonical_text(crlf_path)
    assert caught.value.code == crlf["canonical_file_error"]

    tabbed = next(vector for vector in fixture["vectors"] if vector["id"] == "tab_newline")
    with pytest.raises(COUNTER.TokenizerContractError) as caught:
        COUNTER.normalize_description(tabbed["text"])
    assert caught.value.code == tabbed["metadata_error"]


@pytest.mark.parametrize(
    "case",
    _json(FIXTURES / "context-budget-cases.json")["cases"],
    ids=lambda case: case["case_id"],
)
def test_all_12_budget_boundaries_are_exact(case: dict[str, Any]) -> None:
    expected = case["expected"]

    def apply_case() -> None:
        if case["operation"] == "metadata":
            COUNTER.assert_metadata_budget(**case["input"])
        elif case["operation"] == "description":
            COUNTER.assert_description_budget("x" * case["input"]["byte_count"])
        elif case["operation"] == "activation":
            COUNTER.assert_activation_budget(case["input"])
        else:  # pragma: no cover - fixture contract guard
            raise AssertionError(f"unknown boundary operation: {case['operation']}")

    if expected == "PASS":
        apply_case()
    else:
        with pytest.raises(COUNTER.TokenizerContractError) as caught:
            apply_case()
        assert caught.value.code == expected


def test_repository_dependency_lock_closes_exact_tiktoken_pin() -> None:
    """Non-waivable J02 gate: the repository, not the host Python, owns the pin."""

    try:
        result = COUNTER.verify_repository_tokenizer_lock(ROOT)
    except COUNTER.TokenizerContractError as exc:
        pytest.fail(f"{exc.code}: {exc}", pytrace=False)
    assert result["status"] == "PASS"
    assert result["dependency_group"] == "skill-context"
    assert result["pyproject_requirement"] == "tiktoken==0.13.0"
    assert result["runtime_dependency_exposure"] is False


def _write_dependency_lock_fixture(
    tmp_path: Path,
    *,
    pyproject_transform=lambda value: value,
    lock_transform=lambda value: value,
) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    (root / "pyproject.toml").write_text(
        pyproject_transform(pyproject), encoding="utf-8", newline="\n"
    )
    (root / "uv.lock").write_text(
        lock_transform(lock), encoding="utf-8", newline="\n"
    )
    return root


def _replace_exact(value: str, old: str, new: str) -> str:
    assert value.count(old) == 1
    return value.replace(old, new)


def test_repository_dependency_lock_rejects_nonexclusive_dependency_group(
    tmp_path: Path,
) -> None:
    root = _write_dependency_lock_fixture(
        tmp_path,
        pyproject_transform=lambda value: _replace_exact(
            value,
            'skill-context = [\n    "tiktoken==0.13.0",\n]',
            'skill-context = [\n    "tiktoken==0.13.0",\n    "pytest==8.4.1",\n]',
        ),
    )
    with pytest.raises(COUNTER.TokenizerContractError) as caught:
        COUNTER.verify_repository_tokenizer_lock(root)
    assert caught.value.code == "TOKENIZER_CONTRACT_UNAVAILABLE"


def test_repository_dependency_lock_rejects_runtime_exposure(tmp_path: Path) -> None:
    root = _write_dependency_lock_fixture(
        tmp_path,
        pyproject_transform=lambda value: _replace_exact(
            value,
            '    "PyYAML>=6.0,<7",\n]',
            '    "PyYAML>=6.0,<7",\n    "tiktoken==0.13.0",\n]',
        ),
    )
    with pytest.raises(COUNTER.TokenizerContractError) as caught:
        COUNTER.verify_repository_tokenizer_lock(root)
    assert caught.value.code == "TOKENIZER_CONTRACT_UNAVAILABLE"


def test_repository_dependency_lock_rejects_expanded_uv_group(tmp_path: Path) -> None:
    root = _write_dependency_lock_fixture(
        tmp_path,
        lock_transform=lambda value: _replace_exact(
            value,
            'skill-context = [\n    { name = "tiktoken" },\n]',
            'skill-context = [\n    { name = "pytest" },\n    { name = "tiktoken" },\n]',
        ),
    )
    with pytest.raises(COUNTER.TokenizerContractError) as caught:
        COUNTER.verify_repository_tokenizer_lock(root)
    assert caught.value.code == "TOKENIZER_CONTRACT_UNAVAILABLE"
