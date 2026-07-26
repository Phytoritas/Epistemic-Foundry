#!/usr/bin/env python3
"""Validate the Epistemic Foundry v4 specification and reference-plugin bundle.

This validator proves structural consistency of the specification bundle. It
must not be read as evidence that the reference blueprint is already an
implemented or production-ready plugin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from referencing import Registry, Resource

VERSION = "4.0.0"
EXPECTED = {
    "schemas": 124,
    "examples": 124,
    "workflows": 22,
    "workflow_nodes": 327,
    "prompts": 65,
    "work_packages": 156,
    "invariants": 64,
    "audit_families": 24,
    "audit_lenses": 288,
    "plugin_skills": 29,
    "plugin_hooks": 7,
    "roles": 28,
}
REQUIRED_FILES = {
    "VERSION", "README.md", "MASTER_SPEC.md", "MASTER_EXECUTION_PROMPT.md",
    "AGENTS.md", "CLAUDE.md", "docs/product_constitution.md",
    "docs/v4_evolution_architecture.md", "docs/verifier_firewall.md",
    "docs/anti_goodhart_and_open_endedness.md",
    "docs/quality_diversity_archive.md",
    "docs/statistical_search_governance.md",
    "docs/evolution_security_threat_model.md",
    "docs/shinka_backend_adapter_contract.md",
    "docs/evolution_plugin_skills_and_cli.md",
    "docs/evolution_evaluation_benchmark.md",
    "docs/evolution_state_machine.md", "docs/evolution_ui_ux_contract.md",
    "docs/migration_v3_to_v4.md",
    "research/shinkaevolve_gap_analysis.md",
    "research/shinkaevolve_source_manifest.json",
    "manifests/development_manifest.yaml", "manifests/acceptance_matrix.yaml",
    "manifests/product_invariants.yaml", "manifests/requirements_traceability.yaml",
    "manifests/288_lens_evolution_audit_matrix.yaml",
    "manifests/role_registry.yaml",
    "tools/run_288_lens_evolution_audit.py", "tools/validate_spec_bundle.py",
    "plugin_blueprint/epistemic-foundry/.codex-plugin/plugin.json",
    "plugin_blueprint/epistemic-foundry/.mcp.json",
    "plugin_blueprint/epistemic-foundry/README_SPEC_ONLY.md",
}
ALIASES = {
    "claim-card": "sample_claim.json",
    "context-assembly-manifest": "sample_context_manifest.json",
    "evidence-node": "sample_evidence.json",
    "hypothesis-passport": "sample_passport.json",
    "insight-card": "sample_insight.json",
    "validation-target-manifest": "sample_validation_target.json",
}
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".mjs", ".toml", ".txt"}
SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9]{32,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
PLACEHOLDER_PATTERNS = [
    re.compile(r"\bTODO\b"), re.compile(r"\bFIXME\b"), re.compile(r"\[\[MISSING:"),
    re.compile(r"<INSERT_[A-Z_]+>"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path, errors: list[str]) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
        return None


def load_yaml(path: Path, errors: list[str]) -> Any | None:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{path}: invalid YAML: {exc}")
        return None


def topo_layers(ids: set[str], deps: dict[str, set[str]]) -> tuple[list[list[str]], list[str]]:
    indegree = {x: len(deps.get(x, set())) for x in ids}
    children: dict[str, set[str]] = defaultdict(set)
    for child, parents in deps.items():
        for parent in parents:
            children[parent].add(child)
    ready = sorted(x for x, d in indegree.items() if d == 0)
    layers: list[list[str]] = []
    seen: list[str] = []
    while ready:
        layer = ready
        layers.append(layer)
        nxt: list[str] = []
        for x in layer:
            seen.append(x)
            for child in sorted(children.get(x, set())):
                indegree[child] -= 1
                if indegree[child] == 0:
                    nxt.append(child)
        ready = sorted(set(nxt))
    return layers, sorted(ids - set(seen))


def scope_overlap(a: str, b: str) -> bool:
    if a == b:
        return True
    aa = a[:-3] if a.endswith("/**") else a
    bb = b[:-3] if b.endswith("/**") else b
    return (a.endswith("/**") and (b == aa or b.startswith(aa + "/"))) or \
           (b.endswith("/**") and (a == bb or a.startswith(bb + "/")))


def validate_schemas(root: Path, errors: list[str], report: dict[str, Any]) -> dict[str, Any]:
    schema_paths = sorted((root / "schemas").glob("*.schema.json"))
    example_paths = sorted((root / "examples").glob("*.json"))
    if len(schema_paths) != EXPECTED["schemas"]:
        errors.append(f"schema count {len(schema_paths)} != {EXPECTED['schemas']}")
    if len(example_paths) != EXPECTED["examples"]:
        errors.append(f"example count {len(example_paths)} != {EXPECTED['examples']}")

    schemas: dict[str, Any] = {}
    registry = Registry()
    ids: set[str] = set()
    for path in schema_paths:
        doc = load_json(path, errors)
        if not isinstance(doc, dict):
            continue
        try:
            jsonschema.Draft202012Validator.check_schema(doc)
        except Exception as exc:
            errors.append(f"{path}: Draft 2020-12 meta-validation failed: {exc}")
            continue
        sid = doc.get("$id")
        if not isinstance(sid, str) or not sid:
            errors.append(f"{path}: missing $id")
        elif sid in ids:
            errors.append(f"{path}: duplicate $id {sid}")
        else:
            ids.add(sid)
            registry = registry.with_resource(sid, Resource.from_contents(doc))
        if doc.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            errors.append(f"{path}: must use Draft 2020-12")
        if doc.get("type") != "object" or doc.get("additionalProperties") is not False:
            errors.append(f"{path}: top-level must be strict object")
        schemas[path.name] = doc

    used: set[str] = set()
    valid = 0
    for path in schema_paths:
        stem = path.name.removesuffix(".schema.json")
        candidates = [ALIASES.get(stem), f"sample_{stem}.json", f"sample_{stem.replace('-', '_')}.json"]
        example = next((root / "examples" / c for c in candidates if c and (root / "examples" / c).exists()), None)
        if example is None:
            errors.append(f"{path}: no canonical example")
            continue
        used.add(example.name)
        instance = load_json(example, errors)
        schema = schemas.get(path.name)
        if instance is None or schema is None:
            continue
        try:
            problems = sorted(jsonschema.Draft202012Validator(schema, registry=registry).iter_errors(instance), key=lambda e: list(e.path))
        except Exception as exc:
            errors.append(f"{example}: validator construction failed: {exc}")
            continue
        if problems:
            for err in problems[:20]:
                loc = "/".join(map(str, err.path)) or "<root>"
                errors.append(f"{example} vs {path.name} at {loc}: {err.message}")
        else:
            valid += 1
    extra = sorted(p.name for p in example_paths if p.name not in used)
    if extra:
        errors.append(f"unmapped examples: {extra}")
    report["schemas"] = {"count": len(schema_paths), "examples": len(example_paths), "valid_examples": valid, "unique_ids": len(ids)}
    return schemas


def validate_workflows(root: Path, schemas: dict[str, Any], errors: list[str], report: dict[str, Any]) -> None:
    paths = sorted((root / "workflows").glob("*.workflow.yaml"))
    if len(paths) != EXPECTED["workflows"]:
        errors.append(f"workflow count {len(paths)} != {EXPECTED['workflows']}")
    node_schema = schemas.get("node-contract.schema.json")
    node_validator = jsonschema.Draft202012Validator(node_schema) if node_schema else None
    workflow_ids: set[str] = set()
    subdeps: dict[str, set[str]] = defaultdict(set)
    details: dict[str, Any] = {}
    total_nodes = 0

    for path in paths:
        doc = load_yaml(path, errors)
        if not isinstance(doc, dict):
            continue
        wid = doc.get("workflow_id")
        if not isinstance(wid, str) or not wid:
            errors.append(f"{path}: missing workflow_id")
            continue
        if wid in workflow_ids:
            errors.append(f"{path}: duplicate workflow_id {wid}")
        workflow_ids.add(wid)
        if str(doc.get("version")) != VERSION:
            errors.append(f"{path}: version {doc.get('version')} != {VERSION}")
        nodes = doc.get("nodes", [])
        if not isinstance(nodes, list) or not nodes:
            errors.append(f"{path}: nodes must be non-empty list")
            continue
        total_nodes += len(nodes)
        by_id: dict[str, dict[str, Any]] = {}
        for idx, node in enumerate(nodes):
            if not isinstance(node, dict):
                errors.append(f"{path}: node {idx} not object")
                continue
            nid = node.get("node_id")
            if not isinstance(nid, str) or not nid:
                errors.append(f"{path}: node {idx} missing node_id")
                continue
            if nid in by_id:
                errors.append(f"{path}: duplicate node {nid}")
            by_id[nid] = node
            if node_validator:
                for err in sorted(node_validator.iter_errors(node), key=lambda e: list(e.path)):
                    loc = "/".join(map(str, err.path)) or "<root>"
                    errors.append(f"{path}:{nid} NodeContract {loc}: {err.message}")
            for field in ("input_schema_ref", "output_schema_ref"):
                ref = node.get(field)
                if isinstance(ref, str) and not (root / ref).exists():
                    errors.append(f"{path}:{nid}: missing {field} {ref}")
            etype, eref = node.get("executor_type"), node.get("executor_ref")
            if not isinstance(eref, str) or not eref:
                errors.append(f"{path}:{nid}: missing executor_ref")
            elif etype == "llm":
                target = (root / eref).resolve()
                prompts_root = (root / "prompts").resolve()
                if not target.exists() or prompts_root not in target.parents:
                    errors.append(f"{path}:{nid}: LLM prompt missing/outside prompts: {eref}")
            elif etype == "subworkflow":
                target = root / eref
                if not target.exists():
                    errors.append(f"{path}:{nid}: subworkflow missing: {eref}")
                else:
                    child = load_yaml(target, errors)
                    if isinstance(child, dict) and isinstance(child.get("workflow_id"), str):
                        subdeps[wid].add(child["workflow_id"])
            elif ("/" in eref or eref.endswith((".py", ".mjs"))) and not (root / eref).exists():
                errors.append(f"{path}:{nid}: executable path missing: {eref}")
            elif "/" not in eref and not eref.startswith("epistemic_foundry."):
                errors.append(f"{path}:{nid}: invalid provider-neutral executor_ref {eref}")

        ids = set(by_id)
        deps: dict[str, set[str]] = {}
        for nid, node in by_id.items():
            ds = set(node.get("depends_on", []))
            missing = ds - ids
            if missing:
                errors.append(f"{path}:{nid}: missing dependencies {sorted(missing)}")
            if nid in ds:
                errors.append(f"{path}:{nid}: self dependency")
            deps[nid] = ds
        layers, cyclic = topo_layers(ids, deps)
        if cyclic:
            errors.append(f"{path}: cyclic nodes {cyclic}")
        for li, layer in enumerate(layers):
            for i, left_id in enumerate(layer):
                for right_id in layer[i+1:]:
                    left, right = by_id[left_id], by_id[right_id]
                    for a in left.get("write_scope", []):
                        for b in right.get("write_scope", []):
                            if scope_overlap(a, b):
                                errors.append(f"{path}: parallel layer {li} write conflict {left_id}:{a} vs {right_id}:{b}")
                    le = {x for x in left.get("resource_dependencies", []) if str(x).startswith("exclusive:")}
                    re_ = {x for x in right.get("resource_dependencies", []) if str(x).startswith("exclusive:")}
                    if le & re_:
                        errors.append(f"{path}: parallel exclusive resource conflict {left_id}/{right_id}: {sorted(le & re_)}")
        details[path.name] = {"workflow_id": wid, "nodes": len(nodes), "layers": len(layers), "max_width": max(map(len, layers), default=0)}

    _, cycle = topo_layers(set(workflow_ids), subdeps)
    if cycle:
        errors.append(f"subworkflow cycle: {cycle}")
    if total_nodes != EXPECTED["workflow_nodes"]:
        errors.append(f"workflow node count {total_nodes} != {EXPECTED['workflow_nodes']}")
    report["workflows"] = {"count": len(paths), "total_nodes": total_nodes, "details": details}


def validate_development(root: Path, errors: list[str], report: dict[str, Any]) -> set[str]:
    dev = load_yaml(root / "manifests/development_manifest.yaml", errors)
    items = dev.get("work_packages", []) if isinstance(dev, dict) else []
    if len(items) != EXPECTED["work_packages"]:
        errors.append(f"work-package count {len(items)} != {EXPECTED['work_packages']}")
    by_id: dict[str, dict[str, Any]] = {}
    required_fields = {"id", "phase", "phase_title", "title", "depends_on", "write_scope", "model_tier", "risk_class", "owner_role", "independent_review", "review_role", "exit_criteria", "required_checks", "stop_conditions", "evidence_artifacts", "rollback_or_recovery", "initial_status"}
    for item in items:
        wid = item.get("id")
        if not isinstance(wid, str) or not wid:
            errors.append("work package missing id")
            continue
        if wid in by_id:
            errors.append(f"duplicate work package {wid}")
        by_id[wid] = item
        missing = required_fields - set(item)
        if missing:
            errors.append(f"work package {wid}: missing fields {sorted(missing)}")
        if not item.get("exit_criteria") or not item.get("required_checks"):
            errors.append(f"work package {wid}: empty exit criteria/checks")
    expected_ids = {f"{chr(letter)}{n:02d}" for letter in range(ord('A'), ord('Z') + 1) for n in range(1, 7)}
    if set(by_id) != expected_ids:
        errors.append(f"A-Z work-package ID set mismatch: missing={sorted(expected_ids-set(by_id))}, extra={sorted(set(by_id)-expected_ids)}")
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for suffix in ("04", "06"):
            checkpoint_id = f"{letter}{suffix}"
            checkpoint = by_id.get(checkpoint_id, {})
            if checkpoint.get("review_role") != "integration_reviewer" or checkpoint.get("independent_review") != "required":
                errors.append(f"{checkpoint_id} must be independently reviewed integration checkpoint")

    ids = set(by_id)
    deps: dict[str, set[str]] = {}
    for wid, item in by_id.items():
        ds = set(item.get("depends_on", []))
        if ds - ids:
            errors.append(f"work package {wid}: missing dependencies {sorted(ds-ids)}")
        deps[wid] = ds
    layers, cyclic = topo_layers(ids, deps)
    if cyclic:
        errors.append(f"work-package cycle: {cyclic}")
    for li, layer in enumerate(layers):
        for i, left_id in enumerate(layer):
            for right_id in layer[i+1:]:
                for a in by_id[left_id].get("write_scope", []):
                    for b in by_id[right_id].get("write_scope", []):
                        if scope_overlap(a, b):
                            errors.append(f"work-package parallel layer {li} write conflict {left_id}:{a} vs {right_id}:{b}")

    inv = load_yaml(root / "manifests/product_invariants.yaml", errors)
    invariants = inv.get("invariants", []) if isinstance(inv, dict) else []
    trace = load_yaml(root / "manifests/requirements_traceability.yaml", errors)
    reqs = trace.get("requirements", []) if isinstance(trace, dict) else []
    if len(invariants) != EXPECTED["invariants"] or len(reqs) != EXPECTED["invariants"]:
        errors.append(f"invariant/trace counts {len(invariants)}/{len(reqs)} != {EXPECTED['invariants']}")
    inv_ids = {x.get("id") for x in invariants if x.get("id")}
    req_ids = {x.get("requirement_id") for x in reqs if x.get("requirement_id")}
    if inv_ids != req_ids:
        errors.append(f"invariant trace ID mismatch: {sorted(inv_ids ^ req_ids)}")
    for req in reqs:
        rid = req.get("requirement_id")
        for p in req.get("artifacts", []):
            if not (root / p).exists():
                errors.append(f"requirement {rid}: missing artifact {p}")
        if set(req.get("work_packages", [])) - ids:
            errors.append(f"requirement {rid}: unknown work packages {sorted(set(req.get('work_packages', []))-ids)}")
        if not req.get("verification"):
            errors.append(f"requirement {rid}: no verification checks")

    acceptance = load_yaml(root / "manifests/acceptance_matrix.yaml", errors)
    levels = acceptance.get("release_levels", {}) if isinstance(acceptance, dict) else {}
    expected_levels = {"SPEC_BUNDLE", "PLUGIN_ALPHA", "EVOLUTION_MVP_50", "PILOT_200", "PRODUCTION_2000", "CROSS_DOMAIN_QUALIFIED"}
    if set(levels) != expected_levels:
        errors.append(f"release levels mismatch: {sorted(levels)}")
    report["development"] = {"work_packages": len(items), "layers": len(layers), "max_width": max(map(len, layers), default=0), "invariants": len(invariants), "release_levels": sorted(levels)}
    return ids


def validate_audit(root: Path, errors: list[str], report: dict[str, Any], run: bool) -> None:
    matrix = load_yaml(root / "manifests/288_lens_evolution_audit_matrix.yaml", errors)
    families = matrix.get("families", []) if isinstance(matrix, dict) else []
    lenses = [x for f in families for x in f.get("lenses", [])]
    if len(families) != EXPECTED["audit_families"] or len(lenses) != EXPECTED["audit_lenses"]:
        errors.append(f"audit shape {len(families)} families/{len(lenses)} lenses")
    if any(len(f.get("lenses", [])) != 12 for f in families):
        errors.append("each audit family must contain 12 lenses")
    ids = [x.get("lens_id") for x in lenses]
    if len(ids) != len(set(ids)):
        errors.append("duplicate audit lens IDs")
    summary = None
    if run:
        proc = subprocess.run([sys.executable, str(root / "tools/run_288_lens_evolution_audit.py"), "--root", str(root)], text=True, capture_output=True)
        if proc.returncode != 0:
            errors.append("288-lens evolution audit failed: " + (proc.stdout + "\n" + proc.stderr).strip())
        result = load_json(root / "reports/288_lens_evolution_audit_results.json", errors)
        if isinstance(result, dict):
            summary = result.get("summary")
            if summary != {"PASS": 264, "CONDITIONAL": 24, "FAIL": 0}:
                errors.append(f"unexpected 288-lens summary: {summary}")
    report["audit_288"] = summary or {"families": len(families), "lenses": len(lenses), "not_executed": not run}


def parse_frontmatter(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    return yaml.safe_load(text[4:end])


def validate_plugin(root: Path, errors: list[str], report: dict[str, Any]) -> None:
    pr = root / "plugin_blueprint/epistemic-foundry"
    manifest = load_json(pr / ".codex-plugin/plugin.json", errors)
    if isinstance(manifest, dict):
        if manifest.get("name") != "epistemic-foundry" or manifest.get("version") != VERSION:
            errors.append("plugin manifest name/version mismatch")
        for raw in manifest.get("hooks", []):
            if not (pr / raw).exists():
                errors.append(f"plugin manifest hook missing: {raw}")
        for field in ("skills", "mcpServers"):
            raw = manifest.get(field)
            if not isinstance(raw, str) or not (pr / raw).exists():
                errors.append(f"plugin manifest {field} missing: {raw}")
        if manifest.get("license") != "TBD-BEFORE-RELEASE":
            errors.append("reference blueprint must preserve explicit unreleased license conditional")

    mcp = load_json(pr / ".mcp.json", errors)
    if not isinstance(mcp, dict) or not mcp.get("mcpServers"):
        errors.append("plugin .mcp.json must declare mcpServers")
    skills = sorted((pr / "skills").glob("*/SKILL.md"))
    if len(skills) != EXPECTED["plugin_skills"]:
        errors.append(f"plugin skill count {len(skills)} != {EXPECTED['plugin_skills']}")
    skill_names: set[str] = set()
    for path in skills:
        fm = parse_frontmatter(path)
        if not isinstance(fm, dict):
            errors.append(f"{path}: missing YAML frontmatter")
            continue
        for key in ("name", "description"):
            if not fm.get(key):
                errors.append(f"{path}: frontmatter missing {key}")
        name = str(fm.get("name", ""))
        if name in skill_names:
            errors.append(f"duplicate skill name {name}")
        skill_names.add(name)

    hooks = sorted((pr / "hooks").glob("*.json"))
    if len(hooks) != EXPECTED["plugin_hooks"]:
        errors.append(f"plugin hook bundle count {len(hooks)} != {EXPECTED['plugin_hooks']}")
    for path in hooks:
        load_json(path, errors)
    for path in [pr / "bin/efoundry.mjs", *sorted((pr / "dist").glob("*.mjs"))]:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if "78" not in text or "blueprint" not in text.lower():
            errors.append(f"{path}: specification-only stub must fail closed with exit code 78")
    readme = (pr / "README_SPEC_ONLY.md").read_text(encoding="utf-8")
    if "not an implemented" not in readme.lower() and "구현" not in readme:
        errors.append("reference blueprint README must deny implementation claim")
    report["plugin_blueprint"] = {"skills": len(skills), "hook_bundles": len(hooks), "manifest_version": manifest.get("version") if isinstance(manifest, dict) else None, "status": "SPECIFICATION_ONLY"}


def validate_roles_prompts_and_text(root: Path, errors: list[str], report: dict[str, Any]) -> None:
    prompts = sorted((root / "prompts").rglob("*.md"))
    if len(prompts) != EXPECTED["prompts"]:
        errors.append(f"prompt count {len(prompts)} != {EXPECTED['prompts']}")
    for path in prompts:
        text = path.read_text(encoding="utf-8")
        if "evidence" not in text.lower() and "근거" not in text:
            errors.append(f"{path}: prompt lacks evidence grounding language")

    roles = load_yaml(root / "manifests/role_registry.yaml", errors)
    role_items = roles.get("roles", []) if isinstance(roles, dict) else []
    if len(role_items) != EXPECTED["roles"]:
        errors.append(f"role count {len(role_items)} != {EXPECTED['roles']}")
    role_ids = {r.get("role_id") for r in role_items if r.get("role_id")}
    codex_map = load_yaml(root / "adapters/codex/role_mapping.yaml", errors)
    mapped = set(codex_map.get("roles", {})) if isinstance(codex_map, dict) and isinstance(codex_map.get("roles"), dict) else set()
    if mapped != role_ids:
        errors.append(f"Codex role mapping mismatch: {sorted(mapped ^ role_ids)}")
    if isinstance(codex_map, dict):
        for rid, spec in codex_map.get("roles", {}).items():
            ref = spec.get("result_schema") if isinstance(spec, dict) else None
            if not isinstance(ref, str) or not (root / ref).exists():
                errors.append(f"Codex role {rid}: missing result schema {ref}")
    claude_profiles = sorted((root / ".claude/agents").glob("ef-*.md"))
    if len(claude_profiles) != EXPECTED["roles"]:
        errors.append(f"Claude EF role profile count {len(claude_profiles)} != {EXPECTED['roles']}")

    codex_agents = sorted((root / ".codex/agents").glob("*.toml"))
    try:
        tomllib.loads((root / ".codex/config.toml").read_text(encoding="utf-8"))
        for path in codex_agents:
            tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Codex TOML parse error: {exc}")

    forbidden_hits: list[str] = []
    placeholder_hits: list[str] = []
    secret_hits: list[str] = []
    fence_errors: list[str] = []
    active_roots = [root / x for x in ["MASTER_SPEC.md", "MASTER_EXECUTION_PROMPT.md", "AGENTS.md", "CLAUDE.md", "README.md", "docs", "research", "manifests", "schemas", "workflows", "prompts", "plugin_blueprint"]]
    paths: list[Path] = []
    for item in active_roots:
        if item.is_file():
            paths.append(item)
        elif item.exists():
            paths.extend(p for p in item.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES)
    for path in sorted(set(paths)):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if "TOMICS" in text or "tomics" in text:
            forbidden_hits.append(f"{rel}: domain-specific TOMICS token")
        cleaned = text.replace("TBD-BEFORE-RELEASE", "")
        for pat in PLACEHOLDER_PATTERNS:
            if pat.search(cleaned):
                placeholder_hits.append(f"{rel}: {pat.pattern}")
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                secret_hits.append(f"{rel}: {pat.pattern}")
        if path.suffix.lower() == ".md" and text.count("```") % 2:
            fence_errors.append(rel)
    errors.extend(f"forbidden domain token {x}" for x in forbidden_hits)
    errors.extend(f"unfinished placeholder {x}" for x in placeholder_hits)
    errors.extend(f"potential secret {x}" for x in secret_hits)
    errors.extend(f"unbalanced Markdown fence {x}" for x in fence_errors)
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if version != VERSION:
        errors.append(f"VERSION {version!r} != {VERSION}")
    report["text_and_adapters"] = {"prompts": len(prompts), "roles": len(role_items), "codex_agents": len(codex_agents), "claude_role_profiles": len(claude_profiles), "text_files_scanned": len(set(paths)), "forbidden_domain_hits": len(forbidden_hits), "placeholder_hits": len(placeholder_hits), "secret_hits": len(secret_hits), "markdown_fence_errors": len(fence_errors)}


#: Directory prefixes that are working-tree infrastructure, not shipped bundle
#: content. Version control, harness runtime state, virtualenvs, and build or
#: test caches exist only in a developer checkout, so counting them as manifest
#: inventory turns any local implementation work into a spurious FAIL.
NON_BUNDLE_PREFIXES = (
    ".git/",
    ".rah/",
    ".venv/",
    "__pycache__/",
    ".pytest_cache/",
    "build/",
    "dist/",
    # Implementation tree and harness design docs: real project content, but
    # not part of the released specification bundle inventory.
    "docs/architecture/",
    "src/",
    "tests/",
)

#: Filename suffixes that are never bundle content.
NON_BUNDLE_SUFFIXES = (".pyc", ".pyo", ".egg-info")

#: Root-level files that belong to the checkout rather than the bundle.
NON_BUNDLE_FILES = {".gitignore", "pyproject.toml"}

#: Reports this validator rewrites on every run. Their bytes change as a result
#: of validating, so hashing them against a manifest recorded before the run
#: makes a second consecutive run fail by construction. They stay in the
#: manifest inventory (they are shipped) but are exempt from the hash check.
SELF_WRITTEN_REPORTS = {
    "reports/spec_validation_results.json",
    "reports/288_lens_evolution_audit_results.json",
    "reports/216_lens_plugin_audit_results.json",
    "reports/144_lens_audit_results.json",
}


def _is_non_bundle_path(rel: str) -> bool:
    """True when `rel` is local working-tree infrastructure."""
    if rel in NON_BUNDLE_FILES:
        return True
    if any(rel == prefix.rstrip("/") or rel.startswith(prefix) for prefix in NON_BUNDLE_PREFIXES):
        return True
    if any(f"/{prefix}" in f"/{rel}" for prefix in ("__pycache__/", ".pytest_cache/")):
        return True
    return rel.endswith(NON_BUNDLE_SUFFIXES)


def validate_package_manifest(root: Path, errors: list[str], report: dict[str, Any]) -> None:
    mp, cp = root / "PACKAGE_MANIFEST.json", root / "MANIFEST.sha256"
    if not mp.exists() and not cp.exists():
        report["package_manifest"] = {"status": "not_present_prebuild"}
        return
    if not mp.exists() or not cp.exists():
        errors.append("PACKAGE_MANIFEST.json and MANIFEST.sha256 must coexist")
        return
    doc = load_json(mp, errors)
    if not isinstance(doc, dict):
        return
    excluded = {"PACKAGE_MANIFEST.json", "MANIFEST.sha256"}
    if set(doc.get("excluded_from_recursive_manifest", [])) != excluded:
        errors.append("manifest excluded set mismatch")
    listed: set[str] = set()
    mismatches: list[str] = []
    for entry in doc.get("files", []):
        rel = entry.get("path")
        if not isinstance(rel, str) or rel in listed:
            mismatches.append(f"invalid/duplicate path {rel}")
            continue
        listed.add(rel)
        path = root / rel
        if not path.exists():
            mismatches.append(f"missing {rel}")
        elif rel in SELF_WRITTEN_REPORTS:
            # Present and inventoried, but its bytes are produced by this run.
            continue
        elif sha256_file(path) != entry.get("sha256") or path.stat().st_size != entry.get("bytes"):
            mismatches.append(f"hash/size mismatch {rel}")
    actual = {
        rel
        for rel in (
            p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
        )
        if rel not in excluded and not _is_non_bundle_path(rel)
    }
    if listed != actual:
        mismatches.append(f"inventory mismatch missing={sorted(actual-listed)[:10]} extra={sorted(listed-actual)[:10]}")
    if cp.read_text(encoding="utf-8").strip().split()[0] != sha256_file(mp):
        mismatches.append("MANIFEST.sha256 mismatch")
    errors.extend(f"package manifest {x}" for x in mismatches)
    report["package_manifest"] = {"status": "valid" if not mismatches else "invalid", "files": len(listed), "mismatches": len(mismatches)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--no-audit", action="store_true")
    parser.add_argument("--json-report", type=Path, default=Path("reports/spec_validation_results.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    errors: list[str] = []
    report: dict[str, Any] = {"architecture_name": "Epistemic Foundry", "version": VERSION, "scope": "specification_bundle_and_reference_blueprint_only"}
    for rel in sorted(REQUIRED_FILES):
        if not (root / rel).exists():
            errors.append(f"missing required file {rel}")
    schemas = validate_schemas(root, errors, report)
    validate_workflows(root, schemas, errors, report)
    validate_development(root, errors, report)
    validate_audit(root, errors, report, run=not args.no_audit)
    validate_plugin(root, errors, report)
    validate_roles_prompts_and_text(root, errors, report)
    validate_package_manifest(root, errors, report)
    report["summary"] = {"status": "PASS" if not errors else "FAIL", "error_count": len(errors)}
    report["errors"] = errors
    out = args.json_report if args.json_report.is_absolute() else root / args.json_report
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        print(f"SPECIFICATION VALIDATION: FAIL ({len(errors)} errors)")
        for x in errors:
            print(f"- {x}")
        print(f"Report: {out}")
        return 1
    print("SPECIFICATION VALIDATION: PASS")
    print(f"{EXPECTED['schemas']} schemas / {EXPECTED['examples']} examples / {EXPECTED['workflows']} workflows / {EXPECTED['workflow_nodes']} nodes / {EXPECTED['work_packages']} work packages / {EXPECTED['invariants']} invariants")
    a = report.get("audit_288", {})
    print(f"288-LENS EVOLUTION AUDIT: {a.get('PASS', '?')} PASS / {a.get('CONDITIONAL', '?')} CONDITIONAL / {a.get('FAIL', '?')} FAIL")
    print(f"Report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
