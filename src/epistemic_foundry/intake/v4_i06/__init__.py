"""Genome intake, scope and falsifiability integration gate (I06).

I05 admits a hypothesis genome document that declares a scope and a falsifier;
this gate binds those declarations to the artifacts they name, refusing a genome
whose scope vector, falsifier genes or prediction genes are missing, malformed,
mis-attributed or out of the bounds the genome declared, and refusing one that
presumes an authority intake does not grant.  Every decision resolves to one
immutable, re-derivable receipt.
"""

from __future__ import annotations

from .gate import (
    ADMITTED,
    FALSIFIER_KIND,
    FINDING_CODES,
    GENOME_KIND,
    PREDICTION_KIND,
    REFUSED,
    SCOPE_KIND,
    GenomeIntakeGateError,
    gate_genome_intake,
    gate_intake_batch,
    intake_binding_findings,
    intake_status,
    require_admissible,
    verify_contract,
)

__all__ = [
    "ADMITTED",
    "FALSIFIER_KIND",
    "FINDING_CODES",
    "GENOME_KIND",
    "GenomeIntakeGateError",
    "PREDICTION_KIND",
    "REFUSED",
    "SCOPE_KIND",
    "gate_genome_intake",
    "gate_intake_batch",
    "intake_binding_findings",
    "intake_status",
    "require_admissible",
    "verify_contract",
]
