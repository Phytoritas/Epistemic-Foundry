"""Evolution Chamber: typed candidate populations that propose, never certify.

The constitutional boundary (`AGENTS.md`): evolution may propose; it may not
certify itself. Concretely, a mutation operator may not touch the fields that
carry authority — the evaluator binding, the holdout, policy, promotion state,
or prior ledger history. `mutation.py` enforces that by path, so an operator
cannot quietly rewrite the rules it is judged by.
"""

from __future__ import annotations

from .mutation import (
    AuthorityMutationRefused,
    FORBIDDEN_MUTATION_PATHS,
    apply_mutation,
    build_mutation_receipt,
)
from .run_spec import build_evolution_run_spec

__all__ = [
    "AuthorityMutationRefused",
    "FORBIDDEN_MUTATION_PATHS",
    "apply_mutation",
    "build_evolution_run_spec",
    "build_mutation_receipt",
]
